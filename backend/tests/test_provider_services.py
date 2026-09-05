import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.security import create_access_token
from app.main import app
from app.models.enums import ServiceCategory, UserRole, UserStatus
from app.models.provider import Provider, ProviderService
from app.models.service import Service
from app.models.user import User


@pytest.fixture
def provider_user() -> User:
    return User(
        id=uuid.uuid4(),
        role=UserRole.PROVIDER.value,
        first_name="Amit",
        last_name="Patel",
        phone="+919876543212",
        email="amit@provider.com",
        status=UserStatus.ACTIVE.value,
    )


@pytest.fixture
def provider_record(provider_user: User) -> Provider:
    return Provider(
        id=uuid.uuid4(),
        user_id=provider_user.id,
        business_name="Amit Quick Fix",
        phone="+919876543212",
    )


@pytest.fixture
def catalog_service() -> Service:
    return Service(
        id=uuid.uuid4(),
        name="Flat Tyre Replacement",
        category=ServiceCategory.TYRE.value,
        base_price=Decimal("350.00"),
        is_emergency=True,
        is_active=True,
    )


@pytest.mark.asyncio
async def test_service_catalog_listing(catalog_service: Service) -> None:
    with patch(
        "app.api.v1.services.ServiceRepository.list_active",
        new_callable=AsyncMock,
    ) as mock_svc_list:
        mock_svc_list.return_value = [catalog_service]

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/v1/services")

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] == 1
    assert data["services"][0]["name"] == "Flat Tyre Replacement"


@pytest.mark.asyncio
async def test_provider_adds_service_capability(
    provider_user: User, provider_record: Provider, catalog_service: Service
) -> None:
    token = create_access_token(
        user_id=provider_user.id, role=UserRole.PROVIDER.value
    )
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "service_id": str(catalog_service.id),
        "price_from": 350.0,
        "price_to": 600.0,
    }

    with (
        patch("app.api.deps.UserRepository.get_by_id", new_callable=AsyncMock) as mock_user_get,
        patch("app.services.provider_service.ProviderRepository.get_by_user_id", new_callable=AsyncMock) as mock_prov_get,
        patch("app.services.provider_service.ServiceRepository.get_by_id", new_callable=AsyncMock) as mock_cat_get,
        patch("app.services.provider_service.ProviderServiceRepository.get_by_provider_and_service", new_callable=AsyncMock) as mock_dup_check,
        patch("app.services.provider_service.record_audit_event", new_callable=AsyncMock),
    ):
        mock_user_get.return_value = provider_user
        mock_prov_get.return_value = provider_record
        mock_cat_get.return_value = catalog_service
        mock_dup_check.return_value = None  # No duplicate

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/v1/providers/me/services", json=payload, headers=headers
            )

    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["service_name"] == "Flat Tyre Replacement"
    assert float(data["price_from"]) == 350.0
    assert float(data["price_to"]) == 600.0


@pytest.mark.asyncio
async def test_duplicate_service_mapping_rejected(
    provider_user: User, provider_record: Provider, catalog_service: Service
) -> None:
    token = create_access_token(
        user_id=provider_user.id, role=UserRole.PROVIDER.value
    )
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "service_id": str(catalog_service.id),
        "price_from": 400.0,
        "price_to": 700.0,
    }

    existing_ps = ProviderService(
        id=uuid.uuid4(),
        provider_id=provider_record.id,
        service_id=catalog_service.id,
    )

    with (
        patch("app.api.deps.UserRepository.get_by_id", new_callable=AsyncMock) as mock_user_get,
        patch("app.services.provider_service.ProviderRepository.get_by_user_id", new_callable=AsyncMock) as mock_prov_get,
        patch("app.services.provider_service.ServiceRepository.get_by_id", new_callable=AsyncMock) as mock_cat_get,
        patch("app.services.provider_service.ProviderServiceRepository.get_by_provider_and_service", new_callable=AsyncMock) as mock_dup_check,
    ):
        mock_user_get.return_value = provider_user
        mock_prov_get.return_value = provider_record
        mock_cat_get.return_value = catalog_service
        mock_dup_check.return_value = existing_ps  # Already mapped!

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/v1/providers/me/services", json=payload, headers=headers
            )

    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "PROVIDER_SERVICE_DUPLICATE"


@pytest.mark.asyncio
async def test_invalid_price_range_rejected(
    provider_user: User, catalog_service: Service
) -> None:
    token = create_access_token(
        user_id=provider_user.id, role=UserRole.PROVIDER.value
    )
    headers = {"Authorization": f"Bearer {token}"}
    # price_from > price_to is invalid
    payload = {
        "service_id": str(catalog_service.id),
        "price_from": 1000.0,
        "price_to": 500.0,
    }

    with patch("app.api.deps.UserRepository.get_by_id", new_callable=AsyncMock) as mock_user_get:
        mock_user_get.return_value = provider_user

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/v1/providers/me/services", json=payload, headers=headers
            )

    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"
