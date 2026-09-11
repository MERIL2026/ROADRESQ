from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_db_session, get_redis
from app.core.db import engine
from app.core.redis import redis_client
from app.main import app


@pytest.fixture(autouse=True)
async def cleanup_connections():
    """Ensures database and redis connections do not leak across event loops."""
    yield
    try:
        await engine.dispose()
    except Exception:
        pass
    try:
        await redis_client.close()
    except Exception:
        pass


@pytest.fixture(autouse=True)
def override_db_and_redis(request: pytest.FixtureRequest):
    """Provides mock DB session and Redis for unit tests unless real DB is requested."""
    # Don't override for integration tests that require live DB connection
    nodeid = request.node.nodeid
    if (
        "test_phase_1_database" in nodeid
        or "test_auth" in nodeid
        or "test_phase_4_dispatch_booking" in nodeid
    ):
        yield
        return

    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()
    mock_session.commit = AsyncMock()

    async def _get_db():
        yield mock_session

    mock_redis = AsyncMock()
    mock_redis.get.return_value = "online"
    mock_redis.set.return_value = True
    mock_redis.delete.return_value = True

    app.dependency_overrides[get_db_session] = _get_db
    app.dependency_overrides[get_redis] = lambda: mock_redis

    yield

    app.dependency_overrides.pop(get_db_session, None)
    app.dependency_overrides.pop(get_redis, None)


@pytest.fixture
async def async_client():
    """Async HTTP client fixture for API testing."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client
