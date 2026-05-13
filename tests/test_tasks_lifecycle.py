"""Tests for tasks.py F009-lifecycle-aware feature directory resolution.

The F009 lifecycle places allocator output under
`.etc_sdlc/features/active/F<NNN>-<slug>/`. Pre-F009 features stayed at
the flat path `.etc_sdlc/features/F<NNN>-<slug>/`. Shipped features
move to `.etc_sdlc/features/shipped/F<NNN>-<slug>/`.

Before this fix, `tasks.py --feature F001-foo` only looked at the flat
path, missing features under active/. This caused the "Tasks created
but in legacy path" reconciliation symptom reported in a live build.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

TASKS_SCRIPT = Path(__file__).parent.parent / "scripts" / "tasks.py"


def _run_tasks(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python3", str(TASKS_SCRIPT), *args],
        capture_output=True, text=True, timeout=15, cwd=cwd,
    )


def _write_task_yaml(tasks_dir: Path, task_id: str, status: str = "pending") -> Path:
    tasks_dir.mkdir(parents=True, exist_ok=True)
    path = tasks_dir / f"{task_id}-test.yaml"
    path.write_text(
        f"task_id: '{task_id}'\n"
        f"title: test task {task_id}\n"
        f"status: {status}\n"
        "assigned_agent: backend-developer\n"
        "estimated_complexity: 3\n"
        "requires_reading: []\n"
        "files_in_scope: []\n"
        "acceptance_criteria: []\n"
        "dependencies: []\n",
        encoding="utf-8",
    )
    return path


class TestActiveLifecycleLookup:
    """tasks.py --feature F<NNN>-<slug> finds features under active/."""

    def test_list_finds_task_in_active_subdirectory(self, tmp_path: Path) -> None:
        feature = "F100-feature-in-active"
        tasks_dir = tmp_path / ".etc_sdlc" / "features" / "active" / feature / "tasks"
        _write_task_yaml(tasks_dir, "001")
        result = _run_tasks("list", "--feature", feature, cwd=tmp_path)
        assert result.returncode == 0
        assert "001" in result.stdout
        assert "test task 001" in result.stdout

    def test_set_status_finds_task_in_active_subdirectory(
        self, tmp_path: Path
    ) -> None:
        feature = "F101-set-status-active"
        tasks_dir = tmp_path / ".etc_sdlc" / "features" / "active" / feature / "tasks"
        task_path = _write_task_yaml(tasks_dir, "001", status="pending")
        result = _run_tasks(
            "set-status", "001", "in_progress", "--feature", feature, cwd=tmp_path,
        )
        assert result.returncode == 0
        # Verify the YAML was updated in place under active/
        content = task_path.read_text(encoding="utf-8")
        assert "in_progress" in content


class TestFlatPathLookupStillWorks:
    """The F009-lifecycle-gap fix must preserve legacy flat-path lookup."""

    def test_list_finds_task_in_flat_path(self, tmp_path: Path) -> None:
        feature = "F002-legacy-flat"
        tasks_dir = tmp_path / ".etc_sdlc" / "features" / feature / "tasks"
        _write_task_yaml(tasks_dir, "001")
        result = _run_tasks("list", "--feature", feature, cwd=tmp_path)
        assert result.returncode == 0
        assert "001" in result.stdout


class TestShippedLookup:
    """tasks.py finds shipped features for read-only operations."""

    def test_list_finds_task_in_shipped_subdirectory(self, tmp_path: Path) -> None:
        feature = "F003-shipped-feature"
        tasks_dir = tmp_path / ".etc_sdlc" / "features" / "shipped" / feature / "tasks"
        _write_task_yaml(tasks_dir, "001", status="completed")
        result = _run_tasks("list", "--feature", feature, cwd=tmp_path)
        assert result.returncode == 0
        assert "001" in result.stdout


class TestBulkCreateLifecycle:
    """bulk-create writes to wherever the feature already lives."""

    def test_bulk_create_writes_into_active_when_feature_lives_there(
        self, tmp_path: Path
    ) -> None:
        feature = "F200-bulk-into-active"
        # Pre-create the feature dir under active/ (as the allocator would)
        (tmp_path / ".etc_sdlc" / "features" / "active" / feature / "tasks").mkdir(
            parents=True
        )
        json_arr = (
            '[{"task_id":"001","title":"new task","assigned_agent":"backend-developer",'
            '"estimated_complexity":3,"requires_reading":[],'
            '"files_in_scope":["src/new.py"],"acceptance_criteria":["ac"],'
            '"dependencies":[]}]'
        )
        result = subprocess.run(
            [
                "python3", str(TASKS_SCRIPT),
                "bulk-create", "--feature", feature, "--json", json_arr,
            ],
            capture_output=True, text=True, timeout=15, cwd=tmp_path,
        )
        assert result.returncode == 0, result.stderr
        # File should land under active/, not flat
        active_path = (
            tmp_path / ".etc_sdlc" / "features" / "active" / feature / "tasks"
        )
        assert any(active_path.glob("001-*.yaml")), (
            "bulk-create should have written into active/ where the feature dir lives"
        )
        # And NOT under flat
        flat_path = tmp_path / ".etc_sdlc" / "features" / feature / "tasks"
        assert not flat_path.exists() or not any(flat_path.glob("001-*.yaml"))

    def test_bulk_create_refuses_into_shipped(self, tmp_path: Path) -> None:
        feature = "F201-cannot-modify-shipped"
        (tmp_path / ".etc_sdlc" / "features" / "shipped" / feature / "tasks").mkdir(
            parents=True
        )
        json_arr = (
            '[{"task_id":"001","title":"new task","assigned_agent":"backend-developer",'
            '"estimated_complexity":3,"requires_reading":[],'
            '"files_in_scope":["src/placeholder.py"],"acceptance_criteria":["ac"],"dependencies":[]}]'
        )
        result = subprocess.run(
            [
                "python3", str(TASKS_SCRIPT),
                "bulk-create", "--feature", feature, "--json", json_arr,
            ],
            capture_output=True, text=True, timeout=15, cwd=tmp_path,
        )
        # bulk-create should refuse to modify a shipped feature
        assert result.returncode != 0
        assert "shipped" in result.stdout.lower() or "shipped" in result.stderr.lower()

    def test_bulk_create_falls_back_to_flat_when_feature_absent(
        self, tmp_path: Path
    ) -> None:
        """If no feature dir exists anywhere, bulk-create auto-creates at
        the flat path — preserves the legacy default behavior."""
        feature = "F300-auto-flat-creation"
        json_arr = (
            '[{"task_id":"001","title":"new task","assigned_agent":"backend-developer",'
            '"estimated_complexity":3,"requires_reading":[],'
            '"files_in_scope":["src/placeholder.py"],"acceptance_criteria":["ac"],"dependencies":[]}]'
        )
        result = subprocess.run(
            [
                "python3", str(TASKS_SCRIPT),
                "bulk-create", "--feature", feature, "--json", json_arr,
            ],
            capture_output=True, text=True, timeout=15, cwd=tmp_path,
        )
        assert result.returncode == 0, result.stderr
        flat_path = tmp_path / ".etc_sdlc" / "features" / feature / "tasks"
        assert any(flat_path.glob("001-*.yaml")), (
            "bulk-create should fall back to flat path when no active/shipped exists"
        )


class TestNoFeatureFilterIteratesAll:
    """`tasks.py list` (no --feature) walks active/ + flat + shipped/."""

    def test_list_no_filter_picks_up_active_features(self, tmp_path: Path) -> None:
        _write_task_yaml(
            tmp_path / ".etc_sdlc" / "features" / "active" / "F500-active" / "tasks",
            "001",
        )
        _write_task_yaml(
            tmp_path / ".etc_sdlc" / "features" / "F501-flat" / "tasks",
            "002",
        )
        result = _run_tasks("list", cwd=tmp_path)
        assert result.returncode == 0
        assert "001" in result.stdout
        assert "002" in result.stdout
