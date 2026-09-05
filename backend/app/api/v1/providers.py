import uuid

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_client_ip,
    get_db_session,
    get_redis,
    get_request_id,
    get_user_agent,
    require_provider,
)
from app.core.redis import RedisClient
from app.models.user import User
from app.schemas.auth import MessageResponse
from app.schemas.common import APIResponse, ResponseMeta
from app.schemas.provider import (
    ProviderAvailabilityBatchUpdateRequest,
    ProviderAvailabilityResponse,
    ProviderBookingListResponse,
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
    ProviderStatusUpdateRequest,
)
from app.services.provider_service import ProviderServiceLayer

router = APIRouter(prefix="/providers", tags=["Provider Domain"])


# ==============================================================================
# 3.1 Provider Profile Endpoints
# ==============================================================================


@router.get(
    "/me",
    response_model=APIResponse[ProviderProfileResponse],
    status_code=status.HTTP_200_OK,
    summary="Retrieve current authenticated provider's business profile",
)
async def get_my_profile(
    request: Request,
    current_user: User = Depends(require_provider),
    session: AsyncSession = Depends(get_db_session),
    redis: RedisClient = Depends(get_redis),
) -> APIResponse[ProviderProfileResponse]:
    request_id = get_request_id(request)
    service = ProviderServiceLayer(session, redis)
    profile = await service.get_profile(current_user.id)
    return APIResponse(
        data=profile,
        meta=ResponseMeta(request_id=request_id),
    )


