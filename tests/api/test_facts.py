"""Tests for the entity fact API endpoints.

These cover transport, error translation, and the rules the application layer
relies on: the entity in the path having to own the fact, provenance ids being
checked against the campaign, indistinguishable 404s, and fields a caller may
not repoint. Repositories are stubbed, so the database-side rules (campaign
scoping through the parent fact, audience pairing in the schema) are covered in
``test_fact_repo.py`` and ``test_audience_repo.py``.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import (
    get_current_campaign,
    get_document_statement_repo,
    get_entity_repo,
    get_event_repo,
    get_fact_audience_repo,
    get_fact_repo,
    get_player_repo,
)
from app.application.exceptions import NotFoundError
from app.main import app
from app.models import Campaign, Entity, EntityFact, EntityFactAudience
from app.repositories import (
    DocumentStatementRepository,
    EntityRepository,
    EventRepository,
    FactAudienceRepository,
    FactRepository,
    PlayerRepository,
)

NOW = datetime(2026, 1, 1, tzinfo=UTC)

BASE = "/api/campaigns/{campaign_id}/entities/{entity_id}/facts"

CREATE_BODY = {
    "fact_type": "physical_trait",
    "content": "Missing two fingers on the left hand.",
    "confidence": 0.9,
    "importance": 3,
}


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


def make_entity(campaign: Campaign, *, entity_id: UUID | None = None) -> Entity:
    """Build an entity in the campaign."""
    return Entity(
        id=entity_id or uuid4(),
        campaign_id=campaign.id,
        entity_type="actor",
        name="Sela",
        description=None,
        created_at=NOW,
        updated_at=NOW,
        deleted_at=None,
    )


def make_fact(
    campaign: Campaign,
    entity: Entity,
    *,
    fact_id: UUID | None = None,
    audiences: list[EntityFactAudience] | None = None,
    **overrides: Any,
) -> EntityFact:
    """Build a fact, with optional audience rules."""
    fields: dict[str, Any] = {
        "id": fact_id or uuid4(),
        "campaign_id": campaign.id,
        "entity_id": entity.id,
        "statement_id": None,
        "event_id": None,
        "fact_type": "physical_trait",
        "content": "Missing two fingers on the left hand.",
        "confidence": 0.9,
        "importance": 3,
        "status": "active",
        "created_at": NOW,
        "updated_at": NOW,
        "deleted_at": None,
    }
    fields.update(overrides)
    return EntityFact(audiences=audiences or [], **fields)


def make_audience(
    fact: EntityFact, *, audience_type: str = "general"
) -> EntityFactAudience:
    """Build an audience rule for a fact."""
    return EntityFactAudience(
        id=uuid4(),
        fact_id=fact.id,
        audience_type=audience_type,
        player_id=None,
        created_at=NOW,
        updated_at=NOW,
        deleted_at=None,
    )


@dataclass
class Harness:
    """Stubbed repositories plus a client."""

    client: TestClient
    campaign: Campaign
    entity: Entity
    facts: AsyncMock
    entities: AsyncMock
    statements: AsyncMock
    events: AsyncMock
    audiences: AsyncMock
    players: AsyncMock

    @property
    def url(self) -> str:
        return BASE.format(campaign_id=self.campaign.id, entity_id=self.entity.id)

    def item_url(self, fact_id: UUID) -> str:
        return f"{self.url}/{fact_id}"


def override_repository(repo: AsyncMock) -> Any:
    """Build a dependency override returning a fixed repository."""

    def dependency() -> AsyncMock:
        return repo

    return dependency


@contextmanager
def authorized() -> Iterator[Harness]:
    """Override the campaign scope and every repository the routes use."""
    campaign = make_campaign()
    entity = make_entity(campaign)

    facts = AsyncMock(spec=FactRepository)
    facts.session = AsyncMock(spec=AsyncSession)
    facts.campaign_id = campaign.id
    entities = AsyncMock(spec=EntityRepository)
    entities.session = AsyncMock(spec=AsyncSession)
    entities.campaign_id = campaign.id
    statements = AsyncMock(spec=DocumentStatementRepository)
    statements.session = AsyncMock(spec=AsyncSession)
    statements.campaign_id = campaign.id
    events = AsyncMock(spec=EventRepository)
    events.session = AsyncMock(spec=AsyncSession)
    events.campaign_id = campaign.id
    audiences = AsyncMock(spec=FactAudienceRepository)
    audiences.session = AsyncMock(spec=AsyncSession)
    audiences.campaign_id = campaign.id
    players = AsyncMock(spec=PlayerRepository)
    players.session = AsyncMock(spec=AsyncSession)
    players.campaign_id = campaign.id
    players.get.return_value = (entity, object())

    # Every entity resolves by default; individual tests override this to
    # simulate a missing entity or a fact belonging to a different one.
    entities.get.return_value = entity

    app.dependency_overrides[get_fact_repo] = override_repository(facts)
    app.dependency_overrides[get_entity_repo] = override_repository(entities)
    app.dependency_overrides[get_document_statement_repo] = override_repository(
        statements
    )
    app.dependency_overrides[get_event_repo] = override_repository(events)
    app.dependency_overrides[get_fact_audience_repo] = override_repository(audiences)
    app.dependency_overrides[get_player_repo] = override_repository(players)

    def current_campaign() -> Campaign:
        return campaign

    app.dependency_overrides[get_current_campaign] = current_campaign
    try:
        yield Harness(
            TestClient(app),
            campaign,
            entity,
            facts,
            entities,
            statements,
            events,
            audiences,
            players,
        )
    finally:
        app.dependency_overrides.clear()


class TestCreate:
    """POST the collection."""

    def test_creates_a_fact(self) -> None:
        with authorized() as h:
            h.facts.create.return_value = make_fact(h.campaign, h.entity)
            response = h.client.post(h.url, json=CREATE_BODY)
            assert response.status_code == 201
            assert response.json()["fact_type"] == "physical_trait"

    def test_entity_comes_from_the_path(self) -> None:
        with authorized() as h:
            h.facts.create.return_value = make_fact(h.campaign, h.entity)
            h.client.post(h.url, json=CREATE_BODY)
            assert h.facts.create.await_args.kwargs["entity_id"] == h.entity.id

    def test_rejects_a_campaign_in_the_body(self) -> None:
        """``extra="forbid"`` turns a wrong-scope body into a 422."""
        with authorized() as h:
            response = h.client.post(
                h.url, json={**CREATE_BODY, "campaign_id": str(uuid4())}
            )
            assert response.status_code == 422
            h.facts.create.assert_not_awaited()

    def test_rejects_an_entity_in_the_body(self) -> None:
        with authorized() as h:
            response = h.client.post(
                h.url, json={**CREATE_BODY, "entity_id": str(uuid4())}
            )
            assert response.status_code == 422
            h.facts.create.assert_not_awaited()

    def test_rejects_an_unknown_field(self) -> None:
        with authorized() as h:
            response = h.client.post(h.url, json={**CREATE_BODY, "author": "gm"})
            assert response.status_code == 422

    @pytest.mark.parametrize(
        ("field", "value"),
        [("confidence", 1.5), ("confidence", -0.1), ("importance", -1)],
    )
    def test_rejects_out_of_range_values(self, field: str, value: float) -> None:
        with authorized() as h:
            response = h.client.post(h.url, json={**CREATE_BODY, field: value})
            assert response.status_code == 422

    def test_rejects_an_unknown_status(self) -> None:
        with authorized() as h:
            response = h.client.post(h.url, json={**CREATE_BODY, "status": "maybe"})
            assert response.status_code == 422

    def test_accepts_an_empty_patch_of_defaults(self) -> None:
        """``status`` and ``importance`` default rather than being required."""
        with authorized() as h:
            h.facts.create.return_value = make_fact(h.campaign, h.entity)
            response = h.client.post(
                h.url, json={"fact_type": "history", "content": "Fled the city."}
            )
            assert response.status_code == 201
            assert response.json()["status"] == "active"


class TestProvenance:
    """A statement or event from another campaign must be refused."""

    def test_accepts_a_statement_in_the_campaign(self) -> None:
        with authorized() as h:
            h.facts.create.return_value = make_fact(h.campaign, h.entity)
            statement_id = uuid4()
            h.statements.get.return_value = object()
            response = h.client.post(
                h.url, json={**CREATE_BODY, "statement_id": str(statement_id)}
            )
            assert response.status_code == 201
            h.statements.get.assert_awaited_once_with(statement_id)

    def test_rejects_a_missing_statement(self) -> None:
        with authorized() as h:
            h.statements.get.return_value = None
            response = h.client.post(
                h.url, json={**CREATE_BODY, "statement_id": str(uuid4())}
            )
            assert response.status_code == 422
            h.facts.create.assert_not_awaited()

    def test_rejects_a_missing_event(self) -> None:
        with authorized() as h:
            h.events.get.return_value = None
            response = h.client.post(
                h.url, json={**CREATE_BODY, "event_id": str(uuid4())}
            )
            assert response.status_code == 422
            h.facts.create.assert_not_awaited()

    def test_does_not_distinguish_absent_from_foreign(self) -> None:
        """A caller learns nothing about ids outside their campaign.

        The response echoes back the id the caller supplied, which discloses
        nothing they did not already know, so the status, code, and message
        are what have to match.
        """
        with authorized() as h:
            h.statements.get.return_value = None
            absent = h.client.post(
                h.url, json={**CREATE_BODY, "statement_id": str(uuid4())}
            )
            foreign = h.client.post(
                h.url, json={**CREATE_BODY, "statement_id": str(uuid4())}
            )
            assert absent.status_code == foreign.status_code
            for key in ("code", "detail"):
                assert absent.json()[key] == foreign.json()[key], key

    def test_skips_validation_when_no_provenance_is_given(self) -> None:
        with authorized() as h:
            h.facts.create.return_value = make_fact(h.campaign, h.entity)
            response = h.client.post(h.url, json=CREATE_BODY)
            assert response.status_code == 201
            h.statements.get.assert_not_awaited()
            h.events.get.assert_not_awaited()


class TestEntityMustExist:
    """The entity in the path is checked against the campaign."""

    def test_create_404s_for_a_missing_entity(self) -> None:
        with authorized() as h:
            h.entities.get.return_value = None
            response = h.client.post(h.url, json=CREATE_BODY)
            assert response.status_code == 404
            h.facts.create.assert_not_awaited()

    def test_list_404s_for_a_missing_entity(self) -> None:
        with authorized() as h:
            h.entities.get.return_value = None
            response = h.client.get(h.url)
            assert response.status_code == 404
            h.facts.list_filtered.assert_not_awaited()


class TestList:
    """GET the collection."""

    def test_returns_items_and_a_total(self) -> None:
        with authorized() as h:
            fact = make_fact(h.campaign, h.entity)
            h.facts.list_filtered.return_value = [fact]
            h.facts.count_filtered.return_value = 1
            response = h.client.get(h.url)
            assert response.status_code == 200
            body = response.json()
            assert body["total"] == 1
            assert len(body["items"]) == 1

    def test_page_and_total_use_the_same_predicate(self) -> None:
        """The total must describe the rows a client can actually page through."""
        with authorized() as h:
            h.facts.list_filtered.return_value = []
            h.facts.count_filtered.return_value = 0
            h.client.get(h.url, params={"status": "active", "fact_type": "history"})
            listed = h.facts.list_filtered.await_args.kwargs
            counted = h.facts.count_filtered.await_args.kwargs
            for key in ("entity_id", "status", "fact_type", "event_id"):
                assert listed[key] == counted[key], key

    def test_filters_by_status_and_type(self) -> None:
        with authorized() as h:
            h.facts.list_filtered.return_value = []
            h.facts.count_filtered.return_value = 0
            h.client.get(h.url, params={"status": "invalidated", "fact_type": "lore"})
            assert h.facts.list_filtered.await_args.kwargs["status"] == "invalidated"
            assert h.facts.list_filtered.await_args.kwargs["fact_type"] == "lore"

    def test_reports_total_pages(self) -> None:
        with authorized() as h:
            h.facts.list_filtered.return_value = []
            h.facts.count_filtered.return_value = 45
            body = h.client.get(h.url, params={"page_size": 20}).json()
            assert body["total_pages"] == 3

    def test_rejects_a_zero_page(self) -> None:
        with authorized() as h:
            assert h.client.get(h.url, params={"page": 0}).status_code == 422

    def test_rejects_an_oversized_page(self) -> None:
        with authorized() as h:
            assert h.client.get(h.url, params={"page_size": 500}).status_code == 422

    def test_does_not_expose_deleted_at(self) -> None:
        with authorized() as h:
            h.facts.list_filtered.return_value = [make_fact(h.campaign, h.entity)]
            h.facts.count_filtered.return_value = 1
            assert "deleted_at" not in h.client.get(h.url).json()["items"][0]


class TestGet:
    """GET an item."""

    def test_returns_the_fact_with_audiences(self) -> None:
        with authorized() as h:
            fact = make_fact(h.campaign, h.entity)
            fact.audiences = [make_audience(fact)]
            h.facts.get.return_value = fact
            h.facts.get_with_audiences.return_value = fact
            response = h.client.get(h.item_url(fact.id))
            assert response.status_code == 200
            body = response.json()
            assert body["audiences"][0]["audience_type"] == "general"

    def test_404s_for_a_missing_fact(self) -> None:
        with authorized() as h:
            h.facts.get.return_value = None
            response = h.client.get(h.item_url(uuid4()))
            assert response.status_code == 404

    def test_404s_for_a_fact_of_another_entity(self) -> None:
        """The path names the entity, so a sibling entity's fact is not here."""
        with authorized() as h:
            other = make_entity(h.campaign)
            h.facts.get.return_value = make_fact(h.campaign, other)
            response = h.client.get(h.item_url(h.facts.get.return_value.id))
            assert response.status_code == 404
            h.facts.get_with_audiences.assert_not_awaited()

    def test_does_not_expose_deleted_at(self) -> None:
        with authorized() as h:
            fact = make_fact(h.campaign, h.entity)
            h.facts.get.return_value = fact
            h.facts.get_with_audiences.return_value = fact
            assert "deleted_at" not in h.client.get(h.item_url(fact.id)).json()


