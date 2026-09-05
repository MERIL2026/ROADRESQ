import uuid
from datetime import timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.deps import authorize_resource_owner
from app.core.config import settings
from app.core.errors import (
    AuthenticationError,
    ForbiddenError,
    OTPInvalidError,
    OTPRateLimitedError,
)
from app.core.otp import OTPService
from app.core.rate_limit import check_rate_limit
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.audit import AuditLog
from app.models.enums import UserRole, UserStatus
from app.models.user import User


@pytest.fixture
def db_session_factory():
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    return session_factory


# =========================================================================
# 1. PASSWORD SECURITY TESTS
# =========================================================================

def test_password_hash_generation_and_verification() -> None:
    raw = "SuperSecretPassword123!"
    hashed = hash_password(raw)

    assert hashed != raw
    assert hashed.startswith("$2b$") or hashed.startswith("$2a$")
    assert verify_password(raw, hashed) is True
    assert verify_password("WrongPassword123!", hashed) is False
    assert verify_password("", hashed) is False


def test_password_never_plaintext() -> None:
    raw = "MyP@ssw0rd2026!"
    hashed = hash_password(raw)
    assert raw not in hashed


# =========================================================================
# 2. JWT ACCESS & REFRESH TOKEN TESTS
# =========================================================================

def test_jwt_access_token_creation_and_decoding() -> None:
    user_id = uuid.uuid4()
    role = UserRole.CUSTOMER.value

    token = create_access_token(user_id=user_id, role=role)
    payload = decode_token(token, expected_type="access")

    assert payload["sub"] == str(user_id)
    assert payload["role"] == role
    assert payload["type"] == "access"
    assert "jti" in payload
    assert payload["exp"] > payload["iat"]


def test_jwt_expired_token() -> None:
    user_id = uuid.uuid4()
    token = create_access_token(
        user_id=user_id,
        role=UserRole.CUSTOMER.value,
        expires_delta=timedelta(seconds=-10),
    )
    with pytest.raises(AuthenticationError) as exc_info:
        decode_token(token)
    assert exc_info.value.code == "AUTH_TOKEN_EXPIRED"


def test_jwt_invalid_signature() -> None:
    user_id = uuid.uuid4()
    token = create_access_token(user_id=user_id, role=UserRole.CUSTOMER.value)
    tampered_token = token[:-5] + "aaaaa"

    with pytest.raises(AuthenticationError) as exc_info:
        decode_token(tampered_token)
    assert exc_info.value.code == "AUTH_INVALID_TOKEN"


def test_jwt_wrong_token_type() -> None:
    user_id = uuid.uuid4()
    refresh_token_str, _, _ = create_refresh_token(user_id=user_id)

    with pytest.raises(AuthenticationError) as exc_info:
        decode_token(refresh_token_str, expected_type="access")
    assert exc_info.value.code == "AUTH_INVALID_TOKEN_TYPE"


# =========================================================================
# 3. OTP FOUNDATION TESTS (REDIS-BACKED)
# =========================================================================

@pytest.mark.asyncio
async def test_otp_generation_verification_lifecycle() -> None:
    phone = f"+91999{uuid.uuid4().hex[:7]}"
    purpose = "TEST_AUTH"

    raw_otp, expires_in = await OTPService.request_otp(phone=phone, purpose=purpose)
    assert len(raw_otp) == settings.OTP_LENGTH
    assert raw_otp.isdigit()
    assert expires_in == settings.OTP_EXPIRE_SECONDS

    # Verify matching OTP
    verified = await OTPService.verify_otp(phone=phone, code=raw_otp, purpose=purpose)
    assert verified is True

    # Single-use check: verifying again must fail
    with pytest.raises(OTPInvalidError):
        await OTPService.verify_otp(phone=phone, code=raw_otp, purpose=purpose)


@pytest.mark.asyncio
async def test_otp_incorrect_code_and_max_attempts() -> None:
    phone = f"+91998{uuid.uuid4().hex[:7]}"
    purpose = "TEST_ATTEMPTS"

    raw_otp, _ = await OTPService.request_otp(phone=phone, purpose=purpose)

    # Attempt 1: wrong code
    with pytest.raises(OTPInvalidError) as exc1:
        await OTPService.verify_otp(phone=phone, code="000000", purpose=purpose)
    assert exc1.value.details.get("remaining_attempts") == 2

    # Attempt 2: wrong code
    with pytest.raises(OTPInvalidError) as exc2:
        await OTPService.verify_otp(phone=phone, code="111111", purpose=purpose)
    assert exc2.value.details.get("remaining_attempts") == 1

    # Attempt 3: max attempts reached -> invalidates OTP completely
    with pytest.raises(OTPInvalidError) as exc3:
        await OTPService.verify_otp(phone=phone, code="222222", purpose=purpose)
    assert exc3.value.code == "AUTH_OTP_MAX_ATTEMPTS_EXCEEDED"

    # Subsequent attempt -> OTP no longer exists
    with pytest.raises(OTPInvalidError):
        await OTPService.verify_otp(phone=phone, code=raw_otp, purpose=purpose)


