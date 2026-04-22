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


class TestDirtyMarkerBlocks:
    """When .tdd-dirty is present, the hook blocks stop."""

    def test_should_block_when_tdd_dirty_present(
        self, run_hook: Any, tmp_path: Path
    ) -> None:
        (tmp_path / ".tdd-dirty").write_text("")
        result = run_hook(HOOK_NAME, _build_input(tmp_path))
        assert result.exit_code == 2

    def test_should_mention_dirty_marker_in_stderr(
        self, run_hook: Any, tmp_path: Path
    ) -> None:
        (tmp_path / ".tdd-dirty").write_text("")
        result = run_hook(HOOK_NAME, _build_input(tmp_path))
        assert ".tdd-dirty" in result.stderr

    def test_should_mention_completion_discipline_standard(
        self, run_hook: Any, tmp_path: Path
    ) -> None:
        (tmp_path / ".tdd-dirty").write_text("")
        result = run_hook(HOOK_NAME, _build_input(tmp_path))
        assert "completion-discipline.md" in result.stderr

    def test_should_list_three_valid_exit_paths(
        self, run_hook: Any, tmp_path: Path
    ) -> None:
        """Rule 5 in the standard: exactly three valid exits."""
        (tmp_path / ".tdd-dirty").write_text("")
        result = run_hook(HOOK_NAME, _build_input(tmp_path))
        # Must reference all three: complete / escalate / block
        assert "Complete the work" in result.stderr
        assert "escalate" in result.stderr.lower()
        assert "blocked" in result.stderr.lower()


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


class TestBothSignals:
    """Both signals firing should produce one block with both messages."""

    def test_should_block_and_mention_both_signals(
        self, run_hook: Any, tmp_path: Path
    ) -> None:
        (tmp_path / ".tdd-dirty").write_text("")
        tasks_dir = tmp_path / ".etc_sdlc" / "features" / "sample" / "tasks"
        tasks_dir.mkdir(parents=True)
        (tasks_dir / "001.yaml").write_text("task_id: '001'\nstatus: in_progress\n")

        result = run_hook(HOOK_NAME, _build_input(tmp_path))
        assert result.exit_code == 2
        assert ".tdd-dirty" in result.stderr
        assert "in_progress" in result.stderr


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
        (tmp_path / ".tdd-dirty").write_text("")
        payload = _build_input(tmp_path)
        payload["last_message"] = "Great work today, all tests passing!"
        result = run_hook(HOOK_NAME, payload)
        assert result.exit_code == 2
