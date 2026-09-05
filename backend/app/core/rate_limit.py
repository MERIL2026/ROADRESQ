from app.core.errors import RateLimitError
from app.core.redis import redis_client


async def check_rate_limit(
    key: str,
    max_requests: int,
    window_seconds: int,
) -> tuple[bool, int, int]:
    """
    Evaluates rate limits against Redis using atomic counter with TTL.
    Returns (is_allowed, current_count, retry_after_seconds).
    """
    redis = redis_client.client
    redis_key = f"ratelimit:{key}"

    # Use Redis pipeline for atomic increment and ttl check
    pipe = redis.pipeline()
    pipe.incr(redis_key)
    pipe.ttl(redis_key)
    results = await pipe.execute()

    count = int(results[0])
    ttl = int(results[1])

    # If key was newly created, set its expiration
    if count == 1 or ttl == -1:
        await redis.expire(redis_key, window_seconds)
        ttl = window_seconds

    is_allowed = count <= max_requests
    retry_after = max(1, ttl) if not is_allowed else 0
    return is_allowed, count, retry_after


async def enforce_rate_limit(
    key: str,
    max_requests: int,
    window_seconds: int,
    error_code: str = "RATE_LIMITED",
    message: str = "Request quota exceeded. Please try again later.",
) -> None:
    """
    Enforces a rate limit for the given key.
    Raises RateLimitError if max_requests is exceeded.
    """
    is_allowed, count, retry_after = await check_rate_limit(
        key=key,
        max_requests=max_requests,
        window_seconds=window_seconds,
    )
    if not is_allowed:
        raise RateLimitError(
            message=message,
            code=error_code,
            details={
                "retry_after_seconds": retry_after,
                "current_requests": count,
                "max_requests": max_requests,
                "window_seconds": window_seconds,
            },
        )
