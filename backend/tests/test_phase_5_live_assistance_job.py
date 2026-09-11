"""Phase 5: Live Assistance & Job Execution — Comprehensive Test Suite."""

import json
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_redis
from app.core.security import create_access_token
from app.core.websocket import ws_manager
from app.main import app
from app.models.booking import Booking, BookingLocation
from app.models.enums import (
    BookingStatus,
    BookingType,
    EstimateStatus,
    InspectionCondition,
    JobStatus,
    LocationType,
    ProviderVerificationStatus,
    UserRole,
    UserStatus,
    VehicleFuelType,
)
from app.models.job import (
    Estimate,
    EstimateItem,
    Inspection,
    InspectionItem,
    JobCard,
)
from app.models.provider import Provider
from app.models.service import Service
from app.models.user import User
from app.models.vehicle import Vehicle
from app.schemas.estimate import (
    EstimateCreateRequest,
    EstimateItemCreate,
    EstimateRejectRequest,
    EstimateReviseRequest,
)
from app.schemas.inspection import InspectionCreateRequest, InspectionItemCreate
from app.schemas.job import JobCardCompleteRequest
from app.schemas.tracking import ArrivalVerifyRequest, ProviderLocationPingRequest
from app.services.estimate_service import EstimateService
from app.services.job_service import JobService
from app.services.tracking_service import TrackingService

# ==============================================================================
# Shared Fixtures
# ==============================================================================


@pytest.fixture
def customer_user() -> User:
    return User(
        id=uuid.uuid4(),
        role=UserRole.CUSTOMER.value,
        first_name="Priya",
        last_name="Sharma",
        phone="+919876540001",
        email="priya@customer.com",
        status=UserStatus.ACTIVE.value,
    )


@pytest.fixture
def other_customer_user() -> User:
    return User(
        id=uuid.uuid4(),
        role=UserRole.CUSTOMER.value,
        first_name="Rohan",
        last_name="Verma",
        phone="+919876540099",
        email="rohan@customer.com",
        status=UserStatus.ACTIVE.value,
    )


@pytest.fixture
def provider_user() -> User:
    return User(
        id=uuid.uuid4(),
        role=UserRole.PROVIDER.value,
        first_name="Arjun",
        last_name="Mehta",
        phone="+919876540002",
        email="arjun@provider.com",
        status=UserStatus.ACTIVE.value,
    )


@pytest.fixture
def other_provider_user() -> User:
    return User(
        id=uuid.uuid4(),
        role=UserRole.PROVIDER.value,
        first_name="Vikram",
        last_name="Singh",
        phone="+919876540098",
        email="vikram@provider.com",
        status=UserStatus.ACTIVE.value,
    )


@pytest.fixture
def admin_user() -> User:
    return User(
        id=uuid.uuid4(),
        role=UserRole.ADMIN.value,
        first_name="Admin",
        last_name="User",
        phone="+919876540000",
        email="admin@roadresq.com",
        status=UserStatus.ACTIVE.value,
    )


@pytest.fixture
def verified_provider(provider_user: User) -> Provider:
    return Provider(
        id=uuid.uuid4(),
        user_id=provider_user.id,
        business_name="Arjun Motors",
        provider_type="MECHANIC",
        verification_status=ProviderVerificationStatus.VERIFIED.value,
        is_online=True,
        phone="+919876540002",
        rating_avg=Decimal("4.8"),
        rating_count=35,
        service_radius_km=Decimal("20.0"),
    )


@pytest.fixture
def other_verified_provider(other_provider_user: User) -> Provider:
    return Provider(
        id=uuid.uuid4(),
        user_id=other_provider_user.id,
        business_name="Vikram Repairs",
        provider_type="MECHANIC",
        verification_status=ProviderVerificationStatus.VERIFIED.value,
        is_online=True,
        phone="+919876540098",
        rating_avg=Decimal("4.5"),
        rating_count=15,
        service_radius_km=Decimal("15.0"),
    )


@pytest.fixture
def sample_service() -> Service:
    return Service(
        id=uuid.uuid4(),
        name="Flat Tyre Repair",
        category="TYRE",
        base_price=Decimal("499.00"),
        is_emergency=True,
        is_active=True,
    )


