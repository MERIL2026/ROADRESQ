import json
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)
from app.core.geospatial import haversine_distance_km
from app.core.redis import RedisClient, redis_client
from app.models.booking import Booking
from app.models.enums import (
    AuditAction,
    BookingStatus,
    ProviderVerificationStatus,
)
from app.models.provider import Provider
from app.repositories.booking import BookingRepository
from app.repositories.provider import ProviderRepository
from app.schemas.dispatch import (
    DispatchAcceptResponse,
    DispatchOfferListResponse,
    DispatchOfferResponse,
    ProviderLocationResponse,
)
from app.services.audit_service import record_audit_event
from app.services.eligibility_service import ProviderEligibilityService


class DispatchService:
    """Core Dispatch & Matching Engine for pairing Roadside Assistance requests with Providers."""

    DEFAULT_OFFER_TTL_SECONDS: int = 45

    def __init__(
        self, session: AsyncSession, redis: RedisClient | None = None
    ) -> None:
        self.session = session
        self.redis = redis or redis_client
        self.booking_repo = BookingRepository(session)
        self.provider_repo = ProviderRepository(session)
        self.eligibility_service = ProviderEligibilityService(
            session=session, redis=self.redis
        )

    async def update_provider_location(
        self,
        provider_id: uuid.UUID,
        latitude: float,
        longitude: float,
    ) -> ProviderLocationResponse:
        """Stores provider live GPS coordinates into Redis Geospatial index."""
        if not (-90.0 <= latitude <= 90.0) or not (-180.0 <= longitude <= 180.0):
            raise ValidationError(
                message="Invalid GPS coordinates out of bounds.",
                code="INVALID_COORDINATES",
            )

        provider = await self.provider_repo.get_by_id(provider_id)
        if not provider:
            raise NotFoundError(
                message="Provider not found.",
                code="PROVIDER_NOT_FOUND",
            )

        # 1. Update Geospatial Index
        await self.redis.geoadd(
            key="geo:providers",
            longitude=longitude,
            latitude=latitude,
            member=str(provider.id),
        )

        # 2. Store direct coordinate cache
        now = datetime.now(UTC)
        payload = f"{latitude}:{longitude}:{now.isoformat()}"
        await self.redis.set(
            key=f"provider:location:{provider.id}",
            value=payload,
            expire_seconds=86400,
        )

        return ProviderLocationResponse(
            provider_id=provider.id,
            latitude=latitude,
            longitude=longitude,
            updated_at=now,
        )

    async def get_provider_location(
        self, provider_id: uuid.UUID
    ) -> tuple[float, float] | None:
        """Retrieves cached provider GPS coordinates from Redis."""
        data = await self.redis.get(f"provider:location:{provider_id}")
        if data:
            parts = data.split(":")
            if len(parts) >= 2:
                try:
                    return float(parts[0]), float(parts[1])
                except ValueError:
                    pass
        return None

    async def initiate_dispatch(
        self,
        booking_id: uuid.UUID,
    ) -> Booking:
        """
        Discovers eligible candidates, computes distance rankings, and creates a 45s dispatch offer.
        """
        booking = await self.booking_repo.get_by_id_with_relations(booking_id)
        if not booking:
            raise NotFoundError(
                message="Booking not found.",
                code="BOOKING_NOT_FOUND",
            )

        # Extract customer pickup location
        c_lat, c_lon = 0.0, 0.0
        for loc in booking.locations:
            if loc.location_type in ("PICKUP", "SERVICE"):
                c_lat, c_lon = BookingRepository.extract_coordinates(loc.location)
                break

        # Check declined providers set in Redis
        declined_key = f"dispatch:declined:{booking.id}"
        declined_ids = await self.redis.smembers(declined_key)

        # Find all online/verified providers
        stmt = (
            select(Provider)
            .where(
                Provider.verification_status.in_([
                    ProviderVerificationStatus.VERIFIED.value,
                    ProviderVerificationStatus.ACTIVE.value,
                ]),
                Provider.is_online.is_(True),
            )
        )
        result = await self.session.execute(stmt)
        all_online_providers = result.scalars().all()

        candidates: list[tuple[Provider, float]] = []

        for p in all_online_providers:
            # Skip if provider already declined this booking
            if str(p.id) in declined_ids:
                continue

            # Check domain eligibility (account active, services offered, working hours)
            eligibility = await self.eligibility_service.evaluate_provider_eligibility(
                provider_id=p.id,
                service_id=booking.service_id,
                evaluation_time=datetime.now(UTC),
            )
            if not eligibility.is_eligible:
                continue

            # Calculate distance
            p_coords = await self.get_provider_location(p.id)
            if p_coords:
                dist = haversine_distance_km(c_lat, c_lon, p_coords[0], p_coords[1])
            else:
                # Default distance estimation if GPS ping pending
                dist = 5.0

            # Radius filter
            if dist <= float(p.service_radius_km):
                candidates.append((p, dist))

        # Rank candidates: 1st by shortest distance, 2nd by highest rating
        candidates.sort(key=lambda item: (item[1], -float(item[0].rating_avg)))

        if not candidates:
            # No candidate available -> transition to EXPIRED
            booking.status = BookingStatus.EXPIRED.value
            await self.booking_repo.add_status_history(
                booking_id=booking.id,
                status=BookingStatus.EXPIRED.value,
                actor_user_id=None,
                actor_role="SYSTEM",
                notes="No eligible providers available in dispatch radius",
            )
            await self.session.flush()
            return booking

        # Select top candidate and create temporary offer
        best_provider, distance_km = candidates[0]
        now = datetime.now(UTC)
        expires_at = now + timedelta(seconds=self.DEFAULT_OFFER_TTL_SECONDS)

        offer_payload = {
            "booking_id": str(booking.id),
            "provider_id": str(best_provider.id),
            "distance_km": distance_km,
            "created_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
        }

        # Store offer in Redis
        offer_key = f"dispatch:offer:{booking.id}"
        await self.redis.set(
            key=offer_key,
            value=json.dumps(offer_payload),
            expire_seconds=self.DEFAULT_OFFER_TTL_SECONDS,
        )

        # Store pointer for provider's active offer lookup
        provider_offer_key = f"provider:active_offer:{best_provider.id}"
        await self.redis.set(
            key=provider_offer_key,
            value=str(booking.id),
            expire_seconds=self.DEFAULT_OFFER_TTL_SECONDS,
        )

        booking.status = BookingStatus.PROVIDER_ASSIGNED.value
        await self.booking_repo.add_status_history(
            booking_id=booking.id,
            status=BookingStatus.PROVIDER_ASSIGNED.value,
            actor_user_id=None,
            actor_role="SYSTEM",
            notes=f"Offered to provider {best_provider.business_name} ({distance_km} km away)",
        )
        await self.session.flush()

        return booking

    async def get_provider_active_offers(
        self, provider_id: uuid.UUID
    ) -> DispatchOfferListResponse:
        """Retrieves active incoming dispatch offers for a specific provider."""
        booking_id_str = await self.redis.get(f"provider:active_offer:{provider_id}")
        if not booking_id_str:
            return DispatchOfferListResponse(offers=[], total=0)

        offer_data_str = await self.redis.get(f"dispatch:offer:{booking_id_str}")
        if not offer_data_str:
            return DispatchOfferListResponse(offers=[], total=0)

        try:
            offer_dict = json.loads(offer_data_str)
        except Exception:
            return DispatchOfferListResponse(offers=[], total=0)

        if offer_dict.get("provider_id") != str(provider_id):
            return DispatchOfferListResponse(offers=[], total=0)

        booking_uuid = uuid.UUID(booking_id_str)
        booking = await self.booking_repo.get_by_id_with_relations(booking_uuid)
        if not booking or booking.status not in (
            BookingStatus.REQUESTED.value,
            BookingStatus.SEARCHING.value,
            BookingStatus.PROVIDER_ASSIGNED.value,
        ):
            return DispatchOfferListResponse(offers=[], total=0)

        p_lat, p_lon, p_address = 0.0, 0.0, None
        for loc in booking.locations:
            if loc.location_type in ("PICKUP", "SERVICE"):
                p_lat, p_lon = BookingRepository.extract_coordinates(loc.location)
                p_address = loc.address_text
                break

        cust_name = (
            f"{booking.customer.first_name} {booking.customer.last_name or ''}".strip()
            if booking.customer
            else None
        )
        svc_name = booking.service.name if booking.service else "Roadside Assistance"
        svc_cat = booking.service.category if booking.service else "GENERAL"
        est_price = booking.service.base_price if booking.service else None

        expires_at = datetime.fromisoformat(offer_dict["expires_at"])
        remaining_ttl = max(0, int((expires_at - datetime.now(UTC)).total_seconds()))

        offer_response = DispatchOfferResponse(
            booking_id=booking.id,
            booking_number=booking.booking_number,
            service_id=booking.service_id,
            service_name=svc_name,
            service_category=svc_cat,
            customer_name=cust_name,
            problem_description=booking.problem_description,
            pickup_address=p_address,
            pickup_latitude=p_lat,
            pickup_longitude=p_lon,
            distance_km=offer_dict.get("distance_km"),
            estimated_earnings=est_price,
            expires_at=expires_at,
            ttl_seconds=remaining_ttl,
        )

        return DispatchOfferListResponse(offers=[offer_response], total=1)

    async def accept_dispatch_offer(
        self,
        booking_id: uuid.UUID,
        user_id: uuid.UUID,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> DispatchAcceptResponse:
        """
        Atomically accepts a dispatch offer for the authenticated provider.
        """
        provider = await self.provider_repo.get_by_user_id(user_id)
        if not provider:
            raise NotFoundError(
                message="Provider profile not found for user.",
                code="PROVIDER_NOT_FOUND",
            )

        offer_key = f"dispatch:offer:{booking_id}"
        offer_str = await self.redis.get(offer_key)
        if not offer_str:
            raise ConflictError(
                message="This dispatch offer has expired or is no longer available.",
                code="DISPATCH_OFFER_EXPIRED",
            )

        try:
            offer_dict = json.loads(offer_str)
            if offer_dict.get("provider_id") != str(provider.id):
                raise ForbiddenError(
                    message="This dispatch offer was not issued to your provider account.",
                    code="FORBIDDEN",
                )
        except (ValueError, KeyError):
            pass

        # Atomic PostgreSQL update
        success = await self.booking_repo.assign_provider_atomic(
            booking_id=booking_id,
            provider_id=provider.id,
        )

        if not success:
            raise ConflictError(
                message="Booking is no longer available (already assigned or cancelled).",
                code="BOOKING_ALREADY_ASSIGNED",
            )

        # Cleanup Redis Offer
        await self.redis.delete(offer_key)
        await self.redis.delete(f"provider:active_offer:{provider.id}")

        # Add status history
        await self.booking_repo.add_status_history(
            booking_id=booking_id,
            status=BookingStatus.ACCEPTED.value,
            actor_user_id=user_id,
            actor_role="PROVIDER",
            notes=f"Accepted by {provider.business_name}",
        )

        await record_audit_event(
            session=self.session,
            action=AuditAction.STATUS_CHANGE.value,
            entity_type="Booking",
            entity_id=booking_id,
            actor_user_id=user_id,
            new_data={
                "status": BookingStatus.ACCEPTED.value,
                "provider_id": str(provider.id),
            },
            ip_address=ip_address,
            user_agent=user_agent,
        )

        booking = await self.booking_repo.get_by_id(booking_id)
        b_num = booking.booking_number if booking else str(booking_id)

        return DispatchAcceptResponse(
            booking_id=booking_id,
            booking_number=b_num,
            status=BookingStatus.ACCEPTED.value,
            message="Dispatch offer successfully accepted. You are now assigned to this booking.",
        )

    async def reject_dispatch_offer(
        self,
        booking_id: uuid.UUID,
        user_id: uuid.UUID,
        reason: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        """
        Rejects a dispatch offer and immediately advances dispatch to the next candidate.
        """
        provider = await self.provider_repo.get_by_user_id(user_id)
        if not provider:
            raise NotFoundError(
                message="Provider profile not found for user.",
                code="PROVIDER_NOT_FOUND",
            )

        # Add provider to declined set in Redis with 1-hour TTL
        declined_key = f"dispatch:declined:{booking_id}"
        await self.redis.sadd(declined_key, str(provider.id))
        await self.redis.expire(declined_key, 3600)

        # Remove active offer
        await self.redis.delete(f"dispatch:offer:{booking_id}")
        await self.redis.delete(f"provider:active_offer:{provider.id}")

        # Record decline history
        await self.booking_repo.add_status_history(
            booking_id=booking_id,
            status=BookingStatus.SEARCHING.value,
            actor_user_id=user_id,
            actor_role="PROVIDER",
            notes=f"Offer declined by {provider.business_name}. Reason: {reason or 'Not specified'}",
        )

        await record_audit_event(
            session=self.session,
            action=AuditAction.UPDATE.value,
            entity_type="BookingDispatch",
            entity_id=booking_id,
            actor_user_id=user_id,
            new_data={
                "action": "OFFER_DECLINED",
                "provider_id": str(provider.id),
                "reason": reason,
            },
            ip_address=ip_address,
            user_agent=user_agent,
        )

        # Advance dispatch to next candidate
        await self.initiate_dispatch(booking_id=booking_id)
