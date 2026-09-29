"""Tests for campaign isolation and soft-delete filtering in entity repositories.

The statements are inspected by compiling them, so these tests assert real query
behaviour without needing a database.
"""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Entity, EntityAlias
from app.repositories.entity_repo import (
    SPECIALIZATION_RELATIONSHIPS,
    EntityAliasRepository,
    EntityRepository,
    MatchTerm,
    escape_like,
)
from app.schemas.entity import EntityType

NOW = datetime(2026, 1, 1, tzinfo=UTC)


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

        assert await repo.count_filtered(entity_type="actor") == 7
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

        await repo.create(entity_type="actor", name="Larkfellow")

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


class TestSoftDeleteWithSpecializations:
    """Deleting an entity must not leave a live specialization behind."""

    def make_entity_with(self, **specializations: Any) -> MagicMock:
        """Build an entity with every specialization attribute set."""
        entity = MagicMock()
        entity.id = uuid4()
        entity.created_at = NOW
        entity.updated_at = NOW
        entity.deleted_at = None
        for name in SPECIALIZATION_RELATIONSHIPS:
            row = specializations.get(name)
            if row is None:
                row = MagicMock()
                row.deleted_at = None
            setattr(entity, name, row)
        return entity

    @pytest.mark.asyncio
    async def test_stamps_entity_and_specialization_in_one_flush(self) -> None:
        """Both rows are written by the same flush, so they cannot diverge."""
        session = AsyncMock(spec=AsyncSession)
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        session.execute.return_value = result
        repo = EntityRepository(session, uuid4())
        entity = self.make_entity_with()
        repo.get_with = AsyncMock(return_value=entity)  # type: ignore[method-assign]

        deleted = await repo.soft_delete_with_specializations(entity.id)

        assert deleted is True
        assert entity.deleted_at is not None
        for name in SPECIALIZATION_RELATIONSHIPS:
            assert getattr(entity, name).deleted_at is not None
        session.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_also_stamps_the_natural_name_alias(self) -> None:
        """A deleted entity must stop being recognised by its own name.

        The name alias is what the matcher reads, so leaving it live would keep
        a deleted entity in the vocabulary while the rest of its row waits for a
        retcon. Same hazard as the specialization, same transaction.
        """
        session = AsyncMock(spec=AsyncSession)
        name_alias = MagicMock(deleted_at=None)
        name_alias.alias = "Larkfellow"
        name_alias.kind = "name"
        alias_result = MagicMock()
        alias_result.scalars.return_value.all.return_value = [name_alias]
        session.execute.return_value = alias_result
        repo = EntityRepository(session, uuid4())
        entity = self.make_entity_with()
        repo.get_with = AsyncMock(return_value=entity)  # type: ignore[method-assign]

        deleted = await repo.soft_delete_with_specializations(entity.id)

        assert deleted is True
        assert name_alias.deleted_at == entity.deleted_at

    @pytest.mark.asyncio
    async def test_stamps_exactly_the_same_instant(self) -> None:
        """One timestamp for both rows, so ordering between them is defined."""
        session = AsyncMock(spec=AsyncSession)
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        session.execute.return_value = result
        repo = EntityRepository(session, uuid4())
        entity = self.make_entity_with()
        repo.get_with = AsyncMock(return_value=entity)  # type: ignore[method-assign]

        await repo.soft_delete_with_specializations(entity.id)

        assert all(
            getattr(entity, name).deleted_at == entity.deleted_at
            for name in SPECIALIZATION_RELATIONSHIPS
        )

    @pytest.mark.asyncio
    async def test_absent_specializations_are_left_alone(self) -> None:
        """An entity with no specialization row is still deleted."""
        session = AsyncMock(spec=AsyncSession)
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        session.execute.return_value = result
        repo = EntityRepository(session, uuid4())
        entity = self.make_entity_with()
        for name in SPECIALIZATION_RELATIONSHIPS:
            setattr(entity, name, None)
        repo.get_with = AsyncMock(return_value=entity)  # type: ignore[method-assign]

        deleted = await repo.soft_delete_with_specializations(entity.id)

        assert deleted is True
        assert entity.deleted_at is not None

    @pytest.mark.asyncio
    async def test_missing_entity_reports_not_deleted(self) -> None:
        """Nothing is written when the entity is already gone or not visible."""
        session = AsyncMock(spec=AsyncSession)
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        session.execute.return_value = result
        repo = EntityRepository(session, uuid4())
        repo.get_with = AsyncMock(return_value=None)  # type: ignore[method-assign]

        assert await repo.soft_delete_with_specializations(uuid4()) is False
        session.flush.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_loads_every_specialization_relationship(self) -> None:
        """All six are loaded, so no specialization is missed by the cascade."""
        session = AsyncMock(spec=AsyncSession)
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        session.execute.return_value = result
        repo = EntityRepository(session, uuid4())
        entity = self.make_entity_with()
        repo.get_with = AsyncMock(return_value=entity)  # type: ignore[method-assign]

        await repo.soft_delete_with_specializations(entity.id)

        assert repo.get_with.await_args.args[1:] == SPECIALIZATION_RELATIONSHIPS

    def test_relationship_set_matches_the_entity_type_enum(self) -> None:
        """The cascade cannot silently miss a type that was added later."""
        assert set(SPECIALIZATION_RELATIONSHIPS) == {
            entity_type.value for entity_type in EntityType
        }
        for name in SPECIALIZATION_RELATIONSHIPS:
            assert hasattr(Entity, name)


