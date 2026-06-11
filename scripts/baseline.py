"""baseline.py — single owner of the architecture-baseline.yaml format.

Implements the core read/validate/status surface of the brownfield
architecture-baseline feature (F-2026-06-10): the machine baseline at
``.etc_sdlc/architecture-baseline.yaml`` and its schema. This module is the
ONLY component that parses the baseline format (skills/hooks read at most the
single status token via this CLI); see design.md "Module Structure" and
gray-areas GA-A06.

Schema (v1) — the machine baseline (per repo):
    schema_version: int (currently 1)
    status:         str  (closed enum: unratified | ratified; one-way)
    ratified_by:    str | None  (non-null iff ratified; sanitized, 64-char cap)
    ratified_at:    str | None  (ISO-8601; non-null iff ratified)
    confidence:     mapping {score: low|medium|high, inputs: {...}}
    inventory:      list  (DISCOVER output: candidate normative artifacts)
    claims:         list  (VERIFY output: claim ledger; classification enum)
    exemplars:      list  (RATIFY output: golden registry)        [optional]
    do_not_copy:    list                                          [optional]
    rules:          list  (ENFORCE input; /rule-sweep appends)
    seams:          list  (per-repo mirror of the workspace seam map)

Invariants (asserted by ``validate_schema``): ``schema_version`` int; reject
unknown top-level fields; ``status``/claim ``classification``/``confidence.
score`` are closed enums; ``ratified_by``/``ratified_at`` non-null iff
``status: ratified``. Future ``schema_version`` is warn-and-skip (``load``
returns None, logs a WARNING) per contract-completeness ADR-002. All writes
are atomic (tempfile + ``os.replace``); free-form strings are sanitized at
the capture site (strip ``[\\x00-\\x1f\\x7f]``, length-cap).

Public surface (later waves — render-doc / sync-seams — compose these):
    SCHEMA_VERSION, REQUIRED_FIELDS
    LEGAL_STATUSES, LEGAL_CLASSIFICATIONS, LEGAL_CONFIDENCE_SCORES
    LEGAL_TRANSITIONS (one-way unratified -> ratified; no inverse exists)
    NAME_MAX_LEN, FREEFORM_MAX_LEN, BASELINE_RELATIVE_PATH
    RatificationBlockedError
    load(path) -> dict | None
    validate_schema(d) -> None
    status_token(repo_root) -> str
    sanitize_freeform(value, *, max_len) -> str
    atomic_dump(path, data) -> None
    init_baseline(repo_root, discover_json) -> Path
    ratify(path, *, ratified_by) -> None
    append_rule(path, *, statement, who, trigger, mechanizable=False) -> str

CLI exit codes (house style per GA-A06): 0 = success, 1 = could-not-evaluate
(usage/IO/missing/malformed-for-status), 2 = domain failure (schema
violation). ``status`` always exits 0 when evaluable and emits one token;
callers branch on the TOKEN, never the code.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

SCHEMA_VERSION: int = 1

# The machine baseline lives at this path inside every target repo / workspace
# repo. Skills resolve <repo_root> / this; the CLI is the only YAML reader.
BASELINE_RELATIVE_PATH: Path = Path(".etc_sdlc") / "architecture-baseline.yaml"

REQUIRED_FIELDS: tuple[str, ...] = (
    "schema_version",
    "status",
    "confidence",
    "inventory",
    "claims",
    "rules",
    "seams",
)

# Optional top-level fields: present in RATIFY output, absent in a fresh
# unratified baseline. Listed so the reject-unknown check does not flag them.
# ``baseline_exempt`` is the operator escape hatch (the GA-A04 ``unratified``
# hard-block release valve): a repo declared out of baseline scope. Its
# presence is consumed by the gate; this module only validates its shape.
_OPTIONAL_FIELDS: frozenset[str] = frozenset(
    {"ratified_by", "ratified_at", "exemplars", "do_not_copy", "baseline_exempt"}
)

_KNOWN_FIELDS: frozenset[str] = frozenset(REQUIRED_FIELDS) | _OPTIONAL_FIELDS

# Closed enums (design.md Data Model). Stored values outside these sets are
# schema violations, surfaced as `malformed` by status_token — never coerced.
LEGAL_STATUSES: frozenset[str] = frozenset({"unratified", "ratified"})
LEGAL_CLASSIFICATIONS: frozenset[str] = frozenset(
    {"VERIFIED", "STALE", "ASPIRATIONAL", "CONTRADICTED"}
)
LEGAL_CONFIDENCE_SCORES: frozenset[str] = frozenset({"low", "medium", "high"})

# The one-way ratification state machine. Mirrors the
# value_hypothesis._LEGAL_TRANSITIONS precedent (a frozenset of legal edges):
# the single legal edge with no reverse and no self-loop is what makes
# de-ratification structurally impossible — there is deliberately no inverse
# function (negative-capability test in tests/test_baseline.py).
LEGAL_TRANSITIONS: frozenset[tuple[str, str]] = frozenset({("unratified", "ratified")})

# Rule defaults (design.md Data Model + layered-review ADR-004 graduation
# metadata). A freshly appended rule is human-judgment-enforced and not yet a
# mechanization candidate; /rule-sweep flips ``mechanizable`` as rules graduate.
_DEFAULT_ENFORCED_BY: str = "human-judgment"

# Sanitization caps (Security Considerations / design Data Model): names are
# capped tighter than general free-form prose.
NAME_MAX_LEN: int = 64
FREEFORM_MAX_LEN: int = 512

# Strip every control-character codepoint matching [\x00-\x1f\x7f] via
# str.translate (keeps the module dependency-free, mirrors value_hypothesis).
_CONTROL_CHAR_TRANSLATION: dict[int, None] = {code: None for code in (*range(0x00, 0x20), 0x7F)}

# The status subcommand emits one of these tokens. `missing`/`malformed` are
# computed (never stored); `unratified`/`ratified` mirror the stored enum.
_STATUS_MISSING: str = "missing"
_STATUS_MALFORMED: str = "malformed"


class RatificationBlockedError(Exception):
    """Raised when ``ratify`` cannot proceed: a non-VERIFIED claim is unresolved.

    This is an expected domain failure (the matrix-walk forcing function found
    an empty cell), not an infrastructure error — callers surface its
    ``blocking_claims`` as one ``CL-NNN: <reason>`` line each and exit 2. The
    message embeds the same lines so a bare ``str(exc)`` is already useful.
    """

    def __init__(self, blocking_claims: list[tuple[str, str]]) -> None:
        self.blocking_claims = blocking_claims
        body = "; ".join(f"{claim_id}: {reason}" for claim_id, reason in blocking_claims)
        super().__init__(f"ratification blocked by unresolved claim(s): {body}")


def sanitize_freeform(value: str, *, max_len: int) -> str:
    """Sanitize a free-form string at the capture site.

    Strips every control-character codepoint matching ``[\\x00-\\x1f\\x7f]``,
    then caps the result at ``max_len`` characters. Control chars are removed
    BEFORE the cap so they do not consume length budget. This is the single
    capture-site defense for untrusted discovered content (claim text, rule
    statements, ratified-by names); see Security Considerations.

    Args:
        value: The raw string to clean.
        max_len: Maximum length of the returned string (use ``NAME_MAX_LEN``
            for names, ``FREEFORM_MAX_LEN`` for general prose).

    Returns:
        The control-char-stripped, length-capped string.
    """
    return value.translate(_CONTROL_CHAR_TRANSLATION)[:max_len]


def load(path: Path) -> dict[str, Any] | None:
    """Read and validate an architecture-baseline YAML file.

    Args:
        path: Path to an ``architecture-baseline.yaml`` file.

    Returns:
        The parsed baseline dict, or None if the file declares a
        ``schema_version`` newer than this reader supports (warn-and-skip per
        contract-completeness ADR-002).

    Raises:
        ValueError: If the file is missing, the YAML is malformed, the top
            level is not a mapping, ``schema_version`` is not an integer, or
            any ``validate_schema`` invariant is violated.
    """
    if not path.exists():
        msg = f"architecture-baseline file not found: {path}"
        raise ValueError(msg)

    raw = path.read_text(encoding="utf-8")
    try:
        parsed = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        msg = f"malformed YAML in {path}: {exc}"
        raise ValueError(msg) from exc

    if not isinstance(parsed, dict):
        msg = f"architecture-baseline at {path} must be a YAML mapping; got {type(parsed).__name__}"
        raise ValueError(msg)

    schema_version = parsed.get("schema_version")
    if not isinstance(schema_version, int) or isinstance(schema_version, bool):
        msg = (
            f"schema_version must be an integer in {path}; "
            f"got {schema_version!r} ({type(schema_version).__name__})"
        )
        raise ValueError(msg)

    if schema_version > SCHEMA_VERSION:
        logger.warning(
            "Skipping %s: unknown future schema_version=%d (supported: %d)",
            path,
            schema_version,
            SCHEMA_VERSION,
        )
        return None

    validate_schema(parsed)
    return parsed


def validate_schema(d: object) -> None:
    """Enforce the design.md Data Model invariants on a baseline dict.

    Typed ``object`` (not ``dict[str, Any]``) because the input originates as
    untrusted parsed YAML whose top-level shape is unverified until the
    isinstance guard below narrows it — mirroring the value_hypothesis.py
    handling of the same untrusted-YAML boundary. Declaring ``dict`` would
    make the runtime guard statically unreachable (Pyright reportUnreachable);
    ``object`` keeps the guard both reachable and type-meaningful.

    Args:
        d: Candidate baseline value to validate (any parsed-YAML object).

    Raises:
        ValueError: If ``d`` is not a mapping, a required field is missing, an
            unknown top-level field is present, ``status`` /
            ``confidence.score`` / any claim ``classification`` is outside its
            closed enum, or the ratified attestation invariant
            (``ratified_by``/``ratified_at`` non-null iff ``status: ratified``)
            is violated.
    """
    if not isinstance(d, dict):
        msg = f"architecture-baseline must be a mapping; got {type(d).__name__}"
        raise ValueError(msg)

    missing = [field for field in REQUIRED_FIELDS if field not in d]
    if missing:
        msg = f"architecture-baseline missing required field(s): {', '.join(missing)}"
        raise ValueError(msg)

    unknown = sorted(set(d.keys()) - _KNOWN_FIELDS)
    if unknown:
        msg = f"architecture-baseline has unknown top-level field(s): {', '.join(unknown)}"
        raise ValueError(msg)

    _validate_status_enum(d["status"])
    _validate_ratified_attestation(d)
    _validate_confidence(d["confidence"])
    _validate_claims(d["claims"])
    _validate_baseline_exempt(d.get("baseline_exempt"))


def _validate_status_enum(status: Any) -> None:
    """Enforce that ``status`` is one of the closed enum values."""
    if status not in LEGAL_STATUSES:
        msg = (
            f"architecture-baseline status {status!r} is not legal; "
            f"expected one of: {sorted(LEGAL_STATUSES)}"
        )
        raise ValueError(msg)


def _validate_ratified_attestation(d: dict[str, Any]) -> None:
    """Enforce ``ratified_by``/``ratified_at`` non-null iff status ratified.

    A ratified baseline must carry both attestation fields; an unratified one
    must carry neither (the one-way transition fills them — see design Data
    Model invariants). Either half being out of sync is a schema violation.
    """
    is_ratified = d["status"] == "ratified"
    has_by = d.get("ratified_by") is not None
    has_at = d.get("ratified_at") is not None
    if is_ratified and not (has_by and has_at):
        msg = (
            "architecture-baseline status is 'ratified' but ratified_by/"
            "ratified_at is null; both must be set on ratification"
        )
        raise ValueError(msg)
    if not is_ratified and (has_by or has_at):
        msg = (
            "architecture-baseline is unratified but carries ratified_by/"
            "ratified_at; attestation is set only on ratification"
        )
        raise ValueError(msg)


def _validate_confidence(confidence: Any) -> None:
    """Enforce that ``confidence.score`` is one of the closed enum values."""
    if not isinstance(confidence, dict):
        msg = f"architecture-baseline confidence must be a mapping; got {type(confidence).__name__}"
        raise ValueError(msg)
    score = confidence.get("score")
    if score not in LEGAL_CONFIDENCE_SCORES:
        msg = (
            f"architecture-baseline confidence.score {score!r} is not legal; "
            f"expected one of: {sorted(LEGAL_CONFIDENCE_SCORES)}"
        )
        raise ValueError(msg)


def _validate_claims(claims: Any) -> None:
    """Enforce that every claim's ``classification`` is in the closed enum."""
    if not isinstance(claims, list):
        msg = f"architecture-baseline claims must be a list; got {type(claims).__name__}"
        raise ValueError(msg)
    for claim in claims:
        if not isinstance(claim, dict):
            msg = f"architecture-baseline claim must be a mapping; got {claim!r}"
            raise ValueError(msg)
        classification = claim.get("classification")
        if classification not in LEGAL_CLASSIFICATIONS:
            claim_id = claim.get("id", "<unknown>")
            msg = (
                f"architecture-baseline claim {claim_id} classification "
                f"{classification!r} is not legal; expected one of: "
                f"{sorted(LEGAL_CLASSIFICATIONS)}"
            )
            raise ValueError(msg)


