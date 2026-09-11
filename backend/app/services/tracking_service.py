import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import (
    ForbiddenError,
    NotFoundError,
    ValidationError,
)
from app.core.geospatial import haversine_distance_km
from app.core.otp import OTPService
from app.core.redis import RedisClient, redis_client
from app.core.websocket import ws_manager
from app.models.enums import AuditAction, BookingStatus, JobStatus, UserRole
from app.repositories.booking import BookingRepository
from app.repositories.job import JobRepository
from app.repositories.provider import ProviderRepository
from app.repositories.tracking import TrackingRepository
from app.schemas.job import JobCardResponse
from app.schemas.tracking import (
    ArrivalOTPGenerateResponse,
    ArrivalVerifyRequest,
    BookingLiveTrackingResponse,
    LocationCoordinate,
    ProviderLocationPingRequest,
    ProviderLocationResponse,
)
from app.services.audit_service import record_audit_event


class TrackingService:
    """Domain service managing provider GPS tracking, live map views, and Arrival OTP."""

    STALE_LOCATION_THRESHOLD_SECONDS = 300  # 5 minutes

    def __init__(self, session: AsyncSession, redis: RedisClient | None = None) -> None:
        self.session = session
        self.redis = redis or redis_client
        self.tracking_repo = TrackingRepository(session)
        self.booking_repo = BookingRepository(session)
        self.provider_repo = ProviderRepository(session)
        self.job_repo = JobRepository(session)

    async def update_provider_location(
        self,
        user_id: uuid.UUID,
        data: ProviderLocationPingRequest,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> ProviderLocationResponse:
        """
        Ingests provider GPS coordinates into Redis for real-time dispatch & active tracking.
        If provider is currently EN_ROUTE (ON_THE_WAY) on an active booking, appends to PostGIS history.
        """
        provider = await self.provider_repo.get_by_user_id(user_id)
        if not provider:
            raise NotFoundError(
                message="Provider profile not found.",
                code="PROVIDER_NOT_FOUND",
            )

        now = datetime.now(UTC)
        provider_id_str = str(provider.id)

        # 1. Update Ephemeral Redis Presence & Geo Index
        geo_key = "provider:locations:live"
        await self.redis.geoadd(
            key=geo_key,
            longitude=data.longitude,
            latitude=data.latitude,
            member=provider_id_str,
        )

        point_data = {
            "provider_id": provider_id_str,
            "latitude": data.latitude,
            "longitude": data.longitude,
            "accuracy_m": float(data.accuracy_m)
            if data.accuracy_m is not None
            else None,
            "heading": float(data.heading) if data.heading is not None else None,
            "speed_kmh": float(data.speed_kmh) if data.speed_kmh is not None else None,
            "recorded_at": now.isoformat(),
        }
        point_key = f"provider:location:point:{provider_id_str}"
        await self.redis.set(point_key, json.dumps(point_data), expire_seconds=600)

        # 2. Check for active assigned booking in ON_THE_WAY status
        active_bookings = await self.booking_repo.list_by_provider(
            provider_id=provider.id,
            status=BookingStatus.ON_THE_WAY.value,
            limit=1,
        )

        if active_bookings:
            active_booking = active_bookings[0]
            # Persist historical telemetry record
            await self.tracking_repo.create_location_update(
                provider_id=provider.id,
                booking_id=active_booking.id,
                latitude=data.latitude,
                longitude=data.longitude,
                accuracy_m=data.accuracy_m,
                heading=data.heading,
                speed_kmh=data.speed_kmh,
                recorded_at=now,
            )

            # Compute real-time distance and ETA if booking has a pickup location
            distance_km: float | None = None
            eta_minutes: int | None = None
            if active_booking.locations:
                loc = active_booking.locations[0]
                # Extract coordinates from WKT geometry if present
                cust_lat, cust_lon = self._extract_point_coords(loc)
                if cust_lat is not None and cust_lon is not None:
                    distance_km = haversine_distance_km(
                        data.latitude, data.longitude, cust_lat, cust_lon
                    )
                    avg_speed = (
                        float(data.speed_kmh)
                        if data.speed_kmh and data.speed_kmh > 5
                        else 30.0
                    )
                    eta_minutes = max(1, round((distance_km / avg_speed) * 60))

            # Broadcast live WebSocket event to the booking channel
            loc_event_data = {
                "provider_id": provider_id_str,
                "latitude": data.latitude,
                "longitude": data.longitude,
                "heading": float(data.heading) if data.heading is not None else None,
                "speed_kmh": float(data.speed_kmh)
                if data.speed_kmh is not None
                else None,
                "accuracy_m": float(data.accuracy_m)
                if data.accuracy_m is not None
                else None,
                "recorded_at": now.isoformat(),
                "distance_km": distance_km,
                "eta_minutes": eta_minutes,
            }
            await ws_manager.broadcast_to_booking(
                booking_id=active_booking.id,
                event="provider.location.updated",
                data=loc_event_data,
            )

        return ProviderLocationResponse(
            provider_id=provider.id,
            latitude=data.latitude,
            longitude=data.longitude,
            recorded_at=now,
            accuracy_m=data.accuracy_m,
            heading=data.heading,
            speed_kmh=data.speed_kmh,
        )

    async def _resolve_provider_location(
        self, provider_id: uuid.UUID, booking_id: uuid.UUID, now: datetime
    ) -> tuple[ProviderLocationResponse | None, bool]:
        """Fetches provider live location from Redis or PostgreSQL fallback with staleness check."""
        point_key = f"provider:location:point:{provider_id}"
        raw_point = await self.redis.get(point_key)
        if raw_point:
            try:
                p_data = json.loads(raw_point)
                recorded_dt = datetime.fromisoformat(p_data["recorded_at"])
                is_stale = (
                    now - recorded_dt
                ).total_seconds() > self.STALE_LOCATION_THRESHOLD_SECONDS
                return ProviderLocationResponse(
                    provider_id=provider_id,
                    latitude=p_data["latitude"],
                    longitude=p_data["longitude"],
                    accuracy_m=Decimal(str(p_data["accuracy_m"]))
                    if p_data.get("accuracy_m") is not None
                    else None,
                    heading=Decimal(str(p_data["heading"]))
                    if p_data.get("heading") is not None
                    else None,
                    speed_kmh=Decimal(str(p_data["speed_kmh"]))
                    if p_data.get("speed_kmh") is not None
                    else None,
                    recorded_at=recorded_dt,
                ), is_stale
            except Exception:
                pass

        latest_db = await self.tracking_repo.get_latest_location_by_booking(booking_id)
        if latest_db:
            db_lat, db_lon = self._extract_point_coords(latest_db)
            if db_lat is not None and db_lon is not None:
                is_stale = (
                    now - latest_db.recorded_at
                ).total_seconds() > self.STALE_LOCATION_THRESHOLD_SECONDS
                return ProviderLocationResponse(
                    provider_id=provider_id,
                    latitude=db_lat,
                    longitude=db_lon,
                    accuracy_m=latest_db.accuracy_m,
                    heading=latest_db.heading,
                    speed_kmh=latest_db.speed_kmh,
                    recorded_at=latest_db.recorded_at,
                ), is_stale

        return None, False

    async def get_booking_live_tracking(
        self,
        booking_id: uuid.UUID,
        user_id: uuid.UUID,
        user_role: str,
    ) -> BookingLiveTrackingResponse:
        """
        Retrieves current live tracking status, provider position, distance, and ETA for a booking.
        Enforces strict object-level authorization (IDOR protection).
        """
        booking = await self.booking_repo.get_by_id(booking_id)
        if not booking:
            raise NotFoundError(
                message="Booking not found.",
                code="BOOKING_NOT_FOUND",
            )

        # IDOR Authorization
        if user_role == UserRole.CUSTOMER.value and booking.customer_id != user_id:
            raise ForbiddenError(
                message="You are not authorized to track this booking.",
                code="FORBIDDEN",
            )
        if user_role == UserRole.PROVIDER.value:
            provider = await self.provider_repo.get_by_user_id(user_id)
            if not provider or booking.provider_id != provider.id:
                raise ForbiddenError(
                    message="You are not authorized to view tracking for this booking.",
                    code="FORBIDDEN",
                )

        # Extract customer pickup location
        dest_coord: LocationCoordinate | None = None
        cust_lat: float | None = None
        cust_lon: float | None = None
        if booking.locations:
            loc = booking.locations[0]
            cust_lat, cust_lon = self._extract_point_coords(loc)
            if cust_lat is not None and cust_lon is not None:
                dest_coord = LocationCoordinate(latitude=cust_lat, longitude=cust_lon)

        if not booking.provider_id:
            return BookingLiveTrackingResponse(
                booking_id=booking.id,
                status=booking.status,
                destination_location=dest_coord,
            )

        now = datetime.now(UTC)
        prov_loc, is_stale = await self._resolve_provider_location(
            booking.provider_id, booking.id, now
        )

        distance_km: float | None = None
        eta_minutes: int | None = None
        if prov_loc and cust_lat is not None and cust_lon is not None:
            distance_km = haversine_distance_km(
                prov_loc.latitude, prov_loc.longitude, cust_lat, cust_lon
            )
            speed = (
                float(prov_loc.speed_kmh)
                if prov_loc.speed_kmh and prov_loc.speed_kmh > 5
                else 30.0
            )
            eta_minutes = max(1, round((distance_km / speed) * 60))

        return BookingLiveTrackingResponse(
            booking_id=booking.id,
            status=booking.status,
            provider_id=booking.provider_id,
            provider_location=prov_loc,
            destination_location=dest_coord,
            distance_km=distance_km,
            eta_minutes=eta_minutes,
            is_stale=is_stale,
            updated_at=prov_loc.recorded_at if prov_loc else None,
        )

    async def generate_arrival_otp(
        self,
        booking_id: uuid.UUID,
        user_id: uuid.UUID,
        user_role: str,
    ) -> ArrivalOTPGenerateResponse:
        """
        Generates/retrieves a 6-digit cryptographic Arrival OTP for the booking.
        Accessible only by the authenticated customer or administrative operator.
        """
        booking = await self.booking_repo.get_by_id(booking_id)
        if not booking:
            raise NotFoundError(
                message="Booking not found.",
                code="BOOKING_NOT_FOUND",
            )

        if user_role == UserRole.CUSTOMER.value and booking.customer_id != user_id:
            raise ForbiddenError(
                message="You are not authorized to view the arrival OTP for this booking.",
                code="FORBIDDEN",
            )

        valid_states = {
            BookingStatus.ON_THE_WAY.value,
            BookingStatus.ARRIVED.value,
            BookingStatus.ACCEPTED.value,
        }
        if booking.status not in valid_states:
            raise ValidationError(
                message=(
                    f"Arrival OTP cannot be requested for booking in '{booking.status}' status."
                ),
                code="INVALID_BOOKING_STATE",
            )

        raw_otp, expires_in = await OTPService.request_otp(
            phone=f"BOOKING_{booking_id}",
            purpose="ARRIVAL",
        )

        return ArrivalOTPGenerateResponse(
            booking_id=booking_id,
            otp=raw_otp
            if (settings.DEBUG or settings.APP_ENV in ("development", "testing"))
            else None,
            expires_in_seconds=expires_in,
            message="Arrival OTP generated successfully. Share this 6-digit code with your service provider upon arrival.",
        )

    async def verify_arrival(
        self,
        booking_id: uuid.UUID,
        user_id: uuid.UUID,
        data: ArrivalVerifyRequest,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> JobCardResponse:
        """
        Validates arrival OTP provided by customer to the arriving provider.
        Enforces optional proximity geofence and advances state to ARRIVED.
        Auto-initializes the JobCard in INSPECTION status.
        """
        booking = await self.booking_repo.get_by_id(booking_id)
        if not booking:
            raise NotFoundError(
                message="Booking not found.",
                code="BOOKING_NOT_FOUND",
            )

        provider = await self.provider_repo.get_by_user_id(user_id)
        if not provider or booking.provider_id != provider.id:
            raise ForbiddenError(
                message="You are not authorized to verify arrival for this booking.",
                code="FORBIDDEN",
            )

        if booking.status not in (
            BookingStatus.ON_THE_WAY.value,
            BookingStatus.ACCEPTED.value,
        ):
            if booking.status == BookingStatus.ARRIVED.value:
                job_card = await self.job_repo.get_by_booking_id(booking_id)
                if job_card:
                    return JobCardResponse.model_validate(job_card)
            raise ValidationError(
                message=f"Cannot mark arrival for booking in '{booking.status}' status.",
                code="INVALID_STATUS_TRANSITION",
            )

        # Proximity validation check if GPS coordinates are provided
        if (
            data.latitude is not None
            and data.longitude is not None
            and booking.locations
        ):
            cust_lat, cust_lon = self._extract_point_coords(booking.locations[0])
            if cust_lat is not None and cust_lon is not None:
                dist = haversine_distance_km(
                    data.latitude, data.longitude, cust_lat, cust_lon
                )
                # Allow up to 2.0 km radius buffer for GPS drift/urban canyons
                if dist > 2.0:
                    raise ValidationError(
                        message=f"Provider location is too far ({dist:.2f} km) from pickup location to verify arrival.",
                        code="ARRIVAL_PROXIMITY_FAILED",
                        details={"distance_km": dist, "max_allowed_km": 2.0},
                    )

        # Verify OTP
        is_valid = await OTPService.verify_otp(
            phone=f"BOOKING_{booking_id}",
            code=data.otp,
            purpose="ARRIVAL",
        )
        if not is_valid:
            raise ValidationError(
                message="Invalid or expired Arrival OTP.",
                code="ARRIVAL_OTP_INVALID",
            )

        # Transition Booking -> ARRIVED
        old_status = booking.status
        now = datetime.now(UTC)
        booking.status = BookingStatus.ARRIVED.value
        booking.arrived_at = now

        await self.booking_repo.add_status_history(
            booking_id=booking.id,
            status=BookingStatus.ARRIVED.value,
            actor_user_id=user_id,
            actor_role=UserRole.PROVIDER.value,
            notes="Provider arrived and verified customer Arrival OTP.",
        )

        # Initialize or retrieve JobCard
        job_card = await self.job_repo.get_by_booking_id(booking.id)
        if not job_card:
            job_card = await self.job_repo.create_job_card(
                booking_id=booking.id,
                provider_id=provider.id,
                mechanic_user_id=user_id,
                job_status=JobStatus.INSPECTION.value,
                started_at=now,
            )
        elif not job_card.started_at:
            job_card.started_at = now

        await self.session.flush()

        # Audit event
        await record_audit_event(
            session=self.session,
            action=AuditAction.STATUS_CHANGE.value,
            entity_type="Booking",
            entity_id=booking.id,
            actor_user_id=user_id,
            old_data={"status": old_status},
            new_data={
                "status": BookingStatus.ARRIVED.value,
                "job_card_id": str(job_card.id),
            },
            ip_address=ip_address,
            user_agent=user_agent,
        )

        # Broadcast events
        await ws_manager.broadcast_to_booking(
            booking_id=booking.id,
            event="booking.status.updated",
            data={"status": BookingStatus.ARRIVED.value, "booking_id": str(booking.id)},
        )
        await ws_manager.broadcast_to_booking(
            booking_id=booking.id,
            event="job.status.updated",
            data={
                "job_status": JobStatus.INSPECTION.value,
                "job_card_id": str(job_card.id),
            },
        )

        reloaded = await self.job_repo.get_by_id(job_card.id)
        return JobCardResponse.model_validate(reloaded or job_card)

    def _extract_point_coords(
        self, loc_obj: object
    ) -> tuple[float | None, float | None]:
        """Helper to extract latitude and longitude from GeoAlchemy2 Geography or WKT/object."""
        try:
            loc_val = getattr(loc_obj, "location", None)
            if loc_val is None:
                return None, None
            # If shapely/geoalchemy element or string
            loc_str = str(loc_val)
            if "POINT" in loc_str.upper():
                coords_str = (
                    loc_str.upper()
                    .replace("POINT", "")
                    .replace("(", "")
                    .replace(")", "")
                    .strip()
                )
                parts = coords_str.split()
                if len(parts) >= 2:
                    lon = float(parts[0])
                    lat = float(parts[1])
                    return lat, lon
        except Exception:
            pass
        return None, None
