"""Event repository."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Event
from app.repositories.base import BaseRepository


class EventRepository(BaseRepository[Event]):
    """Repository for Event operations."""

    @property
    def model(self) -> type[Event]:
        return Event

    async def list_by_date_range(
        self,
        start: datetime | None = None,
        end: datetime | None = None,
        *,
        status: str | None = None,
    ) -> list[Event]:
        """List events within date range."""
        stmt = self._campaign_scope(select(Event))
        if start:
            stmt = stmt.where(Event.occurred_at >= start)
        if end:
            stmt = stmt.where(Event.occurred_at <= end)
        if status:
            stmt = stmt.where(Event.status == status)
        stmt = stmt.order_by(Event.occurred_at.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())