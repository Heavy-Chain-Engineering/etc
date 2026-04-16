#!/usr/bin/env python3
"""Tests for scripts/check-vocabulary.py — vocabulary consistency verification.

Validates that the vocabulary checker parses markdown tables from
INVARIANTS.md, scans context directories for term violations, and
respects exemption patterns.
"""

import os
import subprocess
import textwrap



SCRIPT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "scripts",
    "check-vocabulary.py",
)


def run_vocab_check(
    vocab_name: str,
    invariants_path: str | None = None,
    project_root: str | None = None,
    concept_id: str | None = None,
) -> subprocess.CompletedProcess:
    """Run check-vocabulary.py with the given arguments."""
    cmd = ["python3", SCRIPT_PATH, vocab_name]
    if invariants_path:
        cmd.extend(["--invariants", invariants_path])
    if project_root:
        cmd.extend(["--project-root", project_root])
    if concept_id:
        cmd.extend(["--concept-id", concept_id])
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=15,
    )


def write_invariants_with_vocab(directory: str, content: str) -> str:
    """Write an INVARIANTS.md with vocabulary content."""
    path = os.path.join(directory, "INVARIANTS.md")
    with open(path, "w") as f:
        f.write(textwrap.dedent(content))
    return path


# ---------------------------------------------------------------------------
# Test: Vocabulary violation detection (AC5)
# ---------------------------------------------------------------------------


class TestVocabularyViolations:
    def test_detects_undeclared_term(self, tmp_path):
        """Script should flag terms used in a context that are not in its vocabulary."""
        # Create context directory with a file using wrong term
        ctx_dir = tmp_path / "src" / "salesforce_etl"
        ctx_dir.mkdir(parents=True)
        (ctx_dir / "mapper.py").write_text(
            'status = "suspended"  # wrong term for this context\n'
        )

        inv_path = write_invariants_with_vocab(
            str(tmp_path),
            """\
            # Invariants

            ## CONCEPT-002: Vendor status vocabulary
            - **Contexts:** Salesforce ETL, Internal API
            - **Precondition:** Status values from declared terms
            - **Postcondition:** Database uses canonical terms
            - **Invariant:** No undeclared status terms
            - **Layers:** test
            - **Verify:** `python3 scripts/check-vocabulary.py vendor_status`
            - **Fail action:** Block merge

            ### Vocabulary: test_status
            | Context | Term | Canonical |
            |---------|------|-----------|
            | Salesforce ETL | "approved" | active |
            | Salesforce ETL | "onboarding" | pending |
            | Internal API | "active" | active |
            | Internal API | "suspended" | suspended |
        """,
        )

        result = run_vocab_check(
            "test_status",
            invariants_path=inv_path,
            project_root=str(tmp_path),
        )
        assert result.returncode == 1
        assert "suspended" in result.stdout
        assert "Salesforce ETL" in result.stdout

    def test_detects_violation_from_venlink_example(self, tmp_path):
        """VenLink CONCEPT-002 scenario: ETL uses wrong term (AC12)."""
        ctx_dir = tmp_path / "src" / "salesforce_etl"
        ctx_dir.mkdir(parents=True)
        # ETL code uses "active" but that's an Internal API term, not declared for ETL
        (ctx_dir / "transform.py").write_text(
            'mapped_status = "active"\n'
        )

        inv_path = write_invariants_with_vocab(
            str(tmp_path),
            """\
            # Invariants

            ## CONCEPT-002: Vendor status vocabulary
            - **Contexts:** Salesforce ETL, Internal API
            - **Precondition:** Status values from declared terms
            - **Postcondition:** Database uses canonical terms
            - **Invariant:** No undeclared status terms
            - **Layers:** test
            - **Verify:** `python3 scripts/check-vocabulary.py vendor_status`
            - **Fail action:** Block merge

            ### Vocabulary: venlink_status
            | Context | Term | Canonical |
            |---------|------|-----------|
            | Salesforce ETL | "approved" | active |
            | Salesforce ETL | "onboarding" | pending |
            | Internal API | "active" | active |
            | Internal API | "suspended" | suspended |
        """,
        )

        result = run_vocab_check(
            "venlink_status",
            invariants_path=inv_path,
            project_root=str(tmp_path),
        )
        assert result.returncode == 1
        assert "active" in result.stdout
        assert "Salesforce ETL" in result.stdout


# ---------------------------------------------------------------------------
# Test: Clean vocabulary passes (AC6)
# ---------------------------------------------------------------------------


