import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.security import create_access_token
from app.main import app
from app.models.enums import (
    ProviderType,
    ProviderVerificationStatus,
    UserRole,
    UserStatus,
)
from app.models.provider import Provider
from app.models.user import User


@pytest.fixture
def provider_user() -> User:
    u_id = uuid.uuid4()
    return User(
        id=u_id,
        role=UserRole.PROVIDER.value,
        first_name="Ravi",
        last_name="Mechanic",
        phone="+919876543210",
        email="ravi@provider.com",
        status=UserStatus.ACTIVE.value,
    )


@pytest.fixture
def provider_record(provider_user: User) -> Provider:
    p_id = uuid.uuid4()
    return Provider(
        id=p_id,
        user_id=provider_user.id,
        business_name="Ravi Auto Garage",
        provider_type=ProviderType.GARAGE.value,
        description="24/7 Car and Bike repairs",
        phone="+919876543210",
        service_radius_km=Decimal("20.00"),
        rating_avg=Decimal("4.80"),
        rating_count=15,
        verification_status=ProviderVerificationStatus.VERIFIED.value,
        is_online=True,
    )


@pytest.fixture
def customer_user() -> User:
    u_id = uuid.uuid4()
    return User(
        id=u_id,
        role=UserRole.CUSTOMER.value,
        first_name="Ananya",
        last_name="Sharma",
        phone="+919876500000",
        email="ananya@customer.com",
        status=UserStatus.ACTIVE.value,
    )


@pytest.mark.asyncio
async def test_provider_reads_own_profile(
    provider_user: User, provider_record: Provider
) -> None:
    token = create_access_token(
        user_id=provider_user.id, role=UserRole.PROVIDER.value
    )
    headers = {"Authorization": f"Bearer {token}"}

    with (
        patch("app.api.deps.UserRepository.get_by_id", new_callable=AsyncMock) as mock_user_get,
        patch("app.services.provider_service.ProviderRepository.get_by_user_id", new_callable=AsyncMock) as mock_prov_get,
    ):
        mock_user_get.return_value = provider_user
        mock_prov_get.return_value = provider_record

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/v1/providers/me", headers=headers)

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["id"] == str(provider_record.id)
    assert data["business_name"] == "Ravi Auto Garage"
    assert data["verification_status"] == ProviderVerificationStatus.VERIFIED.value
    assert data["is_online"] is True


@pytest.mark.asyncio
async def test_provider_updates_own_profile(
    provider_user: User, provider_record: Provider
) -> None:
    token = create_access_token(
        user_id=provider_user.id, role=UserRole.PROVIDER.value
    )
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "business_name": "Ravi Modern Garage",
        "service_radius_km": 35.5,
        "description": "Expanded emergency towing and battery service",
    }

    with (
        patch("app.api.deps.UserRepository.get_by_id", new_callable=AsyncMock) as mock_user_get,
        patch("app.services.provider_service.ProviderRepository.get_by_user_id", new_callable=AsyncMock) as mock_prov_get,
        patch("app.services.provider_service.record_audit_event", new_callable=AsyncMock) as mock_audit,
    ):
        mock_user_get.return_value = provider_user
        mock_prov_get.return_value = provider_record

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.put(
                "/api/v1/providers/me", json=payload, headers=headers
            )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["business_name"] == "Ravi Modern Garage"
    assert float(data["service_radius_km"]) == 35.5
    assert mock_audit.called


@pytest.mark.asyncio
async def test_customer_cannot_access_provider_profile(customer_user: User) -> None:
    token = create_access_token(
        user_id=customer_user.id, role=UserRole.CUSTOMER.value
    )
    headers = {"Authorization": f"Bearer {token}"}

    with patch("app.api.deps.UserRepository.get_by_id", new_callable=AsyncMock) as mock_user_get:
        mock_user_get.return_value = customer_user

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/v1/providers/me", headers=headers)

    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "FORBIDDEN"


@pytest.mark.asyncio
async def test_public_provider_response_sanitized(provider_record: Provider) -> None:
    with patch(
        "app.services.provider_service.ProviderRepository.get_by_id",
        new_callable=AsyncMock,
    ) as mock_prov_get:
        mock_prov_get.return_value = provider_record

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(f"/api/v1/providers/{provider_record.id}")

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["id"] == str(provider_record.id)
    assert data["business_name"] == "Ravi Auto Garage"
    # Private verification status, phone, and user_id must NOT be exposed publicly
    assert "user_id" not in data
    assert "verification_status" not in data
    assert "phone" not in data


@pytest.mark.asyncio
async def test_profile_update_validation_radius_bounds(
    provider_user: User, provider_record: Provider
) -> None:
    token = create_access_token(
        user_id=provider_user.id, role=UserRole.PROVIDER.value
    )
    headers = {"Authorization": f"Bearer {token}"}

    # Radius > 200 km is invalid
    payload = {"service_radius_km": 500.0}

    with patch("app.api.deps.UserRepository.get_by_id", new_callable=AsyncMock) as mock_user_get:
        mock_user_get.return_value = provider_user

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.put(
                "/api/v1/providers/me", json=payload, headers=headers
            )

    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"
