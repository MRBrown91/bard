"""Test that no function leaves two rows pending in the same flush.

ADR-023 records that SQLAlchemy orders a flush by ``relationship()``
declarations, not by foreign key columns, and that this codebase expresses
ownership as foreign key columns without ORM relationships. An ``entities``
row and its ``campaigns`` parent therefore have no dependency edge, and when
both are pending in one flush the child can be inserted first:

    insert or update on table "entities" violates foreign key constraint
    "entities_campaign_id_fkey"

This is documented upstream behaviour rather than a defect, and the models are
deliberately shaped this way, so the rule cannot be enforced by the framework
or fixed by the metadata. The invariant is one row per flush, which is why
``BaseRepository.create``, ``SpecializedRepository.create``, and
``resolve_current_user`` each add and then flush immediately.

The failure is an ``IntegrityError`` against live data with no other symptom,
so this walks the application package and asserts the property structurally:
a new write that batches a parent and a child has to be decided deliberately
rather than discovered in production.
"""

import ast
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

APP_DIR = Path(__file__).resolve().parents[2] / "app"


@dataclass(frozen=True)
class Write:
    """A pending write found in the source."""

    where: str
    line: int

    def __str__(self) -> str:
        return f"{self.where}:{self.line}"


def _dotted(node: ast.expr) -> str:
    """Render an attribute chain such as ``user_repo.session`` as a string."""
    if isinstance(node, ast.Attribute):
        return f"{_dotted(node.value)}.{node.attr}"
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Call):
        return _dotted(node.func)
    return ""


def _is_session_call(node: ast.Call, attribute: str) -> bool:
    """Report whether a call is ``<something>.session.<attribute>(...)``.

    Matching on ``session`` in the receiver is what keeps ``set.add()`` from
    being counted as a database write, and it accepts both a bare
    ``session.add()`` and the ``user_repo.session.add()`` form.
    """
    if not isinstance(node.func, ast.Attribute) or node.func.attr != attribute:
        return False
    return "session" in _dotted(node.func.value).lower()


def _writes(node: ast.AST, where: str) -> tuple[list[Write], list[Write]]:
    """Return the (adds, flushes) in a function body, in source order."""
    adds = [
        Write(where, child.lineno)
        for child in ast.walk(node)
        if isinstance(child, ast.Call) and _is_session_call(child, "add")
    ]
    flushes = [
        Write(where, child.lineno)
        for child in ast.walk(node)
        if isinstance(child, ast.Call) and _is_session_call(child, "flush")
    ]
    return sorted(adds, key=lambda w: w.line), sorted(flushes, key=lambda w: w.line)


def _offenders(
    adds: list[Write], flushes: list[Write]
) -> list[str]:
    """Return the adds that leave more than one row pending at once.

    Walks adds and flushes in source order. A flush retires every row pending
    before it, so a second add after that flush is fine and a second add before
    it is not. Order is taken from line numbers, which is a heuristic: a flush
    inside a branch counts for the whole function. That is acceptable for a
    review-time guard, where a false positive costs one extra flush, but it is
    why the rule is the stricter one row per flush rather than a real proof.
    """
    events = sorted(
        [(add.line, True) for add in adds] + [(flush.line, False) for flush in flushes]
    )
    pending = 0
    offenders: list[str] = []
    for line, is_add in events:
        if not is_add:
            pending = 0
            continue
        pending += 1
        if pending > 1:
            offenders.append(str(Write(adds[0].where, line)))
    return offenders


def _functions() -> Iterator[tuple[str, ast.FunctionDef | ast.AsyncFunctionDef]]:
    """Yield (qualified name, node) for every function in the application."""
    for path in sorted(APP_DIR.rglob("*.py")):
        tree = ast.parse(path.read_text(), filename=str(path))
        relative = path.relative_to(APP_DIR.parent)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                yield f"{relative}::{node.name}", node