def _validate_baseline_exempt(exempt: Any) -> None:
    """Enforce the optional ``baseline_exempt`` block's shape when present.

    The hatch is ``{reason: <non-empty str>, recorded_at: <ISO-8601 str>}``
    (wave-0 pin). Absent is fine; present-but-malformed (non-mapping, empty
    reason) is a schema violation. ``status_token`` deliberately does NOT
    reinterpret an exempt baseline — it still returns the stored status; the
    gate consumer decides what exempt means.
    """
    if exempt is None:
        return
    if not isinstance(exempt, dict):
        msg = (
            f"architecture-baseline baseline_exempt must be a mapping; got {type(exempt).__name__}"
        )
        raise ValueError(msg)
    reason = exempt.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        msg = "architecture-baseline baseline_exempt.reason must be a non-empty string"
        raise ValueError(msg)


def status_token(repo_root: Path) -> str:
    """Compute the four-token status of a repo's architecture baseline.

    Args:
        repo_root: The repository root directory to inspect.

    Returns:
        Exactly one of ``missing`` | ``unratified`` | ``ratified`` |
        ``malformed``. A schema-violating or unparseable baseline — including
        one whose stored ``status`` is an unknown value — yields
        ``malformed`` (never a truthy/falsy coercion). The stored enum
        (``unratified``/``ratified``) is mirrored verbatim.

    Raises:
        OSError: If ``repo_root`` exists but is not a directory (a caller
            passed bad input). The CLI maps this to the exit-1
            could-not-evaluate path, distinct from the ``missing`` token (a
            non-existent ``repo_root`` is still ``missing``).
    """
    if repo_root.exists() and not repo_root.is_dir():
        msg = f"repo_root is not a directory: {repo_root}"
        raise NotADirectoryError(msg)

    baseline_path = repo_root / BASELINE_RELATIVE_PATH
    if not baseline_path.exists():
        return _STATUS_MISSING

    try:
        parsed = load(baseline_path)
    except ValueError:
        return _STATUS_MALFORMED

    if parsed is None:
        # Future schema_version (warn-and-skip): this reader cannot vouch for
        # the contents, so it is treated as malformed rather than honored.
        return _STATUS_MALFORMED

    return str(parsed["status"])


