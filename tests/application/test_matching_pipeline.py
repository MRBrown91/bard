"""Tests for the deterministic matching pipeline.

Each tier is tested on its own so a failure names the step that broke, then the
tiers are tested together for the properties that only show up in combination:
longest match wins, no substring matches, no overlapping reports, and a total
order that does not depend on the database.
"""

from uuid import uuid4

import pytest

from app.application.entities.matching_pipeline import (
    CASELESS_ALIAS_CONFIDENCE,
    CASELESS_NAME_CONFIDENCE,
    EXACT_ALIAS_CONFIDENCE,
    EXACT_NAME_CONFIDENCE,
    FUZZY_CONFIDENCE,
    MatchSettings,
    build_vocabulary,
    find_term_matches,
    levenshtein_within,
    make_entry,
    normalize,
    tokenize,
)

SELA = uuid4()
BRAM = uuid4()
LARK = uuid4()
HOUSE_RIVEN = uuid4()
DUNCAN = uuid4()


def entry(entity_id: object, name: str, term: str, is_alias: bool = False) -> object:
    """Build a vocabulary entry, asserting the term is indexable."""
    built = make_entry(entity_id, name, term, is_alias=is_alias)
    assert built is not None, f"term {term!r} produced no entry"
    return built


def vocabulary(*entries: object) -> object:
    """Index a set of entries."""
    return build_vocabulary(entries)


def scores(text: str, vocab: object, settings: MatchSettings | None = None) -> list:
    """Return the confidence of each match, in text order."""
    return [m.confidence for m in find_term_matches(text, vocab, settings)]


def names(text: str, vocab: object, settings: MatchSettings | None = None) -> list:
    """Return the entity name each match resolved to."""
    return [m.entry.name for m in find_term_matches(text, vocab, settings)]


class TestTokenize:
    """Tokenization decides what can match at all."""

    def test_splits_on_whitespace_and_punctuation(self) -> None:
        assert tokenize("Sela crossed, the bridge!") == (
            "Sela",
            "crossed",
            "the",
            "bridge",
        )

    def test_keeps_digits_in_a_token(self) -> None:
        assert tokenize("Gate 9 opened") == ("Gate", "9", "opened")

    def test_treats_underscore_as_a_separator(self) -> None:
        assert tokenize("guard_captain") == ("guard", "captain")

    def test_handles_non_ascii_names(self) -> None:
        assert tokenize("Åsa och Élodie") == ("Åsa", "och", "Élodie")

    def test_empty_and_punctuation_only(self) -> None:
        assert tokenize("") == ()
        assert tokenize("... !!! ") == ()


class TestNormalize:
    """The key both sides are looked up by."""

    def test_lowercases_and_joins(self) -> None:
        assert normalize(("Sela", "of", "Riven")) == "sela of riven"

    def test_apostrophe_name_matches_the_same_text(self) -> None:
        """A name with punctuation is split, and must still match itself."""
        vocab = vocabulary(entry(uuid4(), "O'Brien", "O'Brien"))
        assert names("He found O'Brien waiting.", vocab) == ["O'Brien"]


class TestLevenshtein:
    """The distance function the fuzzy tier depends on."""

    def test_identical_strings(self) -> None:
        assert levenshtein_within("sela", "sela", 2) == 0

    def test_one_substitution(self) -> None:
        assert levenshtein_within("sela", "selb", 2) == 1

    def test_one_insertion(self) -> None:
        assert levenshtein_within("sela", "selaa", 2) == 1

    def test_one_deletion(self) -> None:
        assert levenshtein_within("selaa", "sela", 2) == 1

    def test_beyond_the_limit_is_none_not_a_number(self) -> None:
        assert levenshtein_within("sela", "zzzzz", 2) is None

    def test_length_difference_alone_can_exceed_the_limit(self) -> None:
        assert levenshtein_within("a", "abcdefgh", 2) is None

    def test_empty_string(self) -> None:
        assert levenshtein_within("", "ab", 2) == 2
        assert levenshtein_within("", "", 2) == 0


