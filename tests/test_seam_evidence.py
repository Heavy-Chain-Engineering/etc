#!/usr/bin/env python3
"""Tests for hooks/check-seam-evidence.sh -- integration seam evidence gate.

Validates that the verify-phase hook parses SEAMS.md, checks evidence at
L1/L2/L3 for each declared seam, handles progressive adoption (no SEAMS.md
= skip), malformed entries, SEAM-DEV entries, and missing test files.
"""

import json
import os
import subprocess
import textwrap

HOOK_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "hooks",
    "check-seam-evidence.sh",
)


def run_seam_hook(cwd: str) -> subprocess.CompletedProcess:
    """Run the check-seam-evidence hook with the given CWD."""
    hook_input = json.dumps(
        {
            "tool_name": "Task",
            "tool_input": {},
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


def write_seams(directory: str, content: str) -> str:
    """Write a SEAMS.md file into the given directory."""
    path = os.path.join(directory, "SEAMS.md")
    with open(path, "w") as f:
        f.write(textwrap.dedent(content))
    return path


def write_test_file(base_dir: str, relative_path: str, content: str) -> str:
    """Write a test file at the given relative path under base_dir."""
    full_path = os.path.join(base_dir, relative_path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, "w") as f:
        f.write(textwrap.dedent(content))
    return full_path


# ---------------------------------------------------------------------------
# Test: Progressive adoption -- no SEAMS.md
# ---------------------------------------------------------------------------


class TestNoSeamsFile:
    def test_exits_0_with_warning_when_no_seams_file(self, tmp_path):
        """AC10: No SEAMS.md exits 0 with warning."""
        result = run_seam_hook(cwd=str(tmp_path))
        assert result.returncode == 0
        assert "No SEAMS.md found" in result.stderr
        assert "seam evidence checks skipped" in result.stderr

    def test_exits_0_when_cwd_is_dot(self):
        """Hook should exit 0 when CWD is '.'."""
        hook_input = json.dumps(
            {"tool_name": "Task", "tool_input": {}, "cwd": "."}
        )
        result = subprocess.run(
            ["bash", HOOK_PATH],
            input=hook_input,
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert result.returncode == 0

    def test_exits_0_when_cwd_is_empty(self):
        """Hook should exit 0 when CWD is empty."""
        hook_input = json.dumps(
            {"tool_name": "Task", "tool_input": {}, "cwd": ""}
        )
        result = subprocess.run(
            ["bash", HOOK_PATH],
            input=hook_input,
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert result.returncode == 0


# ---------------------------------------------------------------------------
# Test: Empty SEAMS.md
# ---------------------------------------------------------------------------


class TestEmptySeamsFile:
    def test_exits_0_when_seams_file_has_no_entries(self, tmp_path):
        """Edge case 1: Empty SEAMS.md with no entries exits 0."""
        write_seams(
            str(tmp_path),
            """\
            # Integration Seams

            This file has no seam entries yet.
        """,
        )
        result = run_seam_hook(cwd=str(tmp_path))
        assert result.returncode == 0
        assert "no seam entries" in result.stderr


# ---------------------------------------------------------------------------
# Test: L1 evidence checks
# ---------------------------------------------------------------------------


class TestL1Evidence:
    def test_passes_when_test_exists_with_marker(self, tmp_path):
        """AC1: L1 seam passes when test exists with integration marker."""
        write_test_file(
            str(tmp_path),
            "tests/integration/test_foo.py",
            """\
            import pytest

            @pytest.mark.integration
            def test_something():
                pass
        """,
        )
        write_seams(
            str(tmp_path),
            """\
            # Integration Seams

            ## SEAM-001: Foo to Bar
            - **Producer:** src/foo/
            - **Consumer:** src/bar/
            - **Interface:** FooBar query
            - **Integration test:** tests/integration/test_foo.py
            - **Evidence level:** L1
        """,
        )
        result = run_seam_hook(cwd=str(tmp_path))
        assert result.returncode == 0

    def test_fails_when_test_file_missing(self, tmp_path):
        """AC2: L1 fails when test file does not exist."""
        write_seams(
            str(tmp_path),
            """\
            # Integration Seams

            ## SEAM-001: Foo to Bar
            - **Producer:** src/foo/
            - **Consumer:** src/bar/
            - **Interface:** FooBar query
            - **Integration test:** tests/integration/test_foo.py
            - **Evidence level:** L1
        """,
        )
        result = run_seam_hook(cwd=str(tmp_path))
        assert result.returncode == 2
        assert "SEAM-001" in result.stderr
        assert "test file not found" in result.stderr

    def test_fails_when_integration_marker_missing(self, tmp_path):
        """AC3: L1 fails when integration marker is absent."""
        write_test_file(
            str(tmp_path),
            "tests/integration/test_foo.py",
            """\
            def test_something():
                pass
        """,
        )
        write_seams(
            str(tmp_path),
            """\
            # Integration Seams

            ## SEAM-001: Foo to Bar
            - **Producer:** src/foo/
            - **Consumer:** src/bar/
            - **Interface:** FooBar query
            - **Integration test:** tests/integration/test_foo.py
            - **Evidence level:** L1
        """,
        )
        result = run_seam_hook(cwd=str(tmp_path))
        assert result.returncode == 2
        assert "SEAM-001" in result.stderr
        assert "no @pytest.mark.integration marker" in result.stderr

    def test_recognizes_module_level_pytestmark(self, tmp_path):
        """AC13: Module-level pytestmark assignment is recognized."""
        write_test_file(
            str(tmp_path),
            "tests/integration/test_foo.py",
            """\
            import pytest

            pytestmark = [pytest.mark.integration]

            def test_something():
                pass
        """,
        )
        write_seams(
            str(tmp_path),
            """\
            # Integration Seams

            ## SEAM-001: Foo to Bar
            - **Producer:** src/foo/
            - **Consumer:** src/bar/
            - **Interface:** FooBar query
            - **Integration test:** tests/integration/test_foo.py
            - **Evidence level:** L1
        """,
        )
        result = run_seam_hook(cwd=str(tmp_path))
        assert result.returncode == 0


# ---------------------------------------------------------------------------
# Test: L2 evidence checks
# ---------------------------------------------------------------------------


class TestL2Evidence:
    def test_passes_when_test_imports_both_sides(self, tmp_path):
        """AC4: L2 passes when test imports both producer and consumer."""
        write_test_file(
            str(tmp_path),
            "tests/integration/test_iam_rel.py",
            """\
            import pytest
            from venlink.iam import user_service
            from venlink.relationships import org_membership

            @pytest.mark.integration
            def test_membership_lookup():
                pass
        """,
        )
        write_seams(
            str(tmp_path),
            """\
            # Integration Seams

            ## SEAM-002: IAM to Relationships
            - **Producer:** src/venlink/iam/
            - **Consumer:** src/venlink/relationships/
            - **Interface:** UserOrganizationMembership model query
            - **Integration test:** tests/integration/test_iam_rel.py
            - **Evidence level:** L2
        """,
        )
        result = run_seam_hook(cwd=str(tmp_path))
        assert result.returncode == 0

    def test_fails_when_consumer_import_missing(self, tmp_path):
        """AC5: L2 fails when test imports only producer."""
        write_test_file(
            str(tmp_path),
            "tests/integration/test_iam_rel.py",
            """\
            import pytest
            from venlink.iam import user_service

            @pytest.mark.integration
            def test_membership_lookup():
                pass
        """,
        )
        write_seams(
            str(tmp_path),
            """\
            # Integration Seams

            ## SEAM-002: IAM to Relationships
            - **Producer:** src/venlink/iam/
            - **Consumer:** src/venlink/relationships/
            - **Interface:** UserOrganizationMembership model query
            - **Integration test:** tests/integration/test_iam_rel.py
            - **Evidence level:** L2
        """,
        )
        result = run_seam_hook(cwd=str(tmp_path))
        assert result.returncode == 2
        assert "SEAM-002" in result.stderr
        assert "missing import from consumer" in result.stderr
        assert "venlink.relationships" in result.stderr

    def test_fails_when_producer_import_missing(self, tmp_path):
        """L2 fails when test imports only consumer."""
        write_test_file(
            str(tmp_path),
            "tests/integration/test_iam_rel.py",
            """\
            import pytest
            from venlink.relationships import org_membership

            @pytest.mark.integration
            def test_membership_lookup():
                pass
        """,
        )
        write_seams(
            str(tmp_path),
            """\
            # Integration Seams

            ## SEAM-002: IAM to Relationships
            - **Producer:** src/venlink/iam/
            - **Consumer:** src/venlink/relationships/
            - **Interface:** UserOrganizationMembership model query
            - **Integration test:** tests/integration/test_iam_rel.py
            - **Evidence level:** L2
        """,
        )
        result = run_seam_hook(cwd=str(tmp_path))
        assert result.returncode == 2
        assert "missing import from producer" in result.stderr
        assert "venlink.iam" in result.stderr


# ---------------------------------------------------------------------------
# Test: L3 evidence checks
# ---------------------------------------------------------------------------


class TestL3Evidence:
    def test_passes_with_l3_real_marker_and_no_mocks(self, tmp_path):
        """AC6: L3 passes with L3-real marker and no interface mocks."""
        write_test_file(
            str(tmp_path),
            "tests/integration/test_search.py",
            """\
            import pytest
            from venlink.iam import user_service
            from venlink.search import query_engine

            # seam-evidence: L3-real

            @pytest.mark.integration
            def test_tenant_isolation():
                pass
        """,
        )
        write_seams(
            str(tmp_path),
            """\
            # Integration Seams

            ## SEAM-003: IAM to Search
            - **Producer:** src/venlink/iam/
            - **Consumer:** src/venlink/search/
            - **Interface:** tenant-scoped query filtering
            - **Integration test:** tests/integration/test_search.py
            - **Evidence level:** L3
        """,
        )
        result = run_seam_hook(cwd=str(tmp_path))
        assert result.returncode == 0

    def test_fails_when_l3_real_marker_absent(self, tmp_path):
        """AC7: L3 fails when L3-real marker is absent."""
        write_test_file(
            str(tmp_path),
            "tests/integration/test_search.py",
            """\
            import pytest
            from venlink.iam import user_service
            from venlink.search import query_engine

            @pytest.mark.integration
            def test_tenant_isolation():
                pass
        """,
        )
        write_seams(
            str(tmp_path),
            """\
            # Integration Seams

            ## SEAM-003: IAM to Search
            - **Producer:** src/venlink/iam/
            - **Consumer:** src/venlink/search/
            - **Interface:** tenant-scoped query filtering
            - **Integration test:** tests/integration/test_search.py
            - **Evidence level:** L3
        """,
        )
        result = run_seam_hook(cwd=str(tmp_path))
        assert result.returncode == 2
        assert "SEAM-003" in result.stderr
        assert "L3-real" in result.stderr

    def test_fails_when_producer_is_mocked(self, tmp_path):
        """AC8: L3 fails when producer module is mocked."""
        write_test_file(
            str(tmp_path),
            "tests/integration/test_search.py",
            """\
            import pytest
            from unittest.mock import patch
            from venlink.iam import user_service
            from venlink.search import query_engine

            # seam-evidence: L3-real

            @pytest.mark.integration
            @patch("venlink.iam.user_service.get_user")
            def test_tenant_isolation(mock_get_user):
                pass
        """,
        )
        write_seams(
            str(tmp_path),
            """\
            # Integration Seams

            ## SEAM-003: IAM to Search
            - **Producer:** src/venlink/iam/
            - **Consumer:** src/venlink/search/
            - **Interface:** tenant-scoped query filtering
            - **Integration test:** tests/integration/test_search.py
            - **Evidence level:** L3
        """,
        )
        result = run_seam_hook(cwd=str(tmp_path))
        assert result.returncode == 2
        assert "SEAM-003" in result.stderr
        assert "venlink.iam" in result.stderr
        assert "mocked" in result.stderr

    def test_allows_mocking_unrelated_modules(self, tmp_path):
        """AC9: L3 allows mocking of unrelated modules."""
        write_test_file(
            str(tmp_path),
            "tests/integration/test_search.py",
            """\
            import pytest
            from unittest.mock import patch
            from venlink.iam import user_service
            from venlink.search import query_engine

            # seam-evidence: L3-real

            @pytest.mark.integration
            @patch("stripe.Charge.create")
            def test_tenant_isolation(mock_stripe):
                pass
        """,
        )
        write_seams(
            str(tmp_path),
            """\
            # Integration Seams

            ## SEAM-003: IAM to Search
            - **Producer:** src/venlink/iam/
            - **Consumer:** src/venlink/search/
            - **Interface:** tenant-scoped query filtering
            - **Integration test:** tests/integration/test_search.py
            - **Evidence level:** L3
        """,
        )
        result = run_seam_hook(cwd=str(tmp_path))
        assert result.returncode == 0

    def test_fails_when_consumer_is_mocked(self, tmp_path):
        """L3 fails when consumer module is mocked."""
        write_test_file(
            str(tmp_path),
            "tests/integration/test_search.py",
            """\
            import pytest
            from venlink.iam import user_service
            from venlink.search import query_engine

            # seam-evidence: L3-real

            @pytest.mark.integration
            def test_tenant_isolation(monkeypatch):
                monkeypatch.setattr("venlink.search.query_engine.run", lambda: None)
        """,
        )
        write_seams(
            str(tmp_path),
            """\
            # Integration Seams

            ## SEAM-003: IAM to Search
            - **Producer:** src/venlink/iam/
            - **Consumer:** src/venlink/search/
            - **Interface:** tenant-scoped query filtering
            - **Integration test:** tests/integration/test_search.py
            - **Evidence level:** L3
        """,
        )
        result = run_seam_hook(cwd=str(tmp_path))
        assert result.returncode == 2
        assert "venlink.search" in result.stderr

    def test_inline_l3_marker_not_recognized(self, tmp_path):
        """Edge case 9: Inline L3-real marker does not match."""
        write_test_file(
            str(tmp_path),
            "tests/integration/test_search.py",
            """\
            import pytest
            from venlink.iam import user_service
            from venlink.search import query_engine

            x = 1  # seam-evidence: L3-real

            @pytest.mark.integration
            def test_tenant_isolation():
                pass
        """,
        )
        write_seams(
            str(tmp_path),
            """\
            # Integration Seams

            ## SEAM-003: IAM to Search
            - **Producer:** src/venlink/iam/
            - **Consumer:** src/venlink/search/
            - **Interface:** tenant-scoped query filtering
            - **Integration test:** tests/integration/test_search.py
            - **Evidence level:** L3
        """,
        )
        result = run_seam_hook(cwd=str(tmp_path))
        assert result.returncode == 2
        assert "L3-real" in result.stderr


# ---------------------------------------------------------------------------
# Test: SEAM-DEV entries
# ---------------------------------------------------------------------------


class TestSeamDev:
    def test_seam_dev_entry_with_constraint_is_parsed(self, tmp_path):
        """AC11: SEAM-DEV entry with Constraint field is parsed without error."""
        write_test_file(
            str(tmp_path),
            "tests/integration/test_dev_sim.py",
            """\
            import pytest

            @pytest.mark.integration
            def test_dev_simulation():
                pass
        """,
        )
        write_seams(
            str(tmp_path),
            """\
            # Integration Seams

            ## SEAM-DEV-001: Dev simulation to Approval flow
            - **Producer:** src/venlink/dev/routes.py
            - **Consumer:** src/venlink/relationships/invitation_service.py
            - **Interface:** Dev simulation creates entities
            - **Constraint:** Dev sim MUST create entities with at least 1 admin user
            - **Integration test:** tests/integration/test_dev_sim.py
            - **Evidence level:** L1
        """,
        )
        result = run_seam_hook(cwd=str(tmp_path))
        assert result.returncode == 0

    def test_seam_dev_follows_same_evidence_checks(self, tmp_path):
        """SEAM-DEV entries follow the same L1/L2/L3 checks as standard entries."""
        write_test_file(
            str(tmp_path),
            "tests/integration/test_dev_sim.py",
            """\
            import pytest
            from venlink.dev import routes
            from venlink.relationships import invitation_service

            @pytest.mark.integration
            def test_dev_simulation():
                pass
        """,
        )
        write_seams(
            str(tmp_path),
            """\
            # Integration Seams

            ## SEAM-DEV-001: Dev simulation to Approval flow
            - **Producer:** src/venlink/dev/
            - **Consumer:** src/venlink/relationships/
            - **Interface:** Dev simulation creates entities
            - **Constraint:** Dev sim MUST create entities with at least 1 admin user
            - **Integration test:** tests/integration/test_dev_sim.py
            - **Evidence level:** L2
        """,
        )
        result = run_seam_hook(cwd=str(tmp_path))
        assert result.returncode == 0


# ---------------------------------------------------------------------------
# Test: Multiple seams with partial failure
# ---------------------------------------------------------------------------


class TestMultipleSeams:
    def test_partial_failure_reports_all_failures(self, tmp_path):
        """AC12: Multiple seams where some pass and some fail."""
        # SEAM-001: L1 pass
        write_test_file(
            str(tmp_path),
            "tests/integration/test_one.py",
            """\
            import pytest

            @pytest.mark.integration
            def test_one():
                pass
        """,
        )
        # SEAM-002: L1 fail (file missing)
        # (no test file created)

        # SEAM-003: L3 fail (no L3-real marker)
        write_test_file(
            str(tmp_path),
            "tests/integration/test_three.py",
            """\
            import pytest
            from venlink.iam import user_service
            from venlink.search import query_engine

            @pytest.mark.integration
            def test_three():
                pass
        """,
        )

        write_seams(
            str(tmp_path),
            """\
            # Integration Seams

            ## SEAM-001: First seam (passes)
            - **Producer:** src/a/
            - **Consumer:** src/b/
            - **Interface:** Query
            - **Integration test:** tests/integration/test_one.py
            - **Evidence level:** L1

            ## SEAM-002: Second seam (fails L1)
            - **Producer:** src/c/
            - **Consumer:** src/d/
            - **Interface:** Event
            - **Integration test:** tests/integration/test_missing.py
            - **Evidence level:** L1

            ## SEAM-003: Third seam (fails L3)
            - **Producer:** src/venlink/iam/
            - **Consumer:** src/venlink/search/
            - **Interface:** Filter
            - **Integration test:** tests/integration/test_three.py
            - **Evidence level:** L3
        """,
        )
        result = run_seam_hook(cwd=str(tmp_path))
        assert result.returncode == 2
        assert "SEAM-002" in result.stderr
        assert "SEAM-003" in result.stderr
        # SEAM-001 should NOT appear in failures
        assert "SEAM-001" not in result.stderr

    def test_five_entries_mixed_types_all_parsed(self, tmp_path):
        """AC15: SEAMS.md with 5 entries (3 standard, 2 SEAM-DEV) all parsed."""
        for i in range(1, 6):
            write_test_file(
                str(tmp_path),
                f"tests/integration/test_{i}.py",
                """\
                import pytest

                @pytest.mark.integration
                def test_something():
                    pass
            """,
            )

        write_seams(
            str(tmp_path),
            """\
            # Integration Seams

            ## SEAM-001: First
            - **Producer:** src/a/
            - **Consumer:** src/b/
            - **Interface:** Q
            - **Integration test:** tests/integration/test_1.py
            - **Evidence level:** L1

            ## SEAM-002: Second
            - **Producer:** src/c/
            - **Consumer:** src/d/
            - **Interface:** Q
            - **Integration test:** tests/integration/test_2.py
            - **Evidence level:** L1

            ## SEAM-003: Third
            - **Producer:** src/e/
            - **Consumer:** src/f/
            - **Interface:** Q
            - **Integration test:** tests/integration/test_3.py
            - **Evidence level:** L1

            ## SEAM-DEV-001: Fourth
            - **Producer:** src/g/
            - **Consumer:** src/h/
            - **Interface:** Q
            - **Constraint:** Must match prod
            - **Integration test:** tests/integration/test_4.py
            - **Evidence level:** L1

            ## SEAM-DEV-002: Fifth
            - **Producer:** src/i/
            - **Consumer:** src/j/
            - **Interface:** Q
            - **Constraint:** Must match prod
            - **Integration test:** tests/integration/test_5.py
            - **Evidence level:** L1
        """,
        )
        result = run_seam_hook(cwd=str(tmp_path))
        assert result.returncode == 0


# ---------------------------------------------------------------------------
# Test: Malformed entries
# ---------------------------------------------------------------------------


class TestMalformedEntries:
    def test_missing_required_field_skips_entry(self, tmp_path):
        """Edge case 7: Missing required field warns and skips."""
        write_test_file(
            str(tmp_path),
            "tests/integration/test_good.py",
            """\
            import pytest

            @pytest.mark.integration
            def test_good():
                pass
        """,
        )
        write_seams(
            str(tmp_path),
            """\
            # Integration Seams

            ## SEAM-001: Good entry
            - **Producer:** src/a/
            - **Consumer:** src/b/
            - **Interface:** Q
            - **Integration test:** tests/integration/test_good.py
            - **Evidence level:** L1

            ## SEAM-003: Bad entry missing evidence level
            - **Producer:** src/c/
            - **Consumer:** src/d/
            - **Interface:** Q
            - **Integration test:** tests/integration/test_missing.py
        """,
        )
        result = run_seam_hook(cwd=str(tmp_path))
        # Should pass (SEAM-001 OK, SEAM-003 skipped with warning)
        assert result.returncode == 0
        assert "SEAM-003" in result.stderr
        assert "missing required field" in result.stderr

    def test_unknown_evidence_level_skips(self, tmp_path):
        """Edge case 5: Unknown evidence level warns and skips."""
        write_test_file(
            str(tmp_path),
            "tests/integration/test_foo.py",
            """\
            import pytest

            @pytest.mark.integration
            def test_foo():
                pass
        """,
        )
        write_seams(
            str(tmp_path),
            """\
            # Integration Seams

            ## SEAM-005: Future evidence level
            - **Producer:** src/a/
            - **Consumer:** src/b/
            - **Interface:** Q
            - **Integration test:** tests/integration/test_foo.py
            - **Evidence level:** L4
        """,
        )
        result = run_seam_hook(cwd=str(tmp_path))
        assert result.returncode == 0
        assert "Unknown evidence level" in result.stderr
        assert "L4" in result.stderr

    def test_malformed_seams_does_not_block(self, tmp_path):
        """Malformed SEAMS.md (no headings) does not block."""
        seams_path = os.path.join(str(tmp_path), "SEAMS.md")
        with open(seams_path, "w") as f:
            f.write("Random text, no seam headings\n")
        result = run_seam_hook(cwd=str(tmp_path))
        assert result.returncode == 0


# ---------------------------------------------------------------------------
# Test: Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_test_file_fails_l1(self, tmp_path):
        """Edge case 6: Empty test file fails L1 (no marker)."""
        write_test_file(
            str(tmp_path),
            "tests/integration/test_empty.py",
            "",
        )
        write_seams(
            str(tmp_path),
            """\
            # Integration Seams

            ## SEAM-001: Empty test
            - **Producer:** src/a/
            - **Consumer:** src/b/
            - **Interface:** Q
            - **Integration test:** tests/integration/test_empty.py
            - **Evidence level:** L1
        """,
        )
        result = run_seam_hook(cwd=str(tmp_path))
        assert result.returncode == 2
        assert "no @pytest.mark.integration marker" in result.stderr

    def test_two_seams_same_test_file(self, tmp_path):
        """Edge case 4: Two seams pointing to the same test file."""
        write_test_file(
            str(tmp_path),
            "tests/integration/test_shared.py",
            """\
            import pytest

            @pytest.mark.integration
            def test_shared():
                pass
        """,
        )
        write_seams(
            str(tmp_path),
            """\
            # Integration Seams

            ## SEAM-001: First seam using shared test
            - **Producer:** src/a/
            - **Consumer:** src/b/
            - **Interface:** Q
            - **Integration test:** tests/integration/test_shared.py
            - **Evidence level:** L1

            ## SEAM-002: Second seam using shared test
            - **Producer:** src/c/
            - **Consumer:** src/d/
            - **Interface:** Q
            - **Integration test:** tests/integration/test_shared.py
            - **Evidence level:** L1
        """,
        )
        result = run_seam_hook(cwd=str(tmp_path))
        assert result.returncode == 0

    def test_src_prefix_stripped_for_import_check(self, tmp_path):
        """Edge case 8: src/ prefix is stripped for import checking."""
        write_test_file(
            str(tmp_path),
            "tests/integration/test_iam.py",
            """\
            import pytest
            from venlink.iam import service
            from venlink.search import engine

            @pytest.mark.integration
            def test_iam():
                pass
        """,
        )
        write_seams(
            str(tmp_path),
            """\
            # Integration Seams

            ## SEAM-001: IAM to Search
            - **Producer:** src/venlink/iam/
            - **Consumer:** src/venlink/search/
            - **Interface:** Query
            - **Integration test:** tests/integration/test_iam.py
            - **Evidence level:** L2
        """,
        )
        result = run_seam_hook(cwd=str(tmp_path))
        assert result.returncode == 0

    def test_import_style_with_import_keyword(self, tmp_path):
        """L2 recognizes 'import pkg' style imports (not just 'from pkg')."""
        write_test_file(
            str(tmp_path),
            "tests/integration/test_iam.py",
            """\
            import pytest
            import venlink.iam
            import venlink.search

            @pytest.mark.integration
            def test_iam():
                pass
        """,
        )
        write_seams(
            str(tmp_path),
            """\
            # Integration Seams

            ## SEAM-001: IAM to Search
            - **Producer:** src/venlink/iam/
            - **Consumer:** src/venlink/search/
            - **Interface:** Query
            - **Integration test:** tests/integration/test_iam.py
            - **Evidence level:** L2
        """,
        )
        result = run_seam_hook(cwd=str(tmp_path))
        assert result.returncode == 0
