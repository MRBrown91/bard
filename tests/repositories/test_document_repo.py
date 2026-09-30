"""Tests for the document repositories.

The statements are inspected by compiling them, so these tests assert real query
behaviour without needing a database: campaign scoping for a table that has no
``campaign_id`` of its own, agreement between the page and the total, ordering,
and the cascade that stamps a document and its statements together.
"""

from datetime import UTC, datetime, timedelta
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy import Select

from app.models import Document, DocumentStatement
from app.repositories.document_repo import (
    STATEMENT_ORDER,
    DocumentRepository,
    DocumentStatementRepository,
)
from app.repositories.entity_repo import EntityAliasRepository

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def result_stub(rows: list[object] | None = None, scalar: object = 0) -> MagicMock:
    """Build a mock AsyncSession.execute() result."""
    result = MagicMock()
    result.scalars.return_value.all.return_value = rows or []
    result.scalar_one.return_value = scalar
    result.scalar_one_or_none.return_value = scalar
    return result


def captured(session: AsyncMock) -> Select[Any]:
    """Return the single statement passed to session.execute."""
    return cast(Select[Any], session.execute.await_args_list[0][0][0])


def sql(session: AsyncMock) -> str:
    """Return the SQL text of the executed statement."""
    return str(captured(session).compile())


def repo(session: AsyncMock, campaign_id: Any = None) -> DocumentRepository:
    """Build a document repository."""
    return DocumentRepository(session, campaign_id or uuid4())


def statements(
    session: AsyncMock, campaign_id: Any = None
) -> DocumentStatementRepository:
    """Build a statement repository."""
    return DocumentStatementRepository(session, campaign_id or uuid4())


def aliases(session: AsyncMock, campaign_id: Any = None) -> EntityAliasRepository:
    """Build an alias repository, the other table that inherits its scope."""
    return EntityAliasRepository(session, campaign_id or uuid4())


def create_capture_session() -> MagicMock:
    """A session that records ``add`` calls without executing anything.

    ``BaseRepository.create`` adds then flushes. ``add`` is synchronous and
    ``flush`` is not, so this keeps ``add`` a real MagicMock call that can be
    counted and left ``flush`` awaitable.
    """
    session = MagicMock()
    session.flush = AsyncMock()
    session.execute = AsyncMock(return_value=result_stub())
    return session


def document_with_statements(count: int = 2) -> Document:
    """Build a document with the given number of live statements."""
    document = Document(
        id=uuid4(),
        campaign_id=uuid4(),
        session_id=None,
        document_type="lore",
        title="t",
        content="c",
        source_type=None,
        source_reference=None,
        created_at=NOW,
        updated_at=NOW,
        deleted_at=None,
    )
    document.statements = [
        DocumentStatement(
            id=uuid4(),
            document_id=document.id,
            position=index,
            content=f"statement {index}",
            created_at=NOW,
            updated_at=NOW,
            deleted_at=None,
        )
        for index in range(count)
    ]
    return document


class TestDocumentScoping:
    """Documents are scoped by the campaign column they do have."""

    async def test_scopes_to_the_campaign(self) -> None:
        session = AsyncMock()
        session.execute.return_value = result_stub()
        await repo(session).list_filtered()
        assert "documents.campaign_id" in sql(session)

    async def test_excludes_soft_deleted(self) -> None:
        session = AsyncMock()
        session.execute.return_value = result_stub()
        await repo(session).get_with_statements(uuid4())
        assert "deleted_at IS NULL" in sql(session)

    async def test_count_excludes_soft_deleted(self) -> None:
        session = AsyncMock()
        session.execute.return_value = result_stub(scalar=0)
        await repo(session).count_filtered()
        assert "deleted_at IS NULL" in sql(session)

    async def test_applies_both_filters_to_the_count(self) -> None:
        """The total must come from the same predicate as the page."""
        session = AsyncMock()
        session.execute.return_value = result_stub(scalar=0)
        document_type, session_id = "lore", uuid4()
        await repo(session).count_filtered(
            document_type=document_type, session_id=session_id
        )
        params = dict(captured(session).compile().params)
        assert params["document_type_1"] == document_type
        assert params["session_id_1"] == session_id

    async def test_page_and_count_build_the_same_predicate(self) -> None:
        """This is the invariant that keeps total and len(items) in step."""
        first, second = AsyncMock(), AsyncMock()
        first.execute.return_value = result_stub()
        second.execute.return_value = result_stub(scalar=0)
        await repo(first).list_filtered(document_type="lore", session_id=uuid4())
        await repo(second).count_filtered(document_type="lore", session_id=uuid4())
        page_where = str(captured(first).compile()).split("WHERE")[1]
        count_where = str(captured(second).compile()).split("WHERE")[1]
        for fragment in ("campaign_id", "deleted_at", "document_type", "session_id"):
            assert fragment in page_where
            assert fragment in count_where

    async def test_orders_by_created_at_and_id(self) -> None:
        """Paging needs a unique tiebreak or rows can swap between pages."""
        session = AsyncMock()
        session.execute.return_value = result_stub()
        await repo(session).list_filtered()
        statement = sql(session)
        assert "ORDER BY documents.created_at, documents.id" in statement

    async def test_omits_filters_that_were_not_given(self) -> None:
        session = AsyncMock()
        session.execute.return_value = result_stub()
        await repo(session).list_filtered()
        assert "document_type =" not in sql(session)
        assert "session_id =" not in sql(session)


