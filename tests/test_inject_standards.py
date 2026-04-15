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


class TestResearchDiscipline:
    """Verify the research-discipline section appears in onboarding context.

    Added 2026-04-14 after a session wasted ~40 minutes disassembling a built
    Worker bundle to trace framework internals when the canonical API was one
    context7 query away. The rule is now injected into every subagent at
    spawn so the discipline fires from working context instead of having to
    be recalled from training.

    Full rule: standards/process/research-discipline.md
    """

    def test_should_include_research_discipline_section_when_invoked(
        self, run_hook: Any, tmp_project: Path
    ) -> None:
        # Arrange
        hook_input = {"cwd": str(tmp_project), "agent_type": "backend"}

        # Act
        result = run_hook("inject-standards.sh", hook_input)

        # Assert
        assert result.exit_code == 0
        assert "Research Discipline" in result.stdout, (
            "Subagents must be briefed on the docs-before-source rule at "
            "spawn time; the section is missing from inject-standards.sh"
        )

    def test_should_name_context7_as_the_first_research_tool(
        self, run_hook: Any, tmp_project: Path
    ) -> None:
        """context7 must appear in the onboarding so subagents know the name
        of the MCP server to query, not just the abstract concept of 'docs'."""
        # Arrange
        hook_input = {"cwd": str(tmp_project), "agent_type": "backend"}

        # Act
        result = run_hook("inject-standards.sh", hook_input)

        # Assert
        assert "context7" in result.stdout, (
            "inject-standards.sh must name context7 explicitly so subagents "
            "know which tool to reach for — 'consult current docs' is too "
            "abstract to act on without the concrete tool name"
        )

    def test_should_warn_against_reading_built_artifacts_before_docs(
        self, run_hook: Any, tmp_project: Path
    ) -> None:
        """The failure mode this rule prevents is disassembling dist/ bundles
        before checking docs. The hook must name that failure mode explicitly
        so a future agent recognises itself in it."""
        # Arrange
        hook_input = {"cwd": str(tmp_project), "agent_type": "backend"}

        # Act
        result = run_hook("inject-standards.sh", hook_input)

        # Assert
        assert "bundles" in result.stdout.lower() or "dist/" in result.stdout, (
            "inject-standards.sh must call out bundle/dist disassembly as "
            "the specific failure mode the rule prevents — the abstract "
            "version ('read docs first') is too weak to fire in the moment"
        )


class TestGitCommitDiscipline:
    """Verify the git commit discipline section appears in onboarding context.

    Added 2026-04-15 after a /build wave in venlink-platform's
    vendor-perspective-client-detail feature saw three parallel frontend
    agents (tasks 002, 003, 004) independently hit the same git-index race
    — `git add <path> && git commit` silently swept other agents' staged
    files into each agent's commit. Recovery burned ~10 minutes. The rule
    is now injected into every subagent at spawn so the discipline fires
    from working context the moment an agent reaches for `git add`.

    Full rule: standards/git/commit-discipline.md
    """

    def test_should_include_git_commit_discipline_section_when_invoked(
        self, run_hook: Any, tmp_project: Path
    ) -> None:
        # Arrange
        hook_input = {"cwd": str(tmp_project), "agent_type": "backend"}

        # Act
        result = run_hook("inject-standards.sh", hook_input)

        # Assert
        assert result.exit_code == 0
        assert "Git Commit Discipline" in result.stdout, (
            "Subagents must be briefed on the parallel-agent git safety "
            "rule at spawn time; the section is missing from "
            "inject-standards.sh"
        )

    def test_should_name_git_commit_paths_form_explicitly(
        self, run_hook: Any, tmp_project: Path
    ) -> None:
        """The safe form is `git commit -m "..." -- <paths>` — agents must
        see the literal command, not an abstract 'use the safe form' hint.
        The abstract version drifts past agents in the heat of the moment."""
        # Arrange
        hook_input = {"cwd": str(tmp_project), "agent_type": "backend"}

        # Act
        result = run_hook("inject-standards.sh", hook_input)

        # Assert
        assert "git commit -m" in result.stdout, (
            "inject-standards.sh must show the literal `git commit -m` "
            "form so agents recognize it as a command to run, not an "
            "abstract principle"
        )
        assert "--" in result.stdout, (
            "inject-standards.sh must name the `--` path separator "
            "explicitly; it's the whole mechanism that makes the "
            "parallel-safe form actually parallel-safe"
        )
        assert "<your-paths>" in result.stdout or "<paths>" in result.stdout, (
            "inject-standards.sh must show a paths placeholder so agents "
            "see the shape of the command, not just the prefix"
        )

    def test_should_warn_against_git_add_glob_patterns(
        self, run_hook: Any, tmp_project: Path
    ) -> None:
        """The abstract rule 'be careful with globs' drifts past agents in
        the heat of the moment. The hook must name `git add .` and
        `git add -u` explicitly as forbidden so a future agent recognises
        itself in the failure mode."""
        # Arrange
        hook_input = {"cwd": str(tmp_project), "agent_type": "backend"}

        # Act
        result = run_hook("inject-standards.sh", hook_input)

        # Assert
        assert "git add ." in result.stdout, (
            "inject-standards.sh must explicitly forbid `git add .` — "
            "the abstract 'be careful with globs' rule is too weak to "
            "fire in the moment"
        )
        assert "git add -u" in result.stdout, (
            "inject-standards.sh must explicitly forbid `git add -u` — "
            "it's the other common glob form agents reach for when "
            "'add everything I changed' is on their mind"
        )


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
