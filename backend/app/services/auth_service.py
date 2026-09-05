import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import (
    AuthenticationError,
    ConflictError,
    ForbiddenError,
    ValidationError,
)
from app.core.otp import OTPService
from app.core.rate_limit import enforce_rate_limit
from app.core.redis import redis_client
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.enums import (
    ProviderType,
    ProviderVerificationStatus,
    UserRole,
    UserStatus,
)
from app.models.provider import Provider
from app.models.user import User
from app.repositories.user import UserRepository
from app.schemas.auth import (
    LogoutRequest,
    MessageResponse,
    OTPRequest,
    OTPRequestResponse,
    OTPVerifyRequest,
    OTPVerifyResponse,
    TokenRefreshRequest,
    TokenRefreshResponse,
    TokenResponse,
    UserLoginRequest,
    UserRegisterRequest,
    UserResponse,
)
from app.services.audit_service import record_audit_event


class AuthService:
    """Domain service for user auth, token lifecycle, and session management."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.user_repo = UserRepository(session)

    async def register(
        self,
        data: UserRegisterRequest,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> TokenResponse:
        """
        Registers a new user account, performs validation, hashes password,
        persists identity, creates initial provider profile, and returns JWT.
        """
        # Disallow direct registration of privileged administrative roles
        if data.role not in (UserRole.CUSTOMER, UserRole.PROVIDER):
            raise ValidationError(
                message=(
                    "Only CUSTOMER and PROVIDER roles are permitted for registration."
                ),
                code="AUTH_INVALID_ROLE",
            )

        clean_phone = data.phone.strip()
        clean_email = data.email.strip().lower() if data.email else None

        # Check unique constraints
        existing_phone = await self.user_repo.get_by_phone(clean_phone)
        if existing_phone:
            raise ConflictError(
                message="Phone number is already registered.",
                code="AUTH_DUPLICATE_PHONE",
                details={"field": "phone"},
            )

        if clean_email:
            existing_email = await self.user_repo.get_by_email(clean_email)
            if existing_email:
                raise ConflictError(
                    message="Email address is already registered.",
                    code="AUTH_DUPLICATE_EMAIL",
                    details={"field": "email"},
                )

        # Hash password securely
        pwd_hash = hash_password(data.password)

        # Create user entity
        user = User(
            role=data.role.value,
            first_name=data.first_name.strip(),
            last_name=data.last_name.strip() if data.last_name else None,
            phone=clean_phone,
            email=clean_email,
            password_hash=pwd_hash,
            status=UserStatus.ACTIVE.value,
        )
        self.session.add(user)
        await self.session.flush()

        # If registering as a provider, create initial provider profile
        if data.role == UserRole.PROVIDER:
            provider = Provider(
                user_id=user.id,
                business_name=f"{user.first_name}'s Service",
                provider_type=ProviderType.OTHER.value,
                phone=user.phone,
                service_radius_km=15.0,
                verification_status=ProviderVerificationStatus.PENDING.value,
                is_online=False,
            )
            self.session.add(provider)
            await self.session.flush()

        # Record audit log
        await record_audit_event(
            session=self.session,
            action="CREATE",
            entity_type="User",
            entity_id=user.id,
            actor_user_id=user.id,
            new_data={
                "role": user.role,
                "phone": user.phone,
                "email": user.email,
                "first_name": user.first_name,
                "status": user.status,
            },
            ip_address=ip_address,
            user_agent=user_agent,
        )

        # Generate tokens
        return await self._issue_token_bundle(user)

    async def login(
        self,
        data: UserLoginRequest,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> TokenResponse:
        """
        Authenticates user credentials, applies brute force rate limiting,
        updates last login timestamp, and returns token bundle.
        """
        clean_identifier = data.phone_or_email.strip()

        # Enforce rate limit per IP + identifier
        rate_key = f"login:{ip_address or 'unknown'}_{clean_identifier}"
        await enforce_rate_limit(
            key=rate_key,
            max_requests=settings.RATE_LIMIT_LOGIN_MAX_ATTEMPTS,
            window_seconds=settings.RATE_LIMIT_LOGIN_WINDOW_SECONDS,
            error_code="RATE_LIMITED",
            message="Too many failed login attempts. Please try again later.",
        )

        user = await self.user_repo.get_by_phone_or_email(clean_identifier)
        if not user or not user.password_hash:
            # Audit failed attempt
            await record_audit_event(
                session=self.session,
                action="FAILED_LOGIN",
                entity_type="User",
                new_data={"identifier": clean_identifier, "reason": "user_not_found"},
                ip_address=ip_address,
                user_agent=user_agent,
            )
            raise AuthenticationError(
                message="Invalid credentials.",
                code="AUTH_INVALID_CREDENTIALS",
            )

        if user.status != UserStatus.ACTIVE.value:
            raise ForbiddenError(
                message=f"Account is {user.status.lower()}. Please contact support.",
                code="AUTH_ACCOUNT_INACTIVE",
                details={"status": user.status},
            )

        if not verify_password(data.password, user.password_hash):
            # Audit failed attempt
            await record_audit_event(
                session=self.session,
                action="FAILED_LOGIN",
                entity_type="User",
                entity_id=user.id,
                actor_user_id=user.id,
                new_data={"reason": "invalid_password"},
                ip_address=ip_address,
                user_agent=user_agent,
            )
            raise AuthenticationError(
                message="Invalid credentials.",
                code="AUTH_INVALID_CREDENTIALS",
            )

        # Update last login timestamp
        await self.user_repo.update_last_login(user.id)

        # Audit successful login
        await record_audit_event(
            session=self.session,
            action="LOGIN",
            entity_type="User",
            entity_id=user.id,
            actor_user_id=user.id,
            new_data={"status": "success"},
            ip_address=ip_address,
            user_agent=user_agent,
        )

        return await self._issue_token_bundle(user)

    async def refresh_tokens(
        self,
        data: TokenRefreshRequest,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> TokenRefreshResponse:
        """
        Validates refresh token against Redis session store,
        executes token rotation (invalidates old JTI, issues new JTI),
        and returns refreshed token pair.
        """
        # Decode token and verify type
        payload = decode_token(data.refresh_token, expected_type="refresh")
        user_id_str = payload.get("sub", "")
        old_jti = payload.get("jti", "")

        try:
            user_id = uuid.UUID(user_id_str)
        except ValueError:
            raise AuthenticationError(
                message="Invalid subject identifier in refresh token.",
                code="AUTH_INVALID_TOKEN",
            ) from None

        redis = redis_client.client
        session_key = f"refresh_token:{user_id}:{old_jti}"
        session_exists = await redis.get(session_key)

        if not session_exists:
            # Token is not in active sessions (could be reused, revoked, or expired)
            await record_audit_event(
                session=self.session,
                action="TOKEN_REUSE_DETECTED",
                entity_type="User",
                actor_user_id=user_id,
                entity_id=user_id,
                new_data={"jti": old_jti},
                ip_address=ip_address,
                user_agent=user_agent,
            )
            raise AuthenticationError(
                message="Refresh token has been revoked or expired.",
                code="AUTH_TOKEN_REVOKED",
            )

        # Invalidate old refresh token session (Token Rotation)
        await redis.delete(session_key)

        # Load user and verify active status
        user = await self.user_repo.get_by_id(user_id)
        if not user or user.status != UserStatus.ACTIVE.value:
            raise ForbiddenError(
                message="User account is no longer active.",
                code="AUTH_ACCOUNT_INACTIVE",
            )

        # Issue new Access & Refresh tokens
        access_token = create_access_token(user_id=user.id, role=user.role)
        new_refresh_token, new_jti, new_expire = create_refresh_token(user_id=user.id)

        # Store new refresh token in Redis
        new_session_key = f"refresh_token:{user.id}:{new_jti}"
        ttl_seconds = int((new_expire - datetime.now(UTC)).total_seconds())
        await redis.set(new_session_key, "1", ex=max(60, ttl_seconds))

        # Audit token rotation
        await record_audit_event(
            session=self.session,
            action="TOKEN_REFRESH",
            entity_type="User",
            actor_user_id=user.id,
            entity_id=user.id,
            new_data={"rotated_from_jti": old_jti, "new_jti": new_jti},
            ip_address=ip_address,
            user_agent=user_agent,
        )

        return TokenRefreshResponse(
            access_token=access_token,
            refresh_token=new_refresh_token,
            token_type="Bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

    async def logout(
        self,
        current_user: User,
        data: LogoutRequest | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> MessageResponse:
        """
        Revokes the refresh token session in Redis and logs the event.
        """
        redis = redis_client.client
        revoked_count = 0

        if data and data.refresh_token:
            try:
                payload = decode_token(data.refresh_token, expected_type="refresh")
                jti = payload.get("jti")
                if jti:
                    key = f"refresh_token:{current_user.id}:{jti}"
                    await redis.delete(key)
                    revoked_count += 1
            except Exception:
                pass

        # Also purge any active sessions matching user pattern
        pattern = f"refresh_token:{current_user.id}:*"
        keys = [k async for k in redis.scan_iter(match=pattern)]
        if keys:
            await redis.delete(*keys)
            revoked_count += len(keys)

        await record_audit_event(
            session=self.session,
            action="LOGOUT",
            entity_type="User",
            actor_user_id=current_user.id,
            entity_id=current_user.id,
            new_data={"revoked_sessions": revoked_count},
            ip_address=ip_address,
            user_agent=user_agent,
        )

        return MessageResponse(
            message="Successfully logged out and revoked active sessions."
        )

    async def request_otp(
        self,
        data: OTPRequest,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> OTPRequestResponse:
        """Generates a cryptographic rate-limited OTP and records an audit event."""
        clean_phone = data.phone.strip()
        purpose = data.purpose.strip().upper()

        raw_otp, expires_in = await OTPService.request_otp(
            phone=clean_phone, purpose=purpose, ip_address=ip_address
        )

        await record_audit_event(
            session=self.session,
            action="OTP_REQUEST",
            entity_type="OTP",
            new_data={
                "phone": clean_phone,
                "purpose": purpose,
                "expires_in": expires_in,
            },
            ip_address=ip_address,
            user_agent=user_agent,
        )

        return OTPRequestResponse(
            message="OTP generated and sent successfully.",
            expires_in_seconds=expires_in,
            phone=clean_phone,
        )

    async def verify_otp(
        self,
        data: OTPVerifyRequest,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> OTPVerifyResponse:
        """
        Verifies OTP code. If purpose is LOGIN and user exists, issues JWT token bundle.
        """
        clean_phone = data.phone.strip()
        purpose = data.purpose.strip().upper()

        is_verified = await OTPService.verify_otp(
            phone=clean_phone, code=data.code, purpose=purpose
        )

        await record_audit_event(
            session=self.session,
            action="STATUS_CHANGE",
            entity_type="OTP",
            new_data={
                "phone": clean_phone,
                "purpose": purpose,
                "verified": is_verified,
            },
            ip_address=ip_address,
            user_agent=user_agent,
        )

        tokens: TokenResponse | None = None
        if purpose == "LOGIN":
            user = await self.user_repo.get_by_phone(clean_phone)
            if user:
                if user.status != UserStatus.ACTIVE.value:
                    raise ForbiddenError(
                        message=f"Account is {user.status.lower()}.",
                        code="AUTH_ACCOUNT_INACTIVE",
                    )
                await self.user_repo.update_last_login(user.id)
                tokens = await self._issue_token_bundle(user)
                return OTPVerifyResponse(
                    verified=True,
                    message="OTP verified and user logged in successfully.",
                    tokens=tokens,
                )

        return OTPVerifyResponse(
            verified=True,
            message="OTP verified successfully.",
            tokens=None,
        )

    async def _issue_token_bundle(self, user: User) -> TokenResponse:
        """Internal helper to generate JWT access/refresh tokens and persist session."""
        access_token = create_access_token(user_id=user.id, role=user.role)
        refresh_token, jti, expire = create_refresh_token(user_id=user.id)

        # Store refresh token session in Redis
        redis = redis_client.client
        session_key = f"refresh_token:{user.id}:{jti}"
        ttl_seconds = int((expire - datetime.now(UTC)).total_seconds())
        await redis.set(session_key, "1", ex=max(60, ttl_seconds))

        user_resp = UserResponse(
            id=user.id,
            role=user.role,
            first_name=user.first_name,
            last_name=user.last_name,
            phone=user.phone,
            email=user.email,
            status=user.status,
            last_login_at=user.last_login_at,
            created_at=user.created_at,
            updated_at=user.updated_at,
        )

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="Bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            user=user_resp,
        )
