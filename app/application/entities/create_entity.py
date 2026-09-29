"""Create entity use cases."""

from uuid import UUID

from app.application.entities.matching_vocabulary import invalidate_vocabulary
from app.application.exceptions import ConflictError, NotFoundError
from app.models.entity.entity import ALIAS_KIND_ALIAS, ALIAS_KIND_NAME
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
    if data.name in requested:
        raise ConflictError(
            "An alias cannot duplicate the entity's own name",
            {"name": data.name},
        )

    entity = await entity_repo.create(
        entity_type=data.entity_type,
        name=data.name,
        description=data.description,
    )

    # The entity's own name is held here as a name row, so that every term the
    # matcher can recognise lives in this one table. See ADR-027.
    await alias_repo.create(
        entity_id=entity.id, alias=data.name, kind=ALIAS_KIND_NAME
    )

    for alias_data in data.aliases:
        await alias_repo.create(
            entity_id=entity.id,
            alias=alias_data.alias,
            kind=ALIAS_KIND_ALIAS,
        )

    # A new name and new aliases are both new matchable terms.
    invalidate_vocabulary(entity_repo)
    return EntityRead.model_validate(entity)


async def add_alias(
    entity_id: UUID,
    data: EntityAliasCreate,
    entity_repo: EntityRepository,
    alias_repo: EntityAliasRepository,
) -> EntityAliasRead:
    """Add an alias to an entity within the scoped campaign.

    An entity's natural name alias is already a row in this table, so the
    unique index would reject the duplicate anyway. Catching it here means the
    caller learns *why*, rather than getting a constraint violation.
    """
    entity = await entity_repo.get(entity_id)
    if not entity:
        raise NotFoundError("Entity not found", {"entity_id": str(entity_id)})

    if data.alias == entity.name:
        raise ConflictError(
            "Alias is already the entity's own name",
            {"entity_id": str(entity_id), "alias": data.alias},
        )

    existing = await alias_repo.get_by_alias(entity_id, data.alias)
    if existing:
        raise ConflictError(
            "Alias already exists for this entity",
            {"entity_id": str(entity_id), "alias": data.alias},
        )

    alias = await alias_repo.create(
        entity_id=entity_id, alias=data.alias, kind=ALIAS_KIND_ALIAS
    )
    invalidate_vocabulary(entity_repo)
    return EntityAliasRead.model_validate(alias)
