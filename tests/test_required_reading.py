"""Tests for hooks/check-required-reading.sh — the required reading gate.

Verifies that the hook blocks edits to files in a task's scope when the agent
has not read the required files listed in the active task, and allows edits
in all other cases (no task dir, no active task, file not in scope, all
required files read).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


HOOK_NAME = "check-required-reading.sh"


def _build_input(
    file_path: str,
    cwd: str,
    transcript_path: str,
) -> dict[str, Any]:
    """Build the JSON input structure expected by the hook."""
    return {
        "tool_input": {"file_path": file_path},
        "cwd": cwd,
        "transcript_path": transcript_path,
    }


def test_should_allow_when_no_task_dir(
    run_hook: Any,
    tmp_path: Path,
) -> None:
    """No .etc_sdlc/tasks/ directory exists -- hook should allow."""
    # Arrange
    transcript_path = tmp_path / "transcript.jsonl"
    transcript_path.write_text("")
    file_path = str(tmp_path / "src" / "handler.py")
    hook_input = _build_input(file_path, str(tmp_path), str(transcript_path))

    # Act
    result = run_hook(HOOK_NAME, hook_input)

    # Assert
    assert result.exit_code == 0


def test_should_allow_when_no_active_task(
    run_hook: Any,
    tmp_project: Path,
    task_file: Any,
    transcript_file: Any,
) -> None:
    """Tasks exist but none has status: in_progress -- hook should allow."""
    # Arrange
    task_file(
        task_id="001",
        title="Some task",
        status="pending",
        requires_reading=["spec/design.md"],
        files_in_scope=["src/"],
    )
    transcript = transcript_file([])
    file_path = str(tmp_project / "src" / "handler.py")
    hook_input = _build_input(file_path, str(tmp_project), str(transcript))

    # Act
    result = run_hook(HOOK_NAME, hook_input)

    # Assert
    assert result.exit_code == 0


def test_should_allow_when_file_not_in_scope(
    run_hook: Any,
    tmp_project: Path,
    task_file: Any,
    transcript_file: Any,
) -> None:
    """Editing a file NOT in the task's files_in_scope -- hook should allow."""
    # Arrange
    task_file(
        task_id="002",
        title="Scoped task",
        status="in_progress",
        requires_reading=["spec/design.md"],
        files_in_scope=["src/api/"],
    )
    transcript = transcript_file([])
    file_path = str(tmp_project / "docs" / "notes.md")
    hook_input = _build_input(file_path, str(tmp_project), str(transcript))

    # Act
    result = run_hook(HOOK_NAME, hook_input)

    # Assert
    assert result.exit_code == 0


def test_should_block_when_required_files_not_read(
    run_hook: Any,
    tmp_project: Path,
    task_file: Any,
    transcript_file: Any,
) -> None:
    """Task requires reading spec/design.md but transcript has no Read calls."""
    # Arrange
    task_file(
        task_id="003",
        title="Reading task",
        status="in_progress",
        requires_reading=["spec/design.md"],
        files_in_scope=["src/"],
    )
    transcript = transcript_file([])
    file_path = str(tmp_project / "src" / "handler.py")
    hook_input = _build_input(file_path, str(tmp_project), str(transcript))

    # Act
    result = run_hook(HOOK_NAME, hook_input)

    # Assert
    assert result.exit_code == 2
    assert "spec/design.md" in result.stderr
    assert "BLOCKED" in result.stderr


def test_should_allow_when_required_files_read(
    run_hook: Any,
    tmp_project: Path,
    task_file: Any,
    transcript_file: Any,
) -> None:
    """Transcript has Read calls for all required files -- hook should allow."""
    # Arrange
    task_file(
        task_id="004",
        title="Fully read task",
        status="in_progress",
        requires_reading=["spec/design.md", "spec/adr-001.md"],
        files_in_scope=["src/"],
    )
    transcript = transcript_file([
        ("Read", "spec/design.md"),
        ("Read", "spec/adr-001.md"),
    ])
    file_path = str(tmp_project / "src" / "handler.py")
    hook_input = _build_input(file_path, str(tmp_project), str(transcript))

    # Act
    result = run_hook(HOOK_NAME, hook_input)

    # Assert
    assert result.exit_code == 0
