"""Contract tests for scripts/spec_enforcer_chunker.py.

Feature: F-2026-05-22-spec-enforcer-hierarchical-breakdown — Task 001.

Covers:
- AC-001: 13-AC numbered-shape spec → strategy "chunked", 3 chunks (6,6,1).
- AC-002: <=10-AC spec → strategy "single" with one chunk holding all ACs.
- AC-003: --chunk-size + --threshold CLI flags override the defaults.
- AC-004: AC parser handles BOTH numbered (`^\\d+\\.\\s+\\*\\*AC-`) and
  heading (`^###\\s+AC-`) shapes; dedupes by AC number.
- AC-007: `aggregate_verdicts` helper applies OR-semantics across chunks.
- AC-009: Backward compat — with --threshold 999, F026's 13-AC spec emits
  strategy "single" with one chunk containing all 13 ACs.

Plus the edge cases from spec.md (0 ACs, 1 AC, threshold-equal, threshold+1,
chunk-size-multiple, --chunk-size 0, missing path, both shapes deduped).

All tests are stdlib + pytest only. The chunker itself uses only the
stdlib per spec BR-008; tests follow the same constraint where feasible.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
CHUNKER_SCRIPT = SCRIPTS_DIR / "spec_enforcer_chunker.py"

# Make scripts/ importable so the pure-helper aggregation tests can call
# `aggregate_verdicts` directly without going through subprocess.
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import spec_enforcer_chunker  # pyright: ignore[reportMissingImports]  # noqa: E402

# ── Helpers ─────────────────────────────────────────────────────────────


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    """Invoke the chunker CLI in a subprocess and return the completed proc.

    Uses argv-list invocation (never shell string) so the test mirrors the
    /build conductor's planned invocation shape per spec BR-008.
    """
    return subprocess.run(
        ["python3", str(CHUNKER_SCRIPT), *args],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )


def _write_numbered_spec(spec_path: Path, ac_count: int) -> None:
    """Write a synthetic spec.md with ``ac_count`` numbered-shape ACs."""
    lines = ["# Synthetic PRD\n", "## Acceptance Criteria\n"]
    for i in range(1, ac_count + 1):
        lines.append(f"{i}. **AC-{i:03d} — Synthetic AC {i}.** Body text.\n")
    spec_path.write_text("".join(lines), encoding="utf-8")


def _write_heading_spec(spec_path: Path, ac_count: int) -> None:
    """Write a synthetic spec.md with ``ac_count`` heading-shape ACs."""
    lines = ["# Synthetic PRD\n", "## Acceptance Criteria\n"]
    for i in range(1, ac_count + 1):
        lines.append(f"### AC-{i:03d} — Synthetic AC {i}\n\nBody text.\n")
    spec_path.write_text("".join(lines), encoding="utf-8")


def _write_bullet_spec(spec_path: Path, ac_count: int) -> None:
    """Write a synthetic spec.md with unsupported bullet-shape ACs."""
    lines = ["# Synthetic PRD\n", "## Acceptance Criteria\n"]
    for i in range(1, ac_count + 1):
        lines.append(f"- **AC-{i:03d}:** Bullet AC {i} body.\n")
    spec_path.write_text("".join(lines), encoding="utf-8")


# ── AC-001 — chunked path against F026 (13 ACs) ─────────────────────────


def test_should_emit_chunked_strategy_with_three_chunks_when_partitioning_thirteen_ac_spec(
    tmp_path: Path,
) -> None:
    # Arrange — 13 numbered ACs are above the default threshold of 10,
    # so the default invocation must engage chunking.
    spec_path = tmp_path / "thirteen_ac_spec.md"
    _write_numbered_spec(spec_path, ac_count=13)

    # Act
    result = _run_cli("partition", str(spec_path))

    # Assert
    assert result.returncode == 0, (
        f"chunker exited {result.returncode}; stderr: {result.stderr}"
    )
    payload = json.loads(result.stdout)
    assert payload["strategy"] == "chunked"
    chunks = payload["chunks"]
    assert [len(c["ac_numbers"]) for c in chunks] == [6, 6, 1]
    # AC numbers preserved in encounter order across the three chunks.
    flattened = [n for c in chunks for n in c["ac_numbers"]]
    assert flattened == list(range(1, 14))


# ── AC-002 — single-dispatch fast path ──────────────────────────────────


def test_should_emit_single_strategy_when_synthetic_spec_has_fewer_than_threshold_acs(
    tmp_path: Path,
) -> None:
    # Arrange — synthesize a 5-AC spec under the 10-AC default threshold.
    # Per the task brief, no shipped/ spec has between 1 and 10 numbered
    # ACs, so a synthetic fixture is the cleanest way to satisfy the AC-002
    # contract; the small-spec fast path is also exercised against the real
    # F022 fixture in the companion test below (with --threshold 999).
    spec_path = tmp_path / "small_spec.md"
    _write_numbered_spec(spec_path, ac_count=5)

    # Act
    result = _run_cli("partition", str(spec_path))

    # Assert
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["strategy"] == "single"
    assert len(payload["chunks"]) == 1
    assert payload["chunks"][0]["ac_numbers"] == [1, 2, 3, 4, 5]


def test_should_emit_single_strategy_when_twelve_ac_spec_runs_with_threshold_above_its_ac_count(
    tmp_path: Path,
) -> None:
    # Arrange — 12 ACs is above the default threshold of 10. Raise the
    # threshold above 12 to exercise the small-spec fast path.
    spec_path = tmp_path / "twelve_ac_spec.md"
    _write_numbered_spec(spec_path, ac_count=12)

    # Act
    result = _run_cli(
        "partition", str(spec_path), "--threshold", "999"
    )

    # Assert
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["strategy"] == "single"
    assert len(payload["chunks"]) == 1
    assert payload["chunks"][0]["ac_numbers"] == list(range(1, 13))


# ── AC-003 — CLI overrides honored ──────────────────────────────────────


def test_should_emit_two_equal_chunks_when_chunk_size_and_threshold_overrides_applied(
    tmp_path: Path,
) -> None:
    # Arrange — 8-AC spec, override --threshold 5 (8 > 5 engages chunking)
    # and --chunk-size 4 (8 ACs → 2 chunks of 4).
    spec_path = tmp_path / "eight_ac_spec.md"
    _write_numbered_spec(spec_path, ac_count=8)

    # Act
    result = _run_cli(
        "partition",
        str(spec_path),
        "--chunk-size",
        "4",
        "--threshold",
        "5",
    )

    # Assert
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["strategy"] == "chunked"
    assert [len(c["ac_numbers"]) for c in payload["chunks"]] == [4, 4]


# ── AC-004 — parser handles both shapes ─────────────────────────────────


def test_should_parse_numbered_ac_shape_when_partitioning_numbered_spec(
    tmp_path: Path,
) -> None:
    # Arrange/Act — numbered specs use `1. **AC-NNN` markers.
    spec_path = tmp_path / "numbered_spec.md"
    _write_numbered_spec(spec_path, ac_count=13)
    result = _run_cli("partition", str(spec_path), "--threshold", "999")

    # Assert — all 13 numbered ACs surfaced.
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["chunks"][0]["ac_numbers"] == list(range(1, 14))


def test_should_parse_heading_ac_shape_when_partitioning_heading_only_synthetic_spec(
    tmp_path: Path,
) -> None:
    # Arrange — synthesize a heading-shape spec. F019 in shipped/ uses a
    # bullet-list shape (`- **AC-NN:**`) that matches neither parser
    # regex by design, so a synthetic heading-shape fixture is required
    # to prove the parser handles `^###\s+AC-(\d+)`. The bullet shape's
    # graceful zero-AC behavior is asserted separately below.
    spec_path = tmp_path / "heading_spec.md"
    _write_heading_spec(spec_path, ac_count=4)

    # Act
    result = _run_cli("partition", str(spec_path))

    # Assert
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["strategy"] == "single"
    assert payload["chunks"][0]["ac_numbers"] == [1, 2, 3, 4]


def test_should_dedupe_by_ac_number_when_spec_contains_both_numbered_and_heading_shapes(
    tmp_path: Path,
) -> None:
    # Arrange — synthesize a spec where AC-001 appears in BOTH numbered
    # and heading forms (Edge Case 11). Parser must dedupe by AC number
    # and preserve encounter order.
    body = (
        "# Mixed PRD\n\n"
        "## Acceptance Criteria\n"
        "1. **AC-001 — first encounter.** Numbered form body.\n"
        "2. **AC-002 — only numbered.** Body.\n"
        "### AC-001 — second encounter\n"
        "Heading-form duplicate; should be deduped.\n"
        "### AC-003 — only heading\n"
        "Body.\n"
    )
    spec_path = tmp_path / "mixed_spec.md"
    spec_path.write_text(body, encoding="utf-8")

    # Act
    result = _run_cli("partition", str(spec_path))

    # Assert
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    # Three unique ACs, in encounter order, no duplicate AC-001.
    assert payload["chunks"][0]["ac_numbers"] == [1, 2, 3]


def test_should_emit_zero_chunks_when_spec_has_no_recognizable_ac_markers(
    tmp_path: Path,
) -> None:
    # Arrange/Act — bullet-shape `- **AC-NN:**` markers are not recognized
    # per spec design. Edge Case 10: zero recognizable ACs -> strategy
    # "single" with zero chunks.
    spec_path = tmp_path / "bullet_spec.md"
    _write_bullet_spec(spec_path, ac_count=3)
    result = _run_cli("partition", str(spec_path))

    # Assert
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["strategy"] == "single"
    assert payload["chunks"] == []
    # Edge Case 10 mandates the verbatim stderr warning so the
    # operator knows downstream verification will be trivial.
    assert (
        "spec.md contained no recognizable AC markers" in result.stderr
        and "downstream spec-enforcer will produce a trivial verdict"
        in result.stderr
    ), f"missing EC-010 warning in stderr: {result.stderr!r}"


# ── AC-007 — Aggregation OR-semantics ───────────────────────────────────


class TestAggregation:
    """Pure-helper tests for the aggregation OR-semantics (BR-005, AC-007).

    The helper lives in scripts/spec_enforcer_chunker.py so the conductor's
    inline aggregation logic in skills/build/SKILL.md has a tested mirror.
    """

    def test_should_return_compliant_when_all_chunks_returned_compliant(self) -> None:
        # Arrange / Act
        result = spec_enforcer_chunker.aggregate_verdicts(
            ["COMPLIANT", "COMPLIANT"]
        )
        # Assert
        assert result == "COMPLIANT"

    def test_should_return_non_compliant_when_any_chunk_returned_non_compliant(
        self,
    ) -> None:
        # Arrange / Act
        result = spec_enforcer_chunker.aggregate_verdicts(
            ["COMPLIANT", "NON-COMPLIANT"]
        )
        # Assert
        assert result == "NON-COMPLIANT"

    def test_should_return_non_compliant_when_any_chunk_returned_insufficient_evidence(
        self,
    ) -> None:
        # Arrange / Act
        result = spec_enforcer_chunker.aggregate_verdicts(
            ["COMPLIANT", "INSUFFICIENT_EVIDENCE"]
        )
        # Assert
        assert result == "NON-COMPLIANT"

    def test_should_return_compliant_when_verdict_list_is_empty(self) -> None:
        # Arrange / Act — vacuous truth: no chunks → no failures.
        result = spec_enforcer_chunker.aggregate_verdicts([])
        # Assert
        assert result == "COMPLIANT"

    def test_should_prefer_non_compliant_over_insufficient_evidence_in_mixed_lists(
        self,
    ) -> None:
        # Arrange / Act — both flagged; NON-COMPLIANT wins per BR-005.
        result = spec_enforcer_chunker.aggregate_verdicts(
            ["NON-COMPLIANT", "INSUFFICIENT_EVIDENCE", "COMPLIANT"]
        )
        # Assert
        assert result == "NON-COMPLIANT"


# ── AC-009 — Backward compat fast path on F026 ──────────────────────────


def test_should_emit_single_strategy_when_thirteen_ac_spec_runs_with_threshold_above_thirteen(
    tmp_path: Path,
) -> None:
    # Arrange/Act — with 13 ACs and --threshold 999, the chunker must NOT
    # engage the chunked path. This is the byte-shape parity check for the
    # legacy single-dispatch contract (BR-007 / AC-009).
    spec_path = tmp_path / "thirteen_ac_spec.md"
    _write_numbered_spec(spec_path, ac_count=13)
    result = _run_cli(
        "partition", str(spec_path), "--threshold", "999"
    )

    # Assert
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["strategy"] == "single"
    assert len(payload["chunks"]) == 1
    assert payload["chunks"][0]["ac_numbers"] == list(range(1, 14))


# ── Edge cases from spec.md Edge Cases section ──────────────────────────


def test_should_emit_single_with_zero_chunks_when_spec_has_zero_acs(
    tmp_path: Path,
) -> None:
    # Edge Case 5 — empty AC list.
    spec_path = tmp_path / "no_acs.md"
    spec_path.write_text("# Empty PRD\n\nNo ACs here.\n", encoding="utf-8")

    result = _run_cli("partition", str(spec_path))

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["strategy"] == "single"
    assert payload["chunks"] == []


def test_should_emit_single_with_one_chunk_when_spec_has_one_ac(
    tmp_path: Path,
) -> None:
    # Edge Case 4 — exactly one AC.
    spec_path = tmp_path / "one_ac.md"
    _write_numbered_spec(spec_path, ac_count=1)

    result = _run_cli("partition", str(spec_path))

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["strategy"] == "single"
    assert payload["chunks"][0]["ac_numbers"] == [1]


def test_should_emit_single_strategy_when_ac_count_equals_threshold_exactly(
    tmp_path: Path,
) -> None:
    # Edge Case 1 — threshold is inclusive; 10 ACs at threshold 10 → single.
    spec_path = tmp_path / "ten_acs.md"
    _write_numbered_spec(spec_path, ac_count=10)

    result = _run_cli("partition", str(spec_path))

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["strategy"] == "single"
    assert len(payload["chunks"][0]["ac_numbers"]) == 10


def test_should_emit_two_chunks_six_and_five_when_spec_has_eleven_acs(
    tmp_path: Path,
) -> None:
    # Edge Case 2 — threshold + 1 → chunked, last chunk smaller.
    spec_path = tmp_path / "eleven_acs.md"
    _write_numbered_spec(spec_path, ac_count=11)

    result = _run_cli("partition", str(spec_path))

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["strategy"] == "chunked"
    assert [len(c["ac_numbers"]) for c in payload["chunks"]] == [6, 5]


def test_should_emit_two_equal_chunks_when_ac_count_is_chunk_size_multiple(
    tmp_path: Path,
) -> None:
    # Edge Case 3 — 12 ACs at chunk size 6 → 2 chunks of 6, no smaller tail.
    spec_path = tmp_path / "twelve_acs.md"
    _write_numbered_spec(spec_path, ac_count=12)

    result = _run_cli("partition", str(spec_path))

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["strategy"] == "chunked"
    assert [len(c["ac_numbers"]) for c in payload["chunks"]] == [6, 6]


def test_should_exit_nonzero_when_chunk_size_is_zero(tmp_path: Path) -> None:
    # Edge Case 8 — --chunk-size 0 is rejected.
    spec_path = tmp_path / "small.md"
    _write_numbered_spec(spec_path, ac_count=3)

    result = _run_cli(
        "partition", str(spec_path), "--chunk-size", "0"
    )

    assert result.returncode == 1
    assert "chunk-size" in result.stderr.lower()


def test_should_exit_nonzero_when_threshold_is_zero(tmp_path: Path) -> None:
    # Edge Case 8 — --threshold 0 is rejected.
    spec_path = tmp_path / "small.md"
    _write_numbered_spec(spec_path, ac_count=3)

    result = _run_cli(
        "partition", str(spec_path), "--threshold", "0"
    )

    assert result.returncode == 1
    assert "threshold" in result.stderr.lower()


def test_should_exit_nonzero_when_spec_path_does_not_exist(tmp_path: Path) -> None:
    # Edge Case 9 — missing path.
    missing = tmp_path / "does_not_exist.md"

    result = _run_cli("partition", str(missing))

    assert result.returncode == 1
    assert str(missing) in result.stderr or "not found" in result.stderr.lower()


def test_should_emit_effective_chunk_size_and_threshold_to_stderr(
    tmp_path: Path,
) -> None:
    # Edge Case 7 — operator-transparency: effective values printed to stderr.
    spec_path = tmp_path / "small.md"
    _write_numbered_spec(spec_path, ac_count=3)

    result = _run_cli(
        "partition", str(spec_path), "--chunk-size", "7", "--threshold", "12"
    )

    assert result.returncode == 0, result.stderr
    assert "7" in result.stderr
    assert "12" in result.stderr


# ── Public-API contracts (Python import, not CLI) ───────────────────────


def test_should_return_dict_with_strategy_and_chunks_when_partition_called_directly(
    tmp_path: Path,
) -> None:
    # The conductor will invoke the CLI, but the Python-level helper must
    # remain importable so callers (including the aggregation tests above)
    # can compose it without spawning a subprocess.
    spec_path = tmp_path / "small.md"
    _write_numbered_spec(spec_path, ac_count=3)

    payload = spec_enforcer_chunker.partition(spec_path)

    assert payload["strategy"] == "single"
    assert payload["chunks"][0]["ac_numbers"] == [1, 2, 3]


def test_should_raise_value_error_when_partition_called_with_zero_chunk_size(
    tmp_path: Path,
) -> None:
    # Public-API contract: ValueError on chunk_size <= 0 (per design.md
    # exit-1 mapping; CLI catches this and translates to exit code 1).
    spec_path = tmp_path / "small.md"
    _write_numbered_spec(spec_path, ac_count=3)

    with pytest.raises(ValueError):
        spec_enforcer_chunker.partition(spec_path, chunk_size=0)


def test_should_raise_value_error_when_partition_called_with_zero_threshold(
    tmp_path: Path,
) -> None:
    spec_path = tmp_path / "small.md"
    _write_numbered_spec(spec_path, ac_count=3)

    with pytest.raises(ValueError):
        spec_enforcer_chunker.partition(spec_path, threshold=0)
