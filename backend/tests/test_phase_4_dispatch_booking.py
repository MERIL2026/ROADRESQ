"""Phase 4: Core Dispatch & Booking — Unit Tests."""

import json
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_redis
from app.core.geospatial import haversine_distance_km
from app.core.security import create_access_token
from app.main import app
from app.models.booking import Booking
from app.models.enums import (
    BookingStatus,
    BookingType,
    ProviderVerificationStatus,
    UserRole,
    UserStatus,
    VehicleFuelType,
)
from app.models.provider import Provider
from app.models.service import PlatformService
from app.models.user import User
from app.models.vehicle import Vehicle
from app.schemas.booking import BookingListResponse, BookingResponse
from app.services.booking_service import BookingService

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
        provider_type="INDIVIDUAL",
        verification_status=ProviderVerificationStatus.VERIFIED.value,
        is_online=True,
        phone="+919876540002",
        rating_avg=Decimal("4.5"),
        rating_count=20,
        service_radius_km=Decimal("15.0"),
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
        year=2022,
        color="White",
        is_primary=True,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


@pytest.fixture
def platform_service() -> PlatformService:
    return PlatformService(
        id=uuid.uuid4(),
        name="Tyre Repair",
        category="TYRE",
        description="Fix punctured tyres on-site",
        base_price=Decimal("500.00"),
        is_emergency=True,
        is_active=True,
    )


