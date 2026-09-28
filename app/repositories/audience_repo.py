"""Audience and visibility repositories.

The two audience tables have no ``campaign_id`` column, so the campaign scope
inherited from ``BaseRepository`` is a silent no-op for them. Every read
therefore has to establish the campaign by joining the parent fact. Without
that, an audience id from another campaign resolves normally, which is the same
class of leak ADR-021 fixed for the specialized entity tables.
"""

from uuid import UUID

from sqlalchemy import Select, and_, select

from app.models import (
    EntityFact,
    EntityFactAudience,
    EntityRelationshipFact,
    EntityRelationshipFactAudience,
)
from app.repositories.base import BaseRepository, _SelectT


class _ScopedAudienceRepository[T: EntityFactAudience | EntityRelationshipFactAudience](
    BaseRepository[T]
):
    """Shared parent-join scoping for the two audience tables.

    ``fact_model`` is the parent table, and it carries ``campaign_id``, so one
    join establishes the campaign for a table that cannot.
    """

    @property
    def fact_model(self) -> type[EntityFact] | type[EntityRelationshipFact]:
        raise NotImplementedError

    def _fact_scope(self, stmt: _SelectT) -> _SelectT:
        """Join the parent fact and apply the campaign scope.

        The join condition also requires a live parent, so the rules of a
        soft-deleted fact are not reachable. That predicate belongs in the join
        rather than a where clause: filtering the right table of an inner join
        in the where clause lets the rows back in.
        """
        if self.campaign_id is None:
            return stmt
        return stmt.join(
            self.fact_model,
            and_(
                self.model.fact_id == self.fact_model.id,
                self.fact_model.deleted_at.is_(None),
            ),
        ).where(self.fact_model.campaign_id == self.campaign_id)

    def filtered_stmt(self, fact_id: UUID | None = None) -> Select[T]:
        """Build a query filtered by deletion, campaign, and optionally fact.

        Named without a leading underscore on purpose: the soft-delete guard in
        ``test_no_undeleted_reads.py`` skips private methods, so a private
        helper here would leave the whole audience repository unchecked. Public
        also matches ``DocumentRepository.filtered_stmt``.
        """
        stmt = self._fact_scope(self._active_scope(select(self.model)))
        if fact_id is not None:
            stmt = stmt.where(self.model.fact_id == fact_id)
        return stmt.order_by(self.model.created_at, self.model.id)

    async def get_by_fact(self, fact_id: UUID) -> list[T]:
        """Get the live audience rules for a fact, in a stable order."""
        result = await self.session.execute(self.filtered_stmt(fact_id))
        return list(result.scalars().all())

    async def get_by_id(self, id: UUID) -> T | None:
        """Get one rule by id, scoped to the campaign through its fact."""
        stmt = self.filtered_stmt().where(self.model.id == id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_player(self, player_id: UUID) -> list[T]:
        """Get the rules naming a player, scoped to the campaign.

        This is a lookup, not an authorization decision. Nothing here decides
        whether a fact is visible to a player; see ADR-025 for why enforcement
        is deferred.
        """
        stmt = self.filtered_stmt().where(self.model.player_id == player_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class FactAudienceRepository(_ScopedAudienceRepository[EntityFactAudience]):
    """Repository for EntityFactAudience operations."""

    @property
    def model(self) -> type[EntityFactAudience]:
        return EntityFactAudience

    @property
    def fact_model(self) -> type[EntityFact]:
        return EntityFact


class RelationshipFactAudienceRepository(
    _ScopedAudienceRepository[EntityRelationshipFactAudience]
):
    """Repository for EntityRelationshipFactAudience operations."""

    @property
    def model(self) -> type[EntityRelationshipFactAudience]:
        return EntityRelationshipFactAudience

    @property
    def fact_model(self) -> type[EntityRelationshipFact]:
        return EntityRelationshipFact
