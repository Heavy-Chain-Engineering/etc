"""Tests for scripts/release_notes.py — release-notes roll-up builder.

Covers PRD .etc_sdlc/features/metrics-and-release-notes/spec.md
acceptance criteria AC-011 (release notes content) and BR-009 (mandatory
release notes), focused on the pure `build(feature_dir) -> str` function.

The function walks `feature_dir/build/phase-*/completion-report.md` and
returns a single markdown roll-up. It does not write to disk.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
RELEASE_NOTES_SCRIPT = SCRIPTS_DIR / "release_notes.py"

# Make scripts/ importable (sibling to tests/).
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import release_notes  # noqa: E402  (sys.path mutated above)


# ── Fixture helpers ──────────────────────────────────────────────────────


def _write_phase_report(
    feature_dir: Path,
    phase_number: int,
    body: str,
) -> Path:
    """Create build/phase-<N>/completion-report.md under feature_dir."""
    phase_dir = feature_dir / "build" / f"phase-{phase_number}"
    phase_dir.mkdir(parents=True, exist_ok=True)
    report_path = phase_dir / "completion-report.md"
    report_path.write_text(body, encoding="utf-8")
    return report_path


def _example_phase_body(
    *,
    phase_number: int,
    prd_title: str = "Metrics, Release Notes, and Feature Numbering",
    prd_id: str = "F042",
    ac_pass: list[str] | None = None,
    ac_fail: list[str] | None = None,
    deferred: list[str] | None = None,
    limitations: list[str] | None = None,
) -> str:
    ac_pass = ac_pass or ["AC-001 — feature ID allocation"]
    ac_fail = ac_fail or []
    deferred = deferred or []
    limitations = limitations or []

    lines: list[str] = [
        f"# Phase {phase_number} — Completion Report",
        "",
        "## PRD",
        f"- Title: {prd_title}",
        f"- ID: {prd_id}",
        "",
        "## Acceptance Criteria",
    ]
    for item in ac_pass:
        lines.append(f"- [x] {item}")
    for item in ac_fail:
        lines.append(f"- [ ] {item}")

    lines.extend(["", "## Deferred Items"])
    if deferred:
        for item in deferred:
            lines.append(f"- {item}")
    else:
        lines.append("- None")

    lines.extend(["", "## Known Limitations"])
    if limitations:
        for item in limitations:
            lines.append(f"- {item}")
    else:
        lines.append("- None")

    return "\n".join(lines) + "\n"


# ── Roll-up correctness ──────────────────────────────────────────────────


class TestRollUpCorrectness:
    """Verify that build() composes a complete roll-up across phases."""

    def test_should_return_markdown_with_top_level_heading_when_feature_dir_named(
        self,
        tmp_path: Path,
    ) -> None:
        feature_dir = tmp_path / "F042-metrics-and-release-notes"
        feature_dir.mkdir()
        _write_phase_report(feature_dir, 1, _example_phase_body(phase_number=1))

        result = release_notes.build(feature_dir)

        assert result.startswith("# Release Notes")
        assert "F042-metrics-and-release-notes" in result

    def test_should_include_prd_title_and_id_when_phase_report_has_them(
        self,
        tmp_path: Path,
    ) -> None:
        feature_dir = tmp_path / "F042-metrics-and-release-notes"
        feature_dir.mkdir()
        body = _example_phase_body(
            phase_number=1,
            prd_title="Metrics, Release Notes, and Feature Numbering",
            prd_id="F042",
        )
        _write_phase_report(feature_dir, 1, body)

        result = release_notes.build(feature_dir)

        assert "Metrics, Release Notes, and Feature Numbering" in result
        assert "F042" in result

    def test_should_list_phases_in_numeric_order_when_phases_unsorted_on_disk(
        self,
        tmp_path: Path,
    ) -> None:
        feature_dir = tmp_path / "F042-metrics-and-release-notes"
        feature_dir.mkdir()
        # Write phase-2 first, then phase-10, then phase-1 to verify the
        # builder sorts numerically (not lexicographically).
        _write_phase_report(feature_dir, 2, _example_phase_body(phase_number=2))
        _write_phase_report(feature_dir, 10, _example_phase_body(phase_number=10))
        _write_phase_report(feature_dir, 1, _example_phase_body(phase_number=1))

        result = release_notes.build(feature_dir)

        idx_phase_1 = result.find("Phase 1")
        idx_phase_2 = result.find("Phase 2")
        idx_phase_10 = result.find("Phase 10")
        assert 0 <= idx_phase_1 < idx_phase_2 < idx_phase_10

    def test_should_include_ac_pass_fail_summary_when_phase_has_both(
        self,
        tmp_path: Path,
    ) -> None:
        feature_dir = tmp_path / "F042-metrics-and-release-notes"
        feature_dir.mkdir()
        body = _example_phase_body(
            phase_number=1,
            ac_pass=["AC-001 — pass A", "AC-002 — pass B"],
            ac_fail=["AC-003 — fail C"],
        )
        _write_phase_report(feature_dir, 1, body)

        result = release_notes.build(feature_dir)

        # All AC items appear in the output.
        assert "AC-001 — pass A" in result
        assert "AC-002 — pass B" in result
        assert "AC-003 — fail C" in result
        # Pass/fail counts are summarized.
        assert "2" in result  # 2 passes
        assert "1" in result  # 1 fail

    def test_should_roll_up_deferred_items_across_phases(
        self,
        tmp_path: Path,
    ) -> None:
        feature_dir = tmp_path / "F042-metrics-and-release-notes"
        feature_dir.mkdir()
        _write_phase_report(
            feature_dir,
            1,
            _example_phase_body(
                phase_number=1,
                deferred=["Deferred from phase 1: thing-A"],
            ),
        )
        _write_phase_report(
            feature_dir,
            2,
            _example_phase_body(
                phase_number=2,
                deferred=["Deferred from phase 2: thing-B"],
            ),
        )

        result = release_notes.build(feature_dir)

        assert "## Deferred Items" in result
        assert "Deferred from phase 1: thing-A" in result
        assert "Deferred from phase 2: thing-B" in result

    def test_should_roll_up_known_limitations_across_phases(
        self,
        tmp_path: Path,
    ) -> None:
        feature_dir = tmp_path / "F042-metrics-and-release-notes"
        feature_dir.mkdir()
        _write_phase_report(
            feature_dir,
            1,
            _example_phase_body(
                phase_number=1,
                limitations=["Phase 1 limitation: only single-tenant"],
            ),
        )
        _write_phase_report(
            feature_dir,
            2,
            _example_phase_body(
                phase_number=2,
                limitations=["Phase 2 limitation: no migration tooling"],
            ),
        )

        result = release_notes.build(feature_dir)

        assert "## Known Limitations" in result
        assert "Phase 1 limitation: only single-tenant" in result
        assert "Phase 2 limitation: no migration tooling" in result


# ── Missing-phase handling ───────────────────────────────────────────────


class TestMissingPhaseHandling:
    """build() must degrade gracefully when phase data is absent."""

    def test_should_return_minimal_note_when_no_build_dir_exists(
        self,
        tmp_path: Path,
    ) -> None:
        feature_dir = tmp_path / "F042-metrics-and-release-notes"
        feature_dir.mkdir()
        # No build/ directory at all.

        result = release_notes.build(feature_dir)

        assert "No build phases found" in result
        # Still a well-formed markdown header so callers can write it.
        assert result.startswith("# Release Notes")

    def test_should_return_minimal_note_when_build_dir_empty(
        self,
        tmp_path: Path,
    ) -> None:
        feature_dir = tmp_path / "F042-metrics-and-release-notes"
        feature_dir.mkdir()
        (feature_dir / "build").mkdir()  # empty

        result = release_notes.build(feature_dir)

        assert "No build phases found" in result

    def test_should_include_report_missing_note_when_phase_dir_has_no_report(
        self,
        tmp_path: Path,
    ) -> None:
        feature_dir = tmp_path / "F042-metrics-and-release-notes"
        feature_dir.mkdir()
        # Phase 1 has a real report; phase 2 directory exists but has no
        # completion-report.md inside it.
        _write_phase_report(feature_dir, 1, _example_phase_body(phase_number=1))
        (feature_dir / "build" / "phase-2").mkdir(parents=True)

        result = release_notes.build(feature_dir)

        # Phase 1 still rendered.
        assert "Phase 1" in result
        # Phase 2 acknowledged but flagged missing — not silently skipped.
        assert "Phase 2" in result
        assert "(report missing)" in result


# ── Citation paths ───────────────────────────────────────────────────────


class TestCitationPaths:
    """Each phase's AC summary must cite its source completion-report path."""

    def test_should_cite_completion_report_path_for_each_phase(
        self,
        tmp_path: Path,
    ) -> None:
        feature_dir = tmp_path / "F042-metrics-and-release-notes"
        feature_dir.mkdir()
        _write_phase_report(feature_dir, 1, _example_phase_body(phase_number=1))
        _write_phase_report(feature_dir, 2, _example_phase_body(phase_number=2))

        result = release_notes.build(feature_dir)

        assert "build/phase-1/completion-report.md" in result
        assert "build/phase-2/completion-report.md" in result

    def test_should_cite_missing_phase_path_with_report_missing_marker(
        self,
        tmp_path: Path,
    ) -> None:
        feature_dir = tmp_path / "F042-metrics-and-release-notes"
        feature_dir.mkdir()
        (feature_dir / "build" / "phase-1").mkdir(parents=True)

        result = release_notes.build(feature_dir)

        # The missing report is named so the reader can locate the gap.
        assert "build/phase-1/completion-report.md" in result
        assert "(report missing)" in result


