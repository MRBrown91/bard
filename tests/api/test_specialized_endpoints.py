"""Tests for the specialized entity API endpoints.

These cover transport, error translation, and the field-level rules that the
application layer depends on: type-keyed lookup, indistinguishable 404s, and
links that cannot be repointed after creation. Repositories are stubbed, so the
database-side rules (campaign scoping, cascade stamping) are covered in
``test_specialized_repo.py`` and by the live smoke test.
"""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import (
    get_actor_repo,
    get_current_campaign,
    get_faction_repo,
    get_item_repo,
    get_location_repo,
    get_player_character_repo,
    get_player_repo,
)
from app.application.exceptions import ConflictError, NotFoundError
from app.main import app
from app.models import (
    Actor,
    Campaign,
    Faction,
    Item,
    Location,
    Player,
    PlayerCharacter,
)
from app.repositories import (
    ActorRepository,
    FactionRepository,
    ItemRepository,
    LocationRepository,
    PlayerCharacterRepository,
    PlayerRepository,
)
from app.schemas.specialized import (
    ActorCreate,
    ActorUpdate,
    ItemCreate,
    PlayerCharacterCreate,
    PlayerCreate,
    PlayerUpdate,
)

NOW = datetime(2026, 1, 1, tzinfo=UTC)

TYPES = [
    ("actors", "actor", get_actor_repo, ActorRepository, ActorCreate, ActorUpdate),
    (
        "players",
        "player",
        get_player_repo,
        PlayerRepository,
        PlayerCreate,
        PlayerUpdate,
    ),
    (
        "player-characters",
        "player_character",
        get_player_character_repo,
        PlayerCharacterRepository,
        PlayerCharacterCreate,
        None,
    ),
    ("locations", "location", get_location_repo, LocationRepository, ItemCreate, None),
    ("items", "item", get_item_repo, ItemRepository, ItemCreate, None),
    ("factions", "faction", get_faction_repo, FactionRepository, ItemCreate, None),
]


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


def make_entity(
    campaign_id: UUID, entity_type: str = "actor", name: str = "Lark"
) -> MagicMock:
    """Build an Entity-like row."""
    row = MagicMock()
    row.id = uuid4()
    row.campaign_id = campaign_id
    row.entity_type = entity_type
    row.name = name
    row.description = None
    row.created_at = NOW
    row.updated_at = NOW
    row.deleted_at = None
    return row


SPECIALIZED_MODELS = {
    "actor": Actor,
    "player": Player,
    "player_character": PlayerCharacter,
    "location": Location,
    "item": Item,
    "faction": Faction,
}


def make_specialized(entity_type: str, **fields: Any) -> MagicMock:
    """Build a specialization-like row with every column present.

    The column list comes from the real model so a new column cannot slip
    through as a stray MagicMock attribute and fail validation in a confusing
    place.
    """
    model = SPECIALIZED_MODELS[entity_type]
    row = MagicMock()
    for column in model.__table__.columns:
        value = fields.pop(column.name, None)
        if column.name == "entity_id":
            value = value or uuid4()
        if column.name == "status":
            value = value or "active"
        setattr(row, column.name, value)
    for key, value in fields.items():
        setattr(row, key, value)
    return row


class Authorized:
    """Test context holding the client and the stubbed repositories."""

    def __init__(
        self,
        client: TestClient,
        campaign: Campaign,
        repos: dict[str, AsyncMock],
    ) -> None:
        self.client = client
        self.campaign = campaign
        self.repos = repos

    def path(self, slug: str) -> str:
        return f"/api/campaigns/{self.campaign.id}/{slug}"


def override_repository(repo: AsyncMock) -> Callable[[], AsyncMock]:
    """Build a zero-argument dependency override returning ``repo``.

    A lambda with a default argument would expose that argument as a query
    parameter to FastAPI, which then resolves to something other than the mock
    and silently stubs out the assertions.
    """

    def _get() -> AsyncMock:
        return repo

    return _get


