from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import Page


class LocationIn(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    altitude_m: float | None = None
    accuracy_m: float | None = Field(default=None, ge=0)
    source: str | None = None
    captured_at: datetime


class LocationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    device_id: UUID
    latitude: float
    longitude: float
    altitude_m: float | None
    accuracy_m: float | None
    source: str | None
    captured_at: datetime
    created_at: datetime


class LocationListOut(BaseModel):
    items: list[LocationOut]
    page: Page
