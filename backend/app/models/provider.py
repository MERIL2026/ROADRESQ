import uuid
from datetime import datetime, time
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, utc_now
from app.models.enums import (
    ProviderDocumentStatus,
    ProviderDocumentType,
    ProviderType,
    ProviderVerificationStatus,
)

if TYPE_CHECKING:
    from app.models.booking import Booking
    from app.models.service import Service
    from app.models.user import User


class Provider(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Service providers, mechanics, garages, and towing operators."""

    __tablename__ = "providers"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    business_name: Mapped[str] = mapped_column(String(160), nullable=False)
    provider_type: Mapped[str] = mapped_column(
        String(40), nullable=False, default=ProviderType.MECHANIC.value
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    service_radius_km: Mapped[Decimal] = mapped_column(
        Numeric(6, 2), default=Decimal("15.00"), nullable=False
    )
    rating_avg: Mapped[Decimal] = mapped_column(
        Numeric(3, 2), default=Decimal("0.00"), nullable=False
    )
    rating_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    verification_status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default=ProviderVerificationStatus.PENDING.value,
    )
    is_online: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="provider_profile")
    documents: Mapped[list["ProviderDocument"]] = relationship(
        "ProviderDocument", back_populates="provider", cascade="all, delete-orphan"
    )
    services: Mapped[list["ProviderService"]] = relationship(
        "ProviderService", back_populates="provider", cascade="all, delete-orphan"
    )
    availability: Mapped[list["ProviderAvailability"]] = relationship(
        "ProviderAvailability",
        back_populates="provider",
        cascade="all, delete-orphan",
    )
    bookings: Mapped[list["Booking"]] = relationship(
        "Booking", back_populates="provider"
    )

    __table_args__ = (
        Index("ix_providers_verification_online", "verification_status", "is_online"),
        Index("ix_providers_type", "provider_type"),
    )


class ProviderDocument(Base, UUIDPrimaryKeyMixin):
    """Uploaded verification documents for provider onboarding."""

    __tablename__ = "provider_documents"

    provider_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("providers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    document_type: Mapped[str] = mapped_column(
        String(50), nullable=False, default=ProviderDocumentType.IDENTITY.value
    )
    file_url: Mapped[str] = mapped_column(Text, nullable=False)
    document_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default=ProviderDocumentStatus.PENDING.value,
    )
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    # Relationships
    provider: Mapped["Provider"] = relationship("Provider", back_populates="documents")

    __table_args__ = (
        Index("ix_provider_documents_provider_status", "provider_id", "status"),
        Index("ix_provider_documents_type", "document_type"),
    )


class ProviderService(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Mapping of services offered by a provider with reference pricing."""

    __tablename__ = "provider_services"

    provider_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("providers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    service_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("services.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    price_from: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    price_to: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    provider: Mapped["Provider"] = relationship("Provider", back_populates="services")
    service: Mapped["Service"] = relationship(
        "Service", back_populates="provider_services"
    )

    __table_args__ = (
        UniqueConstraint(
            "provider_id",
            "service_id",
            name="uq_provider_services_provider_service",
        ),
        Index("ix_provider_services_service_active", "service_id", "is_active"),
    )


class ProviderAvailability(Base, UUIDPrimaryKeyMixin):
    """Recurring weekly schedule windows for a service provider."""

    __tablename__ = "provider_availability"

    provider_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("providers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    day_of_week: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    # Relationships
    provider: Mapped["Provider"] = relationship(
        "Provider", back_populates="availability"
    )

    __table_args__ = (
        Index("ix_provider_availability_provider_day", "provider_id", "day_of_week"),
    )
