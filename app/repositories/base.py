"""Base repository with campaign-scoped query pattern."""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from sqlalchemy.orm import DeclarativeBase

class BaseRepository[T: DeclarativeBase](ABC):
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

    def _active_scope(self, stmt: Select[Any]) -> Select[Any]:
        """Exclude soft-deleted rows.

        Every table inherits ``deleted_at`` from ``TimestampMixin``, so this
        applies unconditionally. Soft deletion preserves rows for retcons
        (ADR-010); it must not make them visible to ordinary reads, or a
        "deleted" campaign would still be fully usable and a deleted document
        would still be returned by the API that promised to remove it.
        """
        return stmt.where(self.model.deleted_at.is_(None))  # type: ignore[attr-defined]

    async def get(self, id: UUID) -> T | None:
        """Get by ID with campaign scope, excluding soft-deleted rows."""
        stmt = self._active_scope(select(self.model).where(self.model.id == id))  # type: ignore[attr-defined]
        stmt = self._campaign_scope(stmt)
        result = await self.session.execute(stmt)
        return cast(T | None, result.scalar_one_or_none())

    async def list(
        self,
        *,
        offset: int = 0,
        limit: int = 100,
        order_by: str | None = None,
    ) -> Sequence[T]:
        """List active rows with pagination and campaign scope."""
        stmt = self._active_scope(select(self.model))
        stmt = self._campaign_scope(stmt).offset(offset).limit(limit)
        if order_by and hasattr(self.model, order_by):
            stmt = stmt.order_by(getattr(self.model, order_by))
        result = await self.session.execute(stmt)
        return cast(Sequence[T], result.scalars().all())

    async def count(self) -> int:
        """Count active rows with campaign scope."""
        stmt = self._active_scope(select(func.count()).select_from(self.model))
        stmt = self._campaign_scope(stmt)
        result = await self.session.execute(stmt)
        return cast(int, result.scalar_one())

    async def create(self, **kwargs: Any) -> T:
        """Create new record, defaulting campaign_id from the scope.

        Models that have no ``campaign_id`` column (for example the entity
        alias table, which inherits isolation through its parent entity) are
        left untouched.
        """
        if self.campaign_id is not None and hasattr(self.model, "campaign_id"):
            kwargs.setdefault("campaign_id", self.campaign_id)
        obj = self.model(**kwargs)
        self.session.add(obj)
        await self.session.flush()
        return obj

    async def update(self, id: UUID, **kwargs: Any) -> T | None:
        """Update by ID with campaign scope.

        The row is refreshed after the flush because ``updated_at`` is a
        server-side ``onupdate`` default. Without the refresh the attribute is
        expired, and reading it would trigger implicit IO from async context.
        """
        obj = await self.get(id)
        if obj is None:
            return None
        for key, value in kwargs.items():
            setattr(obj, key, value)
        await self.session.flush()
        await self.session.refresh(obj)
        return obj

    async def soft_delete(self, id: UUID) -> bool:
        """Soft delete by ID with campaign scope."""
        obj = await self.get(id)
        if obj is None:
            return False
        obj.deleted_at = datetime.now(UTC)  # type: ignore[attr-defined]
        await self.session.flush()
        return True

    async def exists(self, id: UUID) -> bool:
        """Check existence of an active row with campaign scope."""
        stmt = self._active_scope(select(self.model.id).where(self.model.id == id))  # type: ignore[attr-defined]
        stmt = self._campaign_scope(stmt)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none() is not None