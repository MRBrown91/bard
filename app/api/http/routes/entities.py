"""Entity and alias CRUD API endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.api.dependencies import (
    CurrentCampaign,
    get_entity_alias_repo,
    get_entity_repo,
)
from app.application.entities.create_entity import add_alias, create_entity
from app.application.entities.get_entity import get_entity_with_aliases, list_entities
from app.application.entities.update_entity import (
    remove_alias,
    soft_delete_entity,
    update_entity,
)
from app.repositories import EntityAliasRepository, EntityRepository
from app.schemas.entity import (
    EntityAliasCreate,
    EntityAliasRead,
    EntityCreate,
    EntityList,
    EntityRead,
    EntityUpdate,
    EntityWithAliasesRead,
)

router = APIRouter(prefix="/api/campaigns", tags=["entities"])


@router.post(
    "/{campaign_id}/entities",
    response_model=EntityRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_entity_endpoint(
    data: EntityCreate,
    campaign: CurrentCampaign,
    entity_repo: Annotated[EntityRepository, Depends(get_entity_repo)],
    alias_repo: Annotated[EntityAliasRepository, Depends(get_entity_alias_repo)],
) -> EntityRead:
    """Create a new entity with optional aliases."""
    return await create_entity(data, entity_repo, alias_repo)


@router.get(
    "/{campaign_id}/entities",
    response_model=EntityList,
)
async def list_entities_endpoint(
    campaign: CurrentCampaign,
    entity_repo: Annotated[EntityRepository, Depends(get_entity_repo)],
    entity_type: Annotated[str | None, Query(max_length=50)] = None,
    name_contains: Annotated[str | None, Query(max_length=255)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> EntityList:
    """List entities with optional filters."""
    entities, total = await list_entities(
        entity_repo,
        entity_type=entity_type,
        name_contains=name_contains,
        offset=(page - 1) * page_size,
        limit=page_size,
    )
    return EntityList(
        items=entities,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size,
    )


@router.get(
    "/{campaign_id}/entities/{entity_id}",
    response_model=EntityWithAliasesRead,
)
async def get_entity_endpoint(
    entity_id: UUID,
    campaign: CurrentCampaign,
    entity_repo: Annotated[EntityRepository, Depends(get_entity_repo)],
) -> EntityWithAliasesRead:
    """Get entity with its aliases."""
    return await get_entity_with_aliases(entity_id, entity_repo)


@router.patch(
    "/{campaign_id}/entities/{entity_id}",
    response_model=EntityRead,
)
async def update_entity_endpoint(
    entity_id: UUID,
    data: EntityUpdate,
    campaign: CurrentCampaign,
    entity_repo: Annotated[EntityRepository, Depends(get_entity_repo)],
    alias_repo: Annotated[EntityAliasRepository, Depends(get_entity_alias_repo)],
) -> EntityRead:
    """Update entity base fields."""
    return await update_entity(entity_id, data, entity_repo, alias_repo)


@router.delete(
    "/{campaign_id}/entities/{entity_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_entity_endpoint(
    entity_id: UUID,
    campaign: CurrentCampaign,
    entity_repo: Annotated[EntityRepository, Depends(get_entity_repo)],
) -> None:
    """Soft delete entity."""
    await soft_delete_entity(entity_id, entity_repo)


@router.post(
    "/{campaign_id}/entities/{entity_id}/aliases",
    response_model=EntityAliasRead,
    status_code=status.HTTP_201_CREATED,
)
async def add_alias_endpoint(
    entity_id: UUID,
    data: EntityAliasCreate,
    campaign: CurrentCampaign,
    entity_repo: Annotated[EntityRepository, Depends(get_entity_repo)],
    alias_repo: Annotated[EntityAliasRepository, Depends(get_entity_alias_repo)],
) -> EntityAliasRead:
    """Add an alias to an entity."""
    return await add_alias(entity_id, data, entity_repo, alias_repo)


@router.delete(
    "/{campaign_id}/entities/{entity_id}/aliases/{alias_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_alias_endpoint(
    entity_id: UUID,
    alias_id: UUID,
    campaign: CurrentCampaign,
    entity_repo: Annotated[EntityRepository, Depends(get_entity_repo)],
    alias_repo: Annotated[EntityAliasRepository, Depends(get_entity_alias_repo)],
) -> None:
    """Soft delete an alias from an entity."""
    await remove_alias(entity_id, alias_id, entity_repo, alias_repo)