def atomic_dump(path: Path, data: dict[str, Any]) -> None:
    """Atomically write ``data`` to ``path`` as canonical YAML.

    Serializes first (so a serialization failure never touches the target),
    writes to a temp file in the same directory, fsyncs, then publishes via a
    single ``os.replace``. On any failure the temp file is unlinked so callers
    never observe a partially-written baseline. This is the single write path
    every later-wave mutator (init / ratify / append-rule / sync-seams) uses.

    Args:
        path: Destination file path. Parent directories are created.
        data: The baseline (or seam-map) dict to serialize.

    Raises:
        yaml.YAMLError | TypeError | ValueError: If ``data`` is not
            serializable. The target file is left untouched.
        OSError: On a filesystem failure during write or rename.
    """
    body = yaml.safe_dump(data, sort_keys=False, default_flow_style=False)

    target_dir = path.parent
    target_dir.mkdir(parents=True, exist_ok=True)

    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(target_dir))
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(str(tmp_path), str(path))
    except OSError:
        _unlink_quietly(tmp_path)
        raise


def _unlink_quietly(path: Path) -> None:
    """Remove ``path`` if present, swallowing the not-found race only.

    Used by ``atomic_dump`` cleanup: the temp file may already be gone if the
    failure happened after the rename. Any other OSError propagates.
    """
    try:
        path.unlink()
    except FileNotFoundError:
        pass


