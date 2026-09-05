from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_client_ip,
    get_db_session,
    get_request_id,
    get_user_agent,
    require_customer,
)
from app.models.user import User
from app.schemas.common import APIResponse, ResponseMeta
from app.schemas.vehicle import (
    VehicleCreateRequest,
    VehicleListResponse,
    VehicleResponse,
)
from app.services.vehicle_service import VehicleService

router = APIRouter(prefix="/vehicles", tags=["Customer Vehicles"])


@router.get(
    "/me",
    response_model=APIResponse[VehicleListResponse],
    status_code=status.HTTP_200_OK,
    summary="List all vehicles registered by the authenticated customer",
)
async def list_my_vehicles(
    request: Request,
    current_user: User = Depends(require_customer),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse[VehicleListResponse]:
    request_id = get_request_id(request)
    service = VehicleService(session)
    result = await service.list_vehicles(current_user.id)
    return APIResponse(
        data=result,
        meta=ResponseMeta(request_id=request_id),
    )


@router.post(
    "/me",
    response_model=APIResponse[VehicleResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Register a new vehicle under customer profile",
)
async def register_vehicle(
    data: VehicleCreateRequest,
    request: Request,
    current_user: User = Depends(require_customer),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse[VehicleResponse]:
    request_id = get_request_id(request)
    ip_address = get_client_ip(request)
    user_agent = get_user_agent(request)

    service = VehicleService(session)
    result = await service.register_vehicle(
        user_id=current_user.id,
        data=data,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    await session.commit()

    return APIResponse(
        data=result,
        meta=ResponseMeta(request_id=request_id),
    )
