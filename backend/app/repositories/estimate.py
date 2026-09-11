import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.enums import EstimateStatus
from app.models.job import Estimate, EstimateItem
from app.schemas.estimate import EstimateItemCreate


class EstimateRepository:
    """Repository handling Estimate and EstimateItem persistence."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, estimate_id: uuid.UUID) -> Estimate | None:
        """Retrieves an estimate with line items."""
        stmt = (
            select(Estimate)
            .where(Estimate.id == estimate_id)
            .options(selectinload(Estimate.items))
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_number(self, estimate_number: str) -> Estimate | None:
        """Retrieves an estimate by unique number reference."""
        stmt = (
            select(Estimate)
            .where(Estimate.estimate_number == estimate_number)
            .options(selectinload(Estimate.items))
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_job_card(self, job_card_id: uuid.UUID) -> Sequence[Estimate]:
        """Lists all estimates associated with a JobCard."""
        stmt = (
            select(Estimate)
            .where(Estimate.job_card_id == job_card_id)
            .options(selectinload(Estimate.items))
            .order_by(desc(Estimate.created_at))
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_latest_estimate_by_job_card(
        self, job_card_id: uuid.UUID
    ) -> Estimate | None:
        """Retrieves the most recent estimate for a JobCard."""
        stmt = (
            select(Estimate)
            .where(Estimate.job_card_id == job_card_id)
            .options(selectinload(Estimate.items))
            .order_by(desc(Estimate.created_at))
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_estimate(
        self,
        job_card_id: uuid.UUID,
        estimate_number: str,
        subtotal: Decimal,
        tax_amount: Decimal,
        discount_amount: Decimal,
        total_amount: Decimal,
        status: str = EstimateStatus.PENDING_APPROVAL.value,
    ) -> Estimate:
        """Creates a new estimate record."""
        estimate = Estimate(
            job_card_id=job_card_id,
            estimate_number=estimate_number,
            subtotal=subtotal,
            tax_amount=tax_amount,
            discount_amount=discount_amount,
            total_amount=total_amount,
            status=status,
        )
        self.session.add(estimate)
        await self.session.flush()
        return estimate

    async def create_estimate_items(
        self,
        estimate_id: uuid.UUID,
        items_data: Sequence[tuple[EstimateItemCreate, Decimal]],
    ) -> list[EstimateItem]:
        """
        Creates itemized estimate entries with pre-computed line totals.
        items_data contains tuples of (EstimateItemCreate, calculated_line_total).
        """
        created_items: list[EstimateItem] = []
        for item, line_total in items_data:
            item_entity = EstimateItem(
                estimate_id=estimate_id,
                description=item.description.strip(),
                quantity=item.quantity,
                unit_price=item.unit_price,
                tax_rate=item.tax_rate,
                line_total=line_total,
            )
            self.session.add(item_entity)
            created_items.append(item_entity)
        await self.session.flush()
        return created_items

    async def approve_estimate(
        self, estimate: Estimate, user_id: uuid.UUID
    ) -> Estimate:
        """Records customer approval on an estimate."""
        estimate.status = EstimateStatus.APPROVED.value
        estimate.approved_by = user_id
        estimate.approved_at = datetime.now(UTC)
        await self.session.flush()
        return estimate

    async def reject_estimate(
        self, estimate: Estimate, user_id: uuid.UUID, rejection_reason: str
    ) -> Estimate:
        """Records customer rejection on an estimate."""
        estimate.status = EstimateStatus.REJECTED.value
        estimate.rejected_by = user_id
        estimate.rejected_at = datetime.now(UTC)
        estimate.rejection_reason = rejection_reason.strip()
        await self.session.flush()
        return estimate

    async def mark_revised(self, estimate: Estimate) -> Estimate:
        """Marks a prior estimate as superseded/revised."""
        estimate.status = EstimateStatus.REVISED.value
        await self.session.flush()
        return estimate