class TestUpdate:
    """PATCH an item."""

    def test_updates_the_fields_sent(self) -> None:
        with authorized() as h:
            fact = make_fact(h.campaign, h.entity)
            h.facts.get.return_value = fact
            h.facts.get_with_audiences.return_value = fact
            response = h.client.patch(h.item_url(fact.id), json={"content": "Revised"})
            assert response.status_code == 200
            assert h.facts.update.await_args.kwargs == {"content": "Revised"}

    def test_ignores_fields_that_were_not_sent(self) -> None:
        """A PATCH must not blank out fields the caller never mentioned."""
        with authorized() as h:
            fact = make_fact(h.campaign, h.entity)
            h.facts.get.return_value = fact
            h.facts.get_with_audiences.return_value = fact
            h.client.patch(h.item_url(fact.id), json={"content": "Revised"})
            assert h.facts.update.await_args.kwargs == {"content": "Revised"}

    def test_allows_every_status(self) -> None:
        """Status moves freely between the three values; P1D.5 keys off it."""
        for status in ("active", "invalidated", "superseded"):
            with authorized() as h:
                fact = make_fact(h.campaign, h.entity)
                h.facts.get.return_value = fact
                h.facts.get_with_audiences.return_value = fact
                response = h.client.patch(h.item_url(fact.id), json={"status": status})
                assert response.status_code == 200
                assert h.facts.update.await_args.kwargs == {"status": status}

    def test_rejects_repointing_provenance(self) -> None:
        """A fact's statement and event are provenance and cannot be moved."""
        for field in ("statement_id", "event_id", "fact_type", "entity_id"):
            with authorized() as h:
                fact = make_fact(h.campaign, h.entity)
                h.facts.get.return_value = fact
                body = {field: str(uuid4())}
                response = h.client.patch(h.item_url(fact.id), json=body)
                assert response.status_code == 422, field
                h.facts.update.assert_not_awaited()

    def test_404s_for_a_fact_of_another_entity(self) -> None:
        with authorized() as h:
            other = make_entity(h.campaign)
            h.facts.get.return_value = make_fact(h.campaign, other)
            assert (
                h.client.patch(h.item_url(uuid4()), json={"content": "x"}).status_code
                == 404
            )
            h.facts.update.assert_not_awaited()


