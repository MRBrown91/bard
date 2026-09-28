"""Deterministic entity matching steps, as pure functions.

Nothing here touches the database or the transport. The pipeline is a pure
function of (tokens, vocabulary, settings), which is what makes it testable in
isolation and keeps the ordering and scoring rules in one place.

**How a mention is found.** The text is tokenized into words, and every
contiguous run of 1..N tokens is looked up in a vocabulary built from the
campaign's entity names and aliases. Generating candidates from *tokens* rather
than by substring search is what stops a short name from matching inside a
longer word: "Ann" is never a candidate inside "Anne", because "Anne" is a
single token and only whole tokens are looked up.

**Scoring is by strongest step, one answer per term.** A term that matched a
name exactly is not also reported as a case-insensitive or fuzzy match, so the
confidence on a candidate always means the same thing: the best evidence found
for it. The tiers are strictly ordered and do not overlap:

===================  ==========
Step                 Confidence
===================  ==========
exact name           1.0
exact alias          0.95
case-insensitive     0.9
  name
case-insensitive     0.85
  alias
fuzzy, distance 1    0.8
fuzzy, distance 2    0.7
===================  ==========

Fuzzy scores on distance alone, not on whether the term is a name or an alias,
because at that tier the two are not meaningfully different. When a name and an
alias tie on distance the name wins: it is the entity's primary identifier.
"""

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from uuid import UUID

# Runs of alphanumerics, treating underscore as a separator. Unicode-aware, so
# non-ASCII names tokenize into words rather than into single characters.
_TOKEN = re.compile(r"[^\W_]+", re.UNICODE)

# Confidence per tier. Named so a test can assert the ordering without
# hardcoding the numbers a second time.
EXACT_NAME_CONFIDENCE = 1.0
EXACT_ALIAS_CONFIDENCE = 0.95
CASELESS_NAME_CONFIDENCE = 0.9
CASELESS_ALIAS_CONFIDENCE = 0.85
#: Keyed by edit distance, and deliberately the only source of a fuzzy score.
FUZZY_CONFIDENCE: dict[int, float] = {1: 0.8, 2: 0.7}


@dataclass(frozen=True, slots=True)
class MatchSettings:
    """Tunables for the matching pipeline.

    ``fuzzy_enabled`` is separate from ``max_fuzzy_distance`` so a caller can
    turn the tier off without passing an impossible distance, which reads as a
    contradiction.
    """

    fuzzy_enabled: bool = True
    max_fuzzy_distance: int = 2
    #: Fuzzy needs the *stored term* to be at least this long, not just the
    #: word in the text. Checking only the text would still let a three-letter
    #: name sit within distance 1 of any four-letter word, so "Anne" would
    #: match a character named "Ann" -- and two short names would still sit
    #: within distance 2 of each other, which is what the floor is for. A term
    #: shorter than this is never fuzzy matched.
    min_fuzzy_length: int = 4
    #: Longest run of tokens considered as one term. Derived from the
    #: vocabulary by default; set only to cap pathological input.
    max_phrase_tokens: int | None = None

    def __post_init__(self) -> None:
        if self.max_fuzzy_distance not in FUZZY_CONFIDENCE:
            # A distance with no defined tier would fall through to a floor
            # value and quietly misreport how sure a match is. Refuse instead.
            raise ValueError(
                "max_fuzzy_distance must be one of "
                f"{sorted(FUZZY_CONFIDENCE)}, got {self.max_fuzzy_distance}"
            )
        if self.min_fuzzy_length < 1:
            raise ValueError("min_fuzzy_length must be at least 1")


@dataclass(frozen=True, slots=True)
class VocabularyEntry:
    """One term in the vocabulary and the entity it identifies."""

    entity_id: UUID
    name: str
    term: str
    is_alias: bool
    #: Tokens of ``term``: the shape the text is matched against.
    tokens: tuple[str, ...]
    #: Lowercased token join, the key for the case-insensitive and fuzzy tiers.
    normalized: str


@dataclass(slots=True)
class Vocabulary:
    """Indexed terms, ready for lookup.

    Names are *not* unique: ``ix_entities_campaign_name`` is a plain index, so
    two entities in one campaign may share a name. Every lookup therefore maps
    to a list, and one text match can yield several candidates. That is correct
    rather than ambiguous -- the domain permits the collision, so the matcher
    reports what is actually there instead of silently picking one.

    Not frozen: the maps are mutable containers, built once and then only read.
    """

    entries: tuple[VocabularyEntry, ...] = ()
    exact: dict[str, list[VocabularyEntry]] = field(default_factory=dict)
    caseless: dict[str, list[VocabularyEntry]] = field(default_factory=dict)
    by_length: dict[int, list[VocabularyEntry]] = field(default_factory=dict)
    max_tokens: int = 1


