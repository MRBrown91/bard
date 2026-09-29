"""Tests for the entity matcher.

The pipeline's own scoring is covered in ``test_matching_pipeline.py``. What is
left here is the part the matcher owns: loading the campaign vocabulary and
collapsing matches to one candidate per entity.
"""

from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from app.application.entities.entity_matching import EntityCandidate, EntityMatcher
from app.application.entities.matching_pipeline import (
    CASELESS_NAME_CONFIDENCE,
    EXACT_ALIAS_CONFIDENCE,
    EXACT_NAME_CONFIDENCE,
    FUZZY_CONFIDENCE,
    MatchSettings,
)
from app.repositories import EntityRepository, MatchTerm

SELA = UUID("11111111-1111-1111-1111-111111111111")
BRAM = UUID("22222222-2222-2222-2222-222222222222")
LARK = UUID("33333333-3333-3333-3333-333333333333")


def term(
    entity_id: UUID, name: str, term: str, is_alias: bool = False
) -> MatchTerm:
    """Build a repository term row."""
    return MatchTerm(entity_id=entity_id, name=name, term=term, is_alias=is_alias)


def matcher(
    *terms: MatchTerm, settings: MatchSettings | None = None
) -> tuple[EntityMatcher, AsyncMock]:
    """Build a matcher over a stubbed repository holding these terms.

    Each matcher gets its own campaign id so the process-wide vocabulary cache
    cannot serve one test's terms to another. The stub keeps a real attribute
    here rather than a mock, because the matcher reads it to decide whether the
    result may be cached at all.
    """
    repo = AsyncMock(spec=EntityRepository)
    repo.campaign_id = uuid4()
    repo.list_match_terms.return_value = list(terms)
    return EntityMatcher(repo, settings), repo


class TestCandidates:
    """The result contract."""

    @pytest.mark.asyncio
    async def test_finds_a_named_entity(self) -> None:
        m, _ = matcher(term(SELA, "Sela", "Sela"))
        found = await m.find_candidates("Sela drew her sword.")
        assert found == [
            EntityCandidate(
                entity_id=SELA,
                name="Sela",
                matched_text="Sela",
                confidence=EXACT_NAME_CONFIDENCE,
            )
        ]

    @pytest.mark.asyncio
    async def test_returns_the_entity_name_for_an_alias_hit(self) -> None:
        """A hit on the alias still labels the result with the real name."""
        m, _ = matcher(term(SELA, "Sela", "The Viper", is_alias=True))
        found = await m.find_candidates("The Viper waited.")
        assert found[0].name == "Sela"
        assert found[0].matched_text == "The Viper"
        assert found[0].confidence == EXACT_ALIAS_CONFIDENCE

    @pytest.mark.asyncio
    async def test_orders_by_confidence(self) -> None:
        """Three entities, three tiers, most confident first."""
        m, _ = matcher(
            term(SELA, "Sela", "Sela"),
            term(BRAM, "Bram", "The Viper", is_alias=True),
            term(LARK, "Duncan", "Duncan"),
        )
        found = await m.find_candidates("Sela met The Viper. duncan waited.")
        assert [c.name for c in found] == ["Sela", "Bram", "Duncan"]
        assert [c.confidence for c in found] == [
            EXACT_NAME_CONFIDENCE,
            EXACT_ALIAS_CONFIDENCE,
            CASELESS_NAME_CONFIDENCE,
        ]

    @pytest.mark.asyncio
    async def test_no_mentions_is_empty(self) -> None:
        m, _ = matcher(term(SELA, "Sela", "Sela"))
        assert await m.find_candidates("Nothing to report.") == []