class TestDelete:
    """DELETE an item."""

    def test_soft_deletes(self) -> None:
        with authorized() as h:
            fact = make_fact(h.campaign, h.entity)
            h.facts.get.return_value = fact
            h.facts.soft_delete.return_value = True
            response = h.client.delete(h.item_url(fact.id))
            assert response.status_code == 204
            h.facts.soft_delete.assert_awaited_once_with(fact.id)

    def test_404s_when_already_deleted(self) -> None:
        """A deleted fact reads as absent, so a second delete is a 404."""
        with authorized() as h:
            fact = make_fact(h.campaign, h.entity)
            h.facts.get.return_value = None
            h.facts.soft_delete.return_value = False
            assert h.client.delete(h.item_url(fact.id)).status_code == 404


class TestAudiences:
    """The audience sub-resource."""

    def test_adds_a_rule(self) -> None:
        with authorized() as h:
            fact = make_fact(h.campaign, h.entity)
            h.facts.get.return_value = fact
            h.audiences.create.return_value = make_audience(fact)
            response = h.client.post(
                f"{h.item_url(fact.id)}/audiences", json={"audience_type": "dm"}
            )
            assert response.status_code == 201
            assert h.audiences.create.await_args.kwargs["fact_id"] == fact.id

    def test_rejects_a_player_rule_with_no_player(self) -> None:
        with authorized() as h:
            fact = make_fact(h.campaign, h.entity)
            h.facts.get.return_value = fact
            response = h.client.post(
                f"{h.item_url(fact.id)}/audiences", json={"audience_type": "player"}
            )
            assert response.status_code == 422
            h.audiences.create.assert_not_awaited()

    def test_rejects_a_player_id_on_a_non_player_rule(self) -> None:
        with authorized() as h:
            fact = make_fact(h.campaign, h.entity)
            h.facts.get.return_value = fact
            response = h.client.post(
                f"{h.item_url(fact.id)}/audiences",
                json={"audience_type": "general", "player_id": str(uuid4())},
            )
            assert response.status_code == 422
            h.audiences.create.assert_not_awaited()

    def test_accepts_a_player_rule_with_a_player(self) -> None:
        with authorized() as h:
            fact = make_fact(h.campaign, h.entity)
            h.facts.get.return_value = fact
            rule = make_audience(fact, audience_type="player")
            rule.player_id = uuid4()
            h.audiences.create.return_value = rule
            response = h.client.post(
                f"{h.item_url(fact.id)}/audiences",
                json={"audience_type": "player", "player_id": str(rule.player_id)},
            )
            assert response.status_code == 201

    def test_rejects_a_fact_id_in_the_body(self) -> None:
        with authorized() as h:
            fact = make_fact(h.campaign, h.entity)
            h.facts.get.return_value = fact
            response = h.client.post(
                f"{h.item_url(fact.id)}/audiences",
                json={"audience_type": "dm", "fact_id": str(uuid4())},
            )
            assert response.status_code == 422

    def test_rejects_a_player_that_is_not_a_player(self) -> None:
        """The campaign-scoped player repository raises for anything else."""
        with authorized() as h:
            fact = make_fact(h.campaign, h.entity)
            h.facts.get.return_value = fact
            h.players.get.side_effect = NotFoundError(
                "Player not found", {"entity_id": str(uuid4())}
            )
            response = h.client.post(
                f"{h.item_url(fact.id)}/audiences",
                json={"audience_type": "player", "player_id": str(uuid4())},
            )
            assert response.status_code == 404
            h.audiences.create.assert_not_awaited()

    def test_does_not_check_a_player_for_other_rule_types(self) -> None:
        with authorized() as h:
            fact = make_fact(h.campaign, h.entity)
            h.facts.get.return_value = fact
            h.audiences.create.return_value = make_audience(fact)
            response = h.client.post(
                f"{h.item_url(fact.id)}/audiences", json={"audience_type": "dm"}
            )
            assert response.status_code == 201
            h.players.get.assert_not_awaited()

    def test_removes_a_rule(self) -> None:
        with authorized() as h:
            fact = make_fact(h.campaign, h.entity)
            rule = make_audience(fact)
            h.facts.get.return_value = fact
            h.audiences.get_by_id.return_value = rule
            h.audiences.soft_delete.return_value = True
            response = h.client.delete(
                f"{h.item_url(fact.id)}/audiences/{rule.id}"
            )
            assert response.status_code == 204
            h.audiences.soft_delete.assert_awaited_once_with(rule.id)

    def test_404s_for_a_rule_of_another_fact(self) -> None:
        """A rule id is not enough; it has to belong to the fact in the path."""
        with authorized() as h:
            fact = make_fact(h.campaign, h.entity)
            other_fact = make_fact(h.campaign, h.entity)
            rule = make_audience(other_fact)
            h.facts.get.return_value = fact
            h.audiences.get_by_id.return_value = rule
            response = h.client.delete(
                f"{h.item_url(fact.id)}/audiences/{rule.id}"
            )
            assert response.status_code == 404
            h.audiences.soft_delete.assert_not_awaited()

    def test_404s_for_a_rule_from_another_campaign(self) -> None:
        """The scoped audience repository simply will not resolve it."""
        with authorized() as h:
            fact = make_fact(h.campaign, h.entity)
            h.facts.get.return_value = fact
            h.audiences.get_by_id.return_value = None
            response = h.client.delete(
                f"{h.item_url(fact.id)}/audiences/{uuid4()}"
            )
            assert response.status_code == 404
            h.audiences.soft_delete.assert_not_awaited()
