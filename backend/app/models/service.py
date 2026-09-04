from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Index, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.booking import Booking
    from app.models.provider import ProviderService


class Service(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Master catalog of road assistance and automotive services."""

    __tablename__ = "services"

    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    base_price: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2), nullable=True
    )
    is_emergency: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )

    # Relationships
    provider_services: Mapped[list["ProviderService"]] = relationship(
        "ProviderService", back_populates="service"
    )
    bookings: Mapped[list["Booking"]] = relationship(
        "Booking", back_populates="service"
    )

    __table_args__ = (
        Index("ix_services_category_active", "category", "is_active"),
    )
