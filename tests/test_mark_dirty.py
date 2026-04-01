"""Tests for hooks/mark-dirty.sh.

Verifies that the mark-dirty hook creates a .tdd-dirty marker file when
production source code (files under /src/) is modified, and does not create
the marker for non-source files. The hook must never block (always exit 0).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest


HOOK_NAME = "mark-dirty.sh"


class TestMarkerCreation:
    """Tests for .tdd-dirty marker file creation."""

    def test_should_create_marker_when_src_file(
        self, run_hook: Any, tmp_project: Path
    ) -> None:
        # Arrange
        hook_input = {
            "tool_input": {"file_path": "src/app.py"},
            "cwd": str(tmp_project),
        }

        # Act
        run_hook(HOOK_NAME, hook_input)

        # Assert
        assert (tmp_project / ".tdd-dirty").exists()

    def test_should_create_marker_when_src_file_with_absolute_path(
        self, run_hook: Any, tmp_project: Path
    ) -> None:
        # Arrange
        hook_input = {
            "tool_input": {"file_path": "/full/path/src/app.py"},
            "cwd": str(tmp_project),
        }

        # Act
        run_hook(HOOK_NAME, hook_input)

        # Assert
        assert (tmp_project / ".tdd-dirty").exists()

    def test_should_not_create_marker_when_non_src_file(
        self, run_hook: Any, tmp_project: Path
    ) -> None:
        # Arrange
        hook_input = {
            "tool_input": {"file_path": "README.md"},
            "cwd": str(tmp_project),
        }

        # Act
        run_hook(HOOK_NAME, hook_input)

        # Assert
        assert not (tmp_project / ".tdd-dirty").exists()


class TestExitCode:
    """Tests that the hook never blocks (always exits 0)."""

    @pytest.mark.parametrize(
        "file_path",
        [
            "src/app.py",
            "README.md",
            "tests/test_app.py",
            "/absolute/src/module.py",
        ],
        ids=["src-file", "readme", "test-file", "absolute-src"],
    )
    def test_should_always_exit_zero(
        self, run_hook: Any, tmp_project: Path, file_path: str
    ) -> None:
        # Arrange
        hook_input = {
            "tool_input": {"file_path": file_path},
            "cwd": str(tmp_project),
        }

        # Act
        result = run_hook(HOOK_NAME, hook_input)

        # Assert
        assert result.exit_code == 0
