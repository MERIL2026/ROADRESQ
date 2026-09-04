import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Index, Integer, SmallInteger, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.booking import Booking
    from app.models.user import User


class Vehicle(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Customer-owned vehicles registered on the platform."""

    __tablename__ = "vehicles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    registration_number: Mapped[str] = mapped_column(
        String(30), unique=True, nullable=False
    )
    make: Mapped[str | None] = mapped_column(String(80), nullable=True)
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    variant: Mapped[str | None] = mapped_column(String(100), nullable=True)
    fuel_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    year: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    color: Mapped[str | None] = mapped_column(String(50), nullable=True)
    vin: Mapped[str | None] = mapped_column(String(100), nullable=True)
    odometer_km: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="vehicles")
    bookings: Mapped[list["Booking"]] = relationship(
        "Booking", back_populates="vehicle"
    )

    __table_args__ = (
        Index("ix_vehicles_registration_number", "registration_number"),
    )
