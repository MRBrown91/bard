"""Update and delete entity use cases."""

from uuid import UUID

from app.application.entities.matching_vocabulary import invalidate_vocabulary
from app.application.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)
from app.models.entity.entity import ALIAS_KIND_NAME
from app.repositories import EntityAliasRepository, EntityRepository
from app.schemas.entity import EntityRead, EntityUpdate

REQUIRED_FIELDS = ("name", "entity_type")


async def update_entity(
    entity_id: UUID,
    data: EntityUpdate,
    entity_repo: EntityRepository,
    alias_repo: EntityAliasRepository | None = None,
) -> EntityRead:
    """Update entity base fields.

    Only fields explicitly present in the request body are applied, so PATCH can
    clear a nullable field without disturbing the rest of the entity.

    A new name also retargets the entity's natural name alias, since that row
    is what the matcher reads. ``alias_repo`` is optional so callers that only
    edit non-name fields need not supply one; a rename without it is refused
    rather than leaving the entity matchable by a name it no longer has.
    """
    changes = data.model_dump(exclude_unset=True)

    nulled = [
        field
        for field in REQUIRED_FIELDS
        if field in changes and changes[field] is None
    ]
    if nulled:
        raise ValidationError(
            "Field cannot be null",
            {"entity_id": str(entity_id), "fields": nulled},
        )

    new_name = changes.get("name")
    if new_name is not None and alias_repo is not None:
        clash = await alias_repo.get_by_alias(entity_id, new_name)
        if clash is not None:
            raise ConflictError(
                "The new name is already an alias of this entity",
                {"entity_id": str(entity_id), "name": new_name},
            )

    if not changes:
        entity = await entity_repo.get(entity_id)
    else:
        entity = await entity_repo.update(entity_id, **changes)

    if entity is None:
        raise NotFoundError("Entity not found", {"entity_id": str(entity_id)})

    if new_name is not None:
        if alias_repo is None:
            raise ValidationError(
                "Renaming requires an alias repository to move the natural "
                "name alias",
                {"entity_id": str(entity_id)},
            )
        if not await alias_repo.rename(entity_id, new_name):
            raise NotFoundError(
                "Entity has no natural name alias to rename",
                {"entity_id": str(entity_id)},
            )

    if changes:
        # A renamed entity stops matching its old name, which only the cache
        # knows about. Description-only edits leave the vocabulary untouched.
        invalidate_vocabulary(entity_repo)
    return EntityRead.model_validate(entity)


async def soft_delete_entity(
    entity_id: UUID,
    entity_repo: EntityRepository,
) -> None:
    """Soft delete an entity, preserving it for retcons.

    The repository stamps the specialization in the same transaction. Without
    that a deleted entity would leave a specialization row that still looks
    live.
    """
    if not await entity_repo.soft_delete_with_specializations(entity_id):
        raise NotFoundError("Entity not found", {"entity_id": str(entity_id)})
    # A deleted entity must stop being recognized while its row lives on for
    # retcons, so the cached vocabulary is now wrong in the dangerous direction.
    invalidate_vocabulary(entity_repo)


async def remove_alias(
    entity_id: UUID,
    alias_id: UUID,
    entity_repo: EntityRepository,
    alias_repo: EntityAliasRepository,
) -> None:
    """Soft delete an alias belonging to an entity in the scoped campaign.

    The natural name alias is refused. It is what makes the entity matchable by
    its own name, and removing it would leave an entity that exists but can
    never be recognised by the name it is called.
    """
    entity = await entity_repo.get(entity_id)
    if not entity:
        raise NotFoundError("Entity not found", {"entity_id": str(entity_id)})

    alias = await alias_repo.get(alias_id)
    if not alias or alias.entity_id != entity_id:
        raise NotFoundError("Alias not found", {"alias_id": str(alias_id)})

    if alias.kind == ALIAS_KIND_NAME:
        raise ValidationError(
            "An entity's own name cannot be removed as an alias; rename the "
            "entity instead",
            {"entity_id": str(entity_id), "alias_id": str(alias_id)},
        )

    await alias_repo.soft_delete(alias_id)
    invalidate_vocabulary(entity_repo)
