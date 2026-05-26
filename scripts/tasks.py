#!/usr/bin/env python3
"""tasks.py — Native task tracker with hierarchical decomposition.

Operates on YAML task files in .etc_sdlc/features/*/tasks/ and .etc_sdlc/tasks/.
Supports recursive task decomposition for arbitrarily large systems.

Usage:
    python3 tasks.py list [--status STATUS] [--tree]
    python3 tasks.py next
    python3 tasks.py status
    python3 tasks.py board
    python3 tasks.py set-status [--feature NAME] TASK_ID STATUS
    python3 tasks.py deps TASK_ID
    python3 tasks.py score [TASK_ID]
    python3 tasks.py tree
    python3 tasks.py waves [--feature NAME]
    python3 tasks.py phases [--feature NAME]
    python3 tasks.py ready-to-decompose
    python3 tasks.py create --task-id ID --title T --agent A --file F --ac C [...]
    python3 tasks.py bulk-create [--feature NAME]
        [--json JSON | --json-file PATH] [--allow-existing]
    python3 tasks.py validate FEATURE_ID --measured VALUE --evidence PATH_OR_URL
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import sys
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import yaml

# ── Shared constants ────────────────────────────────────────────────────

VALID_STATUSES = {  # cq-exempt: CQ-001
    "pending",
    "in_progress",
    "completed",
    "escalated",
    "blocked",
    "decomposed",
}

REQUIRED_FIELDS = (
    "task_id",
    "title",
    "assigned_agent",
    "files_in_scope",
    "acceptance_criteria",
)

# ── Complexity scoring thresholds (from DSL changeset_budget) ────────────
COMPLEXITY_THRESHOLDS = {  # cq-exempt: CQ-001
    "target_loc": 300,
    "warn_loc": 500,
    "max_loc": 1000,
}

# Complexity score formula weights
CRITERIA_WEIGHT = 1.5   # Each acceptance criterion adds ~1.5 points
FILES_WEIGHT = 1.0      # Each file in scope adds ~1.0 points
DECOMPOSE_THRESHOLD = 7  # Tasks scoring > 7 should be decomposed


# F009-lifecycle-gap fix: F009 lifecycle-aware feature directory resolution. The allocator
# places new features under `.etc_sdlc/features/active/F<NNN>-<slug>/`;
# legacy features remain at `.etc_sdlc/features/F<NNN>-<slug>/`;
# shipped features move to `.etc_sdlc/features/shipped/F<NNN>-<slug>/`.
# These helpers are inlined (rather than imported from feature_paths.py)
# so tasks.py remains a single-file CLI that runs without sys.path setup.

_FEATURE_LIFECYCLE_DIRS = ("active", "shipped", "rejections")


def _find_feature_dir_lifecycle(root: Path, name: str) -> Path | None:
    """Find `name` in active/, flat, or shipped/. Returns None if absent."""
    features_dir = root / ".etc_sdlc" / "features"
    for candidate in (
        features_dir / "active" / name,
        features_dir / name,
        features_dir / "shipped" / name,
    ):
        if candidate.is_dir():
            return candidate
    return None


def _iter_all_feature_dirs(root: Path) -> Iterator[Path]:
    """Yield every feature directory across active/, flat, and shipped/."""
    features_dir = root / ".etc_sdlc" / "features"
    if not features_dir.is_dir():
        return
    # active/ subdirectory
    active = features_dir / "active"
    if active.is_dir():
        for child in active.iterdir():
            if child.is_dir():
                yield child
    # Flat path (excluding the lifecycle directory names themselves)
    for child in features_dir.iterdir():
        if not child.is_dir():
            continue
        if child.name in _FEATURE_LIFECYCLE_DIRS:
            continue
        yield child
    # shipped/ subdirectory
    shipped = features_dir / "shipped"
    if shipped.is_dir():
        for child in shipped.iterdir():
            if child.is_dir():
                yield child


def find_task_files(root: Path, feature: str | None = None) -> list[Path]:
    """Find all task YAML files in feature dirs and global task dir.

    When ``feature`` is given, only tasks under
    ``.etc_sdlc/features/<feature>/tasks/`` are returned. The global
    ``.etc_sdlc/tasks/`` dir is skipped in that case because it is not
    scoped to any feature.
    """
    files: list[Path] = []

    if feature is not None:
        # F009-lifecycle-gap fix: honor F009 lifecycle. Search active/ → flat → shipped/.
        feature_dir = _find_feature_dir_lifecycle(root, feature)
        if feature_dir is not None:
            scoped = feature_dir / "tasks"
            if scoped.is_dir():
                files.extend(sorted(scoped.glob("*.yaml")))
        return files

    # No feature filter — include every feature plus the legacy global dir.
    # F009-lifecycle-gap fix: iterate ALL feature dirs across active/ + flat + shipped/.
    for feature_dir in sorted(_iter_all_feature_dirs(root)):
        tasks_dir = feature_dir / "tasks"
        if tasks_dir.is_dir():
            files.extend(sorted(tasks_dir.glob("*.yaml")))

    global_tasks = root / ".etc_sdlc" / "tasks"
    if global_tasks.is_dir():
        files.extend(sorted(global_tasks.glob("*.yaml")))

    return files


def load_task(path: Path) -> dict:
    """Load a task YAML file and add the file path."""
    with open(path) as f:
        task = yaml.safe_load(f) or {}
    task["_path"] = path
    return task


def load_all_tasks(root: Path, feature: str | None = None) -> list[dict]:
    """Load all task files, optionally scoped to a single feature."""
    return [load_task(p) for p in find_task_files(root, feature=feature)]


def score_complexity(task: dict) -> int:
    """Calculate complexity score (1-10) from task attributes.

    Formula:
    - Base score of 1
    - +1.5 per acceptance criterion (above 1)
    - +1.0 per file in scope (above 1)
    - Capped at 10

    Tasks scoring > DECOMPOSE_THRESHOLD should be decomposed into subtasks.
    """
    criteria_count = len(task.get("acceptance_criteria") or [])
    files_count = len(task.get("files_in_scope") or [])

    score = 1.0
    score += max(0, criteria_count - 1) * CRITERIA_WEIGHT
    score += max(0, files_count - 1) * FILES_WEIGHT

    return min(10, max(1, round(score)))


def get_children(task_id: str, all_tasks: list[dict]) -> list[dict]:
    """Get direct children of a task (subtasks)."""
    return [t for t in all_tasks if t.get("parent_task") == task_id]


def is_leaf(task_id: str, all_tasks: list[dict]) -> bool:
    """A task is a leaf if it has no children."""
    return len(get_children(task_id, all_tasks)) == 0


def get_leaf_tasks(all_tasks: list[dict]) -> list[dict]:
    """Get all leaf tasks (no children — these are the implementable units)."""
    parent_ids = {t.get("parent_task") for t in all_tasks if t.get("parent_task")}
    return [t for t in all_tasks if t.get("task_id") not in parent_ids]


# ── F008: implicit-dependency phrasings ─────────────────────────────────
#
# Three case-insensitive regex patterns scan ``context`` and
# ``acceptance_criteria`` for phrasings that imply a hard dependency edge
# the planner would otherwise miss. See spec/wave-planner-implicit-deps.md
# (BR-002) for the authoritative list.

_IMPLICIT_DEP_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"stub\s+until\s+task\s+([0-9]+)", re.IGNORECASE),
    re.compile(r"placeholder\s+for\s+task\s+([0-9]+)", re.IGNORECASE),
    re.compile(r"until\s+task\s+([0-9]+)\s+lands", re.IGNORECASE),
)

# Control-character strip used by both the stderr fail-fast message and
# the cmd_waves note printer. Mirrors F003 (operator path sanitization)
# and F007 (matched-line sanitization). See spec Security Considerations
# items 3 and 4.
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x1f\x7f]")
_PHRASE_MAX_LEN = 256


def _sanitize_phrase(phrase: str) -> str:
    """Strip control characters and cap length for terminal-safe printing."""
    cleaned = _CONTROL_CHARS_RE.sub("", phrase)
    if len(cleaned) > _PHRASE_MAX_LEN:
        cleaned = cleaned[:_PHRASE_MAX_LEN]
    return cleaned


def _scannable_fields(task: dict) -> list[tuple[str, str]]:
    """Return ``(source_field, text)`` tuples for the two scanned fields."""
    fields: list[tuple[str, str]] = [("context", task.get("context") or "")]
    for idx, ac in enumerate(task.get("acceptance_criteria") or []):
        if isinstance(ac, str):
            fields.append((f"acceptance_criteria[{idx}]", ac))
    return fields


def _scan_implicit_deps(
    tasks: list[dict],
) -> tuple[list[dict], list[tuple[str, str, str, str]]]:
    """Scan ``context`` and ``acceptance_criteria`` for implicit deps.

    For each task and each pattern in ``_IMPLICIT_DEP_PATTERNS``, scan the
    ``context`` string and every entry in ``acceptance_criteria``. When a
    pattern matches, append the captured task ID to the source task's
    ``dependencies`` list IN-MEMORY (no disk writes). The captured ID must
    correspond to an existing ``task_id`` in ``tasks`` — otherwise call
    ``sys.exit(1)`` with a stderr message naming the source task, the
    missing reference, and the matched phrase verbatim (sanitized).

    Returns a 2-tuple ``(augmented_tasks, promoted_edges)`` where
    ``promoted_edges`` is a de-duplicated list of
    ``(source_task_id, target_task_id, matched_phrase, source_field)``
    tuples for downstream printing by ``cmd_waves``.
    """
    known_task_ids = {t.get("task_id") for t in tasks if t.get("task_id")}
    promoted_edges: list[tuple[str, str, str, str]] = []
    seen_edges: set[tuple[str, str, str, str]] = set()

    for task in tasks:
        source_id = task.get("task_id") or ""
        for source_field, text in _scannable_fields(task):
            _scan_field(
                task,
                source_id,
                source_field,
                text,
                known_task_ids,
                promoted_edges,
                seen_edges,
            )

    return tasks, promoted_edges


def _scan_field(
    task: dict,
    source_id: str,
    source_field: str,
    text: str,
    known_task_ids: set,
    promoted_edges: list[tuple[str, str, str, str]],
    seen_edges: set[tuple[str, str, str, str]],
) -> None:
    """Run every implicit-dep pattern against one field's text.

    Mutates ``task["dependencies"]`` in-place and appends to
    ``promoted_edges`` / ``seen_edges`` for caller-visible state.
    Calls ``sys.exit(1)`` on the first match referencing an unknown
    task ID.
    """
    for pattern in _IMPLICIT_DEP_PATTERNS:
        for match in pattern.finditer(text):
            captured_id = match.group(1)
            matched_phrase = _sanitize_phrase(match.group(0))

            if captured_id not in known_task_ids:
                sys.stderr.write(
                    f"error: task {source_id} references task "
                    f"{captured_id} via phrase \"{matched_phrase}\" "
                    f"but no such task exists in this feature.\n"
                )
                sys.exit(1)

            deps = task.get("dependencies")
            if deps is None:
                deps = []
                task["dependencies"] = deps
            if captured_id not in deps:
                deps.append(captured_id)

            edge = (source_id, captured_id, matched_phrase, source_field)
            if edge not in seen_edges:
                seen_edges.add(edge)
                promoted_edges.append(edge)


def compute_waves(
    tasks: list[dict],
) -> tuple[dict[int, list[dict]], list[tuple[str, str, str, str]]]:
    """Group pending leaf tasks into execution waves by dependency.

    Wave 0: tasks with no unmet dependencies
    Wave N: tasks whose dependencies are all in waves < N or already completed

    Already-completed and decomposed tasks never appear in any wave, but
    their task_ids are pre-populated into ``satisfied_ids`` so pending tasks
    that depend on them are scheduled in Wave 0 instead of waiting forever.

    Before wave-packing, ``_scan_implicit_deps`` walks each task's
    ``context`` and ``acceptance_criteria`` for stub/placeholder phrasings
    (F008) and promotes any captured task IDs into the source task's
    ``dependencies`` in-memory. The promoted-edge tuples are returned
    alongside the wave map so the caller can surface them to operators.
    """
    tasks, promoted_edges = _scan_implicit_deps(tasks)
    leaf_tasks = get_leaf_tasks(tasks)

    # Pre-populate: anything already completed or decomposed counts as satisfied
    # for dependency purposes, and is excluded from the remaining work.
    satisfied_ids: set[str] = {
        t.get("task_id", "")
        for t in tasks
        if t.get("status") in ("completed", "decomposed")
    }
    remaining = [
        t for t in leaf_tasks
        if t.get("status") not in ("completed", "decomposed")
    ]

    waves: dict[int, list[dict]] = {}
    wave_num = 0

    while remaining:
        current_wave = []
        still_remaining = []

        for t in remaining:
            deps = t.get("dependencies") or []
            # Also consider parent's deps
            parent_id = t.get("parent_task")
            if parent_id:
                parent = next((p for p in tasks if p.get("task_id") == parent_id), None)
                if parent:
                    deps = list(set(deps + (parent.get("dependencies") or [])))

            if all(d in satisfied_ids for d in deps):
                current_wave.append(t)
            else:
                still_remaining.append(t)

        if not current_wave:
            # Circular dependency or unresolvable — dump remaining into last wave
            waves[wave_num] = still_remaining
            break

        waves[wave_num] = current_wave
        satisfied_ids.update(t.get("task_id", "") for t in current_wave)
        remaining = still_remaining
        wave_num += 1

    return waves, promoted_edges


# ── F-2026-05-26: phase/wave decoupling ──────────────────────────────────
#
# A *phase* is a top-level WBS group — the depth-1 ancestor of a leaf task.
# A *wave* is a dependency-ordered group of leaf tasks computed WITHIN a
# phase (reusing compute_waves' algorithm scoped to that phase). When a
# feature is fully flat (no decomposition), the whole build is one phase
# (``phase-0``) so today's behavior is preserved exactly.

# Statuses that count as already-satisfied for dependency purposes.
_SATISFIED_STATUSES: tuple[str, ...] = ("completed", "decomposed")


@dataclass(frozen=True)
class PhaseWave:
    """A dependency-ordered group of leaf tasks WITHIN a phase.

    ``wave_num`` is 0-based within its phase (not globally). ``task_ids``
    lists the leaf-task ids assigned to this wave, in the order
    ``compute_waves`` packed them.
    """

    wave_num: int
    task_ids: tuple[str, ...]


@dataclass(frozen=True)
class Phase:
    """A top-level WBS group carrying its ordered intra-phase waves.

    ``phase_id`` is the 0-based dependency-ordered position. ``name`` is the
    top-level task title (or its id) for a decomposed group, or ``phase-0``
    for the flat-fallback single phase. ``top_level_task_id`` is the depth-1
    ancestor id, or ``None`` for the flat fallback.
    """

    phase_id: int
    name: str
    top_level_task_id: str | None
    waves: tuple[PhaseWave, ...] = ()


def _pending_leaf_tasks(tasks: list[dict]) -> list[dict]:
    """Return pending (not completed/decomposed) leaf tasks.

    Mirrors ``compute_waves``: leaf tasks whose status is not in
    ``_SATISFIED_STATUSES``.
    """
    leaf_tasks = get_leaf_tasks(tasks)
    return [t for t in leaf_tasks if t.get("status") not in _SATISFIED_STATUSES]


def _top_level_ancestor(task_id: str, parent_of: dict[str, str | None]) -> str:
    """Walk ``parent_task`` links up to the depth-1 ancestor (the root)."""
    current = task_id
    while True:
        parent = parent_of.get(current)
        if not parent:
            return current
        current = parent


def _waves_to_phase_waves(waves: dict[int, list[dict]]) -> tuple[PhaseWave, ...]:
    """Convert a ``compute_waves`` wave-map into ordered ``PhaseWave`` tuples,
    re-indexing wave numbers to a contiguous 0-based sequence."""
    phase_waves: list[PhaseWave] = []
    for new_num, original_num in enumerate(sorted(waves)):
        task_ids = tuple(
            t.get("task_id", "") for t in waves[original_num]
        )
        phase_waves.append(PhaseWave(wave_num=new_num, task_ids=task_ids))
    return tuple(phase_waves)


def _is_flat(tasks: list[dict]) -> bool:
    """True when NO task declares a non-empty ``parent_task`` (no WBS)."""
    return not any(t.get("parent_task") for t in tasks)


def _group_by_phase(
    pending: list[dict], parent_of: dict[str, str | None]
) -> dict[str, list[dict]]:
    """Group pending leaf tasks by their depth-1 ancestor (phase key)."""
    groups: dict[str, list[dict]] = {}
    for task in pending:
        ancestor = _top_level_ancestor(task.get("task_id", ""), parent_of)
        groups.setdefault(ancestor, []).append(task)
    return groups


def _phase_dependency_edges(
    groups: dict[str, list[dict]], task_to_phase: dict[str, str]
) -> dict[str, set[str]]:
    """Map each phase key → set of phase keys it depends on (cross-phase)."""
    edges: dict[str, set[str]] = {key: set() for key in groups}
    for phase_key, phase_tasks in groups.items():
        for task in phase_tasks:
            for dep in task.get("dependencies") or []:
                dep_phase = task_to_phase.get(dep)
                if dep_phase is not None and dep_phase != phase_key:
                    edges[phase_key].add(dep_phase)
    return edges


def _order_phases(
    groups: dict[str, list[dict]], edges: dict[str, set[str]]
) -> list[str]:
    """Topologically order phase keys (dependencies first).

    On a cycle, mirror ``compute_waves``' circular-dep handling: dump the
    still-unresolvable phase keys (in ancestor-id order) at the end.
    """
    ordered: list[str] = []
    placed: set[str] = set()
    remaining = sorted(groups)

    while remaining:
        ready = [
            key for key in remaining if edges[key] <= placed
        ]
        if not ready:
            # Circular cross-phase dependency — append the rest in id order.
            ordered.extend(remaining)
            break
        ordered.extend(ready)
        placed.update(ready)
        remaining = [key for key in remaining if key not in placed]

    return ordered


def _phase_name(top_level_id: str, tasks_by_id: dict[str, dict]) -> str:
    """Human-readable phase name: the top-level task title, else its id."""
    top_task = tasks_by_id.get(top_level_id)
    if top_task:
        title = top_task.get("title")
        if isinstance(title, str) and title.strip():
            return title
    return top_level_id


def compute_phase_plan(tasks: list[dict]) -> list[Phase]:
    """Group pending leaf tasks into dependency-ordered phases of waves.

    Flat fallback (BR-02): if NO task declares a ``parent_task``, the whole
    build is ONE phase (``phase-0``) whose waves are exactly those
    ``compute_waves`` produces — preserving today's behavior with zero
    regression.

    Decomposed (BR-03/BR-04): each distinct depth-1 ancestor of a pending
    leaf task defines one phase. Phases are emitted in cross-phase
    dependency order; within each phase, waves are computed over that
    phase's leaf tasks using the SAME algorithm as ``compute_waves`` with
    tasks in earlier phases counted as satisfied.

    Every pending leaf task appears in exactly one (phase, wave) cell
    (BR-01/BR-10). Empty / all-done inputs yield ``[]`` (EC-1/EC-2); a
    circular cross-phase dependency does not loop forever (EC-4).
    """
    pending = _pending_leaf_tasks(tasks)
    if not pending:
        return []

    if _is_flat(tasks):
        waves, _ = compute_waves([dict(t) for t in tasks])
        return [
            Phase(
                phase_id=0,
                name="phase-0",
                top_level_task_id=None,
                waves=_waves_to_phase_waves(waves),
            )
        ]

    parent_of: dict[str, str | None] = {
        t.get("task_id", ""): t.get("parent_task") for t in tasks
    }
    tasks_by_id: dict[str, dict] = {t.get("task_id", ""): t for t in tasks}

    groups = _group_by_phase(pending, parent_of)
    task_to_phase: dict[str, str] = {
        t.get("task_id", ""): _top_level_ancestor(t.get("task_id", ""), parent_of)
        for t in pending
    }
    edges = _phase_dependency_edges(groups, task_to_phase)
    order = _order_phases(groups, edges)

    return _build_phases(order, groups, tasks, tasks_by_id)


def _build_phases(
    order: list[str],
    groups: dict[str, list[dict]],
    tasks: list[dict],
    tasks_by_id: dict[str, dict],
) -> list[Phase]:
    """Compute intra-phase waves for each phase in dependency order.

    Tasks placed in earlier phases are marked completed (in a per-phase
    copy) so ``compute_waves`` treats them as satisfied deps (BR-04).
    """
    satisfied: set[str] = {
        t.get("task_id", "")
        for t in tasks
        if t.get("status") in _SATISFIED_STATUSES
    }
    phases: list[Phase] = []

    for phase_id, phase_key in enumerate(order):
        phase_tasks = groups[phase_key]
        scoped = _scope_tasks_for_phase(phase_tasks, satisfied)
        waves, _ = compute_waves(scoped)
        phases.append(
            Phase(
                phase_id=phase_id,
                name=_phase_name(phase_key, tasks_by_id),
                top_level_task_id=phase_key,
                waves=_waves_to_phase_waves(waves),
            )
        )
        satisfied.update(t.get("task_id", "") for t in phase_tasks)

    return phases


def _scope_tasks_for_phase(
    phase_tasks: list[dict], satisfied: set[str]
) -> list[dict]:
    """Build the task list ``compute_waves`` runs over for one phase.

    Includes copies of this phase's leaf tasks plus zero-cost ``completed``
    placeholders for every already-satisfied id referenced as a dependency,
    so cross-phase deps resolve to Wave 0 inside this phase.
    """
    scoped: list[dict] = [dict(t) for t in phase_tasks]
    own_ids = {t.get("task_id", "") for t in phase_tasks}
    referenced: set[str] = set()
    for task in phase_tasks:
        for dep in task.get("dependencies") or []:
            if dep in satisfied and dep not in own_ids:
                referenced.add(dep)
    for dep_id in sorted(referenced):
        scoped.append(
            {"task_id": dep_id, "status": "completed", "dependencies": []}
        )
    return scoped


# ── Commands ─────────────────────────────────────────────────────────────


def cmd_list(root: Path, status_filter: str | None = None, tree: bool = False) -> None:
    """List all tasks with id, title, status, agent."""
    tasks = load_all_tasks(root)
    if not tasks:
        print("No tasks found.")
        return

    if status_filter:
        tasks = [t for t in tasks if t.get("status") == status_filter]

    if tree:
        _print_tree(tasks)
        return

    for t in tasks:
        tid = t.get("task_id", "???")
        title = t.get("title", "(no title)")
        status = t.get("status", "unknown")
        agent = t.get("assigned_agent", "-")
        parent = t.get("parent_task", "")
        indent = "  " if parent else ""
        complexity = t.get("complexity") or score_complexity(t)
        print(f"  {indent}[{status:12s}]  {tid:>8s}  {title}  ({agent}) c={complexity}")


def _print_tree(tasks: list[dict], parent_id: str | None = None, indent: int = 0) -> None:
    """Recursively print task tree."""
    children = [t for t in tasks if t.get("parent_task") == parent_id]
    # Also include root tasks (no parent) when parent_id is None
    if parent_id is None:
        children = [t for t in tasks if not t.get("parent_task")]

    for t in children:
        tid = t.get("task_id", "???")
        title = t.get("title", "(no title)")
        status = t.get("status", "unknown")
        complexity = t.get("complexity") or score_complexity(t)
        has_children = any(c.get("parent_task") == tid for c in tasks)
        marker = "├─" if not has_children else "├┬"

        prefix = "│ " * indent
        status_icon = {"completed": "✓", "in_progress": "▶", "escalated": "✗",
                       "decomposed": "↓", "blocked": "◼"}.get(status, "○")

        print(f"  {prefix}{marker} {status_icon} {tid} {title} [c={complexity}]")

        if has_children:
            _print_tree(tasks, tid, indent + 1)


def cmd_next(root: Path) -> None:
    """Show the next leaf task ready for work (pending + all deps completed)."""
    tasks = load_all_tasks(root)
    leaf_tasks = get_leaf_tasks(tasks)
    completed_ids = {t.get("task_id") for t in tasks if t.get("status") == "completed"}

    for t in leaf_tasks:
        if t.get("status") != "pending":
            continue
        deps = t.get("dependencies") or []
        if all(d in completed_ids for d in deps):
            tid = t.get("task_id", "???")
            title = t.get("title", "(no title)")
            agent = t.get("assigned_agent", "-")
            complexity = t.get("complexity") or score_complexity(t)
            print(f"  Next: {tid} — {title} (assign to: {agent}, complexity: {complexity})")
            ac = t.get("acceptance_criteria") or []
            if ac:
                print("  Acceptance criteria:")
                for criterion in ac:
                    print(f"    - {criterion}")
            return

    print("  No tasks ready. All completed or blocked on dependencies.")


def cmd_status(root: Path) -> None:
    """Summary counts by status."""
    tasks = load_all_tasks(root)
    counts: dict[str, int] = {}
    for t in tasks:
        s = t.get("status", "unknown")
        counts[s] = counts.get(s, 0) + 1

    leaf_count = len(get_leaf_tasks(tasks))
    total = len(tasks)
    print(f"  Tasks: {total} total ({leaf_count} leaf, {total - leaf_count} parent)")
    for s in ["pending", "in_progress", "completed", "decomposed", "escalated", "blocked"]:
        if s in counts:
            print(f"    {s}: {counts[s]}")


def cmd_board(root: Path) -> None:
    """Kanban-style view grouped by status."""
    tasks = load_all_tasks(root)
    leaf_tasks = get_leaf_tasks(tasks)
    groups: dict[str, list[dict]] = {}
    for t in leaf_tasks:
        s = t.get("status", "unknown")
        groups.setdefault(s, []).append(t)

    for status in ["pending", "in_progress", "completed", "escalated", "blocked"]:
        if status not in groups:
            continue
        print(f"\n  ── {status.upper()} ({len(groups[status])}) ──")
        for t in groups[status]:
            tid = t.get("task_id", "???")
            title = t.get("title", "(no title)")
            complexity = t.get("complexity") or score_complexity(t)
            print(f"    {tid}  {title}  [c={complexity}]")


def cmd_set_status(
    root: Path, task_id: str, new_status: str, feature: str | None = None
) -> None:
    """Update a task's status in its YAML file.

    When ``feature`` is provided, the lookup is scoped to
    ``.etc_sdlc/features/{feature}/tasks/`` only, so task_id collisions
    across features are resolved deterministically. Without the flag,
    the first match returned by ``load_all_tasks`` wins — which is the
    bug the /hotfix v1.6 build surfaced when set-status 001 landed on
    the wrong feature's task.
    """
    if new_status not in VALID_STATUSES:
        print(
            f"  Error: invalid status '{new_status}'. "
            f"Valid: {', '.join(sorted(VALID_STATUSES))}"
        )
        sys.exit(1)

    tasks = load_all_tasks(root, feature=feature)
    for t in tasks:
        if t.get("task_id") == task_id:
            path = t["_path"]
            text = path.read_text()
            updated = re.sub(
                r"^status:\s*\S+",
                f"status: {new_status}",
                text,
                count=1,
                flags=re.MULTILINE,
            )
            path.write_text(updated)
            scope = f" in feature '{feature}'" if feature else ""
            print(f"  {task_id}: status → {new_status}{scope}")
            return

    scope = f" in feature '{feature}'" if feature else ""
    print(f"  Error: task '{task_id}' not found{scope}.")
    sys.exit(1)


def cmd_deps(root: Path, task_id: str) -> None:
    """Show dependency tree for a task."""
    tasks = load_all_tasks(root)
    task_map = {t.get("task_id"): t for t in tasks}

    if task_id not in task_map:
        print(f"  Error: task '{task_id}' not found.")
        sys.exit(1)

    def show_deps(tid: str, indent: int = 0) -> None:
        t = task_map.get(tid)
        if not t:
            print(f"{'  ' * indent}  {tid} (not found)")
            return
        status = t.get("status", "unknown")
        title = t.get("title", "(no title)")
        marker = "✓" if status == "completed" else "○"
        print(f"{'  ' * indent}  {marker} {tid} — {title} [{status}]")
        for dep in t.get("dependencies") or []:
            show_deps(dep, indent + 1)

    show_deps(task_id)


def cmd_score(root: Path, task_id: str | None = None) -> None:
    """Score complexity for one or all tasks."""
    tasks = load_all_tasks(root)

    if task_id:
        tasks = [t for t in tasks if t.get("task_id") == task_id]
        if not tasks:
            print(f"  Error: task '{task_id}' not found.")
            sys.exit(1)

    print(f"  {'ID':>8s}  {'Score':>5s}  {'Criteria':>8s}  {'Files':>5s}  {'Title'}")
    print(f"  {'─'*8}  {'─'*5}  {'─'*8}  {'─'*5}  {'─'*30}")

    for t in tasks:
        tid = t.get("task_id", "???")
        title = t.get("title", "(no title)")
        criteria = len(t.get("acceptance_criteria") or [])
        files = len(t.get("files_in_scope") or [])
        score = score_complexity(t)
        flag = " ⚠ DECOMPOSE" if score > DECOMPOSE_THRESHOLD else ""
        print(f"  {tid:>8s}  {score:>5d}  {criteria:>8d}  {files:>5d}  {title}{flag}")


def cmd_tree(root: Path) -> None:
    """Print full task hierarchy as a tree."""
    tasks = load_all_tasks(root)
    if not tasks:
        print("No tasks found.")
        return
    _print_tree(tasks)


def cmd_waves(root: Path, feature: str | None = None) -> None:
    """Show execution wave grouping.

    When ``feature`` is given, scopes to that feature's tasks only. This is
    essential for multi-feature repos: without it, pending tasks from other
    features pollute the wave plan and false-positive file conflicts get
    flagged when a completed task from feature A happens to touch the same
    file as a pending task from feature B.
    """
    tasks = load_all_tasks(root, feature=feature)
    waves, promoted_edges = compute_waves(tasks)

    if not waves:
        print("No tasks found.")
        return

    # F008: surface promoted implicit-dep edges before the first wave block.
    for source_id, target_id, matched_phrase, source_field in promoted_edges:
        safe_phrase = _sanitize_phrase(matched_phrase)
        print(
            f"  note: promoted task {source_id} → task {target_id} "
            f"(matched: \"{safe_phrase}\" in {source_id}.{source_field})"
        )

    for wave_num, wave_tasks in sorted(waves.items()):
        # Check file-set overlap within wave
        all_files: list[str] = []
        overlaps: list[str] = []
        for t in wave_tasks:
            files = t.get("files_in_scope") or []
            for f in files:
                if f in all_files:
                    overlaps.append(f)
                all_files.append(f)

        overlap_warning = f" ⚠ FILE OVERLAP: {', '.join(set(overlaps))}" if overlaps else ""
        print(f"\n  ── Wave {wave_num} ({len(wave_tasks)} tasks) ──{overlap_warning}")
        for t in wave_tasks:
            tid = t.get("task_id", "???")
            title = t.get("title", "(no title)")
            agent = t.get("assigned_agent", "-")
            print(f"    {tid}  {title}  ({agent})")


def cmd_phases(root: Path, feature: str | None = None) -> None:
    """Print the ordered phase→wave plan, one block per phase.

    Mirrors ``cmd_waves`` scoping semantics: when ``feature`` is given, the
    plan is computed over that feature's tasks only. Human-readable; exits 0.
    """
    tasks = load_all_tasks(root, feature=feature)
    plan = compute_phase_plan(tasks)

    if not plan:
        print("No tasks found.")
        return

    for phase in plan:
        wave_count = len(phase.waves)
        print(
            f"\n  ══ Phase {phase.phase_id}: {phase.name} "
            f"({wave_count} wave{'s' if wave_count != 1 else ''}) ══"
        )
        for wave in phase.waves:
            task_count = len(wave.task_ids)
            print(
                f"    ── Wave {wave.wave_num} "
                f"({task_count} task{'s' if task_count != 1 else ''}) ──"
            )
            for task_id in wave.task_ids:
                print(f"      {task_id}")


def cmd_ready_to_decompose(root: Path) -> None:
    """Show tasks that score above the decomposition threshold."""
    tasks = load_all_tasks(root)
    candidates = []

    for t in tasks:
        if t.get("status") == "decomposed":
            continue
        score = score_complexity(t)
        if score > DECOMPOSE_THRESHOLD:
            candidates.append((t, score))

    if not candidates:
        print("  No tasks exceed the decomposition threshold.")
        print(f"  (Threshold: complexity > {DECOMPOSE_THRESHOLD})")
        return

    print(f"  Tasks recommended for decomposition (complexity > {DECOMPOSE_THRESHOLD}):\n")
    for t, score in candidates:
        tid = t.get("task_id", "???")
        title = t.get("title", "(no title)")
        criteria = len(t.get("acceptance_criteria") or [])
        files = len(t.get("files_in_scope") or [])
        print(f"  {tid}  {title}")
        print(f"    Score: {score}  ({criteria} criteria, {files} files)")
        print(f"    → Decompose with: /decompose {tid}")
        print()


# ── Create / bulk-create helpers ────────────────────────────────────────


class TaskValidationError(ValueError):
    """Raised when a task dict fails schema validation."""


def _slugify_title(title: str) -> str:
    """Convert a title into a kebab-case filename slug.

    Lowercases, replaces any run of non-alphanumeric characters with a
    single hyphen, strips leading/trailing hyphens, truncates to 80 chars.
    Falls back to 'task' if the result is empty (e.g. title was all
    punctuation).
    """
    lowered = title.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
    if not slug:
        slug = "task"
    if len(slug) > 80:
        slug = slug[:80].rstrip("-") or "task"
    return slug


def _path_token_safe(value: str) -> bool:
    """True if ``value`` is safe to embed in a path token.

    Rejects any of: empty, path separators, parent-dir sequences, or
    leading dot. Used to guard --feature and --filename user inputs.
    """
    if not value:
        return False
    if "/" in value or "\\" in value:
        return False
    if ".." in value:
        return False
    if value.startswith("."):
        return False
    return True


def _validate_task_dict(task: object, label: str) -> None:
    """Validate a task dict in place. Raises TaskValidationError on failure.

    ``label`` is a human-friendly identifier for the task used in error
    messages — either the task_id or 'task at index N' for bulk input.
    """
    if not isinstance(task, dict):
        raise TaskValidationError(f"{label} is not an object")

    for field in REQUIRED_FIELDS:
        if field not in task or task.get(field) in (None, "", []):
            # Use task_id in message when we have it, else the provided label.
            ident = task.get("task_id") or label
            raise TaskValidationError(
                f"task '{ident}' missing required field: {field}"
            )

    # Scalar string fields
    for field in ("task_id", "title", "assigned_agent"):
        value = task[field]
        if not isinstance(value, str) or not value.strip():
            ident = task.get("task_id") or label
            raise TaskValidationError(
                f"task '{ident}' field '{field}' must be a non-empty string"
            )

    # List-of-string fields (required)
    for field in ("files_in_scope", "acceptance_criteria"):
        value = task[field]
        if not isinstance(value, list) or not value:
            ident = task.get("task_id") or label
            raise TaskValidationError(
                f"task '{ident}' field '{field}' must be a non-empty list"
            )
        for item in value:
            if not isinstance(item, str) or not item.strip():
                ident = task.get("task_id") or label
                raise TaskValidationError(
                    f"task '{ident}' field '{field}' contains a non-string or empty item"
                )

    # List-of-string fields (optional)
    for field in ("dependencies", "requires_reading"):
        if field in task and task[field] is not None:
            value = task[field]
            if not isinstance(value, list):
                ident = task.get("task_id") or label
                raise TaskValidationError(
                    f"task '{ident}' field '{field}' must be a list"
                )
            for item in value:
                if not isinstance(item, str) or not item.strip():
                    ident = task.get("task_id") or label
                    raise TaskValidationError(
                        f"task '{ident}' field '{field}' contains a non-string or empty item"
                    )

    # Optional scalar strings
    for field in ("parent_task", "context", "filename"):
        if field in task and task[field] is not None:
            if not isinstance(task[field], str) or not task[field]:
                ident = task.get("task_id") or label
                raise TaskValidationError(
                    f"task '{ident}' field '{field}' must be a non-empty string"
                )

    # Status enum
    status = task.get("status")
    if status is not None and status not in VALID_STATUSES:
        ident = task.get("task_id") or label
        raise TaskValidationError(
            f"task '{ident}' has invalid status '{status}'. "
            f"Valid: {', '.join(sorted(VALID_STATUSES))}"
        )


def _resolve_task_path(root: Path, task: dict, feature: str | None) -> Path:
    """Compute the final on-disk path for a task, with traversal guards.

    F009-lifecycle-gap fix: honors F009 lifecycle. If the feature already exists under
    active/ or flat path, write tasks into the existing location. If
    only shipped/ has it, refuse (can't modify a shipped feature). If
    no feature dir exists, create at the flat path as the legacy
    default — callers expected to allocate via /spec or feature_id.py
    first, but bulk-create's historical behavior is to auto-create
    the flat path, and we preserve that for backwards compatibility.
    """
    if feature is not None:
        if not _path_token_safe(feature):
            raise TaskValidationError(
                f"invalid --feature value '{feature}' (path traversal guard)"
            )
        feature_dir = _find_feature_dir_lifecycle(root, feature)
        if feature_dir is not None:
            # Refuse to write into shipped/. (TaskValidationError inherits
            # from ValueError so we can't use a try/except ValueError dance
            # around relative_to — it would swallow our own raise. Use
            # is_relative_to which is bool-shaped.)
            shipped_root = (root / ".etc_sdlc" / "features" / "shipped").resolve()
            if feature_dir.resolve().is_relative_to(shipped_root):
                raise TaskValidationError(
                    f"feature '{feature}' is in shipped/; cannot modify a "
                    f"shipped feature. Allocate a new feature via /spec."
                )
            tasks_dir = feature_dir / "tasks"
        else:
            # Fallback: legacy flat-path auto-creation.
            tasks_dir = root / ".etc_sdlc" / "features" / feature / "tasks"
    else:
        tasks_dir = root / ".etc_sdlc" / "tasks"

    filename = task.get("filename")
    if filename:
        if not _path_token_safe(filename):
            raise TaskValidationError(
                f"invalid filename '{filename}' (path traversal guard)"
            )
        name = filename if filename.endswith(".yaml") else filename + ".yaml"
    else:
        slug = _slugify_title(task["title"])
        name = f"{task['task_id']}-{slug}.yaml"

    path = tasks_dir / name

    # Resolve and confine to .etc_sdlc tree.
    try:
        resolved = path.resolve()
        etc_root = (root / ".etc_sdlc").resolve()
    except OSError as exc:
        raise TaskValidationError(f"failed to resolve path {path}: {exc}") from exc
    # Use parent check that tolerates non-existence.
    try:
        resolved.relative_to(etc_root)
    except ValueError as exc:
        raise TaskValidationError(
            f"resolved path {resolved} escapes .etc_sdlc"
        ) from exc

    return path


def _emit_task_yaml(task: dict) -> str:
    """Hand-rolled YAML emitter — produces byte-identical output to the
    style used by tests/test_tasks.py::_create_task and existing task
    files under .etc_sdlc/features/*/tasks/.

    Field order is fixed:
      task_id, title, assigned_agent, status, parent_task (if set),
      requires_reading, files_in_scope, acceptance_criteria,
      dependencies, context (if set).
    """
    lines: list[str] = []
    lines.append(f'task_id: "{task["task_id"]}"')
    lines.append(f'title: "{task["title"]}"')
    lines.append(f"assigned_agent: {task['assigned_agent']}")
    lines.append(f"status: {task.get('status', 'pending')}")

    parent = task.get("parent_task")
    if parent:
        lines.append(f'parent_task: "{parent}"')

    reading = task.get("requires_reading") or []
    if reading:
        lines.append("requires_reading:")
        for item in reading:
            lines.append(f"  - {item}")
    else:
        lines.append("requires_reading: []")

    lines.append("files_in_scope:")
    for item in task["files_in_scope"]:
        lines.append(f"  - {item}")

    lines.append("acceptance_criteria:")
    for item in task["acceptance_criteria"]:
        lines.append(f'  - "{item}"')

    deps = task.get("dependencies") or []
    if deps:
        lines.append("dependencies:")
        for item in deps:
            lines.append(f'  - "{item}"')
    else:
        lines.append("dependencies: []")

    context = task.get("context")
    if context:
        lines.append("context: |")
        # Strip a single trailing newline to avoid double blank line at EOF,
        # but preserve internal structure.
        body = context.rstrip("\n")
        for cline in body.split("\n"):
            lines.append(f"  {cline}" if cline else "  ")

    return "\n".join(lines) + "\n"


def _parse_create_argv(argv: list[str]) -> tuple[dict, str | None]:
    """Parse create-command flags from argv (sys.argv[2:] slice).

    Returns (task_dict, feature) where feature is the --feature value or
    None. Unknown or malformed flags raise TaskValidationError.
    """
    task: dict = {
        "files_in_scope": [],
        "acceptance_criteria": [],
        "dependencies": [],
        "requires_reading": [],
    }
    feature: str | None = None

    i = 0
    while i < len(argv):
        flag = argv[i]
        if flag in ("--task-id", "--title", "--agent", "--status",
                    "--parent", "--context", "--feature", "--filename"):
            if i + 1 >= len(argv):
                raise TaskValidationError(f"flag {flag} requires a value")
            value = argv[i + 1]
            i += 2
            if flag == "--task-id":
                task["task_id"] = value
            elif flag == "--title":
                task["title"] = value
            elif flag == "--agent":
                task["assigned_agent"] = value
            elif flag == "--status":
                task["status"] = value
            elif flag == "--parent":
                task["parent_task"] = value
            elif flag == "--context":
                task["context"] = value
            elif flag == "--feature":
                feature = value
            elif flag == "--filename":
                task["filename"] = value
        elif flag in ("--file", "--ac", "--dep", "--read"):
            if i + 1 >= len(argv):
                raise TaskValidationError(f"flag {flag} requires a value")
            value = argv[i + 1]
            i += 2
            if flag == "--file":
                task["files_in_scope"].append(value)
            elif flag == "--ac":
                task["acceptance_criteria"].append(value)
            elif flag == "--dep":
                task["dependencies"].append(value)
            elif flag == "--read":
                task["requires_reading"].append(value)
        else:
            raise TaskValidationError(f"unknown flag: {flag}")

    # Normalize empties so downstream helpers see consistent structure.
    if not task["dependencies"]:
        task["dependencies"] = []
    if not task["requires_reading"]:
        task["requires_reading"] = []
    return task, feature


def cmd_create(root: Path) -> None:
    """Create a single task YAML file from CLI flags."""
    try:
        task, feature = _parse_create_argv(sys.argv[2:])
        _validate_task_dict(task, label=task.get("task_id") or "task")
        path = _resolve_task_path(root, task, feature)
    except TaskValidationError as exc:
        print(f"  Error: {exc}")
        sys.exit(1)

    if path.exists():
        print(f"  Error: target file already exists: {path}")
        sys.exit(1)

    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.write_text(_emit_task_yaml(task))
    except OSError as exc:
        print(f"  Error: failed to write {path}: {exc}")
        sys.exit(1)

    try:
        rel = path.relative_to(root)
    except ValueError:
        rel = path
    print(f"  Created: {rel}")


def _parse_bulk_argv(argv: list[str]) -> tuple[str | None, str | None, str | None, bool]:
    """Parse bulk-create flags. Returns (feature, json_inline, json_file, allow_existing)."""
    feature: str | None = None
    json_inline: str | None = None
    json_file: str | None = None
    allow_existing = False

    i = 0
    while i < len(argv):
        flag = argv[i]
        if flag == "--feature":
            if i + 1 >= len(argv):
                raise TaskValidationError("flag --feature requires a value")
            feature = argv[i + 1]
            i += 2
        elif flag == "--json":
            if i + 1 >= len(argv):
                raise TaskValidationError("flag --json requires a value")
            json_inline = argv[i + 1]
            i += 2
        elif flag == "--json-file":
            if i + 1 >= len(argv):
                raise TaskValidationError("flag --json-file requires a value")
            json_file = argv[i + 1]
            i += 2
        elif flag == "--allow-existing":
            allow_existing = True
            i += 1
        else:
            raise TaskValidationError(f"unknown flag: {flag}")

    if json_inline is not None and json_file is not None:
        raise TaskValidationError(
            "specify at most one of --json, --json-file, or stdin"
        )
    return feature, json_inline, json_file, allow_existing


def cmd_bulk_create(root: Path) -> None:
    """Bulk-create task YAML files from a JSON array with atomic writes."""
    try:
        feature, json_inline, json_file, allow_existing = _parse_bulk_argv(sys.argv[2:])
    except TaskValidationError as exc:
        print(f"  Error: {exc}")
        sys.exit(1)

    # Load JSON from exactly one source.
    try:
        if json_inline is not None:
            raw = json_inline
        elif json_file is not None:
            raw = Path(json_file).read_text()
        else:
            if sys.stdin.isatty():
                print("  Error: no JSON input provided on stdin")
                sys.exit(1)
            raw = sys.stdin.read()
            if not raw.strip():
                print("  Error: no JSON input provided on stdin")
                sys.exit(1)
    except OSError as exc:
        print(f"  Error: failed to read JSON input: {exc}")
        sys.exit(1)

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"  Error: invalid JSON: {exc}")
        sys.exit(1)

    if not isinstance(parsed, list):
        print(f"  Error: expected JSON array, got {type(parsed).__name__}")
        sys.exit(1)

    # Validate every task first, then resolve paths, then detect duplicates.
    try:
        for idx, entry in enumerate(parsed):
            if not isinstance(entry, dict):
                raise TaskValidationError(
                    f"task at index {idx} is not an object"
                )
            _validate_task_dict(entry, label=f"task at index {idx}")

        # Duplicate task_id check within batch
        seen_ids: set[str] = set()
        for entry in parsed:
            tid = entry["task_id"]
            if tid in seen_ids:
                raise TaskValidationError(f"duplicate task_id '{tid}' in batch")
            seen_ids.add(tid)

        # Resolve all paths
        plan: list[tuple[Path, str, dict]] = []
        seen_paths: set[Path] = set()
        for entry in parsed:
            path = _resolve_task_path(root, entry, feature)
            if path in seen_paths:
                raise TaskValidationError(
                    f"duplicate target path '{path}' in batch"
                )
            seen_paths.add(path)
            plan.append((path, _emit_task_yaml(entry), entry))
    except TaskValidationError as exc:
        print(f"  Error: {exc}")
        sys.exit(1)

    # Pre-existence check
    existing = [path for (path, _, _) in plan if path.exists()]
    if existing and not allow_existing:
        print("  Error: target files already exist:")
        for path in existing:
            try:
                rel = path.relative_to(root)
            except ValueError:
                rel = path
            print(f"    {rel}")
        sys.exit(1)

    # Filter out skipped paths when --allow-existing
    skipped: list[Path] = []
    to_write: list[tuple[Path, str]] = []
    for path, content, _ in plan:
        if path.exists() and allow_existing:
            skipped.append(path)
        else:
            to_write.append((path, content))

    # Atomic write with rollback
    written: list[Path] = []
    try:
        for path, content in to_write:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
            written.append(path)
    except OSError as exc:
        # Rollback
        for path in written:
            try:
                path.unlink()
            except OSError:
                pass
        print(f"  Error: write failed ({exc}); rolled back {len(written)} file(s)")
        sys.exit(1)

    # Report
    if skipped:
        print(f"  Created {len(written)} tasks, skipped {len(skipped)} existing:")
    else:
        print(f"  Created {len(written)} tasks:")
    for path in written:
        try:
            rel = path.relative_to(root)
        except ValueError:
            rel = path
        print(f"    {rel}")
    if skipped:
        print("  Skipped (already exist):")
        for path in skipped:
            try:
                rel = path.relative_to(root)
            except ValueError:
                rel = path
            print(f"    {rel}")


# ── validate subcommand (AC-013, BR-011) ────────────────────────────────

FEATURE_ID_PATTERN = re.compile(r"^F\d{3}$")
URL_PREFIXES = ("http://", "https://")
LEGAL_DIRECTIONS = frozenset({"increase", "decrease"})


class ValidateError(ValueError):
    """Raised when validate-subcommand input or state is bad."""


def _parse_validate_argv(argv: list[str]) -> tuple[str, str, str]:
    """Parse ``validate FEATURE_ID --measured V --evidence E`` flags.

    Returns ``(feature_id, measured_raw, evidence_raw)``. Caller is
    responsible for further validation of the values.
    """
    if not argv:
        raise ValidateError("missing feature_id (expected F<NNN>)")

    feature_id = argv[0]
    measured: str | None = None
    evidence: str | None = None

    i = 1
    while i < len(argv):
        flag = argv[i]
        if flag == "--measured":
            if i + 1 >= len(argv):
                raise ValidateError("flag --measured requires a value")
            measured = argv[i + 1]
            i += 2
        elif flag == "--evidence":
            if i + 1 >= len(argv):
                raise ValidateError("flag --evidence requires a value")
            evidence = argv[i + 1]
            i += 2
        else:
            raise ValidateError(f"unknown flag: {flag}")

    if measured is None:
        raise ValidateError("missing required flag: --measured")
    if evidence is None:
        raise ValidateError("missing required flag: --evidence")

    return feature_id, measured, evidence


def _parse_measured(raw: str) -> int | float:
    """Parse ``--measured`` as int or float; reject everything else.

    Integers are returned as ``int``; values containing a decimal point or
    exponent are returned as ``float``. Hex, leading ``+``, ``inf``, and
    ``nan`` are rejected explicitly to keep the on-disk representation
    boring.
    """
    text = raw.strip()
    if not text:
        raise ValidateError("--measured must be a numeric value (int or float)")

    # Reject inf/nan/hex/octal/binary literals that float() would otherwise eat.
    lowered = text.lower().lstrip("+-")
    if lowered in {"inf", "infinity", "nan"} or lowered.startswith(("0x", "0o", "0b")):
        raise ValidateError(
            f"--measured value {raw!r} is not a finite numeric (int or float)"
        )

    if "." in text or "e" in lowered:
        try:
            return float(text)
        except ValueError as exc:
            raise ValidateError(
                f"--measured value {raw!r} is not numeric (int or float)"
            ) from exc

    try:
        return int(text)
    except ValueError as exc:
        raise ValidateError(
            f"--measured value {raw!r} is not numeric (int or float)"
        ) from exc


def _canonicalize_evidence(raw: str, project_root: Path) -> str:
    """Return the canonical evidence string.

    URLs starting with ``http://`` or ``https://`` are returned unchanged.
    Everything else is treated as a filesystem path: resolved via
    ``Path.resolve()`` against ``project_root`` for relative paths, then
    confined to the project working tree. Symbolic links are followed by
    ``resolve()``; the post-resolution path is the boundary check, so
    links pointing outside the tree are rejected.
    """
    if raw.startswith(URL_PREFIXES):
        return raw

    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = project_root / candidate

    try:
        resolved = candidate.resolve()
        root_resolved = project_root.resolve()
    except OSError as exc:
        raise ValidateError(f"failed to resolve evidence path {raw!r}: {exc}") from exc

    try:
        resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise ValidateError(
            f"--evidence path {raw!r} resolves outside the project tree "
            f"({resolved}); refusing to record"
        ) from exc

    return str(resolved)


def _find_value_hypothesis(project_root: Path, feature_id: str) -> Path:
    """Locate the value-hypothesis.yaml for ``feature_id``.

    Searches ``.etc_sdlc/features/<feature_id>-*/`` for the canonical
    file. Returns the first match (feature IDs are unique by BR-002).
    """
    features_dir = project_root / ".etc_sdlc" / "features"
    if not features_dir.is_dir():
        raise ValidateError(
            f"value-hypothesis.yaml not found for {feature_id}: "
            f".etc_sdlc/features directory does not exist under {project_root}"
        )

    matches = sorted(features_dir.glob(f"{feature_id}-*"))
    for candidate in matches:
        target = candidate / "value-hypothesis.yaml"
        if target.is_file():
            return target

    raise ValidateError(
        f"value-hypothesis.yaml not found for {feature_id} "
        f"(searched {features_dir}/{feature_id}-*/value-hypothesis.yaml)"
    )


def _decide_status(
    measured: int | float, direction: str, threshold: int | float
) -> str:
    """Return ``validated`` if the measured value crosses the threshold.

    ``decrease``: validated when ``measured <= threshold``.
    ``increase``: validated when ``measured >= threshold``.
    """
    if direction == "decrease":
        return "validated" if measured <= threshold else "invalidated"
    if direction == "increase":
        return "validated" if measured >= threshold else "invalidated"
    raise ValidateError(
        f"value-hypothesis predicted.direction must be 'increase' or "
        f"'decrease'; got {direction!r}"
    )


def _atomic_write_yaml(target: Path, payload: dict) -> None:
    """Write YAML atomically: temp file in same dir, fsync, rename.

    On any failure the temp file is unlinked. The original ``target`` is
    only ever replaced via ``os.replace`` (atomic on POSIX).
    """
    body = yaml.safe_dump(payload, sort_keys=False, default_flow_style=False)

    target_dir = target.parent
    target_dir.mkdir(parents=True, exist_ok=True)

    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=str(target_dir)
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        # Path.replace is atomic on POSIX and Windows for same-volume moves.
        tmp_path.replace(target)
    except OSError:
        # Best-effort cleanup; original target is untouched because the
        # rename never completed.
        try:
            tmp_path.unlink()
        except OSError:
            pass
        raise


def _load_value_hypothesis_module() -> object:
    """Import scripts/value_hypothesis.py without making scripts a package."""
    module_path = Path(__file__).resolve().parent / "value_hypothesis.py"
    spec = importlib.util.spec_from_file_location("value_hypothesis", module_path)
    if spec is None or spec.loader is None:
        msg = f"cannot load value_hypothesis module at {module_path}"
        raise ValidateError(msg)
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("value_hypothesis", module)
    spec.loader.exec_module(module)
    return module


def _extract_direction_and_threshold(
    hypothesis: dict, target: Path
) -> tuple[str, int | float]:
    """Pull and type-check ``predicted.direction`` / ``predicted.threshold``."""
    predicted = hypothesis.get("predicted") or {}
    direction = predicted.get("direction")
    threshold = predicted.get("threshold")
    if direction not in LEGAL_DIRECTIONS:
        raise ValidateError(
            f"{target} predicted.direction must be 'increase' or 'decrease'; "
            f"got {direction!r}"
        )
    if not isinstance(threshold, (int, float)) or isinstance(threshold, bool):
        raise ValidateError(
            f"{target} predicted.threshold must be numeric; got "
            f"{threshold!r} ({type(threshold).__name__})"
        )
    return direction, threshold


def cmd_validate(
    root: Path, feature_id: str, measured: str, evidence: str
) -> None:
    """Implement ``tasks.py validate`` (AC-013).

    Updates the matching value-hypothesis.yaml: sets ``status`` per
    ``predicted.direction`` and the measured threshold, fills the
    ``validation`` block, and writes atomically.
    """
    if not FEATURE_ID_PATTERN.match(feature_id):
        raise ValidateError(
            f"feature_id {feature_id!r} does not match ^F\\d{{3}}$ "
            f"(expected F<NNN>, e.g. F042)"
        )

    measured_value = _parse_measured(measured)
    evidence_canonical = _canonicalize_evidence(evidence, root)
    target = _find_value_hypothesis(root, feature_id)

    vh = _load_value_hypothesis_module()
    hypothesis = vh.load(target)  # type: ignore[attr-defined]
    if hypothesis is None:
        # load() returned None → unsupported future schema_version.
        raise ValidateError(
            f"{target} has an unsupported schema_version; refusing to write"
        )

    direction, threshold = _extract_direction_and_threshold(hypothesis, target)
    new_status = _decide_status(measured_value, direction, threshold)

    evidence_block = {
        "measured_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "measured_value": measured_value,
        "evidence": evidence_canonical,
    }
    updated = vh.transition_status(  # type: ignore[attr-defined]
        hypothesis, new_status, evidence_block
    )

    try:
        _atomic_write_yaml(target, updated)
    except OSError as exc:
        print(f"  Error: failed to write {target}: {exc}")
        sys.exit(1)

    try:
        rel = target.relative_to(root)
    except ValueError:
        rel = target
    print(f"  {feature_id}: status → {new_status} ({rel})")


def _dispatch_validate(root: Path) -> None:
    """argv parser + cmd_validate caller, with consistent error exit."""
    try:
        feature_id, measured, evidence = _parse_validate_argv(sys.argv[2:])
        cmd_validate(root, feature_id, measured, evidence)
    except ValidateError as exc:
        print(f"  Error: {exc}")
        sys.exit(1)


def main() -> None:
    root = Path.cwd()

    if len(sys.argv) < 2:
        cmd_list(root)
        return

    command = sys.argv[1]

    if command == "list":
        status_filter = None
        tree_view = "--tree" in sys.argv
        if "--status" in sys.argv:
            idx = sys.argv.index("--status")
            if idx + 1 < len(sys.argv):
                status_filter = sys.argv[idx + 1]
        cmd_list(root, status_filter, tree_view)
    elif command == "next":
        cmd_next(root)
    elif command == "status":
        cmd_status(root)
    elif command == "board":
        cmd_board(root)
    elif command == "set-status":
        # Extract optional --feature NAME before positional parsing so the
        # flag can appear anywhere in the argv tail.
        argv_tail = list(sys.argv[2:])
        feature: str | None = None
        if "--feature" in argv_tail:
            idx = argv_tail.index("--feature")
            if idx + 1 >= len(argv_tail):
                print("Error: --feature requires a value")
                sys.exit(1)
            feature = argv_tail[idx + 1]
            del argv_tail[idx : idx + 2]
        if len(argv_tail) < 2:
            print("Usage: tasks.py set-status [--feature NAME] TASK_ID STATUS")
            sys.exit(1)
        cmd_set_status(root, argv_tail[0], argv_tail[1], feature=feature)
    elif command == "deps":
        if len(sys.argv) < 3:
            print("Usage: tasks.py deps TASK_ID")
            sys.exit(1)
        cmd_deps(root, sys.argv[2])
    elif command == "score":
        task_id = sys.argv[2] if len(sys.argv) > 2 else None
        cmd_score(root, task_id)
    elif command == "tree":
        cmd_tree(root)
    elif command == "waves":
        # NOTE: feature was annotated in the set-status branch above; mypy
        # treats main() as one scope and flags re-annotation. Drop the
        # type annotation here — the value is reassigned, not redeclared.
        feature = None
        if "--feature" in sys.argv:
            idx = sys.argv.index("--feature")
            if idx + 1 < len(sys.argv):
                feature = sys.argv[idx + 1]
        cmd_waves(root, feature=feature)
    elif command == "phases":
        feature = None
        if "--feature" in sys.argv:
            idx = sys.argv.index("--feature")
            if idx + 1 < len(sys.argv):
                feature = sys.argv[idx + 1]
        cmd_phases(root, feature=feature)
    elif command == "ready-to-decompose":
        cmd_ready_to_decompose(root)
    elif command == "create":
        cmd_create(root)
    elif command == "bulk-create":
        cmd_bulk_create(root)
    elif command == "validate":
        _dispatch_validate(root)
    else:
        print(f"Unknown command: {command}")
        print(
            "Commands: list, next, status, board, set-status, deps, score, "
            "tree, waves, phases, ready-to-decompose, create, bulk-create, "
            "validate"
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
