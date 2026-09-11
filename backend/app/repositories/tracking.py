import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal

from geoalchemy2.elements import WKTElement
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import ProviderLocationUpdate


class TrackingRepository:
    """
    Repository handling persistence of provider GPS telemetry and
    historical tracking.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_location_update(
        self,
        provider_id: uuid.UUID,
        booking_id: uuid.UUID,
        latitude: float,
        longitude: float,
        accuracy_m: Decimal | float | None = None,
        heading: Decimal | float | None = None,
        speed_kmh: Decimal | float | None = None,
        recorded_at: datetime | None = None,
    ) -> ProviderLocationUpdate:
        """Persists a new GPS telemetry record in PostgreSQL/PostGIS."""
        point_wkt = WKTElement(f"POINT({longitude} {latitude})", srid=4326)
        update = ProviderLocationUpdate(
            provider_id=provider_id,
            booking_id=booking_id,
            location=point_wkt,
            accuracy_m=Decimal(str(accuracy_m)) if accuracy_m is not None else None,
            heading=Decimal(str(heading)) if heading is not None else None,
            speed_kmh=Decimal(str(speed_kmh)) if speed_kmh is not None else None,
            recorded_at=recorded_at or datetime.now(UTC),
        )
        self.session.add(update)
        await self.session.flush()
        return update

    async def get_latest_location_by_booking(
        self, booking_id: uuid.UUID
    ) -> ProviderLocationUpdate | None:
        """Fetches the most recent location point recorded for a given booking."""
        stmt = (
            select(ProviderLocationUpdate)
            .where(ProviderLocationUpdate.booking_id == booking_id)
            .order_by(desc(ProviderLocationUpdate.recorded_at))
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_location_history_by_booking(
        self, booking_id: uuid.UUID, limit: int = 100
    ) -> Sequence[ProviderLocationUpdate]:
        """Retrieves chronological GPS path for an active or completed booking."""
        stmt = (
            select(ProviderLocationUpdate)
            .where(ProviderLocationUpdate.booking_id == booking_id)
            .order_by(ProviderLocationUpdate.recorded_at.asc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_latest_location_by_provider(
        self, provider_id: uuid.UUID
    ) -> ProviderLocationUpdate | None:
        """
        Fetches the most recent location point recorded for a provider
        across bookings.
        """

        stmt = (
            select(ProviderLocationUpdate)
            .where(ProviderLocationUpdate.provider_id == provider_id)
            .order_by(desc(ProviderLocationUpdate.recorded_at))
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
