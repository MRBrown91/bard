"""Entity repository with alias support."""

from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import aliased, selectinload

from app.models import Entity, EntityAlias
from app.repositories.base import BaseRepository
from app.schemas.entity import EntityType

# The six one-to-one specializations declared on Entity. Derived from the enum
# so the set cannot drift from the types that actually have a table.
SPECIALIZATION_RELATIONSHIPS: tuple[str, ...] = tuple(
    entity_type.value for entity_type in EntityType
)

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

    def filtered_stmt(
        self, entity_type: str | None, name_contains: str | None
    ) -> Select[Any]:
        """Build the campaign-scoped, filtered entity select.

        Public so repositories that extend entity queries — the specialized
        repositories — can add their own predicates without duplicating the
        scope and escaping rules.
        """
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

    def _filtered(
        self, entity_type: str | None, name_contains: str | None
    ) -> Select[Any]:
        """Backwards-compatible alias for :meth:`filtered_stmt`."""
        return self.filtered_stmt(entity_type, name_contains)

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

    async def get_with(
        self, id: UUID, *relationship_names: str
    ) -> Entity | None:
        """Get a non-deleted entity with the named relationships loaded.

        The entity must be fetched before its specialization anyway, because
        campaign scope and type both live on the entity, so loading the
        relationship here costs one extra statement rather than a second round
        trip. See ADR-021.
        """
        stmt = self._active_scope(select(Entity).where(Entity.id == id))
        stmt = self._campaign_scope(stmt).options(
            *[selectinload(getattr(Entity, name)) for name in relationship_names]
        )
        result = await self.session.execute(stmt)
        return cast(Entity | None, result.scalar_one_or_none())

    async def soft_delete_with_specializations(self, id: UUID) -> bool:
        """Soft delete an entity together with its specialization.

        Both rows are stamped in one transaction. Leaving a live specialization
        behind is unreachable through the API, because every specialized read
        resolves the entity first, but it is still inconsistent state.
        """
        entity = await self.get_with(id, *SPECIALIZATION_RELATIONSHIPS)
        if entity is None:
            return False
        now = datetime.now(UTC)
        entity.deleted_at = now
        for relationship_name in SPECIALIZATION_RELATIONSHIPS:
            specialized = cast(Any, getattr(entity, relationship_name))
            if specialized is not None:
                specialized.deleted_at = now
        await self.session.flush()
        return True

    async def list_filtered_with(
        self,
        *,
        relationship_names: tuple[str, ...] = (),
        entity_type: str | None = None,
        name_contains: str | None = None,
        base_stmt: Select[Any] | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> list[Entity]:
        """List entities with the named relationships eagerly loaded.

        ``selectinload`` collects the primary keys of the whole page and issues
        a single ``IN`` query, so a page of entities costs one extra statement
        rather than one per row.

        ``base_stmt`` lets a caller add its own predicates, such as requiring a
        child row to exist, and still page over the result. Paging is applied
        after those predicates so a page is never short.
        """
        # An explicit None check: SQLAlchemy clauses raise on __bool__, so
        # `base_stmt or ...` would raise TypeError for every real statement.
        if base_stmt is not None:
            stmt = base_stmt
        else:
            stmt = self._filtered(entity_type, name_contains)
        stmt = stmt.order_by(Entity.created_at.desc())
        if relationship_names:
            stmt = stmt.options(
                *[
                    selectinload(getattr(Entity, name))
                    for name in relationship_names
                ]
            )
        stmt = stmt.offset(offset).limit(limit)
        result = await self.session.execute(stmt)
        return cast(list[Entity], list(result.scalars().all()))


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
