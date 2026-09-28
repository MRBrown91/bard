"""Entity recognition schemas.

The request is a block of text and the response is what the deterministic
matcher found in it. No prompt, no model call: ADR-008 puts exact and fuzzy
matching ahead of asking an LLM to rediscover an identity that is already
recorded as a name, and this endpoint is the deterministic half.

``text`` is stripped and must then be non-empty. A blank request is a 422
rather than a 200 with no candidates, because "I sent you nothing" and "I sent
you text naming nobody" are different answers and a caller should be able to
tell them apart.
"""

from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.application.entities.entity_matching import EntityCandidate

#: Bounds the work the matcher can do. Length in characters is the input the
#: pipeline actually scales with, since it tokenizes before matching.
MAX_TEXT_LENGTH = 10_000

Text = Annotated[str, StringConstraints(strip_whitespace=True)]


class EntityRecognitionRequest(BaseModel):
    """Text to look for campaign entities in."""

    model_config = ConfigDict(extra="forbid")

    text: Annotated[Text, Field(min_length=1, max_length=MAX_TEXT_LENGTH)]


class EntityCandidateSchema(BaseModel):
    """One entity the text mentions.

    ``confidence`` is the strongest tier that matched, so a higher number means
    better evidence and the tiers never overlap. ``matched_text`` is the
    substring that produced the match, verbatim from the request.
    """

    model_config = ConfigDict(from_attributes=True)

    entity_id: UUID
    name: str
    matched_text: str
    confidence: float


class EntityRecognitionResponse(BaseModel):
    """Candidates in descending confidence order, one per entity."""

    candidates: list[EntityCandidateSchema]

    @classmethod
    def from_candidates(
        cls, candidates: list[EntityCandidate]
    ) -> "EntityRecognitionResponse":
        """Build a response from the matcher's result."""
        return cls(
            candidates=[
                EntityCandidateSchema.model_validate(candidate)
                for candidate in candidates
            ]
        )
