from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.service import Service
from app.repositories.base import BaseRepository


class ServiceRepository(BaseRepository[Service]):
    """Async repository for master Service catalog."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Service, session)

    async def get_by_name(self, name: str) -> Service | None:
        stmt = select(Service).where(Service.name == name.strip())
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def list_active(self) -> Sequence[Service]:
        stmt = (
            select(Service)
            .where(Service.is_active.is_(True))
            .order_by(Service.category, Service.name)
        )
        res = await self.session.execute(stmt)
        return res.scalars().all()
