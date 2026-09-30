"""Tests for the relationship fact API endpoints.

Same shape as ``test_facts.py``, with the differences the campaign-level
addressing creates: the two entity ids arrive in the body, so both are checked
against the campaign; they must differ; and there is no owning entity for a
nested path to protect, which is why the fact's own scoping is the whole
isolation story. Repositories are stubbed here; the campaign-scoped SQL is
covered in ``test_fact_repo.py`` and ``test_audience_repo.py``.
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
    get_player_repo,
    get_relationship_fact_audience_repo,
    get_relationship_fact_repo,
)
from app.application.exceptions import NotFoundError
from app.main import app
from app.models import (
    Campaign,
    Entity,
    EntityRelationshipFact,
    EntityRelationshipFactAudience,
)
from app.repositories import (
    DocumentStatementRepository,
    EntityRepository,
    EventRepository,
    PlayerRepository,
    RelationshipFactAudienceRepository,
    RelationshipFactRepository,
)

NOW = datetime(2026, 1, 1, tzinfo=UTC)

BASE = "/api/campaigns/{campaign_id}/relationship-facts"


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


def make_entity(campaign: Campaign, name: str = "Sela") -> Entity:
    """Build an entity in the campaign."""
    return Entity(
        id=uuid4(),
        campaign_id=campaign.id,
        entity_type="actor",
        name=name,
        description=None,
        created_at=NOW,
        updated_at=NOW,
        deleted_at=None,
    )


def make_fact(
    campaign: Campaign,
    source: Entity,
    target: Entity | None = None,
    *,
    fact_id: UUID | None = None,
    audiences: list[EntityRelationshipFactAudience] | None = None,
    **overrides: Any,
) -> EntityRelationshipFact:
    """Build a relationship fact between two entities of the campaign."""
    fields: dict[str, Any] = {
        "id": fact_id or uuid4(),
        "campaign_id": campaign.id,
        "source_entity_id": source.id,
        "target_entity_id": (target or make_entity(campaign, "Ilya")).id,
        "statement_id": None,
        "event_id": None,
        "relationship_type": "knows",
        "content": "Sela and Ilya grew up in the same quarter.",
        "confidence": 0.85,
        "importance": 2,
        "status": "active",
        "created_at": NOW,
        "updated_at": NOW,
        "deleted_at": None,
    }
    fields.update(overrides)
    return EntityRelationshipFact(audiences=audiences or [], **fields)


def make_audience(
    fact: EntityRelationshipFact, *, audience_type: str = "general"
) -> EntityRelationshipFactAudience:
    """Build an audience rule for a relationship fact."""
    return EntityRelationshipFactAudience(
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
    """Stubbed repositories plus a client and the two entities involved."""

    client: TestClient
    campaign: Campaign
    source: Entity
    target: Entity
    facts: AsyncMock
    entities: AsyncMock
    statements: AsyncMock
    events: AsyncMock
    audiences: AsyncMock
    players: AsyncMock

    @property
    def url(self) -> str:
        return BASE.format(campaign_id=self.campaign.id)

    def item_url(self, fact_id: UUID) -> str:
        return f"{self.url}/{fact_id}"

    def create_body(self, **overrides: Any) -> dict[str, Any]:
        """Build a valid create body naming this harness's two entities."""
        body: dict[str, Any] = {
            "source_entity_id": str(self.source.id),
            "target_entity_id": str(self.target.id),
            "relationship_type": "knows",
            "content": "Sela and Ilya grew up in the same quarter.",
        }
        body.update(overrides)
        return body


def override_repository(repo: AsyncMock) -> Any:
    """Build a dependency override returning a fixed repository."""

    def dependency() -> AsyncMock:
        return repo

    return dependency


