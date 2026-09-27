"""Specialized entity CRUD use cases.

One set of functions serves all six types rather than six near-identical
modules. The repository carries the entity type, the relationship name, and
any type-specific validation, so the workflows below are identical for every
type. Splitting them per type would duplicate the orchestration without
changing any behaviour.
"""

from typing import Any
from uuid import UUID

from pydantic import BaseModel

from app.models import Entity
from app.repositories.specialized_repo import SpecializedRepository

S = SpecializedRepository[Any]


async def get_specialized(
    entity_id: UUID, repo: S
) -> tuple[Entity, Any]:
    """Get a specialization with its base entity.

    The repository raises 404 for a missing entity, an entity in another
    campaign, an entity of the wrong type, and an entity whose specialization
    has not been created yet. They are deliberately indistinguishable.
    """
    return await repo.get(entity_id)


async def list_specialized(
    repo: S,
    *,
    name_contains: str | None = None,
    offset: int = 0,
    limit: int = 20,
) -> list[tuple[Entity, Any]]:
    """List specializations for the scoped campaign."""
    return await repo.list(name_contains=name_contains, offset=offset, limit=limit)


async def count_specialized(
    repo: S, *, name_contains: str | None = None
) -> int:
    """Count specializations matching the list filters."""
    return await repo.count(name_contains=name_contains)


async def create_specialized(
    data: BaseModel, repo: S
) -> tuple[Entity, Any]:
    """Attach a specialization to an existing entity of the matching type.

    The entity is created first by a separate call, so this never has to insert
    an entity and its specialization in a mutually dependent order.
    """
    payload: dict[str, Any] = data.model_dump()
    entity_id = payload.pop("entity_id")
    return await repo.create(entity_id, **payload)


async def update_specialized(
    entity_id: UUID, data: BaseModel, repo: S
) -> tuple[Entity, Any]:
    """Update specialization fields, leaving the base entity untouched."""
    payload: dict[str, Any] = data.model_dump(exclude_unset=True)
    return await repo.update(entity_id, **payload)


async def soft_delete_specialized(entity_id: UUID, repo: S) -> None:
    """Soft delete a specialization, keeping it for retcons."""
    await repo.soft_delete(entity_id)
