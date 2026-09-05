import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class ServiceResponse(BaseModel):
    """Platform catalog service details."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    category: str
    description: str | None = None
    base_price: Decimal | None = None
    is_emergency: bool
    is_active: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None



class ServiceListResponse(BaseModel):
    services: list[ServiceResponse]
    total: int
