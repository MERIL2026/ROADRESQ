from fastapi import APIRouter, Response, status
from pydantic import BaseModel

from app.core.config import settings
from app.core.db import check_db_health
from app.core.redis import check_redis_health

router = APIRouter(prefix="/health", tags=["Health & Diagnostics"])


class LivenessResponse(BaseModel):
    status: str
    app_name: str
    environment: str


class ServiceHealth(BaseModel):
    status: str
    details: dict


class ReadinessResponse(BaseModel):
    status: str
    database: ServiceHealth
    redis: ServiceHealth


@router.get("", response_model=LivenessResponse, summary="Liveness Probe")
async def liveness_probe() -> LivenessResponse:
    """Basic liveness probe indicating the backend application service process is running."""
    return LivenessResponse(
        status="ok",
        app_name=settings.APP_NAME,
        environment=settings.APP_ENV,
    )


@router.get("/ready", response_model=ReadinessResponse, summary="Readiness Probe")
async def readiness_probe(response: Response) -> ReadinessResponse:
    """Readiness probe checking PostgreSQL + PostGIS database connection and Redis connection.

    Returns HTTP 200 OK when all infrastructure dependencies are operational.
    Returns HTTP 503 Service Unavailable if any critical service is degraded or offline.
    """
    db_health = await check_db_health()
    redis_health = await check_redis_health()

    is_db_ok = bool(db_health.get("status"))
    is_redis_ok = bool(redis_health.get("status"))

    all_ready = is_db_ok and is_redis_ok

    if not all_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return ReadinessResponse(
        status="ready" if all_ready else "degraded",
        database=ServiceHealth(
            status="healthy" if is_db_ok else "unhealthy",
            details=db_health,
        ),
        redis=ServiceHealth(
            status="healthy" if is_redis_ok else "unhealthy",
            details=redis_health,
        ),
    )
