"""Entity recognition API endpoint."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import CurrentCampaign, get_entity_repo
from app.application.entities.entity_matching import EntityMatcher
from app.repositories import EntityRepository
from app.schemas.recognition import (
    EntityRecognitionRequest,
    EntityRecognitionResponse,
)

router = APIRouter(prefix="/api/campaigns", tags=["entity-recognition"])


@router.post(
    "/{campaign_id}/entity-recognition",
    response_model=EntityRecognitionResponse,
)
async def recognize_entities(
    data: EntityRecognitionRequest,
    campaign: CurrentCampaign,
    entity_repo: Annotated[EntityRepository, Depends(get_entity_repo)],
) -> EntityRecognitionResponse:
    """Find the campaign's entities that a block of text mentions.

    The matcher is built per request around the campaign-scoped repository, so
    the vocabulary can only ever contain entities of the caller's campaign and
    nothing about the matcher outlives the call.

    There is deliberately no ``EntityRecognitionService`` here. It would hold no
    state and forward one call, and a layer that only forwards is a layer that
    later grows a rule in the wrong place. This matches the decision for P1D.1
    to use function-level use cases rather than a ``FactService``.
    """
    matcher = EntityMatcher(entity_repo)
    candidates = await matcher.find_candidates(data.text)
    return EntityRecognitionResponse.from_candidates(candidates)
