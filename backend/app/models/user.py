from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import UserRole, UserStatus

if TYPE_CHECKING:
    from app.models.booking import Booking
    from app.models.provider import Provider
    from app.models.vehicle import Vehicle


class User(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """User accounts across all platform roles."""

    __tablename__ = "users"

    role: Mapped[str] = mapped_column(
        String(30), nullable=False, default=UserRole.CUSTOMER.value
    )
    first_name: Mapped[str] = mapped_column(String(80), nullable=False)
    last_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    phone: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    password_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default=UserStatus.ACTIVE.value
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    vehicles: Mapped[list["Vehicle"]] = relationship(
        "Vehicle", back_populates="user", cascade="all, delete-orphan"
    )
    provider_profile: Mapped["Provider | None"] = relationship(
        "Provider", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    bookings: Mapped[list["Booking"]] = relationship(
        "Booking", back_populates="customer"
    )

    __table_args__ = (Index("ix_users_role_status", "role", "status"),)