class TestListMatchTerms:
    """The vocabulary query behind the entity matcher.

    Compiled and inspected, so these assert the query shape rather than the
    rows: what matters is that the campaign scope reaches the entity table, that
    a soft-deleted alias is excluded in the join, and that the name row makes an
    entity matchable by its own name.

    One statement, not two. An entity's own name is a ``name`` row in
    ``entity_aliases``, so the whole matchable vocabulary is a single join and
    ``is_alias`` comes off each row's kind. See ADR-027.
    """

    def session_for(self, alias_rows: list[object]) -> AsyncMock:
        """Build a session returning the alias rows."""
        session = AsyncMock(spec=AsyncSession)
        session.execute.side_effect = [self.result_with(alias_rows)]
        return session

    def result_with(self, rows: list[object]) -> MagicMock:
        """Build a result whose iterated rows are these tuples."""
        result = MagicMock()
        result.__iter__.return_value = iter(rows)
        return result

    def statements(self, session: AsyncMock) -> list[str]:
        """Return the SQL of each executed statement, in order."""
        return [
            str(cast(Select[Any], call[0][0]).compile())
            for call in session.execute.await_args_list
        ]

    @pytest.mark.asyncio
    async def test_is_a_single_statement(self) -> None:
        """The whole vocabulary is one read of one table."""
        session = self.session_for([])
        await EntityRepository(session, uuid4()).list_match_terms()
        assert len(self.statements(session)) == 1

    @pytest.mark.asyncio
    async def test_scopes_the_query_to_the_campaign(self) -> None:
        """The alias side carries no campaign column, so it inherits the scope
        only by joining the entity."""
        session = self.session_for([])
        await EntityRepository(session, uuid4()).list_match_terms()
        assert "entities.campaign_id = " in self.statements(session)[0]

    @pytest.mark.asyncio
    async def test_omits_scope_without_a_campaign(self) -> None:
        session = self.session_for([])
        await EntityRepository(session, None).list_match_terms()
        assert "entities.campaign_id = " not in self.statements(session)[0]

    @pytest.mark.asyncio
    async def test_excludes_soft_deleted_rows(self) -> None:
        session = self.session_for([])
        await EntityRepository(session, uuid4()).list_match_terms()
        text = self.statements(session)[0]
        assert "entities.deleted_at IS NULL" in text
        assert "entity_aliases.deleted_at IS NULL" in text

    @pytest.mark.asyncio
    async def test_joins_aliases_to_their_entity(self) -> None:
        session = self.session_for([])
        await EntityRepository(session, uuid4()).list_match_terms()
        alias_sql = self.statements(session)[0]
        assert "JOIN entity_aliases" in alias_sql
        assert "entity_aliases.entity_id = entities.id" in alias_sql

    @pytest.mark.asyncio
    async def test_selects_only_the_columns_the_matcher_reads(self) -> None:
        session = self.session_for([])
        await EntityRepository(session, uuid4()).list_match_terms()
        text = self.statements(session)[0]
        # A description or a timestamp would make every transcript message
        # pay for columns the matcher never compares.
        assert "entities.description" not in text
        assert "entities.created_at" not in text

    @pytest.mark.asyncio
    async def test_a_name_row_yields_a_non_alias_term(self) -> None:
        """The entity's own name is a row, and it is not an alias.

        The confidence tiers separate the two: an exact name is 1.0 and an
        exact alias 0.95. Collapsing them would quietly change every score the
        matcher reports, so the kind has to survive the read.
        """
        entity_id = uuid4()
        session = self.session_for(
            [
                SimpleNamespace(
                    id=entity_id, name="Sela", alias="Sela", kind="name"
                ),
                SimpleNamespace(
                    id=entity_id, name="Sela", alias="The Viper", kind="alias"
                ),
            ]
        )

        terms = await EntityRepository(session, uuid4()).list_match_terms()

        assert terms == [
            MatchTerm(
                entity_id=entity_id, name="Sela", term="Sela", is_alias=False
            ),
            MatchTerm(
                entity_id=entity_id,
                name="Sela",
                term="The Viper",
                is_alias=True,
            ),
        ]

    @pytest.mark.asyncio
    async def test_an_entity_with_no_extra_aliases_still_contributes_its_name(
        self,
    ) -> None:
        entity_id = uuid4()
        session = self.session_for(
            [
                SimpleNamespace(
                    id=entity_id, name="Bram", alias="Bram", kind="name"
                )
            ]
        )

        terms = await EntityRepository(session, uuid4()).list_match_terms()

        assert terms == [
            MatchTerm(
                entity_id=entity_id, name="Bram", term="Bram", is_alias=False
            )
        ]

    @pytest.mark.asyncio
    async def test_reports_every_alias_of_an_entity(self) -> None:
        entity_id = uuid4()
        session = self.session_for(
            [
                SimpleNamespace(
                    id=entity_id, name="Sela", alias="Sela", kind="name"
                ),
                SimpleNamespace(
                    id=entity_id, name="Sela", alias="The Viper", kind="alias"
                ),
                SimpleNamespace(
                    id=entity_id, name="Sela", alias="Serpent", kind="alias"
                ),
            ]
        )

        terms = await EntityRepository(session, uuid4()).list_match_terms()

        assert [t.term for t in terms] == ["Sela", "The Viper", "Serpent"]
        assert [t.is_alias for t in terms] == [False, True, True]

    @pytest.mark.asyncio
    async def test_an_alias_row_with_no_value_is_skipped(self) -> None:
        """Defensive: an empty alias must not become a matchable term."""
        session = self.session_for(
            [
                SimpleNamespace(id=uuid4(), name="Sela", alias="", kind="alias")
            ]
        )

        terms = await EntityRepository(session, uuid4()).list_match_terms()

        assert terms == []