@pytest.fixture
def customer_vehicle(customer_user: User) -> Vehicle:
    return Vehicle(
        id=uuid.uuid4(),
        user_id=customer_user.id,
        registration_number="MH01AB1234",
        make="Hyundai",
        model="Creta",
        fuel_type=VehicleFuelType.PETROL.value,
        is_primary=True,
    )


@pytest.fixture
def active_booking(
    customer_user: User,
    verified_provider: Provider,
    customer_vehicle: Vehicle,
    sample_service: Service,
) -> Booking:
    booking = Booking(
        id=uuid.uuid4(),
        booking_number="RR-2026-0911-001",
        customer_id=customer_user.id,
        vehicle_id=customer_vehicle.id,
        provider_id=verified_provider.id,
        service_id=sample_service.id,
        booking_type=BookingType.EMERGENCY.value,
        status=BookingStatus.ON_THE_WAY.value,
        problem_description="Left front tyre puncture on highway",
        requested_at=datetime.now(UTC),
        accepted_at=datetime.now(UTC),
    )
    # Pickup location coordinates: 19.0760, 72.8777 (Mumbai)
    loc = BookingLocation(
        id=uuid.uuid4(),
        booking_id=booking.id,
        location_type=LocationType.PICKUP.value,
        address_text="Bandra West, Mumbai",
        location="POINT(72.8777 19.0760)",
    )
    booking.locations = [loc]
    return booking


@pytest.fixture
def sample_job_card(active_booking: Booking, verified_provider: Provider) -> JobCard:
    return JobCard(
        id=uuid.uuid4(),
        booking_id=active_booking.id,
        provider_id=verified_provider.id,
        job_status=JobStatus.INSPECTION.value,
        started_at=datetime.now(UTC),
    )


@pytest.fixture
def mock_redis() -> AsyncMock:
    """In-memory AsyncMock mimicking Redis operations."""
    store: dict[str, str] = {}

    mock = AsyncMock()

    async def _get(key: str) -> str | None:
        return store.get(key)

    async def _set(
        key: str, value: str, expire_seconds: int | None = None, ex: int | None = None
    ) -> bool:
        store[key] = str(value)
        return True

    async def _delete(key: str) -> bool:
        return bool(store.pop(key, None))

    async def _incr(key: str) -> int:
        val = int(store.get(key, 0)) + 1
        store[key] = str(val)
        return val

    async def _ttl(key: str) -> int:
        return 600

    async def _geoadd(key: str, *args: object, **kwargs: object) -> int:
        return 1

    mock.get.side_effect = _get
    mock.set.side_effect = _set
    mock.delete.side_effect = _delete
    mock.incr.side_effect = _incr
    mock.ttl.side_effect = _ttl
    mock.geoadd.side_effect = _geoadd
    mock.client = mock
    return mock


# ==============================================================================
# 1. TRACKING & LIVE LOCATION TESTS
# ==============================================================================


@pytest.mark.asyncio
async def test_provider_location_push_updates_redis_and_history(
    provider_user: User,
    verified_provider: Provider,
    active_booking: Booking,
    mock_redis: AsyncMock,
) -> None:
    """Test that provider GPS update stores current point in Redis and persists telemetry history."""
    session = AsyncMock()

    service = TrackingService(session, mock_redis)
    service.provider_repo.get_by_user_id = AsyncMock(return_value=verified_provider)
    service.booking_repo.list_by_provider = AsyncMock(return_value=[active_booking])
    service.tracking_repo.create_location_update = AsyncMock()

    req = ProviderLocationPingRequest(
        latitude=19.0750,
        longitude=72.8770,
        accuracy_m=Decimal("5.0"),
        heading=Decimal("90.0"),
        speed_kmh=Decimal("35.0"),
    )

    resp = await service.update_provider_location(
        user_id=provider_user.id,
        data=req,
    )

    assert resp.provider_id == verified_provider.id
    assert resp.latitude == 19.0750
    assert resp.longitude == 72.8770
    assert resp.speed_kmh == Decimal("35.0")

    # Verify Redis store called
    mock_redis.geoadd.assert_called_once()
    # Verify PostGIS history persisted
    service.tracking_repo.create_location_update.assert_called_once()