@pytest.mark.asyncio
async def test_otp_resend_cooldown() -> None:
    phone = f"+91997{uuid.uuid4().hex[:7]}"
    purpose = "TEST_COOLDOWN"

    await OTPService.request_otp(phone=phone, purpose=purpose)

    # Immediately requesting another must trigger cooldown error
    with pytest.raises(OTPRateLimitedError):
        await OTPService.request_otp(phone=phone, purpose=purpose)


# =========================================================================
# 4. REGISTRATION & LOGIN API TESTS
# =========================================================================

@pytest.mark.asyncio
async def test_register_and_login_flow(async_client: AsyncClient) -> None:
    uid = uuid.uuid4().hex[:6]
    phone = f"+91911{uid}"
    email = f"user_{uid}@roadresq.com"
    password = "SecurePassword2026!"

    # 1. Register Customer
    reg_payload = {
        "phone": phone,
        "first_name": "Rajesh",
        "last_name": "Kumar",
        "email": email,
        "password": password,
        "role": "CUSTOMER",
    }
    res = await async_client.post("/api/v1/auth/register", json=reg_payload)
    assert res.status_code == 201
    data = res.json()["data"]

    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "Bearer"
    assert data["user"]["phone"] == phone
    assert data["user"]["email"] == email
    assert data["user"]["role"] == "CUSTOMER"
    assert "password" not in data["user"]
    assert "password_hash" not in data["user"]

    # 2. Prevent Duplicate Phone Registration
    dup_res = await async_client.post("/api/v1/auth/register", json=reg_payload)
    assert dup_res.status_code == 409
    err = dup_res.json()["error"]
    assert err["code"] == "AUTH_DUPLICATE_PHONE"

    # 3. Login with Phone
    login_phone_res = await async_client.post(
        "/api/v1/auth/login",
        json={"phone_or_email": phone, "password": password},
    )
    assert login_phone_res.status_code == 200
    login_data = login_phone_res.json()["data"]
    assert login_data["user"]["id"] == data["user"]["id"]

    # 4. Login with Email
    login_email_res = await async_client.post(
        "/api/v1/auth/login",
        json={"phone_or_email": email, "password": password},
    )
    assert login_email_res.status_code == 200

    # 5. Login with Wrong Password
    bad_pwd_res = await async_client.post(
        "/api/v1/auth/login",
        json={"phone_or_email": phone, "password": "WrongPassword123!"},
    )
    assert bad_pwd_res.status_code == 401
    assert bad_pwd_res.json()["error"]["code"] == "AUTH_INVALID_CREDENTIALS"

    # 6. Login with Nonexistent User (Generic message to prevent account enumeration)
    no_user_res = await async_client.post(
        "/api/v1/auth/login",
        json={"phone_or_email": "+919999999999", "password": password},
    )
    assert no_user_res.status_code == 401
    assert no_user_res.json()["error"]["code"] == "AUTH_INVALID_CREDENTIALS"


@pytest.mark.asyncio
async def test_register_provider_flow(async_client: AsyncClient) -> None:
    uid = uuid.uuid4().hex[:6]
    phone = f"+91912{uid}"
    email = f"provider_{uid}@roadresq.com"
    password = "ProviderPass2026!"

    reg_payload = {
        "phone": phone,
        "first_name": "Suresh",
        "last_name": "Patel",
        "email": email,
        "password": password,
        "role": "PROVIDER",
    }
    res = await async_client.post("/api/v1/auth/register", json=reg_payload)
    assert res.status_code == 201
    data = res.json()["data"]
    assert data["user"]["role"] == "PROVIDER"


# =========================================================================
# 5. REFRESH TOKEN ROTATION & REVOCATION TESTS
# =========================================================================

