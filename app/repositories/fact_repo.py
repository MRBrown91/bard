"""Fact and relationship fact repositories.

Neither repository filters by audience. The audience rules are stored and
returned so a caller can see them, but nothing here decides whether a fact is
visible to a player; enforcement belongs at context construction in Phase 2
(ADR-025). An earlier version of this module's docstrings claimed visibility
filtering that did not exist.

Listing a page and counting the total are built from one predicate, so the
total always equals the number of rows a client can page through. Ordering is
``(created_at, id)`` so a row cannot swap between pages when timestamps tie.
"""

from typing import Any, ClassVar
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.elements import ColumnElement

from app.models import EntityFact, EntityRelationshipFact
from app.repositories.base import BaseRepository


class FactRepository(BaseRepository[EntityFact]):
    """Repository for EntityFact operations."""

    #: Fields a caller may change on an existing fact. ``entity_id``,
    #: ``fact_type``, ``statement_id``, and ``event_id`` are deliberately
    #: absent: the first says *which entity the fact is about* and the rest
    #: are its provenance. The request schema already refuses them, so this
    #: allow-list is the second lock rather than the only one -- a fact's
    #: history should not be rewritable by whoever happens to call the
    #: repository.
    UPDATABLE_FIELDS: ClassVar[frozenset[str]] = frozenset(
        {"content", "confidence", "importance", "status"}
    )

    @property
    def model(self) -> type[EntityFact]:
        return EntityFact

    async def update(self, id: UUID, **kwargs: Any) -> EntityFact | None:
        """Update the mutable fields, ignoring anything not on the allow-list."""
        changes = {k: v for k, v in kwargs.items() if k in self.UPDATABLE_FIELDS}
        if not changes:
            return await self.get(id)
        return await super().update(id, **changes)

    def _filtered_stmt(
        self,
        *,
        entity_id: UUID | None = None,
        status: str | None = None,
        fact_type: str | None = None,
        event_id: UUID | None = None,
        statement_id: UUID | None = None,
    ) -> Select[EntityFact]:
        """Build the one predicate that both the page and the total use."""
        stmt = self._active_scope(select(EntityFact))
        stmt = self._campaign_scope(stmt)
        if entity_id is not None:
            stmt = stmt.where(EntityFact.entity_id == entity_id)
        if status is not None:
            stmt = stmt.where(EntityFact.status == status)
        if fact_type is not None:
            stmt = stmt.where(EntityFact.fact_type == fact_type)
        if event_id is not None:
            stmt = stmt.where(EntityFact.event_id == event_id)
        if statement_id is not None:
            stmt = stmt.where(EntityFact.statement_id == statement_id)
        return stmt

    async def get_with_audiences(self, id: UUID) -> EntityFact | None:
        """Get a fact with its live audience rules loaded."""
        stmt = self._active_scope(
            self._campaign_scope(
                select(EntityFact)
                .options(selectinload(EntityFact.audiences))
                .where(EntityFact.id == id)
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_filtered(
        self,
        *,
        entity_id: UUID | None = None,
        status: str | None = None,
        fact_type: str | None = None,
        event_id: UUID | None = None,
        statement_id: UUID | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> list[EntityFact]:
        """List facts for a page, in a deterministic order."""
        stmt = self._filtered_stmt(
            entity_id=entity_id,
            status=status,
            fact_type=fact_type,
            event_id=event_id,
            statement_id=statement_id,
        )
        stmt = stmt.order_by(EntityFact.created_at, EntityFact.id)
        stmt = stmt.offset(offset).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_filtered(
        self,
        *,
        entity_id: UUID | None = None,
        status: str | None = None,
        fact_type: str | None = None,
        event_id: UUID | None = None,
        statement_id: UUID | None = None,
    ) -> int:
        """Count the rows ``list_filtered`` would page through."""
        stmt = self._filtered_stmt(
            entity_id=entity_id,
            status=status,
            fact_type=fact_type,
            event_id=event_id,
            statement_id=statement_id,
        )
        result = await self.session.execute(
            self._campaign_scope(
                self._active_scope(
                    select(func.count()).select_from(stmt.subquery())
                )
            )
        )
        return result.scalar_one()

    async def list_for_event(self, event_id: UUID) -> list[EntityFact]:
        """List the facts that constitute an event."""
        return await self.list_filtered(event_id=event_id, limit=1000)

    async def list_by_statement(self, statement_id: UUID) -> list[EntityFact]:
        """List the facts extracted from a statement."""
        return await self.list_filtered(statement_id=statement_id, limit=1000)


class RelationshipFactRepository(BaseRepository[EntityRelationshipFact]):
    """Repository for EntityRelationshipFact operations.

    Paging and filtering arrive with P1D.2; the reads here are the provenance
    lookups P1D.4 and P1D.5 need.
    """

    @property
    def model(self) -> type[EntityRelationshipFact]:
        return EntityRelationshipFact

    async def get_with_audiences(self, id: UUID) -> EntityRelationshipFact | None:
        """Get a relationship fact with its live audience rules loaded."""
        stmt = self._active_scope(
            self._campaign_scope(
                select(EntityRelationshipFact)
                .options(selectinload(EntityRelationshipFact.audiences))
                .where(EntityRelationshipFact.id == id)
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def _where(
        self, criterion: ColumnElement[bool]
    ) -> list[EntityRelationshipFact]:
        """Run a single-column provenance lookup, scoped and ordered."""
        stmt = self._active_scope(self._campaign_scope(select(EntityRelationshipFact)))
        stmt = stmt.where(criterion).order_by(
            EntityRelationshipFact.created_at, EntityRelationshipFact.id
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_source(
        self, source_entity_id: UUID
    ) -> list[EntityRelationshipFact]:
        """List outgoing relationship facts for an entity."""
        return await self._where(
            EntityRelationshipFact.source_entity_id == source_entity_id
        )

    async def list_for_target(
        self, target_entity_id: UUID
    ) -> list[EntityRelationshipFact]:
        """List incoming relationship facts for an entity."""
        return await self._where(
            EntityRelationshipFact.target_entity_id == target_entity_id
        )

    async def list_for_event(self, event_id: UUID) -> list[EntityRelationshipFact]:
        """List relationship facts for an event."""
        return await self._where(EntityRelationshipFact.event_id == event_id)

    async def list_by_statement(
        self, statement_id: UUID
    ) -> list[EntityRelationshipFact]:
        """List relationship facts extracted from a statement."""
        return await self._where(EntityRelationshipFact.statement_id == statement_id)
