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
    python3 tasks.py ready-to-decompose
    python3 tasks.py create --task-id ID --title T --agent A --file F --ac C [...]
    python3 tasks.py bulk-create [--feature NAME]
        [--json JSON | --json-file PATH] [--allow-existing]
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml

# ── Shared constants ────────────────────────────────────────────────────

VALID_STATUSES = {
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
COMPLEXITY_THRESHOLDS = {
    "target_loc": 300,
    "warn_loc": 500,
    "max_loc": 1000,
}

# Complexity score formula weights
CRITERIA_WEIGHT = 1.5   # Each acceptance criterion adds ~1.5 points
FILES_WEIGHT = 1.0      # Each file in scope adds ~1.0 points
DECOMPOSE_THRESHOLD = 7  # Tasks scoring > 7 should be decomposed


def find_task_files(root: Path, feature: str | None = None) -> list[Path]:
    """Find all task YAML files in feature dirs and global task dir.

    When ``feature`` is given, only tasks under
    ``.etc_sdlc/features/<feature>/tasks/`` are returned. The global
    ``.etc_sdlc/tasks/`` dir is skipped in that case because it is not
    scoped to any feature.
    """
    files: list[Path] = []

    features_dir = root / ".etc_sdlc" / "features"
    if feature is not None:
        scoped = features_dir / feature / "tasks"
        if scoped.is_dir():
            files.extend(sorted(scoped.glob("*.yaml")))
        return files

    # No feature filter — include every feature plus the legacy global dir.
    if features_dir.is_dir():
        for feature_dir in sorted(features_dir.iterdir()):
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


def compute_waves(tasks: list[dict]) -> dict[int, list[dict]]:
    """Group pending leaf tasks into execution waves by dependency.

    Wave 0: tasks with no unmet dependencies
    Wave N: tasks whose dependencies are all in waves < N or already completed

    Already-completed and decomposed tasks never appear in any wave, but
    their task_ids are pre-populated into ``satisfied_ids`` so pending tasks
    that depend on them are scheduled in Wave 0 instead of waiting forever.
    """
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

    return waves


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
    waves = compute_waves(tasks)

    if not waves:
        print("No tasks found.")
        return

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
    """Compute the final on-disk path for a task, with traversal guards."""
    if feature is not None:
        if not _path_token_safe(feature):
            raise TaskValidationError(
                f"invalid --feature value '{feature}' (path traversal guard)"
            )
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
        feature: str | None = None
        if "--feature" in sys.argv:
            idx = sys.argv.index("--feature")
            if idx + 1 < len(sys.argv):
                feature = sys.argv[idx + 1]
        cmd_waves(root, feature=feature)
    elif command == "ready-to-decompose":
        cmd_ready_to_decompose(root)
    elif command == "create":
        cmd_create(root)
    elif command == "bulk-create":
        cmd_bulk_create(root)
    else:
        print(f"Unknown command: {command}")
        print(
            "Commands: list, next, status, board, set-status, deps, score, "
            "tree, waves, ready-to-decompose, create, bulk-create"
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