@pytest.fixture
def sample_booking(customer_user: User, customer_vehicle: Vehicle, platform_service: PlatformService) -> Booking:
    b = Booking(
        id=uuid.uuid4(),
        booking_number="BK-20260905-ABCD01",
        customer_id=customer_user.id,
        vehicle_id=customer_vehicle.id,
        service_id=platform_service.id,
        booking_type=BookingType.EMERGENCY.value,
        status=BookingStatus.REQUESTED.value,
        problem_description="Flat tyre on highway",
        requested_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    b.customer = customer_user
    b.vehicle = customer_vehicle
    b.service = platform_service
    b.provider = None
    b.locations = []
    b.status_history = []
    return b


# ==============================================================================
# Tests: Customer Vehicle Registration (Step 4.2)
# ==============================================================================


@pytest.mark.asyncio
async def test_register_vehicle_success(customer_user: User) -> None:
    """Customer can register a new vehicle successfully."""
    token = create_access_token(user_id=customer_user.id, role=UserRole.CUSTOMER.value)
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "registration_number": "MH01AB9999",
        "make": "Honda",
        "model": "City",
        "fuel_type": "PETROL",
        "year": 2023,
        "color": "Silver",
        "is_primary": False,
    }

    new_vehicle = Vehicle(
        id=uuid.uuid4(),
        user_id=customer_user.id,
        registration_number="MH01AB9999",
        make="Honda",
        model="City",
        fuel_type="PETROL",
        year=2023,
        color="Silver",
        is_primary=False,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    with (
        patch("app.api.deps.UserRepository.get_by_id", new_callable=AsyncMock) as mock_user,
        patch("app.services.vehicle_service.VehicleRepository.get_by_registration_number", new_callable=AsyncMock) as mock_check,
        patch("app.services.vehicle_service.VehicleRepository.create", new_callable=AsyncMock) as mock_create,
        patch("app.services.vehicle_service.record_audit_event", new_callable=AsyncMock),
    ):
        mock_user.return_value = customer_user
        mock_check.return_value = None
        mock_create.return_value = new_vehicle

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/v1/vehicles/me", json=payload, headers=headers)

    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["registration_number"] == "MH01AB9999"
    assert data["make"] == "Honda"


@pytest.mark.asyncio
async def test_provider_cannot_register_vehicle(provider_user: User) -> None:
    """Provider role cannot access customer vehicle registration."""
    token = create_access_token(user_id=provider_user.id, role=UserRole.PROVIDER.value)
    headers = {"Authorization": f"Bearer {token}"}

    with (
        patch("app.api.deps.UserRepository.get_by_id", new_callable=AsyncMock) as mock_user,
    ):
        mock_user.return_value = provider_user

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/v1/vehicles/me", json={"registration_number": "MH01XX0001"}, headers=headers)

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_list_my_vehicles_returns_list(customer_user: User, customer_vehicle: Vehicle) -> None:
    """Customer can list their registered vehicles."""
    token = create_access_token(user_id=customer_user.id, role=UserRole.CUSTOMER.value)
    headers = {"Authorization": f"Bearer {token}"}

    with (
        patch("app.api.deps.UserRepository.get_by_id", new_callable=AsyncMock) as mock_user,
        patch("app.services.vehicle_service.VehicleRepository.list_by_user", new_callable=AsyncMock) as mock_list,
    ):
        mock_user.return_value = customer_user
        mock_list.return_value = [customer_vehicle]

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/v1/vehicles/me", headers=headers)

    assert resp.status_code == 200
    result = resp.json()["data"]
    assert result["total"] == 1
    assert result["vehicles"][0]["registration_number"] == customer_vehicle.registration_number


# ==============================================================================
# Tests: Booking Creation & Lifecycle (Step 4.3)
# ==============================================================================


@pytest.mark.asyncio
async def test_create_booking_success(
    customer_user: User,
    customer_vehicle: Vehicle,
    platform_service: PlatformService,
    sample_booking: Booking,
) -> None:
    """Customer successfully creates a booking which triggers dispatch."""
    token = create_access_token(user_id=customer_user.id, role=UserRole.CUSTOMER.value)
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "vehicle_id": str(customer_vehicle.id),
        "service_id": str(platform_service.id),
        "booking_type": "EMERGENCY",
        "problem_description": "Flat tyre on NH48",
        "pickup_location": {
            "latitude": 19.076,
            "longitude": 72.877,
            "address_text": "NH48, Pune",
        },
    }

    mock_redis = AsyncMock()
    mock_redis.get.return_value = None
    mock_redis.set.return_value = True
    mock_redis.smembers.return_value = set()
    app.dependency_overrides[get_redis] = lambda: mock_redis

    try:
        with (
            patch("app.api.deps.UserRepository.get_by_id", new_callable=AsyncMock) as mock_user,
            patch("app.services.booking_service.UserRepository.get_by_id", new_callable=AsyncMock) as mock_svc_user,
            patch("app.services.booking_service.VehicleRepository.get_by_id_and_user", new_callable=AsyncMock) as mock_veh,
            patch("app.services.booking_service.ServiceRepository.get_by_id", new_callable=AsyncMock) as mock_svc,
            patch("app.repositories.booking.BookingRepository.create_booking", new_callable=AsyncMock) as mock_create,
            patch("app.repositories.booking.BookingRepository.get_by_id", new_callable=AsyncMock) as mock_get,
            patch("app.services.booking_service.record_audit_event", new_callable=AsyncMock),
            patch("app.services.dispatch_service.DispatchService.initiate_dispatch", new_callable=AsyncMock) as mock_dispatch,
        ):
            mock_user.return_value = customer_user
            mock_svc_user.return_value = customer_user
            mock_veh.return_value = customer_vehicle
            mock_svc.return_value = platform_service
            mock_create.return_value = sample_booking
            mock_get.return_value = sample_booking
            mock_dispatch.return_value = sample_booking

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post("/api/v1/bookings", json=payload, headers=headers)
    finally:
        app.dependency_overrides.pop(get_redis, None)

    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["booking_number"] == "BK-20260905-ABCD01"
    assert data["status"] == BookingStatus.REQUESTED.value