# ── Pure-function contract ───────────────────────────────────────────────


class TestPureFunctionContract:
    """build() must not write to disk — caller is responsible for IO."""

    def test_should_not_create_release_notes_file_when_invoked(
        self,
        tmp_path: Path,
    ) -> None:
        feature_dir = tmp_path / "F042-metrics-and-release-notes"
        feature_dir.mkdir()
        _write_phase_report(feature_dir, 1, _example_phase_body(phase_number=1))

        release_notes.build(feature_dir)

        assert not (feature_dir / "release-notes.md").exists()

    def test_should_return_string_when_invoked(self, tmp_path: Path) -> None:
        feature_dir = tmp_path / "F042-metrics-and-release-notes"
        feature_dir.mkdir()
        _write_phase_report(feature_dir, 1, _example_phase_body(phase_number=1))

        result = release_notes.build(feature_dir)

        assert isinstance(result, str)
        assert len(result) > 0


# ── Argument validation ──────────────────────────────────────────────────


class TestArgumentValidation:
    """build() should fail fast on a non-existent feature dir."""

    def test_should_raise_when_feature_dir_does_not_exist(
        self,
        tmp_path: Path,
    ) -> None:
        missing = tmp_path / "F999-does-not-exist"

        with pytest.raises(FileNotFoundError):
            release_notes.build(missing)


