import uuid
from collections.abc import AsyncGenerator, Callable
from typing import Any

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.errors import AuthenticationError, ForbiddenError
from app.core.redis import RedisClient, redis_client
from app.core.security import decode_token
from app.models.enums import UserRole, UserStatus
from app.models.user import User
from app.repositories.user import UserRepository

security_scheme = HTTPBearer(auto_error=False)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for obtaining async DB session."""
    async for session in get_db():
        yield session


def get_redis() -> RedisClient:
    """Dependency for obtaining Redis client."""
    return redis_client


def get_request_id(request: Request) -> str:
    """Extracts or returns correlation ID from request state."""
    return getattr(request.state, "request_id", "unknown")


def get_client_ip(request: Request) -> str:
    """Extracts client IP address supporting forward proxies."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    client = request.client
    return client.host if client else "unknown"


def get_user_agent(request: Request) -> str:
    """Extracts client User-Agent header."""
    return request.headers.get("User-Agent", "unknown")


async def get_current_user(
    auth: HTTPAuthorizationCredentials | None = Depends(security_scheme),
    session: AsyncSession = Depends(get_db_session),
) -> User:
    """
    Extracts, decodes, and validates JWT Bearer access token from Authorization header.
    Loads user record from the database.
    """
    if not auth or not auth.credentials:
        raise AuthenticationError(
            message="Missing or invalid authorization header.",
            code="AUTH_HEADER_MISSING",
        )

    payload = decode_token(auth.credentials, expected_type="access")
    user_id_str = payload.get("sub")
    if not user_id_str:
        raise AuthenticationError(
            message="Token payload is missing subject.",
            code="AUTH_INVALID_TOKEN",
        )

    try:
        user_id = uuid.UUID(user_id_str)
    except ValueError:
        raise AuthenticationError(
            message="Invalid subject in token payload.",
            code="AUTH_INVALID_TOKEN",
        ) from None

    user_repo = UserRepository(session)
    user = await user_repo.get_by_id(user_id)
    if not user:
        raise AuthenticationError(
            message="User account does not exist.",
            code="AUTH_USER_NOT_FOUND",
        )

    return user


async def get_current_active_user(
    user: User = Depends(get_current_user),
) -> User:
    """Ensures authenticated user is active (not suspended, blocked, or pending)."""
    if user.status != UserStatus.ACTIVE.value:
        raise ForbiddenError(
            message=f"Account is {user.status.lower()}.",
            code="AUTH_ACCOUNT_INACTIVE",
            details={"status": user.status},
        )
    return user


def require_roles(*allowed_roles: UserRole) -> Callable[..., Any]:
    """
    Factory dependency creating a role-enforcement guard.
    Fails with HTTP 403 FORBIDDEN if the user role is not permitted.
    """
    allowed_values = {role.value for role in allowed_roles}

    async def role_checker(
        current_user: User = Depends(get_current_active_user),
    ) -> User:
        if current_user.role not in allowed_values:
            raise ForbiddenError(
                message="You do not have the required permissions for this operation.",
                code="FORBIDDEN",
                details={
                    "user_role": current_user.role,
                    "required_roles": list(allowed_values),
                },
            )
        return current_user

    return role_checker


# Role-specific convenience guards
require_customer = require_roles(UserRole.CUSTOMER)
require_provider = require_roles(UserRole.PROVIDER)
require_admin = require_roles(UserRole.ADMIN)
require_support_or_admin = require_roles(UserRole.SUPPORT, UserRole.ADMIN)


def authorize_resource_owner(
    resource_owner_id: uuid.UUID,
    current_user: User,
    resource_name: str = "resource",
) -> None:
    """
    Object-level authorization check.
    Allows operation if current_user is ADMIN or owns the specified resource.
    Raises ForbiddenError otherwise to prevent IDOR vulnerabilities.
    """
    if current_user.role == UserRole.ADMIN.value:
        return

    if current_user.id != resource_owner_id:
        raise ForbiddenError(
            message=f"You are not authorized to access this {resource_name}.",
            code="FORBIDDEN",
            details={"resource_owner_id": str(resource_owner_id)},
        )
