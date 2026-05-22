"""Fixture-driven tests for scripts/diagnostic_evidence.py::validate_block.

Covers F021 AC-001 and AC-002 by parametrizing pytest over the on-disk
fixture corpus at tests/fixtures/diagnostic-evidence-blocks/{valid,invalid}/.
The corpus is owned by task 002.002 and is intentionally independent of
the inline-sample tests in tests/test_diagnostic_evidence.py (002.001):
different file, different shape, no shared helpers, separate failure
surface so a regression in one corpus cannot mask a regression in the
other.

Test contract:

    - Every file in valid/ — validate_block(file.read_text()) returns
      valid=True. The 12 files cover all 5 evidence_type enum values
      (interpreter-diff, version-diff, upstream-issue, repro,
      error-is-real) plus edge cases (fenced vs inline, with vs without
      surrounding prose, mixed-case enum, multi-line tool output).
    - Every file in invalid/ — validate_block returns valid=False AND
      the reason string contains the substring associated with the
      filename (see _INVALID_FIXTURES below). Substrings are chosen
      against the exact rejection-reason strings shipped in
      scripts/diagnostic_evidence.py.

Fixture loading uses Path.read_text() directly — no helpers shared with
test_diagnostic_evidence.py, per the independence requirement.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = REPO_ROOT / "scripts" / "diagnostic_evidence.py"

FIXTURES_ROOT = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "diagnostic-evidence-blocks"
)
VALID_DIR = FIXTURES_ROOT / "valid"
INVALID_DIR = FIXTURES_ROOT / "invalid"


def _load_module() -> ModuleType:
    """Import scripts/diagnostic_evidence.py as a module.

    scripts/ is not a Python package; load the file directly via
    importlib so the fixture-driven tests do not depend on packaging
    state. Mirrors the pattern used in tests/test_value_hypothesis.py
    and tests/test_diagnostic_evidence.py but does NOT share the helper
    — independence is part of the task contract.
    """
    spec = importlib.util.spec_from_file_location(
        "diagnostic_evidence_fixtures", MODULE_PATH
    )
    if spec is None or spec.loader is None:
        msg = f"Cannot load module at {MODULE_PATH}"
        raise RuntimeError(msg)
    module = importlib.util.module_from_spec(spec)
    sys.modules["diagnostic_evidence_fixtures"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def de() -> ModuleType:
    """Module under test, imported once per test module."""
    return _load_module()


# ── Fixture corpus discovery ──────────────────────────────────────────────


def _valid_fixture_files() -> list[Path]:
    """Return every .yaml file in valid/ sorted by filename."""
    return sorted(VALID_DIR.glob("*.yaml"))


# AC-002: filename → expected substring of the validator's rejection
# reason. Substrings are matched case-insensitively in the assertions
# below. Each entry maps to the exact reason-string family produced by
# scripts/diagnostic_evidence.py in Wave 0.
_INVALID_FIXTURES: tuple[tuple[str, str], ...] = (
    # _validate_single_block: missing field(s).
    ("missing-field-attribution.yaml", "missing required field"),
    ("missing-field-tool_rerun_command.yaml", "missing required field"),
    # _discover_candidate_blocks: malformed YAML body yields no parseable
    # candidate; fallback whole-document parse also fails (or returns
    # no-required-field), so the reason is "no parseable YAML evidence
    # block found in response".
    ("unparseable-yaml.yaml", "no parseable yaml evidence block"),
    # _validate_single_block: enum membership.
    ("enum-out-of-range.yaml", "controlled enum"),
    # _validate_single_block: empty-value check.
    ("empty-field-attribution.yaml", "empty"),
    # _discover_candidate_blocks: >1 candidate fenced blocks → GA-006.
    ("multiple-candidate-blocks.yaml", "ambiguous"),
    # _discover_candidate_blocks: 0 candidate fenced or fallback blocks.
    ("no-candidate-block.yaml", "no parseable yaml evidence block"),
    # _validate_single_block: all four fields present but empty.
    ("all-fields-empty.yaml", "empty"),
)


# ── valid/ corpus assertions (AC-001) ─────────────────────────────────────


def test_should_have_exactly_twelve_valid_fixture_files_when_corpus_loaded() -> None:
    files = _valid_fixture_files()
    assert len(files) == 12, (
        f"AC-001 requires exactly 12 valid fixtures; found {len(files)} "
        f"in {VALID_DIR}: {[f.name for f in files]}"
    )


def test_should_cover_all_five_evidence_type_enum_values_in_valid_corpus(
    de: ModuleType,
) -> None:
    """AC-001: the 12 valid samples must collectively exercise every
    evidence_type enum value. Parse each fixture; collect the canonical
    (lower-cased) evidence_type from each parsed block; assert the set
    equals EVIDENCE_TYPE_ENUM."""
    seen: set[str] = set()
    for fixture in _valid_fixture_files():
        result = de.validate_block(fixture.read_text(encoding="utf-8"))
        assert result.valid is True, (
            f"valid fixture {fixture.name} failed validation: {result.reason}"
        )
        assert result.parsed is not None
        seen.add(result.parsed["evidence_type"])
    assert seen == de.EVIDENCE_TYPE_ENUM, (
        f"valid corpus is missing coverage for enum values: "
        f"{sorted(de.EVIDENCE_TYPE_ENUM - seen)}"
    )


@pytest.mark.parametrize(
    "fixture_path",
    _valid_fixture_files(),
    ids=lambda p: p.name,
)
def test_should_accept_every_valid_fixture_when_validated(
    de: ModuleType,
    fixture_path: Path,
) -> None:
    """AC-001: each valid/*.yaml fixture parses to valid=True."""
    text = fixture_path.read_text(encoding="utf-8")
    result = de.validate_block(text)
    assert result.valid is True, (
        f"{fixture_path.name} expected valid=True; got reason={result.reason!r}"
    )
    assert result.reason is None
    assert result.parsed is not None
    assert result.parsed["evidence_type"] in de.EVIDENCE_TYPE_ENUM


# ── invalid/ corpus assertions (AC-002) ───────────────────────────────────


def test_should_have_exactly_eight_invalid_fixture_files_when_corpus_loaded() -> None:
    files = sorted(INVALID_DIR.glob("*.yaml"))
    assert len(files) == 8, (
        f"AC-002 requires exactly 8 invalid fixtures; found {len(files)} "
        f"in {INVALID_DIR}: {[f.name for f in files]}"
    )


def test_should_have_one_invalid_fixture_per_named_failure_mode_when_corpus_loaded() -> None:
    """AC-002 names eight specific filenames. Assert every named filename
    exists and no unexpected files have crept into invalid/."""
    actual = {p.name for p in INVALID_DIR.glob("*.yaml")}
    expected = {name for name, _ in _INVALID_FIXTURES}
    assert actual == expected, (
        f"invalid/ filename set mismatch.\n"
        f"  missing: {sorted(expected - actual)}\n"
        f"  unexpected: {sorted(actual - expected)}"
    )


@pytest.mark.parametrize(
    ("filename", "expected_reason_substring"),
    _INVALID_FIXTURES,
    ids=[name for name, _ in _INVALID_FIXTURES],
)
def test_should_reject_every_invalid_fixture_with_expected_reason_when_validated(
    de: ModuleType,
    filename: str,
    expected_reason_substring: str,
) -> None:
    """AC-002: each invalid/*.yaml fixture parses to valid=False with a
    reason string whose lower-cased form contains the documented
    substring for that failure mode."""
    fixture_path = INVALID_DIR / filename
    text = fixture_path.read_text(encoding="utf-8")
    result = de.validate_block(text)

    assert result.valid is False, (
        f"{filename} expected valid=False but validator accepted it"
    )
    assert result.reason is not None
    assert expected_reason_substring.lower() in result.reason.lower(), (
        f"{filename}: expected reason substring "
        f"{expected_reason_substring!r} not found in actual reason "
        f"{result.reason!r}"
    )
    assert result.parsed is None
