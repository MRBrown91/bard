"""Deterministic entity matching.

The matcher answers one question: which entities of this campaign does a piece
of text mention, and how confidently. It is deterministic by construction --
ADR-008 requires trying exact and fuzzy matching before asking an LLM to
rediscover an identity that is already recorded as a name.

One candidate per entity. A name mentioned three times in a transcript is one
thing the text is about, not three findings, so repeated mentions collapse to
the strongest match. The pipeline itself is in :mod:`matching_pipeline`; this
module owns the campaign vocabulary and the result contract.
"""

from dataclasses import dataclass
from uuid import UUID

from app.application.entities.matching_pipeline import (
    MatchSettings,
    TermMatch,
    build_vocabulary,
    find_term_matches,
    make_entry,
)
from app.repositories import EntityRepository


@dataclass(frozen=True, slots=True)
class EntityCandidate:
    """A deterministic candidate entity mention."""

    entity_id: UUID
    name: str
    matched_text: str
    confidence: float


class EntityMatcher:
    """Deterministic entity mention matching for one campaign.

    Constructed with a campaign-scoped repository, so isolation comes from the
    repository rather than from anything the matcher remembers. Two matchers
    over two campaigns cannot see each other's vocabulary.
    """

    def __init__(
        self,
        entity_repo: EntityRepository,
        settings: MatchSettings | None = None,
    ) -> None:
        self.entity_repo = entity_repo
        self.settings = settings or MatchSettings()

    async def find_candidates(self, text: str) -> list[EntityCandidate]:
        """Return the entities this campaign's text mentions, best first.

        One candidate per entity, carrying the highest-confidence match found
        for it. Ordered by confidence, then by where the match appeared, then
        by name and id, so the order is total and two runs over the same data
        return the same list.
        """
        if not text.strip():
            return []
        terms = await self.entity_repo.list_match_terms()
        if not terms:
            return []
        entries = [
            entry
            for term in terms
            if (entry := make_entry(
                term.entity_id, term.name, term.term, is_alias=term.is_alias
            ))
            is not None
        ]
        if not entries:
            return []
        matches = find_term_matches(text, build_vocabulary(entries), self.settings)
        return self._best_per_entity(matches)

    def _best_per_entity(self, matches: list[TermMatch]) -> list[EntityCandidate]:
        """Collapse matches to one candidate per entity, then order them."""
        best: dict[UUID, TermMatch] = {}
        for match in matches:
            current = best.get(match.entry.entity_id)
            if current is None or self._ranks_after(match, current):
                best[match.entry.entity_id] = match

        chosen = list(best.values())
        chosen.sort(
            key=lambda match: (
                -match.confidence,
                match.start,
                match.entry.name,
                str(match.entry.entity_id),
            )
        )
        return [
            EntityCandidate(
                entity_id=match.entry.entity_id,
                name=match.entry.name,
                matched_text=match.matched_text,
                confidence=match.confidence,
            )
            for match in chosen
        ]

    @staticmethod
    def _ranks_after(candidate: TermMatch, current: TermMatch) -> bool:
        """True when ``candidate`` is the better of the two for its entity.

        A tie on confidence keeps the earlier mention, so the reported
        ``matched_text`` is the first place the name was used rather than
        whichever occurrence the scan happened to reach last.
        """
        if candidate.confidence != current.confidence:
            return candidate.confidence > current.confidence
        return candidate.start < current.start