class TestExactTiers:
    """Steps 1 and 2."""

    def test_exact_name_scores_highest(self) -> None:
        vocab = vocabulary(entry(SELA, "Sela", "Sela"))
        assert scores("Sela drew her sword.", vocab) == [EXACT_NAME_CONFIDENCE]

    def test_exact_name_is_case_sensitive(self) -> None:
        """Lower case is the same name, but it is weaker evidence."""
        vocab = vocabulary(entry(SELA, "Sela", "Sela"))
        assert scores("sela drew her sword.", vocab) == [CASELESS_NAME_CONFIDENCE]

    def test_exact_alias_scores_below_exact_name(self) -> None:
        vocab = vocabulary(entry(SELA, "Sela", "The Viper", is_alias=True))
        assert scores("The Viper waited.", vocab) == [EXACT_ALIAS_CONFIDENCE]

    def test_caseless_alias_scores_below_caseless_name(self) -> None:
        vocab = vocabulary(entry(SELA, "Sela", "The Viper", is_alias=True))
        assert scores("the viper waited.", vocab) == [CASELESS_ALIAS_CONFIDENCE]

    def test_tiers_are_strictly_ordered(self) -> None:
        """A higher tier must always be more confident, or the order is noise."""
        ordered = [
            EXACT_NAME_CONFIDENCE,
            EXACT_ALIAS_CONFIDENCE,
            CASELESS_NAME_CONFIDENCE,
            CASELESS_ALIAS_CONFIDENCE,
            *FUZZY_CONFIDENCE.values(),
        ]
        assert ordered == sorted(ordered, reverse=True)
        assert len(set(ordered)) == len(ordered)

    def test_name_beats_alias_on_a_tie(self) -> None:
        """Two entities share a term; the name is the primary identifier."""
        shared = "The Viper"
        name_id, alias_id = uuid4(), uuid4()
        vocab = vocabulary(
            entry(name_id, "Sela", shared),
            entry(alias_id, "Someone Else", shared, is_alias=True),
        )
        found = find_term_matches(f"{shared} arrived.", vocab)
        assert found[0].entry.entity_id == name_id
        assert found[0].confidence == EXACT_NAME_CONFIDENCE

    def test_duplicate_names_both_come_back(self) -> None:
        """Nothing in the schema forbids two entities sharing a name."""
        first, second = uuid4(), uuid4()
        vocab = vocabulary(
            entry(first, "Sela", "Sela"), entry(second, "Sela", "Sela")
        )
        found = find_term_matches("Sela waited.", vocab)
        assert {m.entry.entity_id for m in found} == {first, second}


class TestFuzzyTier:
    """Step 5, with its length guard."""

    def test_typo_at_distance_one(self) -> None:
        vocab = vocabulary(entry(LARK, "LarkFellow", "LarkFellow"))
        assert scores("You approach LarkFello.", vocab) == [FUZZY_CONFIDENCE[1]]

    def test_a_case_difference_is_not_fuzzy(self) -> None:
        """Only the case differs, so the caseless tier answers, not fuzzy."""
        vocab = vocabulary(entry(LARK, "LarkFellow", "LarkFellow"))
        assert scores("You approach Larkfellow.", vocab) == [CASELESS_NAME_CONFIDENCE]

    def test_typo_at_distance_two(self) -> None:
        vocab = vocabulary(entry(LARK, "LarkFellow", "LarkFellow"))
        assert scores("You approach LarfFelow.", vocab) == [FUZZY_CONFIDENCE[2]]

    def test_beyond_distance_two_does_not_match(self) -> None:
        vocab = vocabulary(entry(LARK, "LarkFellow", "LarkFellow"))
        assert scores("You approach Zzzzqqq.", vocab) == []

    def test_short_names_are_not_fuzzy_matched(self) -> None:
        """The floor applies to the stored term, not the text.

        Two-letter names sit within distance 2 of each other, and a three-letter
        name sits within distance 1 of most four-letter words, so without the
        floor every short word would match every short name.
        """
        vocab = vocabulary(entry(uuid4(), "Al", "Al"), entry(uuid4(), "Bo", "Bo"))
        assert scores("Al met Bo.", vocab) == [EXACT_NAME_CONFIDENCE] * 2
        assert scores("Al met Zo.", vocab) == [EXACT_NAME_CONFIDENCE]

    def test_a_short_name_does_not_absorb_a_longer_word(self) -> None:
        """The floor is why "Anne" does not fuzzy match a character "Ann"."""
        vocab = vocabulary(entry(uuid4(), "Ann", "Ann"))
        assert scores("Anne left.", vocab) == []

    def test_can_be_disabled(self) -> None:
        vocab = vocabulary(entry(LARK, "LarkFellow", "LarkFellow"))
        settings = MatchSettings(fuzzy_enabled=False)
        assert scores("You approach LarkFello.", vocab, settings) == []
        # The caseless tier is not fuzzy, so disabling fuzzy does not lose it.
        assert scores("You approach Larkfellow.", vocab, settings) == [
            CASELESS_NAME_CONFIDENCE
        ]

    def test_name_wins_over_alias_at_the_same_distance(self) -> None:
        near = "LarkFellow"
        vocab = vocabulary(
            entry(uuid4(), "Sela", near, is_alias=True),
            entry(uuid4(), "Duncan", near),
        )
        found = find_term_matches("You approach Larkfelow.", vocab)
        assert [m.entry.name for m in found] == ["Duncan"]

    def test_no_match_at_all(self) -> None:
        vocab = vocabulary(entry(LARK, "LarkFellow", "LarkFellow"))
        assert scores("Nothing here resembles anything.", vocab) == []


