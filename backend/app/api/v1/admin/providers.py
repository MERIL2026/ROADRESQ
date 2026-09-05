import uuid

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_client_ip,
    get_db_session,
    get_redis,
    get_request_id,
    get_user_agent,
    require_admin,
)
from app.core.redis import RedisClient
from app.models.user import User
from app.schemas.common import APIResponse, ResponseMeta
from app.schemas.provider import (
    ProviderAdminDetailResponse,
    ProviderAdminListResponse,
    ProviderDocumentResponse,
    ProviderDocumentReviewRequest,
    ProviderProfileResponse,
    ProviderVerificationUpdateRequest,
)
from app.services.admin_provider_service import AdminProviderService

router = APIRouter(prefix="/admin/providers", tags=["Admin Provider Verification"])


@router.get(
    "",
    response_model=APIResponse[ProviderAdminListResponse],
    status_code=status.HTTP_200_OK,
    summary="List all registered providers with verification status and pagination",
)
async def list_providers_admin(
    request: Request,
    verification_status: str | None = Query(default=None, alias="status"),
    provider_type: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
    redis: RedisClient = Depends(get_redis),
) -> APIResponse[ProviderAdminListResponse]:
    request_id = get_request_id(request)
    service = AdminProviderService(session, redis)
    result = await service.list_providers(
        verification_status=verification_status,
        provider_type=provider_type,
        page=page,
        page_size=page_size,
    )
    return APIResponse(
        data=result,
        meta=ResponseMeta(request_id=request_id),
    )


@router.get(
    "/{provider_id}",
    response_model=APIResponse[ProviderAdminDetailResponse],
    status_code=status.HTTP_200_OK,
    summary="Retrieve full provider onboarding details, documents, and capabilities",
)
async def get_provider_detail_admin(
    provider_id: uuid.UUID,
    request: Request,
    current_admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
    redis: RedisClient = Depends(get_redis),
) -> APIResponse[ProviderAdminDetailResponse]:
    request_id = get_request_id(request)
    service = AdminProviderService(session, redis)
    result = await service.get_provider_detail(provider_id)
    return APIResponse(
        data=result,
        meta=ResponseMeta(request_id=request_id),
    )


@router.patch(
    "/{provider_id}/verification",
    response_model=APIResponse[ProviderProfileResponse],
    status_code=status.HTTP_200_OK,
    summary="Transition provider verification lifecycle status",
)

async def update_provider_verification(
    provider_id: uuid.UUID,
    data: ProviderVerificationUpdateRequest,
    request: Request,
    current_admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
    redis: RedisClient = Depends(get_redis),
) -> APIResponse[ProviderProfileResponse]:
    request_id = get_request_id(request)
    ip_address = get_client_ip(request)
    user_agent = get_user_agent(request)

    service = AdminProviderService(session, redis)
    profile = await service.update_verification_status(
        provider_id=provider_id,
        new_status=data.verification_status,
        admin_user_id=current_admin.id,
        note=data.note,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    await session.commit()

    return APIResponse(
        data=profile,
        meta=ResponseMeta(request_id=request_id),
    )


@router.patch(
    "/{provider_id}/documents/{document_id}",
    response_model=APIResponse[ProviderDocumentResponse],
    status_code=status.HTTP_200_OK,
    summary="Approve or reject a provider's submitted verification document",
)
async def review_provider_document(
    provider_id: uuid.UUID,
    document_id: uuid.UUID,
    data: ProviderDocumentReviewRequest,
    request: Request,
    current_admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
    redis: RedisClient = Depends(get_redis),
) -> APIResponse[ProviderDocumentResponse]:
    request_id = get_request_id(request)
    ip_address = get_client_ip(request)
    user_agent = get_user_agent(request)

    service = AdminProviderService(session, redis)
    doc = await service.review_document(
        provider_id=provider_id,
        document_id=document_id,
        decision=data.status,
        admin_user_id=current_admin.id,
        rejection_reason=data.rejection_reason,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    await session.commit()

    return APIResponse(
        data=doc,
        meta=ResponseMeta(request_id=request_id),
    )