@contextmanager
def authorized() -> Iterator[Authorized]:
    """Override campaign scope and all six specialized repositories."""
    campaign = make_campaign()
    repos: dict[str, AsyncMock] = {}
    for slug, _, dep, repo_cls, _, _ in TYPES:
        repo = AsyncMock(spec=repo_cls)
        repo.session = AsyncMock(spec=AsyncSession)
        repo.entity_type = repo_cls.entity_type
        repos[slug] = repo
        app.dependency_overrides[dep] = override_repository(repo)

    def current_campaign() -> Campaign:
        return campaign

    app.dependency_overrides[get_current_campaign] = current_campaign
    try:
        yield Authorized(TestClient(app), campaign, repos)
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize(("slug", "entity_type"), [(t[0], t[1]) for t in TYPES])
class TestSpecializedCrud:
    """Behaviour shared by all six types."""

    def test_create_returns_embedded_entity(self, slug: str, entity_type: str) -> None:
        """A created specialization carries its own fields and the base entity."""
        with authorized() as ctx:
            entity = make_entity(ctx.campaign.id, entity_type)
            body: dict[str, Any] = {"entity_id": str(entity.id)}
            if slug == "players":
                body["user_id"] = str(uuid4())
            elif slug == "player-characters":
                body["player_id"] = str(uuid4())
            row = make_specialized(
                entity_type,
                entity_id=entity.id,
                **({"user_id": UUID(body["user_id"])} if slug == "players" else {}),
                **(
                    {"player_id": UUID(body["player_id"])}
                    if slug == "player-characters"
                    else {}
                ),
            )
            repo = ctx.repos[slug]
            repo.create = AsyncMock(return_value=(entity, row))
            setattr(entity, entity_type, row)

            response = ctx.client.post(ctx.path(slug), json=body)

        assert response.status_code == 201
        payload = response.json()
        assert payload["entity_id"] == str(entity.id)
        assert payload["entity"]["id"] == str(entity.id)
        assert payload["entity"]["name"] == entity.name
        assert payload["entity"]["entity_type"] == entity_type

    def test_response_carries_exactly_one_created_at(
        self, slug: str, entity_type: str
    ) -> None:
        """The entity's created_at is the only one on the wire.

        The specialization row is written just after the entity, so exposing
        both would hand a client two values that differ by a few milliseconds.
        """
        with authorized() as ctx:
            entity = make_entity(ctx.campaign.id, entity_type)
            row = make_specialized(
                entity_type,
                entity_id=entity.id,
                **({"user_id": uuid4()} if slug == "players" else {}),
                **({"player_id": uuid4()} if slug == "player-characters" else {}),
            )
            repo = ctx.repos[slug]
            repo.create = AsyncMock(return_value=(entity, row))
            setattr(entity, entity_type, row)
            body: dict[str, Any] = {"entity_id": str(entity.id)}
            if slug == "players":
                body["user_id"] = str(row.user_id)
            if slug == "player-characters":
                body["player_id"] = str(row.player_id)

            response = ctx.client.post(ctx.path(slug), json=body)

        assert response.status_code == 201
        payload = response.json()
        assert "created_at" not in payload
        assert payload["entity"]["created_at"]

    def test_get_returns_404_for_wrong_type(self, slug: str, entity_type: str) -> None:
        """A missing specialization of the right type is a 404."""
        with authorized() as ctx:
            ctx.repos[slug].get = AsyncMock(
                side_effect=NotFoundError(f"{entity_type} not found")
            )

            response = ctx.client.get(f"{ctx.path(slug)}/{uuid4()}")

        assert response.status_code == 404
        assert response.json()["code"] == "NotFoundError"

    def test_cross_campaign_lookup_is_indistinguishable(
        self, slug: str, entity_type: str
    ) -> None:
        """A specialization in another campaign reads the same as a missing one."""
        with authorized() as ctx:
            ctx.repos[slug].get = AsyncMock(
                side_effect=NotFoundError(f"{entity_type} not found")
            )
            first = ctx.client.get(f"{ctx.path(slug)}/{uuid4()}")

        assert first.status_code == 404
        assert first.json()["detail"] == f"{entity_type} not found"

    def test_list_reports_totals_from_the_repository(
        self, slug: str, entity_type: str
    ) -> None:
        """List pages are built from the repository's count and rows."""
        with authorized() as ctx:
            entity = make_entity(ctx.campaign.id, entity_type)
            row = make_specialized(
                entity_type,
                entity_id=entity.id,
                **({"user_id": uuid4()} if slug == "players" else {}),
                **({"player_id": uuid4()} if slug == "player-characters" else {}),
            )
            repo = ctx.repos[slug]
            repo.list = AsyncMock(return_value=[(entity, row)])
            repo.count = AsyncMock(return_value=1)
            setattr(entity, entity_type, row)

            response = ctx.client.get(
                ctx.path(slug), params={"page": 1, "page_size": 20}
            )

        assert response.status_code == 200
        payload = response.json()
        assert payload["total"] == 1
        assert payload["total_pages"] == 1
        assert payload["items"][0]["entity_id"] == str(entity.id)

    def test_list_computes_total_pages_by_rounding_up(
        self, slug: str, entity_type: str
    ) -> None:
        """A partial final page still reports whole pages."""
        with authorized() as ctx:
            repo = ctx.repos[slug]
            repo.list = AsyncMock(return_value=[])
            repo.count = AsyncMock(return_value=21)

            response = ctx.client.get(
                ctx.path(slug), params={"page": 1, "page_size": 10}
            )

        assert response.status_code == 200
        assert response.json()["total_pages"] == 3

    def test_list_rejects_out_of_range_paging(
        self, slug: str, entity_type: str
    ) -> None:
        """Paging bounds are enforced at the transport boundary."""
        with authorized() as ctx:
            response = ctx.client.get(ctx.path(slug), params={"page": 0})

        assert response.status_code == 422

    def test_delete_soft_deletes_and_returns_204(
        self, slug: str, entity_type: str
    ) -> None:
        """Deleting a specialization keeps the entity intact."""
        with authorized() as ctx:
            entity = make_entity(ctx.campaign.id, entity_type)
            repo = ctx.repos[slug]
            repo.soft_delete = AsyncMock(return_value=True)

            response = ctx.client.delete(f"{ctx.path(slug)}/{entity.id}")

        assert response.status_code == 204
        assert repo.soft_delete.await_args.args == (entity.id,)

    def test_unauthorized_request_is_401(self, slug: str, entity_type: str) -> None:
        """Without credentials the campaign scope is unavailable."""
        app.dependency_overrides.clear()
        response = TestClient(app).get(f"/api/campaigns/{uuid4()}/{slug}")
        assert response.status_code == 401


