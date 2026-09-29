"""Shared test fixtures.

The entity vocabulary cache is deliberately process-global, so it is also
process-global during a test run. Without this, one test's campaign would be
served to the next test that happens to use the same id, and the failure would
look like a matching bug rather than leaked state.
"""

import pytest

from app.application.entities.matching_vocabulary import MATCHING_VOCABULARIES


@pytest.fixture(autouse=True)
def clear_matching_vocabulary_cache() -> None:
    """Start every test with an empty vocabulary cache."""
    MATCHING_VOCABULARIES.clear()
    yield
    MATCHING_VOCABULARIES.clear()