@pytest.mark.asyncio
async def test_create_booking_requires_customer_role(provider_user: User) -> None:
    """Only CUSTOMER role may create bookings."""
    token = create_access_token(user_id=provider_user.id, role=UserRole.PROVIDER.value)
    headers = {"Authorization": f"Bearer {token}"}

    with (
        patch("app.api.deps.UserRepository.get_by_id", new_callable=AsyncMock) as mock_user,
    ):
        mock_user.return_value = provider_user

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/bookings",
                json={
                    "vehicle_id": str(uuid.uuid4()),
                    "service_id": str(uuid.uuid4()),
                    "pickup_location": {"latitude": 19.0, "longitude": 72.0},
                },
                headers=headers,
            )

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_list_my_bookings(customer_user: User, sample_booking: Booking) -> None:
    """Customer can list their bookings."""
    token = create_access_token(user_id=customer_user.id, role=UserRole.CUSTOMER.value)
    headers = {"Authorization": f"Bearer {token}"}

    mock_redis = AsyncMock()
    app.dependency_overrides[get_redis] = lambda: mock_redis

    try:
        with (
            patch("app.api.deps.UserRepository.get_by_id", new_callable=AsyncMock) as mock_user,
            patch("app.repositories.booking.BookingRepository.list_by_customer", new_callable=AsyncMock) as mock_list,
            patch("app.repositories.booking.BookingRepository.count_by_customer", new_callable=AsyncMock) as mock_count,
        ):
            mock_user.return_value = customer_user
            mock_list.return_value = [sample_booking]
            mock_count.return_value = 1

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.get("/api/v1/bookings/me", headers=headers)
    finally:
        app.dependency_overrides.pop(get_redis, None)

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] == 1
    assert data["bookings"][0]["booking_number"] == sample_booking.booking_number


@pytest.mark.asyncio
async def test_cancel_booking_success(customer_user: User, sample_booking: Booking) -> None:
    """Customer can cancel a REQUESTED booking."""
    token = create_access_token(user_id=customer_user.id, role=UserRole.CUSTOMER.value)
    headers = {"Authorization": f"Bearer {token}"}

    cancelled_booking = sample_booking
    cancelled_booking.status = BookingStatus.CANCELLED.value
    cancelled_booking.cancellation_reason = "Changed my mind"

    mock_redis = AsyncMock()
    mock_redis.delete.return_value = True
    app.dependency_overrides[get_redis] = lambda: mock_redis

    try:
        with (
            patch("app.api.deps.UserRepository.get_by_id", new_callable=AsyncMock) as mock_user,
            patch("app.repositories.booking.BookingRepository.get_by_id", new_callable=AsyncMock) as mock_get,
            patch("app.repositories.booking.BookingRepository.add_status_history", new_callable=AsyncMock),
            patch("app.services.booking_service.record_audit_event", new_callable=AsyncMock),
        ):
            mock_user.return_value = customer_user
            mock_get.return_value = sample_booking

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post(
                    f"/api/v1/bookings/{sample_booking.id}/cancel",
                    json={"cancellation_reason": "Changed my mind"},
                    headers=headers,
                )
    finally:
        app.dependency_overrides.pop(get_redis, None)

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["status"] == BookingStatus.CANCELLED.value


@pytest.mark.asyncio
async def test_cancel_completed_booking_rejected(customer_user: User, sample_booking: Booking) -> None:
    """Cannot cancel a COMPLETED booking — state machine rejects it."""
    token = create_access_token(user_id=customer_user.id, role=UserRole.CUSTOMER.value)
    headers = {"Authorization": f"Bearer {token}"}

    sample_booking.status = BookingStatus.COMPLETED.value

    mock_redis = AsyncMock()
    app.dependency_overrides[get_redis] = lambda: mock_redis

    try:
        with (
            patch("app.api.deps.UserRepository.get_by_id", new_callable=AsyncMock) as mock_user,
            patch("app.repositories.booking.BookingRepository.get_by_id", new_callable=AsyncMock) as mock_get,
        ):
            mock_user.return_value = customer_user
            mock_get.return_value = sample_booking

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post(
                    f"/api/v1/bookings/{sample_booking.id}/cancel",
                    json={"cancellation_reason": "Trying to cancel completed booking"},
                    headers=headers,
                )
    finally:
        app.dependency_overrides.pop(get_redis, None)

    assert resp.status_code == 422