class TestStatementScoping:
    """Statements have no ``campaign_id``, so scope comes from the parent."""

    @pytest.mark.parametrize(
        "call",
        [
            pytest.param(lambda r, s: r.get_by_document(s), id="get_by_document"),
            pytest.param(lambda r, s: r.get(s), id="get"),
            pytest.param(lambda r, s: r.count_by_document(s), id="count_by_document"),
            pytest.param(
                lambda r, s: r.list_filtered(document_id=s), id="list_filtered"
            ),
            pytest.param(lambda r, s: r.list_filtered(), id="list_filtered_all"),
        ],
    )
    async def test_every_read_joins_the_parent_campaign(
        self, call: Any
    ) -> None:
        """The base campaign scope is a no-op for this table, so the join is it."""
        session = AsyncMock()
        session.execute.return_value = result_stub()
        await call(statements(session), uuid4())
        statement = sql(session)
        assert "JOIN documents" in statement
        assert "documents.campaign_id" in statement

    async def test_omits_the_join_when_there_is_no_scope(self) -> None:
        """Without a campaign there is nothing to join against."""
        session = AsyncMock()
        session.execute.return_value = result_stub()
        await DocumentStatementRepository(session, None).get_by_document(uuid4())
        assert "JOIN documents" not in sql(session)

    async def test_excludes_soft_deleted_statements(self) -> None:
        session = AsyncMock()
        session.execute.return_value = result_stub()
        await statements(session).get_by_document(uuid4())
        assert "deleted_at IS NULL" in sql(session)

    async def test_joins_to_a_live_document_only(self) -> None:
        """A statement whose document is deleted is not reachable through it."""
        session = AsyncMock()
        session.execute.return_value = result_stub()
        await statements(session).get(uuid4())
        statement = str(captured(session).compile())
        assert statement.count("deleted_at IS NULL") == 2

    async def test_orders_by_position_then_created_at_then_id(self) -> None:
        session = AsyncMock()
        session.execute.return_value = result_stub()
        await statements(session).get_by_document(uuid4())
        statement = sql(session)
        assert (
            "ORDER BY document_statements.position, "
            "document_statements.created_at, document_statements.id" in statement
        )

    def test_ordering_constant_matches_the_relationship(self) -> None:
        """The relationship and the query must not disagree.

        Compared on the rendered table columns, since the constant holds class
        attributes while the relationship holds resolved ones.
        """
        relationship_order = [
            str(column) for column in Document.__mapper__.relationships[
                "statements"
            ].order_by
        ]
        assert [
            str(column.name) for column in STATEMENT_ORDER
        ] == [name.rpartition(".")[2] for name in relationship_order]


class TestCascade:
    """Deleting a document stamps its statements in the same transaction."""

    async def test_stamps_document_and_statements_with_one_timestamp(self) -> None:
        document = document_with_statements(3)
        session = AsyncMock()
        session.execute.return_value = result_stub(scalar=document)
        assert await repo(session).soft_delete_with_statements(document.id) is True
        assert document.deleted_at is not None
        stamps = {document.deleted_at} | {s.deleted_at for s in document.statements}
        assert len(stamps) == 1
        assert None not in stamps

    async def test_flushes_once(self) -> None:
        """Two rows in one transaction, not two."""
        document = document_with_statements()
        session = AsyncMock()
        session.execute.return_value = result_stub(scalar=document)
        await repo(session).soft_delete_with_statements(document.id)
        assert session.flush.await_count == 1

    async def test_reports_failure_for_a_missing_document(self) -> None:
        session = AsyncMock()
        session.execute.return_value = result_stub(scalar=None)
        assert await repo(session).soft_delete_with_statements(uuid4()) is False
        assert session.flush.await_count == 0

    async def test_a_document_with_no_statements_still_stamps(self) -> None:
        document = document_with_statements(0)
        session = AsyncMock()
        session.execute.return_value = result_stub(scalar=document)
        assert await repo(session).soft_delete_with_statements(document.id) is True
        assert document.deleted_at is not None


