import hashlib
import hmac
import json
import secrets
from datetime import UTC, datetime

from app.core.config import settings
from app.core.errors import (
    OTPInvalidError,
    OTPRateLimitedError,
)
from app.core.redis import redis_client


def _hash_otp(code: str) -> str:
    """Computes SHA-256 digest of an OTP string."""
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


class OTPService:
    """Manages Redis-backed cryptographic OTP lifecycle."""

    @staticmethod
    async def request_otp(
        phone: str, purpose: str = "AUTH", ip_address: str | None = None
    ) -> tuple[str, int]:
        """
        Generates and stores a secure OTP in Redis.
        Enforces resend cooldown and hourly rate limiting.
        Returns tuple of (raw_otp_for_delivery, expires_in_seconds).
        """
        redis = redis_client.client
        normalized_phone = phone.strip()

        # 1. Enforce Resend Cooldown
        cooldown_key = f"otp_cooldown:{purpose}:{normalized_phone}"
        if await redis.get(cooldown_key):
            ttl = await redis.ttl(cooldown_key)
            raise OTPRateLimitedError(
                message=f"Please wait {ttl} seconds before requesting a new OTP.",
                details={"retry_after_seconds": max(1, ttl)},
            )

        # 2. Enforce Hourly Rate Limit per phone
        rate_key = f"ratelimit:otp_request:{purpose}:{normalized_phone}"
        request_count = await redis.incr(rate_key)
        if request_count == 1:
            await redis.expire(rate_key, settings.RATE_LIMIT_OTP_WINDOW_SECONDS)
        elif request_count > settings.RATE_LIMIT_OTP_MAX_REQUESTS:
            ttl = await redis.ttl(rate_key)
            raise OTPRateLimitedError(
                message="Too many OTP requests. Please try again later.",
                details={"retry_after_seconds": max(1, ttl)},
            )

        # 3. Generate Cryptographically Secure OTP
        max_val = 10**settings.OTP_LENGTH
        otp_int = secrets.randbelow(max_val)
        raw_otp = f"{otp_int:0{settings.OTP_LENGTH}d}"
        otp_hash = _hash_otp(raw_otp)

        # 4. Store Hash & Metadata in Redis
        otp_data = {
            "otp_hash": otp_hash,
            "purpose": purpose,
            "attempts": 0,
            "max_attempts": settings.OTP_MAX_ATTEMPTS,
            "created_at": datetime.now(UTC).isoformat(),
        }
        storage_key = f"otp:{purpose}:{normalized_phone}"
        await redis.set(
            storage_key, json.dumps(otp_data), ex=settings.OTP_EXPIRE_SECONDS
        )

        # 5. Set Resend Cooldown
        await redis.set(
            cooldown_key, "1", ex=settings.OTP_RESEND_COOLDOWN_SECONDS
        )

        # In dev/testing, store plain OTP in test key for automated assertions
        if settings.DEBUG or settings.APP_ENV in ("development", "testing"):
            test_key = f"otp_test_val:{purpose}:{normalized_phone}"
            await redis.set(test_key, raw_otp, ex=settings.OTP_EXPIRE_SECONDS)

        return raw_otp, settings.OTP_EXPIRE_SECONDS

    @staticmethod
    async def verify_otp(
        phone: str, code: str, purpose: str = "AUTH"
    ) -> bool:
        """
        Verifies an OTP against the stored SHA-256 hash using constant-time comparison.
        Enforces maximum attempt bounds and single-use invalidation.
        """
        redis = redis_client.client
        normalized_phone = phone.strip()
        storage_key = f"otp:{purpose}:{normalized_phone}"

        raw_data = await redis.get(storage_key)
        if not raw_data:
            raise OTPInvalidError(
                message="OTP has expired or does not exist. Please request a new one."
            )

        try:
            data = json.loads(raw_data)
        except Exception:
            await redis.delete(storage_key)
            raise OTPInvalidError(message="Corrupted OTP session.") from None

        stored_hash = data.get("otp_hash", "")
        attempts = int(data.get("attempts", 0)) + 1
        max_attempts = int(data.get("max_attempts", settings.OTP_MAX_ATTEMPTS))

        input_hash = _hash_otp(code.strip())
        is_match = hmac.compare_digest(stored_hash, input_hash)

        if is_match:
            # Single-use: instantly invalidate OTP upon successful verification
            await redis.delete(storage_key)
            test_key = f"otp_test_val:{purpose}:{normalized_phone}"
            await redis.delete(test_key)
            return True

        # Incorrect attempt
        if attempts >= max_attempts:
            # Exceeded maximum verification attempts: invalidate completely
            await redis.delete(storage_key)
            test_key = f"otp_test_val:{purpose}:{normalized_phone}"
            await redis.delete(test_key)
            raise OTPInvalidError(
                message=(
                    "Maximum verification attempts exceeded. Please request a new OTP."
                ),
                code="AUTH_OTP_MAX_ATTEMPTS_EXCEEDED",
                details={"attempts": attempts, "max_attempts": max_attempts},
            )

        # Update remaining attempts with remaining TTL
        data["attempts"] = attempts
        ttl = await redis.ttl(storage_key)
        if ttl > 0:
            await redis.set(storage_key, json.dumps(data), ex=ttl)

        remaining = max_attempts - attempts
        raise OTPInvalidError(
            message=f"Incorrect OTP code. {remaining} attempt(s) remaining.",
            code="AUTH_OTP_INVALID",
            details={"attempts": attempts, "remaining_attempts": remaining},
        )

    @staticmethod
    async def get_test_otp(phone: str, purpose: str = "AUTH") -> str | None:
        """Retrieves raw OTP for test harness execution in test environments."""
        if not (settings.DEBUG or settings.APP_ENV in ("development", "testing")):
            return None
        redis = redis_client.client
        test_key = f"otp_test_val:{purpose}:{phone.strip()}"
        val: str | None = await redis.get(test_key)
        return val