# ==============================================================================
# Tests: IDOR — Booking Access Control
# ==============================================================================


@pytest.mark.asyncio
async def test_customer_cannot_access_other_customers_booking(
    customer_user: User, sample_booking: Booking
) -> None:
    """Customer cannot view a booking belonging to a different customer (IDOR guard)."""
    other_customer_id = uuid.uuid4()
    sample_booking.customer_id = other_customer_id  # booking belongs to someone else

    token = create_access_token(user_id=customer_user.id, role=UserRole.CUSTOMER.value)
    headers = {"Authorization": f"Bearer {token}"}

    mock_redis = AsyncMock()
    app.dependency_overrides[get_redis] = lambda: mock_redis

    try:
        with (
            patch("app.api.deps.UserRepository.get_by_id", new_callable=AsyncMock) as mock_user,
            patch("app.repositories.booking.BookingRepository.get_by_id_with_relations", new_callable=AsyncMock) as mock_get,
        ):
            mock_user.return_value = customer_user
            mock_get.return_value = sample_booking

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.get(
                    f"/api/v1/bookings/{sample_booking.id}", headers=headers
                )
    finally:
        app.dependency_overrides.pop(get_redis, None)

    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "FORBIDDEN"


# ==============================================================================
# Tests: Provider Location Ping (Step 4.8)
# ==============================================================================


@pytest.mark.asyncio
async def test_provider_location_update_success(
    provider_user: User, verified_provider: Provider
) -> None:
    """Provider can push GPS coordinates to Redis geospatial index."""
    token = create_access_token(user_id=provider_user.id, role=UserRole.PROVIDER.value)
    headers = {"Authorization": f"Bearer {token}"}

    mock_redis = AsyncMock()
    mock_redis.geoadd = AsyncMock(return_value=True)
    mock_redis.set = AsyncMock(return_value=True)
    app.dependency_overrides[get_redis] = lambda: mock_redis

    try:
        with (
            patch("app.api.deps.UserRepository.get_by_id", new_callable=AsyncMock) as mock_user,
            patch("app.services.dispatch_service.ProviderRepository.get_by_user_id", new_callable=AsyncMock) as mock_prov_by_user,
            patch("app.services.dispatch_service.ProviderRepository.get_by_id", new_callable=AsyncMock) as mock_prov_get,
        ):
            mock_user.return_value = provider_user
            mock_prov_by_user.return_value = verified_provider
            mock_prov_get.return_value = verified_provider

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.put(
                    "/api/v1/providers/me/location",
                    json={"latitude": 19.076, "longitude": 72.877},
                    headers=headers,
                )
    finally:
        app.dependency_overrides.pop(get_redis, None)

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["latitude"] == 19.076
    assert data["longitude"] == 72.877
    assert data["provider_id"] == str(verified_provider.id)


@pytest.mark.asyncio
async def test_provider_location_invalid_coordinates(provider_user: User) -> None:
    """GPS coordinates out of valid range are rejected."""
    token = create_access_token(user_id=provider_user.id, role=UserRole.PROVIDER.value)
    headers = {"Authorization": f"Bearer {token}"}

    with (
        patch("app.api.deps.UserRepository.get_by_id", new_callable=AsyncMock) as mock_user,
    ):
        mock_user.return_value = provider_user

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.put(
                "/api/v1/providers/me/location",
                json={"latitude": 999.0, "longitude": 72.877},  # invalid latitude
                headers=headers,
            )

    assert resp.status_code == 422


# ==============================================================================
# Tests: Dispatch Accept / Reject (Step 4.8)
# ==============================================================================


