"""The natural name alias invariant: exactly one live name row per live entity.

ADR-027 makes an entity matchable by its own name because a ``name`` row exists
in ``entity_aliases``, rather than because of how the vocabulary query is
written. That is a data invariant, and the partial unique index
``uq_entity_aliases_one_name`` only enforces half of it: it makes a *second*
name row impossible, not a missing one. A cross-table invariant cannot be a
CHECK constraint, and a trigger would put domain logic in the database, so this
test is the enforcement for existence.

Structural, like ``test_no_undeleted_reads.py``: it walks the use cases that
create, rename and delete entities and asserts each leaves exactly one live name
row, so a new write path cannot be added without deciding what it does to the
name row.
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from app.application.entities.create_entity import add_alias, create_entity
from app.application.entities.update_entity import (
    remove_alias,
    soft_delete_entity,
    update_entity,
)
from app.models.entity.entity import ALIAS_KIND_NAME
from app.repositories import EntityAliasRepository, EntityRepository
from app.schemas.entity import EntityAliasCreate, EntityCreate, EntityUpdate

ENTITY_ID = UUID("11111111-1111-1111-1111-111111111111")
NOW = "2026-01-01"


def make_alias(entity_id: UUID, alias: str, kind: str) -> MagicMock:
    """An EntityAlias-like row."""
    row = MagicMock()
    row.id = uuid4()
    row.entity_id = entity_id
    row.alias = alias
    row.kind = kind
    row.deleted_at = None
    return row


class FakeAliasStore:
    """A minimal in-memory stand-in for entity_aliases.

    Applies the two unique indexes the real table has, so a use case that would
    violate them fails here rather than passing a mocked test and hitting a
    constraint error in production.
    """

    def __init__(self) -> None:
        self.rows: dict[UUID, list[MagicMock]] = {}

    def live_name_rows(self, entity_id: UUID) -> list[MagicMock]:
        return [
            row
            for row in self.rows.get(entity_id, [])
            if row.kind == ALIAS_KIND_NAME and row.deleted_at is None
        ]

    def add(self, entity_id: UUID, alias: str, kind: str) -> MagicMock:
        rows = self.rows.setdefault(entity_id, [])
        for row in rows:
            if row.deleted_at is None and row.alias == alias:
                raise AssertionError(
                    f"unique (entity_id, alias) violated: {alias!r}"
                )
        if kind == ALIAS_KIND_NAME and self.live_name_rows(entity_id):
            raise AssertionError("uq_entity_aliases_one_name violated")
        row = make_alias(entity_id, alias, kind)
        rows.append(row)
        return row

    def rename(self, entity_id: UUID, name: str) -> bool:
        live = self.live_name_rows(entity_id)
        if len(live) != 1:
            return False
        name_alias = live[0]
        for row in self.rows[entity_id]:
            if row is not name_alias and row.deleted_at is None and row.alias == name:
                raise AssertionError(
                    f"unique (entity_id, alias) violated renaming to {name!r}"
                )
        name_alias.alias = name
        return True

    def soft_delete(self, alias_id: UUID) -> bool:
        for rows in self.rows.values():
            for row in rows:
                if row.id == alias_id and row.deleted_at is None:
                    row.deleted_at = "2026-06-01"
                    return True
        return False

    def soft_delete_names(self, entity_id: UUID) -> None:
        for row in self.live_name_rows(entity_id):
            row.deleted_at = "2026-06-01"


@pytest.fixture
def store() -> FakeAliasStore:
    return FakeAliasStore()


@pytest.fixture
def repos(store: FakeAliasStore) -> tuple[AsyncMock, AsyncMock]:
    """An entity repo bound to one entity, and an alias repo over the store."""
    entity_repo = AsyncMock(spec=EntityRepository)
    entity_repo.campaign_id = uuid4()

    entity = MagicMock()
    entity.id = ENTITY_ID
    entity.campaign_id = entity_repo.campaign_id
    entity.entity_type = "actor"
    entity.name = "Larkfellow"
    entity.description = None
    entity.created_at = NOW
    entity.updated_at = NOW
    entity.deleted_at = None
    entity_repo.get.return_value = entity

    async def create(**kwargs: object) -> MagicMock:
        for field, value in kwargs.items():
            setattr(entity, field, value)
        return entity

    async def update(id: UUID, **kwargs: object) -> MagicMock:
        for field, value in kwargs.items():
            setattr(entity, field, value)
        return entity

    entity_repo.create.side_effect = create
    entity_repo.update.side_effect = update
    entity_repo.soft_delete_with_specializations.side_effect = (
        lambda id: store.soft_delete_names(id) or True
    )

    alias_repo = AsyncMock(spec=EntityAliasRepository)
    alias_repo.create.side_effect = lambda entity_id, alias, kind: store.add(
        entity_id, alias, kind
    )
    alias_repo.rename.side_effect = store.rename
    alias_repo.get_name_alias.side_effect = lambda entity_id: (
        store.live_name_rows(entity_id)[0] if store.live_name_rows(entity_id) else None
    )
    alias_repo.get_by_alias.side_effect = lambda entity_id, alias: next(
        (
            row
            for row in store.rows.get(entity_id, [])
            if row.alias == alias and row.deleted_at is None
        ),
        None,
    )
    alias_repo.get.side_effect = lambda alias_id: next(
        (
            row
            for rows in store.rows.values()
            for row in rows
            if row.id == alias_id and row.deleted_at is None
        ),
        None,
    )
    alias_repo.soft_delete.side_effect = store.soft_delete
    return entity_repo, alias_repo


@pytest.mark.asyncio
async def test_creating_an_entity_leaves_exactly_one_live_name_row(
    repos: tuple[AsyncMock, AsyncMock], store: FakeAliasStore
) -> None:
    entity_repo, alias_repo = repos
    await create_entity(
        EntityCreate(
            entity_type="actor",
            name="Larkfellow",
            aliases=[EntityAliasCreate(alias="Innkeeper")],
        ),
        entity_repo,
        alias_repo,
    )
    assert len(store.live_name_rows(ENTITY_ID)) == 1


@pytest.mark.asyncio
async def test_creating_an_entity_with_no_aliases_still_leaves_one(
    repos: tuple[AsyncMock, AsyncMock], store: FakeAliasStore
) -> None:
    entity_repo, alias_repo = repos
    await create_entity(
        EntityCreate(entity_type="actor", name="Larkfellow"),
        entity_repo,
        alias_repo,
    )
    assert len(store.live_name_rows(ENTITY_ID)) == 1


@pytest.mark.asyncio
async def test_the_name_row_holds_the_current_name(
    repos: tuple[AsyncMock, AsyncMock], store: FakeAliasStore
) -> None:
    entity_repo, alias_repo = repos
    await create_entity(
        EntityCreate(entity_type="actor", name="Larkfellow"),
        entity_repo,
        alias_repo,
    )
    assert store.live_name_rows(ENTITY_ID)[0].alias == "Larkfellow"


@pytest.mark.asyncio
async def test_renaming_moves_the_name_row_and_leaves_exactly_one(
    repos: tuple[AsyncMock, AsyncMock], store: FakeAliasStore
) -> None:
    entity_repo, alias_repo = repos
    await create_entity(
        EntityCreate(entity_type="actor", name="Larkfellow"),
        entity_repo,
        alias_repo,
    )
    await update_entity(
        ENTITY_ID, EntityUpdate(name="Larkfellow the Inn"),
        entity_repo,
        alias_repo,
    )
    live = store.live_name_rows(ENTITY_ID)
    assert len(live) == 1
    assert live[0].alias == "Larkfellow the Inn"


@pytest.mark.asyncio
async def test_renaming_does_not_disturb_a_real_alias(
    repos: tuple[AsyncMock, AsyncMock], store: FakeAliasStore
) -> None:
    entity_repo, alias_repo = repos
    await create_entity(
        EntityCreate(
            entity_type="actor",
            name="Larkfellow",
            aliases=[EntityAliasCreate(alias="Innkeeper")],
        ),
        entity_repo,
        alias_repo,
    )
    await update_entity(
        ENTITY_ID, EntityUpdate(name="Lark"), entity_repo, alias_repo
    )
    assert any(
        row.alias == "Innkeeper" and row.deleted_at is None
        for row in store.rows[ENTITY_ID]
    )


@pytest.mark.asyncio
async def test_adding_an_alias_leaves_exactly_one_name_row(
    repos: tuple[AsyncMock, AsyncMock], store: FakeAliasStore
) -> None:
    entity_repo, alias_repo = repos
    await create_entity(
        EntityCreate(entity_type="actor", name="Larkfellow"),
        entity_repo,
        alias_repo,
    )
    await add_alias(
        ENTITY_ID, EntityAliasCreate(alias="Innkeeper"), entity_repo, alias_repo
    )
    assert len(store.live_name_rows(ENTITY_ID)) == 1


@pytest.mark.asyncio
async def test_removing_a_real_alias_leaves_the_name_row(
    repos: tuple[AsyncMock, AsyncMock], store: FakeAliasStore
) -> None:
    entity_repo, alias_repo = repos
    await create_entity(
        EntityCreate(
            entity_type="actor",
            name="Larkfellow",
            aliases=[EntityAliasCreate(alias="Innkeeper")],
        ),
        entity_repo,
        alias_repo,
    )
    alias_id = next(
        row.id
        for row in store.rows[ENTITY_ID]
        if row.alias == "Innkeeper"
    )
    await remove_alias(ENTITY_ID, alias_id, entity_repo, alias_repo)
    assert len(store.live_name_rows(ENTITY_ID)) == 1


@pytest.mark.asyncio
async def test_soft_deleting_an_entity_leaves_no_live_name_row(
    repos: tuple[AsyncMock, AsyncMock], store: FakeAliasStore
) -> None:
    entity_repo, alias_repo = repos
    await create_entity(
        EntityCreate(entity_type="actor", name="Larkfellow"),
        entity_repo,
        alias_repo,
    )
    await soft_delete_entity(ENTITY_ID, entity_repo)
    # Stamped rather than deleted, so the row survives for a retcon.
    assert store.live_name_rows(ENTITY_ID) == []
    assert any(row.kind == ALIAS_KIND_NAME for row in store.rows[ENTITY_ID])
