import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPKMixin


class DeviceLocation(Base, UUIDPKMixin, TimestampMixin):
    """A single reported device position, stored as a time-series.

    Mirrors the pattern of other device-scoped child tables (telemetry_sample,
    log_bundle, ...): no tenant_id column because tenant scoping happens via
    the parent device at the query layer (device_scope.py). `captured_at` is
    the device-side timestamp and is stored verbatim so positions taken during
    a network partition keep their true time.
    """

    __tablename__ = "device_location"
    __table_args__ = (
        Index("ix_device_location_device_captured", "device_id", "captured_at"),
    )

    device_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("device.id", ondelete="CASCADE"), index=True
    )
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    altitude_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    accuracy_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    # e.g. "gps", "wifi", "cell", "manual"
    source: Mapped[str | None] = mapped_column(String, nullable=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
