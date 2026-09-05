import uuid
from datetime import UTC, datetime

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    """Async repository for User entities."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(User, session)

    async def get_by_phone(self, phone: str) -> User | None:
        """Retrieves user by phone number."""
        stmt = select(User).where(User.phone == phone.strip())
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        """Retrieves user by email address."""
        stmt = select(User).where(User.email == email.strip().lower())
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_by_phone_or_email(self, identifier: str) -> User | None:
        """Retrieves user matching either phone or email."""
        clean_id = identifier.strip()
        stmt = select(User).where(
            or_(User.phone == clean_id, User.email == clean_id.lower())
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def update_last_login(self, user_id: uuid.UUID) -> None:
        """Updates last login timestamp for user."""
        stmt = (
            update(User)
            .where(User.id == user_id)
            .values(last_login_at=datetime.now(UTC), updated_at=datetime.now(UTC))
        )
        await self.session.execute(stmt)
        await self.session.flush()

    async def update_password(self, user_id: uuid.UUID, password_hash: str) -> None:
        """Updates password hash for user."""
        stmt = (
            update(User)
            .where(User.id == user_id)
            .values(password_hash=password_hash, updated_at=datetime.now(UTC))
        )
        await self.session.execute(stmt)
        await self.session.flush()

    async def update_status(self, user_id: uuid.UUID, status: str) -> None:
        """Updates status for user."""
        stmt = (
            update(User)
            .where(User.id == user_id)
            .values(status=status, updated_at=datetime.now(UTC))
        )
        await self.session.execute(stmt)
        await self.session.flush()
