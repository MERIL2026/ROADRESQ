import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_redis
from app.core.security import create_access_token
from app.main import app
from app.models.enums import (
    ProviderVerificationStatus,
    UserRole,
    UserStatus,
)
from app.models.provider import Provider
from app.models.user import User


@pytest.fixture
def provider_user() -> User:
    return User(
        id=uuid.uuid4(),
        role=UserRole.PROVIDER.value,
        first_name="Vikram",
        last_name="Singh",
        phone="+919876543214",
        email="vikram@provider.com",
        status=UserStatus.ACTIVE.value,
    )


@pytest.fixture
def verified_provider(provider_user: User) -> Provider:
    return Provider(
        id=uuid.uuid4(),
        user_id=provider_user.id,
        business_name="Vikram Rescue",
        verification_status=ProviderVerificationStatus.VERIFIED.value,
        is_online=False,
    )


@pytest.fixture
def pending_provider(provider_user: User) -> Provider:
    return Provider(
        id=uuid.uuid4(),
        user_id=provider_user.id,
        business_name="Vikram Rescue",
        verification_status=ProviderVerificationStatus.PENDING.value,
        is_online=False,
    )


@pytest.mark.asyncio
async def test_pending_provider_cannot_go_online(
    provider_user: User, pending_provider: Provider
) -> None:
    token = create_access_token(
        user_id=provider_user.id, role=UserRole.PROVIDER.value
    )
    headers = {"Authorization": f"Bearer {token}"}
    payload = {"is_online": True}

    with (
        patch("app.api.deps.UserRepository.get_by_id", new_callable=AsyncMock) as mock_user_get,
        patch("app.services.provider_service.UserRepository.get_by_id", new_callable=AsyncMock) as mock_svc_user,
        patch("app.services.provider_service.ProviderRepository.get_by_user_id", new_callable=AsyncMock) as mock_prov_get,
    ):
        mock_user_get.return_value = provider_user
        mock_svc_user.return_value = provider_user
        mock_prov_get.return_value = pending_provider

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/v1/providers/me/status", json=payload, headers=headers
            )

    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "PROVIDER_NOT_VERIFIED"


@pytest.mark.asyncio
async def test_verified_provider_without_approved_docs_cannot_go_online(
    provider_user: User, verified_provider: Provider
) -> None:
    token = create_access_token(
        user_id=provider_user.id, role=UserRole.PROVIDER.value
    )
    headers = {"Authorization": f"Bearer {token}"}
    payload = {"is_online": True}

    with (
        patch("app.api.deps.UserRepository.get_by_id", new_callable=AsyncMock) as mock_user_get,
        patch("app.services.provider_service.UserRepository.get_by_id", new_callable=AsyncMock) as mock_svc_user,
        patch("app.services.provider_service.ProviderRepository.get_by_user_id", new_callable=AsyncMock) as mock_prov_get,
        patch("app.services.provider_service.ProviderDocumentRepository.count_approved", new_callable=AsyncMock) as mock_doc_count,
    ):
        mock_user_get.return_value = provider_user
        mock_svc_user.return_value = provider_user
        mock_prov_get.return_value = verified_provider
        mock_doc_count.return_value = 0  # 0 approved documents

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/v1/providers/me/status", json=payload, headers=headers
            )

    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "PROVIDER_NO_APPROVED_DOCUMENTS"


@pytest.mark.asyncio
async def test_verified_provider_without_services_cannot_go_online(
    provider_user: User, verified_provider: Provider
) -> None:
    token = create_access_token(
        user_id=provider_user.id, role=UserRole.PROVIDER.value
    )
    headers = {"Authorization": f"Bearer {token}"}
    payload = {"is_online": True}

    with (
        patch("app.api.deps.UserRepository.get_by_id", new_callable=AsyncMock) as mock_user_get,
        patch("app.services.provider_service.UserRepository.get_by_id", new_callable=AsyncMock) as mock_svc_user,
        patch("app.services.provider_service.ProviderRepository.get_by_user_id", new_callable=AsyncMock) as mock_prov_get,
        patch("app.services.provider_service.ProviderDocumentRepository.count_approved", new_callable=AsyncMock) as mock_doc_count,
        patch("app.services.provider_service.ProviderServiceRepository.count_active", new_callable=AsyncMock) as mock_svc_count,
    ):
        mock_user_get.return_value = provider_user
        mock_svc_user.return_value = provider_user
        mock_prov_get.return_value = verified_provider
        mock_doc_count.return_value = 1  # 1 approved doc
        mock_svc_count.return_value = 0  # 0 active services

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/v1/providers/me/status", json=payload, headers=headers
            )

    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "PROVIDER_NO_ACTIVE_SERVICES"


@pytest.mark.asyncio
async def test_fully_eligible_provider_goes_online_and_offline(
    provider_user: User, verified_provider: Provider
) -> None:
    token = create_access_token(
        user_id=provider_user.id, role=UserRole.PROVIDER.value
    )
    headers = {"Authorization": f"Bearer {token}"}

    mock_redis = AsyncMock()
    app.dependency_overrides[get_redis] = lambda: mock_redis

    with (
        patch("app.api.deps.UserRepository.get_by_id", new_callable=AsyncMock) as mock_user_get,
        patch("app.services.provider_service.UserRepository.get_by_id", new_callable=AsyncMock) as mock_svc_user,
        patch("app.services.provider_service.ProviderRepository.get_by_user_id", new_callable=AsyncMock) as mock_prov_get,
        patch("app.services.provider_service.ProviderDocumentRepository.count_approved", new_callable=AsyncMock) as mock_doc_count,
        patch("app.services.provider_service.ProviderServiceRepository.count_active", new_callable=AsyncMock) as mock_svc_count,
        patch("app.services.provider_service.record_audit_event", new_callable=AsyncMock),
    ):

        mock_user_get.return_value = provider_user
        mock_svc_user.return_value = provider_user
        mock_prov_get.return_value = verified_provider
        mock_doc_count.return_value = 2
        mock_svc_count.return_value = 3

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            # 1. Go Online
            resp_on = await client.post(
                "/api/v1/providers/me/status",
                json={"is_online": True},
                headers=headers,
            )
            assert resp_on.status_code == 200
            assert resp_on.json()["data"]["is_online"] is True
            assert mock_redis.set.called

            # 2. Go Offline
            resp_off = await client.post(
                "/api/v1/providers/me/status",
                json={"is_online": False},
                headers=headers,
            )
            assert resp_off.status_code == 200
            assert resp_off.json()["data"]["is_online"] is False
            assert mock_redis.delete.called
