import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class LocationCoordinate(BaseModel):
    """Geographic coordinate pair."""

    latitude: float = Field(
        ..., ge=-90.0, le=90.0, description="Latitude in decimal degrees"
    )
    longitude: float = Field(
        ..., ge=-180.0, le=180.0, description="Longitude in decimal degrees"
    )


class ProviderLocationPingRequest(BaseModel):
    """Payload for provider live GPS coordinate streaming."""

    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    accuracy_m: Decimal | None = Field(
        default=None, ge=0, description="GPS accuracy in meters"
    )
    heading: Decimal | None = Field(
        default=None, ge=0, le=360, description="Heading compass bearing"
    )
    speed_kmh: Decimal | None = Field(default=None, ge=0, description="Speed in km/h")


class ProviderLocationResponse(BaseModel):
    """Response containing provider live location point."""

    model_config = ConfigDict(from_attributes=True)

    provider_id: uuid.UUID
    latitude: float
    longitude: float
    recorded_at: datetime
    updated_at: datetime | None = None
    accuracy_m: Decimal | None = None
    heading: Decimal | None = None
    speed_kmh: Decimal | None = None


class BookingLiveTrackingResponse(BaseModel):
    """Complete live tracking state for customer and provider views."""

    booking_id: uuid.UUID
    status: str
    provider_id: uuid.UUID | None = None
    provider_location: ProviderLocationResponse | None = None
    destination_location: LocationCoordinate | None = None
    distance_km: float | None = None
    eta_minutes: int | None = None
    is_stale: bool = False
    updated_at: datetime | None = None


class ArrivalOTPGenerateResponse(BaseModel):
    """Response returned when generating/retrieving arrival OTP."""

    booking_id: uuid.UUID
    otp: str | None = None
    expires_in_seconds: int
    message: str


class ArrivalVerifyRequest(BaseModel):
    """Provider payload to verify arrival via customer OTP."""

    otp: str = Field(..., min_length=6, max_length=6, pattern=r"^[0-9]{6}$")
    latitude: float | None = Field(default=None, ge=-90.0, le=90.0)
    longitude: float | None = Field(default=None, ge=-180.0, le=180.0)
