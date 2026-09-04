import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from geoalchemy2 import Geography
from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, utc_now
from app.models.enums import BookingStatus, BookingType, LocationType

if TYPE_CHECKING:
    from app.models.provider import Provider
    from app.models.service import Service
    from app.models.user import User
    from app.models.vehicle import Vehicle


class Booking(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Central transaction for an emergency assistance or scheduled service request."""

    __tablename__ = "bookings"

    booking_number: Mapped[str] = mapped_column(
        String(30), unique=True, nullable=False, index=True
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    vehicle_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vehicles.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    provider_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("providers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    service_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("services.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    booking_type: Mapped[str] = mapped_column(
        String(30), nullable=False, default=BookingType.EMERGENCY.value
    )
    status: Mapped[str] = mapped_column(
        String(40), nullable=False, default=BookingStatus.REQUESTED.value
    )
    problem_description: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )
    scheduled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    arrived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancellation_reason: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )

    # Relationships
    customer: Mapped["User"] = relationship("User", back_populates="bookings")
    vehicle: Mapped["Vehicle"] = relationship("Vehicle", back_populates="bookings")
    provider: Mapped["Provider | None"] = relationship(
        "Provider", back_populates="bookings"
    )
    service: Mapped["Service"] = relationship("Service", back_populates="bookings")
    locations: Mapped[list["BookingLocation"]] = relationship(
        "BookingLocation", back_populates="booking", cascade="all, delete-orphan"
    )
    status_history: Mapped[list["BookingStatusHistory"]] = relationship(
        "BookingStatusHistory",
        back_populates="booking",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_bookings_customer_created", "customer_id", "created_at"),
        Index("ix_bookings_provider_status", "provider_id", "status"),
        Index("ix_bookings_status_requested", "status", "requested_at"),
    )


class BookingLocation(Base, UUIDPrimaryKeyMixin):
    """Pickup, service, or destination geospatial coordinates for a booking."""

    __tablename__ = "booking_locations"

    booking_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("bookings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    location_type: Mapped[str] = mapped_column(
        String(30), nullable=False, default=LocationType.SERVICE.value
    )
    address_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    location: Mapped[Any] = mapped_column(
        Geography(geometry_type="POINT", srid=4326, spatial_index=True),
        nullable=False,
    )
    landmark: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    # Relationships
    booking: Mapped["Booking"] = relationship("Booking", back_populates="locations")

    __table_args__ = (
        Index("ix_booking_locations_booking_type", "booking_id", "location_type"),
    )


class BookingStatusHistory(Base, UUIDPrimaryKeyMixin):
    """Immutable log of booking status transitions for timeline and audit."""

    __tablename__ = "booking_status_history"

    booking_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("bookings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    from_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    to_status: Mapped[str] = mapped_column(String(40), nullable=False)
    changed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    # Relationships
    booking: Mapped["Booking"] = relationship(
        "Booking", back_populates="status_history"
    )

    __table_args__ = (
        Index("ix_booking_status_history_booking_created", "booking_id", "created_at"),
    )
