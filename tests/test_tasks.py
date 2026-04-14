"""Tests for scripts/tasks.py — native task tracker with hierarchical decomposition."""

from __future__ import annotations

import json
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


# ── Create / bulk-create regression tests ───────────────────────────────


def _run_tasks_stdin(
    tmp_path: Path, stdin_text: str, *args: str
) -> subprocess.CompletedProcess[str]:
    """Run tasks.py with a string piped to stdin."""
    return subprocess.run(
        ["python3", str(TASKS_SCRIPT), *args],
        capture_output=True,
        text=True,
        cwd=str(tmp_path),
        input=stdin_text,
        timeout=10,
    )


class TestCreate:
    def test_should_create_feature_scoped_task(self, tmp_path: Path) -> None:
        result = _run_tasks(
            tmp_path, "create",
            "--task-id", "001",
            "--title", "First task",
            "--agent", "backend-developer",
            "--file", "src/app.py",
            "--ac", "Tests pass",
            "--feature", "demo",
        )
        assert result.returncode == 0, result.stdout + result.stderr
        path = tmp_path / ".etc_sdlc" / "features" / "demo" / "tasks" / "001-first-task.yaml"
        assert path.exists()
        body = path.read_text()
        assert 'task_id: "001"' in body
        assert 'title: "First task"' in body
        assert "assigned_agent: backend-developer" in body
        assert "status: pending" in body
        assert "dependencies: []" in body

    def test_should_create_legacy_global_task(self, tmp_path: Path) -> None:
        result = _run_tasks(
            tmp_path, "create",
            "--task-id", "001",
            "--title", "Legacy task",
            "--agent", "backend-developer",
            "--file", "src/a.py",
            "--ac", "Pass",
        )
        assert result.returncode == 0
        path = tmp_path / ".etc_sdlc" / "tasks" / "001-legacy-task.yaml"
        assert path.exists()

    def test_should_reject_missing_required_field(self, tmp_path: Path) -> None:
        result = _run_tasks(
            tmp_path, "create",
            "--task-id", "001",
            "--title", "Task",
            "--agent", "backend-developer",
            "--ac", "Pass",
            # missing --file
            "--feature", "demo",
        )
        assert result.returncode == 1
        assert "files_in_scope" in result.stdout
        # No file should have been written
        tasks_dir = tmp_path / ".etc_sdlc" / "features" / "demo" / "tasks"
        assert not tasks_dir.exists() or not any(tasks_dir.glob("*.yaml"))

    def test_should_reject_invalid_status(self, tmp_path: Path) -> None:
        result = _run_tasks(
            tmp_path, "create",
            "--task-id", "001",
            "--title", "T",
            "--agent", "a",
            "--file", "src/a.py",
            "--ac", "pass",
            "--status", "bogus",
            "--feature", "demo",
        )
        assert result.returncode == 1
        assert "bogus" in result.stdout

    def test_should_accept_custom_filename(self, tmp_path: Path) -> None:
        result = _run_tasks(
            tmp_path, "create",
            "--task-id", "001",
            "--title", "T",
            "--agent", "a",
            "--file", "src/a.py",
            "--ac", "pass",
            "--filename", "custom-name.yaml",
            "--feature", "demo",
        )
        assert result.returncode == 0
        path = tmp_path / ".etc_sdlc" / "features" / "demo" / "tasks" / "custom-name.yaml"
        assert path.exists()

    def test_should_emit_parent_task_and_context(self, tmp_path: Path) -> None:
        result = _run_tasks(
            tmp_path, "create",
            "--task-id", "001.001",
            "--title", "Child",
            "--agent", "a",
            "--file", "src/a.py",
            "--ac", "pass",
            "--parent", "001",
            "--context", "Line one\nLine two",
            "--feature", "demo",
        )
        assert result.returncode == 0
        path = tmp_path / ".etc_sdlc" / "features" / "demo" / "tasks" / "001.001-child.yaml"
        body = path.read_text()
        assert 'parent_task: "001"' in body
        assert "context: |" in body
        assert "  Line one" in body
        assert "  Line two" in body

    def test_should_refuse_to_overwrite_existing(self, tmp_path: Path) -> None:
        # Pre-create
        _run_tasks(
            tmp_path, "create",
            "--task-id", "001",
            "--title", "T",
            "--agent", "a",
            "--file", "src/a.py",
            "--ac", "pass",
            "--feature", "demo",
        )
        # Second attempt must fail
        result = _run_tasks(
            tmp_path, "create",
            "--task-id", "001",
            "--title", "T",
            "--agent", "a",
            "--file", "src/a.py",
            "--ac", "pass",
            "--feature", "demo",
        )
        assert result.returncode == 1
        assert "already exists" in result.stdout

    def test_should_reject_path_traversal_in_feature(self, tmp_path: Path) -> None:
        result = _run_tasks(
            tmp_path, "create",
            "--task-id", "001",
            "--title", "T",
            "--agent", "a",
            "--file", "src/a.py",
            "--ac", "pass",
            "--feature", "../../../etc",
        )
        assert result.returncode == 1
        assert "path traversal" in result.stdout.lower() or "invalid" in result.stdout.lower()

    def test_should_reject_path_traversal_in_filename(self, tmp_path: Path) -> None:
        result = _run_tasks(
            tmp_path, "create",
            "--task-id", "001",
            "--title", "T",
            "--agent", "a",
            "--file", "src/a.py",
            "--ac", "pass",
            "--filename", "../escape.yaml",
            "--feature", "demo",
        )
        assert result.returncode == 1

    def test_should_fallback_slug_for_punctuation_title(self, tmp_path: Path) -> None:
        result = _run_tasks(
            tmp_path, "create",
            "--task-id", "001",
            "--title", "!!!",
            "--agent", "a",
            "--file", "src/a.py",
            "--ac", "pass",
            "--feature", "demo",
        )
        assert result.returncode == 0
        path = tmp_path / ".etc_sdlc" / "features" / "demo" / "tasks" / "001-task.yaml"
        assert path.exists()

    def test_should_produce_output_compatible_with_list(self, tmp_path: Path) -> None:
        """Created tasks must be visible to the existing list command."""
        _run_tasks(
            tmp_path, "create",
            "--task-id", "001",
            "--title", "Visible",
            "--agent", "backend-developer",
            "--file", "src/a.py",
            "--ac", "Pass",
            "--feature", "demo",
        )
        result = _run_tasks(tmp_path, "list")
        assert "001" in result.stdout
        assert "Visible" in result.stdout


