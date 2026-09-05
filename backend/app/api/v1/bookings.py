import uuid

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_client_ip,
    get_current_active_user,
    get_db_session,
    get_redis,
    get_request_id,
    get_user_agent,
    require_customer,
)
from app.core.redis import RedisClient
from app.models.user import User
from app.schemas.booking import (
    BookingCancelRequest,
    BookingCreateRequest,
    BookingDetailResponse,
    BookingListResponse,
    BookingResponse,
)
from app.schemas.common import APIResponse, ResponseMeta
from app.services.booking_service import BookingService
from app.services.dispatch_service import DispatchService

router = APIRouter(prefix="/bookings", tags=["Bookings & Assistance"])


@router.post(
    "",
    response_model=APIResponse[BookingResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create a new roadside assistance booking and initiate dispatch matching",
)
async def create_booking(
    data: BookingCreateRequest,
    request: Request,
    current_user: User = Depends(require_customer),
    session: AsyncSession = Depends(get_db_session),
    redis: RedisClient = Depends(get_redis),
) -> APIResponse[BookingResponse]:
    request_id = get_request_id(request)
    ip_address = get_client_ip(request)
    user_agent = get_user_agent(request)

    booking_service = BookingService(session, redis)
    booking = await booking_service.create_booking(
        customer_id=current_user.id,
        data=data,
        ip_address=ip_address,
        user_agent=user_agent,
    )

    # Initiate dispatch matching engine
    dispatch_service = DispatchService(session, redis)
    await dispatch_service.initiate_dispatch(booking_id=booking.id)

    await session.commit()

    # Re-fetch latest booking status after dispatch offer creation
    updated_booking = await booking_service.booking_repo.get_by_id(booking.id)
    resp_data = (
        BookingResponse.model_validate(updated_booking)
        if updated_booking
        else booking
    )

    return APIResponse(
        data=resp_data,
        meta=ResponseMeta(request_id=request_id),
    )


@router.get(
    "/me",
    response_model=APIResponse[BookingListResponse],
    status_code=status.HTTP_200_OK,
    summary="List assistance bookings for the authenticated customer",
)
async def list_my_bookings(
    request: Request,
    booking_status: str | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(require_customer),
    session: AsyncSession = Depends(get_db_session),
    redis: RedisClient = Depends(get_redis),
) -> APIResponse[BookingListResponse]:
    request_id = get_request_id(request)
    service = BookingService(session, redis)
    result = await service.list_customer_bookings(
        customer_id=current_user.id,
        status=booking_status,
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
    summary="Retrieve detailed status, provider info, and history for a booking",
)
async def get_booking_details(
    booking_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
    redis: RedisClient = Depends(get_redis),
) -> APIResponse[BookingDetailResponse]:
    request_id = get_request_id(request)
    service = BookingService(session, redis)
    details = await service.get_booking_details(
        booking_id=booking_id,
        user_id=current_user.id,
        user_role=current_user.role,
    )
    return APIResponse(
        data=details,
        meta=ResponseMeta(request_id=request_id),
    )


@router.post(
    "/{booking_id}/cancel",
    response_model=APIResponse[BookingResponse],
    status_code=status.HTTP_200_OK,
    summary="Cancel a booking before provider arrival",
)
async def cancel_booking(
    booking_id: uuid.UUID,
    data: BookingCancelRequest,
    request: Request,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
    redis: RedisClient = Depends(get_redis),
) -> APIResponse[BookingResponse]:
    request_id = get_request_id(request)
    ip_address = get_client_ip(request)
    user_agent = get_user_agent(request)

    service = BookingService(session, redis)
    cancelled = await service.cancel_booking(
        booking_id=booking_id,
        user_id=current_user.id,
        user_role=current_user.role,
        data=data,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    await session.commit()

    return APIResponse(
        data=cancelled,
        meta=ResponseMeta(request_id=request_id),
    )
