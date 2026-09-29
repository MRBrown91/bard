"""Tests for entity API endpoints and application error translation.

The campaign and repository dependencies are overridden so these tests exercise
transport, authorization, and error mapping without a database or network.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import (
    get_current_campaign,
    get_entity_alias_repo,
    get_entity_repo,
)
from app.application.exceptions import ConflictError, NotFoundError, ValidationError
from app.main import app
from app.models import Campaign
from app.repositories import EntityAliasRepository, EntityRepository

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def make_campaign(user_id: UUID | None = None) -> Campaign:
    """Build a campaign owned by the given user."""
    return Campaign(
        id=uuid4(),
        user_id=user_id or uuid4(),
        name="The Long Road",
        description=None,
        is_active=True,
        created_at=NOW,
        updated_at=NOW,
        deleted_at=None,
    )


def make_entity_row(campaign_id: UUID, name: str = "Larkfellow") -> MagicMock:
    """Build an Entity-like row."""
    row = MagicMock()
    row.id = uuid4()
    row.campaign_id = campaign_id
    row.entity_type = "actor"
    row.name = name
    row.description = None
    row.created_at = NOW
    row.updated_at = NOW
    row.deleted_at = None
    return row


def make_alias_row(
    entity_id: UUID, alias: str = "Host", kind: str = "alias"
) -> MagicMock:
    """Build an EntityAlias-like row."""
    row = MagicMock()
    row.id = uuid4()
    row.entity_id = entity_id
    row.alias = alias
    row.kind = kind
    row.created_at = NOW
    row.updated_at = NOW
    row.deleted_at = None
    return row


class Authorized:
    """Test context holding the client and the overridden repository stubs."""

    def __init__(
        self,
        client: TestClient,
        entity_repo: AsyncMock,
        alias_repo: AsyncMock,
        created: list[MagicMock],
    ) -> None:
        self.client = client
        self.entity_repo = entity_repo
        self.alias_repo = alias_repo
        self.created = created


@contextmanager
def authorized(campaign: Campaign) -> Iterator[Authorized]:
    """Override campaign scope and repositories for the duration of a test."""
    entity_repo = AsyncMock(spec=EntityRepository)
    alias_repo = AsyncMock(spec=EntityAliasRepository)
    created: list[MagicMock] = []

    async def create_entity_row(**kwargs: object) -> MagicMock:
        row = make_entity_row(campaign.id, str(kwargs.get("name", "Larkfellow")))
        created.append(row)
        return row

    async def update_entity_row(id: UUID, **kwargs: object) -> MagicMock:
        return make_entity_row(campaign.id, str(kwargs.get("name", "Larkfellow")))

    entity_repo.create.side_effect = create_entity_row
    entity_repo.update.side_effect = update_entity_row
    async def get_entity_row(id: UUID, *names: str) -> MagicMock:
        row = make_entity_row(campaign.id)
        row.id = id
        return row

    entity_repo.get_with.side_effect = get_entity_row
    entity_repo.session = AsyncMock(spec=AsyncSession)
    entity_repo.count_filtered.return_value = 0
    entity_repo.list_filtered.return_value = []
    alias_repo.create.side_effect = lambda **kw: make_alias_row(
        kw["entity_id"], str(kw["alias"]), str(kw.get("kind", "alias"))
    )
    alias_repo.get_by_entity.return_value = []
    alias_repo.get_by_alias.return_value = None
    alias_repo.soft_delete.return_value = True
    alias_repo.rename.return_value = True

    app.dependency_overrides[get_current_campaign] = lambda: campaign
    app.dependency_overrides[get_entity_repo] = lambda: entity_repo
    app.dependency_overrides[get_entity_alias_repo] = lambda: alias_repo
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            yield Authorized(client, entity_repo, alias_repo, created)
    finally:
        app.dependency_overrides.clear()


class TestEntityEndpoints:
    """Tests for the entity CRUD surface."""

    def test_create_entity_returns_201(self) -> None:
        """A valid create request returns the persisted entity."""
        campaign = make_campaign()
        with authorized(campaign) as ctx:
            response = ctx.client.post(
                f"/api/campaigns/{campaign.id}/entities",
                json={"entity_type": "actor", "name": "Larkfellow"},
            )

        assert response.status_code == 201
        assert response.json()["name"] == "Larkfellow"
        assert response.json()["campaign_id"] == str(campaign.id)

    def test_create_entity_with_aliases(self) -> None:
        """Aliases supplied at creation are persisted under the new entity."""
        campaign = make_campaign()
        with authorized(campaign) as ctx:
            response = ctx.client.post(
                f"/api/campaigns/{campaign.id}/entities",
                json={
                    "entity_type": "actor",
                    "name": "Larkfellow",
                    "aliases": [{"alias": "Host"}],
                },
            )

        assert response.status_code == 201
        assert len(ctx.created) == 1
        # The name row is created first, then the requested alias.
        created = [call.kwargs for call in ctx.alias_repo.create.await_args_list]
        assert [row["alias"] for row in created] == ["Larkfellow", "Host"]
        assert [
            call.kwargs["kind"] for call in ctx.alias_repo.create.await_args_list
        ] == ["name", "alias"]

    def test_get_entity_includes_aliases(self) -> None:
        """The read model carries the entity's aliases."""
        campaign = make_campaign()
        entity_id = uuid4()
        with authorized(campaign) as ctx:
            row = make_entity_row(campaign.id)
            row.id = entity_id
            row.aliases = [make_alias_row(entity_id, "Host")]

            async def get_with(id: UUID, *names: str) -> MagicMock:
                return row

            ctx.entity_repo.get_with.side_effect = get_with

            response = ctx.client.get(
                f"/api/campaigns/{campaign.id}/entities/{entity_id}"
            )

        assert response.status_code == 200
        body = response.json()
        assert body["id"] == str(entity_id)
        assert [alias["alias"] for alias in body["aliases"]] == ["Host"]

    def test_list_entities_is_paginated(self) -> None:
        """Listing returns a paginated envelope built from repository counts."""
        campaign = make_campaign()
        with authorized(campaign) as ctx:
            ctx.entity_repo.list_filtered.return_value = [make_entity_row(campaign.id)]
            ctx.entity_repo.count_filtered.return_value = 1

            response = ctx.client.get(
                f"/api/campaigns/{campaign.id}/entities",
                params={"page": 1, "page_size": 20},
            )

        body = response.json()
        assert response.status_code == 200
        assert body["total"] == 1
        assert body["total_pages"] == 1
        assert len(body["items"]) == 1
        ctx.entity_repo.list_filtered.assert_awaited_once_with(
            entity_type=None, name_contains=None, offset=0, limit=20
        )

    def test_list_entities_rejects_oversized_page(self) -> None:
        """Pagination bounds are enforced by the transport layer."""
        campaign = make_campaign()
        with authorized(campaign) as ctx:
            response = ctx.client.get(
                f"/api/campaigns/{campaign.id}/entities", params={"page_size": 5000}
            )

        assert response.status_code == 422

    def test_update_entity_returns_200(self) -> None:
        """A patch request returns the updated entity."""
        campaign = make_campaign()
        with authorized(campaign) as ctx:
            response = ctx.client.patch(
                f"/api/campaigns/{campaign.id}/entities/{uuid4()}",
                json={"name": "Renamed"},
            )

        assert response.status_code == 200
        assert response.json()["name"] == "Renamed"

    def test_delete_entity_returns_204(self) -> None:
        """A delete request returns no content."""
        campaign = make_campaign()
        with authorized(campaign) as ctx:
            response = ctx.client.delete(
                f"/api/campaigns/{campaign.id}/entities/{uuid4()}"
            )

        assert response.status_code == 204
        assert response.content == b""

    def test_add_alias_returns_201(self) -> None:
        """A new alias is created under the entity."""
        campaign = make_campaign()
        entity_id = uuid4()
        with authorized(campaign) as ctx:
            ctx.entity_repo.get.return_value = make_entity_row(campaign.id)

            response = ctx.client.post(
                f"/api/campaigns/{campaign.id}/entities/{entity_id}/aliases",
                json={"alias": "Host"},
            )

        assert response.status_code == 201
        assert response.json()["alias"] == "Host"
        assert response.json()["entity_id"] == str(entity_id)

    def test_duplicate_alias_returns_409(self) -> None:
        """A conflicting alias is translated to HTTP 409."""
        campaign = make_campaign()
        entity_id = uuid4()
        with authorized(campaign) as ctx:
            ctx.entity_repo.get.return_value = make_entity_row(campaign.id)
            ctx.alias_repo.get_by_alias.return_value = make_alias_row(entity_id)

            response = ctx.client.post(
                f"/api/campaigns/{campaign.id}/entities/{entity_id}/aliases",
                json={"alias": "Host"},
            )

        assert response.status_code == 409
        assert response.json()["code"] == "ConflictError"
        assert response.json()["extra"]["alias"] == "Host"

    def test_missing_entity_returns_404(self) -> None:
        """An unknown entity is translated to HTTP 404."""
        campaign = make_campaign()
        with authorized(campaign) as ctx:
            ctx.entity_repo.get_with.side_effect = None
            ctx.entity_repo.get_with.return_value = None

            response = ctx.client.get(
                f"/api/campaigns/{campaign.id}/entities/{uuid4()}"
            )

        assert response.status_code == 404
        assert response.json()["code"] == "NotFoundError"

    def test_nulling_required_field_returns_422(self) -> None:
        """A null name is rejected by application validation."""
        campaign = make_campaign()
        with authorized(campaign) as ctx:
            response = ctx.client.patch(
                f"/api/campaigns/{campaign.id}/entities/{uuid4()}",
                json={"name": None},
            )

        assert response.status_code == 422
        assert response.json()["code"] == "ValidationError"

    def test_unauthenticated_request_returns_401(self) -> None:
        """Without a token the campaign scope dependency rejects the request."""
        app.dependency_overrides.clear()
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get(f"/api/campaigns/{uuid4()}/entities")

        assert response.status_code == 401
        assert response.json()["code"] == "UnauthorizedError"
        assert response.headers["WWW-Authenticate"] == "Bearer"


class TestApplicationErrorMapping:
    """Tests for the exception handler registered on the application."""

    @pytest.mark.parametrize(
        ("error", "expected"),
        [
            (NotFoundError("missing"), 404),
            (ConflictError("duplicate"), 409),
            (ValidationError("invalid"), 422),
        ],
    )
    def test_status_codes(self, error: Exception, expected: int) -> None:
        """Each application error maps to its HTTP status code."""
        from app.main import application_error_status

        assert application_error_status(error) == expected  # type: ignore[arg-type]

    def test_unknown_application_error_is_500(self) -> None:
        """An unmapped application error does not leak a 2xx."""
        from app.application.exceptions import ApplicationError
        from app.main import application_error_status

        assert application_error_status(ApplicationError("boom")) == 500
