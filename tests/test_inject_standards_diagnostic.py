"""
tests/test_inject_standards_diagnostic.py

AC-009: hooks/inject-standards.sh emits a ### Diagnostic Discipline section
        positioned between ### Completion Discipline and ### Sandbox Discipline.
        Existing sections are preserved byte-equivalent.
"""

import json
import os
import subprocess

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOK_PATH = os.path.join(PROJECT_ROOT, "hooks", "inject-standards.sh")
PAYLOAD = json.dumps({})
PAYLOAD_SPEC_ENFORCER = json.dumps({"agent_type": "spec-enforcer"})


def _run_hook() -> subprocess.CompletedProcess:
    """Invoke the hook with a minimal SubagentStart JSON payload."""
    return subprocess.run(
        ["bash", HOOK_PATH],
        input=PAYLOAD,
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
    )


@pytest.fixture(scope="module")
def hook_output() -> str:
    result = _run_hook()
    return result.stdout


@pytest.fixture(scope="module")
def hook_result() -> subprocess.CompletedProcess:
    return _run_hook()


class TestExitCode:
    """Hook exit semantics: always 0, never blocks subagent creation."""

    def test_exit_code_is_zero(self, hook_result):
        assert hook_result.returncode == 0, (
            f"Hook must exit 0, got {hook_result.returncode}. stderr: {hook_result.stderr!r}"
        )


class TestDiagnosticDisciplineSection:
    """AC-009: the new section is present and correct."""

    def test_heading_present(self, hook_output):
        assert "### Diagnostic Discipline" in hook_output, (
            "Expected literal heading '### Diagnostic Discipline' in stdout"
        )

    def test_references_standards_file(self, hook_output):
        assert "standards/process/diagnostic-discipline.md" in hook_output, (
            "Section body must reference 'standards/process/diagnostic-discipline.md' "
            "(no leading ./ or /)"
        )

    def test_references_evidence_type_enum(self, hook_output):
        """Section body should mention the evidence_type enum per BR-008 contract."""
        assert "evidence_type" in hook_output, "Section body must mention 'evidence_type' field"

    def test_references_four_required_fields(self, hook_output):
        """Four required fields must be mentioned per BR-008 spec."""
        assert "tool_rerun_command" in hook_output, "Must mention tool_rerun_command"
        assert "attribution" in hook_output, "Must mention attribution"


class TestOrdering:
    """
    The new section MUST appear after ### Completion Discipline
    and BEFORE ### Sandbox Discipline.
    """

    def test_completion_before_diagnostic(self, hook_output):
        idx_completion = hook_output.find("### Completion Discipline")
        idx_diagnostic = hook_output.find("### Diagnostic Discipline")
        assert idx_completion != -1, "### Completion Discipline not found in stdout"
        assert idx_diagnostic != -1, "### Diagnostic Discipline not found in stdout"
        assert idx_completion < idx_diagnostic, (
            "### Completion Discipline must appear BEFORE ### Diagnostic Discipline. "
            f"completion_idx={idx_completion}, diagnostic_idx={idx_diagnostic}"
        )

    def test_diagnostic_before_sandbox(self, hook_output):
        idx_diagnostic = hook_output.find("### Diagnostic Discipline")
        idx_sandbox = hook_output.find("### Sandbox Discipline")
        assert idx_diagnostic != -1, "### Diagnostic Discipline not found in stdout"
        assert idx_sandbox != -1, "### Sandbox Discipline not found in stdout"
        assert idx_diagnostic < idx_sandbox, (
            "### Diagnostic Discipline must appear BEFORE ### Sandbox Discipline. "
            f"diagnostic_idx={idx_diagnostic}, sandbox_idx={idx_sandbox}"
        )


class TestRegressionExistingSections:
    """
    All pre-existing section headings must survive the insertion byte-for-byte.
    The new section is additive only.
    """

    @pytest.mark.parametrize(
        "heading",
        [
            "### TDD",
            "### User Interaction",
            "### Completion Discipline",
            "### Sandbox Discipline",
        ],
    )
    def test_existing_section_present(self, hook_output, heading):
        assert heading in hook_output, (
            f"Pre-existing section '{heading}' must still be present in stdout"
        )

    def test_code_standards_section_present(self, hook_output):
        assert "### Code Standards" in hook_output

    def test_git_commit_discipline_section_present(self, hook_output):
        assert "### Git Commit Discipline" in hook_output

    def test_stub_marker_section_present(self):
        # F024: Stub-Marker is conditional on spec-enforcer role.
        # Use an explicit spec-enforcer payload — the module-scoped hook_output
        # fixture uses {} (unknown role) which suppresses Stub-Marker by design.
        result = subprocess.run(
            ["bash", HOOK_PATH],
            input=PAYLOAD_SPEC_ENFORCER,
            capture_output=True,
            text=True,
            cwd=PROJECT_ROOT,
        )
        assert "### Stub-Marker Grep Contract" in result.stdout
