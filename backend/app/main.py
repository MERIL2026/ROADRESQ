import uuid
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as root_health_router
from app.api.v1.router import api_v1_router
from app.core.config import settings
from app.core.errors import (
    AppError,
    app_exception_handler,
    generic_exception_handler,
)
from app.core.logging import get_logger, setup_logging
from app.core.redis import redis_client

logger = get_logger("roadresq.app")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifecycle context manager for startup and shutdown procedures."""
    setup_logging()
    logger.info("Starting %s in [%s] mode...", settings.APP_NAME, settings.APP_ENV)
    yield
    logger.info("Closing Redis connection pool...")
    await redis_client.close()
    logger.info("Shutdown complete for %s", settings.APP_NAME)


app = FastAPI(
    title=settings.APP_NAME,
    description="RoadResQ Roadside Assistance Platform Backend Core API",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)


# Correlation ID Middleware (X-Request-ID)
@app.middleware("http")
async def request_id_middleware(
    request: Request, call_next: Callable[[Request], Any]
) -> Response:
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request.state.request_id = request_id
    response: Response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


# Enable CORS for local web development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict in production environment
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Exception Handlers
app.add_exception_handler(AppError, app_exception_handler)  # type: ignore[arg-type]
app.add_exception_handler(Exception, generic_exception_handler)

# Mount Routers
app.include_router(root_health_router)
app.include_router(api_v1_router)


@app.get("/", tags=["Root"])
async def root() -> dict[str, str]:
    return {
        "message": "Welcome to RoadResQ Platform API Core",
        "docs": "/docs",
        "health": "/health",
        "api_v1": "/api/v1",
        "readiness": "/api/v1/health/ready",
    }
