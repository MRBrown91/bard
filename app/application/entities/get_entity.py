"""Get entity use cases."""

from uuid import UUID

from app.application.exceptions import NotFoundError
from app.repositories import EntityRepository
from app.schemas.entity import EntityAliasRead, EntityRead, EntityWithAliasesRead


async def get_entity(
    entity_id: UUID,
    entity_repo: EntityRepository,
) -> EntityRead:
    """Get entity by ID within the scoped campaign."""
    entity = await entity_repo.get(entity_id)
    if not entity:
        raise NotFoundError("Entity not found", {"entity_id": str(entity_id)})
    return EntityRead.model_validate(entity)


async def get_entity_with_aliases(
    entity_id: UUID,
    entity_repo: EntityRepository,
) -> EntityWithAliasesRead:
    """Get entity with its active aliases.

    Aliases come from the ``Entity.aliases`` relationship, which filters
    soft-deleted rows in its ``primaryjoin`` and orders by alias so the result
    is stable. The response is built explicitly rather than validated from the
    ORM object, so a relationship left unloaded is an error here rather than a
    silent lazy load.
    """
    entity = await entity_repo.get_with(entity_id, "aliases")
    if not entity:
        raise NotFoundError("Entity not found", {"entity_id": str(entity_id)})

    return EntityWithAliasesRead(
        **EntityRead.model_validate(entity).model_dump(),
        aliases=[EntityAliasRead.model_validate(a) for a in entity.aliases],
    )


async def list_entities(
    entity_repo: EntityRepository,
    *,
    entity_type: str | None = None,
    name_contains: str | None = None,
    offset: int = 0,
    limit: int = 20,
) -> tuple[list[EntityRead], int]:
    """List entities with optional filters and a total matching count."""
    entities = await entity_repo.list_filtered(
        entity_type=entity_type,
        name_contains=name_contains,
        offset=offset,
        limit=limit,
    )
    total = await entity_repo.count_filtered(
        entity_type=entity_type,
        name_contains=name_contains,
    )
    return [EntityRead.model_validate(entity) for entity in entities], total
