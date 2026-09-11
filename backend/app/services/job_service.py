import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import (
    ForbiddenError,
    NotFoundError,
    ValidationError,
)
from app.core.redis import RedisClient, redis_client
from app.core.storage import SafeUrlStorageService
from app.core.websocket import ws_manager
from app.models.enums import AuditAction, BookingStatus, JobStatus, UserRole
from app.repositories.booking import BookingRepository
from app.repositories.job import JobRepository
from app.repositories.provider import ProviderRepository
from app.schemas.inspection import (
    InspectionCreateRequest,
    InspectionResponse,
)
from app.schemas.job import (
    JobCardCompleteRequest,
    JobCardResponse,
)
from app.services.audit_service import record_audit_event


class JobService:
    """Domain service managing the JobCard lifecycle, vehicle inspection, and job completion."""

    def __init__(self, session: AsyncSession, redis: RedisClient | None = None) -> None:
        self.session = session
        self.redis = redis or redis_client
        self.job_repo = JobRepository(session)
        self.booking_repo = BookingRepository(session)
        self.provider_repo = ProviderRepository(session)
        self.storage_service = SafeUrlStorageService()

    async def get_job_card(
        self,
        booking_id: uuid.UUID,
        user_id: uuid.UUID,
        user_role: str,
    ) -> JobCardResponse:
        """Retrieves active JobCard details and attached inspections/estimates."""
        booking = await self.booking_repo.get_by_id(booking_id)
        if not booking:
            raise NotFoundError(
                message="Booking not found.",
                code="BOOKING_NOT_FOUND",
            )

        # IDOR checks
        if user_role == UserRole.CUSTOMER.value and booking.customer_id != user_id:
            raise ForbiddenError(
                message="You are not authorized to access this job card.",
                code="FORBIDDEN",
            )
        if user_role == UserRole.PROVIDER.value:
            provider = await self.provider_repo.get_by_user_id(user_id)
            if not provider or booking.provider_id != provider.id:
                raise ForbiddenError(
                    message="You are not authorized to access this job card.",
                    code="FORBIDDEN",
                )

        job_card = await self.job_repo.get_by_booking_id(booking_id)
        if not job_card:
            raise NotFoundError(
                message="Job card has not been initiated for this booking yet.",
                code="JOB_CARD_NOT_FOUND",
            )

        return JobCardResponse.model_validate(job_card)

    async def create_inspection(
        self,
        booking_id: uuid.UUID,
        user_id: uuid.UUID,
        data: InspectionCreateRequest,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> InspectionResponse:
        """
        Records a comprehensive multi-point vehicle inspection with findings and optional media.
        Enforces private storage URL validation for every attached item image.
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
                message="You are not authorized to perform inspections for this booking.",
                code="FORBIDDEN",
            )

        # Validate allowed booking status
        allowed_statuses = {
            BookingStatus.ARRIVED.value,
            BookingStatus.INSPECTION.value,
            BookingStatus.ESTIMATE_PENDING.value,
            BookingStatus.APPROVED.value,
            BookingStatus.IN_PROGRESS.value,
        }
        if booking.status not in allowed_statuses:
            raise ValidationError(
                message=f"Cannot record inspection for booking in '{booking.status}' status.",
                code="INVALID_BOOKING_STATE",
            )

        # Validate all attached media URLs
        for item in data.items:
            if item.media_url:
                self.storage_service.validate_file_url(item.media_url)

        # Ensure JobCard exists
        job_card = await self.job_repo.get_by_booking_id(booking_id)
        if not job_card:
            job_card = await self.job_repo.create_job_card(
                booking_id=booking_id,
                provider_id=provider.id,
                mechanic_user_id=user_id,
                job_status=JobStatus.INSPECTION.value,
            )

        # Create Inspection session
        inspection = await self.job_repo.create_inspection(
            job_card_id=job_card.id,
            odometer_km=data.odometer_km,
            overall_notes=data.overall_notes.strip() if data.overall_notes else None,
            created_by=user_id,
        )

        # Create individual inspection items
        await self.job_repo.create_inspection_items(
            inspection_id=inspection.id,
            items_data=data.items,
        )

        # Transition booking to INSPECTION if currently ARRIVED
        if booking.status == BookingStatus.ARRIVED.value:
            booking.status = BookingStatus.INSPECTION.value
            await self.booking_repo.add_status_history(
                booking_id=booking.id,
                status=BookingStatus.INSPECTION.value,
                actor_user_id=user_id,
                actor_role=UserRole.PROVIDER.value,
                notes="Vehicle inspection recorded.",
            )
            await ws_manager.broadcast_to_booking(
                booking_id=booking.id,
                event="booking.status.updated",
                data={
                    "status": BookingStatus.INSPECTION.value,
                    "booking_id": str(booking.id),
                },
            )

        await self.session.flush()

        # Record audit event
        await record_audit_event(
            session=self.session,
            action=AuditAction.CREATE.value,
            entity_type="Inspection",
            entity_id=inspection.id,
            actor_user_id=user_id,
            new_data={
                "job_card_id": str(job_card.id),
                "items_count": len(data.items),
                "odometer_km": data.odometer_km,
            },
            ip_address=ip_address,
            user_agent=user_agent,
        )

        reloaded = await self.job_repo.get_inspection_by_id(inspection.id)
        return InspectionResponse.model_validate(reloaded or inspection)

    async def get_latest_inspection(
        self,
        booking_id: uuid.UUID,
        user_id: uuid.UUID,
        user_role: str,
    ) -> InspectionResponse:
        """Retrieves the latest recorded vehicle inspection for a booking."""
        booking = await self.booking_repo.get_by_id(booking_id)
        if not booking:
            raise NotFoundError(
                message="Booking not found.",
                code="BOOKING_NOT_FOUND",
            )

        # IDOR checks
        if user_role == UserRole.CUSTOMER.value and booking.customer_id != user_id:
            raise ForbiddenError(
                message="You are not authorized to view inspection for this booking.",
                code="FORBIDDEN",
            )
        if user_role == UserRole.PROVIDER.value:
            provider = await self.provider_repo.get_by_user_id(user_id)
            if not provider or booking.provider_id != provider.id:
                raise ForbiddenError(
                    message="You are not authorized to view inspection for this booking.",
                    code="FORBIDDEN",
                )

        job_card = await self.job_repo.get_by_booking_id(booking_id)
        if not job_card:
            raise NotFoundError(
                message="No job card found for this booking.",
                code="JOB_CARD_NOT_FOUND",
            )

        inspection = await self.job_repo.get_latest_inspection_by_job_card(job_card.id)
        if not inspection:
            raise NotFoundError(
                message="No inspection recorded for this booking.",
                code="INSPECTION_NOT_FOUND",
            )

        return InspectionResponse.model_validate(inspection)

    async def complete_job(
        self,
        booking_id: uuid.UUID,
        user_id: uuid.UUID,
        data: JobCardCompleteRequest,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> JobCardResponse:
        """
        Concludes roadside assistance service, records completion notes and photographic evidence,
        and transitions both JobCard and Booking to COMPLETED.
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
                message="You are not authorized to complete this job.",
                code="FORBIDDEN",
            )

        job_card = await self.job_repo.get_by_booking_id(booking_id)
        if not job_card:
            raise NotFoundError(
                message="No active job card found for this booking.",
                code="JOB_CARD_NOT_FOUND",
            )

        if data.completion_evidence_url:
            self.storage_service.validate_file_url(data.completion_evidence_url)

        valid_states = {
            JobStatus.IN_PROGRESS.value,
            JobStatus.APPROVED.value,
            JobStatus.INSPECTION.value,
            JobStatus.ESTIMATE_PENDING.value,
        }
        if job_card.job_status not in valid_states:
            raise ValidationError(
                message=f"Cannot complete job card currently in '{job_card.job_status}' status.",
                code="INVALID_JOB_STATE",
            )

        now = datetime.now(UTC)

        # Complete JobCard
        await self.job_repo.complete_job(
            job_card=job_card,
            completion_notes=data.completion_notes.strip(),
            completion_evidence_url=data.completion_evidence_url.strip()
            if data.completion_evidence_url
            else None,
        )

        # Complete Booking
        old_booking_status = booking.status
        booking.status = BookingStatus.COMPLETED.value
        booking.completed_at = now

        await self.booking_repo.add_status_history(
            booking_id=booking.id,
            status=BookingStatus.COMPLETED.value,
            actor_user_id=user_id,
            actor_role=UserRole.PROVIDER.value,
            notes=f"Service completed: {data.completion_notes.strip()}",
        )

        await self.session.flush()

        # Audit event
        await record_audit_event(
            session=self.session,
            action=AuditAction.STATUS_CHANGE.value,
            entity_type="JobCard",
            entity_id=job_card.id,
            actor_user_id=user_id,
            old_data={"job_status": old_booking_status},
            new_data={
                "job_status": JobStatus.COMPLETED.value,
                "notes": data.completion_notes,
                "evidence_url": data.completion_evidence_url,
            },
            ip_address=ip_address,
            user_agent=user_agent,
        )

        # Real-time WebSocket event broadcast
        await ws_manager.broadcast_to_booking(
            booking_id=booking.id,
            event="job.completed",
            data={
                "booking_id": str(booking.id),
                "job_card_id": str(job_card.id),
                "status": BookingStatus.COMPLETED.value,
            },
        )
        await ws_manager.broadcast_to_booking(
            booking_id=booking.id,
            event="booking.status.updated",
            data={
                "status": BookingStatus.COMPLETED.value,
                "booking_id": str(booking.id),
            },
        )

        reloaded = await self.job_repo.get_by_id(job_card.id)
        return JobCardResponse.model_validate(reloaded or job_card)
