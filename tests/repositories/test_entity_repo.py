"""Tests for campaign isolation and soft-delete filtering in entity repositories.

The statements are inspected by compiling them, so these tests assert real query
behaviour without needing a database.
"""

from datetime import UTC, datetime, timedelta
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import EntityAlias
from app.repositories.entity_repo import (
    EntityAliasRepository,
    EntityRepository,
    escape_like,
)


def result_stub(rows: list[object] | None = None, scalar: object = 0) -> MagicMock:
    """Build a mock AsyncSession.execute() result."""
    result = MagicMock()
    result.scalars.return_value.all.return_value = rows or []
    result.scalar_one.return_value = scalar
    return result


def captured(session: AsyncMock) -> Select[Any]:
    """Return the single statement passed to session.execute."""
    return cast(Select[Any], session.execute.await_args_list[0][0][0])


def compiled_params(session: AsyncMock) -> dict[str, object]:
    """Return the bound parameters of the executed statement."""
    return dict(captured(session).compile().params)


def sql(session: AsyncMock) -> str:
    """Return the SQL text of the executed statement."""
    return str(captured(session).compile())


class TestEscapeLike:
    """Tests for LIKE wildcard escaping."""

    def test_escapes_wildcards(self) -> None:
        """User input is matched literally, not as a wildcard pattern."""
        assert escape_like("100%") == "100\\%"
        assert escape_like("a_b") == "a\\_b"
        assert escape_like("back\\slash") == "back\\\\slash"

    def test_leaves_plain_text_unchanged(self) -> None:
        """Ordinary text passes through untouched."""
        assert escape_like("larkfellow") == "larkfellow"


class TestEntityRepositoryScoping:
    """Tests for campaign isolation in EntityRepository."""

    @pytest.mark.asyncio
    async def test_list_filters_by_campaign(self) -> None:
        """Entity listings are restricted to the repository's campaign."""
        campaign_id = uuid4()
        session = AsyncMock(spec=AsyncSession)
        session.execute.return_value = result_stub()
        repo = EntityRepository(session, campaign_id)

        await repo.list_filtered()

        params = compiled_params(session)
        assert campaign_id in params.values()
        assert "entities.campaign_id = :" in sql(session)
        assert "entities.deleted_at IS NULL" in sql(session)

    @pytest.mark.asyncio
    async def test_two_campaigns_produce_different_scopes(self) -> None:
        """Isolation is driven by the repository scope, not a global filter."""
        first = AsyncMock(spec=AsyncSession)
        first.execute.return_value = result_stub()
        second = AsyncMock(spec=AsyncSession)
        second.execute.return_value = result_stub()

        await EntityRepository(first, uuid4()).list_filtered()
        await EntityRepository(second, uuid4()).list_filtered()

        assert compiled_params(first).values() != compiled_params(second).values()

    @pytest.mark.asyncio
    async def test_unscoped_repository_does_not_filter_campaign(self) -> None:
        """Without a campaign scope no campaign filter is emitted."""
        session = AsyncMock(spec=AsyncSession)
        session.execute.return_value = result_stub()

        await EntityRepository(session, None).list_filtered()

        assert "entities.campaign_id = :" not in sql(session)
        assert not any(
            isinstance(value, UUID) for value in compiled_params(session).values()
        )

    @pytest.mark.asyncio
    async def test_get_excludes_soft_deleted(self) -> None:
        """A soft-deleted entity is not returned by get."""
        campaign_id = uuid4()
        session = AsyncMock(spec=AsyncSession)
        session.execute.return_value = result_stub()
        repo = EntityRepository(session, campaign_id)

        await repo.get(uuid4())

        assert "entities.deleted_at IS NULL" in sql(session)
        assert campaign_id in compiled_params(session).values()

    @pytest.mark.asyncio
    async def test_count_uses_the_same_filters(self) -> None:
        """The count query is scoped and filtered like the listing."""
        campaign_id = uuid4()
        session = AsyncMock(spec=AsyncSession)
        session.execute.return_value = result_stub(scalar=7)
        repo = EntityRepository(session, campaign_id)

        assert await repo.count_filtered(entity_type="npc") == 7
        assert "entities.entity_type" in sql(session)


class TestEntityRepositoryFilters:
    """Tests for entity list filtering."""

    @pytest.mark.asyncio
    async def test_name_filter_escapes_wildcards(self) -> None:
        """A percent sign in the filter is literal."""
        session = AsyncMock(spec=AsyncSession)
        session.execute.return_value = result_stub()
        repo = EntityRepository(session, uuid4())

        await repo.list_filtered(name_contains="100%")

        assert any(
            "100\\%" in str(value) for value in compiled_params(session).values()
        )

    @pytest.mark.asyncio
    async def test_name_filter_covers_description(self) -> None:
        """The name filter also matches the description."""
        session = AsyncMock(spec=AsyncSession)
        session.execute.return_value = result_stub()

        await EntityRepository(session, uuid4()).list_filtered(name_contains="inn")

        text = sql(session)
        assert "lower(entities.name) LIKE" in text
        assert "lower(entities.description) LIKE" in text

    @pytest.mark.asyncio
    async def test_find_by_alias_excludes_deleted_aliases(self) -> None:
        """Alias resolution ignores soft-deleted aliases."""
        session = AsyncMock(spec=AsyncSession)
        session.execute.return_value = result_stub()

        await EntityRepository(session, uuid4()).find_by_alias("Host")

        text = sql(session)
        assert "entity_aliases_1.deleted_at IS NULL" in text
        assert "entities.deleted_at IS NULL" in text


