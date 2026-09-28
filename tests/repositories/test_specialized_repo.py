"""Tests for specialized repositories.

Statements are compiled rather than executed, so these assert real query
behaviour — campaign scoping, the entity-type assertion, and the soft-delete
predicates — without needing a database.
"""

from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy import Select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.exceptions import NotFoundError, ValidationError
from app.models import Entity
from app.schemas.entity import EntityType

ALL_REPO_CASES = [
    ("actor", "actors"),
    ("player", "players"),
    ("player_character", "player_characters"),
    ("location", "locations"),
    ("item", "items"),
    ("faction", "factions"),
]


def repo_for(entity_type: str, session: AsyncMock | None = None):
    """Build the repository registered for an entity type string."""
    from app.repositories.specialized_repo import (
        ActorRepository,
        FactionRepository,
        ItemRepository,
        LocationRepository,
        PlayerCharacterRepository,
        PlayerRepository,
    )

    mapping = {
        "actor": ActorRepository,
        "player": PlayerRepository,
        "player_character": PlayerCharacterRepository,
        "location": LocationRepository,
        "item": ItemRepository,
        "faction": FactionRepository,
    }
    return mapping[entity_type](session or session_stub(), uuid4())


def session_stub(rows: list[object] | None = None) -> AsyncMock:
    """Build an AsyncSession mock returning no entity rows."""
    session = AsyncMock(spec=AsyncSession)
    result = MagicMock()
    result.scalars.return_value.all.return_value = rows or []
    result.scalars.return_value.one_or_none.return_value = None
    result.scalar_one.return_value = 0
    result.scalar_one_or_none.return_value = None
    session.execute.return_value = result
    return session


def statements(session: AsyncMock) -> list[Select[Any]]:
    """Return every statement passed to session.execute."""
    return [cast(Select[Any], call[0][0]) for call in session.execute.await_args_list]


def last_sql(session: AsyncMock) -> str:
    """Return the SQL text of the last executed statement."""
    return str(statements(session)[-1].compile())


def all_sql(session: AsyncMock) -> str:
    """Return the SQL text of every statement executed.

    The specialization is loaded by a second selectinload statement, so the
    child's soft-delete predicate appears there rather than in the first.
    """
    return "\n".join(str(stmt.compile()) for stmt in statements(session))


class TestResolution:
    """Type and campaign scoping applied to every specialized lookup."""

    @pytest.mark.parametrize(("entity_type", "table"), ALL_REPO_CASES)
    @pytest.mark.asyncio
    async def test_lookup_is_scoped_and_type_asserted(
        self, entity_type: str, table: str
    ) -> None:
        """A lookup only sees a live entity of the right type in this campaign.

        The type and campaign predicates belong in the query, so a row of the
        wrong type or in another campaign is never loaded and then rejected.
        """
        repo = repo_for(entity_type)
        session = cast(AsyncMock, repo.session)

        with pytest.raises(NotFoundError):
            await repo.get(uuid4())

        text = all_sql(session)
        assert "entities.campaign_id" in text
        assert "entities.entity_type" in text
        assert "entities.deleted_at IS NULL" in text
        # The child's own soft-delete filter lives in the relationship's
        # primaryjoin, so it is asserted there rather than in a statement that
        # short-circuits when no entity is found.
        primaryjoin = str(getattr(Entity, entity_type).property.primaryjoin)
        assert f"{table}.deleted_at IS NULL" in primaryjoin
        assert "entities.id" in primaryjoin and f"{table}.entity_id" in primaryjoin

    @pytest.mark.parametrize(("entity_type", "_table"), ALL_REPO_CASES)
    def test_label_is_derived_from_the_type(
        self, entity_type: str, _table: str
    ) -> None:
        """Errors name the resource rather than a hard-coded string."""
        repo = repo_for(entity_type)
        assert repo.label == entity_type
        error = repo._not_found(uuid4())
        assert error.message == f"{entity_type.capitalize()} not found"

    @pytest.mark.asyncio
    async def test_missing_entity_and_missing_row_are_indistinguishable(self) -> None:
        """A 404 covers a wrong type, another campaign, and no row yet."""
        repo = repo_for("actor")
        with pytest.raises(NotFoundError) as exc:
            await repo.get(uuid4())
        assert exc.value.message == "Actor not found"


