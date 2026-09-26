"""User repository."""

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    """Repository for User operations."""

    @property
    def model(self) -> type[User]:
        return User

    def _campaign_scope(self, stmt: Any) -> Any:
        """Users are not campaign-scoped - override to not filter."""
        return stmt

    async def get_by_auth(self, auth_provider: str, auth_subject: str) -> User | None:
        """Get user by auth provider and subject."""
        stmt = select(User).where(
            User.auth_provider == auth_provider,
            User.auth_subject == auth_subject,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id(self, id: UUID) -> User | None:
        """Get user by ID (no campaign scope)."""
        stmt = select(User).where(User.id == id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()