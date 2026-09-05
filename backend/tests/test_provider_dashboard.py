import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.security import create_access_token
from app.main import app
from app.models.booking import Booking
from app.models.enums import BookingStatus, BookingType, UserRole, UserStatus
from app.models.provider import Provider
from app.models.service import Service
from app.models.user import User


@pytest.fixture
def provider_user() -> User:
    return User(
        id=uuid.uuid4(),
        role=UserRole.PROVIDER.value,
        first_name="Mahesh",
        last_name="Yadav",
        phone="+919876543215",
        email="mahesh@provider.com",
        status=UserStatus.ACTIVE.value,
    )


@pytest.fixture
def provider_record(provider_user: User) -> Provider:
    return Provider(
        id=uuid.uuid4(),
        user_id=provider_user.id,
        business_name="Mahesh Auto Service",
        rating_avg=Decimal("4.90"),
        rating_count=30,
        phone="+919876543215",
        verification_status="ACTIVE",
        is_online=True,
    )



@pytest.mark.asyncio
async def test_provider_dashboard_metrics(
    provider_user: User, provider_record: Provider
) -> None:
    token = create_access_token(
        user_id=provider_user.id, role=UserRole.PROVIDER.value
    )
    headers = {"Authorization": f"Bearer {token}"}

    with (
        patch("app.api.deps.UserRepository.get_by_id", new_callable=AsyncMock) as mock_user_get,
        patch("app.services.provider_service.ProviderRepository.get_by_user_id", new_callable=AsyncMock) as mock_prov_get,
        patch("app.services.provider_service.ProviderBookingQueryRepository.count_active_bookings", new_callable=AsyncMock) as mock_active_count,
        patch("app.services.provider_service.ProviderBookingQueryRepository.count_completed_bookings", new_callable=AsyncMock) as mock_comp_count,
        patch("app.services.provider_service.ProviderDocumentRepository.count_total", new_callable=AsyncMock) as mock_total_docs,
        patch("app.services.provider_service.ProviderDocumentRepository.count_approved", new_callable=AsyncMock) as mock_app_docs,
        patch("app.services.provider_service.ProviderServiceRepository.count_active", new_callable=AsyncMock) as mock_act_svc,
    ):
        mock_user_get.return_value = provider_user
        mock_prov_get.return_value = provider_record
        mock_active_count.return_value = 3
        mock_comp_count.return_value = 45
        mock_total_docs.return_value = 4
        mock_app_docs.return_value = 3
        mock_act_svc.return_value = 5

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/v1/providers/me/dashboard", headers=headers
            )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["business_name"] == "Mahesh Auto Service"
    assert data["active_bookings_count"] == 3
    assert data["completed_bookings_count"] == 45
    assert data["approved_documents_count"] == 3
    assert data["active_services_count"] == 5


@pytest.mark.asyncio
async def test_provider_lists_assigned_bookings(
    provider_user: User, provider_record: Provider
) -> None:
    token = create_access_token(
        user_id=provider_user.id, role=UserRole.PROVIDER.value
    )
    headers = {"Authorization": f"Bearer {token}"}

    customer = User(
        id=uuid.uuid4(),
        first_name="Pooja",
        last_name="Nair",
        phone="+919876599999",
    )
    svc = Service(
        id=uuid.uuid4(),
        name="Emergency Battery Jumpstart",
        category="BATTERY",
    )
    mock_booking = Booking(
        id=uuid.uuid4(),
        booking_number="BK-202609-001",
        customer_id=customer.id,
        vehicle_id=uuid.uuid4(),
        provider_id=provider_record.id,
        service_id=svc.id,
        booking_type=BookingType.EMERGENCY.value,
        status=BookingStatus.ACCEPTED.value,
        problem_description="Car will not turn over in mall parking",
        customer=customer,
        service=svc,
    )

    with (
        patch("app.api.deps.UserRepository.get_by_id", new_callable=AsyncMock) as mock_user_get,
        patch("app.services.provider_service.ProviderRepository.get_by_user_id", new_callable=AsyncMock) as mock_prov_get,
        patch("app.services.provider_service.ProviderBookingQueryRepository.list_assigned_bookings", new_callable=AsyncMock) as mock_list_bks,
    ):
        mock_user_get.return_value = provider_user
        mock_prov_get.return_value = provider_record
        mock_list_bks.return_value = [mock_booking]

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/v1/providers/me/bookings", headers=headers
            )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] == 1
    assert data["bookings"][0]["booking_number"] == "BK-202609-001"
    assert data["bookings"][0]["customer_name"] == "Pooja Nair"
    assert data["bookings"][0]["service_name"] == "Emergency Battery Jumpstart"