@pytest.mark.asyncio
async def test_provider_accept_dispatch_offer_success(
    provider_user: User, verified_provider: Provider, sample_booking: Booking
) -> None:
    """Provider successfully accepts a dispatch offer atomically."""
    token = create_access_token(user_id=provider_user.id, role=UserRole.PROVIDER.value)
    headers = {"Authorization": f"Bearer {token}"}

    offer_payload = {
        "booking_id": str(sample_booking.id),
        "provider_id": str(verified_provider.id),
        "distance_km": 3.5,
        "created_at": datetime.now(UTC).isoformat(),
        "expires_at": (datetime.now(UTC) + timedelta(seconds=30)).isoformat(),
    }

    mock_redis = AsyncMock()
    mock_redis.get.return_value = json.dumps(offer_payload)
    mock_redis.delete = AsyncMock(return_value=True)
    app.dependency_overrides[get_redis] = lambda: mock_redis

    try:
        with (
            patch("app.api.deps.UserRepository.get_by_id", new_callable=AsyncMock) as mock_user,
            patch("app.services.dispatch_service.ProviderRepository.get_by_user_id", new_callable=AsyncMock) as mock_prov,
            patch("app.repositories.booking.BookingRepository.assign_provider_atomic", new_callable=AsyncMock) as mock_atomic,
            patch("app.repositories.booking.BookingRepository.add_status_history", new_callable=AsyncMock),
            patch("app.repositories.booking.BookingRepository.get_by_id", new_callable=AsyncMock) as mock_get,
            patch("app.services.dispatch_service.record_audit_event", new_callable=AsyncMock),
        ):
            mock_user.return_value = provider_user
            mock_prov.return_value = verified_provider
            mock_atomic.return_value = True  # Assignment succeeded
            mock_get.return_value = sample_booking

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post(
                    f"/api/v1/providers/me/dispatch/{sample_booking.id}/accept",
                    json={},
                    headers=headers,
                )
    finally:
        app.dependency_overrides.pop(get_redis, None)

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["status"] == BookingStatus.ACCEPTED.value
    assert "successfully accepted" in data["message"]


@pytest.mark.asyncio
async def test_provider_accept_expired_offer_returns_409(
    provider_user: User, verified_provider: Provider, sample_booking: Booking
) -> None:
    """Accepting an expired dispatch offer returns 409 Conflict."""
    token = create_access_token(user_id=provider_user.id, role=UserRole.PROVIDER.value)
    headers = {"Authorization": f"Bearer {token}"}

    mock_redis = AsyncMock()
    mock_redis.get.return_value = None  # Offer expired / not in Redis
    app.dependency_overrides[get_redis] = lambda: mock_redis

    try:
        with (
            patch("app.api.deps.UserRepository.get_by_id", new_callable=AsyncMock) as mock_user,
            patch("app.services.dispatch_service.ProviderRepository.get_by_user_id", new_callable=AsyncMock) as mock_prov,
        ):
            mock_user.return_value = provider_user
            mock_prov.return_value = verified_provider

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post(
                    f"/api/v1/providers/me/dispatch/{sample_booking.id}/accept",
                    json={},
                    headers=headers,
                )
    finally:
        app.dependency_overrides.pop(get_redis, None)

    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "DISPATCH_OFFER_EXPIRED"


@pytest.mark.asyncio
async def test_atomic_assignment_prevents_double_accept(
    provider_user: User, verified_provider: Provider, sample_booking: Booking
) -> None:
    """When two providers race to accept, PostgreSQL atomic update ensures only one wins."""
    token = create_access_token(user_id=provider_user.id, role=UserRole.PROVIDER.value)
    headers = {"Authorization": f"Bearer {token}"}

    offer_payload = {
        "booking_id": str(sample_booking.id),
        "provider_id": str(verified_provider.id),
        "distance_km": 3.5,
        "created_at": datetime.now(UTC).isoformat(),
        "expires_at": (datetime.now(UTC) + timedelta(seconds=30)).isoformat(),
    }

    mock_redis = AsyncMock()
    mock_redis.get.return_value = json.dumps(offer_payload)
    mock_redis.delete = AsyncMock(return_value=True)
    app.dependency_overrides[get_redis] = lambda: mock_redis

    try:
        with (
            patch("app.api.deps.UserRepository.get_by_id", new_callable=AsyncMock) as mock_user,
            patch("app.services.dispatch_service.ProviderRepository.get_by_user_id", new_callable=AsyncMock) as mock_prov,
            patch("app.repositories.booking.BookingRepository.assign_provider_atomic", new_callable=AsyncMock) as mock_atomic,
        ):
            mock_user.return_value = provider_user
            mock_prov.return_value = verified_provider
            mock_atomic.return_value = False  # Another provider already won

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post(
                    f"/api/v1/providers/me/dispatch/{sample_booking.id}/accept",
                    json={},
                    headers=headers,
                )
    finally:
        app.dependency_overrides.pop(get_redis, None)

    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "BOOKING_ALREADY_ASSIGNED"