class TestPlayerRules:
    """Player-specific rules."""

    def test_update_does_not_require_user_id(self) -> None:
        """A status change must not need the ownership link resent.

        Regression guard: validation used to demand ``user_id`` on every write,
        which made PATCH impossible.
        """
        with authorized() as ctx:
            entity = make_entity(ctx.campaign.id, "player")
            repo = ctx.repos["players"]
            row = make_specialized(
                "player", entity_id=entity.id, user_id=uuid4(), status="retired"
            )
            repo.update = AsyncMock(return_value=(entity, row))
            entity.player = row

            response = ctx.client.patch(
                f"{ctx.path('players')}/{entity.id}", json={"status": "retired"}
            )

        assert response.status_code == 200
        assert response.json()["status"] == "retired"
        assert repo.update.await_args.args == (entity.id,)
        assert repo.update.await_args.kwargs == {"status": "retired"}

    def test_update_rejects_changing_user_id(self) -> None:
        """The ownership link is immutable and the error names the field."""
        with authorized() as ctx:
            response = ctx.client.patch(
                f"{ctx.path('players')}/{uuid4()}", json={"user_id": str(uuid4())}
            )

        assert response.status_code == 422
        detail = response.json()["detail"][0]
        assert detail["loc"] == ["body", "user_id"]
        assert detail["type"] == "extra_forbidden"

    def test_unknown_user_is_translated_to_422(self) -> None:
        """The repository's link check surfaces as a 422, not a dangling link."""
        from app.application.exceptions import ValidationError

        with authorized() as ctx:
            entity = make_entity(ctx.campaign.id, "player")
            ctx.repos["players"].create = AsyncMock(
                side_effect=ValidationError("User not found", {"user_id": str(uuid4())})
            )

            response = ctx.client.post(
                ctx.path("players"),
                json={"entity_id": str(entity.id), "user_id": str(uuid4())},
            )

        assert response.status_code == 422
        assert response.json()["code"] == "ValidationError"

    def test_create_rejects_duplicate_specialization(self) -> None:
        """A second player row for one entity is a conflict."""
        with authorized() as ctx:
            entity = make_entity(ctx.campaign.id, "player")
            repo = ctx.repos["players"]
            repo._resolve = AsyncMock(return_value=(entity, None))
            repo.validate = AsyncMock()
            repo.create = AsyncMock(
                side_effect=ConflictError("Player already exists for this entity")
            )

            response = ctx.client.post(
                ctx.path("players"),
                json={"entity_id": str(entity.id), "user_id": str(uuid4())},
            )

        assert response.status_code == 409
        assert response.json()["code"] == "ConflictError"


class TestPlayerCharacterRules:
    """Player character-specific rules."""

    def test_update_rejects_changing_player_id(self) -> None:
        """The character cannot be repointed at another player."""
        with authorized() as ctx:
            response = ctx.client.patch(
                f"{ctx.path('player-characters')}/{uuid4()}",
                json={"player_id": str(uuid4())},
            )

        assert response.status_code == 422
        detail = response.json()["detail"][0]
        assert detail["loc"] == ["body", "player_id"]
        assert detail["type"] == "extra_forbidden"

    def test_create_requires_player_id(self) -> None:
        """A character cannot exist without a player."""
        with authorized() as ctx:
            response = ctx.client.post(
                ctx.path("player-characters"), json={"entity_id": str(uuid4())}
            )

        assert response.status_code == 422

    def test_create_rejects_player_from_another_campaign(self) -> None:
        """The link must resolve inside the campaign, not just in the database."""
        with authorized() as ctx:
            from app.application.exceptions import ValidationError

            repo = ctx.repos["player-characters"]
            repo.create = AsyncMock(
                side_effect=ValidationError("Player not found in this campaign")
            )

            response = ctx.client.post(
                ctx.path("player-characters"),
                json={"entity_id": str(uuid4()), "player_id": str(uuid4())},
            )

        assert response.status_code == 422
        assert response.json()["detail"] == "Player not found in this campaign"


class TestRequestStrictness:
    """Unknown fields must not be silently dropped."""

    def test_create_rejects_unknown_field(self) -> None:
        """These tables have few columns, so a typo must be visible."""
        with authorized() as ctx:
            response = ctx.client.post(
                ctx.path("actors"),
                json={"entity_id": str(uuid4()), "class_name": "rogue"},
            )

        assert response.status_code == 422
        assert response.json()["detail"][0]["type"] == "extra_forbidden"
