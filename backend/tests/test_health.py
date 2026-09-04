import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_liveness_endpoint(async_client: AsyncClient):
    """Verify /health liveness probe returns HTTP 200 and expected status."""
    response = await async_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "environment" in data


@pytest.mark.asyncio
async def test_root_endpoint(async_client: AsyncClient):
    """Verify root endpoint returns welcome message and docs links."""
    response = await async_client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "RoadResQ" in data["message"]
