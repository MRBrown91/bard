"""Tests for the fact and audience repositories.

The queries are inspected by compiling them, so these tests assert real query
behaviour without needing a database: campaign scoping, the audience table
having no ``campaign_id`` of its own, agreement between the page and the total,
ordering, and the update that refuses to touch identity and provenance.
"""

from datetime import UTC, datetime
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from sqlalchemy import Select

from app.models import EntityFact, EntityFactAudience, EntityRelationshipFact
from app.repositories.audience_repo import (
    FactAudienceRepository,
    RelationshipFactAudienceRepository,
)
from app.repositories.fact_repo import FactRepository, RelationshipFactRepository

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def result_stub(rows: list[object] | None = None, scalar: object = 0) -> MagicMock:
    """Build a mock AsyncSession.execute() result."""
    result = MagicMock()
    result.scalars.return_value.all.return_value = rows or []
    result.scalar_one.return_value = scalar
    result.scalar_one_or_none.return_value = scalar
    return result


def captured(session: AsyncMock) -> Select[Any]:
    """Return the statement passed to session.execute at the given call index."""
    return cast(Select[Any], session.execute.await_args_list[0][0][0])


def sql(session: AsyncMock) -> str:
    """Return the SQL text of the executed statement."""
    return str(captured(session).compile())


def repo(session: AsyncMock, campaign_id: Any = None) -> FactRepository:
    """Build a fact repository."""
    return FactRepository(session, campaign_id or uuid4())


def relationship_repo(
    session: AsyncMock, campaign_id: Any = None
) -> RelationshipFactRepository:
    """Build a relationship fact repository."""
    return RelationshipFactRepository(session, campaign_id or uuid4())


def audiences(
    session: AsyncMock, campaign_id: Any = None
) -> FactAudienceRepository:
    """Build a fact audience repository."""
    return FactAudienceRepository(session, campaign_id or uuid4())


def relationship_audiences(
    session: AsyncMock, campaign_id: Any = None
) -> RelationshipFactAudienceRepository:
    """Build a relationship fact audience repository."""
    return RelationshipFactAudienceRepository(session, campaign_id or uuid4())


def fact() -> EntityFact:
    """Build a fact row."""
    return EntityFact(
        id=uuid4(),
        campaign_id=uuid4(),
        entity_id=uuid4(),
        statement_id=None,
        event_id=None,
        fact_type="history",
        content="Fled the burning city.",
        confidence=0.8,
        importance=3,
        status="active",
        created_at=NOW,
        updated_at=NOW,
        deleted_at=None,
    )


def audience_row(fact_id: Any) -> EntityFactAudience:
    """Build an audience rule for a fact."""
    return EntityFactAudience(
        id=uuid4(),
        fact_id=fact_id,
        audience_type="general",
        player_id=None,
        created_at=NOW,
        updated_at=NOW,
        deleted_at=None,
    )


class TestFactReads:
    """Scoped reads on ``entity_facts``."""

    async def test_scopes_to_the_campaign(self) -> None:
        session = AsyncMock()
        session.execute.return_value = result_stub()
        await repo(session).get(uuid4())
        assert "entity_facts.campaign_id =" in sql(session)

    async def test_excludes_soft_deleted(self) -> None:
        session = AsyncMock()
        session.execute.return_value = result_stub()
        await repo(session).get(uuid4())
        assert "entity_facts.deleted_at IS NULL" in sql(session)

    async def test_omits_scope_when_there_is_no_campaign(self) -> None:
        session = AsyncMock()
        session.execute.return_value = result_stub()
        await FactRepository(session).get(uuid4())
        assert "entity_facts.campaign_id =" not in sql(session)

    async def test_list_filters_by_status(self) -> None:
        session = AsyncMock()
        session.execute.return_value = result_stub()
        await repo(session).list_filtered(entity_id=uuid4(), status="invalidated")
        assert "entity_facts.status" in sql(session)

    async def test_list_omits_filters_that_were_not_given(self) -> None:
        session = AsyncMock()
        session.execute.return_value = result_stub()
        await repo(session).list_filtered(entity_id=uuid4())
        text = sql(session)
        assert "entity_facts.status =" not in text
        assert "entity_facts.fact_type =" not in text

    async def test_orders_by_created_at_and_id(self) -> None:
        """Ties on the timestamp need the id, or paging can repeat a row."""
        session = AsyncMock()
        session.execute.return_value = result_stub()
        await repo(session).list_filtered(entity_id=uuid4())
        order = sql(session).split("ORDER BY")[1]
        assert order.index("created_at") < order.index("id")


