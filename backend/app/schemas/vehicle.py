import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import VehicleFuelType


class VehicleCreateRequest(BaseModel):
    registration_number: str = Field(
        ...,
        min_length=3,
        max_length=30,
        description="Vehicle registration or license plate number",
        examples=["MH01AB1234"],
    )
    make: str | None = Field(
        None, max_length=80, description="Vehicle manufacturer make", examples=["Hyundai"]
    )
    model: str | None = Field(
        None, max_length=100, description="Vehicle model name", examples=["Creta"]
    )
    variant: str | None = Field(
        None, max_length=100, description="Vehicle variant/trim", examples=["SX(O)"]
    )
    fuel_type: VehicleFuelType | None = Field(
        None, description="Vehicle fuel/powertrain type", examples=[VehicleFuelType.PETROL]
    )
    year: int | None = Field(
        None, ge=1970, le=2030, description="Manufacturing year", examples=[2022]
    )
    color: str | None = Field(
        None, max_length=50, description="Exterior vehicle color", examples=["Polar White"]
    )
    vin: str | None = Field(
        None, max_length=100, description="Vehicle identification number"
    )
    odometer_km: int | None = Field(
        None, ge=0, description="Current odometer reading in kilometers"
    )
    is_primary: bool = Field(
        default=False, description="Whether this vehicle is set as default/primary"
    )


class VehicleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    registration_number: str
    make: str | None = None
    model: str | None = None
    variant: str | None = None
    fuel_type: str | None = None
    year: int | None = None
    color: str | None = None
    vin: str | None = None
    odometer_km: int | None = None
    is_primary: bool
    created_at: datetime
    updated_at: datetime


class VehicleListResponse(BaseModel):
    vehicles: list[VehicleResponse]
    total: int
