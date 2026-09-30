"""Relationship fact CRUD API endpoints.

Campaign-level rather than nested under an entity, because a relationship is a
claim *between* two entities and neither owns it. The two entity ids arrive in
the body, which makes the campaign check in the use case load-bearing rather
than incidental — nothing in the path constrains them.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.api.dependencies import (
    CurrentCampaign,
    get_document_statement_repo,
    get_entity_repo,
    get_event_repo,
    get_player_repo,
    get_relationship_fact_audience_repo,
    get_relationship_fact_repo,
)
from app.application.facts.relationship_facts import (
    add_audience,
    create_relationship_fact,
    delete_relationship_fact,
    get_relationship_fact,
    list_relationship_facts,
    remove_audience,
    update_relationship_fact,
)
from app.repositories import (
    DocumentStatementRepository,
    EntityRepository,
    EventRepository,
    PlayerRepository,
    RelationshipFactAudienceRepository,
    RelationshipFactRepository,
)
from app.schemas.audience import (
    RelationshipFactAudienceCreate,
    RelationshipFactAudienceRead,
)
from app.schemas.fact import (
    EntityRelationshipFactCreate,
    EntityRelationshipFactList,
    EntityRelationshipFactRead,
    EntityRelationshipFactUpdate,
    EntityRelationshipFactWithAudiencesRead,
)

router = APIRouter(prefix="/api/campaigns", tags=["relationship-facts"])


@router.post(
    "/{campaign_id}/relationship-facts",
    response_model=EntityRelationshipFactRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_relationship_fact_endpoint(
    data: EntityRelationshipFactCreate,
    campaign: CurrentCampaign,
    fact_repo: Annotated[
        RelationshipFactRepository, Depends(get_relationship_fact_repo)
    ],
    entity_repo: Annotated[EntityRepository, Depends(get_entity_repo)],
    statement_repo: Annotated[
        DocumentStatementRepository, Depends(get_document_statement_repo)
    ],
    event_repo: Annotated[EventRepository, Depends(get_event_repo)],
) -> EntityRelationshipFactRead:
    """Create a relationship between two entities of this campaign.

    Both entity ids are validated against the campaign, and a self-relationship
    is refused. ``statement_id`` and ``event_id`` are optional provenance and
    are checked the same way, so a fact cannot cite another campaign's document.
    """
    return await create_relationship_fact(
        data, fact_repo, entity_repo, statement_repo, event_repo
    )


@router.get(
    "/{campaign_id}/relationship-facts",
    response_model=EntityRelationshipFactList,
)
async def list_relationship_facts_endpoint(
    campaign: CurrentCampaign,
    fact_repo: Annotated[
        RelationshipFactRepository, Depends(get_relationship_fact_repo)
    ],
    entity_repo: Annotated[EntityRepository, Depends(get_entity_repo)],
    source_entity_id: Annotated[UUID | None, Query()] = None,
    target_entity_id: Annotated[UUID | None, Query()] = None,
    relationship_type: Annotated[str | None, Query(max_length=100)] = None,
    fact_status: Annotated[str | None, Query(alias="status", max_length=30)] = None,
    event_id: Annotated[UUID | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> EntityRelationshipFactList:
    """List relationship facts, filterable by source, target, type, or status.

    ``source_entity_id`` and ``target_entity_id`` are separate filters rather
    than one direction pair, so a caller can ask what points *at* an entity
    without also receiving what it points at.
    """
    return await list_relationship_facts(
        fact_repo,
        entity_repo,
        source_entity_id=source_entity_id,
        target_entity_id=target_entity_id,
        relationship_type=relationship_type,
        status=fact_status,
        event_id=event_id,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/{campaign_id}/relationship-facts/{fact_id}",
    response_model=EntityRelationshipFactWithAudiencesRead,
)
async def get_relationship_fact_endpoint(
    fact_id: UUID,
    campaign: CurrentCampaign,
    fact_repo: Annotated[
        RelationshipFactRepository, Depends(get_relationship_fact_repo)
    ],
    audience_repo: Annotated[
        RelationshipFactAudienceRepository, Depends(get_relationship_fact_audience_repo)
    ],
) -> EntityRelationshipFactWithAudiencesRead:
    """Get one relationship fact with its audience rules."""
    return await get_relationship_fact(fact_id, fact_repo, audience_repo)


@router.patch(
    "/{campaign_id}/relationship-facts/{fact_id}",
    response_model=EntityRelationshipFactWithAudiencesRead,
)
async def update_relationship_fact_endpoint(
    fact_id: UUID,
    data: EntityRelationshipFactUpdate,
    campaign: CurrentCampaign,
    fact_repo: Annotated[
        RelationshipFactRepository, Depends(get_relationship_fact_repo)
    ],
) -> EntityRelationshipFactWithAudiencesRead:
    """Update content, confidence, importance, or status.

    The two entity ids and ``relationship_type`` are immutable; sending one is
    a 422 rather than a silent no-op.
    """
    return await update_relationship_fact(fact_id, data, fact_repo)


@router.delete(
    "/{campaign_id}/relationship-facts/{fact_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_relationship_fact_endpoint(
    fact_id: UUID,
    campaign: CurrentCampaign,
    fact_repo: Annotated[
        RelationshipFactRepository, Depends(get_relationship_fact_repo)
    ],
) -> None:
    """Soft delete a relationship fact.

    A 204 means the row is no longer readable, not that it is gone. It is
    retained so a retcon can be reversed and so materialized relationships in
    P1D.3 can be rebuilt from the facts that remain.
    """
    await delete_relationship_fact(fact_id, fact_repo)


@router.post(
    "/{campaign_id}/relationship-facts/{fact_id}/audiences",
    response_model=RelationshipFactAudienceRead,
    status_code=status.HTTP_201_CREATED,
)
async def add_audience_endpoint(
    fact_id: UUID,
    data: RelationshipFactAudienceCreate,
    campaign: CurrentCampaign,
    fact_repo: Annotated[
        RelationshipFactRepository, Depends(get_relationship_fact_repo)
    ],
    audience_repo: Annotated[
        RelationshipFactAudienceRepository, Depends(get_relationship_fact_audience_repo)
    ],
    player_repo: Annotated[PlayerRepository, Depends(get_player_repo)],
) -> RelationshipFactAudienceRead:
    """Attach an audience rule to a relationship fact."""
    return await add_audience(fact_id, data, fact_repo, audience_repo, player_repo)


@router.delete(
    "/{campaign_id}/relationship-facts/{fact_id}/audiences/{audience_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_audience_endpoint(
    fact_id: UUID,
    audience_id: UUID,
    campaign: CurrentCampaign,
    fact_repo: Annotated[
        RelationshipFactRepository, Depends(get_relationship_fact_repo)
    ],
    audience_repo: Annotated[
        RelationshipFactAudienceRepository, Depends(get_relationship_fact_audience_repo)
    ],
) -> None:
    """Soft delete an audience rule from a relationship fact."""
    await remove_audience(fact_id, audience_id, fact_repo, audience_repo)
