import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import EstimateStatus


class EstimateItemCreate(BaseModel):
    """Line item creation specification for an estimate."""

    description: str = Field(..., min_length=2, max_length=255)
    quantity: Decimal = Field(
        default=Decimal("1.00"), gt=Decimal("0.00"), decimal_places=2
    )
    unit_price: Decimal = Field(..., ge=Decimal("0.00"), decimal_places=2)
    tax_rate: Decimal = Field(
        default=Decimal("0.00"),
        ge=Decimal("0.00"),
        le=Decimal("100.00"),
        decimal_places=2,
    )


class EstimateItemResponse(BaseModel):
    """Output representation of an estimate line item."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    description: str
    quantity: Decimal
    unit_price: Decimal
    tax_rate: Decimal
    line_total: Decimal


class EstimateCreateRequest(BaseModel):
    """Payload for creating a new estimate."""

    items: list[EstimateItemCreate] = Field(..., min_length=1)
    discount_amount: Decimal = Field(
        default=Decimal("0.00"), ge=Decimal("0.00"), decimal_places=2
    )


class EstimateReviseRequest(BaseModel):
    """Payload for submitting a revised estimate."""

    items: list[EstimateItemCreate] = Field(..., min_length=1)
    discount_amount: Decimal = Field(
        default=Decimal("0.00"), ge=Decimal("0.00"), decimal_places=2
    )
    revision_notes: str | None = Field(default=None, max_length=500)


class EstimateRejectRequest(BaseModel):
    """Customer rejection payload."""

    rejection_reason: str = Field(..., min_length=3, max_length=500)


class EstimateResponse(BaseModel):
    """Complete estimate details response."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job_card_id: uuid.UUID
    estimate_number: str
    subtotal: Decimal
    tax_amount: Decimal
    discount_amount: Decimal
    total_amount: Decimal
    status: EstimateStatus
    approved_by: uuid.UUID | None = None
    approved_at: datetime | None = None
    rejected_by: uuid.UUID | None = None
    rejected_at: datetime | None = None
    rejection_reason: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    items: list[EstimateItemResponse] = []
