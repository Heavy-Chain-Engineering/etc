"""Tests for scripts/tasks.py — native task tracker."""

from __future__ import annotations

import subprocess
from pathlib import Path

TASKS_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "tasks.py"


def _run_tasks(tmp_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run tasks.py with the given args in tmp_path as cwd."""
    return subprocess.run(
        ["python3", str(TASKS_SCRIPT), *args],
        capture_output=True,
        text=True,
        cwd=str(tmp_path),
        timeout=10,
    )


def _create_task(tasks_dir: Path, task_id: str, title: str, status: str = "pending",
                 deps: list[str] | None = None, agent: str = "backend-developer") -> Path:
    """Create a task YAML file."""
    tasks_dir.mkdir(parents=True, exist_ok=True)
    path = tasks_dir / f"{task_id}-{title.lower().replace(' ', '-')}.yaml"
    lines = [
        f"task_id: \"{task_id}\"",
        f"title: \"{title}\"",
        f"assigned_agent: {agent}",
        f"status: {status}",
        "requires_reading:",
        "  - spec/prd.md",
        "files_in_scope:",
        "  - src/app.py",
        "acceptance_criteria:",
        "  - \"Tests pass\"",
    ]
    if deps:
        lines.append("dependencies:")
        for d in deps:
            lines.append(f"  - \"{d}\"")
    else:
        lines.append("dependencies: []")
    path.write_text("\n".join(lines) + "\n")
    return path


class TestList:
    def test_should_show_all_tasks(self, tmp_path: Path) -> None:
        tasks_dir = tmp_path / ".etc_sdlc" / "tasks"
        _create_task(tasks_dir, "001", "First task", "pending")
        _create_task(tasks_dir, "002", "Second task", "completed")

        result = _run_tasks(tmp_path, "list")
        assert result.returncode == 0
        assert "001" in result.stdout
        assert "002" in result.stdout

    def test_should_filter_by_status(self, tmp_path: Path) -> None:
        tasks_dir = tmp_path / ".etc_sdlc" / "tasks"
        _create_task(tasks_dir, "001", "Pending task", "pending")
        _create_task(tasks_dir, "002", "Done task", "completed")

        result = _run_tasks(tmp_path, "list", "--status", "completed")
        assert result.returncode == 0
        assert "002" in result.stdout
        assert "001" not in result.stdout

    def test_should_find_feature_tasks(self, tmp_path: Path) -> None:
        tasks_dir = tmp_path / ".etc_sdlc" / "features" / "auth" / "tasks"
        _create_task(tasks_dir, "001", "Auth task")

        result = _run_tasks(tmp_path, "list")
        assert "001" in result.stdout

    def test_should_show_no_tasks_message(self, tmp_path: Path) -> None:
        result = _run_tasks(tmp_path, "list")
        assert "No tasks" in result.stdout


class TestNext:
    def test_should_show_ready_task(self, tmp_path: Path) -> None:
        tasks_dir = tmp_path / ".etc_sdlc" / "tasks"
        _create_task(tasks_dir, "001", "Ready task", "pending")

        result = _run_tasks(tmp_path, "next")
        assert "001" in result.stdout
        assert "Ready task" in result.stdout

    def test_should_skip_blocked_task(self, tmp_path: Path) -> None:
        tasks_dir = tmp_path / ".etc_sdlc" / "tasks"
        _create_task(tasks_dir, "001", "Blocker", "pending")
        _create_task(tasks_dir, "002", "Blocked task", "pending", deps=["001"])

        result = _run_tasks(tmp_path, "next")
        assert "001" in result.stdout
        assert "002" not in result.stdout

    def test_should_unblock_when_dep_completed(self, tmp_path: Path) -> None:
        tasks_dir = tmp_path / ".etc_sdlc" / "tasks"
        _create_task(tasks_dir, "001", "Done blocker", "completed")
        _create_task(tasks_dir, "002", "Now ready", "pending", deps=["001"])

        result = _run_tasks(tmp_path, "next")
        assert "002" in result.stdout

    def test_should_show_nothing_when_all_done(self, tmp_path: Path) -> None:
        tasks_dir = tmp_path / ".etc_sdlc" / "tasks"
        _create_task(tasks_dir, "001", "Done", "completed")

        result = _run_tasks(tmp_path, "next")
        assert "No tasks ready" in result.stdout


class TestStatus:
    def test_should_show_counts(self, tmp_path: Path) -> None:
        tasks_dir = tmp_path / ".etc_sdlc" / "tasks"
        _create_task(tasks_dir, "001", "A", "pending")
        _create_task(tasks_dir, "002", "B", "in_progress")
        _create_task(tasks_dir, "003", "C", "completed")

        result = _run_tasks(tmp_path, "status")
        assert "3 total" in result.stdout
        assert "pending: 1" in result.stdout
        assert "in_progress: 1" in result.stdout
        assert "completed: 1" in result.stdout


class TestBoard:
    def test_should_group_by_status(self, tmp_path: Path) -> None:
        tasks_dir = tmp_path / ".etc_sdlc" / "tasks"
        _create_task(tasks_dir, "001", "Pending one", "pending")
        _create_task(tasks_dir, "002", "In progress one", "in_progress")
        _create_task(tasks_dir, "003", "Done one", "completed")

        result = _run_tasks(tmp_path, "board")
        assert "PENDING" in result.stdout
        assert "IN_PROGRESS" in result.stdout
        assert "COMPLETED" in result.stdout


class TestSetStatus:
    def test_should_update_status(self, tmp_path: Path) -> None:
        tasks_dir = tmp_path / ".etc_sdlc" / "tasks"
        path = _create_task(tasks_dir, "001", "Task", "pending")

        result = _run_tasks(tmp_path, "set-status", "001", "in_progress")
        assert result.returncode == 0

        updated = path.read_text()
        assert "status: in_progress" in updated

    def test_should_reject_invalid_status(self, tmp_path: Path) -> None:
        tasks_dir = tmp_path / ".etc_sdlc" / "tasks"
        _create_task(tasks_dir, "001", "Task", "pending")

        result = _run_tasks(tmp_path, "set-status", "001", "bogus")
        assert result.returncode == 1


class TestDeps:
    def test_should_show_dependency_tree(self, tmp_path: Path) -> None:
        tasks_dir = tmp_path / ".etc_sdlc" / "tasks"
        _create_task(tasks_dir, "001", "Base", "completed")
        _create_task(tasks_dir, "002", "Child", "pending", deps=["001"])

        result = _run_tasks(tmp_path, "deps", "002")
        assert "001" in result.stdout
        assert "002" in result.stdout
