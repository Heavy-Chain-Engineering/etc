#!/usr/bin/env python3
"""Tests for hooks/check-concepts.sh — cross-boundary concept enforcement hook.

Validates that the verify-phase hook parses CONCEPT-NNN entries from
INVARIANTS.md, runs their verify commands, and reports violations
without interfering with INV-NNN entries (handled by check-invariants.sh).
"""

import json
import os
import subprocess
import textwrap

HOOK_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "hooks",
    "check-concepts.sh",
)

INV_HOOK_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "hooks",
    "check-invariants.sh",
)


def run_concept_hook(
    file_path: str, cwd: str, tool: str = "Edit"
) -> subprocess.CompletedProcess:
    """Run the check-concepts hook with the given inputs."""
    hook_input = json.dumps(
        {
            "tool_name": tool,
            "tool_input": {"file_path": file_path},
            "cwd": cwd,
        }
    )
    return subprocess.run(
        ["bash", HOOK_PATH],
        input=hook_input,
        capture_output=True,
        text=True,
        timeout=15,
    )


def run_invariants_hook(
    file_path: str, cwd: str, tool: str = "Edit"
) -> subprocess.CompletedProcess:
    """Run the check-invariants hook with the given inputs."""
    hook_input = json.dumps(
        {
            "tool_name": tool,
            "tool_input": {"file_path": file_path},
            "cwd": cwd,
        }
    )
    return subprocess.run(
        ["bash", INV_HOOK_PATH],
        input=hook_input,
        capture_output=True,
        text=True,
        timeout=15,
    )


def write_invariants(directory: str, content: str) -> str:
    """Write an INVARIANTS.md file into the given directory."""
    path = os.path.join(directory, "INVARIANTS.md")
    with open(path, "w") as f:
        f.write(textwrap.dedent(content))
    return path


# ---------------------------------------------------------------------------
# Test: No INVARIANTS.md — passes silently
# ---------------------------------------------------------------------------


class TestNoInvariantsFile:
    def test_passes_when_no_invariants_file(self, tmp_path):
        """Hook should exit 0 when no INVARIANTS.md exists."""
        result = run_concept_hook(
            file_path=str(tmp_path / "src" / "app.py"),
            cwd=str(tmp_path),
        )
        assert result.returncode == 0
        assert result.stderr.strip() == ""


# ---------------------------------------------------------------------------
# Test: CONCEPT entries detected and violations reported (AC2)
# ---------------------------------------------------------------------------


class TestConceptViolations:
    def test_detects_concept_violation(self, tmp_path):
        """Hook should exit 2 when a CONCEPT verify command finds violations."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "bad.py").write_text("CONCEPT_VIOLATION_MARKER = True\n")

        write_invariants(
            str(tmp_path),
            """\
            # Project Invariants

            ## CONCEPT-001: No concept violation markers
            - **Contexts:** Module A, Module B
            - **Precondition:** Source code is clean
            - **Postcondition:** No violation markers exist
            - **Invariant:** CONCEPT_VIOLATION_MARKER never appears
            - **Layers:** test, hook
            - **Verify:** `grep -rn 'CONCEPT_VIOLATION_MARKER' src/ 2>/dev/null`
            - **Fail action:** Block merge
        """,
        )

        result = run_concept_hook(
            file_path=str(src_dir / "bad.py"),
            cwd=str(tmp_path),
        )
        assert result.returncode == 2
        assert "CONCEPT VIOLATION [CONCEPT-001]" in result.stderr
        assert "BLOCKED" in result.stderr

    def test_reports_multiple_concept_violations(self, tmp_path):
        """Hook should report count of all violated concepts."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "bad.py").write_text("MARKER_X = 1\nMARKER_Y = 2\n")

        write_invariants(
            str(tmp_path),
            """\
            # Project Invariants

            ## CONCEPT-001: No marker X
            - **Contexts:** Context A
            - **Precondition:** Clean
            - **Postcondition:** No X
            - **Invariant:** No MARKER_X
            - **Layers:** test
            - **Verify:** `grep -rn 'MARKER_X' src/ 2>/dev/null`
            - **Fail action:** Block merge

            ## CONCEPT-002: No marker Y
            - **Contexts:** Context B
            - **Precondition:** Clean
            - **Postcondition:** No Y
            - **Invariant:** No MARKER_Y
            - **Layers:** test
            - **Verify:** `grep -rn 'MARKER_Y' src/ 2>/dev/null`
            - **Fail action:** Block merge
        """,
        )

        result = run_concept_hook(
            file_path=str(src_dir / "bad.py"),
            cwd=str(tmp_path),
        )
        assert result.returncode == 2
        assert "2 concept(s) violated" in result.stderr
        assert "CONCEPT-001" in result.stderr
        assert "CONCEPT-002" in result.stderr