@contextmanager
def authorized() -> Iterator[Harness]:
    """Override the campaign scope and every repository the routes use."""
    campaign = make_campaign()
    source = make_entity(campaign, "Sela")
    target = make_entity(campaign, "Ilya")

    facts = AsyncMock(spec=RelationshipFactRepository)
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
    audiences = AsyncMock(spec=RelationshipFactAudienceRepository)
    audiences.session = AsyncMock(spec=AsyncSession)
    audiences.campaign_id = campaign.id
    players = AsyncMock(spec=PlayerRepository)
    players.session = AsyncMock(spec=AsyncSession)
    players.campaign_id = campaign.id
    players.get.return_value = (source, object())

    # Both entities resolve by default. Individual tests override this to
    # simulate an entity belonging to a different campaign.
    entities.get.return_value = source

    app.dependency_overrides[get_relationship_fact_repo] = override_repository(facts)
    app.dependency_overrides[get_entity_repo] = override_repository(entities)
    app.dependency_overrides[get_document_statement_repo] = override_repository(
        statements
    )
    app.dependency_overrides[get_event_repo] = override_repository(events)
    app.dependency_overrides[get_relationship_fact_audience_repo] = override_repository(
        audiences
    )
    app.dependency_overrides[get_player_repo] = override_repository(players)

    def current_campaign() -> Campaign:
        return campaign

    app.dependency_overrides[get_current_campaign] = current_campaign
    try:
        yield Harness(
            TestClient(app),
            campaign,
            source,
            target,
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

    def test_creates_a_relationship_fact(self) -> None:
        with authorized() as h:
            fact = make_fact(h.campaign, h.source, h.target)
            h.facts.create.return_value = fact
            response = h.client.post(h.url, json=h.create_body())
            assert response.status_code == 201
            body = response.json()
            assert body["relationship_type"] == "knows"
            assert body["source_entity_id"] == str(h.source.id)
            assert body["target_entity_id"] == str(h.target.id)

    def test_both_entity_ids_come_from_the_body(self) -> None:
        with authorized() as h:
            h.facts.create.return_value = make_fact(h.campaign, h.source, h.target)
            h.client.post(h.url, json=h.create_body())
            created = h.facts.create.await_args.kwargs
            assert created["source_entity_id"] == h.source.id
            assert created["target_entity_id"] == h.target.id

    def test_campaign_comes_from_the_scope_not_the_body(self) -> None:
        """``extra="forbid"`` turns a wrong-scope body into a 422."""
        with authorized() as h:
            response = h.client.post(
                h.url, json=h.create_body(campaign_id=str(uuid4()))
            )
            assert response.status_code == 422
            h.facts.create.assert_not_awaited()

    def test_rejects_an_unknown_field(self) -> None:
        with authorized() as h:
            response = h.client.post(h.url, json=h.create_body(author="gm"))
            assert response.status_code == 422

    @pytest.mark.parametrize(
        ("field", "value"),
        [("confidence", 1.5), ("confidence", -0.1), ("importance", -1)],
    )
    def test_rejects_out_of_range_values(self, field: str, value: float) -> None:
        with authorized() as h:
            response = h.client.post(h.url, json=h.create_body(**{field: value}))
            assert response.status_code == 422

    def test_rejects_an_unknown_status(self) -> None:
        with authorized() as h:
            response = h.client.post(h.url, json=h.create_body(status="maybe"))
            assert response.status_code == 422

    def test_accepts_an_empty_body_of_defaults(self) -> None:
        """``status`` and ``importance`` default rather than being required."""
        with authorized() as h:
            fact = make_fact(h.campaign, h.source, h.target)
            h.facts.create.return_value = fact
            response = h.client.post(
                h.url,
                json={
                    "source_entity_id": str(h.source.id),
                    "target_entity_id": str(h.target.id),
                    "relationship_type": "sibling_of",
                "content": "Sela and Ilya share a mother.",
                },
            )
            assert response.status_code == 201
            assert response.json()["status"] == "active"


class TestEntityValidation:
    """Both ends of the relationship must be entities of this campaign."""

    def test_rejects_a_missing_source(self) -> None:
        with authorized() as h:
            h.entities.get.return_value = None
            response = h.client.post(h.url, json=h.create_body())
            assert response.status_code == 404
            h.facts.create.assert_not_awaited()

    def test_rejects_a_missing_target(self) -> None:
        """The target is checked too; a source-only check would leak."""
        with authorized() as h:
            h.entities.get.side_effect = [h.source, None]
            response = h.client.post(h.url, json=h.create_body())
            assert response.status_code == 404
            h.facts.create.assert_not_awaited()

    def test_checks_the_target_after_the_source(self) -> None:
        """Source first, so the common valid case costs one lookup."""
        with authorized() as h:
            h.entities.get.side_effect = [h.source, h.target]
            h.facts.create.return_value = make_fact(h.campaign, h.source, h.target)
            assert h.client.post(h.url, json=h.create_body()).status_code == 201
            assert h.entities.get.await_count == 2

    def test_rejects_a_self_relationship(self) -> None:
        """A relationship between an entity and itself is meaningless."""
        with authorized() as h:
            body = h.create_body(target_entity_id=str(h.source.id))
            response = h.client.post(h.url, json=body)
            assert response.status_code == 422
            h.facts.create.assert_not_awaited()
            h.entities.get.assert_not_awaited()

    def test_rejects_a_self_relationship_before_any_lookup(self) -> None:
        """The schema refuses it, so no database round trip is wasted."""
        with authorized() as h:
            body = h.create_body(target_entity_id=str(h.source.id))
            assert h.client.post(h.url, json=body).status_code == 422
            h.entities.get.assert_not_awaited()

    def test_does_not_distinguish_absent_from_foreign(self) -> None:
        """A caller learns nothing about ids outside their campaign."""
        with authorized() as h:
            h.entities.get.return_value = None
            absent = h.client.post(h.url, json=h.create_body())
            foreign = h.client.post(h.url, json=h.create_body())
            assert absent.status_code == foreign.status_code
            for key in ("code", "detail"):
                assert absent.json()[key] == foreign.json()[key], key


class TestProvenance:
    """A statement or event from another campaign must be refused."""

    def test_accepts_a_statement_in_the_campaign(self) -> None:
        with authorized() as h:
            h.facts.create.return_value = make_fact(h.campaign, h.source, h.target)
            statement_id = uuid4()
            h.statements.get.return_value = object()
            response = h.client.post(
                h.url, json=h.create_body(statement_id=str(statement_id))
            )
            assert response.status_code == 201
            h.statements.get.assert_awaited_once_with(statement_id)

    def test_rejects_a_missing_statement(self) -> None:
        with authorized() as h:
            h.statements.get.return_value = None
            response = h.client.post(
                h.url, json=h.create_body(statement_id=str(uuid4()))
            )
            assert response.status_code == 422
            h.facts.create.assert_not_awaited()

    def test_rejects_a_missing_event(self) -> None:
        with authorized() as h:
            h.events.get.return_value = None
            response = h.client.post(
                h.url, json=h.create_body(event_id=str(uuid4()))
            )
            assert response.status_code == 422
            h.facts.create.assert_not_awaited()

    def test_skips_validation_when_no_provenance_is_given(self) -> None:
        with authorized() as h:
            h.facts.create.return_value = make_fact(h.campaign, h.source, h.target)
            assert h.client.post(h.url, json=h.create_body()).status_code == 201
            h.statements.get.assert_not_awaited()
            h.events.get.assert_not_awaited()


class TestList:
    """GET the collection."""

    def test_returns_items_and_a_total(self) -> None:
        with authorized() as h:
            h.facts.list_filtered.return_value = [
                make_fact(h.campaign, h.source, h.target)
            ]
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
            h.client.get(
                h.url,
                params={
                    "status": "active",
                    "relationship_type": "knows",
                    "event_id": str(uuid4()),
                },
            )
            listed = h.facts.list_filtered.await_args.kwargs
            counted = h.facts.count_filtered.await_args.kwargs
            for key in (
                "source_entity_id",
                "target_entity_id",
                "relationship_type",
                "status",
                "event_id",
            ):
                assert listed[key] == counted[key], key

    def test_source_and_target_are_separate_filters(self) -> None:
        """Both readings of a relationship are reachable without a direction pair."""
        with authorized() as h:
            h.facts.list_filtered.return_value = []
            h.facts.count_filtered.return_value = 0
            h.client.get(
                h.url,
                params={
                    "source_entity_id": str(h.source.id),
                    "target_entity_id": str(h.target.id),
                },
            )
            listed = h.facts.list_filtered.await_args.kwargs
            assert listed["source_entity_id"] == h.source.id
            assert listed["target_entity_id"] == h.target.id

    def test_filters_by_status_and_type(self) -> None:
        with authorized() as h:
            h.facts.list_filtered.return_value = []
            h.facts.count_filtered.return_value = 0
            h.client.get(
                h.url, params={"status": "invalidated", "relationship_type": "allied"}
            )
            listed = h.facts.list_filtered.await_args.kwargs
            assert listed["status"] == "invalidated"
            assert listed["relationship_type"] == "allied"

    def test_404s_for_a_filter_entity_of_another_campaign(self) -> None:
        """A foreign entity must not silently produce an empty page.

        Returning ``[]`` would confirm nothing either way, which is the weaker
        contract the document endpoints already rejected: the caller cannot tell
        a typo from an id they were never allowed to see.
        """
        with authorized() as h:
            h.entities.get.return_value = None
            response = h.client.get(
                h.url, params={"source_entity_id": str(uuid4())}
            )
            assert response.status_code == 404
            h.facts.list_filtered.assert_not_awaited()

    def test_404s_for_a_foreign_target_filter(self) -> None:
        with authorized() as h:
            h.entities.get.return_value = None
            response = h.client.get(
                h.url, params={"target_entity_id": str(uuid4())}
            )
            assert response.status_code == 404
            h.facts.count_filtered.assert_not_awaited()

    def test_does_not_check_an_entity_when_unfiltered(self) -> None:
        """Listing the whole campaign must not require an entity lookup."""
        with authorized() as h:
            h.facts.list_filtered.return_value = []
            h.facts.count_filtered.return_value = 0
            assert h.client.get(h.url).status_code == 200
            h.entities.get.assert_not_awaited()

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
            h.facts.list_filtered.return_value = [
                make_fact(h.campaign, h.source, h.target)
            ]
            h.facts.count_filtered.return_value = 1
            assert "deleted_at" not in h.client.get(h.url).json()["items"][0]


class TestGet:
    """GET an item."""

    def test_returns_the_fact_with_audiences(self) -> None:
        with authorized() as h:
            fact = make_fact(h.campaign, h.source, h.target)
            fact.audiences = [make_audience(fact)]
            h.facts.get_with_audiences.return_value = fact
            response = h.client.get(h.item_url(fact.id))
            assert response.status_code == 200
            assert response.json()["audiences"][0]["audience_type"] == "general"

    def test_404s_for_a_missing_fact(self) -> None:
        with authorized() as h:
            h.facts.get_with_audiences.return_value = None
            assert h.client.get(h.item_url(uuid4())).status_code == 404

    def test_404s_for_a_fact_of_another_campaign(self) -> None:
        """The scoped repository will not resolve it; nothing else to check."""
        with authorized() as h:
            h.facts.get_with_audiences.return_value = None
            assert h.client.get(h.item_url(uuid4())).status_code == 404

    def test_does_not_expose_deleted_at(self) -> None:
        with authorized() as h:
            fact = make_fact(h.campaign, h.source, h.target)
            h.facts.get_with_audiences.return_value = fact
            assert "deleted_at" not in h.client.get(h.item_url(fact.id)).json()


class TestUpdate:
    """PATCH an item."""

    def test_updates_the_fields_sent(self) -> None:
        with authorized() as h:
            fact = make_fact(h.campaign, h.source, h.target)
            h.facts.get_with_audiences.return_value = fact
            response = h.client.patch(h.item_url(fact.id), json={"content": "Revised"})
            assert response.status_code == 200
            assert h.facts.update.await_args.kwargs == {"content": "Revised"}

    def test_ignores_fields_that_were_not_sent(self) -> None:
        """A PATCH must not blank out fields the caller never mentioned."""
        with authorized() as h:
            fact = make_fact(h.campaign, h.source, h.target)
            h.facts.get_with_audiences.return_value = fact
            h.client.patch(h.item_url(fact.id), json={"content": "Revised"})
            assert h.facts.update.await_args.kwargs == {"content": "Revised"}

    def test_allows_every_status(self) -> None:
        """Status moves freely between the three values; P1D.5 keys off it."""
        for status in ("active", "invalidated", "superseded"):
            with authorized() as h:
                fact = make_fact(h.campaign, h.source, h.target)
                h.facts.get_with_audiences.return_value = fact
                response = h.client.patch(h.item_url(fact.id), json={"status": status})
                assert response.status_code == 200
                assert h.facts.update.await_args.kwargs == {"status": status}

    def test_rejects_repointing_an_end(self) -> None:
        """Moving either end would rewrite the claim without a trace.

        ``extra="forbid"`` makes this a 422 rather than a silent success, which
        is the difference between a caller learning it failed and a caller
        believing it repointed a relationship it did not.
        """
        for field in ("source_entity_id", "target_entity_id"):
            with authorized() as h:
                fact = make_fact(h.campaign, h.source, h.target)
                h.facts.get_with_audiences.return_value = fact
                response = h.client.patch(
                    h.item_url(fact.id), json={field: str(uuid4())}
                )
                assert response.status_code == 422, field
                h.facts.update.assert_not_awaited()

    def test_rejects_reclassifying_the_relationship(self) -> None:
        """``relationship_type`` is the extraction's claim, not an edit."""
        with authorized() as h:
            fact = make_fact(h.campaign, h.source, h.target)
            h.facts.get_with_audiences.return_value = fact
            response = h.client.patch(
                h.item_url(fact.id), json={"relationship_type": "allied"}
            )
            assert response.status_code == 422
            h.facts.update.assert_not_awaited()

    def test_rejects_repointing_provenance(self) -> None:
        with authorized() as h:
            fact = make_fact(h.campaign, h.source, h.target)
            h.facts.get_with_audiences.return_value = fact
            for field in ("statement_id", "event_id"):
                response = h.client.patch(
                    h.item_url(fact.id), json={field: str(uuid4())}
                )
                assert response.status_code == 422, field
                h.facts.update.assert_not_awaited()

    def test_404s_for_a_fact_of_another_campaign(self) -> None:
        with authorized() as h:
            h.facts.update.return_value = None
            h.facts.get_with_audiences.return_value = None
            response = h.client.patch(
                h.item_url(uuid4()), json={"content": "x"}
            )
            assert response.status_code == 404


class TestDelete:
    """DELETE an item."""

    def test_soft_deletes(self) -> None:
        with authorized() as h:
            fact = make_fact(h.campaign, h.source, h.target)
            h.facts.soft_delete.return_value = True
            response = h.client.delete(h.item_url(fact.id))
            assert response.status_code == 204
            h.facts.soft_delete.assert_awaited_once_with(fact.id)

    def test_404s_when_already_deleted(self) -> None:
        """A deleted fact reads as absent, so a second delete is a 404."""
        with authorized() as h:
            h.facts.soft_delete.return_value = False
            assert h.client.delete(h.item_url(uuid4())).status_code == 404


class TestAudiences:
    """The audience sub-resource."""

    def test_adds_a_rule(self) -> None:
        with authorized() as h:
            fact = make_fact(h.campaign, h.source, h.target)
            h.facts.get.return_value = fact
            h.audiences.create.return_value = make_audience(fact)
            response = h.client.post(
                f"{h.item_url(fact.id)}/audiences", json={"audience_type": "dm"}
            )
            assert response.status_code == 201
            assert h.audiences.create.await_args.kwargs["fact_id"] == fact.id

    def test_404s_for_a_fact_of_another_campaign(self) -> None:
        with authorized() as h:
            h.facts.get.return_value = None
            response = h.client.post(
                f"{h.item_url(uuid4())}/audiences", json={"audience_type": "dm"}
            )
            assert response.status_code == 404
            h.audiences.create.assert_not_awaited()

    def test_rejects_a_player_rule_with_no_player(self) -> None:
        with authorized() as h:
            fact = make_fact(h.campaign, h.source, h.target)
            h.facts.get.return_value = fact
            response = h.client.post(
                f"{h.item_url(fact.id)}/audiences", json={"audience_type": "player"}
            )
            assert response.status_code == 422
            h.audiences.create.assert_not_awaited()

    def test_rejects_a_player_id_on_a_non_player_rule(self) -> None:
        with authorized() as h:
            fact = make_fact(h.campaign, h.source, h.target)
            h.facts.get.return_value = fact
            response = h.client.post(
                f"{h.item_url(fact.id)}/audiences",
                json={"audience_type": "general", "player_id": str(uuid4())},
            )
            assert response.status_code == 422
            h.audiences.create.assert_not_awaited()

    def test_accepts_a_player_rule_with_a_player(self) -> None:
        with authorized() as h:
            fact = make_fact(h.campaign, h.source, h.target)
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
            fact = make_fact(h.campaign, h.source, h.target)
            h.facts.get.return_value = fact
            response = h.client.post(
                f"{h.item_url(fact.id)}/audiences",
                json={"audience_type": "dm", "fact_id": str(uuid4())},
            )
            assert response.status_code == 422

    def test_rejects_a_player_that_is_not_a_player(self) -> None:
        """The campaign-scoped player repository raises for anything else."""
        with authorized() as h:
            fact = make_fact(h.campaign, h.source, h.target)
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
            fact = make_fact(h.campaign, h.source, h.target)
            h.facts.get.return_value = fact
            h.audiences.create.return_value = make_audience(fact)
            response = h.client.post(
                f"{h.item_url(fact.id)}/audiences", json={"audience_type": "dm"}
            )
            assert response.status_code == 201
            h.players.get.assert_not_awaited()

    def test_removes_a_rule(self) -> None:
        with authorized() as h:
            fact = make_fact(h.campaign, h.source, h.target)
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
            fact = make_fact(h.campaign, h.source, h.target)
            rule = make_audience(make_fact(h.campaign, h.source, h.target))
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
            fact = make_fact(h.campaign, h.source, h.target)
            h.facts.get.return_value = fact
            h.audiences.get_by_id.return_value = None
            response = h.client.delete(
                f"{h.item_url(fact.id)}/audiences/{uuid4()}"
            )
            assert response.status_code == 404
            h.audiences.soft_delete.assert_not_awaited()
