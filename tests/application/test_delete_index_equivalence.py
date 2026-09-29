"""The delete index must not change which entities are recognized.

The fuzzy tier used to compare a word against every term of a similar length.
It now looks the word up in a delete index and confirms the few candidates it
returns with a real edit distance. That is only safe if the index is a
*superset* of the terms a distance-limited scan would have found: a narrowing
that dropped a real match would silently stop recognizing a name that used to
work, and no confidence assertion would notice, because the name would simply
stop appearing.

So these tests keep a deliberately naive reference scan and assert the index
agrees with it, on vocabularies built to make the two disagree if they can.
"""

import random
import string
from uuid import uuid4

import pytest

from app.application.entities.matching_pipeline import (
    FUZZY_CONFIDENCE,
    MatchSettings,
    VocabularyEntry,
    _fuzzy_best,
    build_vocabulary,
    find_term_matches,
    levenshtein_within,
    make_entry,
)

ALPHABET = string.ascii_lowercase + "áé"


def reference_fuzzy(
    phrase: str,
    entries: list[VocabularyEntry],
    distance: int = 2,
    min_length: int = 4,
) -> dict[str, int]:
    """Every term within ``distance``, as term -> distance, by brute force.

    Mirrors the length gates the production lookup applies: a probe shorter
    than ``min_length`` is not fuzzy matched at all, and neither is a stored
    term. Distance 0 is excluded because the case-insensitive tier already
    reports an exact-equality hit, and scoring it again would double-report it.
    """
    if len(phrase) < min_length:
        return {}
    found: dict[str, int] = {}
    for entry in entries:
        if len(entry.normalized) < min_length:
            continue
        measured = levenshtein_within(phrase, entry.normalized, distance)
        if measured is not None and measured > 0:
            found.setdefault(entry.normalized, measured)
    return found


def index_fuzzy(
    phrase: str, vocabulary, settings: MatchSettings
) -> tuple[set[str], float | None]:
    """The production lookup: the winning terms and the confidence it scored."""
    result = _fuzzy_best(phrase, vocabulary, settings)
    if result is None:
        return set(), None
    entries, confidence = result
    return {entry.normalized for entry in entries}, confidence


def assert_agrees(phrase: str, entries, vocabulary, settings) -> None:
    """The index may narrow the search, but it may not change the answer.

    Two properties, both required:

    * nothing it reports is a false positive -- every reported term really is
      within the distance its confidence claims;
    * nothing better was missed -- the distance it settled on is the best
      distance that exists, so a name that used to score 0.8 still scores 0.8
      rather than silently dropping to no match at all.
    """
    expected = reference_fuzzy(phrase, entries, settings.max_fuzzy_distance)
    reported, confidence = index_fuzzy(phrase, vocabulary, settings)
    if not expected:
        assert not reported and confidence is None, phrase
        return
    assert reported, phrase
    assert reported <= set(expected), phrase
    best = min(expected.values())
    assert confidence == FUZZY_CONFIDENCE[best], (phrase, confidence, best)
    for term in reported:
        assert expected[term] == best, (phrase, term)


def nasty_vocabulary(count: int, seed: int = 3) -> list[VocabularyEntry]:
    """Terms chosen to collide: short names, repeated letters, accents, phrases."""
    rng = random.Random(seed)
    entries = []
    for index in range(count):
        length = rng.randint(1, 9)
        term = "".join(rng.choice(ALPHABET) for _ in range(length))
        if rng.random() < 0.3:
            tail = "".join(rng.choice(ALPHABET) for _ in range(rng.randint(1, 5)))
            term = f"{term} {tail}"
        entry = make_entry(
            uuid4(), f"Name {index}", term, is_alias=rng.random() < 0.5
        )
        if entry:
            entries.append(entry)
    return entries


def corrupted_probes(
    entries: list[VocabularyEntry], per_entry: int = 3, seed: int = 5
) -> list[str]:
    """Terms damaged by one or two edits, which is what fuzzy exists to absorb."""
    rng = random.Random(seed)
    probes: list[str] = []
    for entry in entries:
        for _ in range(per_entry):
            characters = list(entry.normalized)
            for _ in range(rng.randint(1, 2)):
                if not characters:
                    break
                action = rng.choice("sid")
                position = rng.randrange(len(characters))
                if action == "s":
                    characters[position] = rng.choice(ALPHABET)
                elif action == "i":
                    characters.insert(position, rng.choice(ALPHABET))
                else:
                    del characters[position]
            probes.append("".join(characters))
    return probes


class TestDeleteIndexEquivalence:
    @pytest.mark.parametrize("seed", [3, 17, 99])
    def test_finds_everything_a_brute_force_scan_would(self, seed: int) -> None:
        entries = nasty_vocabulary(300, seed=seed)
        vocabulary = build_vocabulary(entries)
        settings = MatchSettings()
        probes = [e.normalized for e in entries] + corrupted_probes(entries)
        for probe in probes:
            assert_agrees(probe, entries, vocabulary, settings)

    def test_random_junk_does_not_diverge(self) -> None:
        """An unrelated probe generator, so agreement is not an artifact of
        probing with the same words the vocabulary was built from."""
        entries = nasty_vocabulary(200, seed=41)
        vocabulary = build_vocabulary(entries)
        settings = MatchSettings()
        rng = random.Random(7)
        probes = [
            "".join(rng.choice(ALPHABET) for _ in range(rng.randint(1, 12)))
            for _ in range(300)
        ]
        for probe in probes:
            assert_agrees(probe, entries, vocabulary, settings)

    def test_agrees_when_fuzzy_distance_is_reduced(self) -> None:
        """The index is built for the widest distance, so a stricter setting has
        to keep agreeing with a brute force scan at that same distance."""
        entries = nasty_vocabulary(200, seed=13)
        vocabulary = build_vocabulary(entries)
        settings = MatchSettings(max_fuzzy_distance=1)
        for probe in [e.normalized for e in entries] + corrupted_probes(entries):
            assert_agrees(probe, entries, vocabulary, settings)

    def test_reported_confidence_matches_the_real_distance(self) -> None:
        """A fuzzy score is a claim about the text, so the pipeline's claim has
        to survive recomputing the distance the entry actually has."""
        entries = nasty_vocabulary(200, seed=29)
        vocabulary = build_vocabulary(entries)
        for probe in corrupted_probes(entries, 1, seed=31):
            for match in find_term_matches(probe, vocabulary, MatchSettings()):
                if match.confidence not in FUZZY_CONFIDENCE.values():
                    continue
                expected = min(
                    distance
                    for distance, score in FUZZY_CONFIDENCE.items()
                    if score == match.confidence
                )
                actual = levenshtein_within(
                    probe, match.entry.normalized, MatchSettings().max_fuzzy_distance
                )
                assert actual == expected, (probe, match.entry.normalized)