# ── Lifecycle: init / ratify / append-rule ──────────────────────────────
#
# These compose the wave-0 primitives (load + validate_schema + atomic_dump +
# sanitize_freeform) into the three baseline state transitions. They are the
# in-process contract; the CLI subcommands below are thin wrappers that map
# them to the house exit-code semantics.


# DISCOVER+VERIFY engine sections the merged output may carry. Each maps 1:1
# to a baseline field; absent sections default to empty (an empty inventory is
# a valid baseline — the no-docs / greenfield fixture).
_ENGINE_LIST_SECTIONS: tuple[str, ...] = (
    "inventory",
    "claims",
    "exemplars",
    "do_not_copy",
    "seams",
)


def init_baseline(repo_root: Path, discover_json: Path) -> Path:
    """Build an unratified baseline from merged DISCOVER+VERIFY engine output.

    Reads ``discover_json`` (the conductor's merged surveyor ``findings``),
    assembles the canonical unratified baseline, sanitizes free-form claim text
    at the capture site, validates the schema, and atomically writes it to
    ``<repo_root>/.etc_sdlc/architecture-baseline.yaml``.

    Args:
        repo_root: The target repository root.
        discover_json: Path to the merged engine-output JSON.

    Returns:
        The path the baseline was written to.

    Raises:
        ValueError: If ``discover_json`` is missing/unreadable, is not a JSON
            mapping, or yields a baseline that violates the schema.
    """
    payload = _read_discover_json(discover_json)
    baseline = _assemble_unratified_baseline(payload)
    validate_schema(baseline)

    baseline_path = repo_root / BASELINE_RELATIVE_PATH
    atomic_dump(baseline_path, baseline)
    return baseline_path


