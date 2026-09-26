"""Entity repository with alias support."""

from typing import cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Entity, EntityAlias
from app.models.entity.entity_types import Actor, Player, PlayerCharacter, Location, Item, Faction
from app.repositories.base import BaseRepository


class EntityRepository(BaseRepository[Entity]):
    """Repository for Entity operations."""

    @property
    def model(self) -> type[Entity]:
        return Entity

    async def get_with_aliases(self, id: UUID) -> Entity | None:
        """Get entity with aliases loaded."""
        stmt = self._campaign_scope(
            select(Entity)
            .options(selectinload(Entity.aliases))  # type: ignore[attr-defined]
            .where(Entity.id == id)
        )
        result = await self.session.execute(stmt)
        return cast(Entity | None, result.scalar_one_or_none())

    async def get_with_specialized(self, id: UUID) -> Entity | None:
        """Get entity with all specialized types loaded."""
        stmt = self._campaign_scope(
            select(Entity)
            .options(
                selectinload(Entity.actor),  # type: ignore[attr-defined]
                selectinload(Entity.player),  # type: ignore[attr-defined]
                selectinload(Entity.player_character),  # type: ignore[attr-defined]
                selectinload(Entity.location),  # type: ignore[attr-defined]
                selectinload(Entity.item),  # type: ignore[attr-defined]
                selectinload(Entity.faction),  # type: ignore[attr-defined]
            )
            .where(Entity.id == id)
        )
        result = await self.session.execute(stmt)
        return cast(Entity | None, result.scalar_one_or_none())

    async def find_by_name(self, name: str) -> Entity | None:
        """Find entity by exact name match."""
        stmt = self._campaign_scope(select(Entity).where(Entity.name == name))
        result = await self.session.execute(stmt)
        return cast(Entity | None, result.scalar_one_or_none())

    async def find_by_alias(self, alias: str) -> Entity | None:
        """Find entity by alias."""
        stmt = self._campaign_scope(
            select(Entity)
            .join(EntityAlias, Entity.id == EntityAlias.entity_id)
            .where(EntityAlias.alias == alias)
        )
        result = await self.session.execute(stmt)
        return cast(Entity | None, result.scalar_one_or_none())


class EntityAliasRepository(BaseRepository[EntityAlias]):
    """Repository for EntityAlias operations."""

    @property
    def model(self) -> type[EntityAlias]:
        return EntityAlias

    async def get_by_entity(self, entity_id: UUID) -> list[EntityAlias]:
        """Get all aliases for an entity."""
        stmt = select(EntityAlias).where(EntityAlias.entity_id == entity_id)
        result = await self.session.execute(stmt)
        return cast(list[EntityAlias], result.scalars().all())


class ActorRepository(BaseRepository[Actor]):
    """Repository for Actor operations."""

    @property
    def model(self) -> type[Actor]:
        return Actor


class PlayerRepository(BaseRepository[Player]):
    """Repository for Player operations."""

    @property
    def model(self) -> type[Player]:
        return Player

    async def get_by_user(self, user_id: UUID) -> list[Player]:
        """Get players linked to a user."""
        stmt = select(Player).where(Player.user_id == user_id)
        result = await self.session.execute(stmt)
        return cast(list[Player], result.scalars().all())


class PlayerCharacterRepository(BaseRepository[PlayerCharacter]):
    """Repository for PlayerCharacter operations."""

    @property
    def model(self) -> type[PlayerCharacter]:
        return PlayerCharacter

    async def get_by_player(self, player_id: UUID) -> list[PlayerCharacter]:
        """Get characters for a player."""
        stmt = select(PlayerCharacter).where(PlayerCharacter.player_id == player_id)
        result = await self.session.execute(stmt)
        return cast(list[PlayerCharacter], result.scalars().all())


class LocationRepository(BaseRepository[Location]):
    """Repository for Location operations."""

    @property
    def model(self) -> type[Location]:
        return Location


class ItemRepository(BaseRepository[Item]):
    """Repository for Item operations."""

    @property
    def model(self) -> type[Item]:
        return Item


class FactionRepository(BaseRepository[Faction]):
    """Repository for Faction operations."""

    @property
    def model(self) -> type[Faction]:
        return Faction