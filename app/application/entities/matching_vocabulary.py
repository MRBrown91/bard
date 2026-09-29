"""Process-local cache of campaign entity vocabularies.

Building a vocabulary costs a query per campaign plus indexing every name and
alias, and P1F calls recognition once per transcript message. Repeating that on
every message meant the cost of a campaign scaled with how many times it was
spoken to, which is backwards.

**Scope: this process only.** The cache is a plain dictionary in memory, and
invalidation is an explicit call from the write paths. Running several worker
processes therefore gives each worker its own copy, and a write that lands in
one worker does not reach another's. That is acceptable here because entity and
alias writes are rare compared to recognition reads, and it is stated rather
than hidden: making it correct across processes needs a shared version marker,
which is part of the P1E indexing decision rather than a detail to invent
alongside it. A deployment that cannot tolerate a stale vocabulary should turn
the cache off by constructing :data:`MATCHING_VOCABULARIES` with
``max_campaigns=0``, and the matcher falls back to reading every time.

Bounded on purpose. A cache that grows with every campaign anyone has looked at
is a memory leak with extra steps, so the least recently used campaign is
evicted once the limit is reached. Evicting is always safe: it costs a rebuild.
"""

from collections import OrderedDict
from dataclasses import dataclass
from uuid import UUID

from app.application.entities.matching_pipeline import Vocabulary


@dataclass
class VocabularyCache:
    """A bounded, process-local cache of per-campaign vocabularies."""

    max_campaigns: int = 32
    _entries: OrderedDict[UUID, Vocabulary] | None = None

    def __post_init__(self) -> None:
        self._entries = OrderedDict()

    def get(self, campaign_id: UUID) -> Vocabulary | None:
        """Return a cached vocabulary, or None. Refreshes recency on a hit."""
        entries = self._entries
        if entries is None:
            return None
        vocabulary = entries.get(campaign_id)
        if vocabulary is not None:
            entries.move_to_end(campaign_id)
        return vocabulary

    def put(self, campaign_id: UUID, vocabulary: Vocabulary) -> None:
        """Cache a vocabulary, evicting the least recently used campaign."""
        entries = self._entries
        if entries is None or self.max_campaigns <= 0:
            return
        entries[campaign_id] = vocabulary
        entries.move_to_end(campaign_id)
        while len(entries) > self.max_campaigns:
            entries.popitem(last=False)

    def invalidate(self, campaign_id: UUID) -> None:
        """Drop a campaign's vocabulary after its entities or aliases change."""
        if self._entries is not None:
            self._entries.pop(campaign_id, None)

    def clear(self) -> None:
        """Drop everything. Used by tests, which must not inherit each other's."""
        if self._entries is not None:
            self._entries.clear()

    def __len__(self) -> int:
        return len(self._entries) if self._entries is not None else 0


#: The cache the matcher reads. A module-level singleton on purpose: the whole
#: point is to outlive a single request, and threading an instance through every
#: route and use case would be plumbing with no behavioural benefit.
MATCHING_VOCABULARIES = VocabularyCache()


def invalidate_vocabulary(repo: object) -> None:
    """Drop the cached vocabulary for whatever campaign ``repo`` is scoped to.

    Called from the entity and alias write paths, which are the only things
    that can change a vocabulary. Takes the repository rather than a campaign id
    so a write cannot invalidate the wrong campaign: the id is read from the
    same scope the write itself went through, and a repository with no campaign
    has no vocabulary to drop.
    """
    campaign_id = getattr(repo, "campaign_id", None)
    if campaign_id is not None:
        MATCHING_VOCABULARIES.invalidate(campaign_id)