@pytest.mark.asyncio
async def test_refresh_token_rotation_and_revocation(async_client: AsyncClient) -> None:
    uid = uuid.uuid4().hex[:6]
    phone = f"+91913{uid}"
    email = f"ref_{uid}@roadresq.com"
    password = "TestRefreshPass2026!"

    reg_res = await async_client.post(
        "/api/v1/auth/register",
        json={
            "phone": phone,
            "first_name": "Aakash",
            "last_name": "Mehta",
            "email": email,
            "password": password,
            "role": "CUSTOMER",
        },
    )
    token_bundle = reg_res.json()["data"]
    refresh_token = token_bundle["refresh_token"]

    # 1. Successful Refresh (Rotation)
    ref_res = await async_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert ref_res.status_code == 200
    ref_data = ref_res.json()["data"]
    assert "access_token" in ref_data
    assert "refresh_token" in ref_data
    rotated_refresh_token = ref_data["refresh_token"]
    assert rotated_refresh_token != refresh_token

    # 2. Replay / Reuse Detection: Old refresh token must be rejected
    reuse_res = await async_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert reuse_res.status_code == 401
    assert reuse_res.json()["error"]["code"] == "AUTH_TOKEN_REVOKED"

    # 3. Logout with Rotated Token
    new_access_token = ref_data["access_token"]
    logout_res = await async_client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {new_access_token}"},
        json={"refresh_token": rotated_refresh_token},
    )
    assert logout_res.status_code == 200

    # 4. Revoked Token cannot be used to refresh
    post_logout_res = await async_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": rotated_refresh_token},
    )
    assert post_logout_res.status_code == 401


# =========================================================================
# 6. GET /auth/me & RBAC / OBJECT-LEVEL AUTHORIZATION TESTS
# =========================================================================

@pytest.mark.asyncio
async def test_auth_me_endpoint(async_client: AsyncClient) -> None:
    uid = uuid.uuid4().hex[:6]
    phone = f"+91914{uid}"
    email = f"me_{uid}@roadresq.com"
    password = "MePassword2026!"

    reg_res = await async_client.post(
        "/api/v1/auth/register",
        json={
            "phone": phone,
            "first_name": "Priya",
            "last_name": "Sharma",
            "email": email,
            "password": password,
            "role": "CUSTOMER",
        },
    )
    tokens = reg_res.json()["data"]
    access_token = tokens["access_token"]

    # Authenticated request
    me_res = await async_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert me_res.status_code == 200
    me_data = me_res.json()["data"]
    assert me_data["phone"] == phone
    assert me_data["first_name"] == "Priya"

    # Unauthenticated request
    unauth_res = await async_client.get("/api/v1/auth/me")
    assert unauth_res.status_code == 401


def test_object_level_authorization_logic() -> None:
    user1_id = uuid.uuid4()
    user2_id = uuid.uuid4()

    owner_user = User(
        id=user1_id,
        role=UserRole.CUSTOMER.value,
        first_name="Owner",
        phone="+919999000001",
        status=UserStatus.ACTIVE.value,
    )
    admin_user = User(
        id=uuid.uuid4(),
        role=UserRole.ADMIN.value,
        first_name="Admin",
        phone="+919999000002",
        status=UserStatus.ACTIVE.value,
    )
    other_user = User(
        id=user2_id,
        role=UserRole.CUSTOMER.value,
        first_name="Other",
        phone="+919999000003",
        status=UserStatus.ACTIVE.value,
    )

    # 1. Owner access succeeds
    authorize_resource_owner(resource_owner_id=user1_id, current_user=owner_user)

    # 2. Admin access succeeds
    authorize_resource_owner(resource_owner_id=user1_id, current_user=admin_user)

    # 3. Non-owner access denied
    with pytest.raises(ForbiddenError):
        authorize_resource_owner(resource_owner_id=user1_id, current_user=other_user)


# =========================================================================
# 7. AUDIT LOG INTEGRATION TESTS
# =========================================================================

@pytest.mark.asyncio
async def test_audit_log_created_without_credentials(
    async_client: AsyncClient, db_session_factory: Any
) -> None:
    uid = uuid.uuid4().hex[:6]
    phone = f"+91915{uid}"
    email = f"audit_{uid}@roadresq.com"
    password = "AuditPassword2026!"

    await async_client.post(
        "/api/v1/auth/register",
        json={
            "phone": phone,
            "first_name": "Audit",
            "last_name": "User",
            "email": email,
            "password": password,
            "role": "CUSTOMER",
        },
    )

    # Verify audit logs in database
    async with db_session_factory() as session:
        stmt = (
            select(AuditLog)
            .where(AuditLog.action.in_(["CREATE", "LOGIN"]))
            .order_by(AuditLog.created_at.desc())
            .limit(10)
        )
        res = await session.execute(stmt)
        logs = res.scalars().all()
        assert len(logs) > 0

        for log in logs:
            payload_str = str(log.new_data or {}) + str(log.old_data or {})
            # CRITICAL: Verify passwords, password_hash, and tokens never leak into audit records
            assert password not in payload_str
            assert "password_hash" not in payload_str
            assert "access_token" not in payload_str
            assert "refresh_token" not in payload_str


# =========================================================================
# 8. ACCOUNT STATUS (SUSPENDED/INACTIVE) TESTS
# =========================================================================

