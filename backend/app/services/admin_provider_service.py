import uuid
from datetime import UTC, datetime
from typing import ClassVar

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import (
    ForbiddenError,
    NotFoundError,
    ValidationError,
)
from app.core.redis import RedisClient, redis_client
from app.models.enums import (
    AuditAction,
    ProviderDocumentStatus,
    ProviderVerificationStatus,
)
from app.repositories.provider import (
    ProviderAvailabilityRepository,
    ProviderDocumentRepository,
    ProviderRepository,
    ProviderServiceRepository,
)
from app.schemas.provider import (
    AvailabilitySlotSchema,
    ProviderAdminDetailResponse,
    ProviderAdminListResponse,
    ProviderAdminSummary,
    ProviderDocumentResponse,
    ProviderProfileResponse,
    ProviderServiceResponse,
)
from app.services.audit_service import record_audit_event


class AdminProviderService:
    """Domain service for administrative provider verification and oversight."""

    # Valid lifecycle state transitions: Current -> Set of allowed Target states
    ALLOWED_TRANSITIONS: ClassVar[dict[str, set[str]]] = {
        ProviderVerificationStatus.PENDING.value: {
            ProviderVerificationStatus.VERIFIED.value,
            ProviderVerificationStatus.REJECTED.value,
        },
        ProviderVerificationStatus.VERIFIED.value: {
            ProviderVerificationStatus.ACTIVE.value,
            ProviderVerificationStatus.SUSPENDED.value,
            ProviderVerificationStatus.REJECTED.value,
        },
        ProviderVerificationStatus.ACTIVE.value: {
            ProviderVerificationStatus.SUSPENDED.value,
            ProviderVerificationStatus.REJECTED.value,
        },
        ProviderVerificationStatus.SUSPENDED.value: {
            ProviderVerificationStatus.ACTIVE.value,
            ProviderVerificationStatus.REJECTED.value,
        },
        ProviderVerificationStatus.REJECTED.value: set(),  # Terminal state
    }

    def __init__(
        self, session: AsyncSession, redis: RedisClient | None = None
    ) -> None:
        self.session = session
        self.redis = redis or redis_client
        self.provider_repo = ProviderRepository(session)
        self.doc_repo = ProviderDocumentRepository(session)
        self.svc_repo = ProviderServiceRepository(session)
        self.avail_repo = ProviderAvailabilityRepository(session)

    async def list_providers(
        self,
        verification_status: str | None = None,
        provider_type: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> ProviderAdminListResponse:
        skip = (page - 1) * page_size
        providers = await self.provider_repo.list_providers(
            verification_status=verification_status,
            provider_type=provider_type,
            skip=skip,
            limit=page_size,
        )
        total = await self.provider_repo.count_providers(
            verification_status=verification_status,
            provider_type=provider_type,
        )

        items = [
            ProviderAdminSummary(
                id=p.id,
                user_id=p.user_id,
                business_name=p.business_name,
                provider_type=p.provider_type,
                phone=p.phone,
                verification_status=p.verification_status,
                is_online=p.is_online,
                rating_avg=p.rating_avg,
                rating_count=p.rating_count,
                created_at=p.created_at,
            )
            for p in providers
        ]
        return ProviderAdminListResponse(
            providers=items, total=total, page=page, page_size=page_size
        )

    async def get_provider_detail(
        self, provider_id: uuid.UUID
    ) -> ProviderAdminDetailResponse:
        provider = await self.provider_repo.get_by_id_with_relations(provider_id)
        if not provider:
            raise NotFoundError(
                message="Provider not found.",
                code="PROVIDER_NOT_FOUND",
            )

        doc_items = [
            ProviderDocumentResponse.model_validate(d)
            for d in provider.documents
        ]
        svc_items = [
            ProviderServiceResponse(
                id=ps.id,
                provider_id=ps.provider_id,
                service_id=ps.service_id,
                service_name=ps.service.name if ps.service else "Unknown",
                category=ps.service.category if ps.service else "GENERAL",
                price_from=ps.price_from,
                price_to=ps.price_to,
                is_active=ps.is_active,
                created_at=ps.created_at,
                updated_at=ps.updated_at,
            )
            for ps in provider.services
        ]
        slot_items = [
            AvailabilitySlotSchema(
                day_of_week=s.day_of_week,
                start_time=s.start_time,
                end_time=s.end_time,
                is_active=s.is_active,
            )
            for s in provider.availability
        ]

        user = provider.user
        return ProviderAdminDetailResponse(
            profile=ProviderProfileResponse.model_validate(provider),
            user_email=user.email if user else None,
            user_phone=user.phone if user else None,
            user_first_name=user.first_name if user else None,
            user_last_name=user.last_name if user else None,
            documents=doc_items,
            services=svc_items,
            availability_slots=slot_items,
        )

    async def update_verification_status(
        self,
        provider_id: uuid.UUID,
        new_status: ProviderVerificationStatus,
        admin_user_id: uuid.UUID,
        note: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> ProviderProfileResponse:
        provider = await self.provider_repo.get_by_id(provider_id)
        if not provider:
            raise NotFoundError(
                message="Provider not found.",
                code="PROVIDER_NOT_FOUND",
            )

        curr_status = provider.verification_status
        target_status = new_status.value

        if curr_status == target_status:
            return ProviderProfileResponse.model_validate(provider)

        allowed = self.ALLOWED_TRANSITIONS.get(curr_status, set())
        if target_status not in allowed:
            raise ValidationError(
                message=(
                    f"Invalid verification status transition from '{curr_status}' "
                    f"to '{target_status}'."
                ),
                code="INVALID_STATUS_TRANSITION",
                details={
                    "current_status": curr_status,
                    "target_status": target_status,
                    "allowed_transitions": list(allowed),
                },
            )

        provider.verification_status = target_status

        # If transitioning to SUSPENDED or REJECTED, immediately force offline
        if target_status in (
            ProviderVerificationStatus.SUSPENDED.value,
            ProviderVerificationStatus.REJECTED.value,
        ):
            if provider.is_online:
                provider.is_online = False
                presence_key = f"presence:provider:{provider.id}"
                await self.redis.delete(presence_key)

        await self.session.flush()

        await record_audit_event(
            session=self.session,
            action=AuditAction.STATUS_CHANGE.value,
            entity_type="ProviderVerification",
            entity_id=provider.id,
            actor_user_id=admin_user_id,
            old_data={"verification_status": curr_status},
            new_data={
                "verification_status": target_status,
                "note": note,
            },
            ip_address=ip_address,
            user_agent=user_agent,
        )

        return ProviderProfileResponse.model_validate(provider)

    async def review_document(
        self,
        provider_id: uuid.UUID,
        document_id: uuid.UUID,
        decision: ProviderDocumentStatus,
        admin_user_id: uuid.UUID,
        rejection_reason: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> ProviderDocumentResponse:
        provider = await self.provider_repo.get_by_id(provider_id)
        if not provider:
            raise NotFoundError(
                message="Provider not found.",
                code="PROVIDER_NOT_FOUND",
            )

        doc = await self.doc_repo.get_by_id(document_id)
        if not doc:
            raise NotFoundError(
                message="Document not found.",
                code="DOCUMENT_NOT_FOUND",
            )

        # Cross-provider validation: ensure doc belongs to specified provider
        if doc.provider_id != provider.id:
            raise ForbiddenError(
                message=(
                    "The requested document does not belong to the specified "
                    "provider."
                ),
                code="CROSS_PROVIDER_DOCUMENT_REVIEW_FORBIDDEN",
            )

        old_status = doc.status
        new_status = decision.value

        doc.status = new_status
        doc.reviewed_by = admin_user_id
        doc.reviewed_at = datetime.now(UTC)

        await self.session.flush()

        await record_audit_event(
            session=self.session,
            action=AuditAction.STATUS_CHANGE.value,
            entity_type="ProviderDocumentReview",
            entity_id=doc.id,
            actor_user_id=admin_user_id,
            old_data={"status": old_status},
            new_data={
                "status": new_status,
                "provider_id": str(provider.id),
                "rejection_reason": rejection_reason,
            },
            ip_address=ip_address,
            user_agent=user_agent,
        )

        return ProviderDocumentResponse.model_validate(doc)
