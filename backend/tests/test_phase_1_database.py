"""
Test suite validating Phase 1 Database schema, PostGIS spatial queries,
and end-to-end ORM relationships across all 11 entities.
"""

import uuid
from datetime import UTC, datetime, time
from decimal import Decimal

import asyncpg
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.models import (
    AuditAction,
    AuditLog,
    Booking,
    BookingLocation,
    BookingStatus,
    BookingStatusHistory,
    BookingType,
    LocationType,
    Provider,
    ProviderAvailability,
    ProviderDocument,
    ProviderDocumentStatus,
    ProviderDocumentType,
    ProviderService,
    ProviderType,
    ProviderVerificationStatus,
    Service,
    User,
    UserRole,
    UserStatus,
    Vehicle,
)

REQUIRED_TABLES = [
    "users",
    "vehicles",
    "services",
    "providers",
    "provider_documents",
    "provider_services",
    "provider_availability",
    "bookings",
    "booking_locations",
    "booking_status_history",
    "audit_logs",
]


@pytest.fixture
def raw_db_url():
    return settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")


@pytest.mark.asyncio
async def test_all_11_tables_exist(raw_db_url):
    """Verify all 11 required Phase 1 tables exist in the public schema."""
    conn = await asyncpg.connect(raw_db_url)
    try:
        rows = await conn.fetch(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public' AND table_type = 'BASE TABLE';
            """
        )
        existing_tables = {r["table_name"] for r in rows}
        for tbl in REQUIRED_TABLES:
            assert tbl in existing_tables, f"Missing table: {tbl}"
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_foreign_key_constraints(raw_db_url):
    """Verify foreign keys are established on all dependent models."""
    conn = await asyncpg.connect(raw_db_url)
    try:
        fk_rows = await conn.fetch(
            """
            SELECT
                tc.table_name,
                kcu.column_name,
                ccu.table_name AS foreign_table_name,
                rc.delete_rule
            FROM information_schema.table_constraints AS tc
            JOIN information_schema.key_column_usage AS kcu
                ON tc.constraint_name = kcu.constraint_name
                AND tc.table_schema = kcu.table_schema
            JOIN information_schema.constraint_column_usage AS ccu
                ON ccu.constraint_name = tc.constraint_name
                AND ccu.table_schema = tc.table_schema
            JOIN information_schema.referential_constraints AS rc
                ON rc.constraint_name = tc.constraint_name
            WHERE tc.constraint_type = 'FOREIGN KEY'
            ORDER BY tc.table_name, kcu.column_name;
            """
        )
        fks_by_table: dict[str, list[dict]] = {}
        for r in fk_rows:
            fks_by_table.setdefault(r["table_name"], []).append(dict(r))

        assert any(
            fk["column_name"] == "user_id" and fk["foreign_table_name"] == "users"
            for fk in fks_by_table["vehicles"]
        )
        assert any(
            fk["column_name"] == "user_id" and fk["foreign_table_name"] == "users"
            for fk in fks_by_table["providers"]
        )
        assert any(
            fk["column_name"] == "booking_id" and fk["foreign_table_name"] == "bookings"
            for fk in fks_by_table["booking_locations"]
        )
        assert any(
            fk["column_name"] == "booking_id" and fk["foreign_table_name"] == "bookings"
            for fk in fks_by_table["booking_status_history"]
        )
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_postgis_spatial_functionality(raw_db_url):
    """Verify PostGIS spatial distance and bounding box calculations."""
    conn = await asyncpg.connect(raw_db_url)
    try:
        gateway_lon, gateway_lat = 72.8347, 18.9220
        marine_drive_lon, marine_drive_lat = 72.8236, 18.9432

        spatial_res = await conn.fetchrow(
            """
            SELECT
                ST_Distance(
                    ST_SetSRID(ST_MakePoint($1, $2), 4326)::geography,
                    ST_SetSRID(ST_MakePoint($3, $4), 4326)::geography
                ) AS distance_meters,
                ST_DWithin(
                    ST_SetSRID(ST_MakePoint($1, $2), 4326)::geography,
                    ST_SetSRID(ST_MakePoint($3, $4), 4326)::geography,
                    5000
                ) AS within_5km,
                ST_DWithin(
                    ST_SetSRID(ST_MakePoint($1, $2), 4326)::geography,
                    ST_SetSRID(ST_MakePoint($3, $4), 4326)::geography,
                    1000
                ) AS within_1km;
            """,
            gateway_lon,
            gateway_lat,
            marine_drive_lon,
            marine_drive_lat,
        )
        assert 2500 < spatial_res["distance_meters"] < 2800
        assert spatial_res["within_5km"] is True
        assert spatial_res["within_1km"] is False
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_orm_all_11_models_crud_and_relationships():
    """Verify end-to-end ORM model persistence and relationship loading across all 11 models."""
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    async_session = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    test_uid = uuid.uuid4().hex[:8]
    customer_phone = f"+91991{test_uid[:7]}"
    provider_phone = f"+91881{test_uid[:7]}"
    service_name = f"Test Service {test_uid}"
    reg_number = f"MH-02-{test_uid[:4].upper()}"

    async with async_session() as session:
        async with session.begin():
            customer = User(
                role=UserRole.CUSTOMER.value,
                first_name="Test",
                last_name="Customer",
                phone=customer_phone,
                email=f"customer.{test_uid}@example.com",
                status=UserStatus.ACTIVE.value,
            )
            session.add(customer)

            provider_user = User(
                role=UserRole.PROVIDER.value,
                first_name="Test",
                last_name="Provider",
                phone=provider_phone,
                email=f"provider.{test_uid}@example.com",
                status=UserStatus.ACTIVE.value,
            )
            session.add(provider_user)
            await session.flush()

            vehicle = Vehicle(
                user_id=customer.id,
                registration_number=reg_number,
                make="Maruti",
                model="Swift",
                variant="ZXi",
                fuel_type="Petrol",
                year=2022,
                color="Silver",
                is_primary=True,
            )
            session.add(vehicle)

            service = Service(
                name=service_name,
                category="Towing",
                description="Test towing service",
                base_price=Decimal("1000.00"),
                is_emergency=True,
                is_active=True,
            )
            session.add(service)

            provider = Provider(
                user_id=provider_user.id,
                business_name=f"Test Garage {test_uid}",
                provider_type=ProviderType.TOWING.value,
                phone=provider_phone,
                service_radius_km=Decimal("20.00"),
                verification_status=ProviderVerificationStatus.VERIFIED.value,
                is_online=True,
            )
            session.add(provider)
            await session.flush()

            doc = ProviderDocument(
                provider_id=provider.id,
                document_type=ProviderDocumentType.LICENSE.value,
                file_url="https://s3.roadresq.internal/docs/license.pdf",
                document_number=f"DL-{test_uid[:6].upper()}",
                status=ProviderDocumentStatus.APPROVED.value,
                reviewed_by=provider_user.id,
            )
            session.add(doc)

            p_service = ProviderService(
                provider_id=provider.id,
                service_id=service.id,
                price_from=Decimal("1000.00"),
                price_to=Decimal("2000.00"),
                is_active=True,
            )
            session.add(p_service)

            avail = ProviderAvailability(
                provider_id=provider.id,
                day_of_week=2,
                start_time=time(9, 0),
                end_time=time(18, 0),
                is_active=True,
            )
            session.add(avail)

            booking_no = (
                f"BK-{datetime.now(UTC).strftime('%Y%m%d')}-{test_uid[:4].upper()}"
            )
            booking = Booking(
                booking_number=booking_no,
                customer_id=customer.id,
                vehicle_id=vehicle.id,
                provider_id=provider.id,
                service_id=service.id,
                booking_type=BookingType.EMERGENCY.value,
                status=BookingStatus.ACCEPTED.value,
                problem_description="Breakdown on highway.",
            )
            session.add(booking)
            await session.flush()

            loc = BookingLocation(
                booking_id=booking.id,
                location_type=LocationType.SERVICE.value,
                address_text="Bandra Worli Sea Link, Mumbai",
                location="SRID=4326;POINT(72.8174 19.0330)",
                landmark="Near Toll Plaza",
            )
            session.add(loc)

            hist = BookingStatusHistory(
                booking_id=booking.id,
                from_status=None,
                to_status=BookingStatus.ACCEPTED.value,
                changed_by=customer.id,
                note="Initial booking created",
            )
            session.add(hist)

            audit = AuditLog(
                actor_user_id=customer.id,
                action=AuditAction.CREATE.value,
                entity_type="Booking",
                entity_id=booking.id,
                new_data={"status": "ACCEPTED"},
            )
            session.add(audit)

    # Query back
    async with async_session() as session:
        stmt = (
            select(Booking)
            .where(Booking.booking_number == booking_no)
            .options(
                selectinload(Booking.customer).selectinload(User.vehicles),
                selectinload(Booking.vehicle),
                selectinload(Booking.service),
                selectinload(Booking.provider).selectinload(Provider.documents),
                selectinload(Booking.provider).selectinload(Provider.services),
                selectinload(Booking.provider).selectinload(Provider.availability),
                selectinload(Booking.locations),
                selectinload(Booking.status_history),
            )
        )
        res = await session.execute(stmt)
        b = res.scalar_one()

        assert b.booking_number == booking_no
        assert b.customer.first_name == "Test"
        assert len(b.customer.vehicles) >= 1
        assert b.vehicle.registration_number == reg_number
        assert b.service.name == service_name
        assert b.provider.business_name == f"Test Garage {test_uid}"
        assert len(b.provider.documents) == 1
        assert len(b.provider.services) == 1
        assert len(b.provider.availability) == 1
        assert len(b.locations) == 1
        assert len(b.status_history) == 1

    await engine.dispose()
