from datetime import datetime, timedelta, UTC
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import require_role
from app.config import get_settings
from app.db.deps import get_db
from app.models.device import Device
from app.models.device_credential import DeviceCredential
from app.models.enums import CommandKind, CredentialKind, PairingState, UserRole
from app.models.pending_command import PendingCommand
from app.schemas.common import Page
from app.schemas.device import (
    BulkProvisionCreate,
    BulkProvisionOut,
    BulkProvisionedDevice,
    DeviceCreate,
    DeviceCreateOut,
    DeviceListOut,
    DeviceOut,
)
from app.services import audit
from app.services.credentials import generate_token, hash_token
from app.services.device_scope import get_tenant_device_or_404
from app.services.tenant_repo import TenantContext, TenantRepo

router = APIRouter(prefix="/devices", tags=["devices"])


async def _create_device_with_pairing_token(
    db: AsyncSession, ctx: TenantContext, name: str
) -> tuple[Device, str]:
    repo = TenantRepo(db, ctx)
    device = repo.stamp_tenant(Device(name=name))
    db.add(device)
    await db.flush()

    settings = get_settings()
    raw_token = generate_token()
    pairing_expires_at = datetime.now(UTC) + timedelta(seconds=settings.pairing_token_ttl_seconds)
    db.add(
        DeviceCredential(
            device_id=device.id,
            kind=CredentialKind.pairing,
            token_hash=hash_token(raw_token),
            expires_at=pairing_expires_at,
        )
    )
    return device, raw_token


@router.get("", response_model=DeviceListOut)
async def list_devices(
    q: str | None = Query(default=None, description="filter by name substring"),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    ctx: TenantContext = Depends(require_role(UserRole.viewer)),
):
    repo = TenantRepo(db, ctx)
    stmt = repo.scoped(Device)
    if q:
        stmt = stmt.where(Device.name.ilike(f"%{q}%"))

    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()

    # Online first, then most-recently-seen, then name -- IMPLEMENTATION_PLAN §1.3.
    stmt = stmt.order_by(
        Device.online.desc(), Device.last_seen_at.desc().nulls_last(), Device.name.asc()
    ).limit(limit).offset(offset)
    devices = (await db.execute(stmt)).scalars().all()

    return DeviceListOut(
        items=[DeviceOut.model_validate(d) for d in devices],
        page=Page(total=total, limit=limit, offset=offset),
    )


@router.get("/{device_id}", response_model=DeviceOut)
async def get_device(
    device_id: UUID,
    db: AsyncSession = Depends(get_db),
    ctx: TenantContext = Depends(require_role(UserRole.viewer)),
):
    repo = TenantRepo(db, ctx)
    device = await repo.get_or_404(Device, device_id)
    if device is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "device not found")
    return DeviceOut.model_validate(device)


@router.post("", response_model=DeviceCreateOut, status_code=status.HTTP_201_CREATED)
async def create_device(
    body: DeviceCreate,
    db: AsyncSession = Depends(get_db),
    ctx: TenantContext = Depends(require_role(UserRole.operator)),
):
    repo = TenantRepo(db, ctx)
    device = repo.stamp_tenant(Device(name=body.name))
    db.add(device)
    await db.flush()

    settings = get_settings()
    raw_token = generate_token()
    pairing_expires_at = datetime.now(UTC) + timedelta(seconds=settings.pairing_token_ttl_seconds)
    db.add(
        DeviceCredential(
            device_id=device.id,
            kind=CredentialKind.pairing,
            token_hash=hash_token(raw_token),
            expires_at=pairing_expires_at,
        )
    )

    await audit.record(
        db, ctx, "device.create", target_device_id=device.id, payload={"name": device.name}
    )
    await db.commit()
    await db.refresh(device)
    return DeviceCreateOut(device=DeviceOut.model_validate(device), pairing_token=raw_token)


@router.post("/{device_id}/credential/rotate", response_model=DeviceCreateOut)
async def rotate_credential(
    device_id: UUID,
    db: AsyncSession = Depends(get_db),
    ctx: TenantContext = Depends(require_role(UserRole.admin)),
):
    """Issue a fresh single-use pairing token, revoking any prior credential.

    The device must re-pair with the new token; its existing live gateway
    connection (if any) is torn down because the gateway checks credential
    validity on every frame, not just at connect time (IMPLEMENTATION_PLAN §2.2).
    """
    repo = TenantRepo(db, ctx)
    device = await repo.get_or_404(Device, device_id)
    if device is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "device not found")

    now = datetime.now(UTC)
    await db.execute(
        DeviceCredential.__table__.update()
        .where(DeviceCredential.device_id == device.id, DeviceCredential.revoked_at.is_(None))
        .values(revoked_at=now)
    )

    settings = get_settings()
    raw_token = generate_token()
    db.add(
        DeviceCredential(
            device_id=device.id,
            kind=CredentialKind.pairing,
            token_hash=hash_token(raw_token),
            expires_at=now + timedelta(seconds=settings.pairing_token_ttl_seconds),
        )
    )
    device.pairing_state = PairingState.pending
    await audit.record(db, ctx, "device.credential.rotate", target_device_id=device.id)
    await db.commit()
    await db.refresh(device)
    return DeviceCreateOut(device=DeviceOut.model_validate(device), pairing_token=raw_token)


