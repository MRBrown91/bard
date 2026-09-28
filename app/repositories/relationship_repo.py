"""Materialized relationship repository."""

from typing import cast
from uuid import UUID

from sqlalchemy import select

from app.models import EntityRelationship
from app.repositories.base import BaseRepository


class RelationshipRepository(BaseRepository[EntityRelationship]):
    """Repository for EntityRelationship operations."""

    @property
    def model(self) -> type[EntityRelationship]:
        return EntityRelationship

    async def list_for_source(self, source_entity_id: UUID) -> list[EntityRelationship]:
        """List current relationships where entity is source."""
        stmt = self._active_scope(
            self._campaign_scope(
                select(EntityRelationship).where(
                    EntityRelationship.source_entity_id == source_entity_id
                )
            )
        )
        result = await self.session.execute(stmt)
        return cast(list[EntityRelationship], result.scalars().all())

    async def list_for_target(self, target_entity_id: UUID) -> list[EntityRelationship]:
        """List current relationships where entity is target."""
        stmt = self._active_scope(
            self._campaign_scope(
                select(EntityRelationship).where(
                    EntityRelationship.target_entity_id == target_entity_id
                )
            )
        )
        result = await self.session.execute(stmt)
        return cast(list[EntityRelationship], result.scalars().all())

    async def list_by_type(self, relationship_type: str) -> list[EntityRelationship]:
        """List relationships by type."""
        stmt = self._active_scope(
            self._campaign_scope(
                select(EntityRelationship).where(
                    EntityRelationship.relationship_type == relationship_type
                )
            )
        )
        result = await self.session.execute(stmt)
        return cast(list[EntityRelationship], result.scalars().all())

    async def get_by_fact(self, fact_id: UUID) -> EntityRelationship | None:
        """Get materialized relationship by supporting fact."""
        stmt = self._active_scope(
            self._campaign_scope(
                select(EntityRelationship).where(
                    EntityRelationship.relationship_fact_id == fact_id
                )
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()