@pytest.mark.asyncio
async def test_get_booking_live_tracking_calculates_distance_and_eta(
    customer_user: User,
    verified_provider: Provider,
    active_booking: Booking,
    mock_redis: AsyncMock,
) -> None:
    """Test customer can fetch live tracking with computed distance and ETA."""
    session = AsyncMock()
    service = TrackingService(session, mock_redis)
    service.booking_repo.get_by_id = AsyncMock(return_value=active_booking)

    # Set mock provider location in Redis
    now = datetime.now(UTC)
    mock_point = {
        "provider_id": str(verified_provider.id),
        "latitude": 19.0700,
        "longitude": 72.8700,
        "accuracy_m": 8.0,
        "heading": 45.0,
        "speed_kmh": 30.0,
        "recorded_at": now.isoformat(),
    }
    await mock_redis.set(
        f"provider:location:point:{verified_provider.id}", json.dumps(mock_point)
    )

    tracking = await service.get_booking_live_tracking(
        booking_id=active_booking.id,
        user_id=customer_user.id,
        user_role=UserRole.CUSTOMER.value,
    )

    assert tracking.booking_id == active_booking.id
    assert tracking.status == BookingStatus.ON_THE_WAY.value
    assert tracking.provider_location is not None
    assert tracking.distance_km is not None
    assert tracking.distance_km > 0
    assert tracking.eta_minutes is not None
    assert tracking.is_stale is False


@pytest.mark.asyncio
async def test_stale_location_flagging(
    customer_user: User,
    verified_provider: Provider,
    active_booking: Booking,
    mock_redis: AsyncMock,
) -> None:
    """Test that GPS points older than 5 minutes are flagged as stale."""
    session = AsyncMock()
    service = TrackingService(session, mock_redis)
    service.booking_repo.get_by_id = AsyncMock(return_value=active_booking)

    # Mock location recorded 10 minutes ago
    stale_time = datetime.now(UTC) - timedelta(minutes=10)
    mock_point = {
        "provider_id": str(verified_provider.id),
        "latitude": 19.0700,
        "longitude": 72.8700,
        "accuracy_m": 10.0,
        "heading": 0.0,
        "speed_kmh": 0.0,
        "recorded_at": stale_time.isoformat(),
    }
    await mock_redis.set(
        f"provider:location:point:{verified_provider.id}", json.dumps(mock_point)
    )

    tracking = await service.get_booking_live_tracking(
        booking_id=active_booking.id,
        user_id=customer_user.id,
        user_role=UserRole.CUSTOMER.value,
    )

    assert tracking.is_stale is True


@pytest.mark.asyncio
async def test_tracking_idor_prevention(
    other_customer_user: User,
    active_booking: Booking,
    mock_redis: AsyncMock,
) -> None:
    """Test that unauthorized customer cannot access another customer's live tracking stream."""
    session = AsyncMock()
    service = TrackingService(session, mock_redis)
    service.booking_repo.get_by_id = AsyncMock(return_value=active_booking)

    with pytest.raises(Exception) as exc_info:
        await service.get_booking_live_tracking(
            booking_id=active_booking.id,
            user_id=other_customer_user.id,
            user_role=UserRole.CUSTOMER.value,
        )
    assert "FORBIDDEN" in str(exc_info.value) or "not authorized" in str(exc_info.value)


# ==============================================================================
# 2. ARRIVAL & ARRIVAL OTP TESTS
# ==============================================================================


