import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.booking import Booking
from app.models.enums import BookingStatus, ProviderDocumentStatus
from app.models.provider import (
    Provider,
    ProviderAvailability,
    ProviderDocument,
    ProviderService,
)
from app.repositories.base import BaseRepository


class ProviderRepository(BaseRepository[Provider]):
    """Async repository for Provider entities."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Provider, session)

    async def get_by_user_id(self, user_id: uuid.UUID) -> Provider | None:
        stmt = (
            select(Provider)
            .where(Provider.user_id == user_id)
            .options(
                selectinload(Provider.documents),
                selectinload(Provider.services).selectinload(ProviderService.service),
                selectinload(Provider.availability),
            )
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_by_id_with_relations(
        self, provider_id: uuid.UUID
    ) -> Provider | None:
        stmt = (
            select(Provider)
            .where(Provider.id == provider_id)
            .options(
                selectinload(Provider.documents),
                selectinload(Provider.services).selectinload(ProviderService.service),
                selectinload(Provider.availability),
                selectinload(Provider.user),
            )
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def list_providers(
        self,
        verification_status: str | None = None,
        provider_type: str | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> Sequence[Provider]:
        stmt = select(Provider)
        if verification_status:
            stmt = stmt.where(Provider.verification_status == verification_status)
        if provider_type:
            stmt = stmt.where(Provider.provider_type == provider_type)

        stmt = stmt.order_by(Provider.created_at.desc()).offset(skip).limit(limit)
        res = await self.session.execute(stmt)
        return res.scalars().all()

    async def count_providers(
        self,
        verification_status: str | None = None,
        provider_type: str | None = None,
    ) -> int:
        stmt = select(func.count(Provider.id))
        if verification_status:
            stmt = stmt.where(Provider.verification_status == verification_status)
        if provider_type:
            stmt = stmt.where(Provider.provider_type == provider_type)

        res = await self.session.execute(stmt)
        return res.scalar_one() or 0

    async def update_online_status(
        self, provider_id: uuid.UUID, is_online: bool
    ) -> None:
        stmt = (
            update(Provider)
            .where(Provider.id == provider_id)
            .values(is_online=is_online, updated_at=datetime.now(UTC))
        )
        await self.session.execute(stmt)
        await self.session.flush()

    async def update_verification_status(
        self, provider_id: uuid.UUID, verification_status: str
    ) -> None:
        stmt = (
            update(Provider)
            .where(Provider.id == provider_id)
            .values(
                verification_status=verification_status,
                updated_at=datetime.now(UTC),
            )
        )
        await self.session.execute(stmt)
        await self.session.flush()


class ProviderDocumentRepository(BaseRepository[ProviderDocument]):
    """Async repository for provider verification documents."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(ProviderDocument, session)

    async def list_by_provider(
        self, provider_id: uuid.UUID
    ) -> Sequence[ProviderDocument]:
        stmt = (
            select(ProviderDocument)
            .where(ProviderDocument.provider_id == provider_id)
            .order_by(ProviderDocument.created_at.desc())
        )
        res = await self.session.execute(stmt)
        return res.scalars().all()

    async def count_approved(self, provider_id: uuid.UUID) -> int:
        stmt = (
            select(func.count(ProviderDocument.id))
            .where(
                ProviderDocument.provider_id == provider_id,
                ProviderDocument.status == ProviderDocumentStatus.APPROVED.value,
            )
        )
        res = await self.session.execute(stmt)
        return res.scalar_one() or 0

    async def count_total(self, provider_id: uuid.UUID) -> int:
        stmt = select(func.count(ProviderDocument.id)).where(
            ProviderDocument.provider_id == provider_id
        )
        res = await self.session.execute(stmt)
        return res.scalar_one() or 0


