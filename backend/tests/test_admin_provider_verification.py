import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.security import create_access_token
from app.main import app
from app.models.enums import (
    ProviderDocumentStatus,
    ProviderDocumentType,
    ProviderType,
    ProviderVerificationStatus,
    UserRole,
    UserStatus,
)
from app.models.provider import Provider, ProviderDocument
from app.models.user import User


@pytest.fixture
def admin_user() -> User:
    return User(
        id=uuid.uuid4(),
        role=UserRole.ADMIN.value,
        first_name="Admin",
        last_name="Super",
        phone="+919876599999",
        email="admin@roadresq.com",
        status=UserStatus.ACTIVE.value,
    )


@pytest.fixture
def provider_record() -> Provider:
    return Provider(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        business_name="Karan Towing",
        provider_type=ProviderType.TOWING.value,
        service_radius_km=Decimal("15.00"),
        rating_avg=Decimal("0.00"),
        rating_count=0,
        verification_status=ProviderVerificationStatus.PENDING.value,
        is_online=False,
    )



@pytest.mark.asyncio
async def test_non_admin_forbidden_from_admin_endpoints(
    provider_record: Provider,
) -> None:
    # Customer tries to call admin endpoint
    customer_token = create_access_token(
        user_id=uuid.uuid4(), role=UserRole.CUSTOMER.value
    )
    headers = {"Authorization": f"Bearer {customer_token}"}

    customer_user = User(
        id=uuid.uuid4(),
        role=UserRole.CUSTOMER.value,
        first_name="Cust",
        status=UserStatus.ACTIVE.value,
    )

    with patch("app.api.deps.UserRepository.get_by_id", new_callable=AsyncMock) as mock_user_get:
        mock_user_get.return_value = customer_user

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/v1/admin/providers", headers=headers)

    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "FORBIDDEN"


@pytest.mark.asyncio
async def test_admin_lists_providers(
    admin_user: User, provider_record: Provider
) -> None:
    token = create_access_token(
        user_id=admin_user.id, role=UserRole.ADMIN.value
    )
    headers = {"Authorization": f"Bearer {token}"}

    with (
        patch("app.api.deps.UserRepository.get_by_id", new_callable=AsyncMock) as mock_user_get,
        patch("app.services.admin_provider_service.ProviderRepository.list_providers", new_callable=AsyncMock) as mock_list,
        patch("app.services.admin_provider_service.ProviderRepository.count_providers", new_callable=AsyncMock) as mock_count,
    ):
        mock_user_get.return_value = admin_user
        mock_list.return_value = [provider_record]
        mock_count.return_value = 1

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/v1/admin/providers?status=PENDING", headers=headers
            )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] == 1
    assert data["providers"][0]["business_name"] == "Karan Towing"


@pytest.mark.asyncio
async def test_admin_verifies_provider_status(
    admin_user: User, provider_record: Provider
) -> None:
    token = create_access_token(
        user_id=admin_user.id, role=UserRole.ADMIN.value
    )
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "verification_status": ProviderVerificationStatus.VERIFIED.value,
        "note": "All documents verified and physical inspection complete.",
    }

    with (
        patch("app.api.deps.UserRepository.get_by_id", new_callable=AsyncMock) as mock_user_get,
        patch("app.services.admin_provider_service.ProviderRepository.get_by_id", new_callable=AsyncMock) as mock_prov_get,
        patch("app.services.admin_provider_service.record_audit_event", new_callable=AsyncMock) as mock_audit,
    ):
        mock_user_get.return_value = admin_user
        mock_prov_get.return_value = provider_record

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.patch(
                f"/api/v1/admin/providers/{provider_record.id}/verification",
                json=payload,
                headers=headers,
            )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["verification_status"] == ProviderVerificationStatus.VERIFIED.value
    assert mock_audit.called


@pytest.mark.asyncio
async def test_admin_approves_and_rejects_document(
    admin_user: User, provider_record: Provider
) -> None:
    token = create_access_token(
        user_id=admin_user.id, role=UserRole.ADMIN.value
    )
    headers = {"Authorization": f"Bearer {token}"}

    doc = ProviderDocument(
        id=uuid.uuid4(),
        provider_id=provider_record.id,
        document_type=ProviderDocumentType.BUSINESS.value,
        file_url="https://storage.roadresq.com/docs/gst.pdf",
        status=ProviderDocumentStatus.PENDING.value,
    )

    with (
        patch("app.api.deps.UserRepository.get_by_id", new_callable=AsyncMock) as mock_user_get,
        patch("app.services.admin_provider_service.ProviderRepository.get_by_id", new_callable=AsyncMock) as mock_prov_get,
        patch("app.services.admin_provider_service.ProviderDocumentRepository.get_by_id", new_callable=AsyncMock) as mock_doc_get,
        patch("app.services.admin_provider_service.record_audit_event", new_callable=AsyncMock) as mock_audit,
    ):
        mock_user_get.return_value = admin_user
        mock_prov_get.return_value = provider_record
        mock_doc_get.return_value = doc

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            # 1. Approve
            resp_approve = await client.patch(
                f"/api/v1/admin/providers/{provider_record.id}/documents/{doc.id}",
                json={"status": "APPROVED"},
                headers=headers,
            )
            assert resp_approve.status_code == 200
            assert resp_approve.json()["data"]["status"] == "APPROVED"

            # 2. Reject with reason
            resp_reject = await client.patch(
                f"/api/v1/admin/providers/{provider_record.id}/documents/{doc.id}",
                json={
                    "status": "REJECTED",
                    "rejection_reason": "Document illegible / expired",
                },
                headers=headers,
            )
            assert resp_reject.status_code == 200
            assert resp_reject.json()["data"]["status"] == "REJECTED"
            assert mock_audit.called



@pytest.mark.asyncio
async def test_cross_provider_document_review_rejected(
    admin_user: User, provider_record: Provider
) -> None:
    token = create_access_token(
        user_id=admin_user.id, role=UserRole.ADMIN.value
    )
    headers = {"Authorization": f"Bearer {token}"}

    # Document belongs to a different provider
    doc = ProviderDocument(
        id=uuid.uuid4(),
        provider_id=uuid.uuid4(),
        document_type=ProviderDocumentType.BUSINESS.value,
        file_url="https://storage.roadresq.com/docs/gst.pdf",
        status=ProviderDocumentStatus.PENDING.value,
    )

    with (
        patch("app.api.deps.UserRepository.get_by_id", new_callable=AsyncMock) as mock_user_get,
        patch("app.services.admin_provider_service.ProviderRepository.get_by_id", new_callable=AsyncMock) as mock_prov_get,
        patch("app.services.admin_provider_service.ProviderDocumentRepository.get_by_id", new_callable=AsyncMock) as mock_doc_get,
    ):
        mock_user_get.return_value = admin_user
        mock_prov_get.return_value = provider_record
        mock_doc_get.return_value = doc

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.patch(
                f"/api/v1/admin/providers/{provider_record.id}/documents/{doc.id}",
                json={"status": "APPROVED"},
                headers=headers,
            )

    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "CROSS_PROVIDER_DOCUMENT_REVIEW_FORBIDDEN"
