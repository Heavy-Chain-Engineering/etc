"""spec_enforcer_chunker.py — Partition spec.md ACs for chunked dispatch.

Feature: F-2026-05-22-spec-enforcer-hierarchical-breakdown — Task 001.

The /build pipeline's Step 7 item 3 dispatches the ``spec-enforcer``
subagent against every AC in a feature's ``spec.md``. The agent operates
under a hard 20-tool-call budget plus a maxTurns=8 cap
(``agents/spec-enforcer.md`` lines 22, 25, 41-46). Empirically, 13+ ACs
exhaust this budget and require SendMessage continuation; 25+ ACs would
fail the gate outright.

This helper adds hierarchical chunking AT THE CONDUCTOR LAYER. The
spec-enforcer agent definition is UNCHANGED — chunking happens before
dispatch. When the AC count is above a tunable threshold (default 10),
the conductor partitions the AC list into chunks of a tunable size
(default 6) and fans out N parallel spec-enforcer dispatches, one per
chunk, in a single orchestrator turn. Verdicts are aggregated with
OR-semantics (any chunk NON-COMPLIANT → overall NON-COMPLIANT).

Public API:
- ``partition(spec_path, chunk_size, threshold) -> dict`` — Parse the
  spec at ``spec_path``, identify ACs by either numbered (``1. **AC-NNN``)
  or heading (``### AC-NNN``) shape, and emit the chunk partition.
- ``aggregate_verdicts(verdicts) -> str`` — Apply BR-005 OR-semantics
  across per-chunk verdicts. Pure helper; the conductor mirrors the same
  logic inline in skills/build/SKILL.md prose.

CLI surface (BR-006):
    python3 scripts/spec_enforcer_chunker.py partition <spec_path> \\
        [--chunk-size N] [--threshold M]

Stdout: JSON object per the schema in spec.md / design.md.
Stderr: effective chunk-size + threshold values (operator transparency),
plus error messages on failure.

Exit codes:
- 0 — partition emitted to stdout
- 1 — missing path, invalid flags (--chunk-size or --threshold ≤ 0),
      or other IO error.

Stdlib only per BR-008: ``re``, ``argparse``, ``json``, ``pathlib``,
``sys``. No third-party deps. No shell-out. No writes outside stdout
and stderr.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# ── Module constants ────────────────────────────────────────────────────

#: AC count above which the chunked dispatch path engages. At or below
#: this value, the conductor uses the legacy single-dispatch shape with
#: zero overhead. Default of 10 chosen empirically: F026 hit the
#: 20-tool-call wall at 13 ACs, so 10 leaves headroom for ~7 tool calls
#: per AC on the single-dispatch path. Tune downward if future specs
#: with denser ACs (e.g., heavy AC-level reachability evidence) exhaust
#: the budget earlier.
_DEFAULT_THRESHOLD = 10

#: ACs per chunk in the chunked dispatch path. The last chunk may be
#: smaller (13 ACs at chunk size 6 → 6 + 6 + 1). Default of 6 chosen
#: empirically: F026 verified 12 ACs cleanly before hitting trouble at
#: AC-009 (a test-file-split investigation), so 6 leaves ~3 tool calls
#: per AC under the budget cap — enough for one Read + targeted Grep
#: per AC with margin for one inconclusive retry.
_DEFAULT_CHUNK_SIZE = 6

#: Regex matching a numbered-shape AC marker at the start of a line.
#: Matches `1. **AC-001 — ...` (the F026 shipped convention). Capture
#: group 1 is the AC integer. ``re.MULTILINE`` is set at use-site.
_AC_NUMBERED_RE = re.compile(r"^(\d+)\.\s+\*\*AC-(\d+)", re.MULTILINE)

#: Regex matching a heading-shape AC marker at the start of a line.
#: Matches `### AC-001 — ...`. Capture group 1 is the AC integer.
#: ``re.MULTILINE`` is set inline in the pattern.
_AC_HEADING_RE = re.compile(r"^###\s+AC-(\d+)", re.MULTILINE)

#: Strategy literal emitted when AC count is ≤ threshold.
_STRATEGY_SINGLE = "single"

#: Strategy literal emitted when AC count is > threshold.
_STRATEGY_CHUNKED = "chunked"


# ── Public API ──────────────────────────────────────────────────────────


def partition(
    spec_path: Path,
    chunk_size: int = _DEFAULT_CHUNK_SIZE,
    threshold: int = _DEFAULT_THRESHOLD,
) -> dict[str, object]:
    """Partition the ACs in ``spec_path`` into a chunk plan.

    Parses ``spec_path`` for AC markers (both numbered and heading
    shapes), dedupes by AC number, preserves encounter order, and emits
    a dict matching the JSON schema documented in spec.md / design.md.

    When the parsed AC count is ≤ ``threshold``, returns
    ``{"strategy": "single", "chunks": [<one chunk with all ACs>]}``
    (or zero chunks when no ACs are present). When the count exceeds
    ``threshold``, returns ``{"strategy": "chunked", "chunks": [...]}``
    with ``ceil(count / chunk_size)`` chunks; the last chunk may carry
    fewer ACs than ``chunk_size``.

    Args:
        spec_path: Filesystem path to a spec.md (or any markdown file)
            to scan. Must exist on disk; ``FileNotFoundError`` is raised
            otherwise.
        chunk_size: ACs per chunk in the chunked path. Must be > 0.
        threshold: AC count above which chunking engages. Must be > 0.

    Returns:
        A dict with keys ``strategy`` ("single" or "chunked") and
        ``chunks`` (a list of dicts, each with ``chunk_id``,
        ``ac_numbers``, and ``ac_text``).

    Raises:
        ValueError: If ``chunk_size <= 0`` or ``threshold <= 0``.
        FileNotFoundError: If ``spec_path`` does not exist.
    """
    if chunk_size <= 0:
        raise ValueError(
            f"chunk_size must be > 0 (got {chunk_size})"
        )
    if threshold <= 0:
        raise ValueError(
            f"threshold must be > 0 (got {threshold})"
        )
    if not spec_path.is_file():
        raise FileNotFoundError(f"spec path does not exist: {spec_path}")

    text = spec_path.read_text(encoding="utf-8")
    ac_numbers = _parse_ac_numbers(text)

    if len(ac_numbers) <= threshold:
        return _build_single_strategy(ac_numbers)
    return _build_chunked_strategy(ac_numbers, chunk_size)


def aggregate_verdicts(verdicts: list[str]) -> str:
    """Apply BR-005 OR-semantics across per-chunk spec-enforcer verdicts.

    The conductor mirrors this logic inline in skills/build/SKILL.md
    prose. This pure helper exists for unit-testability per AC-007 and
    so future callers (if extracted) have a single source of truth.

    Rules (BR-005):
    - If any chunk returned ``NON-COMPLIANT`` → overall ``NON-COMPLIANT``.
    - Else if any chunk returned ``INSUFFICIENT_EVIDENCE`` → overall
      ``NON-COMPLIANT`` (treat as fail-closed with remediation guidance).
    - Else → overall ``COMPLIANT``. Empty input vacuously yields
      ``COMPLIANT`` (no chunks, no failures).

    Args:
        verdicts: A list of per-chunk verdict strings. Each value is
            expected to be one of ``COMPLIANT``, ``NON-COMPLIANT``, or
            ``INSUFFICIENT_EVIDENCE``. Unknown values fall through to
            the ``COMPLIANT`` branch (callers should validate upstream).

    Returns:
        ``"NON-COMPLIANT"`` if any chunk failed or was inconclusive;
        ``"COMPLIANT"`` otherwise.
    """
    if any(v == "NON-COMPLIANT" for v in verdicts):
        return "NON-COMPLIANT"
    if any(v == "INSUFFICIENT_EVIDENCE" for v in verdicts):
        return "NON-COMPLIANT"
    return "COMPLIANT"


# ── Internals ───────────────────────────────────────────────────────────


def _parse_ac_numbers(text: str) -> list[int]:
    """Return AC numbers found in ``text``, deduped, in encounter order.

    Scans both numbered (``^\\d+\\.\\s+\\*\\*AC-(\\d+)``) and heading
    (``^###\\s+AC-(\\d+)``) shapes. The two regexes are matched
    independently across the full text; results are merged by line
    position so the final list preserves the order in which ACs appear
    in the spec.

    Dedupes by AC integer value (Edge Case 11 — a spec containing the
    same AC number under both shapes counts it once, at its first
    appearance).
    """
    found: list[tuple[int, int]] = []  # (offset_in_text, ac_number)
    for match in _AC_NUMBERED_RE.finditer(text):
        # Group 2 is the AC integer; group 1 is the markdown ordinal.
        found.append((match.start(), int(match.group(2))))
    for match in _AC_HEADING_RE.finditer(text):
        found.append((match.start(), int(match.group(1))))

    # Sort by encounter order in the file, then dedupe by AC number.
    found.sort(key=lambda pair: pair[0])
    seen: set[int] = set()
    ordered: list[int] = []
    for _, ac_number in found:
        if ac_number in seen:
            continue
        seen.add(ac_number)
        ordered.append(ac_number)
    return ordered


def _build_single_strategy(ac_numbers: list[int]) -> dict[str, object]:
    """Return the single-dispatch partition for ``ac_numbers``.

    On an empty AC list, emits ``chunks: []`` (Edge Case 5).
    """
    if not ac_numbers:
        return {"strategy": _STRATEGY_SINGLE, "chunks": []}
    return {
        "strategy": _STRATEGY_SINGLE,
        "chunks": [_make_chunk(0, ac_numbers)],
    }


def _build_chunked_strategy(
    ac_numbers: list[int], chunk_size: int
) -> dict[str, object]:
    """Return the chunked partition for ``ac_numbers``.

    Chunks are emitted in encounter order, each of size ``chunk_size``
    except possibly the last (which may be smaller per BR-002).
    """
    chunks: list[dict[str, object]] = []
    for chunk_id, start in enumerate(range(0, len(ac_numbers), chunk_size)):
        slice_ = ac_numbers[start:start + chunk_size]
        chunks.append(_make_chunk(chunk_id, slice_))
    return {"strategy": _STRATEGY_CHUNKED, "chunks": chunks}


def _make_chunk(chunk_id: int, ac_numbers: list[int]) -> dict[str, object]:
    """Return one chunk dict.

    The ``ac_text`` field carries a short human-readable summary that
    the conductor's briefing-prompt template embeds verbatim. v1
    emission is the literal list of ``AC-NNN`` tokens joined by commas,
    which is sufficient for the spec-enforcer's per-AC scoping (the
    agent re-reads spec.md for full AC text). Future revs may expand
    this to the full numbered/heading body text once a second consumer
    needs it (twice-before-abstracting).
    """
    return {
        "chunk_id": chunk_id,
        "ac_numbers": list(ac_numbers),
        "ac_text": ", ".join(f"AC-{n:03d}" for n in ac_numbers),
    }


# ── CLI ─────────────────────────────────────────────────────────────────


def _build_parser() -> argparse.ArgumentParser:
    """Build the argparse parser with the ``partition`` subcommand.

    The single-subcommand shape mirrors the existing ``feature_id.py``
    and ``completion_report.py`` CLIs so operators see a consistent
    invocation form across stdlib helpers under ``scripts/``.
    """
    parser = argparse.ArgumentParser(
        prog="spec_enforcer_chunker.py",
        description=(
            "Partition spec.md ACs into chunks for the /build conductor's "
            "Step 7 item 3 hierarchical spec-enforcer dispatch."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    part = sub.add_parser(
        "partition",
        help="Emit a JSON chunk-partition plan for one spec.md.",
    )
    part.add_argument(
        "spec_path",
        type=Path,
        help="Path to a spec.md (or any markdown file) to partition.",
    )
    part.add_argument(
        "--chunk-size",
        type=int,
        default=_DEFAULT_CHUNK_SIZE,
        help=(
            f"ACs per chunk in the chunked path "
            f"(default {_DEFAULT_CHUNK_SIZE}, must be > 0)."
        ),
    )
    part.add_argument(
        "--threshold",
        type=int,
        default=_DEFAULT_THRESHOLD,
        help=(
            f"AC count above which chunking engages "
            f"(default {_DEFAULT_THRESHOLD}, must be > 0)."
        ),
    )
    return parser


def _cmd_partition(args: argparse.Namespace) -> int:
    """Handle the ``partition`` subcommand.

    Returns a process exit code: 0 on success, 1 on validation or IO
    error (with a one-line stderr message). Emits effective chunk-size
    + threshold values to stderr for operator transparency (Edge Case 7).
    """
    print(
        f"effective chunk-size={args.chunk_size} threshold={args.threshold}",
        file=sys.stderr,
    )
    try:
        payload = partition(
            args.spec_path,
            chunk_size=args.chunk_size,
            threshold=args.threshold,
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"error: failed to read spec: {exc}", file=sys.stderr)
        return 1

    # Edge Case 10 (spec.md): when the spec contains no recognizable AC
    # markers, emit the documented warning to stderr so the operator
    # knows downstream verification will produce a trivial verdict.
    if not payload.get("chunks"):
        print(
            "warning: spec.md contained no recognizable AC markers; "
            "downstream spec-enforcer will produce a trivial verdict",
            file=sys.stderr,
        )

    print(json.dumps(payload, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns the exit code; does not call ``sys.exit``."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "partition":
        return _cmd_partition(args)
    # argparse with required=True should make this unreachable.
    parser.print_help(sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
