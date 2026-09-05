import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import BookingStatus, BookingType, LocationType


class LocationInput(BaseModel):
    latitude: float = Field(
        ..., ge=-90.0, le=90.0, description="Geographic latitude coordinate (-90 to +90)", examples=[19.0760]
    )
    longitude: float = Field(
        ..., ge=-180.0, le=180.0, description="Geographic longitude coordinate (-180 to +180)", examples=[72.8777]
    )
    address_text: str | None = Field(
        None, max_length=500, description="Human readable street address / landmark description"
    )
    landmark: str | None = Field(
        None, max_length=255, description="Nearby landmark or point of interest"
    )
    location_type: LocationType = Field(
        default=LocationType.SERVICE, description="Type of location (PICKUP, SERVICE, DESTINATION)"
    )


class LocationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    booking_id: uuid.UUID
    location_type: str
    address_text: str | None = None
    landmark: str | None = None
    latitude: float
    longitude: float
    created_at: datetime


class BookingCreateRequest(BaseModel):
    vehicle_id: uuid.UUID = Field(..., description="UUID of the customer's registered vehicle")
    service_id: uuid.UUID = Field(..., description="UUID of the requested roadside service from catalog")
    booking_type: BookingType = Field(
        default=BookingType.EMERGENCY, description="EMERGENCY or SCHEDULED service"
    )
    problem_description: str | None = Field(
        None, max_length=1000, description="Customer description of the breakdown or assistance need"
    )
    pickup_location: LocationInput = Field(
        ..., description="Pickup/breakdown location coordinates and address"
    )
    destination_location: LocationInput | None = Field(
        None, description="Optional dropoff/destination location for towing services"
    )
    scheduled_at: datetime | None = Field(
        None, description="Requested time for scheduled appointments"
    )

    @field_validator("scheduled_at")
    @classmethod
    def validate_scheduled_at(cls, v: datetime | None, info: any) -> datetime | None:
        if v is not None:
            # Scheduled time must be in the future if provided
            pass
        return v


class BookingCancelRequest(BaseModel):
    cancellation_reason: str = Field(
        ..., min_length=3, max_length=500, description="Reason for cancelling the booking"
    )


class BookingStatusUpdateRequest(BaseModel):
    status: BookingStatus = Field(
        ..., description="Target lifecycle state to transition the booking into"
    )
    notes: str | None = Field(
        None, max_length=500, description="Optional operator / provider notes for this status transition"
    )


class BookingStatusHistoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    booking_id: uuid.UUID
    status: str
    actor_user_id: uuid.UUID | None = None
    actor_role: str | None = None
    notes: str | None = None
    created_at: datetime


class BookingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    booking_number: str
    customer_id: uuid.UUID
    vehicle_id: uuid.UUID
    provider_id: uuid.UUID | None = None
    service_id: uuid.UUID
    booking_type: str
    status: str
    problem_description: str | None = None
    scheduled_at: datetime | None = None
    requested_at: datetime
    accepted_at: datetime | None = None
    arrived_at: datetime | None = None
    completed_at: datetime | None = None
    cancelled_at: datetime | None = None
    cancellation_reason: str | None = None
    created_at: datetime
    updated_at: datetime


class CustomerSummary(BaseModel):
    id: uuid.UUID
    first_name: str
    last_name: str | None = None
    phone: str
    email: str | None = None


class ProviderSummary(BaseModel):
    id: uuid.UUID
    business_name: str
    provider_type: str
    phone: str | None = None
    rating_avg: Decimal
    rating_count: int


class ServiceSummary(BaseModel):
    id: uuid.UUID
    name: str
    category: str
    base_price: Decimal | None = None
    is_emergency: bool


class VehicleSummary(BaseModel):
    id: uuid.UUID
    registration_number: str
    make: str | None = None
    model: str | None = None
    fuel_type: str | None = None
    color: str | None = None


class BookingDetailResponse(BaseModel):
    booking: BookingResponse
    customer: CustomerSummary | None = None
    provider: ProviderSummary | None = None
    service: ServiceSummary | None = None
    vehicle: VehicleSummary | None = None
    locations: list[LocationResponse] = Field(default_factory=list)
    status_history: list[BookingStatusHistoryResponse] = Field(default_factory=list)


class BookingListResponse(BaseModel):
    bookings: list[BookingResponse]
    total: int
    page: int
    page_size: int
