from collections.abc import AsyncGenerator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.redis import RedisClient, redis_client


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for obtaining async DB session."""
    async for session in get_db():
        yield session


def get_redis() -> RedisClient:
    """Dependency for obtaining Redis client."""
    return redis_client


def get_request_id(request: Request) -> str:
    """Extracts or returns correlation ID from request state."""
    return getattr(request.state, "request_id", "unknown")