# ---------------------------------------------------------------------------
# Test: CONCEPT entries pass on clean projects (AC3)
# ---------------------------------------------------------------------------


class TestConceptPassing:
    def test_passes_when_concepts_hold(self, tmp_path):
        """Hook should exit 0 when CONCEPT verify commands produce no output."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "clean.py").write_text("# Clean file\nx = 1\n")

        write_invariants(
            str(tmp_path),
            """\
            # Project Invariants

            ## CONCEPT-001: No nonexistent markers
            - **Contexts:** Module A
            - **Precondition:** N/A
            - **Postcondition:** N/A
            - **Invariant:** Marker absent
            - **Layers:** test
            - **Verify:** `grep -rn 'THIS_DOES_NOT_EXIST_ANYWHERE_XYZ' src/ 2>/dev/null`
            - **Fail action:** Block merge
        """,
        )

        result = run_concept_hook(
            file_path=str(src_dir / "clean.py"),
            cwd=str(tmp_path),
        )
        assert result.returncode == 0


# ---------------------------------------------------------------------------
# Test: Exemption pattern works (AC4)
# ---------------------------------------------------------------------------


class TestExemption:
    def test_concept_exempt_comment_skips_line(self, tmp_path):
        """Lines with # concept-exempt: CONCEPT-NNN are excluded from violations."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "exempted.py").write_text(
            "BAD_PATTERN = True  # concept-exempt: CONCEPT-001\n"
        )

        write_invariants(
            str(tmp_path),
            """\
            # Project Invariants

            ## CONCEPT-001: No bad patterns
            - **Contexts:** Module A
            - **Precondition:** N/A
            - **Postcondition:** N/A
            - **Invariant:** BAD_PATTERN absent
            - **Layers:** test
            - **Verify:** `grep -rn 'BAD_PATTERN' src/ 2>/dev/null | grep -v '# concept-exempt: CONCEPT-001'`
            - **Fail action:** Block merge
        """,
        )

        result = run_concept_hook(
            file_path=str(src_dir / "exempted.py"),
            cwd=str(tmp_path),
        )
        assert result.returncode == 0


# ---------------------------------------------------------------------------
# Test: CONCEPT and INV coexistence (AC1, AC13)
# ---------------------------------------------------------------------------


