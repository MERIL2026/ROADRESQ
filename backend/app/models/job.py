import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from geoalchemy2 import Geography
from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, utc_now
from app.models.enums import EstimateStatus, InspectionCondition, JobStatus

if TYPE_CHECKING:
    from app.models.booking import Booking
    from app.models.provider import Provider
    from app.models.user import User


class ProviderLocationUpdate(Base, UUIDPrimaryKeyMixin):
    """Historical GPS telemetry coordinate stream for active providers on a booking."""

    __tablename__ = "provider_location_updates"

    provider_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("providers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    booking_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("bookings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    location: Mapped[Geography] = mapped_column(
        Geography(geometry_type="POINT", srid=4326, spatial_index=True),
        nullable=False,
    )
    accuracy_m: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)
    heading: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    speed_kmh: Mapped[Decimal | None] = mapped_column(Numeric(7, 2), nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    # Relationships
    provider: Mapped["Provider"] = relationship("Provider", lazy="selectin")
    booking: Mapped["Booking"] = relationship(
        "Booking", back_populates="location_updates", lazy="selectin"
    )

    __table_args__ = (
        Index(
            "ix_provider_location_updates_booking_recorded",
            "booking_id",
            "recorded_at",
        ),
        Index(
            "ix_provider_location_updates_provider_recorded",
            "provider_id",
            "recorded_at",
        ),
    )


class JobCard(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Operational work order initialized when provider arrives at customer booking."""

    __tablename__ = "job_cards"

    booking_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("bookings.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    provider_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("providers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    mechanic_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    job_status: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        default=JobStatus.INSPECTION.value,
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    customer_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    completion_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    completion_evidence_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    booking: Mapped["Booking"] = relationship(
        "Booking", back_populates="job_card", lazy="selectin"
    )
    provider: Mapped["Provider"] = relationship("Provider", lazy="selectin")
    mechanic: Mapped["User | None"] = relationship(
        "User", foreign_keys=[mechanic_user_id], lazy="selectin"
    )
    inspections: Mapped[list["Inspection"]] = relationship(
        "Inspection",
        back_populates="job_card",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="Inspection.created_at.asc()",
    )
    estimates: Mapped[list["Estimate"]] = relationship(
        "Estimate",
        back_populates="job_card",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="Estimate.created_at.asc()",
    )

    __table_args__ = (
        Index("ix_job_cards_provider_status", "provider_id", "job_status"),
    )


class Inspection(Base, UUIDPrimaryKeyMixin):
    """Vehicle multi-point physical diagnostic and inspection session."""

    __tablename__ = "inspections"

    job_card_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("job_cards.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    odometer_km: Mapped[int | None] = mapped_column(Integer, nullable=True)
    overall_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    # Relationships
    job_card: Mapped["JobCard"] = relationship(
        "JobCard", back_populates="inspections", lazy="selectin"
    )
    creator: Mapped["User | None"] = relationship(
        "User", foreign_keys=[created_by], lazy="selectin"
    )
    items: Mapped[list["InspectionItem"]] = relationship(
        "InspectionItem",
        back_populates="inspection",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class InspectionItem(Base, UUIDPrimaryKeyMixin):
    """Specific component finding and visual evidence for an inspection."""

    __tablename__ = "inspection_items"

    inspection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("inspections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    component: Mapped[str] = mapped_column(String(100), nullable=False)
    condition: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        default=InspectionCondition.GOOD.value,
    )
    finding: Mapped[str | None] = mapped_column(Text, nullable=True)
    media_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommended_action: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    inspection: Mapped["Inspection"] = relationship(
        "Inspection", back_populates="items", lazy="selectin"
    )


class Estimate(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Customer-facing proposed job quote with parts, labor, taxes, and approvals."""

    __tablename__ = "estimates"

    job_card_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("job_cards.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    estimate_number: Mapped[str] = mapped_column(
        String(30), unique=True, nullable=False, index=True
    )
    subtotal: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0.00")
    )
    tax_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0.00")
    )
    discount_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0.00")
    )
    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0.00")
    )
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default=EstimateStatus.PENDING_APPROVAL.value,
    )
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    rejected_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    rejected_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    job_card: Mapped["JobCard"] = relationship(
        "JobCard", back_populates="estimates", lazy="selectin"
    )
    approver: Mapped["User | None"] = relationship(
        "User", foreign_keys=[approved_by], lazy="selectin"
    )
    rejecter: Mapped["User | None"] = relationship(
        "User", foreign_keys=[rejected_by], lazy="selectin"
    )
    items: Mapped[list["EstimateItem"]] = relationship(
        "EstimateItem",
        back_populates="estimate",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (Index("ix_estimates_job_card_status", "job_card_id", "status"),)


class EstimateItem(Base, UUIDPrimaryKeyMixin):
    """Itemized part, labor, or service line entry in an estimate."""

    __tablename__ = "estimate_items"

    estimate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("estimates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, default=Decimal("1.00")
    )
    unit_price: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0.00")
    )
    tax_rate: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, default=Decimal("0.00")
    )
    line_total: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0.00")
    )

    # Relationships
    estimate: Mapped["Estimate"] = relationship(
        "Estimate", back_populates="items", lazy="selectin"
    )
