"""Audience/visibility repositories."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import EntityFactAudience, EntityRelationshipFactAudience
from app.repositories.base import BaseRepository


class FactAudienceRepository(BaseRepository[EntityFactAudience]):
    """Repository for EntityFactAudience operations."""

    @property
    def model(self) -> type[EntityFactAudience]:
        return EntityFactAudience

    async def get_for_fact(self, fact_id: UUID) -> list[EntityFactAudience]:
        """Get all audience rules for a fact."""
        stmt = select(EntityFactAudience).where(EntityFactAudience.fact_id == fact_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_for_player(self, player_id: UUID) -> list[EntityFactAudience]:
        """Get audience rules for a specific player."""
        stmt = select(EntityFactAudience).where(EntityFactAudience.player_id == player_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class RelationshipFactAudienceRepository(BaseRepository[EntityRelationshipFactAudience]):
    """Repository for EntityRelationshipFactAudience operations."""

    @property
    def model(self) -> type[EntityRelationshipFactAudience]:
        return EntityRelationshipFactAudience

    async def get_for_fact(self, fact_id: UUID) -> list[EntityRelationshipFactAudience]:
        """Get all audience rules for a relationship fact."""
        stmt = select(EntityRelationshipFactAudience).where(
            EntityRelationshipFactAudience.fact_id == fact_id
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_for_player(self, player_id: UUID) -> list[EntityRelationshipFactAudience]:
        """Get audience rules for a specific player."""
        stmt = select(EntityRelationshipFactAudience).where(
            EntityRelationshipFactAudience.player_id == player_id
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())