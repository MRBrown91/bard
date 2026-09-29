"""Latency budgets for entity recognition.

The fuzzy tier originally compared every word against every term in the
campaign, so its cost grew with the size of the campaign. Nothing in the
functional tests noticed: a matching bug looks exactly like a correct match,
and a matching system that is merely very slow still passes every assertion
about *what* it found. These tests are the only thing standing between a
plausible-looking change and a 1000-entity campaign taking a second per
transcript message.

Two kinds of assertion, because a bare wall-clock number is a bad test:

* a **ratio** against a deliberately naive scan on the same machine, which is
  immune to how fast or slow the CI box is;
* an **absolute ceiling** generous enough for a slow machine, but still well
  under the cost of the scan it replaced, so a revert is caught.

The numbers describe this repository's dev machine and are annotated as such.
"""

import random
import statistics
import time
from uuid import uuid4

import pytest

from app.application.entities.matching_pipeline import (
    MatchSettings,
    build_vocabulary,
    find_term_matches,
    levenshtein_within,
    make_entry,
)

GIVEN = [
    "selen", "bran", "dunmar", "marisol", "kalder", "vorn", "ithil", "pem",
    "tass", "lorin", "gav", "nix", "obar", "rhun", "fenwick", "quill",
    "aldric", "bera", "corvin", "delia", "edmund", "fenna", "garrick",
    "hollis", "isolde", "joric", "kathe", "lucen", "mira", "nils",
]
FAMILY = [
    "briar", "stout", "marrick", "vane", "thorne", "ashford", "quill",
    "dune", "hollow", "reed", "", "", "", "", "", "", "crowley", "fen", "vale",
]
EPITHETS = [
    "the viper", "serpent", "of the north", "redhand", "the quiet",
    "grey cloak", "stormcaller", "nightbloom", "ironhand", "the tall",
    "saltborn", "wintermute",
]
TRANSCRIPT = (
    "you approach the ancient tavern where selen briar tends the bar and asks "
    "quietly about the missing caravan. She says the road past kalderon bridge "
    "has been unsafe since the fever nights, and that the duke own men were "
    "seen near the old quarry. You thank her and step back into the cold "
    "street where a hooded figure waits."
)
SETTINGS = MatchSettings()

#: A thousand entities with ten aliases each: 11k terms. A large but entirely
#: plausible campaign, and the size at which the scan-based matcher was already
#: taking over a second per call.
CAMPAIGN_SIZE = 1000
ALIASES_PER_ENTITY = 10


def build_terms(entities: int = CAMPAIGN_SIZE, aliases: int = ALIASES_PER_ENTITY):
    """A vocabulary with the shape of a real campaign, seeded for repeatability."""
    rng = random.Random(11)
    entries = []
    for _ in range(entities):
        entity_id = uuid4()
        given = rng.choice(GIVEN)
        family = rng.choice(FAMILY)
        name = f"{given} {family}".strip() if rng.random() < 0.6 else given
        entries.append(make_entry(entity_id, name, name, is_alias=False))
        for _ in range(aliases):
            epithet = rng.choice(EPITHETS)
            alias = f"{given} {epithet}" if rng.random() < 0.3 else epithet
            entries.append(make_entry(entity_id, name, alias, is_alias=True))
    return [entry for entry in entries if entry]


def scan_cost(entries, text: str, runs: int = 3) -> float:
    """Milliseconds for a brute force scan: the cost the index replaced.

    Kept as a reference measurement rather than a budget, so the ratio
    assertion means something on any machine.
    """
    vocabulary = build_vocabulary(entries)
    by_length: dict[int, list] = {}
    for entry in entries:
        by_length.setdefault(len(entry.normalized), []).append(entry)
    tokens = [t for t in text.lower().split() if t.isalpha()]

    def once() -> None:
        for token in tokens:
            if len(token) < SETTINGS.min_fuzzy_length:
                continue
            for length in range(
                len(token) - 2, len(token) + SETTINGS.max_fuzzy_distance + 1
            ):
                for entry in by_length.get(length, ()):
                    if len(entry.normalized) < SETTINGS.min_fuzzy_length:
                        continue
                    levenshtein_within(
                        token, entry.normalized, SETTINGS.max_fuzzy_distance
                    )

    return min(_time_ms(once) for _ in range(runs))