class TestListAndCount:
    """List and count must agree about what a specialization is."""

    @pytest.mark.parametrize(("entity_type", "table"), ALL_REPO_CASES)
    @pytest.mark.asyncio
    async def test_count_requires_a_live_specialization_row(
        self, entity_type: str, table: str
    ) -> None:
        """The total counts entities that have a live specialization.

        Counting entities of the right type alone would include entities whose
        specialization has not been created yet, and the paginated total would
        overstate what a client can page through.
        """
        repo = repo_for(entity_type)
        session = cast(AsyncMock, repo.session)

        await repo.count()

        text = last_sql(session)
        assert "count(*)" in text.lower()
        assert "EXISTS" in text
        assert f"{table}.deleted_at IS NULL" in text
        assert "entities.entity_type" in text

    @pytest.mark.asyncio
    async def test_list_paginates_after_the_existence_check(self) -> None:
        """A page is never short because bare entities were filtered out.

        The existence predicate is part of the paged query, so offset and limit
        apply to rows that are actually returned.
        """
        repo = repo_for("actor")
        session = cast(AsyncMock, repo.session)

        await repo.list(offset=20, limit=10)

        text = last_sql(session)
        assert "EXISTS" in text
        assert "actors.deleted_at IS NULL" in text
        params = statements(session)[-1].compile().params
        assert 20 in params.values()
        assert 10 in params.values()

    @pytest.mark.asyncio
    async def test_list_and_count_share_one_predicate(self) -> None:
        """The two queries cannot drift apart and disagree on the total."""
        repo = repo_for("actor")
        session = cast(AsyncMock, repo.session)

        await repo.count(name_contains="Lark")
        count_sql = last_sql(session)
        await repo.list(name_contains="Lark")
        list_sql = last_sql(session)

        for fragment in ("exists", "actors.deleted_at is null", "like", "escape"):
            assert fragment in count_sql.lower(), count_sql
            assert fragment in list_sql.lower(), list_sql

    @pytest.mark.asyncio
    async def test_list_escapes_like_wildcards(self) -> None:
        """A name filter is a substring match, not a pattern match."""
        repo = repo_for("actor")
        session = cast(AsyncMock, repo.session)

        await repo.list(name_contains="100%_sure")

        params = statements(session)[-1].compile().params
        patterns = [v for v in params.values() if isinstance(v, str)]
        assert any("\\%" in p and "\\_" in p for p in patterns), params

    @pytest.mark.asyncio
    async def test_list_orders_newest_first(self) -> None:
        """Ordering makes paging stable for equal timestamps."""
        repo = repo_for("actor")
        session = cast(AsyncMock, repo.session)

        await repo.list()

        assert "ORDER BY" in last_sql(session).upper()


class TestLinkValidation:
    """Link fields are checked on create and are not re-checked on update."""

    @pytest.mark.asyncio
    async def test_player_update_does_not_require_user_id(self) -> None:
        """Validation passes when the link field is absent.

        Regression guard: validation used to demand ``user_id`` on every write,
        which made every player PATCH fail with "user_id is required". The
        update schema forbids the field, so an update can never re-point the
        link and has nothing to re-validate.
        """
        repo = repo_for("player")
        await repo.validate(status="retired")

    @pytest.mark.asyncio
    async def test_player_missing_user_id_is_left_to_the_schema(self) -> None:
        """The repository does not duplicate the required-field check.

        The create schema declares ``user_id`` required, so a missing one is a
        422 at the boundary rather than a second, differently-worded error.
        """
        repo = repo_for("player")
        await repo.validate()

    @pytest.mark.asyncio
    async def test_player_unknown_user_is_rejected(self) -> None:
        """A user_id that resolves to nothing is refused."""
        repo = repo_for("player")
        with pytest.raises(ValidationError):
            await repo.validate(user_id=uuid4())

    @pytest.mark.asyncio
    async def test_player_character_update_does_not_require_player_id(self) -> None:
        """Same rule for the character link."""
        repo = repo_for("player_character")
        await repo.validate()

    @pytest.mark.asyncio
    async def test_player_character_requires_a_campaign_local_player(self) -> None:
        """The foreign key alone would allow a cross-campaign link.

        The campaign-scoped player lookup is what rejects it, so the error
        names the campaign rule rather than a generic missing row.
        """
        repo = repo_for("player_character", session_stub())

        with pytest.raises(ValidationError) as exc:
            await repo.validate(player_id=uuid4())

        assert exc.value.message == "Player not found in this campaign"


class TestRepositoryShape:
    """Invariants about the tables and repository wiring."""

    @pytest.mark.parametrize(("entity_type", "table"), ALL_REPO_CASES)
    def test_table_has_no_campaign_or_type_column(
        self, entity_type: str, table: str
    ) -> None:
        """Campaign and type live on the entity, so they cannot drift."""
        repo = repo_for(entity_type)
        columns = {c.name for c in repo.model.__table__.columns}
        assert "campaign_id" not in columns
        assert "entity_type" not in columns
        assert "entity_id" in columns
        assert repo.model.__tablename__ == table

    @pytest.mark.parametrize(("entity_type", "_table"), ALL_REPO_CASES)
    def test_repository_is_pinned_to_its_type(
        self, entity_type: str, _table: str
    ) -> None:
        """Each repository names the type and the relationship it reads."""
        repo = repo_for(entity_type)
        assert repo.entity_type.value == entity_type
        assert repo.relationship_name == entity_type

    @pytest.mark.parametrize(("entity_type", "_table"), ALL_REPO_CASES)
    def test_relationship_is_soft_delete_filtered(
        self, entity_type: str, _table: str
    ) -> None:
        """The ORM relationship hides a soft-deleted child row."""
        relationship = getattr(Entity, entity_type)
        primaryjoin = str(relationship.property.primaryjoin)
        assert f"{entity_type}s.deleted_at IS NULL" in primaryjoin

    def test_entity_type_values_match_the_specialized_tables(self) -> None:
        """No enum member lacks a table and no table lacks an enum member."""
        assert {e.value for e in EntityType} == {t for t, _ in ALL_REPO_CASES}
