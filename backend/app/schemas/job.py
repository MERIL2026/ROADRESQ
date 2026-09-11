import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import JobStatus
from app.schemas.estimate import EstimateResponse
from app.schemas.inspection import InspectionResponse


class JobCardCreateRequest(BaseModel):
    """Payload to manually or explicitly initiate a JobCard."""

    mechanic_user_id: uuid.UUID | None = None
    customer_notes: str | None = Field(default=None, max_length=1000)
    provider_notes: str | None = Field(default=None, max_length=1000)


class JobCardStatusUpdateRequest(BaseModel):
    """Payload for updating JobCard operational status."""

    status: JobStatus
    notes: str | None = Field(default=None, max_length=500)


class JobCardCompleteRequest(BaseModel):
    """Payload for concluding roadside assistance execution."""

    completion_notes: str = Field(..., min_length=5, max_length=1000)
    completion_evidence_url: str | None = Field(default=None, max_length=1024)


class JobCardResponse(BaseModel):
    """Operational work order details response."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    booking_id: uuid.UUID
    provider_id: uuid.UUID
    mechanic_user_id: uuid.UUID | None = None
    job_status: JobStatus
    started_at: datetime | None = None
    completed_at: datetime | None = None
    customer_notes: str | None = None
    provider_notes: str | None = None
    completion_notes: str | None = None
    completion_evidence_url: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    inspections: list[InspectionResponse] = []
    estimates: list[EstimateResponse] = []
