from datetime import datetime, UTC
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import require_role
from app.db.deps import get_db
from app.models.device import Device
from app.models.enums import (
    CommandKind,
    DeviceRolloutStatus,
    RolloutStatus,
    RolloutTarget,
    UserRole,
)
from app.models.pending_command import PendingCommand
from app.models.update import UpdateArtifact, UpdateRollout, UpdateRolloutDevice
from app.schemas.common import Page
from app.schemas.update import (
    DeviceUpdateListOut,
    DeviceUpdateOut,
    RolloutDeviceOut,
    UpdateArtifactCreate,
    UpdateArtifactListOut,
    UpdateArtifactOut,
    UpdateRolloutCreate,
    UpdateRolloutDetailOut,
    UpdateRolloutListOut,
    UpdateRolloutOut,
)
from app.services import audit
from app.services.device_scope import get_tenant_device_or_404
from app.services.storage import presigned_download_url
from app.services.tenant_repo import TenantContext, TenantRepo

artifact_router = APIRouter(prefix="/update-artifacts", tags=["updates"])
rollout_router = APIRouter(prefix="/update-rollouts", tags=["updates"])
device_updates_router = APIRouter(tags=["updates"])


def _scoped_artifact_repo(db: AsyncSession, ctx: TenantContext) -> TenantRepo:
    return TenantRepo(db, ctx)


@artifact_router.get("", response_model=UpdateArtifactListOut)
async def list_artifacts(
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    ctx: TenantContext = Depends(require_role(UserRole.viewer)),
):
    repo = TenantRepo(db, ctx)
    stmt = repo.scoped(UpdateArtifact)
    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    stmt = stmt.order_by(UpdateArtifact.created_at.desc()).limit(limit).offset(offset)
    rows = (await db.execute(stmt)).scalars().all()
    return UpdateArtifactListOut(
        items=[UpdateArtifactOut.model_validate(r) for r in rows],
        page=Page(total=total, limit=limit, offset=offset),
    )


@artifact_router.post("", response_model=UpdateArtifactOut, status_code=status.HTTP_201_CREATED)
async def create_artifact(
    body: UpdateArtifactCreate,
    db: AsyncSession = Depends(get_db),
    ctx: TenantContext = Depends(require_role(UserRole.operator)),
):
    """Register a new OTA artifact (a build already staged in object storage).

    storage_url is the object key of the artifact in the HQ bucket; the device
    pulls the blob from there via a presigned URL at apply time. Version is
    unique per tenant (uq_artifact_tenant_version).
    """
    repo = TenantRepo(db, ctx)
    artifact = repo.stamp_tenant(
        UpdateArtifact(
            version=body.version,
            target_board_rev=body.target_board_rev,
            storage_url=body.storage_url,
            checksum_sha256=body.checksum_sha256,
        )
    )
    db.add(artifact)
    await db.flush()
    await audit.record(
        db,
        ctx,
        "update.artifact.create",
        payload={"version": artifact.version, "board_rev": artifact.target_board_rev},
    )
    await db.commit()
    await db.refresh(artifact)
    return UpdateArtifactOut.model_validate(artifact)


async def _resolve_target_devices(
    db: AsyncSession, ctx: TenantContext, body: UpdateRolloutCreate
) -> list[Device]:
    """Determine the concrete device set a rollout targets.

    The rollout's tenant is implied by its artifact (UpdateRollout is not
    tenant-scoped), so every device resolved here is filtered to the caller's
    tenant.
    """
    repo = TenantRepo(db, ctx)
    artifact = await repo.get_or_404(UpdateArtifact, body.artifact_id)
    if artifact is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "artifact not found")

    if body.target == RolloutTarget.all:
        devices = (await db.execute(repo.scoped(Device))).scalars().all()
        return list(devices)

    if body.target == RolloutTarget.specific_devices:
        device_ids = body.target_selector.get("device_ids", [])
        if not device_ids:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "specific_devices target requires device_ids in target_selector",
            )
        devices = (
            await db.execute(repo.scoped(Device).where(Device.id.in_(device_ids)))
        ).scalars().all()
        found = {str(d.id) for d in devices}
        missing = [str(i) for i in device_ids if str(i) not in found]
        if missing:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                f"devices not found in tenant: {', '.join(missing)}",
            )
        return list(devices)

    # device_group: no group model exists yet (ARCHITECTURE), so target every
    # tenant device as a best-effort. Change when a group concept lands.
    devices = (await db.execute(repo.scoped(Device))).scalars().all()
    return list(devices)


@rollout_router.post("", response_model=UpdateRolloutOut, status_code=status.HTTP_201_CREATED)
async def create_rollout(
    body: UpdateRolloutCreate,
    db: AsyncSession = Depends(get_db),
    ctx: TenantContext = Depends(require_role(UserRole.operator)),
):
    """Stage a rollout: pick an artifact, choose the target set, enroll the
    devices. Nothing is pushed yet -- call start on it to actually dispatch."""
    devices = await _resolve_target_devices(db, ctx, body)

    rollout = UpdateRollout(
        artifact_id=body.artifact_id,
        target=body.target,
        target_selector=body.target_selector,
        status=RolloutStatus.pending,
    )
    db.add(rollout)
    await db.flush()

    # Enroll the resolved target set now, so the rollout's scope is fixed and
    # visible before it starts; start() only dispatches to already-enrolled
    # devices rather than re-resolving the selector.
    for device in devices:
        db.add(
            UpdateRolloutDevice(
                rollout_id=rollout.id,
                device_id=device.id,
                status=DeviceRolloutStatus.pending,
            )
        )

    await audit.record(
        db,
        ctx,
        "update.rollout.create",
        payload={"artifact_id": str(body.artifact_id), "target": body.target.value},
    )
    await db.commit()
    await db.refresh(rollout)
    return UpdateRolloutOut.model_validate(rollout)