class TestCoexistence:
    def test_concepts_and_invariants_coexist(self, tmp_path):
        """INVARIANTS.md with both INV and CONCEPT entries is valid.
        check-concepts.sh only processes CONCEPT entries.
        check-invariants.sh only processes INV entries."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "app.py").write_text(
            "INV_MARKER = True\nCONCEPT_MARKER = True\n"
        )

        write_invariants(
            str(tmp_path),
            """\
            # Project Invariants

            ## INV-001: No INV markers
            - **Layers:** hook
            - **Verify:** `grep -rn 'INV_MARKER' src/ 2>/dev/null`
            - **Fail action:** Block merge

            ## CONCEPT-001: No CONCEPT markers
            - **Contexts:** Module A, Module B
            - **Precondition:** Clean
            - **Postcondition:** No markers
            - **Invariant:** CONCEPT_MARKER absent
            - **Layers:** test
            - **Verify:** `grep -rn 'CONCEPT_MARKER' src/ 2>/dev/null`
            - **Fail action:** Block merge
        """,
        )

        # check-concepts.sh should only see CONCEPT-001
        concept_result = run_concept_hook(
            file_path=str(src_dir / "app.py"),
            cwd=str(tmp_path),
        )
        assert concept_result.returncode == 2
        assert "CONCEPT-001" in concept_result.stderr
        assert "INV-001" not in concept_result.stderr

        # check-invariants.sh should only see INV-001
        inv_result = run_invariants_hook(
            file_path=str(src_dir / "app.py"),
            cwd=str(tmp_path),
        )
        assert inv_result.returncode == 2
        assert "INV-001" in inv_result.stderr
        assert "CONCEPT-001" not in inv_result.stderr

    def test_only_concepts_no_invariants(self, tmp_path):
        """INVARIANTS.md with only CONCEPT entries — check-invariants.sh passes."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "app.py").write_text("CONCEPT_ONLY = True\n")

        write_invariants(
            str(tmp_path),
            """\
            # Project Invariants

            ## CONCEPT-001: No concept-only markers
            - **Contexts:** Module A
            - **Precondition:** N/A
            - **Postcondition:** N/A
            - **Invariant:** Absent
            - **Layers:** test
            - **Verify:** `grep -rn 'CONCEPT_ONLY' src/ 2>/dev/null`
            - **Fail action:** Block merge
        """,
        )

        # check-invariants.sh should pass (no INV entries)
        inv_result = run_invariants_hook(
            file_path=str(src_dir / "app.py"),
            cwd=str(tmp_path),
        )
        assert inv_result.returncode == 0

        # check-concepts.sh should catch the violation
        concept_result = run_concept_hook(
            file_path=str(src_dir / "app.py"),
            cwd=str(tmp_path),
        )
        assert concept_result.returncode == 2
        assert "CONCEPT-001" in concept_result.stderr


# ---------------------------------------------------------------------------
# Test: VenLink CONCEPT-001 tenant ownership detection (AC11)
# ---------------------------------------------------------------------------


class TestVenLinkExamples:
    def test_concept_001_catches_tenant_bug(self, tmp_path):
        """CONCEPT-001 verify command catches org_id filtering without current_user."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "search.py").write_text(
            'results = db.filter(org_id=vendor.org_id)\n'
        )

        write_invariants(
            str(tmp_path),
            """\
            # Project Invariants

            ## CONCEPT-001: Organization ownership for multi-tenant queries
            - **Contexts:** IAM, Search
            - **Precondition:** Authenticated user has a non-null organization_id
            - **Postcondition:** Every row belongs to an org the user has access to
            - **Invariant:** query.filter_org == auth_user.org_id
            - **Layers:** test, hook
            - **Verify:** `grep -rn 'filter.*org_id' src/ | grep -v 'current_user' | grep -v '# concept-exempt: CONCEPT-001'`
            - **Fail action:** Block merge
        """,
        )

        result = run_concept_hook(
            file_path=str(src_dir / "search.py"),
            cwd=str(tmp_path),
        )
        assert result.returncode == 2
        assert "CONCEPT-001" in result.stderr

    def test_concept_001_passes_with_current_user(self, tmp_path):
        """CONCEPT-001 passes when org_id uses current_user."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "search.py").write_text(
            'results = db.filter(org_id=current_user.org_id)\n'
        )

        write_invariants(
            str(tmp_path),
            """\
            # Project Invariants

            ## CONCEPT-001: Organization ownership for multi-tenant queries
            - **Contexts:** IAM, Search
            - **Precondition:** Authenticated user has a non-null organization_id
            - **Postcondition:** Every row belongs to an org the user has access to
            - **Invariant:** query.filter_org == auth_user.org_id
            - **Layers:** test, hook
            - **Verify:** `grep -rn 'filter.*org_id' src/ | grep -v 'current_user' | grep -v '# concept-exempt: CONCEPT-001'`
            - **Fail action:** Block merge
        """,
        )

        result = run_concept_hook(
            file_path=str(src_dir / "search.py"),
            cwd=str(tmp_path),
        )
        assert result.returncode == 0