@pytest.mark.asyncio
async def test_provider_reject_dispatch_offer(
    provider_user: User, verified_provider: Provider, sample_booking: Booking
) -> None:
    """Provider rejects a dispatch offer which triggers re-dispatch."""
    token = create_access_token(user_id=provider_user.id, role=UserRole.PROVIDER.value)
    headers = {"Authorization": f"Bearer {token}"}

    mock_redis = AsyncMock()
    mock_redis.sadd = AsyncMock(return_value=True)
    mock_redis.expire = AsyncMock(return_value=True)
    mock_redis.delete = AsyncMock(return_value=True)
    mock_redis.smembers = AsyncMock(return_value=set())
    mock_redis.get = AsyncMock(return_value=None)
    app.dependency_overrides[get_redis] = lambda: mock_redis

    try:
        with (
            patch("app.api.deps.UserRepository.get_by_id", new_callable=AsyncMock) as mock_user,
            patch("app.services.dispatch_service.ProviderRepository.get_by_user_id", new_callable=AsyncMock) as mock_prov,
            patch("app.repositories.booking.BookingRepository.add_status_history", new_callable=AsyncMock),
            patch("app.services.dispatch_service.record_audit_event", new_callable=AsyncMock),
            patch("app.services.dispatch_service.DispatchService.initiate_dispatch", new_callable=AsyncMock),
        ):
            mock_user.return_value = provider_user
            mock_prov.return_value = verified_provider

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post(
                    f"/api/v1/providers/me/dispatch/{sample_booking.id}/reject",
                    json={"reason": "Too far away"},
                    headers=headers,
                )
    finally:
        app.dependency_overrides.pop(get_redis, None)

    assert resp.status_code == 200
    assert "rejected" in resp.json()["data"]["message"].lower()


# ==============================================================================
# Tests: Provider Booking Status Progression (Step 4.9)
# ==============================================================================


@pytest.mark.asyncio
async def test_provider_updates_booking_status_to_on_the_way(
    provider_user: User, verified_provider: Provider, sample_booking: Booking
) -> None:
    """Provider progresses booking from ACCEPTED → ON_THE_WAY."""
    sample_booking.status = BookingStatus.ACCEPTED.value
    sample_booking.provider_id = verified_provider.id

    token = create_access_token(user_id=provider_user.id, role=UserRole.PROVIDER.value)
    headers = {"Authorization": f"Bearer {token}"}

    mock_redis = AsyncMock()
    app.dependency_overrides[get_redis] = lambda: mock_redis

    try:
        with (
            patch("app.api.deps.UserRepository.get_by_id", new_callable=AsyncMock) as mock_user,
            patch("app.repositories.booking.BookingRepository.get_by_id", new_callable=AsyncMock) as mock_get,
            patch("app.services.booking_service.ProviderRepository.get_by_user_id", new_callable=AsyncMock) as mock_prov,
            patch("app.repositories.booking.BookingRepository.add_status_history", new_callable=AsyncMock),
            patch("app.services.booking_service.record_audit_event", new_callable=AsyncMock),
        ):
            mock_user.return_value = provider_user
            mock_get.return_value = sample_booking
            mock_prov.return_value = verified_provider

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.patch(
                    f"/api/v1/providers/me/bookings/{sample_booking.id}/status",
                    json={"status": "ON_THE_WAY"},
                    headers=headers,
                )
    finally:
        app.dependency_overrides.pop(get_redis, None)

    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == BookingStatus.ON_THE_WAY.value


