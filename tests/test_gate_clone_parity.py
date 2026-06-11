"""Clone-parity registry — declared gate-helper clones cannot silently diverge.

Audit init 9. etc's gate scripts are deliberately single-file CLIs (the
distribution model forbids a shared package — see tasks.py:82-83 and the
audit's Do-NOT list), so some helpers exist as intentional CLONES across
scripts. Two real incidents prove what silent clone drift costs:

  - The duplicated legacy-only ``parse_feature_id`` regex silently killed
    BOTH flagship gates (collision + spec-coupling) for every date-form
    feature — months of dead enforcement.
  - ``files_in_scope`` reading drifted semantically between review_gate
    (stringifies every entry) and cross_feature_collision_check (drops
    non-string entries).

This registry is the countermeasure: clone families are DECLARED. Families
marked identical are compared structurally (AST, docstrings stripped — each
copy may document its own gate's context; logic and regexes may not differ).
Families with a known, accepted difference carry an ``allowed_divergence``
note — documented divergence beats silent divergence, and removing an entry
from the registry is a reviewable act.

Comparison method: ``ast.dump`` of the located node with function docstrings
removed. Chosen over raw-text comparison so comments/whitespace don't fire
false positives, while ANY logic or regex change does.
"""

from __future__ import annotations

import ast
import copy
from dataclasses import dataclass, field
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class CloneFamily:
    """One set of symbols that must stay structurally identical."""

    name: str
    members: tuple[tuple[str, str], ...]  # (script relpath, symbol name)
    why: str
    allowed_divergence: str | None = field(default=None)


REGISTRY: tuple[CloneFamily, ...] = (
    CloneFamily(
        name="parse_feature_id",
        members=(
            ("scripts/cross_feature_collision_check.py", "parse_feature_id"),
            ("scripts/spec_coupling_check.py", "parse_feature_id"),
        ),
        why=(
            "Dual-grammar feature-ID parsing. The legacy-only copy of this "
            "function silently killed both gates for all date-form features."
        ),
    ),
    CloneFamily(
        name="legacy-id-pattern",
        members=(
            ("scripts/cross_feature_collision_check.py", "_LEGACY_ID_PATTERN"),
            ("scripts/spec_coupling_check.py", "_LEGACY_ID_PATTERN"),
        ),
        why="The regex IS where the original gate-kill lived; pin it, not just the function.",
    ),
    CloneFamily(
        name="dated-id-pattern",
        members=(
            ("scripts/cross_feature_collision_check.py", "_DATED_ID_PATTERN"),
            ("scripts/spec_coupling_check.py", "_DATED_ID_PATTERN"),
        ),
        why="Date-form grammar must match scripts/feature_id.py's allocator output in both gates.",
    ),
    CloneFamily(
        name="files_in_scope-readers",
        members=(
            ("scripts/review_gate.py", "_task_files"),
            ("scripts/cross_feature_collision_check.py", "load_files_in_scope"),
        ),
        why=(
            "Both read a task YAML's files_in_scope list; semantic drift here "
            "means the review gate and the collision gate disagree about what "
            "files a task touches."
        ),
        allowed_divergence=(
            "DECLARED (audit init 9): review_gate._task_files stringifies "
            "every entry (str(path) for path in scope); "
            "cross_feature_collision_check.load_files_in_scope DROPS "
            "non-string entries (isinstance filter). A task YAML with a "
            "non-string files_in_scope entry is therefore seen by review "
            "but invisible to collision detection. Unifying the behavior is "
            "an operator decision; until then this entry documents the gap "
            "so it cannot be re-discovered the hard way."
        ),
    ),
)


def _locate(path: Path, symbol: str) -> ast.AST:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == symbol:
            return node
        if isinstance(node, ast.Assign):
            targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if symbol in targets:
                return node
    raise AssertionError(
        f"clone-parity registry names {symbol} in {path}, but the symbol is "
        f"absent — update the registry alongside the refactor that moved it"
    )


def _structural_dump(node: ast.AST) -> str:
    """ast.dump with function docstrings stripped (each clone may document
    its own gate's context; logic and regexes may not differ)."""
    node = copy.deepcopy(node)
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.body:
        first = node.body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            node.body = node.body[1:] or [ast.Pass()]
    return ast.dump(node, include_attributes=False)


@pytest.mark.parametrize(
    "family", [f for f in REGISTRY if f.allowed_divergence is None], ids=lambda f: f.name
)
def test_identical_clone_families_match_structurally(family: CloneFamily) -> None:
    dumps: dict[str, str] = {}
    for relpath, symbol in family.members:
        node = _locate(REPO_ROOT / relpath, symbol)
        dumps[f"{relpath}::{symbol}"] = _structural_dump(node)

    values = set(dumps.values())
    assert len(values) == 1, (
        f"clone family '{family.name}' has DIVERGED across:\n  "
        + "\n  ".join(dumps)
        + f"\nWhy this family is pinned: {family.why}\n"
        "Either re-unify the copies, or — if the divergence is a conscious "
        "decision — move the family to allowed_divergence with a note."
    )


@pytest.mark.parametrize(
    "family", [f for f in REGISTRY if f.allowed_divergence is not None], ids=lambda f: f.name
)
def test_divergent_families_still_locate_their_members(family: CloneFamily) -> None:
    """Declared-divergent members must still EXIST — a deleted or renamed
    member silently un-documents the divergence."""
    for relpath, symbol in family.members:
        _locate(REPO_ROOT / relpath, symbol)  # raises with guidance if absent