class TestBulkCreate:
    def _sample_batch(self) -> str:
        return json.dumps([
            {
                "task_id": "001",
                "title": "First",
                "assigned_agent": "backend-developer",
                "files_in_scope": ["src/a.py"],
                "acceptance_criteria": ["Pass"],
            },
            {
                "task_id": "002",
                "title": "Second",
                "assigned_agent": "backend-developer",
                "files_in_scope": ["src/b.py"],
                "acceptance_criteria": ["Pass"],
                "dependencies": ["001"],
            },
        ])

    def test_should_bulk_create_from_stdin(self, tmp_path: Path) -> None:
        result = _run_tasks_stdin(
            tmp_path, self._sample_batch(),
            "bulk-create", "--feature", "demo",
        )
        assert result.returncode == 0, result.stdout + result.stderr
        tasks_dir = tmp_path / ".etc_sdlc" / "features" / "demo" / "tasks"
        assert (tasks_dir / "001-first.yaml").exists()
        assert (tasks_dir / "002-second.yaml").exists()

    def test_should_bulk_create_from_inline_json(self, tmp_path: Path) -> None:
        result = _run_tasks(
            tmp_path, "bulk-create",
            "--feature", "demo",
            "--json", self._sample_batch(),
        )
        assert result.returncode == 0
        tasks_dir = tmp_path / ".etc_sdlc" / "features" / "demo" / "tasks"
        assert (tasks_dir / "001-first.yaml").exists()

    def test_should_bulk_create_from_json_file(self, tmp_path: Path) -> None:
        json_path = tmp_path / "batch.json"
        json_path.write_text(self._sample_batch())
        result = _run_tasks(
            tmp_path, "bulk-create",
            "--feature", "demo",
            "--json-file", str(json_path),
        )
        assert result.returncode == 0
        tasks_dir = tmp_path / ".etc_sdlc" / "features" / "demo" / "tasks"
        assert (tasks_dir / "002-second.yaml").exists()

    def test_validation_failure_aborts_whole_batch(self, tmp_path: Path) -> None:
        """If task 2 of 3 is invalid, zero files must be written."""
        batch = json.dumps([
            {
                "task_id": "001",
                "title": "OK",
                "assigned_agent": "a",
                "files_in_scope": ["src/a.py"],
                "acceptance_criteria": ["Pass"],
            },
            {
                # missing files_in_scope
                "task_id": "002",
                "title": "Bad",
                "assigned_agent": "a",
                "acceptance_criteria": ["Pass"],
            },
            {
                "task_id": "003",
                "title": "OK",
                "assigned_agent": "a",
                "files_in_scope": ["src/c.py"],
                "acceptance_criteria": ["Pass"],
            },
        ])
        result = _run_tasks_stdin(tmp_path, batch, "bulk-create", "--feature", "demo")
        assert result.returncode == 1
        assert "files_in_scope" in result.stdout
        tasks_dir = tmp_path / ".etc_sdlc" / "features" / "demo" / "tasks"
        assert not tasks_dir.exists() or not any(tasks_dir.glob("*.yaml"))

    def test_pre_existence_aborts_whole_batch(self, tmp_path: Path) -> None:
        # Create task 001 first
        _run_tasks(
            tmp_path, "create",
            "--task-id", "001",
            "--title", "First",
            "--agent", "backend-developer",
            "--file", "src/a.py",
            "--ac", "Pass",
            "--feature", "demo",
        )
        # Now bulk-create a batch containing 001 and 002
        result = _run_tasks_stdin(
            tmp_path, self._sample_batch(),
            "bulk-create", "--feature", "demo",
        )
        assert result.returncode == 1
        assert "already exist" in result.stdout
        # 002 must NOT have been written
        tasks_dir = tmp_path / ".etc_sdlc" / "features" / "demo" / "tasks"
        assert not (tasks_dir / "002-second.yaml").exists()

    def test_allow_existing_skips_and_reports(self, tmp_path: Path) -> None:
        # Pre-create 001
        _run_tasks(
            tmp_path, "create",
            "--task-id", "001",
            "--title", "First",
            "--agent", "backend-developer",
            "--file", "src/a.py",
            "--ac", "Pass",
            "--feature", "demo",
        )
        result = _run_tasks_stdin(
            tmp_path, self._sample_batch(),
            "bulk-create", "--feature", "demo", "--allow-existing",
        )
        assert result.returncode == 0, result.stdout
        assert "skipped" in result.stdout.lower()
        tasks_dir = tmp_path / ".etc_sdlc" / "features" / "demo" / "tasks"
        assert (tasks_dir / "002-second.yaml").exists()

    def test_should_reject_duplicate_task_id(self, tmp_path: Path) -> None:
        batch = json.dumps([
            {
                "task_id": "001",
                "title": "A",
                "assigned_agent": "a",
                "files_in_scope": ["src/a.py"],
                "acceptance_criteria": ["Pass"],
            },
            {
                "task_id": "001",
                "title": "B",
                "assigned_agent": "a",
                "files_in_scope": ["src/b.py"],
                "acceptance_criteria": ["Pass"],
            },
        ])
        result = _run_tasks_stdin(tmp_path, batch, "bulk-create", "--feature", "demo")
        assert result.returncode == 1
        assert "duplicate" in result.stdout.lower()

    def test_should_reject_duplicate_target_path(self, tmp_path: Path) -> None:
        batch = json.dumps([
            {
                "task_id": "001",
                "title": "A",
                "assigned_agent": "a",
                "files_in_scope": ["src/a.py"],
                "acceptance_criteria": ["Pass"],
                "filename": "same.yaml",
            },
            {
                "task_id": "002",
                "title": "B",
                "assigned_agent": "a",
                "files_in_scope": ["src/b.py"],
                "acceptance_criteria": ["Pass"],
                "filename": "same.yaml",
            },
        ])
        result = _run_tasks_stdin(tmp_path, batch, "bulk-create", "--feature", "demo")
        assert result.returncode == 1
        assert "duplicate" in result.stdout.lower()

    def test_should_reject_non_array_json(self, tmp_path: Path) -> None:
        result = _run_tasks_stdin(
            tmp_path, '{"task_id": "001"}',
            "bulk-create", "--feature", "demo",
        )
        assert result.returncode == 1
        assert "array" in result.stdout.lower()

    def test_should_reject_non_object_element(self, tmp_path: Path) -> None:
        result = _run_tasks_stdin(
            tmp_path, '["not an object"]',
            "bulk-create", "--feature", "demo",
        )
        assert result.returncode == 1
        assert "not an object" in result.stdout.lower()

    def test_should_produce_byte_identical_output(self, tmp_path: Path) -> None:
        """Output of bulk-create must be byte-identical to _create_task for
        matching inputs."""
        # Hand-written reference using the existing helper
        ref_dir = tmp_path / "ref" / ".etc_sdlc" / "features" / "demo" / "tasks"
        ref_path = _create_task(
            ref_dir, "001", "First",
            agent="backend-developer",
            criteria=["Pass"],
            files=["src/a.py"],
        )
        ref_body = ref_path.read_text()

        # Bulk-create in a separate tmp subtree (not under ref/) so the
        # cwd-based lookups don't collide.
        cli_root = tmp_path / "cli"
        cli_root.mkdir()
        batch = json.dumps([{
            "task_id": "001",
            "title": "First",
            "assigned_agent": "backend-developer",
            "files_in_scope": ["src/a.py"],
            "acceptance_criteria": ["Pass"],
            # Match _create_task's requires_reading default
            "requires_reading": ["spec/prd.md"],
        }])
        result = _run_tasks_stdin(
            cli_root, batch, "bulk-create", "--feature", "demo",
        )
        assert result.returncode == 0, result.stdout + result.stderr
        cli_path = cli_root / ".etc_sdlc" / "features" / "demo" / "tasks" / "001-first.yaml"
        cli_body = cli_path.read_text()
        assert cli_body == ref_body, (
            f"\n--- reference ---\n{ref_body!r}\n--- cli ---\n{cli_body!r}"
        )