def _all_writes() -> dict[str, tuple[list[Write], list[Write]]]:
    """Collect the write calls in every function that performs one."""
    found: dict[str, tuple[list[Write], list[Write]]] = {}
    for name, node in _functions():
        adds, flushes = _writes(node, name)
        if adds:
            found[name] = (adds, flushes)
    return found


WRITES = _all_writes()


class TestOneRowPerFlush:
    """No function may leave a parent and its dependent pending together."""

    def test_the_walk_found_the_known_writes(self) -> None:
        """Guard against the check silently matching nothing.

        If this fails, a write was moved or renamed and the rules below are no
        longer describing the code that exists.
        """
        assert len(WRITES) >= 2, f"expected the known write paths, found {list(WRITES)}"
        assert any("base" in name and "create" in name for name in WRITES), (
            "BaseRepository.create should be among the writes under test"
        )
        assert any("resolve_current_user" in name for name in WRITES), (
            "resolve_current_user should be among the writes under test"
        )

    def test_every_write_flushes(self) -> None:
        """A write that never flushes is a write that batches silently."""
        never_flushed = {
            name: [str(add) for add in adds]
            for name, (adds, flushes) in WRITES.items()
            if not flushes
        }
        assert not never_flushed, f"writes with no flush: {never_flushed}"

    def test_no_function_queues_two_writes_before_flushing(self) -> None:
        """The invariant itself: one pending row per flush."""
        offenders = {
            name: found
            for name, (adds, flushes) in WRITES.items()
            if (found := _offenders(adds, flushes))
        }
        assert not offenders, (
            "these functions queue more than one row before flushing; flush the "
            f"parent first: {offenders}"
        )

    def test_the_add_precedes_the_flush(self) -> None:
        """Flushing before adding would not order the two statements."""
        for name, (adds, flushes) in WRITES.items():
            assert adds[0].line < flushes[0].line, (
                f"{name} flushes before it adds"
            )


class TestDetection:
    """The check has to fail on the shape it exists to catch."""

    def _violations(self, source: str) -> dict[str, list[str]]:
        """Return offenders for a snippet, using the same logic as the walk."""
        tree = ast.parse(source)
        found: dict[str, list[str]] = {}
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            adds, flushes = _writes(node, "snippet")
            offenders = _offenders(adds, flushes) if adds else []
            if offenders:
                found[node.name] = offenders
        return found

    def test_catches_a_batched_parent_and_child(self) -> None:
        source = """
async def create_entity(self, campaign):
    self.session.add(Entity(campaign_id=campaign.id))
    self.session.add(Actor(entity_id=entity_id))
    await self.session.flush()
"""
        assert self._violations(source), "a parent and child in one flush must fail"

    def test_catches_three_rows_where_only_the_first_is_flushed(self) -> None:
        source = """
async def bulk(self):
    await self.session.add(A())
    await self.session.flush()
    await self.session.add(B())
    await self.session.add(C())
    await self.session.flush()
"""
        assert self._violations(source), "a trailing pair with no flush must be caught"

    def test_accepts_one_row_per_flush(self) -> None:
        source = """
async def create(self, **kwargs):
    obj = self.model(**kwargs)
    self.session.add(obj)
    await self.session.flush()
    return obj
"""
        assert not self._violations(source), "one row per flush must pass"

    def test_ignores_a_set_add(self) -> None:
        """``set.add`` is not a database write and must not be counted."""
        source = """
def collect(self, values):
    seen = set()
    for value in values:
        seen.add(value)
    return seen
"""
        assert not WRITES or not self._violations(source)

    @pytest.mark.parametrize("method", ["add", "flush"])
    def test_requires_the_session_receiver(self, method: str) -> None:
        """A bare ``add()`` on something that is not a session is ignored."""
        node = ast.parse(f"x.{method}(1)")
        call = node.body[0].value  # type: ignore[attr-defined]
        assert not _is_session_call(call, method)
