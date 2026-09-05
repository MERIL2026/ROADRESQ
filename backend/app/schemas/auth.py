import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.enums import UserRole


class UserRegisterRequest(BaseModel):
    """User account registration payload."""

    phone: str = Field(
        ..., min_length=10, max_length=20, description="E.164 phone number"
    )
    first_name: str = Field(
        ..., min_length=1, max_length=80, description="User given name"
    )
    last_name: str | None = Field(
        default=None, max_length=80, description="User family name"
    )
    email: EmailStr | None = Field(
        default=None, description="Optional contact email address"
    )
    password: str = Field(
        ..., min_length=8, max_length=128, description="Plaintext password"
    )
    role: UserRole = Field(
        default=UserRole.CUSTOMER,
        description="Platform role (CUSTOMER or PROVIDER)",
    )


class UserLoginRequest(BaseModel):
    """Credential login payload."""

    phone_or_email: str = Field(
        ..., min_length=3, max_length=255, description="Registered phone or email"
    )
    password: str = Field(
        ..., min_length=1, max_length=128, description="Account password"
    )


class UserResponse(BaseModel):
    """Safe user profile response representation (never exposes password hash)."""

    id: uuid.UUID
    role: str
    first_name: str
    last_name: str | None
    phone: str
    email: str | None
    status: str
    last_login_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TokenResponse(BaseModel):
    """JWT access + refresh token bundle with authenticated user metadata."""

    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int
    user: UserResponse


class TokenRefreshRequest(BaseModel):
    """Refresh token exchange request."""

    refresh_token: str = Field(
        ..., min_length=10, description="Active JWT refresh token"
    )


class TokenRefreshResponse(BaseModel):
    """Rotated access and refresh token pair."""

    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int


class OTPRequest(BaseModel):
    """Phone OTP generation request."""

    phone: str = Field(
        ..., min_length=10, max_length=20, description="Target mobile phone number"
    )
    purpose: str = Field(
        default="LOGIN",
        max_length=30,
        description="OTP scope: LOGIN, REGISTER, VERIFICATION",
    )


class OTPRequestResponse(BaseModel):
    """OTP generation confirmation."""

    message: str
    expires_in_seconds: int
    phone: str


class OTPVerifyRequest(BaseModel):
    """OTP verification payload."""

    phone: str = Field(
        ..., min_length=10, max_length=20, description="Mobile phone number"
    )
    code: str = Field(
        ..., min_length=4, max_length=8, description="Received numeric OTP code"
    )
    purpose: str = Field(
        default="LOGIN", max_length=30, description="OTP scope"
    )


class OTPVerifyResponse(BaseModel):
    """OTP verification outcome."""

    verified: bool
    message: str
    tokens: TokenResponse | None = None


class LogoutRequest(BaseModel):
    """Session invalidation request."""

    refresh_token: str | None = Field(
        default=None, description="Optional refresh token to invalidate"
    )


class MessageResponse(BaseModel):
    """Standard operation message response."""

    message: str