@dataclass(frozen=True, slots=True)
class TermMatch:
    """One entity matched at one position, with the tier that produced it.

    A position can produce several of these, when several entities carry the
    same term: nothing in the schema forbids two entities in a campaign from
    sharing a name, and reporting only one of them would silently drop a real
    entity from the results.
    """

    entry: VocabularyEntry
    matched_text: str
    confidence: float
    start: int
    stop: int


def tokenize(text: str) -> tuple[str, ...]:
    """Split text into word tokens."""
    return tuple(match.group(0) for match in _TOKEN.finditer(text))


def normalize(tokens: Sequence[str]) -> str:
    """Build the lookup key for a run of tokens.

    Joining with a single space means the key for "O'Brien" ("o brien") equals
    the key the text produces for "O'Brien", so a name containing punctuation
    matches the way a reader expects even though the tokenizer split it.
    """
    return " ".join(tokens).lower()


def levenshtein_within(a: str, b: str, limit: int) -> int | None:
    """Return the edit distance between ``a`` and ``b``, or None if above ``limit``.

    None rather than a large number, so a caller skips the term instead of
    comparing distances afterwards. The row-based inner loop gives up as soon as
    a whole row exceeds ``limit``: edit distance is non-decreasing in the prefix
    lengths, so a row that is already too far cannot be recovered by a later
    one. That is what keeps a long text from paying for full-length
    comparisons against the whole vocabulary.
    """
    if abs(len(a) - len(b)) > limit:
        return None
    if a == b:
        return 0
    previous = list(range(len(b) + 1))
    for row, char_a in enumerate(a, start=1):
        current = [row]
        for column, char_b in enumerate(b, start=1):
            current.append(
                min(
                    previous[column] + 1,
                    current[column - 1] + 1,
                    previous[column - 1] + (char_a != char_b),
                )
            )
        if min(current) > limit:
            return None
        previous = current
    distance = previous[-1]
    return distance if distance <= limit else None


def make_entry(
    entity_id: UUID, name: str, term: str, *, is_alias: bool
) -> VocabularyEntry | None:
    """Build an indexable entry, or None when the term has no tokens.

    A blank name or alias can match nothing, and admitting it would put an
    empty key in the index that every empty run of tokens hits.
    """
    tokens = tokenize(term)
    if not tokens:
        return None
    return VocabularyEntry(
        entity_id=entity_id,
        name=name,
        term=term,
        is_alias=is_alias,
        tokens=tokens,
        normalized=normalize(tokens),
    )


def build_vocabulary(entries: Iterable[VocabularyEntry]) -> Vocabulary:
    """Index entries for lookup."""
    entries = tuple(entries)

    exact: dict[str, list[VocabularyEntry]] = {}
    caseless: dict[str, list[VocabularyEntry]] = {}
    by_length: dict[int, list[VocabularyEntry]] = {}
    for entry in entries:
        exact.setdefault(" ".join(entry.tokens), []).append(entry)
        caseless.setdefault(entry.normalized, []).append(entry)
        by_length.setdefault(len(entry.normalized), []).append(entry)

    return Vocabulary(
        entries=tuple(entries),
        exact=exact,
        caseless=caseless,
        by_length=by_length,
        max_tokens=max((len(entry.tokens) for entry in entries), default=1),
    )


def _ordered(entries: Iterable[VocabularyEntry]) -> tuple[VocabularyEntry, ...]:
    """Put entries in a total order that does not depend on the query."""
    return tuple(
        sorted(entries, key=lambda entry: (entry.name, str(entry.entity_id)))
    )


def _tier_confidence(entry: VocabularyEntry, *, caseless: bool) -> float:
    if entry.is_alias:
        return CASELESS_ALIAS_CONFIDENCE if caseless else EXACT_ALIAS_CONFIDENCE
    return CASELESS_NAME_CONFIDENCE if caseless else EXACT_NAME_CONFIDENCE


def _best_tier(
    entries: Sequence[VocabularyEntry], *, caseless: bool
) -> tuple[tuple[VocabularyEntry, ...], float]:
    """Keep only the entries at the strongest tier in a bucket.

    A bucket can hold names and aliases of different entities at once. The
    strongest tier present wins outright, so a name at 1.0 excludes an alias at
    0.95 -- the same text is not two different pieces of evidence. Within the
    winning tier every entry survives, because two entities sharing a name are
    both genuinely matched by it.
    """
    best = max(_tier_confidence(entry, caseless=caseless) for entry in entries)
    return (
        _ordered(
            entry
            for entry in entries
            if _tier_confidence(entry, caseless=caseless) == best
        ),
        best,
    )