class TestBaseRepositorySoftDelete:
    """Tests for soft-delete timestamp handling."""

    @pytest.mark.asyncio
    async def test_deleted_at_is_timezone_aware_utc(self) -> None:
        """deleted_at is written as an aware UTC instant, not a naive value."""
        campaign_id = uuid4()
        session = AsyncMock(spec=AsyncSession)
        row = MagicMock()
        row.id = uuid4()
        row.deleted_at = None
        session.execute.return_value = result_stub()
        session.execute.return_value.scalar_one_or_none.return_value = row
        repo = EntityRepository(session, campaign_id)

        assert await repo.soft_delete(row.id) is True

        assert row.deleted_at is not None
        assert row.deleted_at.tzinfo is not None
        assert row.deleted_at.utcoffset() == timedelta(0)

    @pytest.mark.asyncio
    async def test_soft_delete_missing_row_returns_false(self) -> None:
        """Deleting an absent row reports failure without writing."""
        session = AsyncMock(spec=AsyncSession)
        session.execute.return_value = result_stub()
        session.execute.return_value.scalar_one_or_none.return_value = None
        repo = EntityRepository(session, uuid4())

        assert await repo.soft_delete(uuid4()) is False
        session.flush.assert_not_awaited()


class TestBaseRepositoryCreateAndUpdate:
    """Tests for the shared create/update behaviour."""

    @pytest.mark.asyncio
    async def test_create_omits_campaign_id_when_model_has_no_column(self) -> None:
        """EntityAlias has no campaign_id, so the scope must not be injected.

        Injecting it anyway raises TypeError from the declarative constructor.
        """
        session = AsyncMock(spec=AsyncSession)
        repo = EntityAliasRepository(session, uuid4())

        await repo.create(entity_id=uuid4(), alias="Host")

        created = session.add.call_args[0][0]
        assert isinstance(created, EntityAlias)
        assert not hasattr(created, "campaign_id")

    @pytest.mark.asyncio
    async def test_create_injects_campaign_id_when_model_has_column(self) -> None:
        """Models that are campaign-scoped receive the repository campaign."""
        campaign_id = uuid4()
        session = AsyncMock(spec=AsyncSession)
        repo = EntityRepository(session, campaign_id)

        await repo.create(entity_type="npc", name="Larkfellow")

        assert session.add.call_args[0][0].campaign_id == campaign_id

    @pytest.mark.asyncio
    async def test_update_refreshes_after_flush(self) -> None:
        """updated_at is a server-side default, so the row must be reloaded.

        Without the refresh the attribute stays expired and reading it from
        async context raises MissingGreenlet.
        """
        session = AsyncMock(spec=AsyncSession)
        row = MagicMock()
        row.id = uuid4()
        row.updated_at = datetime(2026, 1, 1, tzinfo=UTC)
        session.execute.return_value = result_stub()
        session.execute.return_value.scalar_one_or_none.return_value = row
        repo = EntityRepository(session, uuid4())

        result = await repo.update(row.id, name="Renamed")

        assert result is row
        assert row.name == "Renamed"
        session.flush.assert_awaited_once()
        session.refresh.assert_awaited_once_with(row)

    @pytest.mark.asyncio
    async def test_update_missing_row_does_not_write(self) -> None:
        """Updating an absent row performs no flush or refresh."""
        session = AsyncMock(spec=AsyncSession)
        session.execute.return_value = result_stub()
        session.execute.return_value.scalar_one_or_none.return_value = None
        repo = EntityRepository(session, uuid4())

        assert await repo.update(uuid4(), name="Renamed") is None
        session.flush.assert_not_awaited()
        session.refresh.assert_not_awaited()


class TestEntityAliasRepository:
    """Tests for EntityAliasRepository."""

    @pytest.mark.asyncio
    async def test_get_by_entity_orders_by_alias(self) -> None:
        """Aliases are returned in a stable alphabetical order."""
        session = AsyncMock(spec=AsyncSession)
        session.execute.return_value = result_stub()
        repo = EntityAliasRepository(session, uuid4())

        await repo.get_by_entity(uuid4())

        text = sql(session)
        assert "ORDER BY entity_aliases.alias" in text
        assert "entity_aliases.deleted_at IS NULL" in text

    @pytest.mark.asyncio
    async def test_get_by_alias_scopes_to_entity(self) -> None:
        """Alias lookup requires both the entity and the alias string."""
        session = AsyncMock(spec=AsyncSession)
        session.execute.return_value = result_stub()
        entity_id = uuid4()

        await EntityAliasRepository(session, uuid4()).get_by_alias(entity_id, "Host")

        assert entity_id in compiled_params(session).values()
        assert "Host" in compiled_params(session).values()

    @pytest.mark.asyncio
    async def test_get_excludes_soft_deleted(self) -> None:
        """A removed alias is not returned."""
        session = AsyncMock(spec=AsyncSession)
        session.execute.return_value = result_stub()

        await EntityAliasRepository(session, uuid4()).get(uuid4())

        assert "entity_aliases.deleted_at IS NULL" in sql(session)
