"""Base repository with campaign-scoped query pattern."""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, Generic, TypeVar, cast
from uuid import UUID

from sqlalchemy import Select, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from sqlalchemy.orm import DeclarativeBase

T = TypeVar("T", bound="DeclarativeBase")


class BaseRepository(ABC, Generic[T]):
    """Base repository with automatic campaign isolation."""

    def __init__(self, session: AsyncSession, campaign_id: UUID | None = None):
        self.session = session
        self.campaign_id = campaign_id

    @property
    @abstractmethod
    def model(self) -> type[T]:
        """Return the SQLAlchemy model class."""
        ...

    def _campaign_scope(self, stmt: Select[Any]) -> Select[Any]:
        """Apply campaign_id filter to query."""
        if self.campaign_id is not None and hasattr(self.model, "campaign_id"):
            return stmt.where(self.model.campaign_id == self.campaign_id)  # type: ignore[attr-defined]
        return stmt

    async def get(self, id: UUID) -> T | None:
        """Get by ID with campaign scope."""
        stmt = self._campaign_scope(select(self.model).where(self.model.id == id))  # type: ignore[attr-defined]
        result = await self.session.execute(stmt)
        return cast(T | None, result.scalar_one_or_none())

    async def list(
        self,
        *,
        offset: int = 0,
        limit: int = 100,
        order_by: str | None = None,
    ) -> Sequence[T]:
        """List with pagination and campaign scope."""
        stmt = self._campaign_scope(select(self.model)).offset(offset).limit(limit)
        if order_by and hasattr(self.model, order_by):
            stmt = stmt.order_by(getattr(self.model, order_by))
        result = await self.session.execute(stmt)
        return cast(Sequence[T], result.scalars().all())

    async def count(self) -> int:
        """Count with campaign scope."""
        stmt = self._campaign_scope(select(func.count()).select_from(self.model))
        result = await self.session.execute(stmt)
        return cast(int, result.scalar_one())

    async def create(self, **kwargs: Any) -> T:
        """Create new record with campaign_id."""
        if self.campaign_id is not None:
            kwargs.setdefault("campaign_id", self.campaign_id)
        obj = self.model(**kwargs)
        self.session.add(obj)
        await self.session.flush()
        return obj

    async def update(self, id: UUID, **kwargs: Any) -> T | None:
        """Update by ID with campaign scope."""
        obj = await self.get(id)
        if obj is None:
            return None
        for key, value in kwargs.items():
            setattr(obj, key, value)
        await self.session.flush()
        return obj

    async def soft_delete(self, id: UUID) -> bool:
        """Soft delete by ID with campaign scope."""
        from datetime import datetime
        obj = await self.get(id)
        if obj is None:
            return False
        obj.deleted_at = datetime.now(obj.deleted_at.tzinfo) if obj.deleted_at else datetime.utcnow()  # type: ignore[attr-defined]
        await self.session.flush()
        return True

    async def exists(self, id: UUID) -> bool:
        """Check existence with campaign scope."""
        stmt = self._campaign_scope(select(self.model.id).where(self.model.id == id))  # type: ignore[attr-defined]
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none() is not None