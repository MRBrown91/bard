"""Test that no repository read method can skip the soft-delete filter.

ADR-022 requires that every read excludes soft-deleted rows. Applying the
filter in ``BaseRepository`` does not achieve that on its own: a subclass that
builds its own ``select()`` never passes through ``get``/``list``, so the
filter has to be applied by hand at every hand-written query.

That is easy to forget, and it was forgotten in 36 places, including
``UserRepository.get_by_auth`` — the authentication path, where a deleted row
meant a deprovisioned account could still sign in. This test walks the
repository package and asserts the property structurally, so a new method
cannot be added without deciding whether it filters.
"""

import ast
import inspect
from pathlib import Path

import pytest

from app.repositories.base import BaseRepository

REPOSITORY_DIR = Path(__file__).resolve().parents[2] / "app" / "repositories"

# Methods that build a query by calling another method which already filters,
# so the text of this method legitimately contains no deleted_at predicate.
DELEGATING_HELPERS = (
    "filtered_stmt",
    "_filtered",
    "_live_pairs_stmt",
    "list_filtered_with",
)

# Base methods whose whole job is to read. These must filter by construction.
BASE_READS = ("get", "list", "count", "exists")


def _read_methods() -> list[tuple[str, str]]:
    """Return (qualified name, source) for every public repo method that queries.

    A method counts if it calls ``select()`` itself. Methods reaching storage
    through ``create``/``update``/``soft_delete`` are writes, and ``create`` in
    particular must not filter, or nothing could ever be inserted.
    """
    found: list[tuple[str, str]] = []
    for path in sorted(REPOSITORY_DIR.glob("*_repo.py")):
        source = path.read_text()
        for node in ast.parse(source).body:
            if not isinstance(node, ast.ClassDef):
                continue
            for fn in node.body:
                if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                if fn.name.startswith("_") or fn.name == "model":
                    continue
                body = ast.get_source_segment(source, fn) or ""
                if "select(" in body:
                    found.append((f"{path.name}:{node.name}.{fn.name}", body))
    return found


READ_METHODS = _read_methods()
READ_IDS = [name for name, _ in READ_METHODS]


def test_the_walk_finds_the_methods_it_is_meant_to_check() -> None:
    """Guard against the walk silently matching nothing."""
    assert len(READ_METHODS) > 30, len(READ_METHODS)


def test_every_repository_module_is_actually_checked() -> None:
    """Guard against a module that contributes nothing to the walk.

    The walk only inspects public methods that build a select, in a class
    defined in the file. A module can satisfy that by moving every query into a
    shared base class in another module, or into a private helper, and then no
    method of it is checked at all while the total still looks healthy. That
    happened to ``audience_repo.py`` when its reads were consolidated behind a
    private ``_filtered`` on a shared base, which left four checked methods
    becoming none.

    Asserting per module, rather than only in total, is what makes the
    difference visible.
    """
    modules = {name.split(":")[0] for name in READ_IDS}
    expected = {path.name for path in REPOSITORY_DIR.glob("*_repo.py")}
    missing = expected - modules
    assert not missing, f"no checked read method in: {sorted(missing)}"


@pytest.mark.parametrize(("name", "body"), READ_METHODS, ids=READ_IDS)
def test_read_method_excludes_soft_deleted_rows(name: str, body: str) -> None:
    """Every hand-written select filters deleted_at, directly or by delegation."""
    if any(helper in body for helper in DELEGATING_HELPERS):
        return
    assert "_active_scope" in body or "deleted_at" in body, (
        f"{name} builds a select without a deleted_at predicate; wrap it in "
        "self._active_scope(...) or delegate to a helper that does (ADR-022)"
    )


@pytest.mark.parametrize("method_name", BASE_READS)
def test_base_reads_filter_by_construction(method_name: str) -> None:
    """The inherited reads must apply the filter rather than rely on callers."""
    source = inspect.getsource(getattr(BaseRepository, method_name))
    assert "_active_scope" in source, f"BaseRepository.{method_name} does not filter"


def test_active_scope_runs_before_paging_not_after() -> None:
    """Filtering after limit/offset is how a page comes back short.

    The total would still count every row, so a client paging through the
    results would see gaps it cannot explain — the P1B.2 list/count bug.
    """
    source = inspect.getsource(BaseRepository._active_scope)
    assert "limit" not in source and "offset" not in source