class TestOneCandidatePerEntity:
    """Repeated mentions collapse, keeping the strongest."""

    @pytest.mark.asyncio
    async def test_repeated_name_is_one_candidate(self) -> None:
        m, _ = matcher(term(SELA, "Sela", "Sela"))
        found = await m.find_candidates("Sela crossed. Sela waited. Sela left.")
        assert [c.entity_id for c in found] == [SELA]

    @pytest.mark.asyncio
    async def test_strongest_tier_is_kept(self) -> None:
        """The word appears three times, once with the wrong case."""
        m, _ = matcher(term(SELA, "Sela", "Sela"))
        found = await m.find_candidates("Sela. sela. Sela.")
        assert [c.confidence for c in found] == [EXACT_NAME_CONFIDENCE]

    @pytest.mark.asyncio
    async def test_tie_keeps_the_earlier_mention(self) -> None:
        m, _ = matcher(term(SELA, "Sela", "Sela"))
        found = await m.find_candidates("Sela first. Sela second.")
        assert found[0].matched_text == "Sela"

    @pytest.mark.asyncio
    async def test_a_name_and_its_alias_collapse_to_one(self) -> None:
        m, _ = matcher(
            term(SELA, "Sela", "Sela"), term(SELA, "Sela", "The Viper", is_alias=True)
        )
        found = await m.find_candidates("Sela, known as the Viper, waited.")
        assert [c.entity_id for c in found] == [SELA]
        assert found[0].confidence == EXACT_NAME_CONFIDENCE

    @pytest.mark.asyncio
    async def test_two_entities_sharing_a_name_both_come_back(self) -> None:
        """The schema permits it, so both are reported."""
        other = uuid4()
        m, _ = matcher(term(SELA, "Sela", "Sela"), term(other, "Sela", "Sela"))
        found = await m.find_candidates("Sela waited.")
        assert {c.entity_id for c in found} == {SELA, other}

    @pytest.mark.asyncio
    async def test_distinct_entities_are_all_reported(self) -> None:
        m, _ = matcher(
            term(SELA, "Sela", "Sela"),
            term(BRAM, "Bram", "Bram"),
            term(LARK, "LarkFellow", "LarkFellow"),
        )
        found = await m.find_candidates("Sela met Bram near LarkFello.")
        assert {c.entity_id for c in found} == {SELA, BRAM, LARK}
        assert [c.confidence for c in found if c.entity_id == LARK] == [
            FUZZY_CONFIDENCE[1]
        ]


class TestEmptyInput:
    """Nothing to match is not an error, and costs no query."""

    @pytest.mark.asyncio
    async def test_empty_text_skips_the_query(self) -> None:
        m, repo = matcher(term(SELA, "Sela", "Sela"))
        assert await m.find_candidates("") == []
        repo.list_match_terms.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_whitespace_skips_the_query(self) -> None:
        m, repo = matcher(term(SELA, "Sela", "Sela"))
        assert await m.find_candidates("  \n\t ") == []
        repo.list_match_terms.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_empty_campaign_returns_nothing(self) -> None:
        m, _ = matcher()
        assert await m.find_candidates("Sela waited.") == []

    @pytest.mark.asyncio
    async def test_campaign_with_only_blank_terms(self) -> None:
        m, _ = matcher(term(SELA, "Sela", "  "))
        assert await m.find_candidates("Sela waited.") == []


class TestSettings:
    """Settings reach the pipeline."""

    @pytest.mark.asyncio
    async def test_disabling_fuzzy_drops_typo_matches(self) -> None:
        m, _ = matcher(
            term(LARK, "LarkFellow", "LarkFellow"),
            settings=MatchSettings(fuzzy_enabled=False),
        )
        assert await m.find_candidates("LarkFello waited.") == []
        assert await m.find_candidates("LarkFellow waited.") != []


class TestDeterminism:
    """Same data, same answer."""

    @pytest.mark.asyncio
    async def test_row_order_does_not_change_the_result(self) -> None:
        terms = [
            term(SELA, "Sela", "Sela"),
            term(BRAM, "Bram", "Bram"),
            term(LARK, "LarkFellow", "LarkFellow"),
        ]
        text = "Sela met Bram near LarkFellow."
        first, _ = matcher(*terms)
        second, _ = matcher(*reversed(terms))
        assert await first.find_candidates(text) == await second.find_candidates(text)

    @pytest.mark.asyncio
    async def test_repeated_calls_agree(self) -> None:
        m, _ = matcher(term(SELA, "Sela", "Sela"), term(BRAM, "Bram", "Bram"))
        text = "Sela met Bram. Sela left."
        assert await m.find_candidates(text) == await m.find_candidates(text)
