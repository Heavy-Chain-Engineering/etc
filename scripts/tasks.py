#!/usr/bin/env python3
"""tasks.py — Native task tracker for the etc harness.

Operates on YAML task files in .etc_sdlc/features/*/tasks/ and .etc_sdlc/tasks/.
Replaces the Taskmaster dependency with a thin layer built on our existing format.

Usage:
    python3 tasks.py list [--status STATUS]
    python3 tasks.py next
    python3 tasks.py status
    python3 tasks.py board
    python3 tasks.py set-status TASK_ID STATUS
    python3 tasks.py deps TASK_ID
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml


def find_task_files(root: Path) -> list[Path]:
    """Find all task YAML files in feature dirs and global task dir."""
    files: list[Path] = []

    # Per-feature tasks (preferred)
    features_dir = root / ".etc_sdlc" / "features"
    if features_dir.is_dir():
        for feature_dir in sorted(features_dir.iterdir()):
            tasks_dir = feature_dir / "tasks"
            if tasks_dir.is_dir():
                files.extend(sorted(tasks_dir.glob("*.yaml")))

    # Global tasks (backward compat)
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


def load_all_tasks(root: Path) -> list[dict]:
    """Load all task files."""
    return [load_task(p) for p in find_task_files(root)]


def cmd_list(root: Path, status_filter: str | None = None) -> None:
    """List all tasks with id, title, status, agent."""
    tasks = load_all_tasks(root)
    if not tasks:
        print("No tasks found.")
        return

    if status_filter:
        tasks = [t for t in tasks if t.get("status") == status_filter]

    for t in tasks:
        tid = t.get("task_id", "???")
        title = t.get("title", "(no title)")
        status = t.get("status", "unknown")
        agent = t.get("assigned_agent", "-")
        print(f"  [{status:12s}]  {tid:>4s}  {title}  ({agent})")


def cmd_next(root: Path) -> None:
    """Show the next task ready for work (pending + all deps completed)."""
    tasks = load_all_tasks(root)
    completed_ids = {t.get("task_id") for t in tasks if t.get("status") == "completed"}

    for t in tasks:
        if t.get("status") != "pending":
            continue
        deps = t.get("dependencies") or []
        if all(d in completed_ids for d in deps):
            tid = t.get("task_id", "???")
            title = t.get("title", "(no title)")
            agent = t.get("assigned_agent", "-")
            print(f"  Next: {tid} — {title} (assign to: {agent})")
            ac = t.get("acceptance_criteria") or []
            if ac:
                print(f"  Acceptance criteria:")
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

    total = len(tasks)
    print(f"  Tasks: {total} total")
    for s in ["pending", "in_progress", "completed", "escalated", "blocked"]:
        if s in counts:
            print(f"    {s}: {counts[s]}")


def cmd_board(root: Path) -> None:
    """Kanban-style view grouped by status."""
    tasks = load_all_tasks(root)
    groups: dict[str, list[dict]] = {}
    for t in tasks:
        s = t.get("status", "unknown")
        groups.setdefault(s, []).append(t)

    for status in ["pending", "in_progress", "completed", "escalated", "blocked"]:
        if status not in groups:
            continue
        print(f"\n  ── {status.upper()} ({len(groups[status])}) ──")
        for t in groups[status]:
            tid = t.get("task_id", "???")
            title = t.get("title", "(no title)")
            print(f"    {tid}  {title}")


def cmd_set_status(root: Path, task_id: str, new_status: str) -> None:
    """Update a task's status in its YAML file."""
    valid = {"pending", "in_progress", "completed", "escalated", "blocked"}
    if new_status not in valid:
        print(f"  Error: invalid status '{new_status}'. Valid: {', '.join(sorted(valid))}")
        sys.exit(1)

    tasks = load_all_tasks(root)
    for t in tasks:
        if t.get("task_id") == task_id:
            path = t["_path"]
            text = path.read_text()
            # Replace status line
            import re
            updated = re.sub(
                r"^status:\s*\S+",
                f"status: {new_status}",
                text,
                count=1,
                flags=re.MULTILINE,
            )
            path.write_text(updated)
            print(f"  {task_id}: status → {new_status}")
            return

    print(f"  Error: task '{task_id}' not found.")
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


def main() -> None:
    root = Path.cwd()

    if len(sys.argv) < 2:
        cmd_list(root)
        return

    command = sys.argv[1]

    if command == "list":
        status_filter = None
        if "--status" in sys.argv:
            idx = sys.argv.index("--status")
            if idx + 1 < len(sys.argv):
                status_filter = sys.argv[idx + 1]
        cmd_list(root, status_filter)
    elif command == "next":
        cmd_next(root)
    elif command == "status":
        cmd_status(root)
    elif command == "board":
        cmd_board(root)
    elif command == "set-status":
        if len(sys.argv) < 4:
            print("Usage: tasks.py set-status TASK_ID STATUS")
            sys.exit(1)
        cmd_set_status(root, sys.argv[2], sys.argv[3])
    elif command == "deps":
        if len(sys.argv) < 3:
            print("Usage: tasks.py deps TASK_ID")
            sys.exit(1)
        cmd_deps(root, sys.argv[2])
    else:
        print(f"Unknown command: {command}")
        print("Commands: list, next, status, board, set-status, deps")
        sys.exit(1)


if __name__ == "__main__":
    main()
