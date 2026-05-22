"""diagnostic_evidence.py — validate evidence blocks, emit audit-log rows.

Domain-layer module for F021 (Diagnostic-Dismissal Discipline). Provides
the structural-evidence validator that hooks/check-diagnostic-evidence.sh
and hooks/check-completion-discipline.sh invoke to verify a quality-tool
dismissal carries a parseable YAML evidence block, and the append-only
emitter that records each decision to the F019 audit-log surface at
``<cwd>/.etc_sdlc/efficiency/turn-events.jsonl``.

Evidence block schema (transient, agent-emitted, Entity 1 in design.md):

    tool_rerun_command: "<verbatim shell command the agent executed>"
    tool_rerun_output:  "<verbatim stdout+stderr captured from the re-run>"
    attribution:        "<one-line dismissal reason>"
    evidence_type:      <interpreter-diff | version-diff | upstream-issue
                         | repro | error-is-real>

All four fields required and non-empty. ``evidence_type`` is matched
case-insensitively per architect gray-area GA-004.

Block discovery (GA-005): the validator scans the input text for any
YAML structure — fenced ``` ```yaml ``` block, indented mapping, or
inline mapping — that parses as a dict and contains at least one of the
four required field names. More than one such candidate is rejected as
ambiguous (GA-006).

Audit-log row schema (persistent, Entity 2 in design.md):

    {ts, event_type, feature_id?, wave_num?, tool_name?,
     evidence_type?, decision, reason?}

``event_type`` is restricted to the two F021 values; ``ts`` is
auto-injected as ISO-8601 UTC when not caller-supplied. Append-only via
``Path.open('a')``; parent directory created idempotently.

Public surface:
    REQUIRED_FIELDS:       frozenset[str]
    EVIDENCE_TYPE_ENUM:    frozenset[str]
    FORBIDDEN_PHRASES_SEED: tuple[str, ...]
    ValidationResult:      frozen dataclass(valid, reason, parsed)
    validate_block(text):  pure function -> ValidationResult
    emit_event(event_type, payload, cwd): append JSONL row; raises
        ValueError on out-of-enum event_type.

Errors:
    ``validate_block`` never raises; rejection paths return
    ``ValidationResult(valid=False, reason=<specific>, parsed=None)``.
    ``emit_event`` raises ``ValueError`` when ``event_type`` falls
    outside the F021 enum (so misuse by a caller surfaces loudly), and
    propagates ``OSError`` from filesystem failures.

Security boundaries (per design.md):
    - YAML parsing uses ``yaml.safe_load`` exclusively.
    - Filesystem writes use ``Path.open('a')`` (append-only).
    - No shell invocation, no subprocess spawn, no network.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

REQUIRED_FIELDS: frozenset[str] = frozenset(
    {
        "tool_rerun_command",
        "tool_rerun_output",
        "attribution",
        "evidence_type",
    }
)

# GA-004: stored lowercase so case-insensitive matching is a simple
# normalize-then-membership-check.
EVIDENCE_TYPE_ENUM: frozenset[str] = frozenset(
    {
        "interpreter-diff",
        "version-diff",
        "upstream-issue",
        "repro",
        "error-is-real",
    }
)

# BR-002: illustrative seed list — DOCUMENTATION, not enforcement. The
# structural contract (REQUIRED_FIELDS + EVIDENCE_TYPE_ENUM) is what
# defends against paraphrase drift; this tuple exists so the standard
# doc and tests can cross-reference the observed templates.
FORBIDDEN_PHRASES_SEED: tuple[str, ...] = (
    "host-env false positive",
    "stale cache",
    "noise",
    "tooling drift",
    "diagnostic engine running elsewhere",
    "the IDE is confused",
)

# F021 audit-log event_type enum (BR-007). Closed set; emit_event
# rejects anything else with ValueError.
_VALID_EVENT_TYPES: frozenset[str] = frozenset(
    {
        "diagnostic_dismissal_with_evidence",
        "diagnostic_dismissal_missing_evidence",
    }
)

# F019 audit-log surface (Entity 2 in design.md). The hook layer and
# emit_event share this constant via the public function signature.
_AUDIT_LOG_RELATIVE_PATH: tuple[str, str, str] = (
    ".etc_sdlc",
    "efficiency",
    "turn-events.jsonl",
)

# Fenced-block matcher used during candidate discovery. Captures the
# body between an opening ``` (with optional language tag) and the next
# ``` on its own line. re.DOTALL because evidence blocks span newlines.
_FENCED_BLOCK_RE: re.Pattern[str] = re.compile(
    r"^```[ \t]*[A-Za-z0-9_+-]*[ \t]*\n(.*?)\n```",
    re.DOTALL | re.MULTILINE,
)


@dataclass(frozen=True)
class ValidationResult:
    """Outcome of ``validate_block``.

    Attributes:
        valid: True iff exactly one candidate block was found and every
            required field was present, non-empty, and (for
            evidence_type) within the controlled enum.
        reason: Human-readable rejection reason on ``valid=False``; None
            on ``valid=True``. Names the specific failure so the hook
            can surface it via Pattern B stderr.
        parsed: The parsed mapping when ``valid=True``; None otherwise.
            evidence_type is normalized to lowercase in this dict so
            downstream consumers (audit-log emission) see the canonical
            value regardless of agent casing.
    """

    valid: bool
    reason: str | None
    parsed: dict[str, Any] | None


def validate_block(text: str) -> ValidationResult:
    """Validate an agent response carries exactly one well-formed block.

    Pure function. No I/O, no global state read or written. Safe to
    invoke from any hook context including a Claude Code subprocess.

    Discovery strategy (GA-005): collect every YAML candidate from the
    input — first the bodies of fenced ``` ``` blocks, then the whole
    document as a final fallback — and keep those that parse to a
    mapping containing at least one of the four required field names.

    Args:
        text: Free-form agent response text; may contain prose,
            multiple fenced blocks, and YAML in any placement.

    Returns:
        ValidationResult. ``valid=True`` iff exactly one candidate block
        contains all four required fields non-empty AND
        ``evidence_type`` (case-folded) is in EVIDENCE_TYPE_ENUM.
    """
    candidates = _discover_candidate_blocks(text)

    if len(candidates) == 0:
        return ValidationResult(
            valid=False,
            reason="no parseable YAML evidence block found in response",
            parsed=None,
        )

    if len(candidates) > 1:
        return ValidationResult(
            valid=False,
            reason=(
                f"ambiguous: {len(candidates)} candidate evidence blocks "
                f"found in response (multiple blocks rejected per GA-006)"
            ),
            parsed=None,
        )

    return _validate_single_block(candidates[0])


def _discover_candidate_blocks(text: str) -> list[dict[str, Any]]:
    """Return every YAML mapping containing >=1 required field.

    A "candidate block" is any YAML segment in ``text`` that parses to a
    dict AND contains at least one of the four REQUIRED_FIELDS names as
    a top-level key.

    Discovery strategy: try every fenced ``` ``` block body first; each
    successful fenced parse is one candidate. If NO fenced candidate
    parses (e.g., bare YAML without fences in the response), fall back
    to parsing the whole document as a single segment so GA-005's
    any-YAML-structure contract is honored. Two fenced blocks that
    happen to share identical content count as TWO candidates — the
    agent emitted two blocks, the validator must reject for ambiguity
    per GA-006.
    """
    candidates: list[dict[str, Any]] = []

    for body in _iter_fenced_block_bodies(text):
        mapping = _safe_load_mapping(body)
        if mapping is None:
            continue
        if not _has_any_required_field(mapping):
            continue
        candidates.append(mapping)

    if candidates:
        return candidates

    fallback = _safe_load_mapping(text)
    if fallback is not None and _has_any_required_field(fallback):
        candidates.append(fallback)

    return candidates


def _iter_fenced_block_bodies(text: str) -> list[str]:
    """Return the body of every fenced ``` ``` block in ``text``."""
    return [match.group(1) for match in _FENCED_BLOCK_RE.finditer(text)]


def _safe_load_mapping(body: str) -> dict[str, Any] | None:
    """Parse ``body`` as YAML; return the dict or None on any failure.

    Non-mapping YAML (lists, scalars) and parse errors both return None
    — neither shape can satisfy the four-required-field contract.
    """
    try:
        parsed = yaml.safe_load(body)
    except yaml.YAMLError:
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed


def _has_any_required_field(mapping: dict[str, Any]) -> bool:
    """True iff at least one REQUIRED_FIELDS key is present in mapping."""
    return any(field in mapping for field in REQUIRED_FIELDS)


def _validate_single_block(block: dict[str, Any]) -> ValidationResult:
    """Validate the four-field contract on a single discovered mapping.

    Order of checks: missing fields first (so the agent sees the most
    actionable error), then empty-field check, then enum membership.
    """
    missing = sorted(field for field in REQUIRED_FIELDS if field not in block)
    if missing:
        return ValidationResult(
            valid=False,
            reason=(
                f"evidence block missing required field(s): "
                f"{', '.join(missing)}"
            ),
            parsed=None,
        )

    empty = sorted(
        field for field in REQUIRED_FIELDS if _is_empty(block[field])
    )
    if empty:
        return ValidationResult(
            valid=False,
            reason=(
                f"evidence block has empty value(s) for required "
                f"field(s): {', '.join(empty)}"
            ),
            parsed=None,
        )

    raw_evidence_type = block["evidence_type"]
    if not isinstance(raw_evidence_type, str):
        return ValidationResult(
            valid=False,
            reason=(
                f"evidence_type must be a string; got "
                f"{type(raw_evidence_type).__name__}"
            ),
            parsed=None,
        )

    normalized = raw_evidence_type.strip().lower()
    if normalized not in EVIDENCE_TYPE_ENUM:
        return ValidationResult(
            valid=False,
            reason=(
                f"evidence_type {raw_evidence_type!r} is not in the "
                f"controlled enum {sorted(EVIDENCE_TYPE_ENUM)}"
            ),
            parsed=None,
        )

    canonicalized = dict(block)
    canonicalized["evidence_type"] = normalized
    return ValidationResult(valid=True, reason=None, parsed=canonicalized)


def _is_empty(value: Any) -> bool:
    """True if value is None, empty string, or all-whitespace string.

    Non-string, non-None values (numbers, booleans, mappings, lists) are
    treated as non-empty here — the structural contract speaks to
    field presence, and downstream type checks live at the call site
    (currently: evidence_type-must-be-string in _validate_single_block).
    """
    if value is None:
        return True
    if isinstance(value, str) and value.strip() == "":
        return True
    return False


def emit_event(event_type: str, payload: dict[str, Any], cwd: Path) -> None:
    """Append a JSONL row to the F019 audit-log surface.

    Writes to ``<cwd>/.etc_sdlc/efficiency/turn-events.jsonl``. Parent
    directories are created idempotently. The write is append-only via
    ``Path.open('a')`` — Data Model Invariant 1 (audit log is
    append-only, no row mutation).

    Auto-injects ``ts`` as ISO-8601 UTC when not already present in
    ``payload``; a caller-supplied ``ts`` (e.g. for replay or for tests
    pinning a specific moment) is preserved verbatim.

    Args:
        event_type: One of {diagnostic_dismissal_with_evidence,
            diagnostic_dismissal_missing_evidence}. BR-007 enum.
        payload: Mapping of remaining row fields. ``event_type`` in
            ``payload`` is overridden by the ``event_type`` argument so
            the on-disk row matches the function call.
        cwd: Project root under which ``.etc_sdlc/efficiency/`` lives.
            Caller-provided so the function is callable from any
            working directory (hooks resolve cwd via Claude Code JSON).

    Raises:
        ValueError: If ``event_type`` is not in the F021 enum. The log
            file is NOT created on rejection — misuse surfaces loudly
            without polluting the audit surface.
        OSError: Propagated from the filesystem layer (caller's
            responsibility; design.md GA-007 documents the hook-layer
            warn-and-skip wrapper).
    """
    if event_type not in _VALID_EVENT_TYPES:
        msg = (
            f"event_type {event_type!r} is not a valid F021 event; "
            f"expected one of: {sorted(_VALID_EVENT_TYPES)}"
        )
        raise ValueError(msg)

    row: dict[str, Any] = dict(payload)
    row["event_type"] = event_type
    if "ts" not in row:
        row["ts"] = _utc_now_iso8601()

    log_path = cwd.joinpath(*_AUDIT_LOG_RELATIVE_PATH)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True))
        handle.write("\n")


def _utc_now_iso8601() -> str:
    """Return the current UTC instant as an ISO-8601 string.

    Format: ``YYYY-MM-DDTHH:MM:SS.ffffff+00:00``. ``datetime.now(tz)``
    is preferred over ``utcnow()`` (deprecated in 3.12) so the result
    carries explicit tzinfo and round-trips through
    ``datetime.fromisoformat``.
    """
    return datetime.now(timezone.utc).isoformat()