@pytest.mark.asyncio
async def test_invalid_booking_status_transition_rejected(
    provider_user: User, verified_provider: Provider, sample_booking: Booking
) -> None:
    """Skipping status transitions is blocked by the state machine."""
    sample_booking.status = BookingStatus.REQUESTED.value
    sample_booking.provider_id = verified_provider.id

    token = create_access_token(user_id=provider_user.id, role=UserRole.PROVIDER.value)
    headers = {"Authorization": f"Bearer {token}"}

    mock_redis = AsyncMock()
    app.dependency_overrides[get_redis] = lambda: mock_redis

    try:
        with (
            patch("app.api.deps.UserRepository.get_by_id", new_callable=AsyncMock) as mock_user,
            patch("app.repositories.booking.BookingRepository.get_by_id", new_callable=AsyncMock) as mock_get,
            patch("app.services.booking_service.ProviderRepository.get_by_user_id", new_callable=AsyncMock) as mock_prov,
        ):
            mock_user.return_value = provider_user
            mock_get.return_value = sample_booking
            mock_prov.return_value = verified_provider

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.patch(
                    f"/api/v1/providers/me/bookings/{sample_booking.id}/status",
                    json={"status": "COMPLETED"},  # Illegal jump: REQUESTED → COMPLETED
                    headers=headers,
                )
    finally:
        app.dependency_overrides.pop(get_redis, None)

    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "INVALID_STATUS_TRANSITION"


# ==============================================================================
# Tests: Admin Bookings API (Step 4.10)
# ==============================================================================


@pytest.mark.asyncio
async def test_admin_list_bookings(admin_user: User, sample_booking: Booking) -> None:
    """Admin can list all platform bookings."""
    token = create_access_token(user_id=admin_user.id, role=UserRole.ADMIN.value)
    headers = {"Authorization": f"Bearer {token}"}

    mock_redis = AsyncMock()
    app.dependency_overrides[get_redis] = lambda: mock_redis

    try:
        with (
            patch("app.api.deps.UserRepository.get_by_id", new_callable=AsyncMock) as mock_user,
            patch("app.services.booking_service.BookingService.list_all_bookings", new_callable=AsyncMock) as mock_list,
        ):
            mock_user.return_value = admin_user
            mock_list.return_value = BookingListResponse(
                bookings=[BookingResponse.model_validate(sample_booking)],
                total=1,
                page=1,
                page_size=20,
            )

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.get("/api/v1/admin/bookings", headers=headers)
    finally:
        app.dependency_overrides.pop(get_redis, None)

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] == 1


@pytest.mark.asyncio
async def test_customer_cannot_access_admin_bookings(customer_user: User) -> None:
    """Customer cannot access admin booking endpoint (403 Forbidden)."""
    token = create_access_token(user_id=customer_user.id, role=UserRole.CUSTOMER.value)
    headers = {"Authorization": f"Bearer {token}"}

    with (
        patch("app.api.deps.UserRepository.get_by_id", new_callable=AsyncMock) as mock_user,
    ):
        mock_user.return_value = customer_user

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/v1/admin/bookings", headers=headers)

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_provider_cannot_access_admin_bookings(provider_user: User) -> None:
    """Provider cannot access admin booking endpoint (403 Forbidden)."""
    token = create_access_token(user_id=provider_user.id, role=UserRole.PROVIDER.value)
    headers = {"Authorization": f"Bearer {token}"}

    with (
        patch("app.api.deps.UserRepository.get_by_id", new_callable=AsyncMock) as mock_user,
    ):
        mock_user.return_value = provider_user

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/v1/admin/bookings", headers=headers)

    assert resp.status_code == 403


# ==============================================================================
# Tests: Booking State Machine — Service Layer (Unit)
# ==============================================================================


