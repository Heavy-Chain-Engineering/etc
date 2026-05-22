"""Tests for scripts/diagnostic_evidence.py.

Covers F021 AC-001 + AC-002 (validate_block: pure validator over a YAML
evidence block with four required fields and a case-insensitive enum on
evidence_type, rejecting on missing/empty fields, unparseable YAML,
enum-out-of-range, and multi-candidate-block ambiguity) and AC-008 +
BR-007 (emit_event: append-only JSONL emission to the F019 audit-log
surface with ISO-8601 UTC ts auto-injection and event_type enum
enforcement).

Per F021 architect gray areas:
    - GA-004: enum membership is case-insensitive (normalize input via
      .lower() before comparing against EVIDENCE_TYPE_ENUM).
    - GA-005: block discovery scans for ANY YAML structure (fenced,
      indented, or inline) containing the four required keys.
    - GA-006: more than one candidate block in the same input rejects
      as ambiguous.

The external fixture directory tests/fixtures/diagnostic-evidence-blocks/
is owned by task 002.002 and is intentionally NOT exercised here; this
module uses inline synthetic samples only.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = REPO_ROOT / "scripts" / "diagnostic_evidence.py"


def _load_module() -> ModuleType:
    """Import scripts/diagnostic_evidence.py as a module.

    scripts/ is not a Python package, so we load the file directly via
    importlib. Mirrors the pattern used in tests/test_value_hypothesis.py.
    """
    spec = importlib.util.spec_from_file_location(
        "diagnostic_evidence", MODULE_PATH
    )
    if spec is None or spec.loader is None:
        msg = f"Cannot load module at {MODULE_PATH}"
        raise RuntimeError(msg)
    module = importlib.util.module_from_spec(spec)
    sys.modules["diagnostic_evidence"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def de() -> ModuleType:
    """Module under test, imported once per test module."""
    return _load_module()


# ── Helpers for building synthetic evidence blocks ────────────────────────


def _valid_block_text(evidence_type: str = "interpreter-diff") -> str:
    """Construct a well-formed fenced YAML evidence block."""
    return (
        "Some narrative prose from the agent, then:\n"
        "```yaml\n"
        'tool_rerun_command: "uv run mypy scripts/foo.py"\n'
        'tool_rerun_output: "Success: no issues found in 1 source file"\n'
        'attribution: "IDE was running stale mypy 1.10; CLI is 1.14"\n'
        f"evidence_type: {evidence_type}\n"
        "```\n"
        "Continuing with the next edit.\n"
    )


# ── Public-surface constants ──────────────────────────────────────────────


def test_should_expose_required_fields_as_frozenset_when_module_imported(
    de: ModuleType,
) -> None:
    assert isinstance(de.REQUIRED_FIELDS, frozenset)
    assert de.REQUIRED_FIELDS == frozenset(
        {
            "tool_rerun_command",
            "tool_rerun_output",
            "attribution",
            "evidence_type",
        }
    )


def test_should_expose_evidence_type_enum_as_lowercase_frozenset_when_module_imported(
    de: ModuleType,
) -> None:
    assert isinstance(de.EVIDENCE_TYPE_ENUM, frozenset)
    assert de.EVIDENCE_TYPE_ENUM == frozenset(
        {
            "interpreter-diff",
            "version-diff",
            "upstream-issue",
            "repro",
            "error-is-real",
        }
    )
    # GA-004: stored lowercase so case-insensitive matching is a simple
    # .lower()-then-membership-check.
    for value in de.EVIDENCE_TYPE_ENUM:
        assert value == value.lower()


def test_should_expose_forbidden_phrases_seed_as_tuple_when_module_imported(
    de: ModuleType,
) -> None:
    assert isinstance(de.FORBIDDEN_PHRASES_SEED, tuple)
    assert de.FORBIDDEN_PHRASES_SEED == (
        "host-env false positive",
        "stale cache",
        "noise",
        "tooling drift",
        "diagnostic engine running elsewhere",
        "the IDE is confused",
    )


def test_should_expose_validation_result_as_frozen_dataclass_when_module_imported(
    de: ModuleType,
) -> None:
    result = de.ValidationResult(valid=True, reason=None, parsed={"a": 1})
    assert result.valid is True
    assert result.reason is None
    assert result.parsed == {"a": 1}
    # Frozen: attribute assignment must raise.
    with pytest.raises((AttributeError, Exception)):
        result.valid = False  # type: ignore[misc]


# ── validate_block: positive cases (AC-001) ───────────────────────────────


def test_should_accept_well_formed_block_with_interpreter_diff_when_validated(
    de: ModuleType,
) -> None:
    result = de.validate_block(_valid_block_text("interpreter-diff"))
    assert result.valid is True
    assert result.reason is None
    assert result.parsed is not None
    assert result.parsed["evidence_type"] == "interpreter-diff"


def test_should_accept_well_formed_block_with_version_diff_when_validated(
    de: ModuleType,
) -> None:
    result = de.validate_block(_valid_block_text("version-diff"))
    assert result.valid is True
    assert result.parsed is not None
    assert result.parsed["evidence_type"] == "version-diff"


def test_should_accept_well_formed_block_with_error_is_real_when_validated(
    de: ModuleType,
) -> None:
    result = de.validate_block(_valid_block_text("error-is-real"))
    assert result.valid is True
    assert result.parsed is not None
    assert result.parsed["evidence_type"] == "error-is-real"


def test_should_accept_evidence_type_with_mixed_case_when_validated(
    de: ModuleType,
) -> None:
    # GA-004: case-insensitive enum match.
    result = de.validate_block(_valid_block_text("Interpreter-Diff"))
    assert result.valid is True


def test_should_accept_evidence_type_with_all_uppercase_when_validated(
    de: ModuleType,
) -> None:
    # GA-004: case-insensitive enum match.
    result = de.validate_block(_valid_block_text("UPSTREAM-ISSUE"))
    assert result.valid is True


def test_should_accept_indented_yaml_block_without_fences_when_validated(
    de: ModuleType,
) -> None:
    # GA-005: any-YAML-structure discovery — bare YAML without fences.
    text = (
        "tool_rerun_command: uv run ruff check scripts/foo.py\n"
        'tool_rerun_output: "All checks passed!"\n'
        "attribution: ruff version drift between IDE plugin and CLI\n"
        "evidence_type: version-diff\n"
    )
    result = de.validate_block(text)
    assert result.valid is True
    assert result.parsed is not None
    assert result.parsed["evidence_type"] == "version-diff"


# ── validate_block: negative cases (AC-002) ───────────────────────────────


def test_should_reject_block_missing_attribution_when_validated(
    de: ModuleType,
) -> None:
    text = (
        "```yaml\n"
        'tool_rerun_command: "uv run mypy ."\n'
        'tool_rerun_output: "Success"\n'
        "evidence_type: interpreter-diff\n"
        "```\n"
    )
    result = de.validate_block(text)
    assert result.valid is False
    assert result.reason is not None
    assert "attribution" in result.reason


def test_should_reject_block_missing_tool_rerun_command_when_validated(
    de: ModuleType,
) -> None:
    text = (
        "```yaml\n"
        'tool_rerun_output: "Success"\n'
        'attribution: "stale cache"\n'
        "evidence_type: interpreter-diff\n"
        "```\n"
    )
    result = de.validate_block(text)
    assert result.valid is False
    assert result.reason is not None
    assert "tool_rerun_command" in result.reason


def test_should_reject_block_with_empty_attribution_when_validated(
    de: ModuleType,
) -> None:
    # EC-006: empty fields signal the agent went through the motions.
    text = (
        "```yaml\n"
        'tool_rerun_command: "uv run mypy ."\n'
        'tool_rerun_output: "Success"\n'
        'attribution: ""\n'
        "evidence_type: interpreter-diff\n"
        "```\n"
    )
    result = de.validate_block(text)
    assert result.valid is False
    assert result.reason is not None
    assert "attribution" in result.reason
    assert "empty" in result.reason.lower()


def test_should_reject_block_with_empty_tool_rerun_output_when_validated(
    de: ModuleType,
) -> None:
    text = (
        "```yaml\n"
        'tool_rerun_command: "uv run mypy ."\n'
        'tool_rerun_output: ""\n'
        'attribution: "noise"\n'
        "evidence_type: interpreter-diff\n"
        "```\n"
    )
    result = de.validate_block(text)
    assert result.valid is False
    assert result.reason is not None
    assert "empty" in result.reason.lower()


def test_should_reject_block_with_unknown_evidence_type_when_validated(
    de: ModuleType,
) -> None:
    text = _valid_block_text("not-a-real-tag")
    result = de.validate_block(text)
    assert result.valid is False
    assert result.reason is not None
    assert "evidence_type" in result.reason


def test_should_reject_unparseable_yaml_when_validated(
    de: ModuleType,
) -> None:
    # Deliberately malformed: unbalanced flow-style braces inside a key
    # that contains the four required field names so the discovery
    # routine attempts to parse and fails.
    text = (
        "```yaml\n"
        "tool_rerun_command: [unterminated\n"
        "tool_rerun_output: still bad\n"
        "attribution: { malformed:: { mapping\n"
        "evidence_type: interpreter-diff\n"
        "```\n"
    )
    result = de.validate_block(text)
    assert result.valid is False
    assert result.reason is not None


def test_should_reject_text_with_no_yaml_blocks_when_validated(
    de: ModuleType,
) -> None:
    text = "Just a paragraph of prose with no YAML structure at all.\n"
    result = de.validate_block(text)
    assert result.valid is False
    assert result.reason is not None


def test_should_reject_when_two_candidate_blocks_present(
    de: ModuleType,
) -> None:
    # GA-006: multi-block ambiguity → reject.
    text = _valid_block_text("interpreter-diff") + "\nAnd again:\n" + _valid_block_text(
        "version-diff"
    )
    result = de.validate_block(text)
    assert result.valid is False
    assert result.reason is not None
    reason_lower = result.reason.lower()
    assert "multiple" in reason_lower or "ambiguous" in reason_lower


def test_should_report_specific_reason_string_on_each_rejection_path(
    de: ModuleType,
) -> None:
    # AC-002: reason must be a non-empty string naming the failure on
    # every negative outcome.
    cases: list[str] = [
        "```yaml\nfoo: bar\n```\n",  # no required fields
        _valid_block_text("not-an-enum-member"),  # enum out of range
        _valid_block_text("interpreter-diff")
        + "\n---\n"
        + _valid_block_text("repro"),  # multi-block
    ]
    for text in cases:
        result = de.validate_block(text)
        assert result.valid is False
        assert isinstance(result.reason, str)
        assert result.reason.strip() != ""


# ── validate_block: purity (no I/O) ───────────────────────────────────────


def test_should_be_pure_function_when_validating_block(
    de: ModuleType,
    tmp_path: Path,
) -> None:
    # Purity proxy: changing cwd to an empty dir must not affect the
    # result, and no files must be created in cwd.
    import os

    original_cwd = Path.cwd()
    os.chdir(tmp_path)
    try:
        result = de.validate_block(_valid_block_text("repro"))
        assert result.valid is True
        assert list(tmp_path.iterdir()) == []
    finally:
        os.chdir(original_cwd)


# ── emit_event: happy path (AC-008) ───────────────────────────────────────


def test_should_append_jsonl_row_to_audit_log_when_event_emitted(
    de: ModuleType,
    tmp_path: Path,
) -> None:
    payload = {
        "feature_id": "F021",
        "wave_num": 0,
        "tool_name": "mypy",
        "evidence_type": "interpreter-diff",
        "decision": "accepted",
    }
    de.emit_event("diagnostic_dismissal_with_evidence", payload, tmp_path)

    log_path = tmp_path / ".etc_sdlc" / "efficiency" / "turn-events.jsonl"
    assert log_path.is_file()

    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1

    row = json.loads(lines[0])
    assert row["event_type"] == "diagnostic_dismissal_with_evidence"
    assert row["feature_id"] == "F021"
    assert row["wave_num"] == 0
    assert row["tool_name"] == "mypy"
    assert row["evidence_type"] == "interpreter-diff"
    assert row["decision"] == "accepted"


def test_should_auto_inject_iso_8601_utc_timestamp_when_event_emitted(
    de: ModuleType,
    tmp_path: Path,
) -> None:
    de.emit_event(
        "diagnostic_dismissal_missing_evidence",
        {"decision": "unresolved"},
        tmp_path,
    )

    log_path = tmp_path / ".etc_sdlc" / "efficiency" / "turn-events.jsonl"
    row = json.loads(log_path.read_text(encoding="utf-8").splitlines()[0])

    ts_raw = row["ts"]
    assert isinstance(ts_raw, str)
    # ISO-8601 UTC: parseable + tzinfo present + zero UTC offset.
    parsed = datetime.fromisoformat(ts_raw)
    assert parsed.tzinfo is not None
    assert parsed.utcoffset() == timezone.utc.utcoffset(None)


def test_should_preserve_caller_supplied_timestamp_when_event_emitted(
    de: ModuleType,
    tmp_path: Path,
) -> None:
    # Caller-supplied ts must not be overwritten.
    supplied = "2026-05-20T12:34:56+00:00"
    de.emit_event(
        "diagnostic_dismissal_with_evidence",
        {"ts": supplied, "decision": "accepted"},
        tmp_path,
    )
    log_path = tmp_path / ".etc_sdlc" / "efficiency" / "turn-events.jsonl"
    row = json.loads(log_path.read_text(encoding="utf-8").splitlines()[0])
    assert row["ts"] == supplied


def test_should_create_parent_directory_idempotently_when_event_emitted(
    de: ModuleType,
    tmp_path: Path,
) -> None:
    # No .etc_sdlc/ pre-created. Two emissions should both succeed.
    de.emit_event(
        "diagnostic_dismissal_with_evidence", {"decision": "accepted"}, tmp_path
    )
    de.emit_event(
        "diagnostic_dismissal_missing_evidence",
        {"decision": "unresolved"},
        tmp_path,
    )
    log_path = tmp_path / ".etc_sdlc" / "efficiency" / "turn-events.jsonl"
    assert log_path.is_file()
    assert len(log_path.read_text(encoding="utf-8").splitlines()) == 2


def test_should_append_not_truncate_when_multiple_events_emitted(
    de: ModuleType,
    tmp_path: Path,
) -> None:
    # Data Model Invariant 1: append-only.
    for i in range(3):
        de.emit_event(
            "diagnostic_dismissal_with_evidence",
            {"decision": "accepted", "feature_id": f"F{i:03d}"},
            tmp_path,
        )
    log_path = tmp_path / ".etc_sdlc" / "efficiency" / "turn-events.jsonl"
    rows = [
        json.loads(line)
        for line in log_path.read_text(encoding="utf-8").splitlines()
    ]
    assert len(rows) == 3
    feature_ids = [r["feature_id"] for r in rows]
    assert feature_ids == ["F000", "F001", "F002"]


# ── emit_event: enum enforcement (BR-007) ─────────────────────────────────


def test_should_raise_value_error_when_event_type_outside_enum(
    de: ModuleType,
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError) as excinfo:
        de.emit_event("not_a_real_event_type", {"decision": "accepted"}, tmp_path)
    assert "event_type" in str(excinfo.value)


def test_should_raise_value_error_when_event_type_is_empty(
    de: ModuleType,
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError):
        de.emit_event("", {"decision": "accepted"}, tmp_path)


def test_should_accept_both_canonical_event_types_when_emitted(
    de: ModuleType,
    tmp_path: Path,
) -> None:
    de.emit_event(
        "diagnostic_dismissal_with_evidence", {"decision": "accepted"}, tmp_path
    )
    de.emit_event(
        "diagnostic_dismissal_missing_evidence",
        {"decision": "unresolved", "reason": "missing_attribution"},
        tmp_path,
    )
    log_path = tmp_path / ".etc_sdlc" / "efficiency" / "turn-events.jsonl"
    rows = [
        json.loads(line)
        for line in log_path.read_text(encoding="utf-8").splitlines()
    ]
    assert rows[0]["event_type"] == "diagnostic_dismissal_with_evidence"
    assert rows[1]["event_type"] == "diagnostic_dismissal_missing_evidence"
    assert rows[1]["reason"] == "missing_attribution"


def test_should_not_create_log_file_when_event_type_rejected(
    de: ModuleType,
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError):
        de.emit_event("bogus_event", {"decision": "accepted"}, tmp_path)
    log_path = tmp_path / ".etc_sdlc" / "efficiency" / "turn-events.jsonl"
    assert not log_path.exists()