@router.post("/{device_id}/credential/revoke")
async def revoke_credential(
    device_id: UUID,
    db: AsyncSession = Depends(get_db),
    ctx: TenantContext = Depends(require_role(UserRole.admin)),
):
    repo = TenantRepo(db, ctx)
    device = await repo.get_or_404(Device, device_id)
    if device is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "device not found")

    now = datetime.now(UTC)
    await db.execute(
        DeviceCredential.__table__.update()
        .where(DeviceCredential.device_id == device.id, DeviceCredential.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    device.pairing_state = PairingState.revoked
    await audit.record(db, ctx, "device.credential.revoke", target_device_id=device.id)
    await db.commit()
    return {"ok": True}


@router.post("/bulk", response_model=BulkProvisionOut, status_code=status.HTTP_201_CREATED)
async def bulk_provision(
    body: BulkProvisionCreate,
    db: AsyncSession = Depends(get_db),
    ctx: TenantContext = Depends(require_role(UserRole.operator)),
):
    """Provision many devices at once, issuing a fresh pairing token per device.

    Provisioning means creating a `pending` device record the operator can
    hand (name + token) to someone who physically has the hardware, mirroring
    the single-device create flow for fleets. Each device gets its own unique
    token, so onboarding one unit never leaks another's credential.
    """
    if not body.names:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "names must not be empty")

    settings = get_settings()
    repo = TenantRepo(db, ctx)
    now = datetime.now(UTC)
    items: list[BulkProvisionedDevice] = []

    for name in body.names:
        device = repo.stamp_tenant(Device(name=name))
        db.add(device)
        await db.flush()
        raw_token = generate_token()
        db.add(
            DeviceCredential(
                device_id=device.id,
                kind=CredentialKind.pairing,
                token_hash=hash_token(raw_token),
                expires_at=now + timedelta(seconds=settings.pairing_token_ttl_seconds),
            )
        )
        items.append(
            BulkProvisionedDevice(
                device=DeviceOut.model_validate(device), pairing_token=raw_token
            )
        )

    await audit.record(
        db, ctx, "device.bulk_provision", payload={"names": body.names}
    )
    await db.commit()
    return BulkProvisionOut(items=items)


@router.post("/{device_id}/disable", response_model=DeviceOut)
async def disable_device(
    device_id: UUID,
    db: AsyncSession = Depends(get_db),
    ctx: TenantContext = Depends(require_role(UserRole.admin)),
):
    """Immediately refuse the device's connection even with a valid credential.

    The device model already models `disabled` as a pairing state; this is the
    operator-visible endpoint that flips it. The gateway refuses connections
    (and tears down live ones) for any device in the `disabled` state, so the
    effect is immediate.
    """
    repo = TenantRepo(db, ctx)
    device = await repo.get_or_404(Device, device_id)
    if device is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "device not found")

    device.pairing_state = PairingState.disabled
    device.online = False
    await audit.record(db, ctx, "device.disable", target_device_id=device.id)
    await db.commit()
    await db.refresh(device)
    return DeviceOut.model_validate(device)


@router.post("/{device_id}/factory-reset")
async def factory_reset(
    device_id: UUID,
    db: AsyncSession = Depends(get_db),
    ctx: TenantContext = Depends(require_role(UserRole.admin)),
):
    """Queue a factory-reset command for the device.

    Wipes local state on the device and requires re-pairing. Like other ops
    commands, this is handed to agent-gateway via PendingCommand on the
    device's next heartbeat (cross-process handoff, ARCHITECTURE.md §2) rather
    than pushed synchronously.
    """
    await get_tenant_device_or_404(db, ctx, device_id)

    command_id = f"factory_reset:{uuid4()}"
    db.add(
        PendingCommand(
            device_id=device_id, command_id=command_id, kind=CommandKind.factory_reset
        )
    )
    await audit.record(db, ctx, "device.factory_reset.request", target_device_id=device_id)
    await db.commit()
    return {"ok": True, "command_id": command_id}
