from redis.asyncio import Redis

from app.core.config import settings

# Global async redis instance
redis_client: Redis = Redis.from_url(settings.REDIS_URL, decode_responses=True)


async def check_redis_health() -> dict[str, str | bool]:
    """Health check helper to ping Redis server."""
    try:
        ping_response = await redis_client.ping()
        return {
            "status": bool(ping_response),
            "redis": "connected" if ping_response else "unresponsive",
        }
    except Exception as e:
        return {
            "status": False,
            "redis": "disconnected",
            "error": str(e),
        }