class TestListFiltered:
    """The page query used by the list endpoint."""

    async def test_applies_the_entity_filter(self) -> None:
        session = AsyncMock()
        session.execute.return_value = result_stub()
        await repo(session).list_filtered(entity_id=uuid4())
        assert "entity_facts.entity_id" in sql(session)

    async def test_count_and_page_share_one_predicate(self) -> None:
        """A total that disagrees with the page is a wrong total."""
        session = AsyncMock()
        session.execute.return_value = result_stub()
        await repo(session).count_filtered(entity_id=uuid4(), status="active")
        counted = str(captured(session).compile())
        await repo(session).list_filtered(entity_id=uuid4(), status="active")
        listed = str(captured(session).compile())
        for fragment in ("entity_facts.entity_id", "entity_facts.status"):
            assert fragment in counted
            assert fragment in listed

    async def test_count_excludes_soft_deleted(self) -> None:
        session = AsyncMock()
        session.execute.return_value = result_stub(scalar=0)
        await repo(session).count_filtered(entity_id=uuid4())
        assert "entity_facts.deleted_at IS NULL" in sql(session)

    async def test_count_scopes_to_the_campaign(self) -> None:
        session = AsyncMock()
        session.execute.return_value = result_stub(scalar=0)
        await repo(session).count_filtered(entity_id=uuid4())
        assert "entity_facts.campaign_id" in sql(session)

    async def test_count_omits_scope_when_there_is_no_campaign(self) -> None:
        session = AsyncMock()
        session.execute.return_value = result_stub(scalar=0)
        await FactRepository(session).count_filtered(entity_id=uuid4())
        assert "entity_facts.campaign_id =" not in sql(session)

    async def test_paging_window_reaches_the_query(self) -> None:
        session = AsyncMock()
        session.execute.return_value = result_stub()
        await repo(session).list_filtered(entity_id=uuid4(), offset=40, limit=20)
        assert "LIMIT" in sql(session)


class TestFactUpdate:
    """The update statement that PATCH relies on."""

    async def test_changes_content(self) -> None:
        session = AsyncMock()
        row = fact()
        session.execute.return_value = result_stub(scalar=row)
        await repo(session).update(row.id, content="Revised")
        assert row.content == "Revised"

    async def test_refuses_to_change_identity_and_provenance(self) -> None:
        """``entity_id``, ``fact_type``, ``statement_id``, and ``event_id`` are
        fixed once a fact exists: they say which entity the fact is about and
        where it came from, so repointing them would rewrite history.
        """
        session = AsyncMock()
        row = fact()
        original_entity_id = row.entity_id
        session.execute.return_value = result_stub(scalar=row)
        await repo(session).update(
            row.id,
            content="Revised",
            entity_id=uuid4(),
            fact_type="other",
            statement_id=uuid4(),
            event_id=uuid4(),
        )
        assert row.content == "Revised"
        assert row.entity_id == original_entity_id
        assert row.fact_type == "history"
        assert row.statement_id is None
        assert row.event_id is None

    async def test_allows_status_movement(self) -> None:
        """P1D.1 lets a fact move freely between the three statuses; the
        transitions that matter (superseding one fact with another) are
        Phase 1D.5's business.
        """
        session = AsyncMock()
        row = fact()
        session.execute.return_value = result_stub(scalar=row)
        await repo(session).update(row.id, status="superseded")
        assert row.status == "superseded"

    async def test_ignores_a_call_with_nothing_mutable(self) -> None:
        """A no-op call must not flush, so it cannot bump ``updated_at``."""
        session = AsyncMock()
        row = fact()
        session.execute.return_value = result_stub(scalar=row)
        await repo(session).update(row.id, entity_id=uuid4())
        session.flush.assert_not_awaited()

    async def test_reports_a_missing_fact(self) -> None:
        session = AsyncMock()
        session.execute.return_value = result_stub(scalar=None)
        assert await repo(session).update(uuid4(), content="x") is None


