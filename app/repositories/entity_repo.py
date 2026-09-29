"""Entity repository with alias support."""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.orm import aliased, selectinload

from app.models import Entity, EntityAlias
from app.models.entity.entity import ALIAS_KIND_NAME
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


@dataclass(frozen=True, slots=True)
class MatchTerm:
    """One string the entity matcher can recognize, and what it belongs to.

    ``term`` is the name or the alias; ``name`` is always the entity's own
    name, so a caller can label a result without a second lookup. Keeping the
    pair here is what lets the matcher return the right display name for a hit
    that came from an alias.
    """

    entity_id: UUID
    name: str
    term: str
    is_alias: bool



class EntityRepository(BaseRepository[Entity]):
    """Repository for Entity operations.

    Reads exclude soft-deleted rows so that retention of invalid history does
    not make deleted entities visible to the application.
    """

    @property
    def model(self) -> type[Entity]:
        return Entity

    async def get(self, id: UUID) -> Entity | None:
        """Get a non-deleted entity by ID with campaign scope."""
        stmt = self._active_scope(select(Entity).where(Entity.id == id))
        stmt = self._campaign_scope(stmt)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

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

    async def list_match_terms(self) -> list[MatchTerm]:
        """List every name and alias the matcher can recognize.

    One row per matchable term. An entity's own name is held in
    ``entity_aliases`` as a ``name`` row, so this is a single join over one
    table and ``is_alias`` is read off the row's kind rather than inferred
    from which query produced it. See ADR-027.

    Returns plain values rather than ``Entity`` objects because the matcher
    compares strings and ids: loading descriptions, timestamps, and the
    specializations it will never read would make every transcript message
    pay for a full entity load.
    """
        stmt = self._campaign_scope(
            self._active_scope(
                cast(
                    Select[Any],
                    select(
                        Entity.id, Entity.name, EntityAlias.alias, EntityAlias.kind
                    ).join(
                        EntityAlias,
                        and_(
                            EntityAlias.entity_id == Entity.id,
                            EntityAlias.deleted_at.is_(None),
                        ),
                    ),
                )
            )
        )
        rows = await self.session.execute(stmt)
        return [
            MatchTerm(
                entity_id=row.id,
                name=row.name,
                term=row.alias,
                is_alias=row.kind != ALIAS_KIND_NAME,
            )
            for row in rows
            if row.alias
        ]

    async def find_by_name(self, name: str) -> Entity | None:
        stmt = self._active_scope(select(Entity).where(Entity.name == name))
        result = await self.session.execute(self._campaign_scope(stmt))
        return result.scalar_one_or_none()

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
        return result.scalar_one_or_none()

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
        return result.scalar_one_or_none()

    async def soft_delete_with_specializations(self, id: UUID) -> bool:
        """Soft delete an entity together with its specialization and name alias.

        Both rows are stamped in one transaction. Leaving a live specialization
        behind is unreachable through the API, because every specialized read
        resolves the entity first, but it is still inconsistent state. The
        natural name alias must be stamped the same way so the entity stops
        being recognised while the rest remains for retcons.
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

        await self._stamp_name_aliases(id, now)

        await self.session.flush()
        return True

    async def _stamp_name_aliases(self, id: UUID, now: datetime) -> None:
        """Soft delete every live name row for an entity.

        ``scalars().all()`` rather than ``scalar_one_or_none()``: the partial
        unique index permits at most one *live* name row, but a rename that
        collided with an existing alias before this constraint existed can leave
        a soft-deleted one behind. Stamping all of them is both correct and
        immune to that, where asking for exactly one would raise on a database
        carrying legacy data.
        """
        stmt = self._active_scope(
            select(EntityAlias).where(
                EntityAlias.entity_id == id,
                EntityAlias.kind == ALIAS_KIND_NAME,
            )
        )
        result = await self.session.execute(stmt)
        for alias_row in cast(Any, result).scalars().all():
            cast(Any, alias_row).deleted_at = now

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

    async def get(self, id: UUID) -> EntityAlias | None:
        """Get a non-deleted alias by ID."""
        stmt = self._active_scope(select(EntityAlias).where(EntityAlias.id == id))
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

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
        return result.scalar_one_or_none()

    async def get_name_alias(self, entity_id: UUID) -> EntityAlias | None:
        """Get an entity's live natural name alias, if it has one."""
        stmt = self._active_scope(
            select(EntityAlias).where(
                EntityAlias.entity_id == entity_id,
                EntityAlias.kind == ALIAS_KIND_NAME,
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def rename(self, entity_id: UUID, name: str) -> bool:
        """Point an entity's natural name alias at a new name.

        Renaming the entity without moving this row would leave the entity
        matchable only by a name it no longer has, so the two are updated
        together. Returns False when there is no live name alias, which should
        not happen but must not silently appear to succeed.
        """
        name_alias = await self.get_name_alias(entity_id)
        if name_alias is None:
            return False
        name_alias.alias = name
        await self.session.flush()
        return True