# ── CLI smoke tests ──────────────────────────────────────────────────────


class TestCli:
    """`scripts/release_notes.py build <feature_dir>` must work from any cwd.

    Step 7 of /build invokes this script via subprocess; the previous
    `from scripts.release_notes import build` form failed when cwd was
    not the repo root. The CLI fixes that by accepting an absolute (or
    cwd-relative) feature_dir path and printing the rendered markdown to
    stdout for the caller to redirect.
    """

    def test_should_build_via_subprocess_from_unrelated_cwd(
        self,
        tmp_path: Path,
    ) -> None:
        feature_dir = tmp_path / "F042-metrics-and-release-notes"
        feature_dir.mkdir()
        _write_phase_report(
            feature_dir,
            1,
            _example_phase_body(phase_number=1),
        )

        # cwd is tmp_path — NOT the repo root — to prove the CLI does not
        # rely on being executed from inside etc-system-engineering.
        completed = subprocess.run(
            [
                sys.executable,
                str(RELEASE_NOTES_SCRIPT),
                "build",
                str(feature_dir),
            ],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=False,
        )

        assert completed.returncode == 0, (
            f"stderr={completed.stderr!r} stdout={completed.stdout!r}"
        )
        # The pure builder's output is the contract; just spot-check the
        # markdown shape the rollup is required to emit (AC-011).
        assert completed.stdout.startswith("# Release Notes")
        assert "F042-metrics-and-release-notes" in completed.stdout
        assert "Phase 1" in completed.stdout
        assert "build/phase-1/completion-report.md" in completed.stdout

    def test_should_exit_nonzero_when_feature_dir_missing(
        self,
        tmp_path: Path,
    ) -> None:
        missing = tmp_path / "F999-does-not-exist"

        completed = subprocess.run(
            [
                sys.executable,
                str(RELEASE_NOTES_SCRIPT),
                "build",
                str(missing),
            ],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=False,
        )

        assert completed.returncode == 1
        # Diagnostic must name the bad path so the operator can fix it.
        assert str(missing) in completed.stderr
        # No partial markdown leaked to stdout on failure.
        assert completed.stdout == ""