class TestNoSubstringMatches:
    """The reason candidates come from tokens."""

    def test_short_name_does_not_match_inside_a_longer_word(self) -> None:
        vocab = vocabulary(entry(uuid4(), "Ann", "Ann"))
        assert scores("Anne left.", vocab) == []

    def test_longer_word_does_not_match_a_shorter_name(self) -> None:
        vocab = vocabulary(entry(uuid4(), "Ann", "Ann"))
        assert scores("Ann left.", vocab) == [EXACT_NAME_CONFIDENCE]

    def test_match_inside_punctuation_still_works(self) -> None:
        vocab = vocabulary(entry(SELA, "Sela", "Sela"))
        assert scores('"Sela," she said.', vocab) == [EXACT_NAME_CONFIDENCE]

    def test_matched_text_keeps_the_original_punctuation(self) -> None:
        vocab = vocabulary(entry(SELA, "Sela", "Sela"))
        found = find_term_matches('"Sela," she said.', vocab)
        assert found[0].matched_text == "Sela"


class TestMultiWordNames:
    """Phrases are matched as runs of tokens."""

    def test_two_word_name(self) -> None:
        vocab = vocabulary(entry(HOUSE_RIVEN, "House Riven", "House Riven"))
        assert names("They reached House Riven at dusk.", vocab) == ["House Riven"]

    def test_case_insensitive_two_word_name(self) -> None:
        vocab = vocabulary(entry(HOUSE_RIVEN, "House Riven", "House Riven"))
        assert scores("They reached house riven.", vocab) == [
            CASELESS_NAME_CONFIDENCE
        ]

    def test_longest_match_wins_over_its_prefix(self) -> None:
        """Both are real entities; the longer phrase is the more specific read."""
        vocab = vocabulary(
            entry(BRAM, "Bram", "Bram"), entry(DUNCAN, "Bram Stout", "Bram Stout")
        )
        found = find_term_matches("Bram Stout arrived.", vocab)
        assert [m.entry.name for m in found] == ["Bram Stout"]

    def test_partial_phrase_falls_back_to_the_shorter_name(self) -> None:
        vocab = vocabulary(
            entry(BRAM, "Bram", "Bram"), entry(DUNCAN, "Bram Stout", "Bram Stout")
        )
        found = find_term_matches("Bram arrived alone.", vocab)
        assert [m.entry.name for m in found] == ["Bram"]

    def test_max_phrase_tokens_caps_the_phrase(self) -> None:
        vocab = vocabulary(entry(uuid4(), "Bram Stout", "Bram Stout"))
        settings = MatchSettings(max_phrase_tokens=1)
        assert names("Bram Stout arrived.", vocab, settings) == []


class TestOverlaps:
    """A match consumes its tokens, so nothing is reported twice."""

    def test_words_are_not_reported_twice(self) -> None:
        vocab = vocabulary(
            entry(BRAM, "Bram", "Bram"), entry(DUNCAN, "Stout", "Stout")
        )
        found = find_term_matches("Bram Stout arrived.", vocab)
        assert [(m.entry.name, m.matched_text) for m in found] == [
            ("Bram", "Bram"),
            ("Stout", "Stout"),
        ]

    def test_a_longer_match_swallows_the_tokens_inside_it(self) -> None:
        vocab = vocabulary(
            entry(BRAM, "Bram", "Bram"),
            entry(HOUSE_RIVEN, "Bram Stout", "Bram Stout"),
        )
        found = find_term_matches("Bram Stout arrived.", vocab)
        assert [m.entry.name for m in found] == ["Bram Stout"]

    def test_offsets_locate_each_match_in_the_source(self) -> None:
        text = "Sela met Bram."
        vocab = vocabulary(
            entry(SELA, "Sela", "Sela"), entry(BRAM, "Bram", "Bram")
        )
        found = find_term_matches(text, vocab)
        assert [text[m.start : m.stop] for m in found] == ["Sela", "Bram"]


