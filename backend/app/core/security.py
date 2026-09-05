import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt

from app.core.config import settings
from app.core.errors import AuthenticationError


def hash_password(password: str) -> str:
    """Securely hashes a plaintext password using bcrypt with work factor 12."""
    salt = bcrypt.gensalt(rounds=12)
    pwd_bytes = password.encode("utf-8")
    return bcrypt.hashpw(pwd_bytes, salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plaintext password against a stored bcrypt hash in constant time."""
    try:
        pwd_bytes = plain_password.encode("utf-8")
        hash_bytes = hashed_password.encode("utf-8")
        return bool(bcrypt.checkpw(pwd_bytes, hash_bytes))
    except Exception:
        return False


def create_access_token(
    user_id: uuid.UUID | str,
    role: str,
    extra_claims: dict[str, Any] | None = None,
    expires_delta: timedelta | None = None,
) -> str:
    """Generates a cryptographically signed JWT access token."""
    now = datetime.now(UTC)
    expire = now + (
        expires_delta
        if expires_delta is not None
        else timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "role": role,
        "type": "access",
        "jti": str(uuid.uuid4()),
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    if extra_claims:
        for k, v in extra_claims.items():
            if k not in payload:
                payload[k] = v
    encoded_jwt: str = jwt.encode(
        payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM
    )
    return encoded_jwt


def create_refresh_token(
    user_id: uuid.UUID | str,
    expires_delta: timedelta | None = None,
) -> tuple[str, str, datetime]:
    """
    Generates a cryptographically signed JWT refresh token.
    Returns a tuple of (token_string, jti, expires_at_datetime).
    """
    now = datetime.now(UTC)
    expire = now + (
        expires_delta
        if expires_delta is not None
        else timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    )
    token_jti = str(uuid.uuid4())
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "type": "refresh",
        "jti": token_jti,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    encoded_jwt: str = jwt.encode(
        payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM
    )
    return encoded_jwt, token_jti, expire


def decode_token(
    token: str, expected_type: str | None = None
) -> dict[str, Any]:
    """
    Decodes and validates a JWT token.
    Enforces signature validity, expiration, and token type.
    """
    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except jwt.ExpiredSignatureError:
        raise AuthenticationError(
            message="Token has expired",
            code="AUTH_TOKEN_EXPIRED",
        ) from None
    except jwt.InvalidTokenError:
        raise AuthenticationError(
            message="Invalid token format or signature",
            code="AUTH_INVALID_TOKEN",
        ) from None

    if expected_type and payload.get("type") != expected_type:
        received_type = payload.get("type")
        raise AuthenticationError(
            message=(
                f"Invalid token type: expected {expected_type}, "
                f"received {received_type}"
            ),
            code="AUTH_INVALID_TOKEN_TYPE",
        )

    if not payload.get("sub"):
        raise AuthenticationError(
            message="Token payload is missing subject identifier",
            code="AUTH_INVALID_TOKEN",
        )

    return payload
