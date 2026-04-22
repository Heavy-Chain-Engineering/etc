"""Tests for hooks/check-completion-discipline.sh.

The hook enforces `standards/process/completion-discipline.md` via
system-state inspection. It blocks Stop events when either of two
signals indicates unfinished work:

  1. `.tdd-dirty` marker is present
  2. Any task in `.etc_sdlc/features/*/tasks/*.yaml` has
     `status: in_progress`

Language of the agent's final message is deliberately NOT checked.
The hook must work purely on filesystem state.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

HOOK_NAME = "check-completion-discipline.sh"


def _build_input(cwd: Path) -> dict[str, Any]:
    """Build the JSON input structure expected by a Stop hook."""
    return {"cwd": str(cwd)}


class TestNoSignals:
    """When no unfinished-work signals are present, the hook allows stop."""

    def test_should_allow_stop_when_no_dirty_marker_and_no_tasks(
        self, run_hook: Any, tmp_path: Path
    ) -> None:
        result = run_hook(HOOK_NAME, _build_input(tmp_path))
        assert result.exit_code == 0
        assert result.stderr == ""

    def test_should_allow_stop_when_empty_etc_sdlc_directory(
        self, run_hook: Any, tmp_path: Path
    ) -> None:
        (tmp_path / ".etc_sdlc" / "features").mkdir(parents=True)
        result = run_hook(HOOK_NAME, _build_input(tmp_path))
        assert result.exit_code == 0

    def test_should_allow_stop_when_tasks_all_completed(
        self, run_hook: Any, tmp_path: Path
    ) -> None:
        tasks_dir = tmp_path / ".etc_sdlc" / "features" / "sample" / "tasks"
        tasks_dir.mkdir(parents=True)
        (tasks_dir / "001.yaml").write_text("task_id: '001'\nstatus: completed\n")
        (tasks_dir / "002.yaml").write_text("task_id: '002'\nstatus: completed\n")
        result = run_hook(HOOK_NAME, _build_input(tmp_path))
        assert result.exit_code == 0

    def test_should_allow_stop_when_cwd_missing(
        self, run_hook: Any
    ) -> None:
        """If cwd is not provided, the hook cannot evaluate state — allow."""
        result = run_hook(HOOK_NAME, {})
        assert result.exit_code == 0


class TestDirtyMarkerTriggersCI:
    """When .tdd-dirty is present, the hook runs CI inline before
    deciding. If CI passes (or vacuously passes because tests/
    pyproject aren't set up in the tmp dir), the marker is cleared
    and the hook allows the stop. If CI fails, the hook blocks.

    This replaces the prior peer-hooks race between ci-gate.sh and
    check-completion-discipline.sh. Now both responsibilities live
    in this single hook and run sequentially.
    """

    def test_should_clear_marker_and_allow_when_ci_vacuously_passes(
        self, run_hook: Any, tmp_path: Path
    ) -> None:
        """In a tmp dir with no tests/ or pyproject.toml, every CI
        step is skipped, so CI passes vacuously and the marker clears.
        """
        (tmp_path / ".tdd-dirty").write_text("")
        result = run_hook(HOOK_NAME, _build_input(tmp_path))
        assert result.exit_code == 0
        assert not (tmp_path / ".tdd-dirty").exists(), (
            "Marker must be cleared after successful CI run"
        )

    def test_should_block_when_pytest_fails(
        self, run_hook: Any, tmp_path: Path
    ) -> None:
        """If tests/ exists and pytest fails, the hook blocks with
        exit 1 (CI failure) and the marker remains set.
        """
        (tmp_path / ".tdd-dirty").write_text("")
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_failing.py").write_text(
            "def test_must_fail():\n    assert False\n"
        )
        result = run_hook(HOOK_NAME, _build_input(tmp_path))
        assert result.exit_code == 1
        assert "CI GATE FAILED" in result.stderr
        assert (tmp_path / ".tdd-dirty").exists(), (
            "Marker must remain when CI fails"
        )

    def test_should_clear_marker_when_passing_tests_exist(
        self, run_hook: Any, tmp_path: Path
    ) -> None:
        (tmp_path / ".tdd-dirty").write_text("")
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_passing.py").write_text(
            "def test_must_pass():\n    assert True\n"
        )
        result = run_hook(HOOK_NAME, _build_input(tmp_path))
        assert result.exit_code == 0
        assert not (tmp_path / ".tdd-dirty").exists()


class TestInProgressTasksBlock:
    """When any task has status: in_progress, the hook blocks stop."""

    def test_should_block_when_one_task_in_progress(
        self, run_hook: Any, tmp_path: Path
    ) -> None:
        tasks_dir = tmp_path / ".etc_sdlc" / "features" / "sample" / "tasks"
        tasks_dir.mkdir(parents=True)
        (tasks_dir / "001.yaml").write_text(
            "task_id: '001'\ntitle: Something\nstatus: in_progress\n"
        )
        result = run_hook(HOOK_NAME, _build_input(tmp_path))
        assert result.exit_code == 2

    def test_should_count_multiple_in_progress_tasks(
        self, run_hook: Any, tmp_path: Path
    ) -> None:
        tasks_dir = tmp_path / ".etc_sdlc" / "features" / "sample" / "tasks"
        tasks_dir.mkdir(parents=True)
        (tasks_dir / "001.yaml").write_text("task_id: '001'\nstatus: in_progress\n")
        (tasks_dir / "002.yaml").write_text("task_id: '002'\nstatus: in_progress\n")
        (tasks_dir / "003.yaml").write_text("task_id: '003'\nstatus: completed\n")
        result = run_hook(HOOK_NAME, _build_input(tmp_path))
        assert result.exit_code == 2
        assert "2 task" in result.stderr

    def test_should_block_on_in_progress_across_multiple_features(
        self, run_hook: Any, tmp_path: Path
    ) -> None:
        for feature_slug in ("auth", "billing"):
            tasks_dir = tmp_path / ".etc_sdlc" / "features" / feature_slug / "tasks"
            tasks_dir.mkdir(parents=True)
            (tasks_dir / "001.yaml").write_text(
                "task_id: '001'\nstatus: in_progress\n"
            )
        result = run_hook(HOOK_NAME, _build_input(tmp_path))
        assert result.exit_code == 2
        assert "2 task" in result.stderr

    def test_should_mention_completion_discipline_standard(
        self, run_hook: Any, tmp_path: Path
    ) -> None:
        tasks_dir = tmp_path / ".etc_sdlc" / "features" / "sample" / "tasks"
        tasks_dir.mkdir(parents=True)
        (tasks_dir / "001.yaml").write_text("task_id: '001'\nstatus: in_progress\n")
        result = run_hook(HOOK_NAME, _build_input(tmp_path))
        assert "completion-discipline.md" in result.stderr

    def test_should_list_three_valid_exit_paths(
        self, run_hook: Any, tmp_path: Path
    ) -> None:
        """Rule 5 in the standard: exactly three valid exits."""
        tasks_dir = tmp_path / ".etc_sdlc" / "features" / "sample" / "tasks"
        tasks_dir.mkdir(parents=True)
        (tasks_dir / "001.yaml").write_text("task_id: '001'\nstatus: in_progress\n")
        result = run_hook(HOOK_NAME, _build_input(tmp_path))
        assert "Complete the work" in result.stderr
        assert "escalate" in result.stderr.lower()
        assert "blocked" in result.stderr.lower()


class TestSequencing:
    """Step 1 (CI gate) runs before Step 2 (in_progress check).
    Behavior depends on which step fails first.
    """

    def test_ci_failure_blocks_before_task_check_runs(
        self, run_hook: Any, tmp_path: Path
    ) -> None:
        """If CI fails, the hook exits 1 without reaching the task
        check — the user sees CI output, not task output.
        """
        (tmp_path / ".tdd-dirty").write_text("")
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_failing.py").write_text(
            "def test_must_fail():\n    assert False\n"
        )
        # Also set an in_progress task; it should NOT be reported
        # because CI failure short-circuits at step 1.
        tasks_dir = tmp_path / ".etc_sdlc" / "features" / "sample" / "tasks"
        tasks_dir.mkdir(parents=True)
        (tasks_dir / "001.yaml").write_text("task_id: '001'\nstatus: in_progress\n")

        result = run_hook(HOOK_NAME, _build_input(tmp_path))
        assert result.exit_code == 1
        assert "CI GATE FAILED" in result.stderr
        # Step 2 message should NOT appear — we short-circuited.
        assert "COMPLETION DISCIPLINE" not in result.stderr

    def test_ci_pass_then_task_block_sequences_correctly(
        self, run_hook: Any, tmp_path: Path
    ) -> None:
        """If CI passes (clearing marker), in_progress task then blocks
        with the completion-discipline message.
        """
        (tmp_path / ".tdd-dirty").write_text("")
        tasks_dir = tmp_path / ".etc_sdlc" / "features" / "sample" / "tasks"
        tasks_dir.mkdir(parents=True)
        (tasks_dir / "001.yaml").write_text("task_id: '001'\nstatus: in_progress\n")

        result = run_hook(HOOK_NAME, _build_input(tmp_path))
        assert result.exit_code == 2
        assert "COMPLETION DISCIPLINE" in result.stderr
        assert "in_progress" in result.stderr
        # Marker was cleared during step 1
        assert not (tmp_path / ".tdd-dirty").exists()


class TestLanguageAgnostic:
    """The hook must not care about the language of the agent's message."""

    def test_should_not_receive_or_check_message_content(
        self, run_hook: Any, tmp_path: Path
    ) -> None:
        """Stop hooks don't take a user message; the hook operates on
        state only. Passing extra fields in the input should be ignored.
        """
        payload = _build_input(tmp_path)
        # Add message-like content the hook should NOT care about.
        payload["last_message"] = "let's call it quits, we've done enough"
        payload["continue"] = False
        result = run_hook(HOOK_NAME, payload)
        # No signals → allow. Language is irrelevant.
        assert result.exit_code == 0

    def test_should_block_regardless_of_message_content(
        self, run_hook: Any, tmp_path: Path
    ) -> None:
        """Even if the agent's message sounds like a normal wrap-up,
        unfinished-work signals still block. The hook's job is to be
        language-agnostic.
        """
        # Use an in_progress task to trigger the block unconditionally.
        # (.tdd-dirty alone would run CI and potentially clear itself.)
        tasks_dir = tmp_path / ".etc_sdlc" / "features" / "sample" / "tasks"
        tasks_dir.mkdir(parents=True)
        (tasks_dir / "001.yaml").write_text("task_id: '001'\nstatus: in_progress\n")
        payload = _build_input(tmp_path)
        payload["last_message"] = "Great work today, all tests passing!"
        result = run_hook(HOOK_NAME, payload)
        assert result.exit_code == 2
