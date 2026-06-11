"""Tests for shared test fixtures in conftest.py."""

import json
from pathlib import Path
from types import ModuleType
from typing import Any

from tests.conftest import load_script_module

REPO_ROOT = Path(__file__).resolve().parent.parent


class TestRunHook:
    """Tests for the run_hook fixture."""

    def test_should_return_hook_result_with_exit_code_when_hook_executes(
        self, run_hook: Any
    ) -> None:
        # Arrange — block-dangerous-commands with a safe command
        hook_input = {
            "tool_name": "Bash",
            "tool_input": {"command": "echo hello"},
        }

        # Act
        result = run_hook("block-dangerous-commands.sh", hook_input)

        # Assert
        assert result.exit_code == 0
        assert isinstance(result.stdout, str)
        assert isinstance(result.stderr, str)

    def test_should_return_exit_code_2_when_hook_blocks_command(
        self, run_hook: Any
    ) -> None:
        # Arrange — block-dangerous-commands with rm -rf
        hook_input = {
            "tool_name": "Bash",
            "tool_input": {"command": "rm -rf /"},
        }

        # Act
        result = run_hook("block-dangerous-commands.sh", hook_input)

        # Assert
        assert result.exit_code == 2
        assert "BLOCKED" in result.stderr


class TestCompiledDist:
    """Tests for the shared compiled_dist fixture.

    The fixture compiles spec/etc_sdlc.yaml once per session into a tmp
    directory so tests never read or mutate the operator's real dist/.
    """

    def test_should_yield_existing_directory_when_invoked(
        self, compiled_dist: Path
    ) -> None:
        # Assert
        assert compiled_dist.is_dir()

    def test_should_emit_expected_artifacts_when_compiled(
        self, compiled_dist: Path
    ) -> None:
        # Assert — the compiler wrote the canonical tree into the tmp dist
        assert (compiled_dist / "settings-hooks.json").is_file()
        assert (compiled_dist / "agents" / "sem.md").is_file()
        assert (compiled_dist / "skills" / "implement" / "SKILL.md").is_file()

    def test_should_not_be_the_repo_dist_when_invoked(
        self, compiled_dist: Path
    ) -> None:
        # Assert — hermeticity: the fixture's dist is NOT the operator's real
        # dist/, so a suite run never mutates REPO_ROOT/dist.
        assert compiled_dist != REPO_ROOT / "dist"
        assert REPO_ROOT not in compiled_dist.parents


class TestLoadScriptModule:
    """Tests for the shared load_script_module helper."""

    def test_should_return_module_when_script_exists(self) -> None:
        # Act
        module = load_script_module("review_gate")

        # Assert
        assert isinstance(module, ModuleType)
        assert hasattr(module, "main")

    def test_should_register_module_in_sys_modules_when_loaded(self) -> None:
        # Arrange
        import sys

        # Act
        load_script_module("cross_feature_collision_check")

        # Assert
        assert "cross_feature_collision_check" in sys.modules

    def test_should_raise_when_script_missing(self) -> None:
        # Act / Assert
        import pytest

        with pytest.raises(FileNotFoundError):
            load_script_module("definitely_not_a_real_script_xyz")


class TestTmpProject:
    """Tests for the tmp_project fixture."""

    def test_should_create_directory_with_standard_subdirs_when_invoked(
        self, tmp_project: Path
    ) -> None:
        # Assert
        assert tmp_project.is_dir()
        assert (tmp_project / "src").is_dir()
        assert (tmp_project / "tests").is_dir()
        assert (tmp_project / ".etc_sdlc" / "tasks").is_dir()


class TestTaskFile:
    """Tests for the task_file factory fixture."""

    def test_should_create_yaml_task_file_when_called_with_defaults(
        self, task_file: Any, tmp_project: Path
    ) -> None:
        # Act
        path = task_file(task_id="001", title="Test task")

        # Assert
        assert path.exists()
        assert path.suffix == ".yaml"
        content = path.read_text()
        assert "001" in content
        assert "Test task" in content
        assert "status:" in content

    def test_should_include_requires_reading_when_specified(
        self, task_file: Any, tmp_project: Path
    ) -> None:
        # Arrange
        reading_list = ["spec/design.md", "docs/api.md"]

        # Act
        path = task_file(
            task_id="002",
            title="Read task",
            requires_reading=reading_list,
        )

        # Assert
        content = path.read_text()
        assert "spec/design.md" in content
        assert "docs/api.md" in content

    def test_should_include_files_in_scope_when_specified(
        self, task_file: Any, tmp_project: Path
    ) -> None:
        # Act
        path = task_file(
            task_id="003",
            title="Scoped task",
            files_in_scope=["src/app.py", "tests/test_app.py"],
        )

        # Assert
        content = path.read_text()
        assert "src/app.py" in content
        assert "tests/test_app.py" in content


class TestTranscriptFile:
    """Tests for the transcript_file factory fixture."""

    def test_should_create_jsonl_file_when_called_with_tool_entries(
        self, transcript_file: Any, tmp_project: Path
    ) -> None:
        # Arrange
        entries = [
            ("Read", "spec/design.md"),
            ("Read", "docs/api.md"),
        ]

        # Act
        path = transcript_file(entries)

        # Assert
        assert path.exists()
        lines = path.read_text().strip().split("\n")
        assert len(lines) == 2
        first_line = json.loads(lines[0])
        assert first_line["tool_name"] == "Read"
        assert first_line["file_path"] == "spec/design.md"


class TestInvariantsFile:
    """Tests for the invariants_file factory fixture."""

    def test_should_create_invariants_md_when_called_with_entries(
        self, invariants_file: Any, tmp_project: Path
    ) -> None:
        # Arrange
        entries = [
            {
                "id": "INV-001",
                "description": "No TODO comments",
                "verify": "grep -r 'TODO' src/ || true",
            },
        ]

        # Act
        path = invariants_file(entries)

        # Assert
        assert path.exists()
        content = path.read_text()
        assert "INV-001" in content
        assert "No TODO comments" in content
        assert "grep -r 'TODO' src/ || true" in content

    def test_should_create_multiple_invariant_entries_when_given_list(
        self, invariants_file: Any, tmp_project: Path
    ) -> None:
        # Arrange
        entries = [
            {
                "id": "INV-001",
                "description": "First invariant",
                "verify": "echo ok",
            },
            {
                "id": "INV-002",
                "description": "Second invariant",
                "verify": "echo ok2",
            },
        ]

        # Act
        path = invariants_file(entries)

        # Assert
        content = path.read_text()
        assert "INV-001" in content
        assert "INV-002" in content
        assert "First invariant" in content
        assert "Second invariant" in content