# ---------------------------------------------------------------------------
# Test: Concept parsing
# ---------------------------------------------------------------------------


class TestConceptParsing:
    def test_parses_concept_headings(self, tmp_path):
        """Parser extracts CONCEPT-NNN IDs and verify commands."""
        write_invariants(
            str(tmp_path),
            """\
            # Invariants

            ## CONCEPT-001: First concept
            - **Contexts:** A, B
            - **Verify:** `echo "check one"`
            - **Fail action:** Block merge

            ## CONCEPT-042: Second concept
            - **Contexts:** C
            - **Verify:** `grep -rn 'pattern' src/`
            - **Fail action:** Warn
        """,
        )

        parse_result = subprocess.run(
            [
                "bash",
                "-c",
                textwrap.dedent(
                    f"""\
                parse_concepts() {{
                    local file="$1"
                    local current_id=""
                    while IFS= read -r line; do
                        if [[ "$line" =~ ^##[[:space:]]+(CONCEPT-[0-9]+): ]]; then
                            current_id="${{BASH_REMATCH[1]}}"
                        fi
                        if [[ "$line" =~ ^##[[:space:]]+(INV-[0-9]+): ]]; then
                            current_id=""
                        fi
                        if [[ "$line" =~ \\*\\*Verify:\\*\\*[[:space:]]*\\`(.+)\\` ]]; then
                            local cmd="${{BASH_REMATCH[1]}}"
                            if [[ -n "$current_id" && -n "$cmd" ]]; then
                                echo "${{current_id}}|${{cmd}}"
                            fi
                        fi
                    done < "$file"
                }}
                parse_concepts "{tmp_path}/INVARIANTS.md"
            """
                ),
            ],
            capture_output=True,
            text=True,
        )
        lines = parse_result.stdout.strip().split("\n")
        assert len(lines) == 2
        assert lines[0].startswith("CONCEPT-001|")
        assert "echo" in lines[0]
        assert lines[1].startswith("CONCEPT-042|")
        assert "grep" in lines[1]

    def test_ignores_inv_entries(self, tmp_path):
        """Parser should not extract verify commands from INV entries."""
        write_invariants(
            str(tmp_path),
            """\
            # Invariants

            ## INV-001: An invariant
            - **Layers:** hook
            - **Verify:** `echo "inv check"`
            - **Fail action:** Block merge

            ## CONCEPT-001: A concept
            - **Contexts:** A
            - **Verify:** `echo "concept check"`
            - **Fail action:** Block merge
        """,
        )

        parse_result = subprocess.run(
            [
                "bash",
                "-c",
                textwrap.dedent(
                    f"""\
                parse_concepts() {{
                    local file="$1"
                    local current_id=""
                    while IFS= read -r line; do
                        if [[ "$line" =~ ^##[[:space:]]+(CONCEPT-[0-9]+): ]]; then
                            current_id="${{BASH_REMATCH[1]}}"
                        fi
                        if [[ "$line" =~ ^##[[:space:]]+(INV-[0-9]+): ]]; then
                            current_id=""
                        fi
                        if [[ "$line" =~ \\*\\*Verify:\\*\\*[[:space:]]*\\`(.+)\\` ]]; then
                            local cmd="${{BASH_REMATCH[1]}}"
                            if [[ -n "$current_id" && -n "$cmd" ]]; then
                                echo "${{current_id}}|${{cmd}}"
                            fi
                        fi
                    done < "$file"
                }}
                parse_concepts "{tmp_path}/INVARIANTS.md"
            """
                ),
            ],
            capture_output=True,
            text=True,
        )
        lines = [line for line in parse_result.stdout.strip().split("\n") if line]
        assert len(lines) == 1
        assert lines[0].startswith("CONCEPT-001|")
        assert "concept check" in lines[0]


