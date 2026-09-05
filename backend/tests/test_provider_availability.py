import uuid
from datetime import time
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.security import create_access_token
from app.main import app
from app.models.enums import UserRole, UserStatus
from app.models.provider import Provider, ProviderAvailability
from app.models.user import User


@pytest.fixture
def provider_user() -> User:
    return User(
        id=uuid.uuid4(),
        role=UserRole.PROVIDER.value,
        first_name="Deepak",
        last_name="Sharma",
        phone="+919876543213",
        email="deepak@provider.com",
        status=UserStatus.ACTIVE.value,
    )


@pytest.fixture
def provider_record(provider_user: User) -> Provider:
    return Provider(
        id=uuid.uuid4(),
        user_id=provider_user.id,
        business_name="Deepak Battery Care",
        phone="+919876543213",
    )


@pytest.mark.asyncio
async def test_provider_sets_valid_weekly_availability(
    provider_user: User, provider_record: Provider
) -> None:
    token = create_access_token(
        user_id=provider_user.id, role=UserRole.PROVIDER.value
    )
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "slots": [
            {
                "day_of_week": 0,  # Monday
                "start_time": "08:00:00",
                "end_time": "14:00:00",
                "is_active": True,
            },
            {
                "day_of_week": 0,  # Monday afternoon
                "start_time": "15:00:00",
                "end_time": "20:00:00",
                "is_active": True,
            },
            {
                "day_of_week": 1,  # Tuesday
                "start_time": "09:00:00",
                "end_time": "18:00:00",
                "is_active": True,
            },
        ]
    }

    mock_created = [
        ProviderAvailability(
            id=uuid.uuid4(),
            provider_id=provider_record.id,
            day_of_week=0,
            start_time=time(8, 0),
            end_time=time(14, 0),
            is_active=True,
        ),
        ProviderAvailability(
            id=uuid.uuid4(),
            provider_id=provider_record.id,
            day_of_week=0,
            start_time=time(15, 0),
            end_time=time(20, 0),
            is_active=True,
        ),
        ProviderAvailability(
            id=uuid.uuid4(),
            provider_id=provider_record.id,
            day_of_week=1,
            start_time=time(9, 0),
            end_time=time(18, 0),
            is_active=True,
        ),
    ]

    with (
        patch("app.api.deps.UserRepository.get_by_id", new_callable=AsyncMock) as mock_user_get,
        patch("app.services.provider_service.ProviderRepository.get_by_user_id", new_callable=AsyncMock) as mock_prov_get,
        patch("app.services.provider_service.ProviderAvailabilityRepository.replace_schedule", new_callable=AsyncMock) as mock_replace,
        patch("app.services.provider_service.record_audit_event", new_callable=AsyncMock),
    ):
        mock_user_get.return_value = provider_user
        mock_prov_get.return_value = provider_record
        mock_replace.return_value = mock_created

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.put(
                "/api/v1/providers/me/availability",
                json=payload,
                headers=headers,
            )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data["slots"]) == 3


@pytest.mark.asyncio
async def test_overlapping_slots_rejected(provider_user: User) -> None:
    token = create_access_token(
        user_id=provider_user.id, role=UserRole.PROVIDER.value
    )
    headers = {"Authorization": f"Bearer {token}"}
    # Slots overlap on Day 0 (Monday: 08:00-14:00 overlaps with 12:00-18:00)
    payload = {
        "slots": [
            {
                "day_of_week": 0,
                "start_time": "08:00:00",
                "end_time": "14:00:00",
                "is_active": True,
            },
            {
                "day_of_week": 0,
                "start_time": "12:00:00",
                "end_time": "18:00:00",
                "is_active": True,
            },
        ]
    }

    with patch("app.api.deps.UserRepository.get_by_id", new_callable=AsyncMock) as mock_user_get:
        mock_user_get.return_value = provider_user

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.put(
                "/api/v1/providers/me/availability",
                json=payload,
                headers=headers,
            )

    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_invalid_time_range_rejected(provider_user: User) -> None:
    token = create_access_token(
        user_id=provider_user.id, role=UserRole.PROVIDER.value
    )
    headers = {"Authorization": f"Bearer {token}"}
    # start_time >= end_time is invalid
    payload = {
        "slots": [
            {
                "day_of_week": 2,
                "start_time": "18:00:00",
                "end_time": "09:00:00",
                "is_active": True,
            }
        ]
    }

    with patch("app.api.deps.UserRepository.get_by_id", new_callable=AsyncMock) as mock_user_get:
        mock_user_get.return_value = provider_user

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.put(
                "/api/v1/providers/me/availability",
                json=payload,
                headers=headers,
            )

    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"
