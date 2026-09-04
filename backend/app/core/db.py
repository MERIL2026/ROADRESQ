from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

# Create async engine for PostgreSQL/PostGIS
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    future=True,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)


# Async session factory
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for obtaining async DB sessions."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def check_db_health() -> dict[str, str | bool]:
    """Health check helper to verify DB connection and PostGIS extension."""
    try:
        async with AsyncSessionLocal() as session:
            # Query PostGIS version to verify geospatial extension support
            result = await session.execute(text("SELECT PostGIS_Full_Version();"))
            version_row = result.scalar_one_or_none()
            return {
                "status": True,
                "database": "connected",
                "postgis_version": version_row or "installed",
            }
    except Exception as e:
        return {
            "status": False,
            "database": "disconnected",
            "error": str(e),
        }