@router.put(
    "/me",
    response_model=APIResponse[ProviderProfileResponse],
    status_code=status.HTTP_200_OK,
    summary="Update current authenticated provider's business profile",
)
async def update_my_profile(
    data: ProviderProfileUpdateRequest,
    request: Request,
    current_user: User = Depends(require_provider),
    session: AsyncSession = Depends(get_db_session),
    redis: RedisClient = Depends(get_redis),
) -> APIResponse[ProviderProfileResponse]:
    request_id = get_request_id(request)
    ip_address = get_client_ip(request)
    user_agent = get_user_agent(request)

    service = ProviderServiceLayer(session, redis)
    profile = await service.update_profile(
        user_id=current_user.id,
        data=data,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    await session.commit()

    return APIResponse(
        data=profile,
        meta=ResponseMeta(request_id=request_id),
    )


@router.get(
    "/{provider_id}",
    response_model=APIResponse[ProviderPublicResponse],
    status_code=status.HTTP_200_OK,
    summary="Retrieve public profile of a provider without sensitive data",
)
async def get_public_provider_profile(
    provider_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    redis: RedisClient = Depends(get_redis),
) -> APIResponse[ProviderPublicResponse]:
    request_id = get_request_id(request)
    service = ProviderServiceLayer(session, redis)
    profile = await service.get_public_profile(provider_id)
    return APIResponse(
        data=profile,
        meta=ResponseMeta(request_id=request_id),
    )


# ==============================================================================
# 3.2 Provider Documents Endpoints
# ==============================================================================


@router.post(
    "/me/documents",
    response_model=APIResponse[ProviderDocumentResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Submit a verification document (ID, License, Garage certificate)",
)
async def upload_document(
    data: ProviderDocumentUploadRequest,
    request: Request,
    current_user: User = Depends(require_provider),
    session: AsyncSession = Depends(get_db_session),
    redis: RedisClient = Depends(get_redis),
) -> APIResponse[ProviderDocumentResponse]:
    request_id = get_request_id(request)
    ip_address = get_client_ip(request)
    user_agent = get_user_agent(request)

    service = ProviderServiceLayer(session, redis)
    doc = await service.upload_document(
        user_id=current_user.id,
        data=data,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    await session.commit()

    return APIResponse(
        data=doc,
        meta=ResponseMeta(request_id=request_id),
    )


@router.get(
    "/me/documents",
    response_model=APIResponse[ProviderDocumentListResponse],
    status_code=status.HTTP_200_OK,
    summary="List all uploaded verification documents and approval status",
)
async def list_my_documents(
    request: Request,
    current_user: User = Depends(require_provider),
    session: AsyncSession = Depends(get_db_session),
    redis: RedisClient = Depends(get_redis),
) -> APIResponse[ProviderDocumentListResponse]:
    request_id = get_request_id(request)
    service = ProviderServiceLayer(session, redis)
    docs = await service.list_documents(current_user.id)
    return APIResponse(
        data=docs,
        meta=ResponseMeta(request_id=request_id),
    )


@router.delete(
    "/me/documents/{document_id}",
    response_model=APIResponse[MessageResponse],
    status_code=status.HTTP_200_OK,
    summary="Delete a pending or rejected verification document",
)
async def delete_my_document(
    document_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(require_provider),
    session: AsyncSession = Depends(get_db_session),
    redis: RedisClient = Depends(get_redis),
) -> APIResponse[MessageResponse]:
    request_id = get_request_id(request)
    ip_address = get_client_ip(request)
    user_agent = get_user_agent(request)

    service = ProviderServiceLayer(session, redis)
    await service.delete_document(
        user_id=current_user.id,
        document_id=document_id,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    await session.commit()

    return APIResponse(
        data=MessageResponse(message="Document deleted successfully."),
        meta=ResponseMeta(request_id=request_id),
    )


# ==============================================================================
# 3.3 Provider Services Endpoints
# ==============================================================================


@router.get(
    "/me/services",
    response_model=APIResponse[ProviderServiceListResponse],
    status_code=status.HTTP_200_OK,
    summary="List services currently configured by the provider",
)
async def list_my_services(
    request: Request,
    current_user: User = Depends(require_provider),
    session: AsyncSession = Depends(get_db_session),
    redis: RedisClient = Depends(get_redis),
) -> APIResponse[ProviderServiceListResponse]:
    request_id = get_request_id(request)
    service = ProviderServiceLayer(session, redis)
    services = await service.list_provider_services(current_user.id)
    return APIResponse(
        data=services,
        meta=ResponseMeta(request_id=request_id),
    )


@router.post(
    "/me/services",
    response_model=APIResponse[ProviderServiceResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Add a new service capability with pricing to provider portfolio",
)
async def add_service_capability(
    data: ProviderServiceCreateRequest,
    request: Request,
    current_user: User = Depends(require_provider),
    session: AsyncSession = Depends(get_db_session),
    redis: RedisClient = Depends(get_redis),
) -> APIResponse[ProviderServiceResponse]:
    request_id = get_request_id(request)
    ip_address = get_client_ip(request)
    user_agent = get_user_agent(request)

    service = ProviderServiceLayer(session, redis)
    ps = await service.add_provider_service(
        user_id=current_user.id,
        data=data,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    await session.commit()

    return APIResponse(
        data=ps,
        meta=ResponseMeta(request_id=request_id),
    )


@router.put(
    "/me/services/{service_id}",
    response_model=APIResponse[ProviderServiceResponse],
    status_code=status.HTTP_200_OK,
    summary="Update pricing or active status of a provider service capability",
)
async def update_service_capability(
    service_id: uuid.UUID,
    data: ProviderServiceUpdateRequest,
    request: Request,
    current_user: User = Depends(require_provider),
    session: AsyncSession = Depends(get_db_session),
    redis: RedisClient = Depends(get_redis),
) -> APIResponse[ProviderServiceResponse]:
    request_id = get_request_id(request)
    ip_address = get_client_ip(request)
    user_agent = get_user_agent(request)

    service = ProviderServiceLayer(session, redis)
    ps = await service.update_provider_service(
        user_id=current_user.id,
        service_id=service_id,
        data=data,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    await session.commit()

    return APIResponse(
        data=ps,
        meta=ResponseMeta(request_id=request_id),
    )


@router.delete(
    "/me/services/{service_id}",
    response_model=APIResponse[MessageResponse],
    status_code=status.HTTP_200_OK,
    summary="Remove a service capability from provider portfolio",
)
async def remove_service_capability(
    service_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(require_provider),
    session: AsyncSession = Depends(get_db_session),
    redis: RedisClient = Depends(get_redis),
) -> APIResponse[MessageResponse]:
    request_id = get_request_id(request)
    ip_address = get_client_ip(request)
    user_agent = get_user_agent(request)

    service = ProviderServiceLayer(session, redis)
    await service.remove_provider_service(
        user_id=current_user.id,
        service_id=service_id,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    await session.commit()

    return APIResponse(
        data=MessageResponse(message="Service capability removed successfully."),
        meta=ResponseMeta(request_id=request_id),
    )


# ==============================================================================
# 3.4 Provider Availability Endpoints
# ==============================================================================


@router.get(
    "/me/availability",
    response_model=APIResponse[ProviderAvailabilityResponse],
    status_code=status.HTTP_200_OK,
    summary="Retrieve provider recurring weekly working schedule",
)
async def get_my_availability(
    request: Request,
    current_user: User = Depends(require_provider),
    session: AsyncSession = Depends(get_db_session),
    redis: RedisClient = Depends(get_redis),
) -> APIResponse[ProviderAvailabilityResponse]:
    request_id = get_request_id(request)
    service = ProviderServiceLayer(session, redis)
    avail = await service.get_availability(current_user.id)
    return APIResponse(
        data=avail,
        meta=ResponseMeta(request_id=request_id),
    )


@router.put(
    "/me/availability",
    response_model=APIResponse[ProviderAvailabilityResponse],
    status_code=status.HTTP_200_OK,
    summary="Atomically replace provider weekly working schedule",
)
async def update_my_availability(
    data: ProviderAvailabilityBatchUpdateRequest,
    request: Request,
    current_user: User = Depends(require_provider),
    session: AsyncSession = Depends(get_db_session),
    redis: RedisClient = Depends(get_redis),
) -> APIResponse[ProviderAvailabilityResponse]:
    request_id = get_request_id(request)
    ip_address = get_client_ip(request)
    user_agent = get_user_agent(request)

    service = ProviderServiceLayer(session, redis)
    avail = await service.update_availability(
        user_id=current_user.id,
        data=data,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    await session.commit()

    return APIResponse(
        data=avail,
        meta=ResponseMeta(request_id=request_id),
    )


# ==============================================================================
# 3.5 Online / Offline Status Endpoints
# ==============================================================================


@router.post(
    "/me/status",
    response_model=APIResponse[ProviderStatusResponse],
    status_code=status.HTTP_200_OK,
    summary="Toggle live presence online/offline status with eligibility validation",
)
async def set_online_status(
    data: ProviderStatusUpdateRequest,
    request: Request,
    current_user: User = Depends(require_provider),
    session: AsyncSession = Depends(get_db_session),
    redis: RedisClient = Depends(get_redis),
) -> APIResponse[ProviderStatusResponse]:
    request_id = get_request_id(request)
    ip_address = get_client_ip(request)
    user_agent = get_user_agent(request)

    service = ProviderServiceLayer(session, redis)
    resp = await service.set_online_status(
        user_id=current_user.id,
        is_online=data.is_online,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    await session.commit()

    return APIResponse(
        data=resp,
        meta=ResponseMeta(request_id=request_id),
    )


# ==============================================================================
# 3.7 Provider Dashboard & Bookings Endpoints
# ==============================================================================


@router.get(
    "/me/dashboard",
    response_model=APIResponse[ProviderDashboardMetricsResponse],
    status_code=status.HTTP_200_OK,
    summary="Retrieve operational metrics and summary KPIs for provider dashboard",
)
async def get_provider_dashboard(
    request: Request,
    current_user: User = Depends(require_provider),
    session: AsyncSession = Depends(get_db_session),
    redis: RedisClient = Depends(get_redis),
) -> APIResponse[ProviderDashboardMetricsResponse]:
    request_id = get_request_id(request)
    service = ProviderServiceLayer(session, redis)
    metrics = await service.get_dashboard_metrics(current_user.id)
    return APIResponse(
        data=metrics,
        meta=ResponseMeta(request_id=request_id),
    )


@router.get(
    "/me/bookings",
    response_model=APIResponse[ProviderBookingListResponse],
    status_code=status.HTTP_200_OK,
    summary="List assistance bookings assigned to the authenticated provider",
)
async def list_assigned_bookings(
    request: Request,
    booking_status: str | None = Query(default=None, alias="status"),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    current_user: User = Depends(require_provider),
    session: AsyncSession = Depends(get_db_session),
    redis: RedisClient = Depends(get_redis),
) -> APIResponse[ProviderBookingListResponse]:
    request_id = get_request_id(request)
    service = ProviderServiceLayer(session, redis)
    bookings = await service.list_assigned_bookings(
        user_id=current_user.id,
        status=booking_status,
        skip=skip,
        limit=limit,
    )
    return APIResponse(
        data=bookings,
        meta=ResponseMeta(request_id=request_id),
    )
