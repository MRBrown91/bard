"""Create entity use cases."""

from uuid import UUID

from app.application.exceptions import ConflictError, NotFoundError
from app.repositories import EntityAliasRepository, EntityRepository
from app.schemas.entity import (
    EntityAliasCreate,
    EntityAliasRead,
    EntityCreate,
    EntityRead,
)


async def create_entity(
    data: EntityCreate,
    entity_repo: EntityRepository,
    alias_repo: EntityAliasRepository,
) -> EntityRead:
    """Create a new entity with optional aliases.

    The campaign is taken from the repository scope, which the transport layer
    has already authorized, so it cannot be supplied by the caller.
    """
    requested = [alias.alias for alias in data.aliases]
    if len(set(requested)) != len(requested):
        raise ConflictError("Duplicate alias in request", {"aliases": requested})

    entity = await entity_repo.create(
        entity_type=data.entity_type,
        name=data.name,
        description=data.description,
    )

    for alias_data in data.aliases:
        await alias_repo.create(entity_id=entity.id, alias=alias_data.alias)

    return EntityRead.model_validate(entity)


async def add_alias(
    entity_id: UUID,
    data: EntityAliasCreate,
    entity_repo: EntityRepository,
    alias_repo: EntityAliasRepository,
) -> EntityAliasRead:
    """Add an alias to an entity within the scoped campaign."""
    entity = await entity_repo.get(entity_id)
    if not entity:
        raise NotFoundError("Entity not found", {"entity_id": str(entity_id)})

    existing = await alias_repo.get_by_alias(entity_id, data.alias)
    if existing:
        raise ConflictError(
            "Alias already exists for this entity",
            {"entity_id": str(entity_id), "alias": data.alias},
        )

    alias = await alias_repo.create(entity_id=entity_id, alias=data.alias)
    return EntityAliasRead.model_validate(alias)
