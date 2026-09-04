import uuid
from collections.abc import Sequence
from typing import Any, Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    """Generic async repository providing common persistence operations."""

    def __init__(self, model: type[ModelT], session: AsyncSession) -> None:
        self.model = model
        self.session = session

    async def get_by_id(self, entity_id: uuid.UUID) -> ModelT | None:
        """Fetch entity by UUID primary key."""
        result = await self.session.execute(
            select(self.model).where(self.model.id == entity_id)  # type: ignore[attr-defined]
        )
        return result.scalar_one_or_none()

    async def list_all(
        self, skip: int = 0, limit: int = 100
    ) -> Sequence[ModelT]:
        """Fetch list of entities with pagination."""
        result = await self.session.execute(
            select(self.model).offset(skip).limit(limit)
        )
        return result.scalars().all()

    async def create(self, **kwargs: Any) -> ModelT:
        """Create and persist a new entity."""
        instance = self.model(**kwargs)
        self.session.add(instance)
        await self.session.flush()
        return instance

    async def delete(self, instance: ModelT) -> None:
        """Delete an entity from persistence."""
        await self.session.delete(instance)
        await self.session.flush()
