"""Contract tests for scripts/completion_report.py — F005 BR-007.

Covers PRD .etc_sdlc/features/F005-build-completion-reports/spec.md
acceptance criteria AC8-AC10 via:

- Format-shape grep tests over a report written by ``completion_report.py``.
- A round-trip integration test that writes a report via the helper and
  reads it back via ``release_notes.build()`` to prove the writer/reader
  contract aligns.
- A grep test over ``dist/skills/build/SKILL.md`` Step 6d region asserting
  the new ``6d.5`` sub-step documents the helper invocation.

Precedent: tests/test_release_notes.py (sys.path manipulation, tmp_path
report fixtures) + tests/test_user_flow_completeness.py (shared
session-scoped ``compiled_dist`` fixture, grep-based contract assertions
over committed source plus compiled dist/ outputs).

Path-traversal-guard workaround: ``completion_report.py`` resolves
``--feature-dir`` against ``<cwd>/.etc_sdlc/features`` and refuses paths
outside that prefix. Tests work around this by invoking the helper via
subprocess with ``cwd=tmp_path`` and creating the feature dir under
``<tmp_path>/.etc_sdlc/features/F999-test/`` so the resolved feature dir
is a descendant of the resolved allowed root.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
COMPLETION_REPORT_SCRIPT = SCRIPTS_DIR / "completion_report.py"
BUILD_SKILL_REL = Path("skills") / "build" / "SKILL.md"

# Make scripts/ importable (sibling to tests/).
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import release_notes  # pyright: ignore[reportMissingImports]  # noqa: E402

# ── Module-scoped text fixtures ──────────────────────────────────────────

# Compiled artifacts are read from the shared session-scoped ``compiled_dist``
# fixture (conftest.py), which compiles into a tmp dir — the operator's real
# dist/ is never read or mutated by this suite.


@pytest.fixture(scope="module")
def build_skill_dist_text(compiled_dist: Path) -> str:
    path = compiled_dist / BUILD_SKILL_REL
    assert path.exists(), (
        f"missing compiled skill: {path}; "
        "the shared compiled_dist fixture should have created it"
    )
    return path.read_text(encoding="utf-8")


# ── Helpers for the path-traversal-guard workaround ──────────────────────


def _make_feature_dir(tmp_path: Path, slug: str = "F999-test") -> Path:
    """Create ``<tmp_path>/.etc_sdlc/features/<slug>/`` and return its path.

    The helper's path-traversal guard resolves ``<cwd>/.etc_sdlc/features``
    and requires the resolved feature dir to live under that prefix. By
    running the helper with ``cwd=tmp_path`` and placing the feature dir
    under ``<tmp_path>/.etc_sdlc/features/``, the guard accepts the path
    without us touching the real ``.etc_sdlc/features/`` tree.
    """
    feature_dir = tmp_path / ".etc_sdlc" / "features" / slug
    feature_dir.mkdir(parents=True, exist_ok=True)
    return feature_dir


def _write_bullet_file(path: Path, lines: list[str]) -> Path:
    """Write a newline-delimited bullet file (one bullet per line)."""
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return path


def _invoke_write(
    *,
    cwd: Path,
    feature_dir: Path,
    phase: int,
    prd_title: str,
    prd_id: str,
    ac_passed_file: Path,
    ac_failed_file: Path,
    deferred_file: Path,
    limitations_file: Path,
) -> subprocess.CompletedProcess[str]:
    """Run ``completion_report.py write`` via subprocess with ``cwd``.

    Mirrors ``tests/test_release_notes.py::TestCli`` invocation pattern:
    use ``sys.executable`` so the test inherits the active interpreter,
    pass ``cwd`` so the helper's path-traversal guard resolves correctly,
    and capture stdout/stderr for diagnostic assertions on failure.
    """
    return subprocess.run(
        [
            sys.executable,
            str(COMPLETION_REPORT_SCRIPT),
            "write",
            "--feature-dir",
            str(feature_dir),
            "--phase",
            str(phase),
            "--prd-title",
            prd_title,
            "--prd-id",
            prd_id,
            "--ac-passed-file",
            str(ac_passed_file),
            "--ac-failed-file",
            str(ac_failed_file),
            "--deferred-file",
            str(deferred_file),
            "--limitations-file",
            str(limitations_file),
        ],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )


# ── BR-007 contract tests ────────────────────────────────────────────────


def test_completion_report_writes_expected_format(tmp_path: Path) -> None:
    """AC8 / BR-002: the helper writes a report whose body contains the
    canonical heading, the four sections, and ``- [x]``/``- [ ]`` checkbox
    formatting.
    """
    feature_dir = _make_feature_dir(tmp_path, "F999-format-shape")
    inputs_dir = tmp_path / "inputs"
    inputs_dir.mkdir()

    ac_passed_file = _write_bullet_file(
        inputs_dir / "ac_passed.txt",
        ["AC-001 — passed assertion alpha", "AC-002 — passed assertion beta"],
    )
    ac_failed_file = _write_bullet_file(
        inputs_dir / "ac_failed.txt",
        ["AC-099 — known failing assertion"],
    )
    deferred_file = _write_bullet_file(
        inputs_dir / "deferred.txt",
        ["AC-007 surface_status: deferred — operator review"],
    )
    limitations_file = _write_bullet_file(
        inputs_dir / "limitations.txt",
        ["Single-tenant only in this phase"],
    )

    completed = _invoke_write(
        cwd=tmp_path,
        feature_dir=feature_dir,
        phase=2,
        prd_title="Build Completion Reports",
        prd_id="F005",
        ac_passed_file=ac_passed_file,
        ac_failed_file=ac_failed_file,
        deferred_file=deferred_file,
        limitations_file=limitations_file,
    )

    assert completed.returncode == 0, (
        f"helper failed: stderr={completed.stderr!r} stdout={completed.stdout!r}"
    )

    report_path = feature_dir / "build" / "phase-2" / "completion-report.md"
    assert report_path.is_file(), (
        f"completion-report.md was not written at {report_path}"
    )
    body = report_path.read_text(encoding="utf-8")

    # Top-level heading "# Phase N — <title>".
    expected_heading = "# Phase 2 — Build Completion Reports"
    assert expected_heading in body, (
        f"missing top heading: {expected_heading!r}; got body={body!r}"
    )

    # ## PRD section with title + ID bullets.
    assert "## PRD" in body, "missing '## PRD' section header"
    assert "- Title: Build Completion Reports" in body, (
        "missing PRD title bullet '- Title: Build Completion Reports'"
    )
    assert "- ID: F005" in body, "missing PRD id bullet '- ID: F005'"

    # ## Acceptance Criteria with both checkbox states.
    assert "## Acceptance Criteria" in body, (
        "missing '## Acceptance Criteria' section header"
    )
    assert "- [x] AC-001 — passed assertion alpha" in body, (
        "missing passed AC checkbox '- [x] AC-001 — passed assertion alpha'"
    )
    assert "- [x] AC-002 — passed assertion beta" in body, (
        "missing passed AC checkbox '- [x] AC-002 — passed assertion beta'"
    )
    assert "- [ ] AC-099 — known failing assertion" in body, (
        "missing failed AC checkbox '- [ ] AC-099 — known failing assertion'"
    )

    # ## Deferred Items with the operator-supplied bullet.
    assert "## Deferred Items" in body, (
        "missing '## Deferred Items' section header"
    )
    assert "- AC-007 surface_status: deferred — operator review" in body, (
        "missing deferred-items bullet"
    )

    # ## Known Limitations with the operator-supplied bullet.
    assert "## Known Limitations" in body, (
        "missing '## Known Limitations' section header"
    )
    assert "- Single-tenant only in this phase" in body, (
        "missing known-limitations bullet"
    )


def test_completion_report_creates_phase_directory(tmp_path: Path) -> None:
    """AC8: the helper creates ``<feature_dir>/build/phase-<N>/`` if absent."""
    feature_dir = _make_feature_dir(tmp_path, "F999-mkdir")
    inputs_dir = tmp_path / "inputs"
    inputs_dir.mkdir()

    ac_passed_file = _write_bullet_file(inputs_dir / "ac_passed.txt", ["AC-1 — ok"])
    ac_failed_file = _write_bullet_file(inputs_dir / "ac_failed.txt", [])
    deferred_file = _write_bullet_file(inputs_dir / "deferred.txt", [])
    limitations_file = _write_bullet_file(inputs_dir / "limitations.txt", [])

    # Pre-condition: build/phase-3/ does NOT exist.
    phase_dir = feature_dir / "build" / "phase-3"
    assert not phase_dir.exists(), (
        f"precondition violated: {phase_dir} should not pre-exist"
    )

    completed = _invoke_write(
        cwd=tmp_path,
        feature_dir=feature_dir,
        phase=3,
        prd_title="Phase Dir Creation",
        prd_id="F999",
        ac_passed_file=ac_passed_file,
        ac_failed_file=ac_failed_file,
        deferred_file=deferred_file,
        limitations_file=limitations_file,
    )

    assert completed.returncode == 0, (
        f"helper failed: stderr={completed.stderr!r} stdout={completed.stdout!r}"
    )
    assert phase_dir.is_dir(), (
        f"helper did not create phase directory at {phase_dir}"
    )
    report_path = phase_dir / "completion-report.md"
    assert report_path.is_file(), (
        f"helper did not write completion-report.md at {report_path}"
    )


def test_completion_report_accepts_phase_zero(tmp_path: Path) -> None:
    """#43: phase 0 is the flat-fallback phase introduced by the phase→wave
    decoupling (#35). ``--phase 0`` MUST be accepted and write to
    ``build/phase-0/``; only NEGATIVE phases are rejected.
    """
    feature_dir = _make_feature_dir(tmp_path, "F999-phase0")
    inputs_dir = tmp_path / "inputs"
    inputs_dir.mkdir()

    ac_passed_file = _write_bullet_file(inputs_dir / "ac_passed.txt", ["AC-1 — ok"])
    ac_failed_file = _write_bullet_file(inputs_dir / "ac_failed.txt", [])
    deferred_file = _write_bullet_file(inputs_dir / "deferred.txt", [])
    limitations_file = _write_bullet_file(inputs_dir / "limitations.txt", [])

    completed = _invoke_write(
        cwd=tmp_path,
        feature_dir=feature_dir,
        phase=0,
        prd_title="Flat Fallback Phase",
        prd_id="F999",
        ac_passed_file=ac_passed_file,
        ac_failed_file=ac_failed_file,
        deferred_file=deferred_file,
        limitations_file=limitations_file,
    )

    assert completed.returncode == 0, (
        f"phase 0 was rejected: stderr={completed.stderr!r} stdout={completed.stdout!r}"
    )
    report_path = feature_dir / "build" / "phase-0" / "completion-report.md"
    assert report_path.is_file(), (
        f"helper did not write completion-report.md at {report_path}"
    )


def test_completion_report_rejects_negative_phase(tmp_path: Path) -> None:
    """#43: the lower bound moves from ``< 1`` to ``< 0`` — negatives still fail."""
    feature_dir = _make_feature_dir(tmp_path, "F999-neg")
    inputs_dir = tmp_path / "inputs"
    inputs_dir.mkdir()

    files = [
        _write_bullet_file(inputs_dir / "ac_passed.txt", []),
        _write_bullet_file(inputs_dir / "ac_failed.txt", []),
        _write_bullet_file(inputs_dir / "deferred.txt", []),
        _write_bullet_file(inputs_dir / "limitations.txt", []),
    ]
    completed = _invoke_write(
        cwd=tmp_path,
        feature_dir=feature_dir,
        phase=-1,
        prd_title="Negative Phase",
        prd_id="F999",
        ac_passed_file=files[0],
        ac_failed_file=files[1],
        deferred_file=files[2],
        limitations_file=files[3],
    )
    assert completed.returncode == 1, "negative phase should still be rejected"
    assert "non-negative" in completed.stderr or "must be" in completed.stderr


def test_completion_report_handles_empty_sections(tmp_path: Path) -> None:
    """AC8 / BR-002: empty AC/deferred/limitations input files emit the
    literal ``- (none)`` placeholder (not blank content).
    """
    feature_dir = _make_feature_dir(tmp_path, "F999-empty")
    inputs_dir = tmp_path / "inputs"
    inputs_dir.mkdir()

    # Touch all four input files; leave them empty.
    ac_passed_file = _write_bullet_file(inputs_dir / "ac_passed.txt", [])
    ac_failed_file = _write_bullet_file(inputs_dir / "ac_failed.txt", [])
    deferred_file = _write_bullet_file(inputs_dir / "deferred.txt", [])
    limitations_file = _write_bullet_file(inputs_dir / "limitations.txt", [])

    completed = _invoke_write(
        cwd=tmp_path,
        feature_dir=feature_dir,
        phase=1,
        prd_title="Empty Sections",
        prd_id="F999",
        ac_passed_file=ac_passed_file,
        ac_failed_file=ac_failed_file,
        deferred_file=deferred_file,
        limitations_file=limitations_file,
    )

    assert completed.returncode == 0, (
        f"helper failed: stderr={completed.stderr!r} stdout={completed.stdout!r}"
    )

    report_path = feature_dir / "build" / "phase-1" / "completion-report.md"
    body = report_path.read_text(encoding="utf-8")

    # Each empty section emits the literal "- (none)" placeholder.
    placeholder = "- (none)"
    assert body.count(placeholder) >= 3, (
        f"expected at least 3 occurrences of {placeholder!r} (one per empty "
        f"section: AC, Deferred Items, Known Limitations); got body={body!r}"
    )

    # Spot-check that each empty section contains the placeholder by
    # slicing the body on section headers.
    ac_idx = body.find("## Acceptance Criteria")
    deferred_idx = body.find("## Deferred Items")
    limitations_idx = body.find("## Known Limitations")
    assert ac_idx != -1, "missing '## Acceptance Criteria' header"
    assert deferred_idx != -1, "missing '## Deferred Items' header"
    assert limitations_idx != -1, "missing '## Known Limitations' header"

    ac_section = body[ac_idx:deferred_idx]
    deferred_section = body[deferred_idx:limitations_idx]
    limitations_section = body[limitations_idx:]

    assert placeholder in ac_section, (
        f"empty AC section missing placeholder {placeholder!r}; "
        f"section={ac_section!r}"
    )
    assert placeholder in deferred_section, (
        f"empty Deferred Items section missing placeholder {placeholder!r}; "
        f"section={deferred_section!r}"
    )
    assert placeholder in limitations_section, (
        f"empty Known Limitations section missing placeholder {placeholder!r}; "
        f"section={limitations_section!r}"
    )


def test_completion_report_round_trip_with_release_notes(tmp_path: Path) -> None:
    """AC9 / BR-007: write a report via the helper, then read it via
    ``release_notes.build()`` and assert the roll-up contains the PRD
    title, ID, AC checkboxes, and bullets the helper just wrote.

    This is the load-bearing integration test — proves the writer/reader
    contract holds end-to-end.
    """
    feature_dir = _make_feature_dir(tmp_path, "F999-roundtrip")
    inputs_dir = tmp_path / "inputs"
    inputs_dir.mkdir()

    ac_passed_file = _write_bullet_file(
        inputs_dir / "ac_passed.txt",
        [
            "AC-001 — round-trip passed alpha",
            "AC-002 — round-trip passed beta",
        ],
    )
    ac_failed_file = _write_bullet_file(inputs_dir / "ac_failed.txt", [])
    deferred_file = _write_bullet_file(
        inputs_dir / "deferred.txt",
        ["AC-007 surface_status: deferred — round-trip deferred bullet"],
    )
    limitations_file = _write_bullet_file(inputs_dir / "limitations.txt", [])

    completed = _invoke_write(
        cwd=tmp_path,
        feature_dir=feature_dir,
        phase=1,
        prd_title="Round Trip Contract",
        prd_id="F005",
        ac_passed_file=ac_passed_file,
        ac_failed_file=ac_failed_file,
        deferred_file=deferred_file,
        limitations_file=limitations_file,
    )

    assert completed.returncode == 0, (
        f"helper failed: stderr={completed.stderr!r} stdout={completed.stdout!r}"
    )

    # Now invoke the reader on the parent feature directory.
    rollup = release_notes.build(feature_dir)

    # PRD title and ID land in the roll-up.
    assert "Round Trip Contract" in rollup, (
        f"roll-up missing PRD title 'Round Trip Contract'; got {rollup!r}"
    )
    assert "F005" in rollup, (
        f"roll-up missing PRD id 'F005'; got {rollup!r}"
    )

    # At least one passed AC checkbox bullet from the writer's input.
    assert "[x] AC-001 — round-trip passed alpha" in rollup, (
        "roll-up missing passed AC checkbox bullet "
        "'[x] AC-001 — round-trip passed alpha'"
    )

    # At least one deferred-item bullet from the writer's input.
    assert "AC-007 surface_status: deferred — round-trip deferred bullet" in rollup, (
        "roll-up missing deferred-items bullet "
        "'AC-007 surface_status: deferred — round-trip deferred bullet'"
    )


def test_build_skill_documents_step_6d_5(build_skill_dist_text: str) -> None:
    """AC10 / BR-007: the compiled ``dist/skills/build/SKILL.md`` Step 6d
    region contains the new ``6d.5`` sub-step that invokes
    ``completion_report.py write`` with the ``--feature-dir`` and
    ``--phase`` flags from BR-001.
    """
    # Slice the skill body on Step 6d / Step 7 markers so the assertions
    # are scoped to the Step 6 region (precedent: tests/test_release_notes.py
    # and tests/test_user_flow_completeness.py both slice on phase markers
    # before grepping).
    step_6d_idx = build_skill_dist_text.find("6d.")
    assert step_6d_idx != -1, (
        "compiled dist/skills/build/SKILL.md missing Step 6d marker"
    )

    # Search from Step 6d onward (the end of Step 6 transitions into
    # Step 7; tests don't need to be precise about the upper bound — any
    # of the required tokens must appear after the 6d marker).
    step_6d_region = build_skill_dist_text[step_6d_idx:]

    # Sub-step header literal.
    assert "6d.5" in step_6d_region, (
        "compiled dist/skills/build/SKILL.md Step 6d region missing literal "
        "'6d.5' sub-step header"
    )

    # Helper invocation form.
    assert "completion_report.py write" in step_6d_region, (
        "compiled dist/skills/build/SKILL.md Step 6d region missing literal "
        "'completion_report.py write' helper invocation"
    )

    # BR-001 flag signature.
    assert "--feature-dir" in step_6d_region, (
        "compiled dist/skills/build/SKILL.md Step 6d region missing literal "
        "'--feature-dir' flag"
    )
    assert "--phase" in step_6d_region, (
        "compiled dist/skills/build/SKILL.md Step 6d region missing literal "
        "'--phase' flag"
    )
