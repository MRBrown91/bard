"""Tests for entity use cases.

These tests exercise the application layer with mocked repositories so no
database, network, or LLM provider is required.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.entities.create_entity import add_alias, create_entity
from app.application.entities.get_entity import (
    get_entity,
    get_entity_with_aliases,
    list_entities,
)
from app.application.entities.update_entity import (
    remove_alias,
    soft_delete_entity,
    update_entity,
)
from app.application.exceptions import ConflictError, NotFoundError, ValidationError
from app.repositories import EntityAliasRepository, EntityRepository
from app.schemas.entity import (
    EntityAliasCreate,
    EntityCreate,
    EntityRead,
    EntityUpdate,
    EntityWithAliasesRead,
)

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def make_entity(campaign_id: UUID | None = None, **overrides: object) -> MagicMock:
    """Build an Entity-like mock with the attributes the use cases read."""
    entity = MagicMock()
    entity.id = overrides.pop("id", uuid4())
    entity.campaign_id = campaign_id or uuid4()
    entity.entity_type = overrides.pop("entity_type", "actor")
    entity.name = overrides.pop("name", "Larkfellow")
    entity.description = overrides.pop("description", "A wary innkeeper")
    entity.created_at = NOW
    entity.updated_at = NOW
    entity.deleted_at = None
    for key, value in overrides.items():
        setattr(entity, key, value)
    return entity


def make_alias(entity_id: UUID, alias: str = "The Innkeeper") -> MagicMock:
    """Build an EntityAlias-like mock."""
    row = MagicMock()
    row.id = uuid4()
    row.entity_id = entity_id
    row.alias = alias
    row.created_at = NOW
    row.updated_at = NOW
    row.deleted_at = None
    return row


def entity_repo_stub() -> AsyncMock:
    """Return a repository mock whose create() honours the campaign scope."""
    repo = AsyncMock(spec=EntityRepository)
    repo.campaign_id = uuid4()

    async def create(**kwargs: object) -> MagicMock:
        return make_entity(campaign_id=repo.campaign_id, **kwargs)

    repo.create.side_effect = create

    async def update(id: UUID, **kwargs: object) -> MagicMock:
        return make_entity(campaign_id=repo.campaign_id, id=id, **kwargs)

    repo.update.side_effect = update
    repo.session = AsyncMock(spec=AsyncSession)
    return repo


def alias_repo_stub() -> AsyncMock:
    """Return an alias repository mock whose create() returns a new row."""
    repo = AsyncMock(spec=EntityAliasRepository)

    async def create(**kwargs: object) -> MagicMock:
        entity_id = kwargs["entity_id"]
        assert isinstance(entity_id, UUID)
        return make_alias(entity_id=entity_id, alias=str(kwargs["alias"]))

    repo.create.side_effect = create
    repo.session = AsyncMock(spec=AsyncSession)
    return repo


class TestCreateEntity:
    """Tests for the create_entity use case."""

    @pytest.mark.asyncio
    async def test_creates_entity_with_campaign_from_repository(self) -> None:
        """The campaign is taken from the authorized repository scope."""
        repo = entity_repo_stub()
        alias_repo = alias_repo_stub()

        result = await create_entity(
            EntityCreate(entity_type="actor", name="Larkfellow", description=None),
            repo,
            alias_repo,
        )

        assert result.name == "Larkfellow"
        assert result.campaign_id == repo.campaign_id
        repo.create.assert_awaited_once_with(
            entity_type="actor", name="Larkfellow", description=None
        )
        alias_repo.create.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_creates_aliases_in_request_order(self) -> None:
        """Aliases supplied at creation are persisted in order."""
        repo = entity_repo_stub()
        alias_repo = alias_repo_stub()

        await create_entity(
            EntityCreate(
                entity_type="actor",
                name="Larkfellow",
                aliases=[
                    EntityAliasCreate(alias="Innkeeper"),
                    EntityAliasCreate(alias="Host"),
                ],
            ),
            repo,
            alias_repo,
        )

        created = [call.kwargs["alias"] for call in alias_repo.create.await_args_list]
        assert created == ["Innkeeper", "Host"]

    @pytest.mark.asyncio
    async def test_rejects_duplicate_aliases_in_request(self) -> None:
        """A duplicate alias in the same request is a conflict, not a 500."""
        repo = entity_repo_stub()
        alias_repo = alias_repo_stub()

        with pytest.raises(ConflictError):
            await create_entity(
                EntityCreate(
                    entity_type="actor",
                    name="Larkfellow",
                    aliases=[
                        EntityAliasCreate(alias="Innkeeper"),
                        EntityAliasCreate(alias="Innkeeper"),
                    ],
                ),
                repo,
                alias_repo,
            )

        repo.create.assert_not_awaited()


class TestAddAlias:
    """Tests for the add_alias use case."""

    @pytest.mark.asyncio
    async def test_adds_alias_to_existing_entity(self) -> None:
        """An alias is attached to the entity."""
        entity_id = uuid4()
        repo = entity_repo_stub()
        repo.get.return_value = make_entity(id=entity_id)
        alias_repo = alias_repo_stub()
        alias_repo.get_by_alias.return_value = None

        result = await add_alias(
            entity_id, EntityAliasCreate(alias="Host"), repo, alias_repo
        )

        assert result.entity_id == entity_id
        assert result.alias == "Host"
        alias_repo.create.assert_awaited_once_with(entity_id=entity_id, alias="Host")

    @pytest.mark.asyncio
    async def test_missing_entity_is_not_found(self) -> None:
        """An unknown entity yields NotFoundError."""
        repo = entity_repo_stub()
        repo.get.return_value = None
        alias_repo = alias_repo_stub()

        with pytest.raises(NotFoundError):
            await add_alias(uuid4(), EntityAliasCreate(alias="Host"), repo, alias_repo)

    @pytest.mark.asyncio
    async def test_duplicate_alias_is_conflict(self) -> None:
        """A repeated alias for the same entity yields ConflictError."""
        entity_id = uuid4()
        repo = entity_repo_stub()
        repo.get.return_value = make_entity(id=entity_id)
        alias_repo = alias_repo_stub()
        alias_repo.get_by_alias.return_value = make_alias(entity_id)

        with pytest.raises(ConflictError):
            await add_alias(
                entity_id, EntityAliasCreate(alias="Host"), repo, alias_repo
            )

        alias_repo.create.assert_not_awaited()


class TestGetEntity:
    """Tests for the get_entity use case."""

    @pytest.mark.asyncio
    async def test_returns_entity(self) -> None:
        """An existing entity is returned as a read model."""
        repo = entity_repo_stub()
        repo.get.return_value = make_entity(name="Mirek")

        result = await get_entity(uuid4(), repo)

        assert isinstance(result, EntityRead)
        assert result.name == "Mirek"

    @pytest.mark.asyncio
    async def test_missing_entity_is_not_found(self) -> None:
        """An unknown entity yields NotFoundError."""
        repo = entity_repo_stub()
        repo.get.return_value = None

        with pytest.raises(NotFoundError):
            await get_entity(uuid4(), repo)


class TestGetEntityWithAliases:
    """Tests for the get_entity_with_aliases use case."""

    @pytest.mark.asyncio
    async def test_assembles_aliases(self) -> None:
        """Aliases are read from the loaded relationship and attached."""
        entity_id = uuid4()
        entity = make_entity(
            id=entity_id,
            aliases=[make_alias(entity_id, "Host"), make_alias(entity_id, "Innkeeper")],
        )
        repo = entity_repo_stub()
        repo.get_with.return_value = entity

        result = await get_entity_with_aliases(entity_id, repo)

        assert isinstance(result, EntityWithAliasesRead)
        assert [alias.alias for alias in result.aliases] == ["Host", "Innkeeper"]
        repo.get_with.assert_awaited_once_with(entity_id, "aliases")

    @pytest.mark.asyncio
    async def test_missing_entity_is_not_found(self) -> None:
        """An unknown entity yields NotFoundError."""
        repo = entity_repo_stub()
        repo.get_with.return_value = None

        with pytest.raises(NotFoundError):
            await get_entity_with_aliases(uuid4(), repo)


class TestListEntities:
    """Tests for the list_entities use case."""

    @pytest.mark.asyncio
    async def test_delegates_filters_to_repository(self) -> None:
        """Filtering and pagination belong to the repository, not the use case."""
        repo = entity_repo_stub()
        repo.list_filtered.return_value = [make_entity(name="Mirek")]
        repo.count_filtered.return_value = 1

        items, total = await list_entities(
            repo,
            entity_type="actor",
            name_contains="mir",
            offset=20,
            limit=10,
        )

        assert total == 1
        assert [item.name for item in items] == ["Mirek"]
        repo.list_filtered.assert_awaited_once_with(
            entity_type="actor", name_contains="mir", offset=20, limit=10
        )
        repo.count_filtered.assert_awaited_once_with(
            entity_type="actor", name_contains="mir"
        )

    @pytest.mark.asyncio
    async def test_no_filters(self) -> None:
        """Omitted filters are passed through as None."""
        repo = entity_repo_stub()
        repo.list_filtered.return_value = []
        repo.count_filtered.return_value = 0

        items, total = await list_entities(repo, offset=0, limit=20)

        assert items == []
        assert total == 0


class TestUpdateEntity:
    """Tests for the update_entity use case."""

    @pytest.mark.asyncio
    async def test_applies_only_supplied_fields(self) -> None:
        """Fields absent from the request body are left untouched."""
        repo = entity_repo_stub()

        await update_entity(uuid4(), EntityUpdate(name="New Name"), repo)

        repo.update.assert_awaited_once()
        assert repo.update.await_args.kwargs == {"name": "New Name"}

    @pytest.mark.asyncio
    async def test_allows_clearing_nullable_description(self) -> None:
        """An explicit null description is a change, not an omission."""
        repo = entity_repo_stub()

        await update_entity(uuid4(), EntityUpdate(description=None), repo)

        assert repo.update.await_args.kwargs == {"description": None}

    @pytest.mark.asyncio
    async def test_empty_body_does_not_write(self) -> None:
        """An empty PATCH body is a read, not a write."""
        repo = entity_repo_stub()
        repo.get.return_value = make_entity()

        await update_entity(uuid4(), EntityUpdate(), repo)

        repo.update.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_nulling_required_field_is_rejected(self) -> None:
        """A null name is an application validation error, not a database error."""
        repo = entity_repo_stub()

        with pytest.raises(ValidationError):
            await update_entity(uuid4(), EntityUpdate.model_construct(name=None), repo)

        repo.update.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_missing_entity_is_not_found(self) -> None:
        """Updating an unknown entity yields NotFoundError."""
        repo = entity_repo_stub()
        repo.update.side_effect = None
        repo.update.return_value = None

        with pytest.raises(NotFoundError):
            await update_entity(uuid4(), EntityUpdate(name="New Name"), repo)


class TestSoftDeleteEntity:
    """Tests for the soft_delete_entity use case.

    The cascade itself is asserted in the repository tests, where the rows are
    actually stamped. What matters here is that the use case delegates and
    translates a missing entity.
    """

    @pytest.mark.asyncio
    async def test_delegates_to_the_repository(self) -> None:
        """The repository owns the cascade, so the use case only delegates."""
        repo = entity_repo_stub()
        entity_id = uuid4()
        repo.soft_delete_with_specializations.return_value = True

        await soft_delete_entity(entity_id, repo)

        repo.soft_delete_with_specializations.assert_awaited_once_with(entity_id)

    @pytest.mark.asyncio
    async def test_missing_entity_is_not_found(self) -> None:
        """Deleting an unknown entity yields NotFoundError."""
        repo = entity_repo_stub()
        repo.soft_delete_with_specializations.return_value = False

        with pytest.raises(NotFoundError):
            await soft_delete_entity(uuid4(), repo)


class TestRemoveAlias:
    """Tests for the remove_alias use case."""

    @pytest.mark.asyncio
    async def test_removes_alias_owned_by_entity(self) -> None:
        """An alias belonging to the entity is soft deleted."""
        entity_id = uuid4()
        alias = make_alias(entity_id)
        repo = entity_repo_stub()
        repo.get.return_value = make_entity(id=entity_id)
        alias_repo = alias_repo_stub()
        alias_repo.get.return_value = alias

        await remove_alias(entity_id, alias.id, repo, alias_repo)

        alias_repo.soft_delete.assert_awaited_once_with(alias.id)

    @pytest.mark.asyncio
    async def test_alias_of_another_entity_is_not_found(self) -> None:
        """An alias from a different entity is indistinguishable from missing."""
        entity_id = uuid4()
        repo = entity_repo_stub()
        repo.get.return_value = make_entity(id=entity_id)
        alias_repo = alias_repo_stub()
        alias_repo.get.return_value = make_alias(uuid4())

        with pytest.raises(NotFoundError):
            await remove_alias(entity_id, uuid4(), repo, alias_repo)

        alias_repo.soft_delete.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_missing_entity_is_not_found(self) -> None:
        """An unknown entity yields NotFoundError before touching aliases."""
        repo = entity_repo_stub()
        repo.get.return_value = None
        alias_repo = alias_repo_stub()

        with pytest.raises(NotFoundError):
            await remove_alias(uuid4(), uuid4(), repo, alias_repo)

        alias_repo.get.assert_not_awaited()