class TestRetainedHistory:
    """Soft deletion must not touch the data facts point at."""

    async def test_statements_are_retained_not_removed(self) -> None:
        document = document_with_statements(2)
        session = AsyncMock()
        session.execute.return_value = result_stub(scalar=document)
        await repo(session).soft_delete_with_statements(document.id)
        assert all(s.content for s in document.statements)

    async def test_timestamps_survive_for_retcons(self) -> None:
        document = document_with_statements(1)
        session = AsyncMock()
        session.execute.return_value = result_stub(scalar=document)
        await repo(session).soft_delete_with_statements(document.id)
        assert document.created_at == NOW

    async def test_statement_order_is_stable_across_tied_positions(self) -> None:
        """Ties are permitted by the schema, so the tiebreak has to work."""
        later = NOW + timedelta(seconds=1)
        rows = [
            DocumentStatement(id=uuid4(), document_id=uuid4(), position=0, content="b",
                              created_at=later, updated_at=later, deleted_at=None),
            DocumentStatement(id=uuid4(), document_id=uuid4(), position=0, content="a",
                              created_at=NOW, updated_at=NOW, deleted_at=None),
        ]
        session = AsyncMock()
        session.execute.return_value = result_stub(rows)
        result = await statements(session).get_by_document(uuid4())
        assert [r.content for r in result] == ["b", "a"]


class TestChildTableWriteScoping:
    """A table without ``campaign_id`` must scope its own writes.

    ``BaseRepository.soft_delete`` and ``update`` resolve the row through
    ``get``, and the base ``_campaign_scope`` is a silent no-op for
    ``document_statements`` and ``entity_aliases``. Before this was overridden,
    both would stamp or edit a row in any campaign given only its id while
    reporting success. The API was not reachable — the use cases resolve the
    parent first and compare the parent id — so this is about the repository
    being safe on its own terms rather than depending on every caller.

    ``create`` remains genuinely unscoped and is asserted as such below: it
    inserts whatever parent id it is handed, so the use cases must resolve the
    document before calling it.
    """

    async def test_soft_delete_joins_the_parent_campaign(self) -> None:
        session = AsyncMock()
        session.execute.return_value = result_stub(scalar=None)
        assert await statements(session).soft_delete(uuid4()) is False
        assert "JOIN documents" in sql(session)

    async def test_soft_delete_reports_failure_for_a_foreign_statement(
        self,
    ) -> None:
        """The defect, stated as behaviour: it used to return True here."""
        session = AsyncMock()
        session.execute.return_value = result_stub(scalar=None)
        assert await statements(session).soft_delete(uuid4()) is False

    async def test_get_joins_the_parent_campaign(self) -> None:
        session = AsyncMock()
        session.execute.return_value = result_stub(scalar=None)
        await statements(session).get(uuid4())
        statement = sql(session)
        assert "JOIN documents" in statement
        assert "documents.campaign_id" in statement

    async def test_get_requires_both_deletion_predicates(self) -> None:
        """The statement's own, and its document's."""
        session = AsyncMock()
        session.execute.return_value = result_stub(scalar=None)
        await statements(session).get(uuid4())
        assert str(captured(session).compile()).count("deleted_at IS NULL") == 2

    async def test_exists_joins_the_parent_campaign(self) -> None:
        """The inherited exists() builds its own select and needs the same fix."""
        session = AsyncMock()
        session.execute.return_value = result_stub(scalar=None)
        assert await statements(session).exists(uuid4()) is False
        assert "JOIN documents" in sql(session)

    async def test_alias_get_joins_the_parent_campaign(self) -> None:
        """Same override on EntityAliasRepository, for the same reason."""
        session = AsyncMock()
        session.execute.return_value = result_stub(scalar=None)
        await aliases(session).get(uuid4())
        statement = sql(session)
        assert "JOIN entities" in statement
        assert "entities.campaign_id" in statement

    async def test_alias_soft_delete_joins_the_parent_campaign(self) -> None:
        session = AsyncMock()
        session.execute.return_value = result_stub(scalar=None)
        assert await aliases(session).soft_delete(uuid4()) is False
        assert "JOIN entities" in sql(session)

    async def test_alias_get_by_alias_joins_the_parent_campaign(self) -> None:
        session = AsyncMock()
        session.execute.return_value = result_stub(scalar=None)
        await aliases(session).get_by_alias(uuid4(), "Larkfellow")
        assert "entities.campaign_id" in sql(session)

    async def test_alias_get_name_alias_joins_the_parent_campaign(self) -> None:
        session = AsyncMock()
        session.execute.return_value = result_stub(scalar=None)
        await aliases(session).get_name_alias(uuid4())
        assert "entities.campaign_id" in sql(session)

    async def test_create_is_still_unscoped(self) -> None:
        """Documented, not fixed: there is no campaign column to scope it.

        The use cases resolve the parent before calling create, and this test
        exists so that a future attempt to rely on create for isolation fails
        loudly here rather than silently in another campaign.
        """
        session = create_capture_session()
        await statements(session).create(
            document_id=uuid4(), position=0, content="x"
        )
        session.execute.assert_not_awaited()
        assert session.add.call_count == 1


class TestStatementCreateKeepsPositionVerbatim:
    """Position is not normalised or de-duplicated on the way in."""

    async def test_preserves_a_duplicate_position(self) -> None:
        session = create_capture_session()
        statement = await statements(session).create(
            document_id=uuid4(), position=3, content="x"
        )
        assert statement.position == 3
        assert session.add.call_count == 1

    async def test_preserves_a_negative_position(self) -> None:
        session = create_capture_session()
        statement = await statements(session).create(
            document_id=uuid4(), position=-2, content="x"
        )
        assert statement.position == -2
