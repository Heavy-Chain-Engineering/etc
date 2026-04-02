"""Tests for hooks/inject-standards.sh.

Verifies that the SubagentStart hook injects engineering standards,
active task context, and project invariants into subagent onboarding.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


class TestTddSection:
    """Verify TDD standards appear in onboarding context."""

    def test_should_include_tdd_section_when_invoked(
        self, run_hook: Any, tmp_project: Path
    ) -> None:
        # Arrange
        hook_input = {"cwd": str(tmp_project), "agent_type": "backend"}

        # Act
        result = run_hook("inject-standards.sh", hook_input)

        # Assert
        assert result.exit_code == 0
        assert "TDD" in result.stdout
        assert "Red/Green/Refactor" in result.stdout


class TestCodeStandards:
    """Verify code standards appear in onboarding context."""

    def test_should_include_code_standards_when_invoked(
        self, run_hook: Any, tmp_project: Path
    ) -> None:
        # Arrange
        hook_input = {"cwd": str(tmp_project), "agent_type": "backend"}

        # Act
        result = run_hook("inject-standards.sh", hook_input)

        # Assert
        assert result.exit_code == 0
        assert "type annotations" in result.stdout


class TestActiveTaskInjection:
    """Verify active task content is injected when present."""

    def test_should_include_active_task_when_present(
        self, run_hook: Any, tmp_project: Path, task_file: Any
    ) -> None:
        # Arrange
        task_file(
            task_id="007",
            title="Implement widget parser",
            status="in_progress",
            files_in_scope=["src/parser.py"],
        )
        hook_input = {"cwd": str(tmp_project), "agent_type": "backend"}

        # Act
        result = run_hook("inject-standards.sh", hook_input)

        # Assert
        assert result.exit_code == 0
        assert "Active Task" in result.stdout
        assert "Implement widget parser" in result.stdout
        assert "in_progress" in result.stdout


class TestInvariantsInjection:
    """Verify INVARIANTS.md content is injected when present."""

    def test_should_include_invariants_when_present(
        self, run_hook: Any, tmp_project: Path, invariants_file: Any
    ) -> None:
        # Arrange
        invariants_file([
            {
                "id": "INV-001",
                "description": "All endpoints require authentication",
                "verify": "grep -r '@require_auth' src/",
            },
        ])
        hook_input = {"cwd": str(tmp_project), "agent_type": "backend"}

        # Act
        result = run_hook("inject-standards.sh", hook_input)

        # Assert
        assert result.exit_code == 0
        assert "Project Invariants" in result.stdout
        assert "All endpoints require authentication" in result.stdout


class TestAntipattersInjection:
    """Verify antipatterns content is injected when present."""

    def test_should_include_antipatterns_when_present(
        self, run_hook: Any, tmp_project: Path
    ) -> None:
        # Arrange
        antipatterns_content = (
            "# Antipatterns — Lessons from Escaped Bugs\n"
            "\n"
            "## AP-001: Async exception swallowing in FastAPI middleware\n"
            "- **Date discovered:** 2026-04-01\n"
            "- **Root cause:** try/except caught all exceptions\n"
            "- **Class of bug:** Error handling that's too broad\n"
            "- **Prevention rule:** Never catch bare Exception in middleware.\n"
        )
        antipatterns_path = tmp_project / ".etc_sdlc" / "antipatterns.md"
        antipatterns_path.write_text(antipatterns_content)
        hook_input = {"cwd": str(tmp_project), "agent_type": "backend"}

        # Act
        result = run_hook("inject-standards.sh", hook_input)

        # Assert
        assert result.exit_code == 0
        assert "Known Antipatterns" in result.stdout
        assert "AP-001" in result.stdout
        assert "Async exception swallowing" in result.stdout

    def test_should_not_include_antipatterns_section_when_absent(
        self, run_hook: Any, tmp_path: Path
    ) -> None:
        # Arrange — bare tmp_path with no antipatterns file
        hook_input = {"cwd": str(tmp_path), "agent_type": "unknown"}

        # Act
        result = run_hook("inject-standards.sh", hook_input)

        # Assert
        assert result.exit_code == 0
        assert "Known Antipatterns" not in result.stdout


class TestBareProject:
    """Verify hook succeeds on a bare directory with no tasks or invariants."""

    def test_should_not_fail_when_bare_project(
        self, run_hook: Any, tmp_path: Path
    ) -> None:
        # Arrange — bare tmp_path with no .etc_sdlc/ or INVARIANTS.md
        hook_input = {"cwd": str(tmp_path), "agent_type": "unknown"}

        # Act
        result = run_hook("inject-standards.sh", hook_input)

        # Assert
        assert result.exit_code == 0
        assert "Engineering Standards" in result.stdout
        assert "Active Task" not in result.stdout
        assert "Project Invariants" not in result.stdout
