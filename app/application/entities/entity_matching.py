"""Deterministic entity matching interfaces."""

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class EntityCandidate:
    """A deterministic candidate entity mention."""

    entity_id: UUID
    name: str
    matched_text: str
    confidence: float


class EntityMatcher:
    """Interface boundary for deterministic entity mention matching."""

    def find_candidates(self, text: str) -> list[EntityCandidate]:
        """Return candidates found in text.

        Phase 1 intentionally has no implementation because campaign data is
        not yet wired into the service layer.
        """
        del text
        return []
