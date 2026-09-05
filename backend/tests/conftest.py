import pytest
from httpx import ASGITransport, AsyncClient

from app.core.db import engine
from app.core.redis import redis_client
from app.main import app


@pytest.fixture(autouse=True)
async def cleanup_connections():
    """Ensures database and redis connections do not leak across event loops."""
    yield
    await engine.dispose()
    await redis_client.close()


@pytest.fixture
async def async_client():
    """Async HTTP client fixture for API testing."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client