class ProviderServiceRepository(BaseRepository[ProviderService]):
    """Async repository for provider service capabilities."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(ProviderService, session)

    async def get_by_provider_and_service(
        self, provider_id: uuid.UUID, service_id: uuid.UUID
    ) -> ProviderService | None:
        stmt = (
            select(ProviderService)
            .where(
                ProviderService.provider_id == provider_id,
                ProviderService.service_id == service_id,
            )
            .options(selectinload(ProviderService.service))
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def list_by_provider(
        self, provider_id: uuid.UUID, active_only: bool = False
    ) -> Sequence[ProviderService]:
        stmt = (
            select(ProviderService)
            .where(ProviderService.provider_id == provider_id)
            .options(selectinload(ProviderService.service))
        )
        if active_only:
            stmt = stmt.where(ProviderService.is_active.is_(True))
        stmt = stmt.order_by(ProviderService.created_at.asc())
        res = await self.session.execute(stmt)
        return res.scalars().all()

    async def count_active(self, provider_id: uuid.UUID) -> int:
        stmt = select(func.count(ProviderService.id)).where(
            ProviderService.provider_id == provider_id,
            ProviderService.is_active.is_(True),
        )
        res = await self.session.execute(stmt)
        return res.scalar_one() or 0


class ProviderAvailabilityRepository(BaseRepository[ProviderAvailability]):
    """Async repository for provider availability schedule."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(ProviderAvailability, session)

    async def list_by_provider(
        self, provider_id: uuid.UUID
    ) -> Sequence[ProviderAvailability]:
        stmt = (
            select(ProviderAvailability)
            .where(ProviderAvailability.provider_id == provider_id)
            .order_by(ProviderAvailability.day_of_week, ProviderAvailability.start_time)
        )
        res = await self.session.execute(stmt)
        return res.scalars().all()

    async def replace_schedule(
        self, provider_id: uuid.UUID, slots_data: list[dict[str, Any]]
    ) -> Sequence[ProviderAvailability]:
        # Atomic replace: delete old slots, insert new
        stmt = delete(ProviderAvailability).where(
            ProviderAvailability.provider_id == provider_id
        )
        await self.session.execute(stmt)

        created_slots: list[ProviderAvailability] = []
        for slot in slots_data:
            avail = ProviderAvailability(
                provider_id=provider_id,
                day_of_week=slot["day_of_week"],
                start_time=slot["start_time"],
                end_time=slot["end_time"],
                is_active=slot.get("is_active", True),
            )
            self.session.add(avail)
            created_slots.append(avail)

        await self.session.flush()
        return created_slots


class ProviderBookingQueryRepository:
    """Read queries for bookings assigned to a provider."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def count_active_bookings(self, provider_id: uuid.UUID) -> int:
        active_statuses = [
            BookingStatus.PROVIDER_ASSIGNED.value,
            BookingStatus.ACCEPTED.value,
            BookingStatus.ON_THE_WAY.value,
            BookingStatus.ARRIVED.value,
            BookingStatus.INSPECTION.value,
            BookingStatus.ESTIMATE_PENDING.value,
            BookingStatus.APPROVED.value,
            BookingStatus.IN_PROGRESS.value,
        ]
        stmt = select(func.count(Booking.id)).where(
            Booking.provider_id == provider_id,
            Booking.status.in_(active_statuses),
        )
        res = await self.session.execute(stmt)
        return res.scalar_one() or 0

    async def count_completed_bookings(self, provider_id: uuid.UUID) -> int:
        completed_statuses = [
            BookingStatus.COMPLETED.value,
            BookingStatus.INVOICE_GENERATED.value,
            BookingStatus.PAYMENT_COMPLETED.value,
            BookingStatus.CLOSED.value,
        ]
        stmt = select(func.count(Booking.id)).where(
            Booking.provider_id == provider_id,
            Booking.status.in_(completed_statuses),
        )
        res = await self.session.execute(stmt)
        return res.scalar_one() or 0

    async def list_assigned_bookings(
        self,
        provider_id: uuid.UUID,
        status: str | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> Sequence[Booking]:
        stmt = (
            select(Booking)
            .where(Booking.provider_id == provider_id)
            .options(
                selectinload(Booking.service),
                selectinload(Booking.customer),
            )
        )
        if status:
            stmt = stmt.where(Booking.status == status)

        stmt = stmt.order_by(Booking.requested_at.desc()).offset(skip).limit(limit)
        res = await self.session.execute(stmt)
        return res.scalars().all()
