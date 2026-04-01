"""Tests for hooks/reinject-context.sh.

Verifies that the post-compaction context recovery hook outputs the
correct reminder text, git history, dirty-marker warnings, and handles
bare directories without crashing.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def test_should_include_reminder_when_invoked(
    run_hook: Any,
    tmp_path: Path,
) -> None:
    # Arrange
    cwd = str(tmp_path)

    # Act
    result = run_hook("reinject-context.sh", {"cwd": cwd})

    # Assert
    assert result.exit_code == 0
    assert "etc harness" in result.stdout
    assert "Fail early and loud" in result.stdout


def test_should_include_git_log_when_in_repo(
    run_hook: Any,
) -> None:
    # Arrange — use the real repo root which is a git repository
    cwd = "/Users/jason/src/etc-system-engineering"

    # Act
    result = run_hook("reinject-context.sh", {"cwd": cwd})

    # Assert
    assert result.exit_code == 0
    assert "Recent Commits" in result.stdout


def test_should_warn_when_tdd_dirty(
    run_hook: Any,
    tmp_path: Path,
) -> None:
    # Arrange — create the .tdd-dirty marker in a temp directory
    dirty_marker = tmp_path / ".tdd-dirty"
    dirty_marker.touch()

    # Act
    result = run_hook("reinject-context.sh", {"cwd": str(tmp_path)})

    # Assert
    assert result.exit_code == 0
    assert "WARNING" in result.stdout
    assert ".tdd-dirty" in result.stdout


def test_should_not_fail_on_bare_directory(
    run_hook: Any,
    tmp_path: Path,
) -> None:
    # Arrange — bare tmp_path with no special files
    cwd = str(tmp_path)

    # Act
    result = run_hook("reinject-context.sh", {"cwd": cwd})

    # Assert
    assert result.exit_code == 0
