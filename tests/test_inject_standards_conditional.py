"""
tests/test_inject_standards_conditional.py

F024: Conditional emission tests for hooks/inject-standards.sh.

Covers AC-001 through AC-007 (task 001 acceptance criteria):
- AC-001+BR-002: Git Commit Discipline role gating
- AC-002+BR-003: Stub-Marker Grep Contract role gating
- AC-003+BR-004: User-Flow Completeness task-AC gating
- AC-004+BR-005: Section ordering when conditionals emit / suppress
- AC-005+BR-006: All 9 base sections always present
- AC-006+BR-008: Exit code 0, stdout/stderr split, backwards compat
- AC-007: Parametrized role x task combinations
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
HOOK_PATH = PROJECT_ROOT / "hooks" / "inject-standards.sh"

# Section heading literals used across all tests
HEADING_GIT_COMMIT = "### Git Commit Discipline"
HEADING_STUB_MARKER = "### Stub-Marker Grep Contract for spec-enforcer"
HEADING_USER_FLOW = "### User-Flow Completeness for User-Facing ACs"

# The 9 invariant base section headings (BR-006). Tuple constant — immutable.
BASE_SECTIONS: tuple[str, ...] = (
    "## Engineering Standards — Onboarding Context",
    "### User Interaction",
    "### TDD",
    "### Code Standards",
    "### Architectural Rules",
    "### Process",
    "### Research Discipline",
    "### Completion Discipline",
    "### Diagnostic Discipline",
    "### Sandbox Discipline",
)

# Section-ordering contract for backend-developer + user-flow task (AC-004/BR-005).
# No single role emits all three conditionals simultaneously:
#   - backend-developer emits Git Commit; not Stub-Marker.
#   - spec-enforcer emits Stub-Marker; not Git Commit.
# AC-008 in spec.md documents the backend-developer snapshot (Stub-Marker absent).
BACKEND_DEV_ORDER: tuple[str, ...] = (
    "### User Interaction",
    "### TDD",
    "### Code Standards",
    "### Architectural Rules",
    "### Process",
    HEADING_GIT_COMMIT,
    "### Research Discipline",
    HEADING_USER_FLOW,
    "### Completion Discipline",
    "### Diagnostic Discipline",
    "### Sandbox Discipline",
)

# Ordering contract for spec-enforcer + user-flow task.
SPEC_ENFORCER_ORDER: tuple[str, ...] = (
    "### User Interaction",
    "### TDD",
    "### Code Standards",
    "### Architectural Rules",
    "### Process",
    "### Research Discipline",
    HEADING_USER_FLOW,
    HEADING_STUB_MARKER,
    "### Completion Discipline",
    "### Diagnostic Discipline",
    "### Sandbox Discipline",
)


# ── Helpers ──────────────────────────────────────────────────────────────────


def _run(payload: dict, cwd: Path | None = None) -> subprocess.CompletedProcess:
    """Invoke inject-standards.sh with the given JSON payload."""
    return subprocess.run(
        ["bash", str(HOOK_PATH)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=str(cwd or PROJECT_ROOT),
    )


def _task_yaml(*, status: str = "in_progress", acs: list[str] | None = None) -> str:
    """Produce a minimal task YAML string."""
    lines = ["task_id: '001'", f"status: {status}"]
    if acs is not None:
        lines.append("acceptance_criteria:")
        for ac in acs:
            escaped = ac.replace("'", "''")
            lines.append(f"  - '{escaped}'")
    return "\n".join(lines) + "\n"


def _write_task(tmp_path: Path, content: str) -> None:
    """Write a task YAML into <tmp_path>/.etc_sdlc/tasks/001-task.yaml."""
    tasks_dir = tmp_path / ".etc_sdlc" / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)
    (tasks_dir / "001-task.yaml").write_text(content)


USER_FLOW_AC = (
    "As an admin, navigate from /admin/settings via the New User affordance, "
    "complete the form, observe success."
)
NON_USER_FLOW_AC = "The API returns HTTP 200 for valid requests."


# ── AC-001 / AC-002 / AC-006 (BR-008): Git Commit Discipline role gating ─────


class TestGitCommitDisciplineRoleGating:
    """AC-001+BR-002: Git Commit Discipline emits for developer roles; suppressed
    for non-developer roles; emits on absent/null/unknown (safe-default over-inject)."""

    @pytest.mark.parametrize(
        "agent_type",
        ["backend-developer", "frontend-developer", "devops-engineer"],
    )
    def test_emitted_for_developer_roles(self, agent_type: str) -> None:
        result = _run({"agent_type": agent_type})
        assert result.returncode == 0
        assert HEADING_GIT_COMMIT in result.stdout, (
            f"Git Commit Discipline must be emitted for role={agent_type!r}"
        )

    @pytest.mark.parametrize(
        "agent_type",
        ["technical-writer", "spec-enforcer", "code-reviewer"],
    )
    def test_suppressed_for_non_developer_roles(self, agent_type: str) -> None:
        result = _run({"agent_type": agent_type})
        assert result.returncode == 0
        assert HEADING_GIT_COMMIT not in result.stdout, (
            f"Git Commit Discipline must be suppressed for role={agent_type!r}"
        )

    def test_emitted_for_absent_agent_type(self) -> None:
        """No agent_type key -> unknown -> safe-default over-inject."""
        result = _run({})
        assert result.returncode == 0
        assert HEADING_GIT_COMMIT in result.stdout, (
            "Git Commit Discipline must be emitted when agent_type is absent (safe default)"
        )

    def test_emitted_for_explicit_unknown(self) -> None:
        """Literal 'unknown' treated same as absent (EC-006)."""
        result = _run({"agent_type": "unknown"})
        assert result.returncode == 0
        assert HEADING_GIT_COMMIT in result.stdout, (
            "Git Commit Discipline must be emitted when agent_type='unknown'"
        )

    def test_emitted_for_null_agent_type(self) -> None:
        """JSON null agent_type -> normalized to unknown -> over-inject."""
        result = _run({"agent_type": None})
        assert result.returncode == 0
        assert HEADING_GIT_COMMIT in result.stdout, (
            "Git Commit Discipline must be emitted when agent_type is null"
        )


# ── AC-002 / AC-005 (BR-003): Stub-Marker Grep Contract role gating ──────────


class TestStubMarkerRoleGating:
    """AC-002+BR-003: Stub-Marker emitted ONLY for spec-enforcer; suppressed
    for all other roles including absent/null/unknown (safe-default under-inject)."""

    def test_emitted_for_spec_enforcer(self) -> None:
        result = _run({"agent_type": "spec-enforcer"})
        assert result.returncode == 0
        assert HEADING_STUB_MARKER in result.stdout, (
            "Stub-Marker Grep Contract must be emitted for role=spec-enforcer"
        )

    @pytest.mark.parametrize(
        "agent_type",
        [
            "backend-developer",
            "frontend-developer",
            "devops-engineer",
            "technical-writer",
            "code-reviewer",
        ],
    )
    def test_suppressed_for_non_spec_enforcer(self, agent_type: str) -> None:
        result = _run({"agent_type": agent_type})
        assert result.returncode == 0
        assert HEADING_STUB_MARKER not in result.stdout, (
            f"Stub-Marker Grep Contract must be suppressed for role={agent_type!r}"
        )

    def test_suppressed_for_absent_agent_type(self) -> None:
        """No agent_type -> unknown -> safe-default under-inject (BR-003 exception)."""
        result = _run({})
        assert result.returncode == 0
        assert HEADING_STUB_MARKER not in result.stdout, (
            "Stub-Marker Grep Contract must be suppressed when agent_type is absent"
        )

    def test_suppressed_for_explicit_unknown(self) -> None:
        result = _run({"agent_type": "unknown"})
        assert result.returncode == 0
        assert HEADING_STUB_MARKER not in result.stdout, (
            "Stub-Marker Grep Contract must be suppressed when agent_type='unknown'"
        )

    def test_suppressed_for_null_agent_type(self) -> None:
        result = _run({"agent_type": None})
        assert result.returncode == 0
        assert HEADING_STUB_MARKER not in result.stdout, (
            "Stub-Marker Grep Contract must be suppressed when agent_type is null"
        )


# ── AC-003 / AC-007 (BR-004): User-Flow Completeness task-AC gating ──────────


class TestUserFlowCompletenessGating:
    """AC-003+BR-004: User-Flow section emitted when in_progress task has a
    User-flow AC; suppressed when no matching AC; emitted when task absent or
    malformed (safe-default over-inject)."""

    def test_emitted_when_task_has_user_flow_ac(self, tmp_path: Path) -> None:
        _write_task(tmp_path, _task_yaml(acs=[USER_FLOW_AC]))
        result = _run({"cwd": str(tmp_path)})
        assert result.returncode == 0
        assert HEADING_USER_FLOW in result.stdout, (
            "User-Flow Completeness must be emitted when task AC matches pattern"
        )

    def test_suppressed_when_task_has_no_user_flow_ac(self, tmp_path: Path) -> None:
        _write_task(tmp_path, _task_yaml(acs=[NON_USER_FLOW_AC]))
        result = _run({"cwd": str(tmp_path)})
        assert result.returncode == 0
        assert HEADING_USER_FLOW not in result.stdout, (
            "User-Flow Completeness must be suppressed when no AC matches pattern"
        )

    def test_emitted_when_no_task_yaml(self, tmp_path: Path) -> None:
        """No .etc_sdlc/tasks/ dir -> safe-default over-inject."""
        result = _run({"cwd": str(tmp_path)})
        assert result.returncode == 0
        assert HEADING_USER_FLOW in result.stdout, (
            "User-Flow Completeness must be emitted when no task YAML exists (safe default)"
        )

    def test_emitted_when_tasks_dir_exists_but_empty(self, tmp_path: Path) -> None:
        """Empty tasks dir (no in_progress task) -> safe-default over-inject."""
        (tmp_path / ".etc_sdlc" / "tasks").mkdir(parents=True)
        result = _run({"cwd": str(tmp_path)})
        assert result.returncode == 0
        assert HEADING_USER_FLOW in result.stdout, (
            "User-Flow Completeness must be emitted when tasks dir exists but is empty"
        )

    def test_emitted_when_task_yaml_is_malformed(self, tmp_path: Path) -> None:
        """Malformed YAML -> safe-default over-inject; exit 0 (EC-002)."""
        tasks_dir = tmp_path / ".etc_sdlc" / "tasks"
        tasks_dir.mkdir(parents=True)
        (tasks_dir / "001-bad.yaml").write_text(
            "status: in_progress\nacceptance_criteria: [invalid: {yaml: [\n"
        )
        result = _run({"cwd": str(tmp_path)})
        assert result.returncode == 0
        assert HEADING_USER_FLOW in result.stdout, (
            "User-Flow Completeness must be emitted when task YAML is malformed (safe default)"
        )

    def test_emitted_when_task_has_mixed_acs_one_matches(self, tmp_path: Path) -> None:
        """At least one AC matches -> emit."""
        _write_task(tmp_path, _task_yaml(acs=[NON_USER_FLOW_AC, USER_FLOW_AC]))
        result = _run({"cwd": str(tmp_path)})
        assert result.returncode == 0
        assert HEADING_USER_FLOW in result.stdout

    def test_suppressed_when_task_has_no_acs_field(self, tmp_path: Path) -> None:
        """in_progress task with no acceptance_criteria key -> suppress."""
        _write_task(tmp_path, _task_yaml(acs=None))
        result = _run({"cwd": str(tmp_path)})
        assert result.returncode == 0
        assert HEADING_USER_FLOW not in result.stdout, (
            "User-Flow Completeness must be suppressed when task has no ACs"
        )

    def test_pattern_requires_both_substrings(self, tmp_path: Path) -> None:
        """AC with 'As ' but no ', navigate from' -> suppress."""
        _write_task(tmp_path, _task_yaml(acs=["As an admin, create a new user."]))
        result = _run({"cwd": str(tmp_path)})
        assert result.returncode == 0
        assert HEADING_USER_FLOW not in result.stdout, (
            "User-Flow pattern requires both 'As ' AND ', navigate from'"
        )


# ── AC-004 / BR-005: Section ordering ────────────────────────────────────────


class TestSectionOrdering:
    """AC-004+BR-005: Section order preserved when conditionals emit or suppress.

    No single role emits all three conditionals: developer roles emit Git Commit
    but not Stub-Marker; spec-enforcer emits Stub-Marker but not Git Commit.
    Tests verify the two maximal-emission cases separately.
    """

    def test_backend_dev_order_with_user_flow_task(self, tmp_path: Path) -> None:
        """backend-developer + user-flow task -> Git Commit + User-Flow emit; Stub-Marker absent.
        Snapshot per spec.md AC-008."""
        _write_task(tmp_path, _task_yaml(acs=[USER_FLOW_AC]))
        result = _run({"cwd": str(tmp_path), "agent_type": "backend-developer"})
        assert result.returncode == 0
        stdout = result.stdout

        positions = [stdout.find(heading) for heading in BACKEND_DEV_ORDER]
        for i, heading in enumerate(BACKEND_DEV_ORDER):
            assert positions[i] != -1, f"Section '{heading}' not found in stdout"
        for i in range(len(BACKEND_DEV_ORDER) - 1):
            assert positions[i] < positions[i + 1], (
                f"Order violated: '{BACKEND_DEV_ORDER[i]}' (pos={positions[i]}) "
                f"must precede '{BACKEND_DEV_ORDER[i + 1]}' (pos={positions[i + 1]})"
            )
        assert HEADING_STUB_MARKER not in stdout, "Stub-Marker must be absent for backend-developer"

    def test_spec_enforcer_order_with_user_flow_task(self, tmp_path: Path) -> None:
        """spec-enforcer + user-flow task -> User-Flow + Stub-Marker emit; Git Commit absent."""
        _write_task(tmp_path, _task_yaml(acs=[USER_FLOW_AC]))
        result = _run({"cwd": str(tmp_path), "agent_type": "spec-enforcer"})
        assert result.returncode == 0
        stdout = result.stdout

        positions = [stdout.find(heading) for heading in SPEC_ENFORCER_ORDER]
        for i, heading in enumerate(SPEC_ENFORCER_ORDER):
            assert positions[i] != -1, f"Section '{heading}' not found in stdout"
        for i in range(len(SPEC_ENFORCER_ORDER) - 1):
            assert positions[i] < positions[i + 1], (
                f"Order violated: '{SPEC_ENFORCER_ORDER[i]}' (pos={positions[i]}) "
                f"must precede '{SPEC_ENFORCER_ORDER[i + 1]}' (pos={positions[i + 1]})"
            )
        assert HEADING_GIT_COMMIT not in stdout, "Git Commit must be absent for spec-enforcer"

    def test_order_preserved_when_git_commit_suppressed(self, tmp_path: Path) -> None:
        """technical-writer + user-flow task: Git Commit absent; remaining sections in order."""
        _write_task(tmp_path, _task_yaml(acs=[USER_FLOW_AC]))
        result = _run({"cwd": str(tmp_path), "agent_type": "technical-writer"})
        stdout = result.stdout

        assert HEADING_GIT_COMMIT not in stdout
        ordered_remaining = [
            h for h in SPEC_ENFORCER_ORDER
            if h in stdout and h != HEADING_STUB_MARKER
        ]
        positions = [stdout.find(h) for h in ordered_remaining]
        for i in range(len(ordered_remaining) - 1):
            assert positions[i] < positions[i + 1], (
                f"Order violated: '{ordered_remaining[i]}' must precede "
                f"'{ordered_remaining[i + 1]}'"
            )

    def test_research_before_user_flow_before_completion(self, tmp_path: Path) -> None:
        """When User-Flow emits: Research Discipline < User-Flow < Completion Discipline."""
        _write_task(tmp_path, _task_yaml(acs=[USER_FLOW_AC]))
        result = _run({"cwd": str(tmp_path), "agent_type": "backend-developer"})
        stdout = result.stdout

        idx_research = stdout.find("### Research Discipline")
        idx_user_flow = stdout.find(HEADING_USER_FLOW)
        idx_completion = stdout.find("### Completion Discipline")

        assert idx_research != -1 and idx_user_flow != -1 and idx_completion != -1
        assert idx_research < idx_user_flow < idx_completion, (
            "Order must be: Research Discipline -> User-Flow -> Completion Discipline"
        )

    def test_process_before_git_before_research(self) -> None:
        """When Git Commit emits: Process < Git Commit < Research Discipline."""
        result = _run({"agent_type": "backend-developer"})
        stdout = result.stdout

        idx_process = stdout.find("### Process")
        idx_git = stdout.find(HEADING_GIT_COMMIT)
        idx_research = stdout.find("### Research Discipline")

        assert idx_process != -1 and idx_git != -1 and idx_research != -1
        assert idx_process < idx_git < idx_research, (
            "Order must be: Process -> Git Commit Discipline -> Research Discipline"
        )


# ── AC-005 / BR-006: Base sections always present ────────────────────────────


class TestBaseSectionsAlwaysPresent:
    """AC-005+BR-006: All base section headings are always present,
    parametrized across role x task combinations (AC-007)."""

    @pytest.mark.parametrize("agent_type", [
        "backend-developer",
        "technical-writer",
        "spec-enforcer",
        "unknown",
    ])
    @pytest.mark.parametrize("task_scenario", [
        "user_flow_ac",
        "no_user_flow_ac",
        "no_task_yaml",
    ])
    def test_base_sections_always_present(
        self,
        agent_type: str,
        task_scenario: str,
        tmp_path: Path,
    ) -> None:
        if task_scenario == "user_flow_ac":
            _write_task(tmp_path, _task_yaml(acs=[USER_FLOW_AC]))
        elif task_scenario == "no_user_flow_ac":
            _write_task(tmp_path, _task_yaml(acs=[NON_USER_FLOW_AC]))
        # "no_task_yaml" -> leave tmp_path empty

        result = _run({"cwd": str(tmp_path), "agent_type": agent_type})
        assert result.returncode == 0

        for section in BASE_SECTIONS:
            assert section in result.stdout, (
                f"Base section '{section}' missing for "
                f"agent_type={agent_type!r} + task_scenario={task_scenario!r}"
            )


# ── AC-006 / BR-008: Exit code, stderr, backwards compat ─────────────────────


class TestBackwardsCompat:
    """AC-006+BR-008: Hook always exits 0; stderr empty on happy path; stdout
    content for unknown role matches pre-F024 'always emit' behavior
    (Git Commit over-injects; all base sections present)."""

    @pytest.mark.parametrize("agent_type", [
        "backend-developer",
        "technical-writer",
        "spec-enforcer",
        "unknown",
        "code-reviewer",
        "frontend-developer",
        "devops-engineer",
    ])
    def test_exit_code_always_zero(self, agent_type: str) -> None:
        result = _run({"agent_type": agent_type})
        assert result.returncode == 0, (
            f"Hook must exit 0 for agent_type={agent_type!r}, "
            f"got {result.returncode}. stderr={result.stderr!r}"
        )

    @pytest.mark.parametrize("agent_type", [
        "backend-developer",
        "technical-writer",
        "spec-enforcer",
        "unknown",
    ])
    def test_stderr_empty_on_happy_path(self, agent_type: str, tmp_path: Path) -> None:
        _write_task(tmp_path, _task_yaml(acs=[USER_FLOW_AC]))
        result = _run({"cwd": str(tmp_path), "agent_type": agent_type})
        assert result.stderr == "", (
            f"stderr must be empty on happy path for agent_type={agent_type!r}, "
            f"got {result.stderr!r}"
        )

    def test_unknown_role_behaves_like_pre_f024(self, tmp_path: Path) -> None:
        """Pre-F024: all sections always emitted. Post-F024: unknown role
        emits Git Commit (over-inject) but suppresses Stub-Marker (under-inject).
        This is the documented backwards-compat contract, not full parity."""
        result = _run({"cwd": str(tmp_path)})
        assert result.returncode == 0
        # Git Commit over-injects (matches pre-F024 behavior)
        assert HEADING_GIT_COMMIT in result.stdout
        # Stub-Marker under-injects (documented F024 change for unknown role)
        assert HEADING_STUB_MARKER not in result.stdout
        # All base sections present
        for section in BASE_SECTIONS:
            assert section in result.stdout


# ── Byte count / token budget smoke test ─────────────────────────────────────


class TestByteCount:
    """Sanity check: technical-writer output is smaller than pre-F024 baseline.
    Pre-F024 worst case: ~7000 bytes. F024 target: <6000 bytes for technical-writer."""

    def test_technical_writer_output_under_6000_bytes(self, tmp_path: Path) -> None:
        """technical-writer suppresses Git Commit + Stub-Marker; no task YAML
        -> User-Flow over-injects. Represents a common low-context dispatch."""
        result = _run({"cwd": str(tmp_path), "agent_type": "technical-writer"})
        byte_count = len(result.stdout.encode("utf-8"))
        assert byte_count < 6000, (
            f"technical-writer stdout is {byte_count} bytes; target <6000. "
            "The conditional suppression is not reducing output as expected."
        )