def test_booking_state_machine_allowed_transitions() -> None:
    """Validate the complete state machine transition map is correct."""
    sm = BookingService.ALLOWED_TRANSITIONS

    # Terminal states have no transitions
    assert sm[BookingStatus.COMPLETED.value] == set()
    assert sm[BookingStatus.CANCELLED.value] == set()

    # Progressive flow
    assert BookingStatus.PROVIDER_ASSIGNED.value in sm[BookingStatus.SEARCHING.value]
    assert BookingStatus.ACCEPTED.value in sm[BookingStatus.PROVIDER_ASSIGNED.value]
    assert BookingStatus.ON_THE_WAY.value in sm[BookingStatus.ACCEPTED.value]
    assert BookingStatus.ARRIVED.value in sm[BookingStatus.ON_THE_WAY.value]
    assert BookingStatus.IN_PROGRESS.value in sm[BookingStatus.ARRIVED.value]
    assert BookingStatus.COMPLETED.value in sm[BookingStatus.IN_PROGRESS.value]

    # Cancel is available before completion
    assert BookingStatus.CANCELLED.value in sm[BookingStatus.REQUESTED.value]
    assert BookingStatus.CANCELLED.value in sm[BookingStatus.SEARCHING.value]
    assert BookingStatus.CANCELLED.value in sm[BookingStatus.ACCEPTED.value]


def test_booking_state_machine_no_illegal_jump() -> None:
    """COMPLETED state cannot transition to anything."""
    sm = BookingService.ALLOWED_TRANSITIONS
    assert len(sm[BookingStatus.COMPLETED.value]) == 0


# ==============================================================================
# Tests: Geospatial Utility (Unit)
# ==============================================================================


def test_haversine_distance_same_point() -> None:
    """Distance from a point to itself is 0."""
    result = haversine_distance_km(19.076, 72.877, 19.076, 72.877)
    assert result == pytest.approx(0.0, abs=1e-6)


def test_haversine_distance_known_pair() -> None:
    """Mumbai to Pune is approximately 120-130 km by straight line."""
    # Mumbai (Bandra): 19.060, 72.836
    # Pune (Shivajinagar): 18.530, 73.848
    result = haversine_distance_km(19.060, 72.836, 18.530, 73.848)
    assert 115.0 <= result <= 135.0


def test_haversine_symmetry() -> None:
    """d(A, B) == d(B, A)."""
    d1 = haversine_distance_km(19.076, 72.877, 28.613, 77.209)
    d2 = haversine_distance_km(28.613, 77.209, 19.076, 72.877)
    assert d1 == pytest.approx(d2, rel=1e-5)


# ==============================================================================
# Tests: Provider Active Dispatch Offers
# ==============================================================================


@pytest.mark.asyncio
async def test_get_active_dispatch_offers_empty(
    provider_user: User, verified_provider: Provider
) -> None:
    """Provider with no pending offers gets empty list."""
    token = create_access_token(user_id=provider_user.id, role=UserRole.PROVIDER.value)
    headers = {"Authorization": f"Bearer {token}"}

    mock_redis = AsyncMock()
    mock_redis.get.return_value = None  # No active offer
    app.dependency_overrides[get_redis] = lambda: mock_redis

    try:
        with (
            patch("app.api.deps.UserRepository.get_by_id", new_callable=AsyncMock) as mock_user,
            patch("app.services.dispatch_service.ProviderRepository.get_by_user_id", new_callable=AsyncMock) as mock_prov,
        ):
            mock_user.return_value = provider_user
            mock_prov.return_value = verified_provider

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.get("/api/v1/providers/me/dispatch/offers", headers=headers)
    finally:
        app.dependency_overrides.pop(get_redis, None)

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] == 0
    assert data["offers"] == []


@pytest.mark.asyncio
async def test_unauthenticated_cannot_access_dispatch_offers() -> None:
    """Unauthenticated access to dispatch offers returns 401."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/providers/me/dispatch/offers")

    assert resp.status_code == 401
