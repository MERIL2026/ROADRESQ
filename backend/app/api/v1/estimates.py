import uuid

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_client_ip,
    get_current_active_user,
    get_db_session,
    get_redis,
    get_request_id,
    get_user_agent,
    require_customer,
    require_provider,
)
from app.core.redis import RedisClient
from app.models.user import User
from app.schemas.common import APIResponse, ResponseMeta
from app.schemas.estimate import (
    EstimateRejectRequest,
    EstimateResponse,
    EstimateReviseRequest,
)
from app.services.estimate_service import EstimateService

router = APIRouter(prefix="/estimates", tags=["Estimates & Pricing"])


@router.get(
    "/{estimate_id}",
    response_model=APIResponse[EstimateResponse],
    status_code=status.HTTP_200_OK,
    summary="Retrieve price estimate details and itemized breakdown",
)
async def get_estimate(
    estimate_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
    redis: RedisClient = Depends(get_redis),
) -> APIResponse[EstimateResponse]:
    request_id = get_request_id(request)
    service = EstimateService(session, redis)
    estimate = await service.get_estimate(
        estimate_id=estimate_id,
        user_id=current_user.id,
        user_role=current_user.role,
    )
    return APIResponse(
        data=estimate,
        meta=ResponseMeta(request_id=request_id),
    )


@router.post(
    "/{estimate_id}/approve",
    response_model=APIResponse[EstimateResponse],
    status_code=status.HTTP_200_OK,
    summary="Customer approval of a proposed estimate (advances booking to IN_PROGRESS)",
)
async def approve_estimate(
    estimate_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(require_customer),
    session: AsyncSession = Depends(get_db_session),
    redis: RedisClient = Depends(get_redis),
) -> APIResponse[EstimateResponse]:
    request_id = get_request_id(request)
    ip_address = get_client_ip(request)
    user_agent = get_user_agent(request)

    service = EstimateService(session, redis)
    approved = await service.approve_estimate(
        estimate_id=estimate_id,
        user_id=current_user.id,
        user_role=current_user.role,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    await session.commit()

    return APIResponse(
        data=approved,
        meta=ResponseMeta(request_id=request_id),
    )


@router.post(
    "/{estimate_id}/reject",
    response_model=APIResponse[EstimateResponse],
    status_code=status.HTTP_200_OK,
    summary="Customer rejection of a proposed estimate",
)
async def reject_estimate(
    estimate_id: uuid.UUID,
    data: EstimateRejectRequest,
    request: Request,
    current_user: User = Depends(require_customer),
    session: AsyncSession = Depends(get_db_session),
    redis: RedisClient = Depends(get_redis),
) -> APIResponse[EstimateResponse]:
    request_id = get_request_id(request)
    ip_address = get_client_ip(request)
    user_agent = get_user_agent(request)

    service = EstimateService(session, redis)
    rejected = await service.reject_estimate(
        estimate_id=estimate_id,
        user_id=current_user.id,
        user_role=current_user.role,
        data=data,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    await session.commit()

    return APIResponse(
        data=rejected,
        meta=ResponseMeta(request_id=request_id),
    )


@router.post(
    "/{estimate_id}/revise",
    response_model=APIResponse[EstimateResponse],
    status_code=status.HTTP_200_OK,
    summary="Provider submits a revised estimate for additional or modified work",
)
async def revise_estimate(
    estimate_id: uuid.UUID,
    data: EstimateReviseRequest,
    request: Request,
    current_user: User = Depends(require_provider),
    session: AsyncSession = Depends(get_db_session),
    redis: RedisClient = Depends(get_redis),
) -> APIResponse[EstimateResponse]:
    request_id = get_request_id(request)
    ip_address = get_client_ip(request)
    user_agent = get_user_agent(request)

    service = EstimateService(session, redis)
    revised = await service.revise_estimate(
        estimate_id=estimate_id,
        user_id=current_user.id,
        data=data,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    await session.commit()

    return APIResponse(
        data=revised,
        meta=ResponseMeta(request_id=request_id),
    )