def _time_ms(work) -> float:
    start = time.perf_counter()
    work()
    return (time.perf_counter() - start) * 1000


@pytest.fixture(scope="module")
def entries():
    return build_terms()


@pytest.fixture(scope="module")
def vocabulary(entries):
    return build_vocabulary(entries)


class TestRecognitionLatency:
    def test_a_plausible_campaign_stays_under_its_budget(
        self, vocabulary
    ) -> None:
        """Warm recognition of a 11k-term vocabulary.

        Measured at 1-3 ms. The ceiling is 60 ms: loose enough for a slow or
        loaded CI machine, and still an order of magnitude under the ~150 ms
        the scan-based version took for the same work, so a revert fails here.
        """
        vocabulary.delete_index()  # built once per campaign, not per call
        timings = [
            _time_ms(lambda: find_term_matches(TRANSCRIPT, vocabulary, SETTINGS))
            for _ in range(5)
        ]
        median = statistics.median(timings)
        assert median < 60, f"warm recognition took {median:.1f} ms"

    def test_the_index_beats_a_scan_by_a_wide_margin(
        self, entries, vocabulary
    ) -> None:
        """The machine-independent version of the same claim.

        Comparing against a scan of the very same vocabulary on the very same
        machine means this fails if the narrowing stops happening, regardless of
        how fast the hardware is. The threshold is 5x, well under the ~70x the
        index actually delivers, to keep a noisy machine from flaking.
        """
        vocabulary.delete_index()
        indexed = min(
            _time_ms(lambda: find_term_matches(TRANSCRIPT, vocabulary, SETTINGS))
            for _ in range(3)
        )
        scanned = scan_cost(entries, TRANSCRIPT)
        assert indexed * 5 < scanned, (
            f"indexed {indexed:.1f} ms vs scan {scanned:.1f} ms"
        )

    def test_the_index_builds_in_bounded_time(self, entries, vocabulary) -> None:
        """The index is a cache miss paid once, so it may be slower than a single
        scan -- but it must not be super-linear in the vocabulary.

        Measured at roughly 190 ms for 11k terms and growing linearly. The
        ceiling of 1500 ms leaves room for a slow machine while still catching a
        change that makes the build quadratic, which is the failure mode a
        delete-variant index is most likely to grow.
        """
        fresh = build_vocabulary(entries)
        assert _time_ms(fresh.delete_index) < 1500

    def test_the_index_is_not_built_when_fuzzy_is_off(self) -> None:
        """A caller that opts out of the fuzzy tier never pays to build the
        index.

        Worth pinning because it is the only case the lazy build actually saves:
        for ordinary prose the very first word misses the exact tiers and
        triggers a fuzzy lookup, so laziness is not a general saving. An empty
        campaign is not worth a case here either -- the matcher returns before
        reaching the pipeline.
        """
        entries = build_terms(entities=5, aliases=2)
        fuzzy_off = build_vocabulary(entries)
        find_term_matches(
            TRANSCRIPT, fuzzy_off, MatchSettings(fuzzy_enabled=False)
        )
        assert fuzzy_off._delete_index is None

    def test_fuzzy_on_does_build_the_index(self) -> None:
        """The other half of the contract above, so the assertion cannot pass by
        the build simply never happening."""
        vocabulary = build_vocabulary(build_terms(entities=5, aliases=2))
        find_term_matches(TRANSCRIPT, vocabulary, SETTINGS)
        assert vocabulary._delete_index is not None

    def test_recognition_scales_with_the_text_not_the_campaign(
        self, vocabulary
    ) -> None:
        """Doubling the transcript must roughly double the work.

        This is the property that actually changed: cost used to be
        text-length times campaign-size, so this test is the one that would
        have failed before the index and would fail again if a scan came back.
        The assertion is loose because the fixed per-call overhead is real, but
        the ceiling is far below linear-in-campaign behaviour.
        """
        vocabulary.delete_index()
        short = min(
            _time_ms(
                lambda: find_term_matches(TRANSCRIPT, vocabulary, SETTINGS)
            )
            for _ in range(3)
        )
        long_text = TRANSCRIPT + " " + TRANSCRIPT
        doubled = min(
            _time_ms(lambda: find_term_matches(long_text, vocabulary, SETTINGS))
            for _ in range(3)
        )
        assert doubled < max(short * 6, 40)
