import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class ProviderLocationPingRequest(BaseModel):
    latitude: float = Field(
        ..., ge=-90.0, le=90.0, description="Current latitude coordinate of the provider", examples=[19.0760]
    )
    longitude: float = Field(
        ..., ge=-180.0, le=180.0, description="Current longitude coordinate of the provider", examples=[72.8777]
    )


class ProviderLocationResponse(BaseModel):
    provider_id: uuid.UUID
    latitude: float
    longitude: float
    updated_at: datetime


class DispatchOfferResponse(BaseModel):
    booking_id: uuid.UUID
    booking_number: str
    service_id: uuid.UUID
    service_name: str
    service_category: str
    customer_name: str | None = None
    problem_description: str | None = None
    pickup_address: str | None = None
    pickup_latitude: float
    pickup_longitude: float
    distance_km: float | None = None
    estimated_earnings: Decimal | None = None
    expires_at: datetime
    ttl_seconds: int


class DispatchOfferListResponse(BaseModel):
    offers: list[DispatchOfferResponse]
    total: int


class DispatchAcceptRequest(BaseModel):
    pass


class DispatchRejectRequest(BaseModel):
    reason: str | None = Field(
        None, max_length=255, description="Optional reason why provider rejected this dispatch offer"
    )


class DispatchAcceptResponse(BaseModel):
    booking_id: uuid.UUID
    booking_number: str
    status: str
    message: str
