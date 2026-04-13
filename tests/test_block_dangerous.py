"""Tests for hooks/block-dangerous-commands.sh.

Validates that the hook blocks destructive operations (rm -rf, force push,
--no-verify, DROP TABLE, git reset --hard, git clean -f, bypass flags)
and allows safe commands (ls, git status, pytest, rm -rf on safe targets).
"""

from __future__ import annotations

from typing import Any

import pytest


HOOK_NAME = "block-dangerous-commands.sh"
BLOCKED = 2
ALLOWED = 0


def _make_input(command: str) -> dict[str, Any]:
    """Build the JSON input dict expected by the hook."""
    return {"tool_input": {"command": command}}


# -- Blocking tests -----------------------------------------------------------


class TestShouldBlockDangerousCommands:
    """Group: commands that must be blocked (exit 2)."""

    def test_should_block_when_rm_rf(self, run_hook: Any) -> None:
        # Arrange
        hook_input = _make_input("rm -rf /important")

        # Act
        result = run_hook(HOOK_NAME, hook_input)

        # Assert
        assert result.exit_code == BLOCKED

    def test_should_block_when_git_force_push(self, run_hook: Any) -> None:
        # Arrange
        hook_input = _make_input("git push --force origin main")

        # Act
        result = run_hook(HOOK_NAME, hook_input)

        # Assert
        assert result.exit_code == BLOCKED

    def test_should_block_when_git_reset_hard(self, run_hook: Any) -> None:
        # Arrange
        hook_input = _make_input("git reset --hard")

        # Act
        result = run_hook(HOOK_NAME, hook_input)

        # Assert
        assert result.exit_code == BLOCKED

    def test_should_block_when_no_verify(self, run_hook: Any) -> None:
        # Arrange
        hook_input = _make_input("git commit --no-verify -m test")

        # Act
        result = run_hook(HOOK_NAME, hook_input)

        # Assert
        assert result.exit_code == BLOCKED

    def test_should_block_when_drop_table(self, run_hook: Any) -> None:
        # Arrange
        hook_input = _make_input('psql -c "DROP TABLE users"')

        # Act
        result = run_hook(HOOK_NAME, hook_input)

        # Assert
        assert result.exit_code == BLOCKED

    def test_should_block_when_bypass_safety(self, run_hook: Any) -> None:
        # Arrange
        hook_input = _make_input("some-tool --dangerously-skip-permissions")

        # Act
        result = run_hook(HOOK_NAME, hook_input)

        # Assert
        assert result.exit_code == BLOCKED

    def test_should_block_when_git_clean_force(self, run_hook: Any) -> None:
        # Arrange
        hook_input = _make_input("git clean -fd")

        # Act
        result = run_hook(HOOK_NAME, hook_input)

        # Assert
        assert result.exit_code == BLOCKED

    @pytest.mark.parametrize(
        "command",
        [
            "git add .",
            "git add . extra-file",
            "git add -A",
            "git add -A src/",
            "git add --all",
            "git add --all src/",
        ],
        ids=["git_add_dot", "git_add_dot_plus", "git_add_A", "git_add_A_path",
             "git_add_all", "git_add_all_path"],
    )
    def test_should_block_when_undisciplined_git_add(
        self, run_hook: Any, command: str
    ) -> None:
        # Arrange
        hook_input = _make_input(command)

        # Act
        result = run_hook(HOOK_NAME, hook_input)

        # Assert
        assert result.exit_code == BLOCKED


# -- Allow tests --------------------------------------------------------------


class TestShouldAllowSafeCommands:
    """Group: commands that must be allowed (exit 0)."""

    def test_should_allow_when_rm_rf_safe_target(self, run_hook: Any) -> None:
        # Arrange
        hook_input = _make_input("rm -rf node_modules")

        # Act
        result = run_hook(HOOK_NAME, hook_input)

        # Assert
        assert result.exit_code == ALLOWED

    @pytest.mark.parametrize(
        "command",
        [
            # Regression cases for the bug where `git\s+add\s+\.` matched any
            # argument starting with a period, incorrectly blocking legitimate
            # staging of dot-prefixed paths (.etc_sdlc/, .gitignore, etc.).
            "git add .gitignore",
            "git add .etc_sdlc/features/init-project/spec.md",
            "git add .github/workflows/ci.yml",
            "git add .env.example",
            "git add .dockerignore .gitattributes",
            "git add spec/file.md .etc_sdlc/foo.md",
        ],
        ids=[
            "dot_gitignore",
            "dot_etc_sdlc_nested",
            "dot_github_workflow",
            "dot_env_example",
            "multiple_dot_prefixed",
            "normal_then_dot_prefixed",
        ],
    )
    def test_should_allow_when_git_add_dot_prefixed_path(
        self, run_hook: Any, command: str
    ) -> None:
        """Regression test: the block regex must not match paths that merely
        start with a dot. Only the standalone `.` argument (meaning 'stage
        everything') is undisciplined."""
        # Arrange
        hook_input = _make_input(command)

        # Act
        result = run_hook(HOOK_NAME, hook_input)

        # Assert
        assert result.exit_code == ALLOWED, (
            f"Expected {command!r} to be allowed but got exit {result.exit_code}. "
            f"stderr: {result.stderr}"
        )

    @pytest.mark.parametrize(
        "command",
        [
            "ls -la",
            "git status",
            "pytest tests/",
        ],
        ids=["ls", "git_status", "pytest"],
    )
    def test_should_allow_when_safe_command(
        self, run_hook: Any, command: str
    ) -> None:
        # Arrange
        hook_input = _make_input(command)

        # Act
        result = run_hook(HOOK_NAME, hook_input)

        # Assert
        assert result.exit_code == ALLOWED


# -- Stderr message tests -----------------------------------------------------


class TestShouldIncludeDescriptiveMessage:
    """Group: blocked operations must explain why in stderr."""

    @pytest.mark.parametrize(
        ("command", "expected_fragment"),
        [
            ("rm -rf /important", "Recursive rm"),
            ("git push --force origin main", "Force push"),
            ("git reset --hard", "Hard reset"),
            ("git commit --no-verify -m test", "bypass safety"),
            ('psql -c "DROP TABLE users"', "Destructive database"),
            ("some-tool --dangerously-skip-permissions", "bypass safety"),
            ("git clean -fd", "git clean"),
        ],
        ids=[
            "rm_rf",
            "force_push",
            "reset_hard",
            "no_verify",
            "drop_table",
            "bypass_safety",
            "git_clean",
        ],
    )
    def test_should_include_reason_in_stderr_when_blocked(
        self, run_hook: Any, command: str, expected_fragment: str
    ) -> None:
        # Arrange
        hook_input = _make_input(command)

        # Act
        result = run_hook(HOOK_NAME, hook_input)

        # Assert
        assert result.exit_code == BLOCKED
        assert expected_fragment in result.stderr, (
            f"Expected '{expected_fragment}' in stderr, got: {result.stderr!r}"
        )
