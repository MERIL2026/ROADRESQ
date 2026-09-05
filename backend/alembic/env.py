import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context
from app.core.config import settings
from app.models import (  # noqa: F401 — import all models so Alembic detects them
    AuditLog,
    Base,
    Booking,
    BookingLocation,
    BookingStatusHistory,
    Provider,
    ProviderAvailability,
    ProviderDocument,
    ProviderService,
    Service,
    User,
    Vehicle,
)

# Alembic Config object
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


ROADRESQ_TABLES = {
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
}


def include_object(object, name, type_, reflected, compare_to):
    """Strictly manage RoadResQ application tables and exclude all PostGIS/system tables."""
    if type_ == "table":
        return name in ROADRESQ_TABLES
    elif type_ in ("index", "column", "unique_constraint", "foreign_key_constraint"):
        table = getattr(object, "table", None)
        if table is not None:
            return table.name in ROADRESQ_TABLES
    return True


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = settings.DATABASE_URL
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in 'online' mode using Async Engine."""
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = settings.DATABASE_URL

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
