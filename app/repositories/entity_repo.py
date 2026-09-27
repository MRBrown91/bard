"""Entity repository with alias support."""

from typing import Any, cast
from uuid import UUID

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import aliased

from app.models import Entity, EntityAlias
from app.models.entity.entity_types import (
    Actor,
    Faction,
    Item,
    Location,
    Player,
    PlayerCharacter,
)
from app.repositories.base import BaseRepository

LIKE_ESCAPE = "\\"


def escape_like(term: str) -> str:
    """Escape LIKE wildcards so user input is matched literally."""
    for char in ("\\", "%", "_"):
        term = term.replace(char, LIKE_ESCAPE + char)
    return term


class EntityRepository(BaseRepository[Entity]):
    """Repository for Entity operations.

    Reads exclude soft-deleted rows so that retention of invalid history does
    not make deleted entities visible to the application.
    """

    @property
    def model(self) -> type[Entity]:
        return Entity

    def _active_scope(self, stmt: Select[Any]) -> Select[Any]:
        """Exclude soft-deleted entities."""
        return stmt.where(Entity.deleted_at.is_(None))

    async def get(self, id: UUID) -> Entity | None:
        """Get a non-deleted entity by ID with campaign scope."""
        stmt = self._active_scope(select(Entity).where(Entity.id == id))
        stmt = self._campaign_scope(stmt)
        result = await self.session.execute(stmt)
        return cast(Entity | None, result.scalar_one_or_none())

    def _filtered(
        self, entity_type: str | None, name_contains: str | None
    ) -> Select[Any]:
        """Build the campaign-scoped, filtered entity select."""
        stmt = self._campaign_scope(self._active_scope(select(Entity)))
        if entity_type is not None:
            stmt = stmt.where(Entity.entity_type == entity_type)
        if name_contains is not None:
            pattern = f"%{escape_like(name_contains)}%"
            stmt = stmt.where(
                or_(
                    Entity.name.ilike(pattern, escape=LIKE_ESCAPE),
                    Entity.description.ilike(pattern, escape=LIKE_ESCAPE),
                )
            )
        return stmt

    async def list_filtered(
        self,
        *,
        entity_type: str | None = None,
        name_contains: str | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> list[Entity]:
        """List entities for the scoped campaign with optional filters."""
        stmt = self._filtered(entity_type, name_contains).order_by(
            Entity.created_at.desc()
        )
        stmt = stmt.offset(offset).limit(limit)
        result = await self.session.execute(stmt)
        return cast(list[Entity], list(result.scalars().all()))

    async def count_filtered(
        self,
        *,
        entity_type: str | None = None,
        name_contains: str | None = None,
    ) -> int:
        """Count entities matching the same filters as ``list_filtered``."""
        stmt = self._filtered(entity_type, name_contains)
        count_stmt = select(func.count()).select_from(stmt.subquery())
        result = await self.session.execute(count_stmt)
        return result.scalar_one()

    async def find_by_name(self, name: str) -> Entity | None:
        """Find entity by exact name match."""
        stmt = self._active_scope(select(Entity).where(Entity.name == name))
        result = await self.session.execute(self._campaign_scope(stmt))
        return cast(Entity | None, result.scalar_one_or_none())

    async def find_by_alias(self, alias: str) -> Entity | None:
        """Find entity by alias."""
        alias_ = aliased(EntityAlias)
        stmt = (
            select(Entity)
            .join(alias_, alias_.entity_id == Entity.id)
            .where(alias_.alias == alias, alias_.deleted_at.is_(None))
        )
        result = await self.session.execute(
            self._campaign_scope(self._active_scope(stmt))
        )
        return cast(Entity | None, result.scalar_one_or_none())


class EntityAliasRepository(BaseRepository[EntityAlias]):
    """Repository for EntityAlias operations.

    Aliases are not directly campaign-scoped (they inherit isolation through
    their parent entity), so callers must verify the parent entity belongs to
    the caller's campaign before using an alias.
    """

    @property
    def model(self) -> type[EntityAlias]:
        return EntityAlias

    def _active_scope(self, stmt: Select[Any]) -> Select[Any]:
        """Exclude soft-deleted aliases."""
        return stmt.where(EntityAlias.deleted_at.is_(None))

    async def get(self, id: UUID) -> EntityAlias | None:
        """Get a non-deleted alias by ID."""
        stmt = self._active_scope(select(EntityAlias).where(EntityAlias.id == id))
        result = await self.session.execute(stmt)
        return cast(EntityAlias | None, result.scalar_one_or_none())

    async def get_by_entity(self, entity_id: UUID) -> list[EntityAlias]:
        """Get all active aliases for an entity."""
        stmt = self._active_scope(
            select(EntityAlias).where(EntityAlias.entity_id == entity_id)
        )
        result = await self.session.execute(stmt.order_by(EntityAlias.alias))
        return cast(list[EntityAlias], list(result.scalars().all()))

    async def get_by_alias(self, entity_id: UUID, alias: str) -> EntityAlias | None:
        """Get alias by entity_id and alias string."""
        stmt = self._active_scope(
            select(EntityAlias).where(
                EntityAlias.entity_id == entity_id,
                EntityAlias.alias == alias,
            )
        )
        result = await self.session.execute(stmt)
        return cast(EntityAlias | None, result.scalar_one_or_none())


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
