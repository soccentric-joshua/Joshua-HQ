from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.enums import DeviceRolloutStatus, RolloutStatus, RolloutTarget
from app.schemas.common import Page


class UpdateArtifactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    version: str
    target_board_rev: str
    storage_url: str
    checksum_sha256: str
    created_at: datetime


class UpdateArtifactListOut(BaseModel):
    items: list[UpdateArtifactOut]
    page: Page


class UpdateArtifactCreate(BaseModel):
    version: str
    target_board_rev: str
    storage_url: str
    checksum_sha256: str


class UpdateRolloutOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    artifact_id: UUID
    target: RolloutTarget
    target_selector: dict[str, Any]
    status: RolloutStatus
    started_at: datetime | None
    completed_at: datetime | None


class UpdateRolloutListOut(BaseModel):
    items: list[UpdateRolloutOut]
    page: Page


class UpdateRolloutCreate(BaseModel):
    artifact_id: UUID
    target: RolloutTarget = RolloutTarget.all
    # {"device_ids": [...], "group": "..."} when target != all
    target_selector: dict[str, Any] = {}


class RolloutDeviceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    device_id: UUID
    status: DeviceRolloutStatus
    applied_at: datetime | None
    error: str | None


class UpdateRolloutDetailOut(BaseModel):
    rollout: UpdateRolloutOut
    artifact: UpdateArtifactOut
    devices: list[RolloutDeviceOut]


class DeviceUpdateOut(BaseModel):
    """A device's own rollout history (join across rollout_device + rollout)."""

    rollout_id: UUID
    version: str
    status: DeviceRolloutStatus
    applied_at: datetime | None
    error: str | None


class DeviceUpdateListOut(BaseModel):
    items: list[DeviceUpdateOut]
    page: Page
