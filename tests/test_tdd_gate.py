"""Tests for hooks/check-test-exists.sh — the TDD gate hook.

Verifies that the hook blocks edits to src/*.py files when no corresponding
test file exists, and allows edits in all other cases.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


HOOK_NAME = "check-test-exists.sh"


def _build_input(file_path: str, cwd: str) -> dict[str, Any]:
    """Build the JSON input structure expected by the hook."""
    return {
        "tool_input": {"file_path": file_path},
        "cwd": cwd,
    }


def test_should_block_when_src_file_has_no_test(
    run_hook: Any,
    tmp_project: Path,
) -> None:
    """Edit src/handler.py with no tests/test_handler.py present."""
    # Arrange
    file_path = str(tmp_project / "src" / "handler.py")
    hook_input = _build_input(file_path, str(tmp_project))

    # Act
    result = run_hook(HOOK_NAME, hook_input)

    # Assert
    assert result.exit_code == 2


def test_should_allow_when_src_file_has_test(
    run_hook: Any,
    tmp_project: Path,
) -> None:
    """Edit src/handler.py when tests/test_handler.py exists."""
    # Arrange
    (tmp_project / "tests" / "test_handler.py").write_text("")
    file_path = str(tmp_project / "src" / "handler.py")
    hook_input = _build_input(file_path, str(tmp_project))

    # Act
    result = run_hook(HOOK_NAME, hook_input)

    # Assert
    assert result.exit_code == 0


def test_should_allow_when_non_src_file(
    run_hook: Any,
    tmp_project: Path,
) -> None:
    """Edit README.md — not under src/, should always be allowed."""
    # Arrange
    file_path = str(tmp_project / "README.md")
    hook_input = _build_input(file_path, str(tmp_project))

    # Act
    result = run_hook(HOOK_NAME, hook_input)

    # Assert
    assert result.exit_code == 0


def test_should_allow_when_init_py(
    run_hook: Any,
    tmp_project: Path,
) -> None:
    """Edit src/__init__.py — special file, always allowed."""
    # Arrange
    file_path = str(tmp_project / "src" / "__init__.py")
    hook_input = _build_input(file_path, str(tmp_project))

    # Act
    result = run_hook(HOOK_NAME, hook_input)

    # Assert
    assert result.exit_code == 0


def test_should_allow_when_non_python_file(
    run_hook: Any,
    tmp_project: Path,
) -> None:
    """Edit src/config.yaml — not a Python file, always allowed."""
    # Arrange
    file_path = str(tmp_project / "src" / "config.yaml")
    hook_input = _build_input(file_path, str(tmp_project))

    # Act
    result = run_hook(HOOK_NAME, hook_input)

    # Assert
    assert result.exit_code == 0


def test_should_include_tdd_message_when_blocked(
    run_hook: Any,
    tmp_project: Path,
) -> None:
    """Blocked edits should include 'Red/Green TDD' in stderr."""
    # Arrange
    file_path = str(tmp_project / "src" / "handler.py")
    hook_input = _build_input(file_path, str(tmp_project))

    # Act
    result = run_hook(HOOK_NAME, hook_input)

    # Assert
    assert result.exit_code == 2
    assert "Red/Green TDD" in result.stderr