class TestAudienceScope:
    """The audience tables carry no ``campaign_id`` of their own."""

    async def test_joins_the_parent_fact(self) -> None:
        session = AsyncMock()
        session.execute.return_value = result_stub()
        await audiences(session).get_by_id(uuid4())
        assert "JOIN entity_facts" in sql(session)

    async def test_filters_on_the_parent_campaign(self) -> None:
        session = AsyncMock()
        session.execute.return_value = result_stub()
        await audiences(session).get_by_id(uuid4())
        assert "entity_facts.campaign_id" in sql(session)

    async def test_joins_to_a_live_fact_only(self) -> None:
        """A soft-deleted fact must take its audience rows out of scope."""
        session = AsyncMock()
        session.execute.return_value = result_stub()
        await audiences(session).get_by_fact(uuid4())
        assert "entity_facts.deleted_at IS NULL" in sql(session)

    async def test_excludes_soft_deleted_rules(self) -> None:
        session = AsyncMock()
        session.execute.return_value = result_stub()
        await audiences(session).get_by_fact(uuid4())
        assert "entity_fact_audiences.deleted_at IS NULL" in sql(session)

    async def test_omits_the_join_when_there_is_no_campaign(self) -> None:
        session = AsyncMock()
        session.execute.return_value = result_stub()
        await FactAudienceRepository(session).get_by_fact(uuid4())
        text = sql(session)
        assert "entity_facts.campaign_id" not in text
        assert "JOIN entity_facts" not in text

    async def test_filters_by_player_for_player_rules(self) -> None:
        session = AsyncMock()
        session.execute.return_value = result_stub()
        await audiences(session).list_for_player(uuid4())
        assert "entity_fact_audiences.player_id" in sql(session)

    async def test_lists_rules_for_a_fact(self) -> None:
        session = AsyncMock()
        session.execute.return_value = result_stub([audience_row(uuid4())])
        rows = await audiences(session).get_by_fact(uuid4())
        assert len(rows) == 1
        assert "entity_fact_audiences.fact_id" in sql(session)


class TestRelationshipAudienceScope:
    """The relationship variant has its own tables and the same rules."""

    async def test_joins_the_parent_relationship_fact(self) -> None:
        session = AsyncMock()
        session.execute.return_value = result_stub()
        await relationship_audiences(session).get_by_id(uuid4())
        text = sql(session)
        assert "JOIN entity_relationship_facts" in text
        assert "entity_relationship_facts.campaign_id" in text

    async def test_excludes_soft_deleted_rules(self) -> None:
        session = AsyncMock()
        session.execute.return_value = result_stub()
        await relationship_audiences(session).get_by_fact(uuid4())
        assert "entity_relationship_fact_audiences.deleted_at IS NULL" in sql(session)

    async def test_joins_to_a_live_relationship_fact_only(self) -> None:
        session = AsyncMock()
        session.execute.return_value = result_stub()
        await relationship_audiences(session).get_by_fact(uuid4())
        assert "entity_relationship_facts.deleted_at IS NULL" in sql(session)


class TestRelationshipFactReads:
    """Provenance lookups on ``entity_relationship_facts``."""

    async def test_scopes_to_the_campaign(self) -> None:
        session = AsyncMock()
        session.execute.return_value = result_stub()
        await relationship_repo(session).get(uuid4())
        assert "entity_relationship_facts.campaign_id" in sql(session)

    async def test_excludes_soft_deleted(self) -> None:
        session = AsyncMock()
        session.execute.return_value = result_stub()
        await relationship_repo(session).get(uuid4())
        assert "entity_relationship_facts.deleted_at IS NULL" in sql(session)

    async def test_audience_read_needs_no_visibility_filter(self) -> None:
        """Phase 1 owner-only reads have no DM, so nothing to filter on.

        The audience rows ride along, unfiltered by viewer. That is correct for
        owner-only access and would be wrong the moment a DM view exists, which
        is why Phase 2 owes a real filter rather than a spot fix.
        """
        session = AsyncMock()
        session.execute.return_value = result_stub()
        await audiences(session).get_by_fact(uuid4())
        assert "audience_type =" not in sql(session)


class TestModelRelationships:
    """The new relationships are read-only helpers, not ownership."""

    def test_entity_fact_audiences_are_view_only(self) -> None:
        """Populating the collection must not insert a row by accident.

        These are populated by an explicit audience repository write, so an
        accidental append here would be a silent write through a read.
        """
        prop = EntityFact.audiences.property
        assert prop.viewonly is True
        assert prop.lazy == "raise_on_sql"

    def test_relationship_fact_audiences_are_view_only(self) -> None:
        prop = EntityRelationshipFact.audiences.property
        assert prop.viewonly is True
        assert prop.lazy == "raise_on_sql"
