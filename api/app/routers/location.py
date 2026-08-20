from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import require_role
from app.db.deps import get_db
from app.models.device_location import DeviceLocation
from app.models.enums import UserRole
from app.schemas.common import Page
from app.schemas.location import LocationIn, LocationListOut, LocationOut
from app.services.device_scope import get_tenant_device_or_404
from app.services.tenant_repo import TenantContext

router = APIRouter(prefix="/devices/{device_id}/location", tags=["location"])


@router.get("", response_model=LocationOut)
async def get_latest_location(
    device_id: UUID,
    db: AsyncSession = Depends(get_db),
    ctx: TenantContext = Depends(require_role(UserRole.viewer)),
):
    """Most recently captured position for a device (no fix -> 404)."""
    await get_tenant_device_or_404(db, ctx, device_id)

    stmt = (
        select(DeviceLocation)
        .where(DeviceLocation.device_id == device_id)
        .order_by(DeviceLocation.captured_at.desc())
        .limit(1)
    )
    loc = (await db.execute(stmt)).scalar_one_or_none()
    if loc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no location fix recorded")
    return LocationOut.model_validate(loc)


@router.get("/history", response_model=LocationListOut)
async def list_location_history(
    device_id: UUID,
    limit: int = Query(default=50, le=500),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    ctx: TenantContext = Depends(require_role(UserRole.viewer)),
):
    await get_tenant_device_or_404(db, ctx, device_id)

    stmt = select(DeviceLocation).where(DeviceLocation.device_id == device_id)
    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    stmt = stmt.order_by(DeviceLocation.captured_at.desc()).limit(limit).offset(offset)
    rows = (await db.execute(stmt)).scalars().all()

    return LocationListOut(
        items=[LocationOut.model_validate(r) for r in rows],
        page=Page(total=total, limit=limit, offset=offset),
    )


@router.post("", response_model=LocationOut, status_code=status.HTTP_201_CREATED)
async def ingest_location(
    device_id: UUID,
    body: LocationIn,
    db: AsyncSession = Depends(get_db),
    ctx: TenantContext = Depends(require_role(UserRole.operator)),
):
    """Ingest a single position fix for a device (device-side timestamp kept)."""
    await get_tenant_device_or_404(db, ctx, device_id)

    loc = DeviceLocation(
        device_id=device_id,
        latitude=body.latitude,
        longitude=body.longitude,
        altitude_m=body.altitude_m,
        accuracy_m=body.accuracy_m,
        source=body.source,
        captured_at=body.captured_at,
    )
    db.add(loc)
    await db.commit()
    await db.refresh(loc)
    return LocationOut.model_validate(loc)
