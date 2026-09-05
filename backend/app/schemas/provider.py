import uuid
from datetime import datetime, time
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import (
    ProviderDocumentStatus,
    ProviderDocumentType,
    ProviderType,
    ProviderVerificationStatus,
)

# ==============================================================================
# 3.1 Provider Profile Schemas
# ==============================================================================


class ProviderProfileResponse(BaseModel):
    """Full provider profile details for authenticated owner or admin."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    business_name: str
    provider_type: str
    description: str | None = None
    phone: str | None = None
    service_radius_km: Decimal
    rating_avg: Decimal
    rating_count: int
    verification_status: str
    is_online: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None



class ProviderProfileUpdateRequest(BaseModel):
    """Request payload to update provider profile information."""

    business_name: str | None = Field(
        default=None,
        min_length=2,
        max_length=160,
        description="Business or trading name of the provider",
    )
    provider_type: ProviderType | None = Field(
        default=None, description="Primary provider capability category"
    )
    description: str | None = Field(
        default=None, max_length=1000, description="Short business biography or notes"
    )
    phone: str | None = Field(
        default=None, min_length=7, max_length=20, description="Contact phone number"
    )
    service_radius_km: Decimal | None = Field(
        default=None,
        gt=Decimal("0.0"),
        le=Decimal("200.0"),
        description="Operating dispatch radius in kilometers (max 200 km)",
    )


class ProviderPublicResponse(BaseModel):
    """Safe, sanitized public-facing provider information."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    business_name: str
    provider_type: str
    description: str | None = None
    service_radius_km: Decimal
    rating_avg: Decimal
    rating_count: int
    is_online: bool


# ==============================================================================
# 3.2 Provider Documents Schemas
# ==============================================================================


class ProviderDocumentUploadRequest(BaseModel):
    """Request payload to submit a verification document."""

    document_type: ProviderDocumentType = Field(
        description="Category of the verification document"
    )
    file_url: str = Field(
        min_length=5,
        max_length=1024,
        description="Secure URI/URL pointing to the uploaded document",
    )
    document_number: str | None = Field(
        default=None,
        max_length=100,
        description="Official document identification number or license code",
    )


class ProviderDocumentResponse(BaseModel):
    """Document record representation."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    provider_id: uuid.UUID
    document_type: str
    file_url: str
    document_number: str | None = None
    status: str
    reviewed_by: uuid.UUID | None = None
    reviewed_at: datetime | None = None
    created_at: datetime | None = None


class ProviderDocumentListResponse(BaseModel):
    documents: list[ProviderDocumentResponse]
    total: int


class ProviderDocumentReviewRequest(BaseModel):
    """Admin review decision for a submitted document."""

    status: ProviderDocumentStatus = Field(
        description="Approval or rejection decision (APPROVED or REJECTED)"
    )
    rejection_reason: str | None = Field(
        default=None,
        max_length=500,
        description="Reason provided to the provider upon document rejection",
    )

    @model_validator(mode="after")
    def validate_review_decision(self) -> "ProviderDocumentReviewRequest":
        if self.status not in (
            ProviderDocumentStatus.APPROVED,
            ProviderDocumentStatus.REJECTED,
        ):
            raise ValueError(
                "Document review decision must be either APPROVED or REJECTED"
            )
        return self


# ==============================================================================
# 3.3 Provider Services Schemas
# ==============================================================================


class ProviderServiceCreateRequest(BaseModel):
    """Request payload to register an offered service capability."""

    service_id: uuid.UUID = Field(description="ID of the catalog service to offer")
    price_from: Decimal | None = Field(
        default=None,
        ge=Decimal("0.0"),
        description="Minimum indicative price for this service",
    )
    price_to: Decimal | None = Field(
        default=None,
        ge=Decimal("0.0"),
        description="Maximum indicative price for this service",
    )

    @model_validator(mode="after")
    def validate_price_range(self) -> "ProviderServiceCreateRequest":
        if (
            self.price_from is not None
            and self.price_to is not None
            and self.price_from > self.price_to
        ):
            raise ValueError("price_from cannot exceed price_to")
        return self


class ProviderServiceUpdateRequest(BaseModel):
    """Request payload to update pricing or active state of a service capability."""

    price_from: Decimal | None = Field(
        default=None,
        ge=Decimal("0.0"),
        description="Minimum indicative price for this service",
    )
    price_to: Decimal | None = Field(
        default=None,
        ge=Decimal("0.0"),
        description="Maximum indicative price for this service",
    )
    is_active: bool | None = Field(
        default=None, description="Whether this service is currently offered"
    )

    @model_validator(mode="after")
    def validate_price_range(self) -> "ProviderServiceUpdateRequest":
        if (
            self.price_from is not None
            and self.price_to is not None
            and self.price_from > self.price_to
        ):
            raise ValueError("price_from cannot exceed price_to")
        return self


class ProviderServiceResponse(BaseModel):
    """Provider service capability mapping with catalog details."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    provider_id: uuid.UUID
    service_id: uuid.UUID
    service_name: str
    category: str
    price_from: Decimal | None = None
    price_to: Decimal | None = None
    is_active: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ProviderServiceListResponse(BaseModel):
    services: list[ProviderServiceResponse]
    total: int


