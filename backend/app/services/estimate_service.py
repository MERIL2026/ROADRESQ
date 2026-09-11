import uuid
from collections.abc import Sequence
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import (
    ForbiddenError,
    NotFoundError,
    ValidationError,
)
from app.core.redis import RedisClient, redis_client
from app.core.websocket import ws_manager
from app.models.enums import (
    AuditAction,
    BookingStatus,
    EstimateStatus,
    JobStatus,
    UserRole,
)
from app.repositories.booking import BookingRepository
from app.repositories.estimate import EstimateRepository
from app.repositories.job import JobRepository
from app.repositories.provider import ProviderRepository
from app.schemas.estimate import (
    EstimateCreateRequest,
    EstimateItemCreate,
    EstimateRejectRequest,
    EstimateResponse,
    EstimateReviseRequest,
)
from app.services.audit_service import record_audit_event


def _quantize_currency(value: Decimal) -> Decimal:
    """Rounds Decimal value to 2 decimal places using standard financial rounding."""
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class EstimateService:
    """Domain service managing price estimation, calculation integrity, customer approval, and revisions."""

    def __init__(self, session: AsyncSession, redis: RedisClient | None = None) -> None:
        self.session = session
        self.redis = redis or redis_client
        self.estimate_repo = EstimateRepository(session)
        self.job_repo = JobRepository(session)
        self.booking_repo = BookingRepository(session)
        self.provider_repo = ProviderRepository(session)

    async def create_estimate(
        self,
        booking_id: uuid.UUID,
        user_id: uuid.UUID,
        data: EstimateCreateRequest,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> EstimateResponse:
        """
        Generates an itemized quote for customer approval.
        Enforces server-side monetary calculations for subtotal, taxes, and totals.
        """
        booking = await self.booking_repo.get_by_id(booking_id)
        if not booking:
            raise NotFoundError(
                message="Booking not found.",
                code="BOOKING_NOT_FOUND",
            )

        provider = await self.provider_repo.get_by_user_id(user_id)
        if not provider or booking.provider_id != provider.id:
            raise ForbiddenError(
                message="You are not authorized to create estimates for this booking.",
                code="FORBIDDEN",
            )

        # Ensure JobCard exists
        job_card = await self.job_repo.get_by_booking_id(booking_id)
        if not job_card:
            job_card = await self.job_repo.create_job_card(
                booking_id=booking_id,
                provider_id=provider.id,
                mechanic_user_id=user_id,
                job_status=JobStatus.ESTIMATE_PENDING.value,
            )

        # Compute line totals and financial aggregates server-side
        subtotal, tax_amount, total_amount, items_with_totals = (
            self._compute_financials(
                items=data.items,
                discount_amount=data.discount_amount,
            )
        )

        estimate_number = f"EST-{uuid.uuid4().hex[:8].upper()}"

        estimate = await self.estimate_repo.create_estimate(
            job_card_id=job_card.id,
            estimate_number=estimate_number,
            subtotal=subtotal,
            tax_amount=tax_amount,
            discount_amount=data.discount_amount,
            total_amount=total_amount,
            status=EstimateStatus.PENDING_APPROVAL.value,
        )

        await self.estimate_repo.create_estimate_items(
            estimate_id=estimate.id,
            items_data=items_with_totals,
        )

        # Transition JobCard and Booking to ESTIMATE_PENDING
        job_card.job_status = JobStatus.ESTIMATE_PENDING.value
        booking.status = BookingStatus.ESTIMATE_PENDING.value

        await self.booking_repo.add_status_history(
            booking_id=booking.id,
            status=BookingStatus.ESTIMATE_PENDING.value,
            actor_user_id=user_id,
            actor_role=UserRole.PROVIDER.value,
            notes=f"Estimate {estimate_number} submitted (Total: INR {total_amount}).",
        )

        await self.session.flush()

        # Audit event
        await record_audit_event(
            session=self.session,
            action=AuditAction.CREATE.value,
            entity_type="Estimate",
            entity_id=estimate.id,
            actor_user_id=user_id,
            new_data={
                "estimate_number": estimate_number,
                "total_amount": str(total_amount),
                "items_count": len(data.items),
            },
            ip_address=ip_address,
            user_agent=user_agent,
        )

        # Real-time WebSocket event broadcast
        await ws_manager.broadcast_to_booking(
            booking_id=booking.id,
            event="estimate.created",
            data={
                "estimate_id": str(estimate.id),
                "estimate_number": estimate_number,
                "total_amount": str(total_amount),
                "status": EstimateStatus.PENDING_APPROVAL.value,
            },
        )
        await ws_manager.broadcast_to_booking(
            booking_id=booking.id,
            event="booking.status.updated",
            data={
                "status": BookingStatus.ESTIMATE_PENDING.value,
                "booking_id": str(booking.id),
            },
        )

        reloaded = await self.estimate_repo.get_by_id(estimate.id)
        return EstimateResponse.model_validate(reloaded or estimate)

    async def get_estimate(
        self,
        estimate_id: uuid.UUID,
        user_id: uuid.UUID,
        user_role: str,
    ) -> EstimateResponse:
        """Retrieves estimate details and itemized breakdown with IDOR access control."""
        estimate = await self.estimate_repo.get_by_id(estimate_id)
        if not estimate:
            raise NotFoundError(
                message="Estimate not found.",
                code="ESTIMATE_NOT_FOUND",
            )

        job_card = await self.job_repo.get_by_id(estimate.job_card_id)
        if not job_card:
            raise NotFoundError(
                message="Associated job card not found.",
                code="JOB_CARD_NOT_FOUND",
            )

        booking = await self.booking_repo.get_by_id(job_card.booking_id)
        if not booking:
            raise NotFoundError(
                message="Associated booking not found.",
                code="BOOKING_NOT_FOUND",
            )

        # IDOR checks
        if user_role == UserRole.CUSTOMER.value and booking.customer_id != user_id:
            raise ForbiddenError(
                message="You are not authorized to view this estimate.",
                code="FORBIDDEN",
            )
        if user_role == UserRole.PROVIDER.value:
            provider = await self.provider_repo.get_by_user_id(user_id)
            if not provider or booking.provider_id != provider.id:
                raise ForbiddenError(
                    message="You are not authorized to view this estimate.",
                    code="FORBIDDEN",
                )

        return EstimateResponse.model_validate(estimate)

    async def approve_estimate(
        self,
        estimate_id: uuid.UUID,
        user_id: uuid.UUID,
        user_role: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> EstimateResponse:
        """
        Customer approval of a pending estimate.
        Transitions the booking and job card to IN_PROGRESS.
        """
        estimate = await self.estimate_repo.get_by_id(estimate_id)
        if not estimate:
            raise NotFoundError(
                message="Estimate not found.",
                code="ESTIMATE_NOT_FOUND",
            )

        job_card = await self.job_repo.get_by_id(estimate.job_card_id)
        if not job_card:
            raise NotFoundError(
                message="Job card not found.",
                code="JOB_CARD_NOT_FOUND",
            )

        booking = await self.booking_repo.get_by_id(job_card.booking_id)
        if not booking:
            raise NotFoundError(
                message="Booking not found.",
                code="BOOKING_NOT_FOUND",
            )

        # Only the booking customer can approve
        if user_role != UserRole.CUSTOMER.value or booking.customer_id != user_id:
            raise ForbiddenError(
                message="Only the customer who created this booking can approve this estimate.",
                code="FORBIDDEN",
            )

        if estimate.status not in (
            EstimateStatus.PENDING_APPROVAL.value,
            EstimateStatus.DRAFT.value,
        ):
            raise ValidationError(
                message=f"Cannot approve estimate in '{estimate.status}' status.",
                code="INVALID_ESTIMATE_STATE",
            )

        # Approve Estimate
        await self.estimate_repo.approve_estimate(estimate=estimate, user_id=user_id)

        # Advance JobCard & Booking -> IN_PROGRESS
        job_card.job_status = JobStatus.IN_PROGRESS.value
        booking.status = BookingStatus.IN_PROGRESS.value

        await self.booking_repo.add_status_history(
            booking_id=booking.id,
            status=BookingStatus.IN_PROGRESS.value,
            actor_user_id=user_id,
            actor_role=UserRole.CUSTOMER.value,
            notes=f"Customer approved estimate {estimate.estimate_number}. Work in progress.",
        )

        await self.session.flush()

        # Audit event
        await record_audit_event(
            session=self.session,
            action=AuditAction.STATUS_CHANGE.value,
            entity_type="Estimate",
            entity_id=estimate.id,
            actor_user_id=user_id,
            old_data={"status": EstimateStatus.PENDING_APPROVAL.value},
            new_data={"status": EstimateStatus.APPROVED.value},
            ip_address=ip_address,
            user_agent=user_agent,
        )

        # Real-time WebSocket event broadcast
        await ws_manager.broadcast_to_booking(
            booking_id=booking.id,
            event="estimate.updated",
            data={
                "estimate_id": str(estimate.id),
                "status": EstimateStatus.APPROVED.value,
            },
        )
        await ws_manager.broadcast_to_booking(
            booking_id=booking.id,
            event="booking.status.updated",
            data={
                "status": BookingStatus.IN_PROGRESS.value,
                "booking_id": str(booking.id),
            },
        )

        reloaded = await self.estimate_repo.get_by_id(estimate.id)
        return EstimateResponse.model_validate(reloaded or estimate)

    async def reject_estimate(
        self,
        estimate_id: uuid.UUID,
        user_id: uuid.UUID,
        user_role: str,
        data: EstimateRejectRequest,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> EstimateResponse:
        """
        Customer rejection of a proposed estimate.
        """
        estimate = await self.estimate_repo.get_by_id(estimate_id)
        if not estimate:
            raise NotFoundError(
                message="Estimate not found.",
                code="ESTIMATE_NOT_FOUND",
            )

        job_card = await self.job_repo.get_by_id(estimate.job_card_id)
        if not job_card:
            raise NotFoundError(
                message="Job card not found.",
                code="JOB_CARD_NOT_FOUND",
            )

        booking = await self.booking_repo.get_by_id(job_card.booking_id)
        if not booking:
            raise NotFoundError(
                message="Booking not found.",
                code="BOOKING_NOT_FOUND",
            )

        if user_role != UserRole.CUSTOMER.value or booking.customer_id != user_id:
            raise ForbiddenError(
                message="Only the customer who created this booking can reject this estimate.",
                code="FORBIDDEN",
            )

        if estimate.status != EstimateStatus.PENDING_APPROVAL.value:
            raise ValidationError(
                message=f"Cannot reject estimate in '{estimate.status}' status.",
                code="INVALID_ESTIMATE_STATE",
            )

        # Reject Estimate
        await self.estimate_repo.reject_estimate(
            estimate=estimate,
            user_id=user_id,
            rejection_reason=data.rejection_reason,
        )

        await self.booking_repo.add_status_history(
            booking_id=booking.id,
            status=booking.status,
            actor_user_id=user_id,
            actor_role=UserRole.CUSTOMER.value,
            notes=f"Customer rejected estimate {estimate.estimate_number}: {data.rejection_reason.strip()}",
        )

        await self.session.flush()

        # Audit event
        await record_audit_event(
            session=self.session,
            action=AuditAction.STATUS_CHANGE.value,
            entity_type="Estimate",
            entity_id=estimate.id,
            actor_user_id=user_id,
            old_data={"status": EstimateStatus.PENDING_APPROVAL.value},
            new_data={
                "status": EstimateStatus.REJECTED.value,
                "rejection_reason": data.rejection_reason,
            },
            ip_address=ip_address,
            user_agent=user_agent,
        )

        # WebSocket broadcast
        await ws_manager.broadcast_to_booking(
            booking_id=booking.id,
            event="estimate.updated",
            data={
                "estimate_id": str(estimate.id),
                "status": EstimateStatus.REJECTED.value,
                "rejection_reason": data.rejection_reason,
            },
        )

        reloaded = await self.estimate_repo.get_by_id(estimate.id)
        return EstimateResponse.model_validate(reloaded or estimate)

    async def revise_estimate(
        self,
        estimate_id: uuid.UUID,
        user_id: uuid.UUID,
        data: EstimateReviseRequest,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> EstimateResponse:
        """
        Provider creates a revised estimate when scope of work changes or previous quote was rejected.
        Supersedes previous estimate without destructive mutation of historical records.
        """
        old_estimate = await self.estimate_repo.get_by_id(estimate_id)
        if not old_estimate:
            raise NotFoundError(
                message="Estimate not found.",
                code="ESTIMATE_NOT_FOUND",
            )

        job_card = await self.job_repo.get_by_id(old_estimate.job_card_id)
        if not job_card:
            raise NotFoundError(
                message="Job card not found.",
                code="JOB_CARD_NOT_FOUND",
            )

        booking = await self.booking_repo.get_by_id(job_card.booking_id)
        if not booking:
            raise NotFoundError(
                message="Booking not found.",
                code="BOOKING_NOT_FOUND",
            )

        provider = await self.provider_repo.get_by_user_id(user_id)
        if not provider or booking.provider_id != provider.id:
            raise ForbiddenError(
                message="You are not authorized to revise estimates for this booking.",
                code="FORBIDDEN",
            )

        # Mark prior estimate as REVISED
        await self.estimate_repo.mark_revised(old_estimate)

        # Compute new financials
        subtotal, tax_amount, total_amount, items_with_totals = (
            self._compute_financials(
                items=data.items,
                discount_amount=data.discount_amount,
            )
        )

        estimate_number = f"EST-REV-{uuid.uuid4().hex[:6].upper()}"

        new_estimate = await self.estimate_repo.create_estimate(
            job_card_id=job_card.id,
            estimate_number=estimate_number,
            subtotal=subtotal,
            tax_amount=tax_amount,
            discount_amount=data.discount_amount,
            total_amount=total_amount,
            status=EstimateStatus.PENDING_APPROVAL.value,
        )

        await self.estimate_repo.create_estimate_items(
            estimate_id=new_estimate.id,
            items_data=items_with_totals,
        )

        # Transition back to ESTIMATE_PENDING
        job_card.job_status = JobStatus.ESTIMATE_PENDING.value
        booking.status = BookingStatus.ESTIMATE_PENDING.value

        await self.booking_repo.add_status_history(
            booking_id=booking.id,
            status=BookingStatus.ESTIMATE_PENDING.value,
            actor_user_id=user_id,
            actor_role=UserRole.PROVIDER.value,
            notes=f"Revised estimate {estimate_number} issued (Total: INR {total_amount}).",
        )

        await self.session.flush()

        # Audit event
        await record_audit_event(
            session=self.session,
            action=AuditAction.CREATE.value,
            entity_type="Estimate",
            entity_id=new_estimate.id,
            actor_user_id=user_id,
            new_data={
                "estimate_number": estimate_number,
                "supersedes_estimate_id": str(old_estimate.id),
                "total_amount": str(total_amount),
            },
            ip_address=ip_address,
            user_agent=user_agent,
        )

        # WebSocket broadcast
        await ws_manager.broadcast_to_booking(
            booking_id=booking.id,
            event="estimate.created",
            data={
                "estimate_id": str(new_estimate.id),
                "estimate_number": estimate_number,
                "total_amount": str(total_amount),
                "status": EstimateStatus.PENDING_APPROVAL.value,
            },
        )

        reloaded = await self.estimate_repo.get_by_id(new_estimate.id)
        return EstimateResponse.model_validate(reloaded or new_estimate)

    def _compute_financials(
        self,
        items: Sequence[EstimateItemCreate],
        discount_amount: Decimal,
    ) -> tuple[Decimal, Decimal, Decimal, list[tuple[EstimateItemCreate, Decimal]]]:
        """
        Calculates line totals, subtotal, tax amount, and grand total.
        Returns (subtotal, tax_amount, total_amount, items_with_calculated_line_totals).
        """
        subtotal = Decimal("0.00")
        tax_amount = Decimal("0.00")
        items_with_totals: list[tuple[EstimateItemCreate, Decimal]] = []

        for item in items:
            item_base = _quantize_currency(item.quantity * item.unit_price)
            item_tax = _quantize_currency(
                item_base * (item.tax_rate / Decimal("100.00"))
            )
            line_total = item_base + item_tax

            subtotal += item_base
            tax_amount += item_tax
            items_with_totals.append((item, line_total))

        subtotal = _quantize_currency(subtotal)
        tax_amount = _quantize_currency(tax_amount)
        discount_amount = _quantize_currency(discount_amount)

        total_amount = max(Decimal("0.00"), subtotal + tax_amount - discount_amount)
        total_amount = _quantize_currency(total_amount)

        return subtotal, tax_amount, total_amount, items_with_totals
