import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.enums import JobStatus
from app.models.job import Inspection, InspectionItem, JobCard
from app.schemas.inspection import InspectionItemCreate


class JobRepository:
    """Repository handling JobCard and Inspection persistence."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, job_card_id: uuid.UUID) -> JobCard | None:
        """Retrieves a JobCard with eager loaded inspections and estimates."""
        stmt = (
            select(JobCard)
            .where(JobCard.id == job_card_id)
            .options(
                selectinload(JobCard.inspections).selectinload(Inspection.items),
                selectinload(JobCard.estimates),
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_booking_id(self, booking_id: uuid.UUID) -> JobCard | None:
        """Retrieves the JobCard associated with a booking ID."""
        stmt = (
            select(JobCard)
            .where(JobCard.booking_id == booking_id)
            .options(
                selectinload(JobCard.inspections).selectinload(Inspection.items),
                selectinload(JobCard.estimates),
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_job_card(
        self,
        booking_id: uuid.UUID,
        provider_id: uuid.UUID,
        mechanic_user_id: uuid.UUID | None = None,
        job_status: str = JobStatus.INSPECTION.value,
        customer_notes: str | None = None,
        provider_notes: str | None = None,
        started_at: datetime | None = None,
    ) -> JobCard:
        """Initializes a new JobCard work order for a booking."""
        job_card = JobCard(
            booking_id=booking_id,
            provider_id=provider_id,
            mechanic_user_id=mechanic_user_id,
            job_status=job_status,
            customer_notes=customer_notes,
            provider_notes=provider_notes,
            started_at=started_at or datetime.now(UTC),
        )
        self.session.add(job_card)
        await self.session.flush()
        return job_card

    async def update_job_status(
        self,
        job_card: JobCard,
        new_status: str,
        provider_notes: str | None = None,
    ) -> JobCard:
        """Mutates operational JobCard status."""
        job_card.job_status = new_status
        if provider_notes:
            job_card.provider_notes = provider_notes
        if new_status == JobStatus.IN_PROGRESS.value and not job_card.started_at:
            job_card.started_at = datetime.now(UTC)
        await self.session.flush()
        return job_card

    async def complete_job(
        self,
        job_card: JobCard,
        completion_notes: str,
        completion_evidence_url: str | None = None,
    ) -> JobCard:
        """Marks a JobCard as completed with mandatory notes and optional evidence."""
        job_card.job_status = JobStatus.COMPLETED.value
        job_card.completed_at = datetime.now(UTC)
        job_card.completion_notes = completion_notes
        job_card.completion_evidence_url = completion_evidence_url
        await self.session.flush()
        return job_card

    async def create_inspection(
        self,
        job_card_id: uuid.UUID,
        odometer_km: int | None = None,
        overall_notes: str | None = None,
        created_by: uuid.UUID | None = None,
    ) -> Inspection:
        """Creates a vehicle inspection session record."""
        inspection = Inspection(
            job_card_id=job_card_id,
            odometer_km=odometer_km,
            overall_notes=overall_notes,
            created_by=created_by,
            created_at=datetime.now(UTC),
        )
        self.session.add(inspection)
        await self.session.flush()
        return inspection

    async def create_inspection_items(
        self,
        inspection_id: uuid.UUID,
        items_data: Sequence[InspectionItemCreate],
    ) -> list[InspectionItem]:
        """Creates itemized inspection findings."""
        created_items: list[InspectionItem] = []
        for item in items_data:
            item_entity = InspectionItem(
                inspection_id=inspection_id,
                component=item.component.strip(),
                condition=item.condition.value,
                finding=item.finding.strip() if item.finding else None,
                media_url=item.media_url.strip() if item.media_url else None,
                recommended_action=item.recommended_action.strip()
                if item.recommended_action
                else None,
            )
            self.session.add(item_entity)
            created_items.append(item_entity)
        await self.session.flush()
        return created_items

    async def get_inspection_by_id(self, inspection_id: uuid.UUID) -> Inspection | None:
        """Retrieves an inspection with its items."""

        stmt = (
            select(Inspection)
            .where(Inspection.id == inspection_id)
            .options(selectinload(Inspection.items))
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_latest_inspection_by_job_card(
        self, job_card_id: uuid.UUID
    ) -> Inspection | None:
        """Retrieves the most recent inspection for a JobCard."""
        stmt = (
            select(Inspection)
            .where(Inspection.job_card_id == job_card_id)
            .options(selectinload(Inspection.items))
            .order_by(desc(Inspection.created_at))
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
