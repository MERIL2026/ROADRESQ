import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import InspectionCondition


class InspectionItemCreate(BaseModel):
    """Payload for creating a single component inspection finding."""

    component: str = Field(..., min_length=2, max_length=100)
    condition: InspectionCondition
    finding: str | None = Field(default=None, max_length=500)
    media_url: str | None = Field(default=None, max_length=1024)
    recommended_action: str | None = Field(default=None, max_length=500)


class InspectionItemResponse(BaseModel):
    """Output representation of an inspection finding item."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    component: str
    condition: str
    finding: str | None = None
    media_url: str | None = None
    recommended_action: str | None = None


class InspectionCreateRequest(BaseModel):
    """Payload for submitting a vehicle inspection report."""

    odometer_km: int | None = Field(
        default=None, ge=0, description="Current odometer reading"
    )
    overall_notes: str | None = Field(default=None, max_length=1000)
    items: list[InspectionItemCreate] = Field(..., min_length=1)


class InspectionResponse(BaseModel):
    """Complete inspection report response."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job_card_id: uuid.UUID
    odometer_km: int | None = None
    overall_notes: str | None = None
    created_by: uuid.UUID | None = None
    created_at: datetime | None = None
    items: list[InspectionItemResponse] = []
