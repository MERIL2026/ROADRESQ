import uuid
from datetime import UTC, datetime
from typing import Sequence

from geoalchemy2.elements import WKBElement, WKTElement
from geoalchemy2.shape import to_shape
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.booking import Booking, BookingLocation, BookingStatusHistory
from app.models.enums import BookingStatus


class BookingRepository:
    """Data repository for Roadside Assistance Bookings, Locations, and Status History."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_booking(
        self,
        booking: Booking,
        locations: list[BookingLocation],
    ) -> Booking:
        self.session.add(booking)
        await self.session.flush()

        for loc in locations:
            loc.booking_id = booking.id
            self.session.add(loc)

        # Record initial status history
        history = BookingStatusHistory(
            id=uuid.uuid4(),
            booking_id=booking.id,
            status=booking.status,
            actor_user_id=booking.customer_id,
            actor_role="CUSTOMER",
            notes="Booking requested by customer",
        )
        self.session.add(history)
        await self.session.flush()

        return booking

    async def get_by_id(self, booking_id: uuid.UUID) -> Booking | None:
        stmt = select(Booking).where(Booking.id == booking_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id_with_relations(
        self, booking_id: uuid.UUID
    ) -> Booking | None:
        stmt = (
            select(Booking)
            .options(
                selectinload(Booking.customer),
                selectinload(Booking.provider),
                selectinload(Booking.service),
                selectinload(Booking.vehicle),
                selectinload(Booking.locations),
                selectinload(Booking.status_history),
            )
            .where(Booking.id == booking_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_booking_number(
        self, booking_number: str
    ) -> Booking | None:
        stmt = (
            select(Booking)
            .options(
                selectinload(Booking.customer),
                selectinload(Booking.provider),
                selectinload(Booking.service),
                selectinload(Booking.vehicle),
                selectinload(Booking.locations),
                selectinload(Booking.status_history),
            )
            .where(Booking.booking_number == booking_number.strip().upper())
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_customer(
        self,
        customer_id: uuid.UUID,
        status: str | None = None,
        skip: int = 0,
        limit: int = 20,
    ) -> Sequence[Booking]:
        stmt = (
            select(Booking)
            .where(Booking.customer_id == customer_id)
            .order_by(Booking.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        if status:
            stmt = stmt.where(Booking.status == status)

        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def count_by_customer(
        self,
        customer_id: uuid.UUID,
        status: str | None = None,
    ) -> int:
        stmt = select(func.count(Booking.id)).where(
            Booking.customer_id == customer_id
        )
        if status:
            stmt = stmt.where(Booking.status == status)

        result = await self.session.execute(stmt)
        return result.scalar_one() or 0

    async def list_all(
        self,
        status: str | None = None,
        booking_type: str | None = None,
        skip: int = 0,
        limit: int = 20,
    ) -> Sequence[Booking]:
        stmt = (
            select(Booking)
            .order_by(Booking.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        if status:
            stmt = stmt.where(Booking.status == status)
        if booking_type:
            stmt = stmt.where(Booking.booking_type == booking_type)

        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def count_all(
        self,
        status: str | None = None,
        booking_type: str | None = None,
    ) -> int:
        stmt = select(func.count(Booking.id))
        if status:
            stmt = stmt.where(Booking.status == status)
        if booking_type:
            stmt = stmt.where(Booking.booking_type == booking_type)

        result = await self.session.execute(stmt)
        return result.scalar_one() or 0

    async def add_status_history(
        self,
        booking_id: uuid.UUID,
        status: str,
        actor_user_id: uuid.UUID | None,
        actor_role: str | None,
        notes: str | None = None,
    ) -> BookingStatusHistory:
        history = BookingStatusHistory(
            id=uuid.uuid4(),
            booking_id=booking_id,
            status=status,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            notes=notes,
        )
        self.session.add(history)
        await self.session.flush()
        return history

    async def assign_provider_atomic(
        self,
        booking_id: uuid.UUID,
        provider_id: uuid.UUID,
    ) -> bool:
        """
        Atomically assigns a provider to a booking with strict WHERE condition.
        Prevents race condition where two providers accept the same booking.
        Returns True if assignment succeeded, False if already assigned or state changed.
        """
        now = datetime.now(UTC)
        stmt = (
            update(Booking)
            .where(
                Booking.id == booking_id,
                Booking.status.in_([
                    BookingStatus.REQUESTED.value,
                    BookingStatus.SEARCHING.value,
                    BookingStatus.PROVIDER_ASSIGNED.value,
                ]),
                Booking.provider_id.is_(None),
            )
            .values(
                provider_id=provider_id,
                status=BookingStatus.ACCEPTED.value,
                accepted_at=now,
            )
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount > 0

    @staticmethod
    def extract_coordinates(location_attr: any) -> tuple[float, float]:
        """Extracts (latitude, longitude) from PostGIS geography point or WKBElement."""
        if location_attr is None:
            return 0.0, 0.0
        if isinstance(location_attr, WKBElement):
            shape = to_shape(location_attr)
            # shape.x is longitude, shape.y is latitude
            return float(shape.y), float(shape.x)
        if isinstance(location_attr, WKTElement):
            text = str(location_attr)
            # POINT(lon lat)
            if "POINT" in text:
                coords = text.replace("POINT", "").replace("(", "").replace(")", "").strip().split()
                if len(coords) >= 2:
                    return float(coords[1]), float(coords[0])
        return 0.0, 0.0