@pytest.mark.asyncio
async def test_arrival_otp_generation_and_verification_flow(
    customer_user: User,
    provider_user: User,
    verified_provider: Provider,
    active_booking: Booking,
    mock_redis: AsyncMock,
) -> None:
    """Test end-to-end Arrival OTP flow: Customer generates OTP, Provider submits OTP, state moves to ARRIVED."""
    session = AsyncMock()
    service = TrackingService(session, mock_redis)
    service.booking_repo.get_by_id = AsyncMock(return_value=active_booking)
    service.provider_repo.get_by_user_id = AsyncMock(return_value=verified_provider)
    service.booking_repo.add_status_history = AsyncMock()
    service.job_repo.get_by_booking_id = AsyncMock(return_value=None)
    service.job_repo.create_job_card = AsyncMock(
        return_value=JobCard(
            id=uuid.uuid4(),
            booking_id=active_booking.id,
            provider_id=verified_provider.id,
            job_status=JobStatus.INSPECTION.value,
            started_at=datetime.now(UTC),
        )
    )
    service.job_repo.get_by_id = AsyncMock(
        return_value=JobCard(
            id=uuid.uuid4(),
            booking_id=active_booking.id,
            provider_id=verified_provider.id,
            job_status=JobStatus.INSPECTION.value,
            started_at=datetime.now(UTC),
        )
    )

    with patch("app.core.otp.redis_client", mock_redis):
        # 1. Customer generates Arrival OTP
        otp_resp = await service.generate_arrival_otp(
            booking_id=active_booking.id,
            user_id=customer_user.id,
            user_role=UserRole.CUSTOMER.value,
        )
        assert otp_resp.booking_id == active_booking.id
        assert otp_resp.expires_in_seconds > 0

        # Retrieve plain OTP stored in test key
        raw_otp = await mock_redis.get(
            f"otp_test_val:ARRIVAL:BOOKING_{active_booking.id}"
        )
        assert raw_otp is not None
        assert len(raw_otp) == 6

        # 2. Provider submits Arrival OTP with coordinates
        verify_req = ArrivalVerifyRequest(
            otp=raw_otp,
            latitude=19.0761,
            longitude=72.8778,
        )

        job_card_resp = await service.verify_arrival(
            booking_id=active_booking.id,
            user_id=provider_user.id,
            data=verify_req,
        )

        assert job_card_resp.booking_id == active_booking.id
        assert job_card_resp.job_status == JobStatus.INSPECTION
        assert active_booking.status == BookingStatus.ARRIVED.value
        assert active_booking.arrived_at is not None


@pytest.mark.asyncio
async def test_arrival_verification_wrong_otp_rejected(
    provider_user: User,
    verified_provider: Provider,
    active_booking: Booking,
    mock_redis: AsyncMock,
) -> None:
    """Test that wrong OTP is rejected with validation error."""
    session = AsyncMock()
    service = TrackingService(session, mock_redis)
    service.booking_repo.get_by_id = AsyncMock(return_value=active_booking)
    service.provider_repo.get_by_user_id = AsyncMock(return_value=verified_provider)

    with patch("app.core.otp.redis_client", mock_redis):
        # Generate valid OTP
        await service.generate_arrival_otp(
            booking_id=active_booking.id,
            user_id=active_booking.customer_id,
            user_role=UserRole.CUSTOMER.value,
        )

        # Provider submits wrong OTP
        verify_req = ArrivalVerifyRequest(
            otp="000000",
            latitude=19.0760,
            longitude=72.8777,
        )

        with pytest.raises(Exception) as exc_info:
            await service.verify_arrival(
                booking_id=active_booking.id,
                user_id=provider_user.id,
                data=verify_req,
            )
        assert (
            "ARRIVAL_OTP_INVALID" in str(exc_info.value)
            or "Invalid" in str(exc_info.value)
            or "Incorrect" in str(exc_info.value)
        )


@pytest.mark.asyncio
async def test_arrival_verification_unauthorized_provider_rejected(
    other_provider_user: User,
    other_verified_provider: Provider,
    active_booking: Booking,
    mock_redis: AsyncMock,
) -> None:
    """Test that an unassigned provider cannot verify arrival on another provider's booking."""
    session = AsyncMock()
    service = TrackingService(session, mock_redis)
    service.booking_repo.get_by_id = AsyncMock(return_value=active_booking)
    service.provider_repo.get_by_user_id = AsyncMock(
        return_value=other_verified_provider
    )

    verify_req = ArrivalVerifyRequest(otp="123456", latitude=19.0760, longitude=72.8777)

    with pytest.raises(Exception) as exc_info:
        await service.verify_arrival(
            booking_id=active_booking.id,
            user_id=other_provider_user.id,
            data=verify_req,
        )
    assert "FORBIDDEN" in str(exc_info.value) or "not authorized" in str(exc_info.value)


# ==============================================================================
# 3. JOB CARD & INSPECTION TESTS
# ==============================================================================


@pytest.mark.asyncio
async def test_job_card_retrieval(
    customer_user: User,
    active_booking: Booking,
    sample_job_card: JobCard,
) -> None:
    """Test authorized customer can retrieve active JobCard work order."""
    session = AsyncMock()
    service = JobService(session)
    service.booking_repo.get_by_id = AsyncMock(return_value=active_booking)
    service.job_repo.get_by_booking_id = AsyncMock(return_value=sample_job_card)

    resp = await service.get_job_card(
        booking_id=active_booking.id,
        user_id=customer_user.id,
        user_role=UserRole.CUSTOMER.value,
    )

    assert resp.id == sample_job_card.id
    assert resp.booking_id == active_booking.id
    assert resp.job_status == JobStatus.INSPECTION


