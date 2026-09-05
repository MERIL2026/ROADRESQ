"""Admin Booking Management API (Phase 4)."""

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
from app.schemas.booking import (
    BookingDetailResponse,
    BookingListResponse,
    BookingResponse,
    BookingStatusUpdateRequest,
)
from app.schemas.common import APIResponse, ResponseMeta
from app.services.booking_service import BookingService
from app.services.dispatch_service import DispatchService

router = APIRouter(prefix="/admin/bookings", tags=["Admin Booking Management"])


@router.get(
    "",
    response_model=APIResponse[BookingListResponse],
    status_code=status.HTTP_200_OK,
    summary="List all platform bookings with optional status/customer filters",
)
async def list_all_bookings(
    request: Request,
    booking_status: str | None = Query(default=None, alias="status"),
    customer_id: uuid.UUID | None = Query(default=None),
    provider_id: uuid.UUID | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
    redis: RedisClient = Depends(get_redis),
) -> APIResponse[BookingListResponse]:
    request_id = get_request_id(request)
    service = BookingService(session, redis)
    result = await service.list_all_bookings(
        status=booking_status,
        customer_id=customer_id,
        provider_id=provider_id,
        page=page,
        page_size=page_size,
    )
    return APIResponse(
        data=result,
        meta=ResponseMeta(request_id=request_id),
    )


@router.get(
    "/{booking_id}",
    response_model=APIResponse[BookingDetailResponse],
    status_code=status.HTTP_200_OK,
    summary="Retrieve full booking detail including status history and dispatch info",
)
async def get_booking_admin(
    booking_id: uuid.UUID,
    request: Request,
    current_admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
    redis: RedisClient = Depends(get_redis),
) -> APIResponse[BookingDetailResponse]:
    request_id = get_request_id(request)
    service = BookingService(session, redis)
    details = await service.get_booking_details(
        booking_id=booking_id,
        user_id=current_admin.id,
        user_role=current_admin.role,
    )
    return APIResponse(
        data=details,
        meta=ResponseMeta(request_id=request_id),
    )


@router.patch(
    "/{booking_id}/status",
    response_model=APIResponse[BookingResponse],
    status_code=status.HTTP_200_OK,
    summary="Admin force-update booking status (supports any valid state machine transition)",
)
async def admin_update_booking_status(
    booking_id: uuid.UUID,
    data: BookingStatusUpdateRequest,
    request: Request,
    current_admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
    redis: RedisClient = Depends(get_redis),
) -> APIResponse[BookingResponse]:
    request_id = get_request_id(request)
    ip_address = get_client_ip(request)
    user_agent = get_user_agent(request)

    service = BookingService(session, redis)
    updated = await service.update_booking_status(
        booking_id=booking_id,
        user_id=current_admin.id,
        user_role=current_admin.role,
        data=data,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    await session.commit()

    return APIResponse(
        data=updated,
        meta=ResponseMeta(request_id=request_id),
    )


@router.post(
    "/{booking_id}/dispatch",
    response_model=APIResponse[BookingResponse],
    status_code=status.HTTP_200_OK,
    summary="Admin force-trigger dispatch matching engine for a booking",
)
async def admin_trigger_dispatch(
    booking_id: uuid.UUID,
    request: Request,
    current_admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
    redis: RedisClient = Depends(get_redis),
) -> APIResponse[BookingResponse]:
    request_id = get_request_id(request)
    dispatch_service = DispatchService(session, redis)
    booking = await dispatch_service.initiate_dispatch(booking_id=booking_id)
    await session.commit()

    booking_service = BookingService(session, redis)
    details = await booking_service.booking_repo.get_by_id(booking.id)
    resp = BookingResponse.model_validate(details if details else booking)

    return APIResponse(
        data=resp,
        meta=ResponseMeta(request_id=request_id),
    )
