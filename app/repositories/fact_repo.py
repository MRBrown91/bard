"""Fact and relationship fact repositories with visibility filtering."""

from typing import cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import EntityFact, EntityRelationshipFact
from app.repositories.base import BaseRepository


class FactRepository(BaseRepository[EntityFact]):
    """Repository for EntityFact operations with visibility filtering."""

    @property
    def model(self) -> type[EntityFact]:
        return EntityFact

    async def get_with_audiences(self, id: UUID) -> EntityFact | None:
        """Get fact with audience rules loaded."""
        stmt = self._campaign_scope(
            select(EntityFact)
            .options(selectinload(EntityFact.audiences))  # type: ignore[attr-defined]
            .where(EntityFact.id == id)
        )
        result = await self.session.execute(stmt)
        return cast(EntityFact | None, result.scalar_one_or_none())

    async def list_for_entity(
        self,
        entity_id: UUID,
        *,
        status: str | None = None,
        fact_type: str | None = None,
    ) -> list[EntityFact]:
        """List facts for an entity with optional filters."""
        stmt = self._campaign_scope(select(EntityFact).where(EntityFact.entity_id == entity_id))
        if status:
            stmt = stmt.where(EntityFact.status == status)
        if fact_type:
            stmt = stmt.where(EntityFact.fact_type == fact_type)
        result = await self.session.execute(stmt)
        return cast(list[EntityFact], result.scalars().all())

    async def list_for_event(self, event_id: UUID) -> list[EntityFact]:
        """List facts for an event."""
        stmt = self._campaign_scope(select(EntityFact).where(EntityFact.event_id == event_id))
        result = await self.session.execute(stmt)
        return cast(list[EntityFact], result.scalars().all())

    async def list_by_statement(self, statement_id: UUID) -> list[EntityFact]:
        """List facts extracted from a statement."""
        stmt = self._campaign_scope(select(EntityFact).where(EntityFact.statement_id == statement_id))
        result = await self.session.execute(stmt)
        return cast(list[EntityFact], result.scalars().all())


class RelationshipFactRepository(BaseRepository[EntityRelationshipFact]):
    """Repository for EntityRelationshipFact operations."""

    @property
    def model(self) -> type[EntityRelationshipFact]:
        return EntityRelationshipFact

    async def get_with_audiences(self, id: UUID) -> EntityRelationshipFact | None:
        """Get relationship fact with audience rules loaded."""
        stmt = self._campaign_scope(
            select(EntityRelationshipFact)
            .options(selectinload(EntityRelationshipFact.audiences))  # type: ignore[attr-defined]
            .where(EntityRelationshipFact.id == id)
        )
        result = await self.session.execute(stmt)
        return cast(EntityRelationshipFact | None, result.scalar_one_or_none())

    async def list_for_source(self, source_entity_id: UUID) -> list[EntityRelationshipFact]:
        """List outgoing relationships for an entity."""
        stmt = self._campaign_scope(
            select(EntityRelationshipFact).where(EntityRelationshipFact.source_entity_id == source_entity_id)
        )
        result = await self.session.execute(stmt)
        return cast(list[EntityRelationshipFact], result.scalars().all())

    async def list_for_target(self, target_entity_id: UUID) -> list[EntityRelationshipFact]:
        """List incoming relationships for an entity."""
        stmt = self._campaign_scope(
            select(EntityRelationshipFact).where(EntityRelationshipFact.target_entity_id == target_entity_id)
        )
        result = await self.session.execute(stmt)
        return cast(list[EntityRelationshipFact], result.scalars().all())

    async def list_for_event(self, event_id: UUID) -> list[EntityRelationshipFact]:
        """List relationship facts for an event."""
        stmt = self._campaign_scope(
            select(EntityRelationshipFact).where(EntityRelationshipFact.event_id == event_id)
        )
        result = await self.session.execute(stmt)
        return cast(list[EntityRelationshipFact], result.scalars().all())

    async def list_by_statement(self, statement_id: UUID) -> list[EntityRelationshipFact]:
        """List relationship facts extracted from a statement."""
        stmt = self._campaign_scope(
            select(EntityRelationshipFact).where(EntityRelationshipFact.statement_id == statement_id)
        )
        result = await self.session.execute(stmt)
        return cast(list[EntityRelationshipFact], result.scalars().all())