@rollout_router.get("", response_model=UpdateRolloutListOut)
async def list_rollouts(
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    ctx: TenantContext = Depends(require_role(UserRole.viewer)),
):
    """Rollouts are scoped to the tenant through their artifact."""
    tenant_artifact_ids = select(UpdateArtifact.id).where(
        UpdateArtifact.tenant_id == ctx.tenant_id
    )
    stmt = select(UpdateRollout).where(UpdateRollout.artifact_id.in_(tenant_artifact_ids))
    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    stmt = stmt.order_by(UpdateRollout.id.desc()).limit(limit).offset(offset)
    rows = (await db.execute(stmt)).scalars().all()
    return UpdateRolloutListOut(
        items=[UpdateRolloutOut.model_validate(r) for r in rows],
        page=Page(total=total, limit=limit, offset=offset),
    )


async def _get_tenant_rollout(
    db: AsyncSession, ctx: TenantContext, rollout_id: UUID
) -> UpdateRollout:
    tenant_artifact_ids = select(UpdateArtifact.id).where(
        UpdateArtifact.tenant_id == ctx.tenant_id
    )
    stmt = select(UpdateRollout).where(
        UpdateRollout.id == rollout_id,
        UpdateRollout.artifact_id.in_(tenant_artifact_ids),
    )
    rollout = (await db.execute(stmt)).scalar_one_or_none()
    if rollout is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "rollout not found")
    return rollout


@rollout_router.get("/{rollout_id}", response_model=UpdateRolloutDetailOut)
async def get_rollout(
    rollout_id: UUID,
    db: AsyncSession = Depends(get_db),
    ctx: TenantContext = Depends(require_role(UserRole.viewer)),
):
    repo = TenantRepo(db, ctx)
    rollout = await _get_tenant_rollout(db, ctx, rollout_id)

    artifact = await repo.get_or_404(UpdateArtifact, rollout.artifact_id)
    device_rows = (
        await db.execute(
            select(UpdateRolloutDevice).where(UpdateRolloutDevice.rollout_id == rollout.id)
        )
    ).scalars().all()

    return UpdateRolloutDetailOut(
        rollout=UpdateRolloutOut.model_validate(rollout),
        artifact=UpdateArtifactOut.model_validate(artifact),
        devices=[RolloutDeviceOut.model_validate(d) for d in device_rows],
    )


@rollout_router.post("/{rollout_id}/start", response_model=UpdateRolloutOut)
async def start_rollout(
    rollout_id: UUID,
    db: AsyncSession = Depends(get_db),
    ctx: TenantContext = Depends(require_role(UserRole.operator)),
):
    """Begin a rollout: mark it in_progress and enqueue an apply_update
    PendingCommand for each enrolled device (delivered by agent-gateway on
    each device's next heartbeat)."""
    repo = TenantRepo(db, ctx)
    rollout = await _get_tenant_rollout(db, ctx, rollout_id)
    if rollout.status not in (RolloutStatus.pending, RolloutStatus.failed):
        raise HTTPException(status.HTTP_409_CONFLICT, f"rollout already {rollout.status.value}")

    artifact = await repo.get_or_404(UpdateArtifact, rollout.artifact_id)
    device_rows = (
        await db.execute(
            select(UpdateRolloutDevice).where(UpdateRolloutDevice.rollout_id == rollout.id)
        )
    ).scalars().all()

    rollout.status = RolloutStatus.in_progress
    rollout.started_at = datetime.now(UTC)
    download_url = presigned_download_url(artifact.storage_url)

    for d in device_rows:
        command_id = f"update:{rollout.id}:{d.device_id}"
        db.add(
            PendingCommand(
                device_id=d.device_id,
                command_id=command_id,
                kind=CommandKind.apply_update,
                payload={
                    "artifact_id": str(artifact.id),
                    "version": artifact.version,
                    "checksum_sha256": artifact.checksum_sha256,
                    "download_url": download_url,
                },
            )
        )

    await audit.record(
        db,
        ctx,
        "update.rollout.start",
        payload={"rollout_id": str(rollout.id), "version": artifact.version},
    )
    await db.commit()
    await db.refresh(rollout)
    return UpdateRolloutOut.model_validate(rollout)


@device_updates_router.get(
    "/devices/{device_id}/updates", response_model=DeviceUpdateListOut
)
async def list_device_updates(
    device_id: UUID,
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    ctx: TenantContext = Depends(require_role(UserRole.viewer)),
):
    """A device's own update history (version, per-device status, outcome)."""
    await get_tenant_device_or_404(db, ctx, device_id)

    rows = (
        await db.execute(
            select(UpdateRolloutDevice, UpdateRollout, UpdateArtifact)
            .join(UpdateRollout, UpdateRollout.id == UpdateRolloutDevice.rollout_id)
            .join(UpdateArtifact, UpdateArtifact.id == UpdateRollout.artifact_id)
            .where(UpdateRolloutDevice.device_id == device_id)
            .order_by(UpdateRolloutDevice.applied_at.desc().nulls_last())
            .limit(limit)
            .offset(offset)
        )
    ).all()
    total = (
        await db.execute(
            select(func.count())
            .select_from(UpdateRolloutDevice)
            .where(UpdateRolloutDevice.device_id == device_id)
        )
    ).scalar_one()

    items = [
        DeviceUpdateOut(
            rollout_id=rd.rollout_id,
            version=artifact.version,
            status=rd.status,
            applied_at=rd.applied_at,
            error=rd.error,
        )
        for rd, _rollout, artifact in rows
    ]
    return DeviceUpdateListOut(items=items, page=Page(total=total, limit=limit, offset=offset))
