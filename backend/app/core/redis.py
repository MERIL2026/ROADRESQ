import asyncio
from typing import Any

from redis.asyncio import ConnectionPool, Redis

from app.core.config import settings


class RedisClient:
    """Async Redis client wrapper providing basic key-value operations."""

    def __init__(self, url: str) -> None:
        self._url: str = url
        self._pool: ConnectionPool | None = None
        self._redis: Redis | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    @property
    def client(self) -> Redis:
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None

        if self._redis is None or self._loop != current_loop:
            self._loop = current_loop
            self._pool = ConnectionPool.from_url(
                self._url, decode_responses=True, max_connections=20
            )
            self._redis = Redis(connection_pool=self._pool)
        return self._redis


    async def ping(self) -> bool:
        """Pings Redis server to verify connectivity."""
        try:
            return bool(await self.client.ping())
        except Exception:
            return False

    async def get(self, key: str) -> str | None:
        """Retrieves a string value by key."""
        result: str | None = await self.client.get(key)
        return result

    async def set(
        self, key: str, value: Any, expire_seconds: int | None = None
    ) -> bool:
        """Sets a string value with optional expiration time in seconds."""
        return bool(await self.client.set(key, str(value), ex=expire_seconds))

    async def delete(self, key: str) -> bool:
        """Deletes a key from Redis."""
        return bool(await self.client.delete(key))

    async def expire(self, key: str, seconds: int) -> bool:
        """Sets TTL on a key."""
        return bool(await self.client.expire(key, seconds))

    async def close(self) -> None:
        """Closes Redis connection pool."""
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None
        if self._pool is not None:
            await self._pool.disconnect()
            self._pool = None
        self._loop = None



# Global Redis client instance
redis_client: RedisClient = RedisClient(settings.REDIS_URL)


async def check_redis_health() -> dict[str, str | bool]:
    """Health check probe helper for Redis."""
    try:
        is_alive = await redis_client.ping()
        return {
            "status": is_alive,
            "redis": "connected" if is_alive else "unresponsive",
        }
    except Exception as e:
        return {
            "status": False,
            "redis": "disconnected",
            "error": str(e),
        }
