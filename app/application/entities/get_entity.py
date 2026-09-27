"""Get entity use cases."""

from uuid import UUID

from app.application.exceptions import NotFoundError
from app.repositories import EntityAliasRepository, EntityRepository
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
    alias_repo: EntityAliasRepository,
) -> EntityWithAliasesRead:
    """Get entity with its active aliases.

    Aliases are loaded with an explicit query rather than ORM relationship
    loading, because Entity deliberately has no alias relationship.
    """
    entity = await entity_repo.get(entity_id)
    if not entity:
        raise NotFoundError("Entity not found", {"entity_id": str(entity_id)})

    aliases = await alias_repo.get_by_entity(entity_id)
    read = EntityWithAliasesRead.model_validate(entity)
    return read.model_copy(
        update={"aliases": [EntityAliasRead.model_validate(alias) for alias in aliases]}
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