def _read_discover_json(discover_json: Path) -> dict[str, Any]:
    """Read and shape-check the merged engine-output JSON file."""
    if not discover_json.exists():
        msg = f"discover-json file not found: {discover_json}"
        raise ValueError(msg)
    try:
        parsed = json.loads(discover_json.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        msg = f"malformed JSON in {discover_json}: {exc}"
        raise ValueError(msg) from exc
    if not isinstance(parsed, dict):
        msg = f"discover-json at {discover_json} must be a JSON object; got {type(parsed).__name__}"
        raise ValueError(msg)
    return parsed


def _assemble_unratified_baseline(payload: dict[str, Any]) -> dict[str, Any]:
    """Map merged engine output onto the canonical unratified baseline shape."""
    baseline: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": "unratified",
        "ratified_by": None,
        "ratified_at": None,
        "confidence": payload.get("confidence", {"score": "low", "inputs": {}}),
    }
    for section in _ENGINE_LIST_SECTIONS:
        baseline[section] = list(payload.get(section) or [])
    # Rules accrue post-init via append-rule; never seeded from discovery.
    baseline["rules"] = []
    _sanitize_claim_text(baseline["claims"])
    return baseline


def _sanitize_claim_text(claims: list[Any]) -> None:
    """Strip control chars / cap length on each claim's free-form ``claim``.

    Discovered claim text is untrusted input (Security Considerations); clean
    it at the capture site so only sanitized text ever reaches agent context.
    """
    for claim in claims:
        if isinstance(claim, dict) and isinstance(claim.get("claim"), str):
            claim["claim"] = sanitize_freeform(claim["claim"], max_len=FREEFORM_MAX_LEN)


def ratify(path: Path, *, ratified_by: str) -> None:
    """Perform the one-way unratified -> ratified transition on a baseline.

    Enforces the matrix-walk forcing function: every non-VERIFIED claim must
    carry a non-null ``resolution`` before ratification succeeds. On success
    the attestation fields are set (name sanitized, UTC ISO-8601 timestamp) and
    the file is atomically rewritten. This function's contract is pure
    transition + attestation; rendering ARCHITECTURE.md is wired in by the
    wave-2 render-doc task, not here.

    Args:
        path: Path to the baseline YAML.
        ratified_by: Operator attestation name (sanitized, 64-char cap).

    Raises:
        ValueError: If the file is missing/malformed, or the current status is
            not a legal source for the unratified -> ratified edge (e.g. an
            already-ratified baseline).
        RatificationBlockedError: If any non-VERIFIED claim lacks a resolution.
    """
    baseline = _load_existing(path)

    current = baseline["status"]
    if (current, "ratified") not in LEGAL_TRANSITIONS:
        msg = (
            f"illegal ratification transition {current!r} -> 'ratified'; "
            "only unratified -> ratified is permitted (one-way)"
        )
        raise ValueError(msg)

    blocking = _unresolved_non_verified_claims(baseline["claims"])
    if blocking:
        raise RatificationBlockedError(blocking)

    baseline["status"] = "ratified"
    baseline["ratified_by"] = sanitize_freeform(ratified_by, max_len=NAME_MAX_LEN)
    baseline["ratified_at"] = _utc_now_iso()
    atomic_dump(path, baseline)


