"""Tests for app-wide soft-delete filtering in BaseRepository.

DATABASE.md requires that "soft-deleted records are excluded from normal
active queries". The filter has to hold for every repository, including the
tables that carry no ``campaign_id`` of their own and therefore get no
protection from campaign scoping.

The statements are inspected by compiling them, so these tests assert real
query behaviour without needing a database.
"""

from datetime import UTC, datetime
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy import Select

from app.repositories.base import BaseRepository
from app.repositories.campaign_repo import CampaignRepository
from app.repositories.document_repo import (
    DocumentRepository,
    DocumentStatementRepository,
)
from app.repositories.entity_repo import EntityAliasRepository, EntityRepository
from app.repositories.user_repo import UserRepository

NOW = datetime(2026, 1, 1, tzinfo=UTC)

# One repository per table shape: with campaign_id, and without it. The
# second group is the one that used to be unprotected, because
# _campaign_scope silently does nothing when the column is absent.
REPOSITORIES: list[type[BaseRepository[Any]]] = [
    CampaignRepository,
    DocumentRepository,
    EntityRepository,
    UserRepository,
    DocumentStatementRepository,
    EntityAliasRepository,
]

UNCAMPAIGNED = [DocumentStatementRepository, EntityAliasRepository]


def result_stub(rows: list[object] | None = None, scalar: object = 0) -> MagicMock:
    """Build a mock AsyncSession.execute() result."""
    result = MagicMock()
    result.scalars.return_value.all.return_value = rows or []
    result.scalar_one.return_value = scalar
    result.scalar_one_or_none.return_value = scalar
    return result


def sql(session: AsyncMock) -> str:
    """Return the SQL text of the executed statement."""
    return str(cast(Select[Any], session.execute.await_args_list[0][0][0]).compile())


class TestActiveScope:
    """Tests for the soft-delete filter itself."""

    @pytest.mark.parametrize("repo_class", REPOSITORIES)
    async def test_filter_is_applied_to_every_repository(
        self, repo_class: type[BaseRepository[Any]]
    ) -> None:
        """Every table inherits deleted_at, so every read filters on it."""
        session = AsyncMock()
        session.execute.return_value = result_stub(scalar=None)
        await repo_class(session, uuid4()).get(uuid4())
        assert "deleted_at IS NULL" in sql(session)

    async def test_defined_once_on_the_base(self) -> None:
        """Repositories inherit the filter rather than re-declaring it."""
        assert BaseRepository._active_scope is not None
        for repo_class in REPOSITORIES:
            assert "_active_scope" not in repo_class.__dict__, repo_class.__name__

    @pytest.mark.parametrize("repo_class", UNCAMPAIGNED)
    async def test_applies_without_a_campaign_id_column(
        self, repo_class: type[BaseRepository[Any]]
    ) -> None:
        """Scoping is a no-op for these tables, so the filter is all they have."""
        session = AsyncMock()
        session.execute.return_value = result_stub()
        await repo_class(session, uuid4()).get(uuid4())
        assert "deleted_at IS NULL" in sql(session)

    async def test_does_not_depend_on_campaign_scoping(self) -> None:
        """A repository with no campaign scope still excludes deleted rows."""
        session = AsyncMock()
        session.execute.return_value = result_stub()
        await DocumentStatementRepository(session, None).get(uuid4())
        assert "deleted_at IS NULL" in sql(session)


class TestReads:
    """Every read path must exclude soft-deleted rows."""

    @pytest.mark.parametrize("repo_class", REPOSITORIES)
    async def test_get_excludes_deleted(
        self, repo_class: type[BaseRepository[Any]]
    ) -> None:
        session = AsyncMock()
        session.execute.return_value = result_stub(scalar=None)
        await repo_class(session, uuid4()).get(uuid4())
        assert "deleted_at IS NULL" in sql(session)

    @pytest.mark.parametrize("repo_class", REPOSITORIES)
    async def test_list_excludes_deleted(
        self, repo_class: type[BaseRepository[Any]]
    ) -> None:
        session = AsyncMock()
        session.execute.return_value = result_stub()
        await repo_class(session, uuid4()).list()
        assert "deleted_at IS NULL" in sql(session)

    @pytest.mark.parametrize("repo_class", REPOSITORIES)
    async def test_count_excludes_deleted(
        self, repo_class: type[BaseRepository[Any]]
    ) -> None:
        session = AsyncMock()
        session.execute.return_value = result_stub(scalar=0)
        await repo_class(session, uuid4()).count()
        assert "deleted_at IS NULL" in sql(session)

    @pytest.mark.parametrize("repo_class", REPOSITORIES)
    async def test_exists_excludes_deleted(
        self, repo_class: type[BaseRepository[Any]]
    ) -> None:
        session = AsyncMock()
        session.execute.return_value = result_stub(scalar=None)
        assert await repo_class(session, uuid4()).exists(uuid4()) is False
        assert "deleted_at IS NULL" in sql(session)

    async def test_list_keeps_its_filters_alongside_the_filter(self) -> None:
        """Adding the filter must not displace campaign scoping or paging."""
        session = AsyncMock()
        session.execute.return_value = result_stub()
        await DocumentRepository(session, uuid4()).list(offset=10, limit=5)
        statement = sql(session)
        assert "deleted_at IS NULL" in statement
        assert "campaign_id" in statement
        assert "LIMIT" in statement


class TestSoftDeleteIdempotence:
    """Deleting an already-deleted row reports failure instead of re-stamping."""

    async def test_soft_delete_of_deleted_row_returns_false(self) -> None:
        session = AsyncMock()
        session.execute.return_value = result_stub(scalar=None)
        assert await CampaignRepository(session, uuid4()).soft_delete(uuid4()) is False
        assert session.commit.await_count == 0
        assert session.flush.await_count == 0

    async def test_update_cannot_touch_a_deleted_row(self) -> None:
        session = AsyncMock()
        session.execute.return_value = result_stub(scalar=None)
        assert (
            await CampaignRepository(session, uuid4()).update(uuid4(), name="x") is None
        )
        assert session.flush.await_count == 0