# ==============================================================================
# 3.4 Provider Availability Schemas
# ==============================================================================


class AvailabilitySlotSchema(BaseModel):
    """Single recurring weekly availability time window."""

    day_of_week: int = Field(
        ge=0,
        le=6,
        description="Day of week (0 = Monday, 1 = Tuesday, ..., 6 = Sunday)",
    )
    start_time: time = Field(description="Start time of working window (HH:MM:SS)")
    end_time: time = Field(description="End time of working window (HH:MM:SS)")
    is_active: bool = Field(
        default=True, description="Whether this time slot is active"
    )

    @model_validator(mode="after")
    def validate_time_window(self) -> "AvailabilitySlotSchema":
        if self.start_time >= self.end_time:
            raise ValueError("start_time must be strictly earlier than end_time")
        return self


class ProviderAvailabilityBatchUpdateRequest(BaseModel):
    """Payload to atomically replace the provider's complete weekly schedule."""

    slots: list[AvailabilitySlotSchema] = Field(
        description="List of weekly schedule slots"
    )

    @model_validator(mode="after")
    def validate_non_overlapping_slots(
        self,
    ) -> "ProviderAvailabilityBatchUpdateRequest":
        by_day: dict[int, list[AvailabilitySlotSchema]] = {}
        for slot in self.slots:
            if not slot.is_active:
                continue
            by_day.setdefault(slot.day_of_week, []).append(slot)

        for day, day_slots in by_day.items():
            sorted_slots = sorted(day_slots, key=lambda s: s.start_time)
            for i in range(len(sorted_slots) - 1):
                curr_slot = sorted_slots[i]
                next_slot = sorted_slots[i + 1]
                if curr_slot.end_time > next_slot.start_time:
                    raise ValueError(
                        f"Overlapping availability slots detected on day {day}: "
                        f"{curr_slot.start_time}-{curr_slot.end_time} overlaps with "
                        f"{next_slot.start_time}-{next_slot.end_time}"
                    )
        return self


class ProviderAvailabilityResponse(BaseModel):
    """Provider's weekly recurring availability schedule."""

    provider_id: uuid.UUID
    slots: list[AvailabilitySlotSchema]


# ==============================================================================
# 3.5 Online / Offline Status Schemas
# ==============================================================================


class ProviderStatusUpdateRequest(BaseModel):
    """Request payload to toggle provider live online/offline presence."""

    is_online: bool = Field(
        description="Desired presence state: True for ONLINE, False for OFFLINE"
    )


class ProviderStatusResponse(BaseModel):
    """Result of provider presence state transition."""

    provider_id: uuid.UUID
    is_online: bool
    verification_status: str
    message: str


# ==============================================================================
# 3.6 Admin Verification Schemas
# ==============================================================================


class ProviderVerificationUpdateRequest(BaseModel):
    """Admin request to transition a provider's verification status."""

    verification_status: ProviderVerificationStatus = Field(
        description="Target verification lifecycle status"
    )
    note: str | None = Field(
        default=None,
        max_length=500,
        description="Administrative review note or justification",
    )


class ProviderAdminSummary(BaseModel):
    """Summary item for administrative provider lists."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    business_name: str
    provider_type: str
    phone: str | None = None
    verification_status: str
    is_online: bool
    rating_avg: Decimal
    rating_count: int
    created_at: datetime | None = None


class ProviderAdminListResponse(BaseModel):
    providers: list[ProviderAdminSummary]
    total: int
    page: int
    page_size: int


class ProviderAdminDetailResponse(BaseModel):
    """Comprehensive provider profile view for administrative review."""

    model_config = ConfigDict(from_attributes=True)

    profile: ProviderProfileResponse
    user_email: str | None = None
    user_phone: str | None = None
    user_first_name: str | None = None
    user_last_name: str | None = None
    documents: list[ProviderDocumentResponse]
    services: list[ProviderServiceResponse]
    availability_slots: list[AvailabilitySlotSchema]


# ==============================================================================
# 3.7 Provider Dashboard & Bookings Schemas
# ==============================================================================


class ProviderDashboardMetricsResponse(BaseModel):
    """Operational KPI summary for the provider dashboard."""

    provider_id: uuid.UUID
    business_name: str
    verification_status: str
    is_online: bool
    active_bookings_count: int
    completed_bookings_count: int
    rating_avg: Decimal
    rating_count: int
    total_documents_count: int
    approved_documents_count: int
    active_services_count: int


class ProviderBookingSummaryResponse(BaseModel):
    """Assigned booking summary for provider requests list."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    booking_number: str
    status: str
    booking_type: str
    service_id: uuid.UUID
    service_name: str | None = None
    customer_id: uuid.UUID
    customer_name: str | None = None
    customer_phone: str | None = None
    problem_description: str | None = None
    requested_at: datetime | None = None
    scheduled_at: datetime | None = None
    accepted_at: datetime | None = None
    arrived_at: datetime | None = None
    completed_at: datetime | None = None


class ProviderBookingListResponse(BaseModel):
    bookings: list[ProviderBookingSummaryResponse]
    total: int

