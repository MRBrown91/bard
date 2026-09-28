"""Tests for the entity recognition endpoint.

The pipeline's scoring is covered in ``tests/application``; these cover the
transport: request validation, the campaign scope the vocabulary comes from,
and the response shape a client sees.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_campaign, get_entity_repo
from app.application.entities.matching_pipeline import (
    CASELESS_NAME_CONFIDENCE,
    EXACT_ALIAS_CONFIDENCE,
    EXACT_NAME_CONFIDENCE,
    FUZZY_CONFIDENCE,
)
from app.main import app
from app.models import Campaign
from app.repositories import EntityRepository, MatchTerm

NOW = datetime(2026, 1, 1, tzinfo=UTC)

URL = "/api/campaigns/{campaign_id}/entity-recognition"

SELA = UUID("11111111-1111-1111-1111-111111111111")
BRAM = UUID("22222222-2222-2222-2222-222222222222")
LARK = UUID("33333333-3333-3333-3333-333333333333")


def make_campaign() -> Campaign:
    """Build a campaign owned by an arbitrary user."""
    return Campaign(
        id=uuid4(),
        user_id=uuid4(),
        name="The Long Road",
        description=None,
        is_active=True,
        created_at=NOW,
        updated_at=NOW,
        deleted_at=None,
    )


@contextmanager
def authorized(*terms: MatchTerm) -> Iterator[tuple[TestClient, str, AsyncMock]]:
    """Override the campaign scope and the entity repository."""
    campaign = make_campaign()
    entities = AsyncMock(spec=EntityRepository)
    entities.session = AsyncMock(spec=AsyncSession)
    entities.campaign_id = campaign.id
    entities.list_match_terms.return_value = list(terms)

    def override() -> AsyncMock:
        return entities

    app.dependency_overrides[get_entity_repo] = override
    app.dependency_overrides[get_current_campaign] = lambda: campaign
    try:
        yield TestClient(app), URL.format(campaign_id=campaign.id), entities
    finally:
        app.dependency_overrides.clear()


def term(entity_id: UUID, name: str, value: str, is_alias: bool = False) -> MatchTerm:
    """Build a repository term row."""
    return MatchTerm(entity_id=entity_id, name=name, term=value, is_alias=is_alias)


class TestResponseShape:
    """What a client gets back."""

    def test_returns_candidates(self) -> None:
        with authorized(term(SELA, "Sela", "Sela")) as (client, url, _):
            response = client.post(url, json={"text": "Sela drew her sword."})
            assert response.status_code == 200
            assert response.json() == {
                "candidates": [
                    {
                        "entity_id": str(SELA),
                        "name": "Sela",
                        "matched_text": "Sela",
                        "confidence": EXACT_NAME_CONFIDENCE,
                    }
                ]
            }

    def test_orders_by_confidence(self) -> None:
        with authorized(
            term(SELA, "Sela", "Sela"),
            term(BRAM, "Bram", "The Viper", is_alias=True),
            term(LARK, "Duncan", "Duncan"),
        ) as (client, url, _):
            body = client.post(
                url, json={"text": "Sela met The Viper. duncan waited."}
            ).json()
            assert [c["name"] for c in body["candidates"]] == [
                "Sela",
                "Bram",
                "Duncan",
            ]
            assert [c["confidence"] for c in body["candidates"]] == [
                EXACT_NAME_CONFIDENCE,
                EXACT_ALIAS_CONFIDENCE,
                CASELESS_NAME_CONFIDENCE,
            ]

    def test_no_mentions_is_an_empty_list(self) -> None:
        with authorized(term(SELA, "Sela", "Sela")) as (client, url, _):
            response = client.post(url, json={"text": "Nothing here at all."})
            assert response.status_code == 200
            assert response.json() == {"candidates": []}

    def test_empty_campaign_is_an_empty_list(self) -> None:
        with authorized() as (client, url, _):
            response = client.post(url, json={"text": "Sela waited."})
            assert response.status_code == 200
            assert response.json() == {"candidates": []}

    def test_reports_the_substring_that_matched(self) -> None:
        with authorized(term(LARK, "LarkFellow", "LarkFellow")) as (client, url, _):
            body = client.post(url, json={"text": "You approach LarkFello."}).json()
            assert body["candidates"][0]["matched_text"] == "LarkFello"
            assert body["candidates"][0]["confidence"] == FUZZY_CONFIDENCE[1]

    def test_repeats_collapse_to_one_candidate(self) -> None:
        with authorized(term(SELA, "Sela", "Sela")) as (client, url, _):
            body = client.post(
                url, json={"text": "Sela crossed. Sela waited. Sela left."}
            ).json()
            assert len(body["candidates"]) == 1


class TestValidation:
    """The request is bounded and strict."""

    def test_rejects_an_empty_string(self) -> None:
        with authorized() as (client, url, _):
            assert client.post(url, json={"text": ""}).status_code == 422

    def test_rejects_a_whitespace_only_string(self) -> None:
        """Blank input is a mistake, not a request that matched nothing."""
        with authorized() as (client, url, _):
            assert client.post(url, json={"text": "   \n "}).status_code == 422

    def test_rejects_a_missing_text_field(self) -> None:
        with authorized() as (client, url, _):
            assert client.post(url, json={}).status_code == 422

    def test_rejects_a_non_string_text(self) -> None:
        with authorized() as (client, url, _):
            assert client.post(url, json={"text": 42}).status_code == 422

    def test_rejects_an_unknown_field(self) -> None:
        with authorized() as (client, url, _):
            body = {"text": "Sela", "limit": 5}
            assert client.post(url, json=body).status_code == 422

    def test_rejects_an_oversized_text(self) -> None:
        """Bounded input is what keeps the matcher's work bounded."""
        with authorized() as (client, url, _):
            response = client.post(url, json={"text": "x" * 10_001})
            assert response.status_code == 422

    def test_strips_surrounding_whitespace_before_matching(self) -> None:
        with authorized(term(SELA, "Sela", "Sela")) as (client, url, _):
            body = client.post(url, json={"text": "  Sela waited.  "}).json()
            assert body["candidates"][0]["matched_text"] == "Sela"