def _unresolved_non_verified_claims(claims: list[Any]) -> list[tuple[str, str]]:
    """Return ``(claim_id, reason)`` for each non-VERIFIED claim with no resolution.

    A VERIFIED claim never needs a resolution (it entered tier-0 silently); any
    other classification must be reason-dismissed at the matrix walk, recorded
    as a non-null ``resolution``. The reason text is the gate message body.
    """
    blocking: list[tuple[str, str]] = []
    for claim in claims:
        if not isinstance(claim, dict):
            continue
        if claim.get("classification") == "VERIFIED":
            continue
        if claim.get("resolution") is None:
            claim_id = str(claim.get("id", "CL-???"))
            reason = f"{claim.get('classification', 'non-VERIFIED')} claim has no resolution"
            blocking.append((claim_id, reason))
    return blocking


def append_rule(
    path: Path,
    *,
    statement: str,
    who: str,
    trigger: str,
    mechanizable: bool = False,
) -> str:
    """Atomically append an R-NNN rule; return its id.

    Rules accrue independently of ratification — this works on a ratified
    baseline without reopening it, and on an unratified one too (status is
    never touched here). The new rule carries provenance ``{who, when,
    trigger}``, the ``mechanizable`` graduation flag, and ``enforced_by``
    defaulting to ``human-judgment``. All free-form fields are sanitized at
    capture.

    Args:
        path: Path to the baseline YAML.
        statement: The rule statement (sanitized, free-form cap).
        who: Provenance author (sanitized, name cap).
        trigger: Provenance trigger (sanitized, free-form cap).
        mechanizable: Whether the rule is a baseline-verify graduation candidate.

    Returns:
        The newly assigned rule id, ``R-NNN``.

    Raises:
        ValueError: If the file is missing or malformed.
    """
    baseline = _load_existing(path)
    rules = baseline.setdefault("rules", [])

    rule_id = f"R-{len(rules) + 1:03d}"
    rules.append(
        {
            "id": rule_id,
            "statement": sanitize_freeform(statement, max_len=FREEFORM_MAX_LEN),
            "provenance": {
                "who": sanitize_freeform(who, max_len=NAME_MAX_LEN),
                "when": _utc_now_iso(),
                "trigger": sanitize_freeform(trigger, max_len=FREEFORM_MAX_LEN),
            },
            "mechanizable": mechanizable,
            "enforced_by": _DEFAULT_ENFORCED_BY,
        }
    )
    atomic_dump(path, baseline)
    return rule_id


def _load_existing(path: Path) -> dict[str, Any]:
    """Load a baseline that must already exist and parse cleanly.

    Wraps ``load`` to reject the warn-and-skip ``None`` (future schema_version)
    as a hard error — a mutator cannot safely rewrite a file it cannot fully
    interpret.
    """
    baseline = load(path)
    if baseline is None:
        msg = f"refusing to mutate {path}: unsupported future schema_version"
        raise ValueError(msg)
    return baseline


