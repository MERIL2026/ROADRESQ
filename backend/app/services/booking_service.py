import uuid
from datetime import UTC, datetime
from typing import Any, ClassVar

from geoalchemy2.elements import WKTElement
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import (
    ForbiddenError,
    NotFoundError,
    ValidationError,
)
from app.core.redis import RedisClient, redis_client
from app.models.booking import Booking, BookingLocation
from app.models.enums import (
    AuditAction,
    BookingStatus,
    BookingType,
    LocationType,
    UserRole,
    UserStatus,
)
from app.repositories.booking import BookingRepository
from app.repositories.provider import ProviderRepository
from app.repositories.service import ServiceRepository
from app.repositories.user import UserRepository
from app.repositories.vehicle import VehicleRepository
from app.schemas.booking import (
    BookingCancelRequest,
    BookingCreateRequest,
    BookingDetailResponse,
    BookingListResponse,
    BookingResponse,
    BookingStatusHistoryResponse,
    BookingStatusUpdateRequest,
    CustomerSummary,
    LocationResponse,
    ProviderSummary,
    ServiceSummary,
    VehicleSummary,
)
from app.services.audit_service import record_audit_event


class BookingService:
    """Domain service managing the Booking lifecycle, state machine, and customer requests."""

    # Explicit State Machine: Current State -> Set of Allowed Target States
    ALLOWED_TRANSITIONS: ClassVar[dict[str, set[str]]] = {
        BookingStatus.REQUESTED.value: {
            BookingStatus.SEARCHING.value,
            BookingStatus.CANCELLED.value,
        },
        BookingStatus.SEARCHING.value: {
            BookingStatus.PROVIDER_ASSIGNED.value,
            BookingStatus.EXPIRED.value,
            BookingStatus.CANCELLED.value,
        },
        BookingStatus.PROVIDER_ASSIGNED.value: {
            BookingStatus.ACCEPTED.value,
            BookingStatus.SEARCHING.value,
            BookingStatus.CANCELLED.value,
        },
        BookingStatus.ACCEPTED.value: {
            BookingStatus.ON_THE_WAY.value,
            BookingStatus.CANCELLED.value,
        },
        BookingStatus.ON_THE_WAY.value: {
            BookingStatus.ARRIVED.value,
            BookingStatus.CANCELLED.value,
        },
        BookingStatus.ARRIVED.value: {
            BookingStatus.INSPECTION.value,
            BookingStatus.IN_PROGRESS.value,
            BookingStatus.CANCELLED.value,
        },
        BookingStatus.INSPECTION.value: {
            BookingStatus.IN_PROGRESS.value,
            BookingStatus.CANCELLED.value,
        },
        BookingStatus.IN_PROGRESS.value: {
            BookingStatus.COMPLETED.value,
        },
        BookingStatus.EXPIRED.value: {
            BookingStatus.SEARCHING.value,  # Retry dispatch
        },
        BookingStatus.COMPLETED.value: set(),  # Terminal state
        BookingStatus.CANCELLED.value: set(),  # Terminal state
    }

    def __init__(
        self, session: AsyncSession, redis: RedisClient | None = None
    ) -> None:
        self.session = session
        self.redis = redis or redis_client
        self.booking_repo = BookingRepository(session)
        self.user_repo = UserRepository(session)
        self.vehicle_repo = VehicleRepository(session)
        self.catalog_repo = ServiceRepository(session)
        self.provider_repo = ProviderRepository(session)

    @staticmethod
    def _generate_booking_number() -> str:
        """Generates human-readable unique booking number: BK-YYYYMMDD-XXXX."""
        date_part = datetime.now(UTC).strftime("%Y%m%d")
        rand_part = uuid.uuid4().hex[:6].upper()
        return f"BK-{date_part}-{rand_part}"

    async def create_booking(
        self,
        customer_id: uuid.UUID,
        data: BookingCreateRequest,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> BookingResponse:
        # 1. Validate Customer
        user = await self.user_repo.get_by_id(customer_id)
        if not user or user.status != UserStatus.ACTIVE.value:
            raise ForbiddenError(
                message="User account is inactive or not found.",
                code="USER_INACTIVE",
            )

        # 2. Validate Vehicle Ownership
        vehicle = await self.vehicle_repo.get_by_id_and_user(
            vehicle_id=data.vehicle_id, user_id=customer_id
        )
        if not vehicle:
            raise NotFoundError(
                message="Vehicle not found or does not belong to the authenticated customer.",
                code="VEHICLE_NOT_FOUND",
            )

        # 3. Validate Service Catalog
        service = await self.catalog_repo.get_by_id(data.service_id)
        if not service or not service.is_active:
            raise ValidationError(
                message="The requested roadside service is inactive or not found.",
                code="SERVICE_NOT_AVAILABLE",
            )

        # 4. Create Locations
        locations: list[BookingLocation] = []

        # Pickup / Breakdown location
        p_lat = data.pickup_location.latitude
        p_lon = data.pickup_location.longitude
        pickup_loc = BookingLocation(
            id=uuid.uuid4(),
            location_type=LocationType.PICKUP.value
            if data.booking_type == BookingType.EMERGENCY
            else LocationType.SERVICE.value,
            address_text=data.pickup_location.address_text,
            landmark=data.pickup_location.landmark,
            location=WKTElement(f"POINT({p_lon} {p_lat})", srid=4326),
        )
        locations.append(pickup_loc)

        # Optional Destination location
        if data.destination_location:
            d_lat = data.destination_location.latitude
            d_lon = data.destination_location.longitude
            dest_loc = BookingLocation(
                id=uuid.uuid4(),
                location_type=LocationType.DESTINATION.value,
                address_text=data.destination_location.address_text,
                landmark=data.destination_location.landmark,
                location=WKTElement(f"POINT({d_lon} {d_lat})", srid=4326),
            )
            locations.append(dest_loc)

        # 5. Create Booking
        booking_number = self._generate_booking_number()
        booking = Booking(
            id=uuid.uuid4(),
            booking_number=booking_number,
            customer_id=customer_id,
            vehicle_id=data.vehicle_id,
            service_id=data.service_id,
            booking_type=data.booking_type.value,
            status=BookingStatus.REQUESTED.value,
            problem_description=data.problem_description.strip()
            if data.problem_description
            else None,
            scheduled_at=data.scheduled_at,
        )

        created_booking = await self.booking_repo.create_booking(
            booking=booking, locations=locations
        )

        # 6. Record Audit Log
        await record_audit_event(
            session=self.session,
            action=AuditAction.CREATE.value,
            entity_type="Booking",
            entity_id=created_booking.id,
            actor_user_id=customer_id,
            new_data={
                "booking_number": created_booking.booking_number,
                "service_id": str(data.service_id),
                "vehicle_id": str(data.vehicle_id),
                "status": created_booking.status,
            },
            ip_address=ip_address,
            user_agent=user_agent,
        )

        return BookingResponse.model_validate(created_booking)

    async def get_booking_details(
        self,
        booking_id: uuid.UUID,
        user_id: uuid.UUID,
        user_role: str,
    ) -> BookingDetailResponse:
        booking = await self.booking_repo.get_by_id_with_relations(booking_id)
        if not booking:
            raise NotFoundError(
                message="Booking not found.",
                code="BOOKING_NOT_FOUND",
            )

        # IDOR Authorization Guard
        if user_role == UserRole.CUSTOMER.value and booking.customer_id != user_id:
            raise ForbiddenError(
                message="You are not authorized to access this booking.",
                code="FORBIDDEN",
            )

        if user_role == UserRole.PROVIDER.value:
            provider = await self.provider_repo.get_by_user_id(user_id)
            if not provider or (booking.provider_id is not None and booking.provider_id != provider.id):
                raise ForbiddenError(
                    message="You are not authorized to view this booking.",
                    code="FORBIDDEN",
                )

        # Extract locations with lat/lon
        loc_responses: list[LocationResponse] = []
        for loc in booking.locations:
            lat, lon = BookingRepository.extract_coordinates(loc.location)
            loc_responses.append(
                LocationResponse(
                    id=loc.id,
                    booking_id=loc.booking_id,
                    location_type=loc.location_type,
                    address_text=loc.address_text,
                    landmark=loc.landmark,
                    latitude=lat,
                    longitude=lon,
                    created_at=loc.created_at,
                )
            )

        # Format history
        history_responses = [
            BookingStatusHistoryResponse.model_validate(h)
            for h in booking.status_history
        ]

        # Summaries
        cust_summary = (
            CustomerSummary(
                id=booking.customer.id,
                first_name=booking.customer.first_name,
                last_name=booking.customer.last_name,
                phone=booking.customer.phone,
                email=booking.customer.email,
            )
            if booking.customer
            else None
        )

        prov_summary = (
            ProviderSummary(
                id=booking.provider.id,
                business_name=booking.provider.business_name,
                provider_type=booking.provider.provider_type,
                phone=booking.provider.phone,
                rating_avg=booking.provider.rating_avg,
                rating_count=booking.provider.rating_count,
            )
            if booking.provider
            else None
        )

        svc_summary = (
            ServiceSummary(
                id=booking.service.id,
                name=booking.service.name,
                category=booking.service.category,
                base_price=booking.service.base_price,
                is_emergency=booking.service.is_emergency,
            )
            if booking.service
            else None
        )

        veh_summary = (
            VehicleSummary(
                id=booking.vehicle.id,
                registration_number=booking.vehicle.registration_number,
                make=booking.vehicle.make,
                model=booking.vehicle.model,
                fuel_type=booking.vehicle.fuel_type,
                color=booking.vehicle.color,
            )
            if booking.vehicle
            else None
        )

        return BookingDetailResponse(
            booking=BookingResponse.model_validate(booking),
            customer=cust_summary,
            provider=prov_summary,
            service=svc_summary,
            vehicle=veh_summary,
            locations=loc_responses,
            status_history=history_responses,
        )

    async def list_customer_bookings(
        self,
        customer_id: uuid.UUID,
        status: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> BookingListResponse:
        skip = (page - 1) * page_size
        bookings = await self.booking_repo.list_by_customer(
            customer_id=customer_id,
            status=status,
            skip=skip,
            limit=page_size,
        )
        total = await self.booking_repo.count_by_customer(
            customer_id=customer_id, status=status
        )

        items = [BookingResponse.model_validate(b) for b in bookings]
        return BookingListResponse(
            bookings=items, total=total, page=page, page_size=page_size
        )

    async def cancel_booking(
        self,
        booking_id: uuid.UUID,
        user_id: uuid.UUID,
        user_role: str,
        data: BookingCancelRequest,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> BookingResponse:
        booking = await self.booking_repo.get_by_id(booking_id)
        if not booking:
            raise NotFoundError(
                message="Booking not found.",
                code="BOOKING_NOT_FOUND",
            )

        # IDOR check
        if user_role == UserRole.CUSTOMER.value and booking.customer_id != user_id:
            raise ForbiddenError(
                message="You are not authorized to cancel this booking.",
                code="FORBIDDEN",
            )

        curr_status = booking.status
        allowed = self.ALLOWED_TRANSITIONS.get(curr_status, set())
        if BookingStatus.CANCELLED.value not in allowed:
            raise ValidationError(
                message=(
                    f"Cannot cancel booking: current status is '{curr_status}'. "
                    f"Cancellations are not permitted in this state."
                ),
                code="INVALID_STATUS_TRANSITION",
            )

        old_status = booking.status
        now = datetime.now(UTC)
        booking.status = BookingStatus.CANCELLED.value
        booking.cancelled_at = now
        booking.cancellation_reason = data.cancellation_reason.strip()

        # Add status history
        await self.booking_repo.add_status_history(
            booking_id=booking.id,
            status=BookingStatus.CANCELLED.value,
            actor_user_id=user_id,
            actor_role=user_role,
            notes=f"Cancelled: {booking.cancellation_reason}",
        )

        # Clean up any active dispatch offer in Redis
        offer_key = f"dispatch:offer:{booking.id}"
        await self.redis.delete(offer_key)

        await self.session.flush()

        await record_audit_event(
            session=self.session,
            action=AuditAction.STATUS_CHANGE.value,
            entity_type="Booking",
            entity_id=booking.id,
            actor_user_id=user_id,
            old_data={"status": old_status},
            new_data={
                "status": booking.status,
                "reason": booking.cancellation_reason,
            },
            ip_address=ip_address,
            user_agent=user_agent,
        )

        return BookingResponse.model_validate(booking)

    async def update_booking_status(
        self,
        booking_id: uuid.UUID,
        user_id: uuid.UUID,
        user_role: str,
        data: BookingStatusUpdateRequest,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> BookingResponse:
        booking = await self.booking_repo.get_by_id(booking_id)
        if not booking:
            raise NotFoundError(
                message="Booking not found.",
                code="BOOKING_NOT_FOUND",
            )

        # Role and Provider ownership verification
        if user_role == UserRole.PROVIDER.value:
            provider = await self.provider_repo.get_by_user_id(user_id)
            if not provider or booking.provider_id != provider.id:
                raise ForbiddenError(
                    message="You are not authorized to update this booking.",
                    code="FORBIDDEN",
                )

        curr_status = booking.status
        target_status = data.status.value

        if curr_status == target_status:
            return BookingResponse.model_validate(booking)

        allowed = self.ALLOWED_TRANSITIONS.get(curr_status, set())
        if target_status not in allowed:
            raise ValidationError(
                message=(
                    f"Invalid booking status transition from '{curr_status}' "
                    f"to '{target_status}'."
                ),
                code="INVALID_STATUS_TRANSITION",
                details={
                    "current_status": curr_status,
                    "target_status": target_status,
                    "allowed_transitions": list(allowed),
                },
            )

        now = datetime.now(UTC)
        booking.status = target_status

        if target_status == BookingStatus.ARRIVED.value:
            booking.arrived_at = now
        elif target_status == BookingStatus.COMPLETED.value:
            booking.completed_at = now

        # Add status history
        await self.booking_repo.add_status_history(
            booking_id=booking.id,
            status=target_status,
            actor_user_id=user_id,
            actor_role=user_role,
            notes=data.notes,
        )

        await self.session.flush()

        await record_audit_event(
            session=self.session,
            action=AuditAction.STATUS_CHANGE.value,
            entity_type="Booking",
            entity_id=booking.id,
            actor_user_id=user_id,
            old_data={"status": curr_status},
            new_data={"status": target_status, "notes": data.notes},
            ip_address=ip_address,
            user_agent=user_agent,
        )

        return BookingResponse.model_validate(booking)