class TestVocabularyPassing:
    def test_passes_when_context_uses_only_declared_terms(self, tmp_path):
        """Script should exit 0 when all contexts use only their declared terms."""
        ctx_dir = tmp_path / "src" / "internal_api"
        ctx_dir.mkdir(parents=True)
        (ctx_dir / "status.py").write_text(
            'STATUS = "active"\nOTHER = "suspended"\n'
        )

        inv_path = write_invariants_with_vocab(
            str(tmp_path),
            """\
            # Invariants

            ## CONCEPT-002: Status vocabulary
            - **Contexts:** Internal API
            - **Precondition:** N/A
            - **Postcondition:** N/A
            - **Invariant:** Valid terms only
            - **Layers:** test
            - **Verify:** `python3 scripts/check-vocabulary.py clean_status`
            - **Fail action:** Block merge

            ### Vocabulary: clean_status
            | Context | Term | Canonical |
            |---------|------|-----------|
            | Internal API | "active" | active |
            | Internal API | "suspended" | suspended |
        """,
        )

        result = run_vocab_check(
            "clean_status",
            invariants_path=inv_path,
            project_root=str(tmp_path),
        )
        assert result.returncode == 0
        assert result.stdout.strip() == ""


# ---------------------------------------------------------------------------
# Test: Exemption pattern
# ---------------------------------------------------------------------------


class TestExemption:
    def test_concept_exempt_skips_line(self, tmp_path):
        """Lines with # concept-exempt: CONCEPT-NNN are skipped."""
        ctx_dir = tmp_path / "src" / "salesforce_etl"
        ctx_dir.mkdir(parents=True)
        (ctx_dir / "mapper.py").write_text(
            'status = "suspended"  # concept-exempt: CONCEPT-002\n'
        )

        inv_path = write_invariants_with_vocab(
            str(tmp_path),
            """\
            # Invariants

            ### Vocabulary: exempt_status
            | Context | Term | Canonical |
            |---------|------|-----------|
            | Salesforce ETL | "approved" | active |
            | Internal API | "active" | active |
            | Internal API | "suspended" | suspended |
        """,
        )

        result = run_vocab_check(
            "exempt_status",
            invariants_path=inv_path,
            project_root=str(tmp_path),
            concept_id="CONCEPT-002",
        )
        assert result.returncode == 0
        assert result.stdout.strip() == ""


# ---------------------------------------------------------------------------
# Test: Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_vocabulary_table(self, tmp_path):
        """Empty vocabulary table = no constraints = pass."""
        inv_path = write_invariants_with_vocab(
            str(tmp_path),
            """\
            # Invariants

            ### Vocabulary: empty_vocab
            | Context | Term | Canonical |
            |---------|------|-----------|
        """,
        )

        result = run_vocab_check(
            "empty_vocab",
            invariants_path=inv_path,
            project_root=str(tmp_path),
        )
        assert result.returncode == 0

    def test_missing_vocabulary_name(self, tmp_path):
        """Nonexistent vocabulary name = no constraints = pass."""
        inv_path = write_invariants_with_vocab(
            str(tmp_path),
            """\
            # Invariants

            ### Vocabulary: some_other_vocab
            | Context | Term | Canonical |
            |---------|------|-----------|
            | A | "x" | y |
        """,
        )

        result = run_vocab_check(
            "nonexistent_vocab",
            invariants_path=inv_path,
            project_root=str(tmp_path),
        )
        assert result.returncode == 0

    def test_missing_context_directory(self, tmp_path):
        """Missing context directory emits warning but doesn't fail."""
        inv_path = write_invariants_with_vocab(
            str(tmp_path),
            """\
            # Invariants

            ### Vocabulary: missing_ctx
            | Context | Term | Canonical |
            |---------|------|-----------|
            | Nonexistent Context | "foo" | bar |
        """,
        )

        result = run_vocab_check(
            "missing_ctx",
            invariants_path=inv_path,
            project_root=str(tmp_path),
        )
        assert result.returncode == 0
        assert "WARNING" in result.stderr

    def test_no_invariants_file(self, tmp_path):
        """No INVARIANTS.md anywhere = pass."""
        result = run_vocab_check(
            "any_vocab",
            invariants_path=str(tmp_path / "INVARIANTS.md"),
            project_root=str(tmp_path),
        )
        # Should not crash — file doesn't exist, warning expected
        # The script handles this gracefully
        assert result.returncode == 0 or "WARNING" in result.stderr

    def test_word_boundary_matching(self, tmp_path):
        """Term 'active' should not match 'inactive' (word boundary)."""
        ctx_dir = tmp_path / "src" / "internal_api"
        ctx_dir.mkdir(parents=True)
        # "inactive" contains "active" as a substring but should NOT match
        (ctx_dir / "status.py").write_text(
            'STATUS = "inactive"\n'
        )

        inv_path = write_invariants_with_vocab(
            str(tmp_path),
            """\
            # Invariants

            ### Vocabulary: boundary_test
            | Context | Term | Canonical |
            |---------|------|-----------|
            | Internal API | "inactive" | inactive |
            | Other | "active" | active |
        """,
        )

        result = run_vocab_check(
            "boundary_test",
            invariants_path=inv_path,
            project_root=str(tmp_path),
        )
        # "inactive" is in Internal API's declared terms, so no violation
        # "active" as a disallowed term should NOT match "inactive" (word boundary)
        assert result.returncode == 0