def _utc_now_iso() -> str:
    """Return the current UTC time as a second-precision ISO-8601 string."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


# ── Command-line interface ──────────────────────────────────────────────
#
# Skills (/init-project, /build, /rule-sweep) invoke this module from
# arbitrary working directories without making `scripts/` importable. The CLI
# is the runtime contract; the in-process helpers above are the contract for
# tests and for later-wave subcommands.


def _cli_validate(args: argparse.Namespace) -> int:
    """``validate <baseline_path>`` — 0 valid, 1 missing/unreadable, 2 schema.

    Distinguishes the could-not-evaluate path (file missing/unreadable → 1)
    from a genuine schema violation (→ 2, with the offending field(s) named
    on stderr) so the schema hook and skills can branch correctly.
    """
    path = Path(args.baseline_path)
    if not path.exists():
        print(f"architecture-baseline file not found: {path}", file=sys.stderr)
        return 1
    try:
        load(path)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return 0


def _cli_status(args: argparse.Namespace) -> int:
    """``status <repo_root>`` — print one token; exit 0 evaluable, 1 IO error.

    The token (``missing`` | ``unratified`` | ``ratified`` | ``malformed``) is
    the contract callers branch on; the exit code only distinguishes
    evaluable (0) from a could-not-inspect IO error (1).
    """
    try:
        token = status_token(Path(args.repo_root))
    except OSError as exc:
        print(f"could not evaluate baseline status: {exc}", file=sys.stderr)
        return 1
    print(token)
    return 0


def _cli_init(args: argparse.Namespace) -> int:
    """``init <repo_root> --from <json>`` — print the written baseline path.

    Exit 0 with the baseline path on stdout; exit 1 (could-not-evaluate) on a
    missing/malformed engine output or a baseline that fails the schema (the
    init path treats a schema failure as bad input, not a domain-2 condition —
    the operator's discovery merge produced something unusable).
    """
    try:
        baseline_path = init_baseline(Path(args.repo_root), Path(args.from_json))
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(str(baseline_path))
    return 0


def _cli_ratify(args: argparse.Namespace) -> int:
    """``ratify <baseline_path> --by <name>`` — one-way transition.

    Exit 0 on success; 2 (domain failure) when a non-VERIFIED claim lacks a
    resolution, listing one ``CL-NNN: <reason>`` per line on stderr; 1 when the
    file is missing/malformed or the transition is otherwise illegal.
    """
    path = Path(args.baseline_path)
    if not path.exists():
        print(f"architecture-baseline file not found: {path}", file=sys.stderr)
        return 1
    try:
        ratify(path, ratified_by=args.by)
    except RatificationBlockedError as exc:
        for claim_id, reason in exc.blocking_claims:
            print(f"{claim_id}: {reason}", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


def _cli_append_rule(args: argparse.Namespace) -> int:
    """``append-rule <baseline_path> --statement … --who … --trigger …``.

    Exit 0 with the new ``R-NNN`` on stdout; 1 when the file is missing or
    malformed. Works on ratified baselines (accrual never reopens ratification).
    """
    path = Path(args.baseline_path)
    if not path.exists():
        print(f"architecture-baseline file not found: {path}", file=sys.stderr)
        return 1
    try:
        rule_id = append_rule(
            path,
            statement=args.statement,
            who=args.who,
            trigger=args.trigger,
            mechanizable=args.mechanizable,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(rule_id)
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="baseline.py",
        description=(
            "Read, validate, and report the status of "
            ".etc_sdlc/architecture-baseline.yaml. Single owner of the "
            "baseline format; used by /init-project, /build, and /rule-sweep."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_validate = sub.add_parser("validate", help="Load a baseline file and enforce the schema.")
    p_validate.add_argument("baseline_path", help="Path to architecture-baseline.yaml.")
    p_validate.set_defaults(func=_cli_validate)

    p_status = sub.add_parser(
        "status",
        help="Print the baseline status token for a repo root.",
    )
    p_status.add_argument("repo_root", help="Repository root directory.")
    p_status.set_defaults(func=_cli_status)

    p_init = sub.add_parser(
        "init",
        help="Create an unratified baseline from merged engine output.",
    )
    p_init.add_argument("repo_root", help="Target repository root directory.")
    p_init.add_argument(
        "--from",
        dest="from_json",
        required=True,
        help="Path to the merged DISCOVER+VERIFY engine-output JSON.",
    )
    p_init.set_defaults(func=_cli_init)

    p_ratify = sub.add_parser(
        "ratify",
        help="Perform the one-way unratified -> ratified transition.",
    )
    p_ratify.add_argument("baseline_path", help="Path to architecture-baseline.yaml.")
    p_ratify.add_argument(
        "--by",
        required=True,
        help="Operator attestation name (recorded as ratified_by).",
    )
    p_ratify.set_defaults(func=_cli_ratify)

    p_append = sub.add_parser(
        "append-rule",
        help="Atomically append an R-NNN rule (does not reopen ratification).",
    )
    p_append.add_argument("baseline_path", help="Path to architecture-baseline.yaml.")
    p_append.add_argument("--statement", required=True, help="The rule statement.")
    p_append.add_argument("--who", required=True, help="Provenance author.")
    p_append.add_argument("--trigger", required=True, help="Provenance trigger.")
    p_append.add_argument(
        "--mechanizable",
        action="store_true",
        help="Mark the rule as a baseline-verify graduation candidate.",
    )
    p_append.set_defaults(func=_cli_append_rule)

    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns the desired process exit code.

    Argparse exits the process directly on parse errors (exit code 2), which
    is the desired behaviour for unknown subcommands and missing required
    arguments.
    """
    parser = _build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
