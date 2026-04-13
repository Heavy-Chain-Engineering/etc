"""Tests for scripts/tasks.py — native task tracker with hierarchical decomposition."""

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


def _create_task(
    tasks_dir: Path,
    task_id: str,
    title: str,
    status: str = "pending",
    deps: list[str] | None = None,
    agent: str = "backend-developer",
    parent: str | None = None,
    criteria: list[str] | None = None,
    files: list[str] | None = None,
) -> Path:
    """Create a task YAML file."""
    tasks_dir.mkdir(parents=True, exist_ok=True)
    path = tasks_dir / f"{task_id}-{title.lower().replace(' ', '-')}.yaml"
    lines = [
        f'task_id: "{task_id}"',
        f'title: "{title}"',
        f"assigned_agent: {agent}",
        f"status: {status}",
    ]
    if parent:
        lines.append(f'parent_task: "{parent}"')
    lines.append("requires_reading:")
    lines.append("  - spec/prd.md")
    lines.append("files_in_scope:")
    for f in (files or ["src/app.py"]):
        lines.append(f"  - {f}")
    lines.append("acceptance_criteria:")
    for c in (criteria or ["Tests pass"]):
        lines.append(f'  - "{c}"')
    if deps:
        lines.append("dependencies:")
        for d in deps:
            lines.append(f'  - "{d}"')
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

    def test_should_only_show_leaf_tasks(self, tmp_path: Path) -> None:
        tasks_dir = tmp_path / ".etc_sdlc" / "tasks"
        _create_task(tasks_dir, "001", "Parent", "decomposed")
        _create_task(tasks_dir, "001.001", "Child", "pending", parent="001")

        result = _run_tasks(tmp_path, "next")
        assert "001.001" in result.stdout
        # Parent should not appear as next (it's decomposed, not a leaf)


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

    def test_should_show_leaf_vs_parent_count(self, tmp_path: Path) -> None:
        tasks_dir = tmp_path / ".etc_sdlc" / "tasks"
        _create_task(tasks_dir, "001", "Parent", "decomposed")
        _create_task(tasks_dir, "001.001", "Child A", "pending", parent="001")
        _create_task(tasks_dir, "001.002", "Child B", "pending", parent="001")

        result = _run_tasks(tmp_path, "status")
        assert "3 total" in result.stdout
        assert "2 leaf" in result.stdout
        assert "1 parent" in result.stdout


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

    def test_should_only_show_leaf_tasks(self, tmp_path: Path) -> None:
        tasks_dir = tmp_path / ".etc_sdlc" / "tasks"
        _create_task(tasks_dir, "001", "Parent", "decomposed")
        _create_task(tasks_dir, "001.001", "Leaf", "pending", parent="001")

        result = _run_tasks(tmp_path, "board")
        assert "001.001" in result.stdout
        # Decomposed parent should not appear on the board


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

    def test_should_accept_decomposed_status(self, tmp_path: Path) -> None:
        tasks_dir = tmp_path / ".etc_sdlc" / "tasks"
        path = _create_task(tasks_dir, "001", "Task", "pending")

        result = _run_tasks(tmp_path, "set-status", "001", "decomposed")
        assert result.returncode == 0
        assert "status: decomposed" in path.read_text()


class TestDeps:
    def test_should_show_dependency_tree(self, tmp_path: Path) -> None:
        tasks_dir = tmp_path / ".etc_sdlc" / "tasks"
        _create_task(tasks_dir, "001", "Base", "completed")
        _create_task(tasks_dir, "002", "Child", "pending", deps=["001"])

        result = _run_tasks(tmp_path, "deps", "002")
        assert "001" in result.stdout
        assert "002" in result.stdout


class TestScore:
    def test_should_score_simple_task(self, tmp_path: Path) -> None:
        tasks_dir = tmp_path / ".etc_sdlc" / "tasks"
        _create_task(tasks_dir, "001", "Simple", criteria=["Pass"], files=["src/a.py"])

        result = _run_tasks(tmp_path, "score")
        assert "001" in result.stdout
        # 1 criterion + 1 file = base score of 1
        assert "1" in result.stdout

    def test_should_flag_complex_task(self, tmp_path: Path) -> None:
        tasks_dir = tmp_path / ".etc_sdlc" / "tasks"
        _create_task(
            tasks_dir, "001", "Complex",
            criteria=["A", "B", "C", "D", "E", "F"],
            files=["src/a.py", "src/b.py", "src/c.py", "src/d.py", "tests/t.py"],
        )

        result = _run_tasks(tmp_path, "score")
        assert "DECOMPOSE" in result.stdout


class TestTree:
    def test_should_show_hierarchy(self, tmp_path: Path) -> None:
        tasks_dir = tmp_path / ".etc_sdlc" / "tasks"
        _create_task(tasks_dir, "001", "Parent", "decomposed")
        _create_task(tasks_dir, "001.001", "Child A", "pending", parent="001")
        _create_task(tasks_dir, "001.002", "Child B", "completed", parent="001")

        result = _run_tasks(tmp_path, "tree")
        assert "001" in result.stdout
        assert "001.001" in result.stdout
        assert "001.002" in result.stdout
        assert "✓" in result.stdout  # completed marker