class TestCampaignScope:
    """The vocabulary comes from the caller's campaign and nowhere else."""

    def test_uses_the_scoped_repository(self) -> None:
        with authorized(term(SELA, "Sela", "Sela")) as (client, url, entities):
            client.post(url, json={"text": "Sela waited."})
            entities.list_match_terms.assert_awaited_once()

    def test_the_repository_decides_the_campaign(self) -> None:
        """The matcher holds no campaign of its own to get wrong."""
        with authorized(term(SELA, "Sela", "Sela")) as (client, url, entities):
            assert entities.campaign_id is not None
            client.post(url, json={"text": "Sela waited."})
            assert entities.list_match_terms.await_count == 1


class TestNoDatabaseForEmptyInput:
    """A request the matcher will reject anyway costs no query."""

    def test_no_query_for_blank_text(self) -> None:
        with authorized(term(SELA, "Sela", "Sela")) as (client, url, entities):
            client.post(url, json={"text": ""})
            entities.list_match_terms.assert_not_awaited()


class TestDeterminism:
    """The same request twice gives the same answer."""

    def test_repeated_requests_agree(self) -> None:
        with authorized(
            term(SELA, "Sela", "Sela"), term(BRAM, "Bram", "Bram")
        ) as (client, url, _):
            payload = {"text": "Sela met Bram. Sela left."}
            first = client.post(url, json=payload).json()
            second = client.post(url, json=payload).json()
            assert first == second


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param({"text": "Sela", "extra": True}, id="unknown-field"),
        pytest.param({"text": ""}, id="empty"),
        pytest.param({}, id="missing"),
    ],
)
def test_bad_requests_are_422(payload: dict[str, object]) -> None:
    """A table for the rejections, so the contract is visible in one place."""
    with authorized() as (client, url, _):
        assert client.post(url, json=payload).status_code == 422