@pytest.mark.asyncio
async def test_login_suspended_user_rejected(
    async_client: AsyncClient, db_session_factory: Any
) -> None:
    uid = uuid.uuid4().hex[:6]
    phone = f"+91916{uid}"
    email = f"suspended_{uid}@roadresq.com"
    password = "SuspendedPassword2026!"

    # Register active user
    await async_client.post(
        "/api/v1/auth/register",
        json={
            "phone": phone,
            "first_name": "Suspended",
            "last_name": "User",
            "email": email,
            "password": password,
            "role": "CUSTOMER",
        },
    )

    # Change status to SUSPENDED in DB
    async with db_session_factory() as session:
        stmt = select(User).where(User.phone == phone)
        res = await session.execute(stmt)
        user = res.scalar_one()
        user.status = UserStatus.SUSPENDED.value
        await session.commit()

    # Attempt login
    login_res = await async_client.post(
        "/api/v1/auth/login",
        json={"phone_or_email": phone, "password": password},
    )
    assert login_res.status_code == 403
    assert login_res.json()["error"]["code"] == "AUTH_ACCOUNT_INACTIVE"


# =========================================================================
# 9. OTP HTTP API ENDPOINTS TEST
# =========================================================================

@pytest.mark.asyncio
async def test_otp_api_endpoints_flow(async_client: AsyncClient) -> None:
    uid = uuid.uuid4().hex[:6]
    phone = f"+91917{uid}"
    email = f"otpuser_{uid}@roadresq.com"
    password = "OtpPassword2026!"

    # 1. Register user so phone exists in DB
    await async_client.post(
        "/api/v1/auth/register",
        json={
            "phone": phone,
            "first_name": "OtpUser",
            "last_name": "Test",
            "email": email,
            "password": password,
            "role": "CUSTOMER",
        },
    )

    # 2. Request OTP via API
    req_res = await async_client.post(
        "/api/v1/auth/otp/request",
        json={"phone": phone, "purpose": "LOGIN"},
    )
    assert req_res.status_code == 200
    assert req_res.json()["data"]["phone"] == phone

    # Retrieve test OTP
    test_otp = await OTPService.get_test_otp(phone=phone, purpose="LOGIN")
    assert test_otp is not None

    # 3. Verify OTP via API -> Logs in user
    verify_res = await async_client.post(
        "/api/v1/auth/otp/verify",
        json={"phone": phone, "code": test_otp, "purpose": "LOGIN"},
    )
    assert verify_res.status_code == 200
    v_data = verify_res.json()["data"]
    assert v_data["verified"] is True
    assert v_data["tokens"] is not None
    assert "access_token" in v_data["tokens"]


# =========================================================================
# 10. RBAC HTTP GUARDS & RATE LIMITER TESTS
# =========================================================================

@pytest.mark.asyncio
async def test_rbac_guards_over_roles() -> None:
    from app.api.deps import require_admin, require_customer, require_provider

    customer_user = User(
        id=uuid.uuid4(),
        role=UserRole.CUSTOMER.value,
        first_name="Cust",
        phone="+919999111111",
        status=UserStatus.ACTIVE.value,
    )
    provider_user = User(
        id=uuid.uuid4(),
        role=UserRole.PROVIDER.value,
        first_name="Prov",
        phone="+919999222222",
        status=UserStatus.ACTIVE.value,
    )
    admin_user = User(
        id=uuid.uuid4(),
        role=UserRole.ADMIN.value,
        first_name="Admin",
        phone="+919999333333",
        status=UserStatus.ACTIVE.value,
    )

    # require_customer
    cust_guard = require_customer
    assert (await cust_guard(customer_user)) == customer_user
    with pytest.raises(ForbiddenError):
        await cust_guard(provider_user)

    # require_provider
    prov_guard = require_provider
    assert (await prov_guard(provider_user)) == provider_user
    with pytest.raises(ForbiddenError):
        await prov_guard(customer_user)

    # require_admin
    admin_guard = require_admin
    assert (await admin_guard(admin_user)) == admin_user
    with pytest.raises(ForbiddenError):
        await admin_guard(customer_user)


@pytest.mark.asyncio
async def test_rate_limiter_logic() -> None:
    key = f"test_rate_key_{uuid.uuid4().hex[:6]}"
    max_reqs = 3
    window = 10

    # 3 allowed requests
    for i in range(max_reqs):
        is_allowed, count, _ = await check_rate_limit(
            key=key, max_requests=max_reqs, window_seconds=window
        )
        assert is_allowed is True
        assert count == i + 1

    # 4th request exceeds rate limit
    is_allowed, count, retry_after = await check_rate_limit(
        key=key, max_requests=max_reqs, window_seconds=window
    )
    assert is_allowed is False
    assert retry_after > 0

