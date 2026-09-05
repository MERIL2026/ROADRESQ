import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.security import create_access_token
from app.main import app
from app.models.enums import (
    ProviderDocumentStatus,
    ProviderDocumentType,
    UserRole,
    UserStatus,
)
from app.models.provider import Provider, ProviderDocument
from app.models.user import User


@pytest.fixture
def provider_user() -> User:
    return User(
        id=uuid.uuid4(),
        role=UserRole.PROVIDER.value,
        first_name="Suresh",
        last_name="Kumar",
        phone="+919876543211",
        email="suresh@provider.com",
        status=UserStatus.ACTIVE.value,
    )


@pytest.fixture
def provider_record(provider_user: User) -> Provider:
    return Provider(
        id=uuid.uuid4(),
        user_id=provider_user.id,
        business_name="Suresh Towing",
        phone="+919876543211",
    )


@pytest.mark.asyncio
async def test_provider_submits_document(
    provider_user: User, provider_record: Provider
) -> None:
    token = create_access_token(
        user_id=provider_user.id, role=UserRole.PROVIDER.value
    )
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "document_type": ProviderDocumentType.LICENSE.value,
        "file_url": "https://storage.roadresq.com/docs/suresh_license.pdf",
        "document_number": "DL-IND-2026-9999",
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
            resp = await client.post(
                "/api/v1/providers/me/documents", json=payload, headers=headers
            )

    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["document_type"] == ProviderDocumentType.LICENSE.value
    assert data["status"] == ProviderDocumentStatus.PENDING.value
    assert mock_audit.called


@pytest.mark.asyncio
async def test_document_unsafe_scheme_rejected(
    provider_user: User, provider_record: Provider
) -> None:
    token = create_access_token(
        user_id=provider_user.id, role=UserRole.PROVIDER.value
    )
    headers = {"Authorization": f"Bearer {token}"}
    # javascript: / ftp: schemes must be rejected
    payload = {
        "document_type": ProviderDocumentType.IDENTITY.value,
        "file_url": "javascript:alert(1)",
    }

    with (
        patch("app.api.deps.UserRepository.get_by_id", new_callable=AsyncMock) as mock_user_get,
        patch("app.services.provider_service.ProviderRepository.get_by_user_id", new_callable=AsyncMock) as mock_prov_get,
    ):
        mock_user_get.return_value = provider_user
        mock_prov_get.return_value = provider_record

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/v1/providers/me/documents", json=payload, headers=headers
            )

    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "STORAGE_INVALID_SCHEME"


@pytest.mark.asyncio
async def test_provider_lists_own_documents(
    provider_user: User, provider_record: Provider
) -> None:
    token = create_access_token(
        user_id=provider_user.id, role=UserRole.PROVIDER.value
    )
    headers = {"Authorization": f"Bearer {token}"}

    doc1 = ProviderDocument(
        id=uuid.uuid4(),
        provider_id=provider_record.id,
        document_type=ProviderDocumentType.IDENTITY.value,
        file_url="https://storage.roadresq.com/docs/id.pdf",
        status=ProviderDocumentStatus.APPROVED.value,
    )
    doc2 = ProviderDocument(
        id=uuid.uuid4(),
        provider_id=provider_record.id,
        document_type=ProviderDocumentType.BUSINESS.value,
        file_url="https://storage.roadresq.com/docs/gst.pdf",
        status=ProviderDocumentStatus.PENDING.value,
    )

    with (
        patch("app.api.deps.UserRepository.get_by_id", new_callable=AsyncMock) as mock_user_get,
        patch("app.services.provider_service.ProviderRepository.get_by_user_id", new_callable=AsyncMock) as mock_prov_get,
        patch("app.services.provider_service.ProviderDocumentRepository.list_by_provider", new_callable=AsyncMock) as mock_doc_list,
    ):
        mock_user_get.return_value = provider_user
        mock_prov_get.return_value = provider_record
        mock_doc_list.return_value = [doc1, doc2]

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/v1/providers/me/documents", headers=headers
            )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] == 2
    assert len(data["documents"]) == 2


@pytest.mark.asyncio
async def test_provider_cannot_delete_approved_document(
    provider_user: User, provider_record: Provider
) -> None:
    token = create_access_token(
        user_id=provider_user.id, role=UserRole.PROVIDER.value
    )
    headers = {"Authorization": f"Bearer {token}"}
    approved_doc = ProviderDocument(
        id=uuid.uuid4(),
        provider_id=provider_record.id,
        document_type=ProviderDocumentType.IDENTITY.value,
        file_url="https://storage.roadresq.com/docs/id.pdf",
        status=ProviderDocumentStatus.APPROVED.value,
    )

    with (
        patch("app.api.deps.UserRepository.get_by_id", new_callable=AsyncMock) as mock_user_get,
        patch("app.services.provider_service.ProviderRepository.get_by_user_id", new_callable=AsyncMock) as mock_prov_get,
        patch("app.services.provider_service.ProviderDocumentRepository.get_by_id", new_callable=AsyncMock) as mock_doc_get,
    ):
        mock_user_get.return_value = provider_user
        mock_prov_get.return_value = provider_record
        mock_doc_get.return_value = approved_doc

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.delete(
                f"/api/v1/providers/me/documents/{approved_doc.id}",
                headers=headers,
            )

    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "DOCUMENT_APPROVED_IMMUTABLE"


@pytest.mark.asyncio
async def test_provider_cannot_delete_another_providers_document(
    provider_user: User, provider_record: Provider
) -> None:
    token = create_access_token(
        user_id=provider_user.id, role=UserRole.PROVIDER.value
    )
    headers = {"Authorization": f"Bearer {token}"}
    other_provider_doc = ProviderDocument(
        id=uuid.uuid4(),
        provider_id=uuid.uuid4(),  # Different provider!
        document_type=ProviderDocumentType.IDENTITY.value,
        file_url="https://storage.roadresq.com/docs/other_id.pdf",
        status=ProviderDocumentStatus.PENDING.value,
    )

    with (
        patch("app.api.deps.UserRepository.get_by_id", new_callable=AsyncMock) as mock_user_get,
        patch("app.services.provider_service.ProviderRepository.get_by_user_id", new_callable=AsyncMock) as mock_prov_get,
        patch("app.services.provider_service.ProviderDocumentRepository.get_by_id", new_callable=AsyncMock) as mock_doc_get,
    ):
        mock_user_get.return_value = provider_user
        mock_prov_get.return_value = provider_record
        mock_doc_get.return_value = other_provider_doc

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.delete(
                f"/api/v1/providers/me/documents/{other_provider_doc.id}",
                headers=headers,
            )

    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "FORBIDDEN"
