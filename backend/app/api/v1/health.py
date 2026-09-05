from fastapi import APIRouter, Depends, Response, status

from app.api.deps import get_request_id
from app.core.config import settings
from app.core.db import check_db_health
from app.core.redis import check_redis_health
from app.schemas.common import APIResponse, ResponseMeta
from app.schemas.health import LivenessData, ReadinessData, ServiceHealthInfo

router = APIRouter(prefix="/health", tags=["Health Diagnostics"])


@router.get(
    "",
    response_model=APIResponse[LivenessData],
    summary="API v1 Liveness Probe",
)
async def v1_liveness(
    request_id: str = Depends(get_request_id),
) -> APIResponse[LivenessData]:
    """Liveness probe verifying that API v1 service process is functioning."""
    return APIResponse(
        data=LivenessData(
            status="ok",
            app_name=settings.APP_NAME,
            environment=settings.APP_ENV,
        ),
        meta=ResponseMeta(request_id=request_id),
    )


@router.get(
    "/ready",
    response_model=APIResponse[ReadinessData],
    summary="API v1 Readiness Probe",
)
async def v1_readiness(
    response: Response,
    request_id: str = Depends(get_request_id),
) -> APIResponse[ReadinessData]:
    """Readiness probe checking PostgreSQL + PostGIS and Redis connectivity.

    Returns HTTP 200 OK when operational.
    Returns HTTP 503 Service Unavailable if any critical dependent service is
    degraded or offline.
    """
    db_health = await check_db_health()
    redis_health = await check_redis_health()

    is_db_ok = bool(db_health.get("status"))
    is_redis_ok = bool(redis_health.get("status"))
    all_ready = is_db_ok and is_redis_ok

    if not all_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return APIResponse(
        data=ReadinessData(
            status="ready" if all_ready else "degraded",
            database=ServiceHealthInfo(
                status="healthy" if is_db_ok else "unhealthy",
                details=db_health,
            ),
            redis=ServiceHealthInfo(
                status="healthy" if is_redis_ok else "unhealthy",
                details=redis_health,
            ),
        ),
        meta=ResponseMeta(request_id=request_id),
    )