def _fuzzy_best(
    normalized: str, vocabulary: Vocabulary, settings: MatchSettings
) -> tuple[tuple[VocabularyEntry, ...], float] | None:
    """Find the closest entries within the distance limit.

    Only entries whose length is within the limit are compared. That is a
    necessary condition for any distance at or under the limit, so it costs no
    real matches, and it is what keeps this from scanning the whole vocabulary
    for every word in the text.

    Every entry at the winning distance comes back, and a name beats an alias at
    the same distance, so a shared term is not reported for one entity and
    withheld from another.
    """
    if len(normalized) < settings.min_fuzzy_length:
        return None
    scored: list[tuple[int, int, VocabularyEntry]] = []
    lowest = len(normalized) - settings.max_fuzzy_distance
    highest = len(normalized) + settings.max_fuzzy_distance
    for length in range(lowest, highest + 1):
        for entry in vocabulary.by_length.get(length, ()):
            if len(entry.normalized) < settings.min_fuzzy_length:
                continue
            distance = levenshtein_within(
                normalized, entry.normalized, settings.max_fuzzy_distance
            )
            if distance is None or distance == 0:
                # Zero means equal, which the case-insensitive tier already
                # reports. Scoring it again would only add a second, worse
                # candidate for the same term.
                continue
            # 0 for a name, 1 for an alias, so a name wins a distance tie the
            # same way it wins a tier tie in the exact buckets.
            scored.append((distance, 1 if entry.is_alias else 0, entry))
    if not scored:
        return None
    best = min((distance, kind) for distance, kind, _ in scored)
    winners = _ordered(
        entry for distance, kind, entry in scored if (distance, kind) == best
    )
    return winners, FUZZY_CONFIDENCE[best[0]]


def _match_phrase(
    phrase: str, vocabulary: Vocabulary, settings: MatchSettings
) -> tuple[tuple[VocabularyEntry, ...], float] | None:
    """Score one run of tokens against the vocabulary, strongest tier first.

    ``phrase`` is a space join of whole tokens, so lowering it is the same
    operation as normalizing a vocabulary term.
    """
    entries = vocabulary.exact.get(phrase)
    if entries:
        return _best_tier(entries, caseless=False)

    entries = vocabulary.caseless.get(phrase.lower())
    if entries:
        return _best_tier(entries, caseless=True)

    if not settings.fuzzy_enabled:
        return None
    return _fuzzy_best(phrase.lower(), vocabulary, settings)


def find_term_matches(
    text: str, vocabulary: Vocabulary, settings: MatchSettings | None = None
) -> list[TermMatch]:
    """Run the pipeline and return every term found, in text order.

    Longest match wins at each position and a match consumes its tokens, so
    "Old Man" is not also reported as "Old" followed by "Man". Greedy
    longest-first is the standard reading of a mention, and it makes the result
    independent of vocabulary ordering: the alternative, preferring a name over
    a longer phrase, gives up a more specific match to win a tie.
    """
    settings = settings or MatchSettings()
    tokens = tokenize(text)
    if not tokens:
        return []

    # Character offsets, so matched_text is the original substring with its own
    # punctuation and case rather than a rejoined approximation of it.
    spans = [match.span() for match in _TOKEN.finditer(text)]
    starts = [start for start, _ in spans]
    stops = [stop for _, stop in spans]

    longest = vocabulary.max_tokens
    if settings.max_phrase_tokens is not None:
        longest = min(longest, settings.max_phrase_tokens)
    longest = max(1, min(longest, len(tokens)))

    matches: list[TermMatch] = []
    index = 0
    while index < len(tokens):
        hit: tuple[tuple[VocabularyEntry, ...], float, int] | None = None
        for width in range(min(longest, len(tokens) - index), 0, -1):
            found = _match_phrase(
                " ".join(tokens[index : index + width]), vocabulary, settings
            )
            if found is not None:
                hit = (found[0], found[1], width)
                break
        if hit is None:
            index += 1
            continue
        entries, confidence, width = hit
        start, stop = starts[index], stops[index + width - 1]
        for entry in entries:
            matches.append(
                TermMatch(
                    entry=entry,
                    matched_text=text[start:stop],
                    confidence=confidence,
                    start=start,
                    stop=stop,
                )
            )
        index += width
    return matches
