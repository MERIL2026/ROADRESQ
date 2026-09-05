from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session, get_request_id
from app.repositories.service import ServiceRepository
from app.schemas.common import APIResponse, ResponseMeta
from app.schemas.service import ServiceListResponse, ServiceResponse

router = APIRouter(prefix="/services", tags=["Service Catalog"])


@router.get(
    "",
    response_model=APIResponse[ServiceListResponse],
    status_code=status.HTTP_200_OK,
    summary="List available platform assistance and automotive services",
)
async def list_services(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse[ServiceListResponse]:
    request_id = get_request_id(request)
    repo = ServiceRepository(session)
    services = await repo.list_active()
    items = [ServiceResponse.model_validate(s) for s in services]
    return APIResponse(
        data=ServiceListResponse(services=items, total=len(items)),
        meta=ResponseMeta(request_id=request_id),
    )