class TestRepeatMentions:
    """One entity mentioned many times is still one match per position here;
    collapsing to one candidate per entity is the matcher's job."""

    def test_each_occurrence_is_found(self) -> None:
        vocab = vocabulary(entry(SELA, "Sela", "Sela"))
        found = find_term_matches("Sela waited. Sela rose. Sela left.", vocab)
        assert [m.matched_text for m in found] == ["Sela", "Sela", "Sela"]

    def test_strongest_tier_wins_for_a_repeated_term(self) -> None:
        vocab = vocabulary(entry(SELA, "Sela", "Sela"))
        found = find_term_matches("Sela. sela. Sela.", vocab)
        assert [m.confidence for m in found] == [
            EXACT_NAME_CONFIDENCE,
            CASELESS_NAME_CONFIDENCE,
            EXACT_NAME_CONFIDENCE,
        ]


class TestEmptyInputs:
    """Nothing to match is not an error."""

    def test_empty_text(self) -> None:
        vocab = vocabulary(entry(SELA, "Sela", "Sela"))
        assert find_term_matches("", vocab) == []

    def test_whitespace_text(self) -> None:
        vocab = vocabulary(entry(SELA, "Sela", "Sela"))
        assert find_term_matches("   \n\t ", vocab) == []

    def test_empty_vocabulary(self) -> None:
        assert find_term_matches("Sela waited.", vocabulary()) == []

    def test_text_with_no_entities(self) -> None:
        vocab = vocabulary(entry(SELA, "Sela", "Sela"))
        assert find_term_matches("Nothing to see here.", vocab) == []


class TestBlankTerms:
    """A blank name or alias must not poison the index."""

    def test_blank_term_is_dropped(self) -> None:
        assert make_entry(uuid4(), "Sela", "   ", is_alias=False) is None

    def test_punctuation_only_term_is_dropped(self) -> None:
        assert make_entry(uuid4(), "Sela", "!!!", is_alias=True) is None

    def test_blank_term_does_not_break_matching(self) -> None:
        vocab = build_vocabulary(
            [
                e
                for e in (
                    make_entry(SELA, "Sela", "Sela", is_alias=False),
                    make_entry(BRAM, "X", " ", is_alias=False),
                )
                if e
            ]
        )
        assert names("Sela waited.", vocab) == ["Sela"]


class TestSettings:
    """Configuration is validated rather than silently clamped."""

    def test_rejects_a_distance_with_no_defined_tier(self) -> None:
        with pytest.raises(ValueError, match="max_fuzzy_distance"):
            MatchSettings(max_fuzzy_distance=3)

    def test_rejects_a_zero_length_floor(self) -> None:
        with pytest.raises(ValueError, match="min_fuzzy_length"):
            MatchSettings(min_fuzzy_length=0)

    def test_defaults_match_the_phase_plan(self) -> None:
        settings = MatchSettings()
        assert settings.fuzzy_enabled is True
        assert settings.max_fuzzy_distance == 2
        assert settings.max_phrase_tokens is None


class TestDeterminism:
    """The same data must give the same answer in the same order."""

    def test_vocabulary_order_does_not_change_the_pick(self) -> None:
        first, second = uuid4(), uuid4()
        terms = [entry(first, "Sela", "Sela"), entry(second, "Sela", "Sela")]
        forward = find_term_matches("Sela waited.", vocabulary(*terms))
        backward = find_term_matches("Sela waited.", vocabulary(*reversed(terms)))
        assert [m.entry.entity_id for m in forward] == [
            m.entry.entity_id for m in backward
        ]

    def test_repeated_runs_agree(self) -> None:
        vocab = vocabulary(
            entry(SELA, "Sela", "Sela"),
            entry(BRAM, "Bram", "Bram"),
            entry(LARK, "LarkFellow", "LarkFellow"),
        )
        text = "Sela met Bram near Larkfellow. Bram left."
        first = find_term_matches(text, vocab)
        second = find_term_matches(text, vocab)
        assert first == second
