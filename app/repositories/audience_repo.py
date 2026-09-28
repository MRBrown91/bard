"""Audience/visibility repositories."""

from uuid import UUID

from sqlalchemy import select

from app.models import EntityFactAudience, EntityRelationshipFactAudience
from app.repositories.base import BaseRepository


class FactAudienceRepository(BaseRepository[EntityFactAudience]):
    """Repository for EntityFactAudience operations."""

    @property
    def model(self) -> type[EntityFactAudience]:
        return EntityFactAudience

    async def get_for_fact(self, fact_id: UUID) -> list[EntityFactAudience]:
        """Get all audience rules for a fact."""
        stmt = self._active_scope(
            select(EntityFactAudience).where(EntityFactAudience.fact_id == fact_id)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_for_player(self, player_id: UUID) -> list[EntityFactAudience]:
        """Get audience rules for a specific player."""
        stmt = self._active_scope(
            select(EntityFactAudience).where(EntityFactAudience.player_id == player_id)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class RelationshipFactAudienceRepository(BaseRepository[EntityRelationshipFactAudience]):
    """Repository for EntityRelationshipFactAudience operations."""

    @property
    def model(self) -> type[EntityRelationshipFactAudience]:
        return EntityRelationshipFactAudience

    async def get_for_fact(self, fact_id: UUID) -> list[EntityRelationshipFactAudience]:
        """Get all audience rules for a relationship fact."""
        stmt = self._active_scope(
            select(EntityRelationshipFactAudience).where(
                EntityRelationshipFactAudience.fact_id == fact_id
            )
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_for_player(self, player_id: UUID) -> list[EntityRelationshipFactAudience]:
        """Get audience rules for a specific player."""
        stmt = self._active_scope(
            select(EntityRelationshipFactAudience).where(
                EntityRelationshipFactAudience.player_id == player_id
            )
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())