class TestWaves:
    def test_should_group_independent_tasks(self, tmp_path: Path) -> None:
        tasks_dir = tmp_path / ".etc_sdlc" / "tasks"
        _create_task(tasks_dir, "001", "Independent A", "pending", files=["src/a.py"])
        _create_task(tasks_dir, "002", "Independent B", "pending", files=["src/b.py"])

        result = _run_tasks(tmp_path, "waves")
        assert "Wave 0" in result.stdout
        assert "2 tasks" in result.stdout

    def test_should_separate_dependent_tasks(self, tmp_path: Path) -> None:
        tasks_dir = tmp_path / ".etc_sdlc" / "tasks"
        _create_task(tasks_dir, "001", "First", "pending", files=["src/a.py"])
        _create_task(tasks_dir, "002", "Second", "pending", deps=["001"], files=["src/b.py"])

        result = _run_tasks(tmp_path, "waves")
        assert "Wave 0" in result.stdout
        assert "Wave 1" in result.stdout

    def test_should_warn_on_file_overlap(self, tmp_path: Path) -> None:
        tasks_dir = tmp_path / ".etc_sdlc" / "tasks"
        _create_task(tasks_dir, "001", "Task A", "pending", files=["src/shared.py"])
        _create_task(tasks_dir, "002", "Task B", "pending", files=["src/shared.py"])

        result = _run_tasks(tmp_path, "waves")
        assert "FILE OVERLAP" in result.stdout

    def test_should_exclude_completed_tasks_from_waves(self, tmp_path: Path) -> None:
        """A completed task must not appear in any wave, and its dependents
        must schedule in Wave 0 because the dep is already satisfied."""
        tasks_dir = tmp_path / ".etc_sdlc" / "tasks"
        _create_task(tasks_dir, "001", "Done", "completed", files=["src/a.py"])
        _create_task(tasks_dir, "002", "Pending dep", "pending", deps=["001"], files=["src/b.py"])

        result = _run_tasks(tmp_path, "waves")
        # 002 depends on completed 001 — it should land in Wave 0, not wait forever
        assert "Wave 0" in result.stdout
        assert "002" in result.stdout
        assert "Pending dep" in result.stdout
        # 001 is completed — it must NOT appear in any wave
        assert "Done" not in result.stdout

    def test_should_scope_to_feature_when_flag_given(self, tmp_path: Path) -> None:
        """--feature <name> must show only that feature's tasks, ignoring other
        features and the global tasks dir."""
        # Feature A (the one we want to see)
        a_tasks = tmp_path / ".etc_sdlc" / "features" / "alpha" / "tasks"
        _create_task(a_tasks, "001", "Alpha one", "pending", files=["src/alpha.py"])
        _create_task(a_tasks, "002", "Alpha two", "pending", files=["src/alpha2.py"])

        # Feature B (should be invisible)
        b_tasks = tmp_path / ".etc_sdlc" / "features" / "beta" / "tasks"
        _create_task(b_tasks, "001", "Beta one", "pending", files=["src/beta.py"])

        # Global tasks (should also be invisible with --feature)
        global_tasks = tmp_path / ".etc_sdlc" / "tasks"
        _create_task(global_tasks, "001", "Legacy one", "pending", files=["src/legacy.py"])

        result = _run_tasks(tmp_path, "waves", "--feature", "alpha")
        assert "Alpha one" in result.stdout
        assert "Alpha two" in result.stdout
        assert "Beta one" not in result.stdout
        assert "Legacy one" not in result.stdout

    def test_should_not_flag_false_overlap_across_features(self, tmp_path: Path) -> None:
        """When --feature scopes to one feature, file overlaps with OTHER
        features' completed tasks must not be flagged. This was the bug that
        surfaced during the /init-project build."""
        # init-project has a pending task touching tests/test_compiler.py
        init_tasks = tmp_path / ".etc_sdlc" / "features" / "init-project" / "tasks"
        _create_task(
            init_tasks, "002", "New compiler test", "pending",
            files=["tests/test_compiler.py"],
        )

        # old test-suite already shipped a (completed) task touching the same file
        old_tasks = tmp_path / ".etc_sdlc" / "tasks"
        _create_task(
            old_tasks, "010", "Historical compiler test", "completed",
            files=["tests/test_compiler.py"],
        )

        # Scoped view: no overlap flag because the completed cross-feature
        # task is not considered.
        scoped = _run_tasks(tmp_path, "waves", "--feature", "init-project")
        assert "FILE OVERLAP" not in scoped.stdout
        assert "New compiler test" in scoped.stdout


class TestReadyToDecompose:
    def test_should_flag_complex_tasks(self, tmp_path: Path) -> None:
        tasks_dir = tmp_path / ".etc_sdlc" / "tasks"
        _create_task(
            tasks_dir, "001", "Huge task",
            criteria=["A", "B", "C", "D", "E", "F", "G"],
            files=["src/a.py", "src/b.py", "src/c.py", "src/d.py"],
        )

        result = _run_tasks(tmp_path, "ready-to-decompose")
        assert "001" in result.stdout
        assert "/decompose" in result.stdout

    def test_should_show_nothing_when_all_small(self, tmp_path: Path) -> None:
        tasks_dir = tmp_path / ".etc_sdlc" / "tasks"
        _create_task(tasks_dir, "001", "Small", criteria=["Pass"], files=["src/a.py"])

        result = _run_tasks(tmp_path, "ready-to-decompose")
        assert "No tasks exceed" in result.stdout
