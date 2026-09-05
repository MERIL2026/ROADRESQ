from typing import Any

from fastapi import Request, status
from fastapi.responses import JSONResponse


class AppError(Exception):
    """Base application exception."""

    def __init__(
        self,
        message: str,
        code: str = "INTERNAL_SERVER_ERROR",
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}


class NotFoundError(AppError):
    def __init__(
        self,
        message: str = "Requested resource was not found",
        code: str = "RESOURCE_NOT_FOUND",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            code=code,
            status_code=status.HTTP_404_NOT_FOUND,
            details=details,
        )


class ConflictError(AppError):
    def __init__(
        self,
        message: str = "Conflict with current resource state",
        code: str = "STATE_CONFLICT",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            code=code,
            status_code=status.HTTP_409_CONFLICT,
            details=details,
        )


class ValidationError(AppError):
    def __init__(
        self,
        message: str = "Validation failed for the request",
        code: str = "VALIDATION_ERROR",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            code=code,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            details=details,
        )


class AuthenticationError(AppError):
    def __init__(
        self,
        message: str = "Invalid credentials or authentication token",
        code: str = "AUTH_INVALID_CREDENTIALS",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            code=code,
            status_code=status.HTTP_401_UNAUTHORIZED,
            details=details,
        )


class ForbiddenError(AppError):
    def __init__(
        self,
        message: str = "Operation not permitted for current user or role",
        code: str = "FORBIDDEN",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            code=code,
            status_code=status.HTTP_403_FORBIDDEN,
            details=details,
        )


class RateLimitError(AppError):
    def __init__(
        self,
        message: str = "Request quota exceeded. Please try again later.",
        code: str = "RATE_LIMITED",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            code=code,
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            details=details,
        )


class OTPInvalidError(AppError):
    def __init__(
        self,
        message: str = "Invalid or expired OTP code",
        code: str = "AUTH_OTP_INVALID",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            code=code,
            status_code=status.HTTP_400_BAD_REQUEST,
            details=details,
        )


class OTPRateLimitedError(AppError):
    def __init__(
        self,
        message: str = (
            "OTP request limit reached. Please wait before requesting another code."
        ),
        code: str = "AUTH_OTP_RATE_LIMITED",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            code=code,
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            details=details,
        )


async def app_exception_handler(request: Request, exc: AppError) -> JSONResponse:
    """Formats AppError into standard API error envelope."""
    request_id = getattr(request.state, "request_id", "unknown")
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
                "request_id": request_id,
            }
        },
    )


async def validation_exception_handler(
    request: Request, exc: Any
) -> JSONResponse:
    """Formats FastAPI/Pydantic validation errors into standard API error envelope."""
    request_id = getattr(request.state, "request_id", "unknown")
    errors = []
    if hasattr(exc, "errors"):
        for err in exc.errors():
            loc = " -> ".join(str(item) for item in err.get("loc", []))
            errors.append(
                {"field": loc, "message": err.get("msg", "Validation error")}
            )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Input validation failed",
                "details": {"validation_errors": errors},
                "request_id": request_id,
            }
        },
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catches unhandled exceptions and hides internal stack traces."""
    request_id = getattr(request.state, "request_id", "unknown")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "An unexpected error occurred. Please contact support.",
                "details": {},
                "request_id": request_id,
            }
        },
    )