@pytest.mark.asyncio
async def test_inspection_creation_with_evidence(
    provider_user: User,
    verified_provider: Provider,
    active_booking: Booking,
    sample_job_card: JobCard,
) -> None:
    """Test provider can submit multi-point inspection report with media URL evidence."""
    session = AsyncMock()
    service = JobService(session)
    service.booking_repo.get_by_id = AsyncMock(return_value=active_booking)
    service.provider_repo.get_by_user_id = AsyncMock(return_value=verified_provider)
    service.job_repo.get_by_booking_id = AsyncMock(return_value=sample_job_card)

    created_insp = Inspection(
        id=uuid.uuid4(),
        job_card_id=sample_job_card.id,
        odometer_km=45200,
        overall_notes="Severe nail puncture on left front sidewall.",
        created_by=provider_user.id,
        created_at=datetime.now(UTC),
    )
    items = [
        InspectionItem(
            id=uuid.uuid4(),
            inspection_id=created_insp.id,
            component="Front Left Tyre",
            condition=InspectionCondition.CRITICAL.value,
            finding="3-inch sidewall tear",
            media_url="https://storage.roadresq.com/evidence/tyre_tear.jpg",
            recommended_action="Replace with new tubeless tyre",
        ),
        InspectionItem(
            id=uuid.uuid4(),
            inspection_id=created_insp.id,
            component="Battery Voltage",
            condition=InspectionCondition.GOOD.value,
            finding="12.6V resting voltage",
            media_url=None,
            recommended_action="No action needed",
        ),
    ]
    created_insp.items = items
    service.job_repo.create_inspection = AsyncMock(return_value=created_insp)
    service.job_repo.create_inspection_items = AsyncMock(return_value=items)
    service.job_repo.get_inspection_by_id = AsyncMock(return_value=created_insp)
    service.booking_repo.add_status_history = AsyncMock()

    active_booking.status = BookingStatus.ARRIVED.value
    insp_req = InspectionCreateRequest(
        odometer_km=45200,
        overall_notes="Severe nail puncture on left front sidewall.",
        items=[
            InspectionItemCreate(
                component="Front Left Tyre",
                condition=InspectionCondition.CRITICAL,
                finding="3-inch sidewall tear",
                media_url="https://storage.roadresq.com/evidence/tyre_tear.jpg",
                recommended_action="Replace with new tubeless tyre",
            ),
            InspectionItemCreate(
                component="Battery Voltage",
                condition=InspectionCondition.GOOD,
                finding="12.6V resting voltage",
            ),
        ],
    )

    resp = await service.create_inspection(
        booking_id=active_booking.id,
        user_id=provider_user.id,
        data=insp_req,
    )

    assert resp.odometer_km == 45200
    assert len(resp.items) == 2
    assert resp.items[0].condition == InspectionCondition.CRITICAL.value


@pytest.mark.asyncio
async def test_inspection_unsafe_media_url_rejected(
    provider_user: User,
    verified_provider: Provider,
    active_booking: Booking,
    sample_job_card: JobCard,
) -> None:
    """Test that unsafe media URLs (e.g. javascript/path traversal) are rejected."""
    session = AsyncMock()
    service = JobService(session)
    active_booking.status = BookingStatus.ARRIVED.value
    service.booking_repo.get_by_id = AsyncMock(return_value=active_booking)
    service.provider_repo.get_by_user_id = AsyncMock(return_value=verified_provider)
    service.job_repo.get_by_booking_id = AsyncMock(return_value=sample_job_card)

    insp_req = InspectionCreateRequest(
        items=[
            InspectionItemCreate(
                component="Brake Pad",
                condition=InspectionCondition.POOR,
                media_url="javascript:alert(1)",
            ),
        ],
    )

    with pytest.raises(Exception) as exc_info:
        await service.create_inspection(
            booking_id=active_booking.id,
            user_id=provider_user.id,
            data=insp_req,
        )
    assert "STORAGE_INVALID_SCHEME" in str(
        exc_info.value
    ) or "Invalid URL scheme" in str(exc_info.value)


# ==============================================================================
# 4. ESTIMATE SERVICE TESTS
# ==============================================================================


