"""Entity fact CRUD API endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.api.dependencies import (
    CurrentCampaign,
    get_document_statement_repo,
    get_entity_repo,
    get_event_repo,
    get_fact_audience_repo,
    get_fact_repo,
    get_player_repo,
)
from app.application.facts.facts import (
    add_audience,
    create_fact,
    delete_fact,
    get_fact,
    list_facts,
    remove_audience,
    update_fact,
)
from app.repositories import (
    DocumentStatementRepository,
    EntityRepository,
    EventRepository,
    FactAudienceRepository,
    FactRepository,
    PlayerRepository,
)
from app.schemas.audience import FactAudienceCreate, FactAudienceRead
from app.schemas.fact import (
    EntityFactCreate,
    EntityFactList,
    EntityFactRead,
    EntityFactUpdate,
    EntityFactWithAudiencesRead,
)

router = APIRouter(prefix="/api/campaigns", tags=["facts"])


@router.post(
    "/{campaign_id}/entities/{entity_id}/facts",
    response_model=EntityFactRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_fact_endpoint(
    entity_id: UUID,
    data: EntityFactCreate,
    campaign: CurrentCampaign,
    fact_repo: Annotated[FactRepository, Depends(get_fact_repo)],
    entity_repo: Annotated[EntityRepository, Depends(get_entity_repo)],
    statement_repo: Annotated[
        DocumentStatementRepository, Depends(get_document_statement_repo)
    ],
    event_repo: Annotated[EventRepository, Depends(get_event_repo)],
) -> EntityFactRead:
    """Create a fact about an entity."""
    return await create_fact(
        entity_id, data, fact_repo, entity_repo, statement_repo, event_repo
    )


@router.get(
    "/{campaign_id}/entities/{entity_id}/facts",
    response_model=EntityFactList,
)
async def list_facts_endpoint(
    entity_id: UUID,
    campaign: CurrentCampaign,
    fact_repo: Annotated[FactRepository, Depends(get_fact_repo)],
    entity_repo: Annotated[EntityRepository, Depends(get_entity_repo)],
    fact_status: Annotated[
        str | None, Query(alias="status", max_length=30)
    ] = None,
    fact_type: Annotated[str | None, Query(max_length=100)] = None,
    event_id: Annotated[UUID | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> EntityFactList:
    """List the facts of one entity."""
    return await list_facts(
        entity_id,
        fact_repo,
        entity_repo,
        status=fact_status,
        fact_type=fact_type,
        event_id=event_id,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/{campaign_id}/entities/{entity_id}/facts/{fact_id}",
    response_model=EntityFactWithAudiencesRead,
)
async def get_fact_endpoint(
    entity_id: UUID,
    fact_id: UUID,
    campaign: CurrentCampaign,
    fact_repo: Annotated[FactRepository, Depends(get_fact_repo)],
    audience_repo: Annotated[
        FactAudienceRepository, Depends(get_fact_audience_repo)
    ],
) -> EntityFactWithAudiencesRead:
    """Get a fact with its audience rules."""
    return await get_fact(entity_id, fact_id, fact_repo, audience_repo)


@router.patch(
    "/{campaign_id}/entities/{entity_id}/facts/{fact_id}",
    response_model=EntityFactWithAudiencesRead,
)
async def update_fact_endpoint(
    entity_id: UUID,
    fact_id: UUID,
    data: EntityFactUpdate,
    campaign: CurrentCampaign,
    fact_repo: Annotated[FactRepository, Depends(get_fact_repo)],
) -> EntityFactWithAudiencesRead:
    """Update the fields the request mentions."""
    return await update_fact(entity_id, fact_id, data, fact_repo)


@router.delete(
    "/{campaign_id}/entities/{entity_id}/facts/{fact_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_fact_endpoint(
    entity_id: UUID,
    fact_id: UUID,
    campaign: CurrentCampaign,
    fact_repo: Annotated[FactRepository, Depends(get_fact_repo)],
) -> None:
    """Soft delete a fact."""
    await delete_fact(entity_id, fact_id, fact_repo)


@router.post(
    "/{campaign_id}/entities/{entity_id}/facts/{fact_id}/audiences",
    response_model=FactAudienceRead,
    status_code=status.HTTP_201_CREATED,
)
async def add_audience_endpoint(
    entity_id: UUID,
    fact_id: UUID,
    data: FactAudienceCreate,
    campaign: CurrentCampaign,
    fact_repo: Annotated[FactRepository, Depends(get_fact_repo)],
    audience_repo: Annotated[
        FactAudienceRepository, Depends(get_fact_audience_repo)
    ],
    player_repo: Annotated[PlayerRepository, Depends(get_player_repo)],
) -> FactAudienceRead:
    """Attach an audience rule to a fact."""
    return await add_audience(
        entity_id, fact_id, data, fact_repo, audience_repo, player_repo
    )


@router.delete(
    "/{campaign_id}/entities/{entity_id}/facts/{fact_id}/audiences/{audience_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_audience_endpoint(
    entity_id: UUID,
    fact_id: UUID,
    audience_id: UUID,
    campaign: CurrentCampaign,
    fact_repo: Annotated[FactRepository, Depends(get_fact_repo)],
    audience_repo: Annotated[
        FactAudienceRepository, Depends(get_fact_audience_repo)
    ],
) -> None:
    """Soft delete an audience rule from a fact."""
    await remove_audience(
        entity_id, fact_id, audience_id, fact_repo, audience_repo
    )
