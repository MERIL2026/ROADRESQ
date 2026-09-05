import uuid
from datetime import UTC, datetime, time
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.models.enums import ProviderVerificationStatus, UserStatus
from app.models.provider import Provider, ProviderAvailability, ProviderService
from app.models.user import User
from app.services.eligibility_service import ProviderEligibilityService


@pytest.fixture
def provider_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def service_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def user_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def active_user(user_id: uuid.UUID) -> User:
    return User(
        id=user_id,
        first_name="Eligible",
        last_name="Provider",
        status=UserStatus.ACTIVE.value,
    )


@pytest.fixture
def eligible_provider(provider_id: uuid.UUID, user_id: uuid.UUID) -> Provider:
    return Provider(
        id=provider_id,
        user_id=user_id,
        business_name="Fast Rescue",
        verification_status=ProviderVerificationStatus.VERIFIED.value,
        is_online=True,
    )


@pytest.mark.asyncio
async def test_fully_eligible_provider_evaluates_true(
    provider_id: uuid.UUID,
    service_id: uuid.UUID,
    active_user: User,
    eligible_provider: Provider,
) -> None:
    session = AsyncMock()
    redis = AsyncMock()

    # Redis presence is active
    redis.get.return_value = "online"

    # Evaluation time: Monday 10:30 AM
    eval_time = datetime(2026, 9, 7, 10, 30, 0, tzinfo=UTC)  # 2026-09-07 is Monday (weekday=0)

    # Active capability
    provider_svc = ProviderService(
        id=uuid.uuid4(),
        provider_id=provider_id,
        service_id=service_id,
        price_from=Decimal("200.00"),
        price_to=Decimal("500.00"),
        is_active=True,
    )

    # Active availability slot for Monday (0) 08:00 - 18:00
    avail_slot = ProviderAvailability(
        id=uuid.uuid4(),
        provider_id=provider_id,
        day_of_week=0,
        start_time=time(8, 0),
        end_time=time(18, 0),
        is_active=True,
    )

    service = ProviderEligibilityService(session=session, redis=redis)
    service.provider_repo.get_by_id = AsyncMock(return_value=eligible_provider)
    service.user_repo.get_by_id = AsyncMock(return_value=active_user)
    service.svc_repo.get_by_provider_and_service = AsyncMock(
        return_value=provider_svc
    )
    service.avail_repo.list_by_provider = AsyncMock(return_value=[avail_slot])

    result = await service.evaluate_provider_eligibility(
        provider_id=provider_id,
        service_id=service_id,
        evaluation_time=eval_time,
    )

    assert result.is_eligible is True
    assert len(result.rejection_reasons) == 0
    assert result.details["redis_presence"] is True
    assert result.details["service_offered"] is True
    assert result.details["availability_match"] is True


@pytest.mark.asyncio
async def test_ineligible_when_provider_offline(
    provider_id: uuid.UUID,
    service_id: uuid.UUID,
    active_user: User,
    eligible_provider: Provider,
) -> None:
    session = AsyncMock()
    redis = AsyncMock()

    # Provider DB is_online is False
    eligible_provider.is_online = False

    service = ProviderEligibilityService(session=session, redis=redis)
    service.provider_repo.get_by_id = AsyncMock(return_value=eligible_provider)
    service.user_repo.get_by_id = AsyncMock(return_value=active_user)
    service.svc_repo.get_by_provider_and_service = AsyncMock(return_value=None)
    service.avail_repo.list_by_provider = AsyncMock(return_value=[])

    result = await service.evaluate_provider_eligibility(
        provider_id=provider_id,
        service_id=service_id,
    )

    assert result.is_eligible is False
    assert any("offline in database" in r for r in result.rejection_reasons)


@pytest.mark.asyncio
async def test_ineligible_when_pending_verification(
    provider_id: uuid.UUID,
    service_id: uuid.UUID,
    active_user: User,
    eligible_provider: Provider,
) -> None:
    session = AsyncMock()
    redis = AsyncMock()

    # Status is PENDING
    eligible_provider.verification_status = (
        ProviderVerificationStatus.PENDING.value
    )

    service = ProviderEligibilityService(session=session, redis=redis)
    service.provider_repo.get_by_id = AsyncMock(return_value=eligible_provider)
    service.user_repo.get_by_id = AsyncMock(return_value=active_user)
    service.svc_repo.get_by_provider_and_service = AsyncMock(return_value=None)
    service.avail_repo.list_by_provider = AsyncMock(return_value=[])

    result = await service.evaluate_provider_eligibility(
        provider_id=provider_id,
        service_id=service_id,
    )

    assert result.is_eligible is False
    assert any("not eligible for dispatch" in r for r in result.rejection_reasons)


@pytest.mark.asyncio
async def test_ineligible_when_outside_availability_hours(
    provider_id: uuid.UUID,
    service_id: uuid.UUID,
    active_user: User,
    eligible_provider: Provider,
) -> None:
    session = AsyncMock()
    redis = AsyncMock()
    redis.get.return_value = "online"

    # Evaluation time: Monday 22:00 (10 PM)
    eval_time = datetime(2026, 9, 7, 22, 0, 0, tzinfo=UTC)

    provider_svc = ProviderService(
        id=uuid.uuid4(),
        provider_id=provider_id,
        service_id=service_id,
        is_active=True,
    )

    # Availability ends at 18:00
    avail_slot = ProviderAvailability(
        id=uuid.uuid4(),
        provider_id=provider_id,
        day_of_week=0,
        start_time=time(8, 0),
        end_time=time(18, 0),
        is_active=True,
    )

    service = ProviderEligibilityService(session=session, redis=redis)
    service.provider_repo.get_by_id = AsyncMock(return_value=eligible_provider)
    service.user_repo.get_by_id = AsyncMock(return_value=active_user)
    service.svc_repo.get_by_provider_and_service = AsyncMock(
        return_value=provider_svc
    )
    service.avail_repo.list_by_provider = AsyncMock(return_value=[avail_slot])

    result = await service.evaluate_provider_eligibility(
        provider_id=provider_id,
        service_id=service_id,
        evaluation_time=eval_time,
    )

    assert result.is_eligible is False
    assert any("outside provider working hours" in r for r in result.rejection_reasons)
