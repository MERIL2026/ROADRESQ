import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError
from app.models.enums import AuditAction
from app.models.vehicle import Vehicle
from app.repositories.vehicle import VehicleRepository
from app.schemas.vehicle import VehicleCreateRequest, VehicleListResponse, VehicleResponse
from app.services.audit_service import record_audit_event


class VehicleService:
    """Domain service for customer vehicle registration and management."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.vehicle_repo = VehicleRepository(session)

    async def register_vehicle(
        self,
        user_id: uuid.UUID,
        data: VehicleCreateRequest,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> VehicleResponse:
        clean_reg = data.registration_number.strip().upper()
        existing = await self.vehicle_repo.get_by_registration_number(clean_reg)
        if existing:
            raise ConflictError(
                message="A vehicle with this registration number is already registered.",
                code="VEHICLE_ALREADY_EXISTS",
            )

        vehicle = Vehicle(
            id=uuid.uuid4(),
            user_id=user_id,
            registration_number=clean_reg,
            make=data.make.strip() if data.make else None,
            model=data.model.strip() if data.model else None,
            variant=data.variant.strip() if data.variant else None,
            fuel_type=data.fuel_type.value if data.fuel_type else None,
            year=data.year,
            color=data.color.strip() if data.color else None,
            vin=data.vin.strip().upper() if data.vin else None,
            odometer_km=data.odometer_km,
            is_primary=data.is_primary,
        )

        created_vehicle = await self.vehicle_repo.create(vehicle)

        await record_audit_event(
            session=self.session,
            action=AuditAction.CREATE.value,
            entity_type="Vehicle",
            entity_id=created_vehicle.id,
            actor_user_id=user_id,
            new_data={
                "registration_number": created_vehicle.registration_number,
                "make": created_vehicle.make,
                "model": created_vehicle.model,
            },
            ip_address=ip_address,
            user_agent=user_agent,
        )

        return VehicleResponse.model_validate(created_vehicle)

    async def list_vehicles(self, user_id: uuid.UUID) -> VehicleListResponse:
        vehicles = await self.vehicle_repo.list_by_user(user_id)
        items = [VehicleResponse.model_validate(v) for v in vehicles]
        return VehicleListResponse(vehicles=items, total=len(items))

    async def get_vehicle(self, vehicle_id: uuid.UUID, user_id: uuid.UUID) -> VehicleResponse:
        vehicle = await self.vehicle_repo.get_by_id_and_user(vehicle_id, user_id)
        if not vehicle:
            raise NotFoundError(
                message="Vehicle not found or not owned by user.",
                code="VEHICLE_NOT_FOUND",
            )
        return VehicleResponse.model_validate(vehicle)