@pytest.mark.asyncio
async def test_estimate_creation_server_side_financial_calculations(
    provider_user: User,
    verified_provider: Provider,
    active_booking: Booking,
    sample_job_card: JobCard,
) -> None:
    """Test server-side itemized calculations: subtotal, tax rate, discount, grand total."""
    session = AsyncMock()
    service = EstimateService(session)
    service.booking_repo.get_by_id = AsyncMock(return_value=active_booking)
    service.provider_repo.get_by_user_id = AsyncMock(return_value=verified_provider)
    service.job_repo.get_by_booking_id = AsyncMock(return_value=sample_job_card)
    service.booking_repo.add_status_history = AsyncMock()

    created_est = Estimate(
        id=uuid.uuid4(),
        job_card_id=sample_job_card.id,
        estimate_number="EST-TEST1234",
        subtotal=Decimal("2000.00"),
        tax_amount=Decimal("360.00"),
        discount_amount=Decimal("100.00"),
        total_amount=Decimal("2260.00"),
        status=EstimateStatus.PENDING_APPROVAL.value,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    created_est.items = [
        EstimateItem(
            id=uuid.uuid4(),
            estimate_id=created_est.id,
            description="New Tubeless Tyre 195/65 R15",
            quantity=Decimal("1.00"),
            unit_price=Decimal("1500.00"),
            tax_rate=Decimal("18.00"),
            line_total=Decimal("1770.00"),
        ),
        EstimateItem(
            id=uuid.uuid4(),
            estimate_id=created_est.id,
            description="Tyre Fitting & Balancing Labor",
            quantity=Decimal("1.00"),
            unit_price=Decimal("500.00"),
            tax_rate=Decimal("18.00"),
            line_total=Decimal("590.00"),
        ),
    ]
    service.estimate_repo.create_estimate = AsyncMock(return_value=created_est)
    service.estimate_repo.create_estimate_items = AsyncMock(
        return_value=created_est.items
    )
    service.estimate_repo.get_by_id = AsyncMock(return_value=created_est)

    req = EstimateCreateRequest(
        items=[
            EstimateItemCreate(
                description="New Tubeless Tyre 195/65 R15",
                quantity=Decimal("1.00"),
                unit_price=Decimal("1500.00"),
                tax_rate=Decimal("18.00"),
            ),
            EstimateItemCreate(
                description="Tyre Fitting & Balancing Labor",
                quantity=Decimal("1.00"),
                unit_price=Decimal("500.00"),
                tax_rate=Decimal("18.00"),
            ),
        ],
        discount_amount=Decimal("100.00"),
    )

    resp = await service.create_estimate(
        booking_id=active_booking.id,
        user_id=provider_user.id,
        data=req,
    )

    assert resp.subtotal == Decimal("2000.00")
    assert resp.tax_amount == Decimal("360.00")
    assert resp.discount_amount == Decimal("100.00")
    assert resp.total_amount == Decimal("2260.00")
    assert resp.status == EstimateStatus.PENDING_APPROVAL


@pytest.mark.asyncio
async def test_estimate_customer_approval_advances_state(
    customer_user: User,
    active_booking: Booking,
    sample_job_card: JobCard,
) -> None:
    """Test customer approving estimate sets state to APPROVED and advances booking/job to IN_PROGRESS."""
    session = AsyncMock()
    service = EstimateService(session)

    sample_est = Estimate(
        id=uuid.uuid4(),
        job_card_id=sample_job_card.id,
        estimate_number="EST-APPROVE01",
        subtotal=Decimal("1000.00"),
        tax_amount=Decimal("180.00"),
        discount_amount=Decimal("0.00"),
        total_amount=Decimal("1180.00"),
        status=EstimateStatus.PENDING_APPROVAL.value,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    sample_est.items = []

    service.estimate_repo.get_by_id = AsyncMock(return_value=sample_est)
    service.job_repo.get_by_id = AsyncMock(return_value=sample_job_card)
    service.booking_repo.get_by_id = AsyncMock(return_value=active_booking)
    service.estimate_repo.approve_estimate = AsyncMock()
    service.booking_repo.add_status_history = AsyncMock()

    _ = await service.approve_estimate(
        estimate_id=sample_est.id,
        user_id=customer_user.id,
        user_role=UserRole.CUSTOMER.value,
    )

    assert sample_job_card.job_status == JobStatus.IN_PROGRESS.value
    assert active_booking.status == BookingStatus.IN_PROGRESS.value


@pytest.mark.asyncio
async def test_estimate_rejection_and_revision_flow(
    customer_user: User,
    provider_user: User,
    verified_provider: Provider,
    active_booking: Booking,
    sample_job_card: JobCard,
) -> None:
    """Test estimate rejection by customer and subsequent revision by provider."""
    session = AsyncMock()
    service = EstimateService(session)

    orig_est = Estimate(
        id=uuid.uuid4(),
        job_card_id=sample_job_card.id,
        estimate_number="EST-ORIG01",
        subtotal=Decimal("3000.00"),
        tax_amount=Decimal("540.00"),
        discount_amount=Decimal("0.00"),
        total_amount=Decimal("3540.00"),
        status=EstimateStatus.PENDING_APPROVAL.value,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    orig_est.items = []

    service.estimate_repo.get_by_id = AsyncMock(return_value=orig_est)
    service.job_repo.get_by_id = AsyncMock(return_value=sample_job_card)
    service.booking_repo.get_by_id = AsyncMock(return_value=active_booking)
    service.provider_repo.get_by_user_id = AsyncMock(return_value=verified_provider)

    async def mock_reject(
        estimate: Estimate, user_id: uuid.UUID, rejection_reason: str
    ) -> Estimate:
        estimate.status = EstimateStatus.REJECTED.value
        estimate.rejected_by = user_id
        estimate.rejection_reason = rejection_reason
        return estimate

    service.estimate_repo.reject_estimate = AsyncMock(side_effect=mock_reject)
    service.estimate_repo.mark_revised = AsyncMock()
    service.booking_repo.add_status_history = AsyncMock()

    # 1. Customer rejects estimate
    _ = await service.reject_estimate(
        estimate_id=orig_est.id,
        user_id=customer_user.id,
        user_role=UserRole.CUSTOMER.value,
        data=EstimateRejectRequest(
            rejection_reason="Quoted price is too high for basic repair"
        ),
    )
    assert orig_est.status == EstimateStatus.REJECTED.value

    # 2. Provider submits revised estimate
    revised_est = Estimate(
        id=uuid.uuid4(),
        job_card_id=sample_job_card.id,
        estimate_number="EST-REV-01",
        subtotal=Decimal("2000.00"),
        tax_amount=Decimal("360.00"),
        discount_amount=Decimal("200.00"),
        total_amount=Decimal("2160.00"),
        status=EstimateStatus.PENDING_APPROVAL.value,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    revised_est.items = []
    service.estimate_repo.create_estimate = AsyncMock(return_value=revised_est)
    service.estimate_repo.create_estimate_items = AsyncMock(return_value=[])
    service.estimate_repo.get_by_id = AsyncMock(return_value=revised_est)

    revise_req = EstimateReviseRequest(
        items=[
            EstimateItemCreate(
                description="Alternative Standard Tyre",
                quantity=Decimal("1.00"),
                unit_price=Decimal("2000.00"),
                tax_rate=Decimal("18.00"),
            ),
        ],
        discount_amount=Decimal("200.00"),
        revision_notes="Applied promotional discount",
    )

    rev_resp = await service.revise_estimate(
        estimate_id=orig_est.id,
        user_id=provider_user.id,
        data=revise_req,
    )

    assert rev_resp.status == EstimateStatus.PENDING_APPROVAL
    assert rev_resp.total_amount == Decimal("2160.00")


# ==============================================================================
# 5. SERVICE COMPLETION TESTS
# ==============================================================================


@pytest.mark.asyncio
async def test_job_completion_with_notes_and_evidence(
    provider_user: User,
    verified_provider: Provider,
    active_booking: Booking,
    sample_job_card: JobCard,
) -> None:
    """Test provider completing job with notes and photographic completion evidence."""
    session = AsyncMock()
    service = JobService(session)

    sample_job_card.job_status = JobStatus.IN_PROGRESS.value
    active_booking.status = BookingStatus.IN_PROGRESS.value

    service.booking_repo.get_by_id = AsyncMock(return_value=active_booking)
    service.provider_repo.get_by_user_id = AsyncMock(return_value=verified_provider)
    service.job_repo.get_by_booking_id = AsyncMock(return_value=sample_job_card)

    async def mock_complete(
        job_card: JobCard,
        completion_notes: str,
        completion_evidence_url: str | None = None,
    ) -> JobCard:
        job_card.job_status = JobStatus.COMPLETED.value
        job_card.completed_at = datetime.now(UTC)
        job_card.completion_notes = completion_notes
        job_card.completion_evidence_url = completion_evidence_url
        return job_card

    service.job_repo.complete_job = AsyncMock(side_effect=mock_complete)
    service.job_repo.get_by_id = AsyncMock(return_value=sample_job_card)
    service.booking_repo.add_status_history = AsyncMock()

    complete_req = JobCardCompleteRequest(
        completion_notes="New tyre fitted and wheel nuts torqued to spec. Tyre pressure calibrated to 33 PSI.",
        completion_evidence_url="https://storage.roadresq.com/evidence/completed_wheel.jpg",
    )

    _ = await service.complete_job(
        booking_id=active_booking.id,
        user_id=provider_user.id,
        data=complete_req,
    )

    assert active_booking.status == BookingStatus.COMPLETED.value
    assert active_booking.completed_at is not None
    assert sample_job_card.job_status == JobStatus.COMPLETED.value


# ==============================================================================
# 6. WEBSOCKET REAL-TIME BROADCAST TESTS
# ==============================================================================


@pytest.mark.asyncio
async def test_websocket_channel_connect_and_broadcast() -> None:
    """Test WebSocketManager connection registration, broadcast, and disconnect."""
    test_booking_id = str(uuid.uuid4())
    mock_ws = AsyncMock()

    await ws_manager.connect(test_booking_id, mock_ws)
    assert test_booking_id in ws_manager._active_connections
    assert mock_ws in ws_manager._active_connections[test_booking_id]

    # Broadcast event
    await ws_manager.broadcast_to_booking(
        booking_id=test_booking_id,
        event="booking.status.updated",
        data={"status": "ARRIVED"},
    )
    mock_ws.send_text.assert_called_once()
    sent_payload = json.loads(mock_ws.send_text.call_args[0][0])
    assert sent_payload["event"] == "booking.status.updated"
    assert sent_payload["data"]["status"] == "ARRIVED"

    # Disconnect
    await ws_manager.disconnect(test_booking_id, mock_ws)
    assert test_booking_id not in ws_manager._active_connections


# ==============================================================================
# 7. FASTAPI API ROUTE INTEGRATION TESTS
# ==============================================================================


@pytest.mark.asyncio
async def test_api_routes_auth_and_schema_validation(
    customer_user: User,
    provider_user: User,
    active_booking: Booking,
    mock_redis: AsyncMock,
) -> None:
    """Integration test validating FastAPI routes with Bearer authentication and Pydantic schemas."""
    customer_token = create_access_token(
        user_id=customer_user.id, role=UserRole.CUSTOMER.value
    )
    provider_token = create_access_token(
        user_id=provider_user.id, role=UserRole.PROVIDER.value
    )

    app.dependency_overrides[get_redis] = lambda: mock_redis

    async def mock_user_lookup(self: Any, uid: uuid.UUID) -> User | None:
        if uid == customer_user.id:
            return customer_user
        if uid == provider_user.id:
            return provider_user
        return None

    with patch("app.api.deps.UserRepository.get_by_id", new=mock_user_lookup):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Anonymous access rejected (401)
            resp_anon = await client.get(
                f"/api/v1/bookings/{active_booking.id}/location"
            )
            assert resp_anon.status_code == 401

            # 2. Verify arrival OTP schema endpoint rejects invalid payload (422)
            resp_invalid_otp = await client.post(
                f"/api/v1/providers/me/bookings/{active_booking.id}/arrive",
                headers={"Authorization": f"Bearer {provider_token}"},
                json={"otp": "123"},  # Invalid: less than 6 digits
            )
            assert resp_invalid_otp.status_code == 422

            # 3. Verify estimate creation requires provider role (403 for customer token)
            resp_forbidden = await client.post(
                f"/api/v1/bookings/{active_booking.id}/estimates",
                headers={"Authorization": f"Bearer {customer_token}"},
                json={
                    "items": [
                        {
                            "description": "Battery",
                            "quantity": 1,
                            "unit_price": 2000,
                            "tax_rate": 18,
                        }
                    ]
                },
            )
            assert resp_forbidden.status_code == 403

    app.dependency_overrides.clear()
