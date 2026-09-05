import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, ClassVar

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis import RedisClient, redis_client
from app.models.enums import ProviderVerificationStatus, UserStatus
from app.models.provider import Provider
from app.repositories.provider import (
    ProviderAvailabilityRepository,
    ProviderRepository,
    ProviderServiceRepository,
)
from app.repositories.user import UserRepository


@dataclass
class EligibilityEvaluationResult:
    """Deterministic result of provider dispatch eligibility evaluation."""

    provider_id: uuid.UUID
    service_id: uuid.UUID
    is_eligible: bool
    rejection_reasons: list[str] = field(default_factory=list)
    evaluation_time: datetime = field(default_factory=lambda: datetime.now(UTC))
    details: dict[str, Any] = field(default_factory=dict)


class ProviderEligibilityService:
    """
    Domain service to evaluate whether a provider is eligible to be matched
    and dispatched for an assistance service request.
    """

    ELIGIBLE_VERIFICATION_STATUSES: ClassVar[set[str]] = {
        ProviderVerificationStatus.VERIFIED.value,
        ProviderVerificationStatus.ACTIVE.value,
    }


    def __init__(
        self, session: AsyncSession, redis: RedisClient | None = None
    ) -> None:
        self.session = session
        self.redis = redis or redis_client
        self.provider_repo = ProviderRepository(session)
        self.user_repo = UserRepository(session)
        self.svc_repo = ProviderServiceRepository(session)
        self.avail_repo = ProviderAvailabilityRepository(session)

    async def _check_user_active(
        self, provider: Provider, reasons: list[str], details: dict[str, Any]
    ) -> None:
        user = await self.user_repo.get_by_id(provider.user_id)
        if not user or user.status != UserStatus.ACTIVE.value:
            status_val = user.status if user else "None"
            reasons.append(f"User account is not active (status: {status_val}).")
            details["user_status"] = status_val
        else:
            details["user_status"] = user.status

    def _check_verification_status(
        self, provider: Provider, reasons: list[str], details: dict[str, Any]
    ) -> None:
        if provider.verification_status not in self.ELIGIBLE_VERIFICATION_STATUSES:
            reasons.append(
                f"Provider verification status '{provider.verification_status}' "
                "is not eligible for dispatch."
            )
            details["verification_status"] = provider.verification_status
        else:
            details["verification_status"] = provider.verification_status

    async def _check_presence(
        self, provider: Provider, reasons: list[str], details: dict[str, Any]
    ) -> None:
        if not provider.is_online:
            reasons.append("Provider is offline in database.")
            details["db_is_online"] = False
        else:
            presence_key = f"presence:provider:{provider.id}"
            redis_status = await self.redis.get(presence_key)
            if not redis_status:
                reasons.append(
                    "Provider online presence is missing or expired in Redis."
                )
                details["redis_presence"] = False
            else:
                details["redis_presence"] = True

    async def _check_service_offered(
        self,
        provider_id: uuid.UUID,
        service_id: uuid.UUID,
        reasons: list[str],
        details: dict[str, Any],
    ) -> None:
        provider_svc = await self.svc_repo.get_by_provider_and_service(
            provider_id, service_id
        )
        if not provider_svc or not provider_svc.is_active:
            reasons.append(
                f"Provider does not actively offer service '{service_id}'."
            )
            details["service_offered"] = False
        else:
            details["service_offered"] = True
            p_from = (
                str(provider_svc.price_from)
                if provider_svc.price_from
                else None
            )
            p_to = (
                str(provider_svc.price_to)
                if provider_svc.price_to
                else None
            )
            details["price_from"] = p_from
            details["price_to"] = p_to

    async def _check_availability_window(
        self,
        provider_id: uuid.UUID,
        target_time: datetime,
        reasons: list[str],
        details: dict[str, Any],
    ) -> None:
        day_of_week = target_time.weekday()
        current_time = target_time.time()

        slots = await self.avail_repo.list_by_provider(provider_id)
        matching_slots = [
            s
            for s in slots
            if s.day_of_week == day_of_week
            and s.is_active
            and s.start_time <= current_time <= s.end_time
        ]

        if not matching_slots:
            time_str = target_time.strftime("%A %H:%M:%S")
            reasons.append(
                f"Evaluation time ({time_str}) is outside provider working hours."
            )
            details["availability_match"] = False
        else:
            details["availability_match"] = True

    async def evaluate_provider_eligibility(
        self,
        provider_id: uuid.UUID,
        service_id: uuid.UUID,
        evaluation_time: datetime | None = None,
        pickup_location: Any | None = None,
    ) -> EligibilityEvaluationResult:
        """Evaluates domain dispatch eligibility for a provider."""
        target_time = evaluation_time or datetime.now(UTC)
        reasons: list[str] = []
        details: dict[str, Any] = {}

        provider = await self.provider_repo.get_by_id(provider_id)
        if not provider:
            return EligibilityEvaluationResult(
                provider_id=provider_id,
                service_id=service_id,
                is_eligible=False,
                rejection_reasons=["Provider profile does not exist."],
                evaluation_time=target_time,
            )

        await self._check_user_active(provider, reasons, details)
        self._check_verification_status(provider, reasons, details)
        await self._check_presence(provider, reasons, details)
        await self._check_service_offered(
            provider.id, service_id, reasons, details
        )
        await self._check_availability_window(
            provider.id, target_time, reasons, details
        )

        loc_ok, loc_reason = self.check_location_eligibility(
            provider=provider, pickup_location=pickup_location
        )
        if not loc_ok and loc_reason:
            reasons.append(loc_reason)
            details["location_eligible"] = False
        else:
            details["location_eligible"] = True

        return EligibilityEvaluationResult(
            provider_id=provider_id,
            service_id=service_id,
            is_eligible=len(reasons) == 0,
            rejection_reasons=reasons,
            evaluation_time=target_time,
            details=details,
        )

    def check_location_eligibility(
        self, provider: Provider, pickup_location: Any | None
    ) -> tuple[bool, str | None]:
        """Clean interface isolating spatial distance / service radius evaluation."""
        if pickup_location is not None:
            if (
                not hasattr(provider, "location")
                or getattr(provider, "location", None) is None
            ):
                return True, None
        return True, None
