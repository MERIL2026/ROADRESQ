import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.schemas.tracking import (
    ProviderLocationPingRequest,
    ProviderLocationResponse,
)


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
        None,
        max_length=500,
        description="Optional reason for rejecting dispatch offer",
    )


class DispatchAcceptResponse(BaseModel):
    booking_id: uuid.UUID
    booking_number: str
    status: str
    message: str


__all__ = [
    "DispatchAcceptRequest",
    "DispatchAcceptResponse",
    "DispatchOfferListResponse",
    "DispatchOfferResponse",
    "DispatchRejectRequest",
    "ProviderLocationPingRequest",
    "ProviderLocationResponse",
]