# ---------------------------------------------------------------------------
# Test: Cascading INVARIANTS.md files
# ---------------------------------------------------------------------------


class TestCascading:
    def test_checks_both_project_and_component_concepts(self, tmp_path):
        """Component INVARIANTS.md CONCEPT entries add to project-root ones."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        component_dir = src_dir / "auth"
        component_dir.mkdir()
        (component_dir / "handler.py").write_text("COMPONENT_CONCEPT_BUG = True\n")

        # Project root — passing concept
        write_invariants(
            str(tmp_path),
            """\
            # Project Invariants

            ## CONCEPT-001: Project-level concept (passes)
            - **Contexts:** Module A
            - **Precondition:** N/A
            - **Postcondition:** N/A
            - **Invariant:** Absent
            - **Layers:** test
            - **Verify:** `grep -rn 'NONEXISTENT_CONCEPT_MARKER' src/ 2>/dev/null`
            - **Fail action:** Block merge
        """,
        )

        # Component — failing concept
        write_invariants(
            str(component_dir),
            """\
            # Auth Concepts

            ## CONCEPT-100: No component concept bugs
            - **Contexts:** Auth
            - **Precondition:** N/A
            - **Postcondition:** N/A
            - **Invariant:** COMPONENT_CONCEPT_BUG absent
            - **Layers:** test
            - **Verify:** `grep -rn 'COMPONENT_CONCEPT_BUG' src/auth/ 2>/dev/null`
            - **Fail action:** Block merge
        """,
        )

        result = run_concept_hook(
            file_path=str(component_dir / "handler.py"),
            cwd=str(tmp_path),
        )
        assert result.returncode == 2
        assert "CONCEPT-100" in result.stderr


# ---------------------------------------------------------------------------
# Test: Resilience
# ---------------------------------------------------------------------------


class TestResilience:
    def test_malformed_invariants_does_not_block(self, tmp_path):
        """Malformed INVARIANTS.md without concept entries passes."""
        inv_path = tmp_path / "INVARIANTS.md"
        inv_path.write_text("Random text, no headings\n")

        result = run_concept_hook(
            file_path=str(tmp_path / "src" / "app.py"),
            cwd=str(tmp_path),
        )
        assert result.returncode == 0

    def test_empty_invariants_file(self, tmp_path):
        """Empty INVARIANTS.md passes."""
        inv_path = tmp_path / "INVARIANTS.md"
        inv_path.write_text("")

        result = run_concept_hook(
            file_path=str(tmp_path / "src" / "app.py"),
            cwd=str(tmp_path),
        )
        assert result.returncode == 0

    def test_verify_command_error_does_not_block(self, tmp_path):
        """A verify command that errors (non-zero exit) should not block."""
        write_invariants(
            str(tmp_path),
            """\
            # Invariants

            ## CONCEPT-001: Check nonexistent path
            - **Contexts:** A
            - **Verify:** `grep -rn 'SOMETHING' /nonexistent/path 2>/dev/null`
            - **Fail action:** Block merge
        """,
        )

        result = run_concept_hook(
            file_path=str(tmp_path / "src" / "app.py"),
            cwd=str(tmp_path),
        )
        assert result.returncode == 0

    def test_no_cwd_passes(self):
        """Hook should exit 0 when CWD is empty or '.'."""
        hook_input = json.dumps(
            {
                "tool_name": "Edit",
                "tool_input": {"file_path": "/tmp/test.py"},
                "cwd": ".",
            }
        )
        result = subprocess.run(
            ["bash", HOOK_PATH],
            input=hook_input,
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert result.returncode == 0
