import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)
from app.core.redis import RedisClient, redis_client
from app.core.storage import storage_service
from app.models.enums import (
    AuditAction,
    ProviderDocumentStatus,
    ProviderVerificationStatus,
    UserStatus,
)
from app.models.provider import Provider, ProviderDocument, ProviderService
from app.repositories.provider import (
    ProviderAvailabilityRepository,
    ProviderBookingQueryRepository,
    ProviderDocumentRepository,
    ProviderRepository,
    ProviderServiceRepository,
)
from app.repositories.service import ServiceRepository
from app.repositories.user import UserRepository
from app.schemas.provider import (
    AvailabilitySlotSchema,
    ProviderAvailabilityBatchUpdateRequest,
    ProviderAvailabilityResponse,
    ProviderBookingListResponse,
    ProviderBookingSummaryResponse,
    ProviderDashboardMetricsResponse,
    ProviderDocumentListResponse,
    ProviderDocumentResponse,
    ProviderDocumentUploadRequest,
    ProviderProfileResponse,
    ProviderProfileUpdateRequest,
    ProviderPublicResponse,
    ProviderServiceCreateRequest,
    ProviderServiceListResponse,
    ProviderServiceResponse,
    ProviderServiceUpdateRequest,
    ProviderStatusResponse,
)
from app.services.audit_service import record_audit_event


