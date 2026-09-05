import uuid
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.vehicle import Vehicle


class VehicleRepository:
    """Data repository for Customer Vehicles."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, vehicle: Vehicle) -> Vehicle:
        self.session.add(vehicle)
        await self.session.flush()
        return vehicle

    async def get_by_id(self, vehicle_id: uuid.UUID) -> Vehicle | None:
        stmt = select(Vehicle).where(Vehicle.id == vehicle_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id_and_user(
        self, vehicle_id: uuid.UUID, user_id: uuid.UUID
    ) -> Vehicle | None:
        stmt = select(Vehicle).where(
            Vehicle.id == vehicle_id,
            Vehicle.user_id == user_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_registration_number(
        self, registration_number: str
    ) -> Vehicle | None:
        clean_reg = registration_number.strip().upper()
        stmt = select(Vehicle).where(Vehicle.registration_number == clean_reg)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_user(self, user_id: uuid.UUID) -> Sequence[Vehicle]:
        stmt = (
            select(Vehicle)
            .where(Vehicle.user_id == user_id)
            .order_by(Vehicle.is_primary.desc(), Vehicle.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()
