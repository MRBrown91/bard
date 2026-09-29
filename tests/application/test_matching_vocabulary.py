"""Tests for the per-campaign vocabulary cache.

The cache is process-global, which is the point (a vocabulary has to outlive a
request) and also the risk (a shared bucket could hand one campaign's names to
another). These tests pin down the isolation, the invalidation points, and the
bound.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.entities.create_entity import add_alias, create_entity
from app.application.entities.entity_matching import EntityMatcher
from app.application.entities.matching_pipeline import build_vocabulary, make_entry
from app.application.entities.matching_vocabulary import (
    MATCHING_VOCABULARIES,
    VocabularyCache,
    invalidate_vocabulary,
)
from app.application.entities.update_entity import (
    remove_alias,
    soft_delete_entity,
    update_entity,
)
from app.repositories import EntityAliasRepository, EntityRepository, MatchTerm
from app.schemas.entity import EntityAliasCreate, EntityCreate, EntityUpdate

SELA = UUID("11111111-1111-1111-1111-111111111111")
BRAM = UUID("22222222-2222-2222-2222-222222222222")
NOW = datetime(2026, 1, 1, tzinfo=UTC)


def make_entity(campaign_id: UUID, **overrides: object) -> MagicMock:
    """An Entity-like mock carrying the attributes the use cases read."""
    entity = MagicMock()
    entity.id = overrides.pop("id", SELA)
    entity.campaign_id = campaign_id
    entity.entity_type = overrides.pop("entity_type", "actor")
    entity.name = overrides.pop("name", "Larkfellow")
    entity.description = None
    entity.created_at = NOW
    entity.updated_at = NOW
    entity.deleted_at = None
    for key, value in overrides.items():
        setattr(entity, key, value)
    return entity


def make_alias(
    entity_id: UUID, alias: str = "The Viper", kind: str = "alias"
) -> MagicMock:
    """An EntityAlias-like mock."""
    row = MagicMock()
    row.id = uuid4()
    row.entity_id = entity_id
    row.alias = alias
    row.kind = kind
    row.created_at = NOW
    row.updated_at = NOW
    row.deleted_at = None
    return row


def alias_repo_for(entity_id: UUID) -> AsyncMock:
    """A stubbed alias repository that reports a rename as successful."""
    repo = AsyncMock(spec=EntityAliasRepository)
    repo.get_by_alias.return_value = None
    repo.create.side_effect = lambda **kw: make_alias(
        kw["entity_id"], str(kw["alias"]), str(kw.get("kind", "alias"))
    )
    repo.rename.return_value = True
    repo.session = AsyncMock(spec=AsyncSession)
    return repo


def repo_for(campaign_id: UUID | None, *terms: MatchTerm) -> AsyncMock:
    """A stubbed entity repository scoped to one campaign."""
    repo = AsyncMock(spec=EntityRepository)
    repo.campaign_id = campaign_id
    repo.list_match_terms.return_value = list(terms)
    return repo


def term(entity_id: UUID, name: str, text: str, is_alias: bool = False) -> MatchTerm:
    return MatchTerm(entity_id=entity_id, name=name, term=text, is_alias=is_alias)


def vocabulary_of(*names: str) -> object:
    return build_vocabulary(
        entry
        for name in names
        if (entry := make_entry(uuid4(), name, name, is_alias=False))
    )


class TestVocabularyCache:
    def test_stores_and_returns_a_vocabulary(self) -> None:
        cache = VocabularyCache()
        campaign = uuid4()
        cache.put(campaign, vocabulary_of("Sela"))
        assert cache.get(campaign) is not None

    def test_misses_return_none(self) -> None:
        assert VocabularyCache().get(uuid4()) is None

    def test_invalidate_removes_only_that_campaign(self) -> None:
        cache = VocabularyCache()
        first, second = uuid4(), uuid4()
        cache.put(first, vocabulary_of("Sela"))
        cache.put(second, vocabulary_of("Bram"))
        cache.invalidate(first)
        assert cache.get(first) is None
        assert cache.get(second) is not None

    def test_evicts_the_least_recently_used_past_the_bound(self) -> None:
        cache = VocabularyCache(max_campaigns=2)
        first, second, third = uuid4(), uuid4(), uuid4()
        cache.put(first, vocabulary_of("Sela"))
        cache.put(second, vocabulary_of("Bram"))
        cache.get(first)  # first is now the most recently used
        cache.put(third, vocabulary_of("Duncan"))
        assert cache.get(second) is None
        assert cache.get(first) is not None
        assert cache.get(third) is not None
        assert len(cache) == 2

    def test_a_bound_of_zero_caches_nothing(self) -> None:
        """The documented way to turn caching off where a stale vocabulary
        cannot be tolerated."""
        cache = VocabularyCache(max_campaigns=0)
        campaign = uuid4()
        cache.put(campaign, vocabulary_of("Sela"))
        assert cache.get(campaign) is None
        assert len(cache) == 0

    def test_invalidate_ignores_an_unknown_campaign(self) -> None:
        VocabularyCache().invalidate(uuid4())


class TestMatcherUsesTheCache:
    @pytest.mark.asyncio
    async def test_the_second_call_does_not_read_the_database(self) -> None:
        repo = repo_for(uuid4(), term(SELA, "Sela", "Sela"))
        matcher = EntityMatcher(repo)
        await matcher.find_candidates("Sela waited.")
        await matcher.find_candidates("Sela waited.")
        assert repo.list_match_terms.await_count == 1

    @pytest.mark.asyncio
    async def test_one_campaign_cannot_see_another_campaigns_names(self) -> None:
        """Campaign isolation, which a shared cache bucket would quietly break."""
        first, second = uuid4(), uuid4()
        sela = repo_for(first, term(SELA, "Sela", "Sela"))
        bram = repo_for(second, term(BRAM, "Bram", "Bram"))
        assert await EntityMatcher(sela).find_candidates("Sela") != []
        assert await EntityMatcher(bram).find_candidates("Sela") == []
        assert await EntityMatcher(sela).find_candidates("Bram") == []

    @pytest.mark.asyncio
    async def test_a_repository_with_no_campaign_is_never_cached(self) -> None:
        """Without a campaign there is no key to scope an entry to."""
        repo = repo_for(None, term(SELA, "Sela", "Sela"))
        matcher = EntityMatcher(repo)
        await matcher.find_candidates("Sela")
        await matcher.find_candidates("Sela")
        assert repo.list_match_terms.await_count == 2
        assert len(MATCHING_VOCABULARIES) == 0

    @pytest.mark.asyncio
    async def test_a_cached_vocabulary_is_served_until_it_is_invalidated(self) -> None:
        campaign = uuid4()
        repo = repo_for(campaign, term(SELA, "Sela", "Sela"))
        matcher = EntityMatcher(repo)
        assert [c.name for c in await matcher.find_candidates("Sela waited.")] == [
            "Sela"
        ]
        repo.list_match_terms.return_value = [term(BRAM, "Bram", "Bram")]
        # Still cached, so the change is not visible yet. This is the behaviour
        # a missed invalidation would leave behind permanently.
        assert [c.name for c in await matcher.find_candidates("Bram waited.")] == []
        invalidate_vocabulary(repo)
        assert await matcher.find_candidates("Sela waited.") == []
        assert [c.name for c in await matcher.find_candidates("Bram waited.")] == [
            "Bram"
        ]


class TestWritePathsInvalidate:
    """Every write that can change a vocabulary has to drop the cached one.

    A missed invalidation is not a stale read of old data, it is a deleted
    entity that still answers to its name, so each use case is listed rather
    than relying on someone to remember.
    """

    @pytest.mark.asyncio
    async def test_create_entity_invalidates(self) -> None:
        campaign = uuid4()
        repo = repo_for(campaign)
        repo.create.return_value = make_entity(campaign, name="Sela")
        aliases = AsyncMock(spec=EntityAliasRepository)
        aliases.create.return_value = make_alias(SELA)
        await create_entity(
            EntityCreate(entity_type="actor", name="Sela"), repo, aliases
        )
        assert MATCHING_VOCABULARIES.get(campaign) is None

    @pytest.mark.asyncio
    async def test_add_alias_invalidates(self) -> None:
        campaign = uuid4()
        repo = repo_for(campaign)
        repo.get.return_value = make_entity(campaign)
        aliases = alias_repo_for(SELA)
        await add_alias(SELA, EntityAliasCreate(alias="The Viper"), repo, aliases)
        assert MATCHING_VOCABULARIES.get(campaign) is None

    @pytest.mark.asyncio
    async def test_renaming_an_entity_invalidates(self) -> None:
        """A renamed entity has to stop answering to its old name, and only the
        cache still believes in that name."""
        campaign = uuid4()
        repo = repo_for(campaign)
        repo.update.return_value = make_entity(campaign, name="Selina")
        await update_entity(
            SELA, EntityUpdate(name="Selina"), repo, alias_repo_for(SELA)
        )
        assert MATCHING_VOCABULARIES.get(campaign) is None

    @pytest.mark.asyncio
    async def test_an_empty_patch_keeps_the_cached_vocabulary(self) -> None:
        """Nothing changed, so there is no reason to throw away a vocabulary
        that is still correct."""
        campaign = uuid4()
        MATCHING_VOCABULARIES.put(campaign, vocabulary_of("Sela"))
        repo = repo_for(campaign)
        repo.get.return_value = make_entity(campaign)
        await update_entity(SELA, EntityUpdate(), repo)
        assert MATCHING_VOCABULARIES.get(campaign) is not None

    @pytest.mark.asyncio
    async def test_soft_deleting_an_entity_invalidates(self) -> None:
        campaign = uuid4()
        repo = repo_for(campaign)
        repo.soft_delete_with_specializations.return_value = True
        await soft_delete_entity(SELA, repo)
        assert MATCHING_VOCABULARIES.get(campaign) is None

    @pytest.mark.asyncio
    async def test_removing_an_alias_invalidates(self) -> None:
        campaign = uuid4()
        repo = repo_for(campaign)
        repo.get.return_value = make_entity(campaign)
        aliases = AsyncMock(spec=EntityAliasRepository)
        aliases.get.return_value = make_alias(SELA)
        await remove_alias(SELA, uuid4(), repo, aliases)
        assert MATCHING_VOCABULARIES.get(campaign) is None


class TestInvalidateHelper:
    def test_ignores_a_repository_with_no_campaign(self) -> None:
        invalidate_vocabulary(repo_for(None))

    def test_reads_the_campaign_from_the_repository(self) -> None:
        campaign = uuid4()
        MATCHING_VOCABULARIES.put(campaign, vocabulary_of("Sela"))
        invalidate_vocabulary(repo_for(campaign))
        assert MATCHING_VOCABULARIES.get(campaign) is None