class ProviderServiceLayer:
    """Domain service for Provider operations, onboarding, and presence."""

    def __init__(
        self, session: AsyncSession, redis: RedisClient | None = None
    ) -> None:
        self.session = session
        self.redis = redis or redis_client
        self.provider_repo = ProviderRepository(session)
        self.doc_repo = ProviderDocumentRepository(session)
        self.svc_repo = ProviderServiceRepository(session)
        self.avail_repo = ProviderAvailabilityRepository(session)
        self.catalog_repo = ServiceRepository(session)
        self.user_repo = UserRepository(session)
        self.booking_query_repo = ProviderBookingQueryRepository(session)

    async def _get_provider_by_user(self, user_id: uuid.UUID) -> Provider:
        provider = await self.provider_repo.get_by_user_id(user_id)
        if not provider:
            raise NotFoundError(
                message="Provider profile not found for the current user.",
                code="PROVIDER_NOT_FOUND",
            )
        return provider

    # ==========================================================================
    # 3.1 Profile Operations
    # ==========================================================================

    async def get_profile(self, user_id: uuid.UUID) -> ProviderProfileResponse:
        provider = await self._get_provider_by_user(user_id)
        return ProviderProfileResponse.model_validate(provider)

    async def update_profile(
        self,
        user_id: uuid.UUID,
        data: ProviderProfileUpdateRequest,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> ProviderProfileResponse:
        provider = await self._get_provider_by_user(user_id)

        old_values: dict[str, Any] = {
            "business_name": provider.business_name,
            "provider_type": provider.provider_type,
            "description": provider.description,
            "phone": provider.phone,
            "service_radius_km": float(provider.service_radius_km),
        }

        if data.business_name is not None:
            provider.business_name = data.business_name.strip()
        if data.provider_type is not None:
            provider.provider_type = data.provider_type.value
        if data.description is not None:
            desc = data.description.strip() if data.description else None
            provider.description = desc
        if data.phone is not None:
            provider.phone = data.phone.strip() if data.phone else None
        if data.service_radius_km is not None:
            provider.service_radius_km = data.service_radius_km

        await self.session.flush()

        new_values: dict[str, Any] = {
            "business_name": provider.business_name,
            "provider_type": provider.provider_type,
            "description": provider.description,
            "phone": provider.phone,
            "service_radius_km": float(provider.service_radius_km),
        }

        await record_audit_event(
            session=self.session,
            action=AuditAction.UPDATE.value,
            entity_type="Provider",
            entity_id=provider.id,
            actor_user_id=user_id,
            old_data=old_values,
            new_data=new_values,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        return ProviderProfileResponse.model_validate(provider)

    async def get_public_profile(
        self, provider_id: uuid.UUID
    ) -> ProviderPublicResponse:
        provider = await self.provider_repo.get_by_id(provider_id)
        if not provider:
            raise NotFoundError(
                message="Provider not found.",
                code="PROVIDER_NOT_FOUND",
            )
        return ProviderPublicResponse.model_validate(provider)

    # ==========================================================================
    # 3.2 Document Operations
    # ==========================================================================

    async def upload_document(
        self,
        user_id: uuid.UUID,
        data: ProviderDocumentUploadRequest,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> ProviderDocumentResponse:
        provider = await self._get_provider_by_user(user_id)
        safe_url = storage_service.validate_file_url(data.file_url)

        doc_num = (
            data.document_number.strip() if data.document_number else None
        )
        doc = ProviderDocument(
            id=uuid.uuid4(),
            provider_id=provider.id,
            document_type=data.document_type.value,
            file_url=safe_url,
            document_number=doc_num,
            status=ProviderDocumentStatus.PENDING.value,
        )

        self.session.add(doc)
        await self.session.flush()

        await record_audit_event(
            session=self.session,
            action=AuditAction.CREATE.value,
            entity_type="ProviderDocument",
            entity_id=doc.id,
            actor_user_id=user_id,
            new_data={
                "provider_id": str(provider.id),
                "document_type": doc.document_type,
                "status": doc.status,
            },
            ip_address=ip_address,
            user_agent=user_agent,
        )

        return ProviderDocumentResponse.model_validate(doc)

    async def list_documents(
        self, user_id: uuid.UUID
    ) -> ProviderDocumentListResponse:
        provider = await self._get_provider_by_user(user_id)
        docs = await self.doc_repo.list_by_provider(provider.id)
        items = [ProviderDocumentResponse.model_validate(d) for d in docs]
        return ProviderDocumentListResponse(documents=items, total=len(items))

    async def delete_document(
        self,
        user_id: uuid.UUID,
        document_id: uuid.UUID,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        provider = await self._get_provider_by_user(user_id)
        doc = await self.doc_repo.get_by_id(document_id)
        if not doc:
            raise NotFoundError(
                message="Document not found.",
                code="DOCUMENT_NOT_FOUND",
            )

        if doc.provider_id != provider.id:
            raise ForbiddenError(
                message="You are not authorized to delete this document.",
                code="FORBIDDEN",
            )

        if doc.status == ProviderDocumentStatus.APPROVED.value:
            raise ForbiddenError(
                message="Approved verification documents cannot be deleted.",
                code="DOCUMENT_APPROVED_IMMUTABLE",
            )

        await self.doc_repo.delete(doc)

        await record_audit_event(
            session=self.session,
            action=AuditAction.DELETE.value,
            entity_type="ProviderDocument",
            entity_id=document_id,
            actor_user_id=user_id,
            old_data={
                "provider_id": str(provider.id),
                "document_type": doc.document_type,
                "status": doc.status,
            },
            ip_address=ip_address,
            user_agent=user_agent,
        )

    # ==========================================================================
    # 3.3 Provider Services Operations
    # ==========================================================================

    async def list_provider_services(
        self, user_id: uuid.UUID
    ) -> ProviderServiceListResponse:
        provider = await self._get_provider_by_user(user_id)
        services = await self.svc_repo.list_by_provider(
            provider.id, active_only=False
        )
        items = []
        for ps in services:
            items.append(
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
            )
        return ProviderServiceListResponse(services=items, total=len(items))

    async def add_provider_service(
        self,
        user_id: uuid.UUID,
        data: ProviderServiceCreateRequest,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> ProviderServiceResponse:
        provider = await self._get_provider_by_user(user_id)

        catalog_svc = await self.catalog_repo.get_by_id(data.service_id)
        if not catalog_svc or not catalog_svc.is_active:
            raise ValidationError(
                message="The specified catalog service is inactive or does not exist.",
                code="SERVICE_NOT_AVAILABLE",
                details={"service_id": str(data.service_id)},
            )

        existing = await self.svc_repo.get_by_provider_and_service(
            provider.id, data.service_id
        )
        if existing:
            raise ConflictError(
                message="This service is already configured for this provider.",
                code="PROVIDER_SERVICE_DUPLICATE",
            )

        ps = ProviderService(
            id=uuid.uuid4(),
            provider_id=provider.id,
            service_id=data.service_id,
            price_from=data.price_from,
            price_to=data.price_to,
            is_active=True,
        )

        self.session.add(ps)
        await self.session.flush()

        await record_audit_event(
            session=self.session,
            action=AuditAction.CREATE.value,
            entity_type="ProviderService",
            entity_id=ps.id,
            actor_user_id=user_id,
            new_data={
                "provider_id": str(provider.id),
                "service_id": str(data.service_id),
                "is_active": True,
            },
            ip_address=ip_address,
            user_agent=user_agent,
        )

        return ProviderServiceResponse(
            id=ps.id,
            provider_id=ps.provider_id,
            service_id=ps.service_id,
            service_name=catalog_svc.name,
            category=catalog_svc.category,
            price_from=ps.price_from,
            price_to=ps.price_to,
            is_active=ps.is_active,
            created_at=ps.created_at,
            updated_at=ps.updated_at,
        )

    async def update_provider_service(
        self,
        user_id: uuid.UUID,
        service_id: uuid.UUID,
        data: ProviderServiceUpdateRequest,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> ProviderServiceResponse:
        provider = await self._get_provider_by_user(user_id)
        ps = await self.svc_repo.get_by_provider_and_service(
            provider.id, service_id
        )
        if not ps:
            raise NotFoundError(
                message="Service capability not found for this provider.",
                code="PROVIDER_SERVICE_NOT_FOUND",
            )

        if data.price_from is not None:
            ps.price_from = data.price_from
        if data.price_to is not None:
            ps.price_to = data.price_to
        if data.is_active is not None:
            ps.is_active = data.is_active

        await self.session.flush()

        await record_audit_event(
            session=self.session,
            action=AuditAction.UPDATE.value,
            entity_type="ProviderService",
            entity_id=ps.id,
            actor_user_id=user_id,
            new_data={
                "provider_id": str(provider.id),
                "service_id": str(service_id),
                "is_active": ps.is_active,
            },
            ip_address=ip_address,
            user_agent=user_agent,
        )

        catalog_svc = await self.catalog_repo.get_by_id(service_id)
        return ProviderServiceResponse(
            id=ps.id,
            provider_id=ps.provider_id,
            service_id=ps.service_id,
            service_name=catalog_svc.name if catalog_svc else "Unknown",
            category=catalog_svc.category if catalog_svc else "GENERAL",
            price_from=ps.price_from,
            price_to=ps.price_to,
            is_active=ps.is_active,
            created_at=ps.created_at,
            updated_at=ps.updated_at,
        )

    async def remove_provider_service(
        self,
        user_id: uuid.UUID,
        service_id: uuid.UUID,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        provider = await self._get_provider_by_user(user_id)
        ps = await self.svc_repo.get_by_provider_and_service(
            provider.id, service_id
        )
        if not ps:
            raise NotFoundError(
                message="Service capability not found for this provider.",
                code="PROVIDER_SERVICE_NOT_FOUND",
            )

        await self.svc_repo.delete(ps)

        await record_audit_event(
            session=self.session,
            action=AuditAction.DELETE.value,
            entity_type="ProviderService",
            entity_id=ps.id,
            actor_user_id=user_id,
            old_data={
                "provider_id": str(provider.id),
                "service_id": str(service_id),
            },
            ip_address=ip_address,
            user_agent=user_agent,
        )

    # ==========================================================================
    # 3.4 Provider Availability Operations
    # ==========================================================================

    async def get_availability(
        self, user_id: uuid.UUID
    ) -> ProviderAvailabilityResponse:
        provider = await self._get_provider_by_user(user_id)
        slots = await self.avail_repo.list_by_provider(provider.id)
        slot_schemas = [
            AvailabilitySlotSchema(
                day_of_week=s.day_of_week,
                start_time=s.start_time,
                end_time=s.end_time,
                is_active=s.is_active,
            )
            for s in slots
        ]
        return ProviderAvailabilityResponse(
            provider_id=provider.id, slots=slot_schemas
        )

    async def update_availability(
        self,
        user_id: uuid.UUID,
        data: ProviderAvailabilityBatchUpdateRequest,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> ProviderAvailabilityResponse:
        provider = await self._get_provider_by_user(user_id)
        slots_data = [s.model_dump() for s in data.slots]
        created_slots = await self.avail_repo.replace_schedule(
            provider.id, slots_data
        )

        await record_audit_event(
            session=self.session,
            action=AuditAction.UPDATE.value,
            entity_type="ProviderAvailability",
            entity_id=provider.id,
            actor_user_id=user_id,
            new_data={"slot_count": len(created_slots)},
            ip_address=ip_address,
            user_agent=user_agent,
        )

        slot_schemas = [
            AvailabilitySlotSchema(
                day_of_week=s.day_of_week,
                start_time=s.start_time,
                end_time=s.end_time,
                is_active=s.is_active,
            )
            for s in created_slots
        ]
        return ProviderAvailabilityResponse(
            provider_id=provider.id, slots=slot_schemas
        )

    # ==========================================================================
    # 3.5 Online / Offline Status Operations
    # ==========================================================================

    async def set_online_status(
        self,
        user_id: uuid.UUID,
        is_online: bool,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> ProviderStatusResponse:
        user = await self.user_repo.get_by_id(user_id)
        if not user or user.status != UserStatus.ACTIVE.value:
            raise ForbiddenError(
                message="Your user account is not active.",
                code="USER_INACTIVE",
            )

        provider = await self._get_provider_by_user(user_id)

        if is_online:
            eligible_statuses = [
                ProviderVerificationStatus.VERIFIED.value,
                ProviderVerificationStatus.ACTIVE.value,
            ]
            if provider.verification_status not in eligible_statuses:
                raise ForbiddenError(
                    message=(
                        f"Cannot go online: provider verification status is "
                        f"'{provider.verification_status}'. Account must be VERIFIED."
                    ),
                    code="PROVIDER_NOT_VERIFIED",
                    details={
                        "verification_status": provider.verification_status
                    },
                )

            approved_count = await self.doc_repo.count_approved(provider.id)
            if approved_count < 1:
                raise ForbiddenError(
                    message=(
                        "Cannot go online: provider must have at least one "
                        "approved verification document."
                    ),
                    code="PROVIDER_NO_APPROVED_DOCUMENTS",
                )

            active_svc_count = await self.svc_repo.count_active(provider.id)
            if active_svc_count < 1:
                raise ForbiddenError(
                    message=(
                        "Cannot go online: provider must configure at least "
                        "one active service capability."
                    ),
                    code="PROVIDER_NO_ACTIVE_SERVICES",
                )

            provider.is_online = True
            await self.session.flush()

            presence_key = f"presence:provider:{provider.id}"
            await self.redis.set(presence_key, "online", expire_seconds=86400)
            msg = "Provider is now online and available for dispatch."

        else:
            provider.is_online = False
            await self.session.flush()

            presence_key = f"presence:provider:{provider.id}"
            await self.redis.delete(presence_key)
            msg = "Provider is now offline."

        await record_audit_event(
            session=self.session,
            action=AuditAction.STATUS_CHANGE.value,
            entity_type="Provider",
            entity_id=provider.id,
            actor_user_id=user_id,
            new_data={"is_online": provider.is_online},
            ip_address=ip_address,
            user_agent=user_agent,
        )

        return ProviderStatusResponse(
            provider_id=provider.id,
            is_online=provider.is_online,
            verification_status=provider.verification_status,
            message=msg,
        )

    # ==========================================================================
    # 3.7 Provider Dashboard & Bookings
    # ==========================================================================

    async def get_dashboard_metrics(
        self, user_id: uuid.UUID
    ) -> ProviderDashboardMetricsResponse:
        provider = await self._get_provider_by_user(user_id)
        active_count = (
            await self.booking_query_repo.count_active_bookings(provider.id)
        )
        completed_count = (
            await self.booking_query_repo.count_completed_bookings(provider.id)
        )
        total_docs = await self.doc_repo.count_total(provider.id)
        approved_docs = await self.doc_repo.count_approved(provider.id)
        active_svcs = await self.svc_repo.count_active(provider.id)

        return ProviderDashboardMetricsResponse(
            provider_id=provider.id,
            business_name=provider.business_name,
            verification_status=provider.verification_status,
            is_online=provider.is_online,
            active_bookings_count=active_count,
            completed_bookings_count=completed_count,
            rating_avg=provider.rating_avg,
            rating_count=provider.rating_count,
            total_documents_count=total_docs,
            approved_documents_count=approved_docs,
            active_services_count=active_svcs,
        )

    async def list_assigned_bookings(
        self,
        user_id: uuid.UUID,
        status: str | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> ProviderBookingListResponse:
        provider = await self._get_provider_by_user(user_id)
        bookings = await self.booking_query_repo.list_assigned_bookings(
            provider.id, status=status, skip=skip, limit=limit
        )
        items = []
        for b in bookings:
            cust_name = (
                f"{b.customer.first_name} {b.customer.last_name or ''}".strip()
                if b.customer
                else None
            )
            items.append(
                ProviderBookingSummaryResponse(
                    id=b.id,
                    booking_number=b.booking_number,
                    status=b.status,
                    booking_type=b.booking_type,
                    service_id=b.service_id,
                    service_name=b.service.name if b.service else None,
                    customer_id=b.customer_id,
                    customer_name=cust_name,
                    customer_phone=b.customer.phone if b.customer else None,
                    problem_description=b.problem_description,
                    requested_at=b.requested_at,
                    scheduled_at=b.scheduled_at,
                    accepted_at=b.accepted_at,
                    arrived_at=b.arrived_at,
                    completed_at=b.completed_at,
                )
            )
        return ProviderBookingListResponse(bookings=items, total=len(items))
