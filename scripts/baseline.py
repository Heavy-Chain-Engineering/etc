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

# The human twin (ARCHITECTURE.md) is rendered at the repo root — two parents
# up from the baseline (<repo>/.etc_sdlc/architecture-baseline.yaml). Tier-0
# placement so agents and humans find it without spelunking. ADR-001.
ARCHITECTURE_DOC_NAME: str = "ARCHITECTURE.md"

# The provenance header stamped at the top of every rendered ARCHITECTURE.md.
# Pinned verbatim (AC-1) so drift between the twins is structurally discouraged:
# a reader who sees this line knows the file is generated, not hand-authored.
GENERATED_DOC_HEADER: str = (
    "generated from .etc_sdlc/architecture-baseline.yaml — edit via /init-project --phase=baseline"
)

# The render skeleton: the template owns section ORDER + fixed prose; the
# renderer substitutes the {{...}} placeholders. baseline.py lives at
# <repo>/scripts/baseline.py, so the template sits two parents up. When the
# template is unavailable (e.g. an install dir that did not ship it), the
# renderer falls back to a self-contained built-in skeleton — the doc must
# never depend on the install dir being present at render time.
ARCHITECTURE_TEMPLATE_PATH: Path = (
    Path(__file__).resolve().parent.parent
    / "skills"
    / "init-project"
    / "templates"
    / "ARCHITECTURE.md.template"
)

# The workspace seam map (workspace mode only — the single editable source).
# Per-repo baseline `seams:` blocks are read-only mirrors regenerated from it.
SEAM_MAP_RELATIVE_PATH: Path = Path(".etc_workspace") / "seam-map.yaml"

# Closed enum for a workspace seam's `kind` (design Data Model artifact 2 /
# ADR-005). A seam-map with a kind outside this set is malformed → sync-seams
# exits 1, never silently mirrors an uninterpretable contract.
LEGAL_SEAM_KINDS: frozenset[str] = frozenset(
    {"url-routing", "auth-session", "data-schema", "embed-loader"}
)

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
    the attestation fields are set (name sanitized, UTC ISO-8601 timestamp),
    the file is atomically rewritten, and the human twin (``ARCHITECTURE.md``)
    is rendered from the now-ratified baseline — the design.md contract "ratify
    performs the one-way transition and the human doc is rendered". Re-ratifying
    therefore regenerates the doc.

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
    _render_doc_from_baseline(path, baseline)


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


# ── render-doc: the ARCHITECTURE.md human twin ──────────────────────────
#
# The renderer projects a ratified (or unratified) baseline into the tier-0
# human doc at the repo root. Output is DETERMINISTIC — every section walks the
# stored list order (which the CLI itself wrote), and empty sections render a
# stable placeholder — so re-renders diff cleanly and re-ratification is a no-op
# when nothing changed (design.md: "keep renderer output deterministic"). The
# machine file is the single source of truth; this doc is regenerated, never
# hand-edited (ADR-001). The template at
# skills/init-project/templates/ARCHITECTURE.md.template is the documented
# skeleton; the renderer owns content so the doc is self-contained even when the
# install dir is unavailable at render time.

_EMPTY_SECTION_PLACEHOLDER: str = "_None recorded._"

# Sentinels bounding the template's maintainer-guidance comment. The renderer
# removes the whole span (delimiters included) so contract prose — and the
# literal double-brace it mentions — never leaks into the rendered doc.
_TEMPLATE_STRIP_START: str = "<!-- RENDER:STRIP-START"
_TEMPLATE_STRIP_END: str = "RENDER:STRIP-END -->"


def render_doc(baseline_path: Path) -> Path:
    """Render the human twin ``ARCHITECTURE.md`` from a baseline file.

    Reads and validates the baseline at ``baseline_path``, projects its
    exemplars / do-not-copy / rules / boundary map / confidence into a
    deterministic Markdown document, and atomically writes it to
    ``<repo_root>/ARCHITECTURE.md`` (two parents up from the baseline, i.e. the
    repo root). The document carries the ``GENERATED_DOC_HEADER`` provenance line
    so its generated nature is structurally obvious.

    Args:
        baseline_path: Path to ``.etc_sdlc/architecture-baseline.yaml``.

    Returns:
        The path the ``ARCHITECTURE.md`` was written to.

    Raises:
        ValueError: If the baseline is missing/malformed or an unsupported
            future schema_version (cannot render what we cannot interpret).
    """
    baseline = _load_existing(baseline_path)
    doc_path = _architecture_doc_path(baseline_path)
    _render_doc_from_baseline(baseline_path, baseline)
    return doc_path


def _architecture_doc_path(baseline_path: Path) -> Path:
    """Resolve the repo-root ARCHITECTURE.md path from the baseline file path.

    The baseline lives at ``<repo>/.etc_sdlc/architecture-baseline.yaml``; the
    human twin sits at ``<repo>/ARCHITECTURE.md`` — two parents up.
    """
    repo_root = baseline_path.parent.parent
    return repo_root / ARCHITECTURE_DOC_NAME


def _render_doc_from_baseline(baseline_path: Path, baseline: dict[str, Any]) -> None:
    """Render and atomically write ARCHITECTURE.md for an in-hand baseline.

    Shared by ``ratify`` (post-transition) and ``render_doc`` (standalone) so
    the rendering contract has exactly one implementation.
    """
    doc_path = _architecture_doc_path(baseline_path)
    body = _compose_architecture_md(baseline)
    _atomic_write_text(doc_path, body)


def _compose_architecture_md(baseline: dict[str, Any]) -> str:
    """Assemble the full ARCHITECTURE.md body from a baseline dict (pure).

    Fills the on-disk template skeleton (which owns section ORDER + fixed prose)
    with rendered fragments. Falls back to a self-contained built-in skeleton
    when the template is unavailable so the doc never depends on the install dir
    being present at render time.
    """
    fragments = _section_fragments(baseline)
    template = _load_template_text()
    if template is None:
        return _builtin_skeleton(fragments)
    return _fill_template(template, fragments)


def _load_template_text() -> str | None:
    """Read the render-skeleton template; return None if it is unavailable."""
    try:
        return ARCHITECTURE_TEMPLATE_PATH.read_text(encoding="utf-8")
    except OSError:
        logger.warning(
            "ARCHITECTURE.md template not found at %s; using built-in skeleton",
            ARCHITECTURE_TEMPLATE_PATH,
        )
        return None


def _section_fragments(baseline: dict[str, Any]) -> dict[str, str]:
    """Build the placeholder -> rendered-fragment substitution map (pure)."""
    confidence = baseline.get("confidence") or {}
    return {
        "STATUS": str(baseline.get("status", "unknown")),
        "RATIFIED_BY": str(baseline.get("ratified_by") or "(unratified)"),
        "RATIFIED_AT": str(baseline.get("ratified_at") or "(unratified)"),
        "CONFIDENCE_SCORE": _confidence_score(confidence),
        "EXEMPLARS": _render_exemplars_body(baseline.get("exemplars") or []),
        "DO_NOT_COPY": _render_do_not_copy_body(baseline.get("do_not_copy") or []),
        "RULES": _render_rules_body(baseline.get("rules") or []),
        "BOUNDARY_MAP": _render_boundary_map_body(baseline.get("seams") or []),
        "CONFIDENCE_INPUTS": _render_confidence_inputs_body(confidence),
    }


def _fill_template(template: str, fragments: dict[str, str]) -> str:
    """Substitute every ``{{KEY}}`` in the template with its fragment.

    First removes the maintainer-guidance block (everything between the
    ``RENDER:STRIP-START`` / ``RENDER:STRIP-END`` sentinels) so no contract
    prose — or the literal ``{{...}}`` it mentions — leaks into the rendered
    doc. The verbatim generated-from header comment lives OUTSIDE the sentinels
    and is preserved.
    """
    rendered = _strip_guidance_block(template)
    for key, value in fragments.items():
        rendered = rendered.replace("{{" + key + "}}", value)
    return rendered


def _strip_guidance_block(template: str) -> str:
    """Remove the sentinel-delimited maintainer-guidance comment from a template.

    Deterministic: drops the entire ``<!-- RENDER:STRIP-START ... RENDER:STRIP-END -->``
    comment (delimiters included) and the blank line the removal would leave
    behind. The verbatim generated-from header comment is a separate comment
    outside the sentinels and is preserved.
    """
    start = template.find(_TEMPLATE_STRIP_START)
    end = template.find(_TEMPLATE_STRIP_END)
    if start == -1 or end == -1:
        return template
    after = template[end + len(_TEMPLATE_STRIP_END) :]
    return template[:start] + after.lstrip("\n")


def _builtin_skeleton(fragments: dict[str, str]) -> str:
    """Self-contained fallback skeleton (template-unavailable path).

    Mirrors the template's section order and the verbatim generated-from header
    so a render without the template still produces a complete, correctly-headed
    document.
    """
    sections = [
        f"<!-- {GENERATED_DOC_HEADER} -->\n# Architecture Baseline\n\n"
        f"**Status:** {fragments['STATUS']} — ratified by {fragments['RATIFIED_BY']} "
        f"on {fragments['RATIFIED_AT']}\n**Confidence:** {fragments['CONFIDENCE_SCORE']}",
        f"## Exemplars\n\n{fragments['EXEMPLARS']}",
        f"## Do Not Copy\n\n{fragments['DO_NOT_COPY']}",
        f"## Rules\n\n{fragments['RULES']}",
        f"## Boundary Map\n\n{fragments['BOUNDARY_MAP']}",
        f"## Confidence\n\nScore: **{fragments['CONFIDENCE_SCORE']}**.\n\n"
        f"{fragments['CONFIDENCE_INPUTS']}",
    ]
    return "\n\n".join(sections) + "\n"


def _render_exemplars_body(exemplars: list[Any]) -> str:
    """Golden registry body: name, paths, applies-to, blessed-by — stored order."""
    if not exemplars:
        return _EMPTY_SECTION_PLACEHOLDER
    lines: list[str] = []
    for exemplar in exemplars:
        name = exemplar.get("name", "(unnamed)")
        paths = ", ".join(str(p) for p in exemplar.get("paths") or [])
        applies_to = exemplar.get("applies_to", "")
        blessed_by = exemplar.get("blessed_by") or "(unrecorded)"
        lines.append(f"- **{name}** (`{paths}`) — {applies_to} _[blessed by {blessed_by}]_")
    return "\n".join(lines)


def _render_do_not_copy_body(entries: list[Any]) -> str:
    """Anti-pattern registry body: path + reason, stored order."""
    if not entries:
        return _EMPTY_SECTION_PLACEHOLDER
    lines: list[str] = []
    for entry in entries:
        path = entry.get("path", "(unspecified)")
        reason = entry.get("reason", "")
        lines.append(f"- `{path}` — {reason}")
    return "\n".join(lines)


def _render_rules_body(rules: list[Any]) -> str:
    """Normative rules body: id + statement + enforcement, stored order."""
    if not rules:
        return _EMPTY_SECTION_PLACEHOLDER
    lines: list[str] = []
    for rule in rules:
        rule_id = rule.get("id", "R-???")
        statement = rule.get("statement", "")
        enforced_by = rule.get("enforced_by", "human-judgment")
        lines.append(f"- **{rule_id}** — {statement} _[enforced by {enforced_by}]_")
    return "\n".join(lines)


def _render_boundary_map_body(seams: list[Any]) -> str:
    """Boundary map body from the per-repo seam block.

    Tolerant of BOTH seam shapes a baseline's ``seams:`` block may carry: the
    ``init`` shape (``signal`` / ``external_owner`` / ``resolution``, design
    Data Model artifact 1) and the ``sync-seams`` workspace-mirror shape
    (``kind`` / ``owner_repo`` / ``contract`` / ``consumer_repos``, artifact 2).
    Each row surfaces an id, a description, and an owner regardless of writer.
    """
    if not seams:
        return _EMPTY_SECTION_PLACEHOLDER
    return "\n".join(_render_seam_row(seam) for seam in seams)


def _render_seam_row(seam: dict[str, Any]) -> str:
    """Render one boundary-map row, normalizing across both seam shapes."""
    seam_id = seam.get("id", "SM-???")
    description = seam.get("signal") or seam.get("contract") or seam.get("kind") or ""
    owner = seam.get("external_owner") or seam.get("owner_repo") or "(boundary-unknown)"
    qualifier = seam.get("resolution") or seam.get("kind") or ""
    return f"- **{seam_id}** — {description} → owner: {owner} _[{qualifier}]_"


def _render_confidence_inputs_body(confidence: dict[str, Any]) -> str:
    """Confidence inputs body: the documented inputs (auditable, never bare)."""
    inputs = confidence.get("inputs") if isinstance(confidence, dict) else None
    if not isinstance(inputs, dict) or not inputs:
        return _EMPTY_SECTION_PLACEHOLDER
    lines = ["Inputs:", ""]
    for key in sorted(inputs):
        lines.append(f"- {key}: {inputs[key]}")
    return "\n".join(lines)


def _confidence_score(confidence: Any) -> str:
    """Extract the confidence score token, defaulting to ``unknown``."""
    if isinstance(confidence, dict):
        return str(confidence.get("score", "unknown"))
    return "unknown"


def _atomic_write_text(path: Path, body: str) -> None:
    """Atomically write ``body`` to ``path`` (tmp + fsync + os.replace).

    The text-mode twin of ``atomic_dump`` — the rendered doc is plain Markdown,
    not YAML, so it needs its own write path with the same atomicity guarantees
    (no partial doc ever observed, no temp debris on success).
    """
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


# ── sync-seams: read-only per-repo seam mirrors ─────────────────────────
#
# Workspace mode (ADR-005) keeps ONE editable seam map at
# <workspace>/.etc_workspace/seam-map.yaml and regenerates a read-only `seams:`
# mirror inside each repo's baseline, filtered to the seams that repo
# participates in (as owner or consumer). A repo cloned alone therefore keeps
# its full seam context — the covr solo-clone blindness fixed. Hand-edits to a
# mirror are overwritten on the next sync; each mirror record carries a note
# saying so. There is no separate validate-seam path: sync-seams validates the
# seam-map itself (exit 1 on malformed) so a bad map never silently mirrors.

# The marker stamped on every mirror record: the mirror is generated, so a
# human edit will not survive the next sync. Mirrored alongside the seam data
# (not a file-level comment) because the baseline is YAML the CLI owns — the
# note rides with the record that a reader is looking at.
_MIRROR_OVERWRITE_NOTE: str = (
    "read-only mirror regenerated by `baseline.py sync-seams`; "
    "hand-edits will be overwritten — edit the workspace seam-map instead"
)


def sync_seams(workspace_root: Path) -> list[Path]:
    """Regenerate each repo's read-only seam mirror from the workspace seam-map.

    Loads and validates ``<workspace>/.etc_workspace/seam-map.yaml`` (malformed
    → ``ValueError``, never a silent partial sync), then for every repo named in
    the map that has an existing baseline on disk, overwrites that baseline's
    ``seams:`` block with the seams touching that repo (owner or consumer),
    each carrying the hand-edits-overwritten note. Repos without a baseline are
    skipped (forward-only; sync never auto-creates a baseline).

    Args:
        workspace_root: The workspace root containing ``.etc_workspace/``.

    Returns:
        The list of baseline paths whose mirrors were rewritten.

    Raises:
        ValueError: If the seam-map is missing, unparseable, or violates the
            seam-map schema (e.g. an out-of-enum ``kind``).
    """
    seam_map = _load_seam_map(workspace_root)
    seams = seam_map.get("seams") or []

    rewritten: list[Path] = []
    for repo in seam_map.get("repos") or []:
        repo_name = repo.get("name")
        baseline_path = workspace_root / str(repo_name) / BASELINE_RELATIVE_PATH
        if not baseline_path.exists():
            continue
        _rewrite_repo_mirror(baseline_path, repo_name, seams)
        rewritten.append(baseline_path)
    return rewritten


def _load_seam_map(workspace_root: Path) -> dict[str, Any]:
    """Read and validate the workspace seam-map; raise on any problem."""
    seam_path = workspace_root / SEAM_MAP_RELATIVE_PATH
    if not seam_path.exists():
        msg = f"workspace seam-map not found: {seam_path}"
        raise ValueError(msg)

    try:
        parsed = yaml.safe_load(seam_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        msg = f"malformed YAML in seam-map {seam_path}: {exc}"
        raise ValueError(msg) from exc

    _validate_seam_map(parsed, seam_path)
    # _validate_seam_map raises unless parsed is a mapping; the isinstance here
    # narrows Any -> dict for the type checker (mirrors load()'s inline guard).
    if not isinstance(parsed, dict):  # pragma: no cover - guarded above
        msg = f"seam-map at {seam_path} must be a YAML mapping"
        raise ValueError(msg)
    return parsed


def _validate_seam_map(parsed: object, seam_path: Path) -> None:
    """Enforce the seam-map schema (design Data Model artifact 2 / ADR-005)."""
    if not isinstance(parsed, dict):
        msg = f"seam-map at {seam_path} must be a YAML mapping; got {type(parsed).__name__}"
        raise ValueError(msg)
    if not isinstance(parsed.get("repos"), list):
        msg = f"seam-map at {seam_path} must carry a 'repos' list"
        raise ValueError(msg)
    seams = parsed.get("seams")
    if not isinstance(seams, list):
        msg = f"seam-map at {seam_path} must carry a 'seams' list"
        raise ValueError(msg)
    for seam in seams:
        _validate_seam_record(seam, seam_path)


def _validate_seam_record(seam: object, seam_path: Path) -> None:
    """Enforce a single seam's shape: mapping with an in-enum ``kind``."""
    if not isinstance(seam, dict):
        msg = f"seam-map at {seam_path} has a non-mapping seam: {seam!r}"
        raise ValueError(msg)
    kind = seam.get("kind")
    if kind not in LEGAL_SEAM_KINDS:
        seam_id = seam.get("id", "<unknown>")
        msg = (
            f"seam-map seam {seam_id} kind {kind!r} is not legal; "
            f"expected one of: {sorted(LEGAL_SEAM_KINDS)}"
        )
        raise ValueError(msg)


def _rewrite_repo_mirror(baseline_path: Path, repo_name: object, seams: list[Any]) -> None:
    """Overwrite one baseline's ``seams:`` block with this repo's filtered mirror."""
    baseline = _load_existing(baseline_path)
    baseline["seams"] = [
        _mirror_record(seam) for seam in seams if _seam_touches_repo(seam, repo_name)
    ]
    atomic_dump(baseline_path, baseline)


def _seam_touches_repo(seam: dict[str, Any], repo_name: object) -> bool:
    """True if ``repo_name`` is the seam's owner or one of its consumers."""
    if seam.get("owner_repo") == repo_name:
        return True
    consumers = seam.get("consumer_repos") or []
    return repo_name in consumers


def _mirror_record(seam: dict[str, Any]) -> dict[str, Any]:
    """Project a workspace seam into a read-only per-repo mirror record.

    Preserves the load-bearing fields a solo-cloned repo needs (kind, owner,
    consumers, contract, evidence) plus the overwrite note. Deterministic field
    order so re-syncs diff cleanly.
    """
    return {
        "id": seam.get("id"),
        "kind": seam.get("kind"),
        "owner_repo": seam.get("owner_repo"),
        "consumer_repos": list(seam.get("consumer_repos") or []),
        "contract": seam.get("contract"),
        "evidence": seam.get("evidence"),
        "_mirror_note": _MIRROR_OVERWRITE_NOTE,
    }


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


def _cli_render_doc(args: argparse.Namespace) -> int:
    """``render-doc <baseline_path>`` — print the ARCHITECTURE.md path.

    Exit 0 with the written doc path on stdout; 1 when the baseline is missing
    or malformed (could-not-evaluate). Re-rendering an already-rendered doc is
    a deterministic no-op at the byte level.
    """
    path = Path(args.baseline_path)
    if not path.exists():
        print(f"architecture-baseline file not found: {path}", file=sys.stderr)
        return 1
    try:
        doc_path = render_doc(path)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(str(doc_path))
    return 0


def _cli_sync_seams(args: argparse.Namespace) -> int:
    """``sync-seams <workspace_root>`` — regenerate read-only per-repo mirrors.

    Exit 0 with one rewritten baseline path per line on stdout; 1 when the
    seam-map is missing or malformed (could-not-evaluate — never a silent
    partial sync).
    """
    try:
        rewritten = sync_seams(Path(args.workspace_root))
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    for path in rewritten:
        print(str(path))
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

    p_render = sub.add_parser(
        "render-doc",
        help="Re-render the human twin ARCHITECTURE.md from the machine baseline.",
    )
    p_render.add_argument("baseline_path", help="Path to architecture-baseline.yaml.")
    p_render.set_defaults(func=_cli_render_doc)

    p_sync = sub.add_parser(
        "sync-seams",
        help="Regenerate each repo's read-only seams mirror from the workspace seam-map.",
    )
    p_sync.add_argument(
        "workspace_root",
        help="Workspace root directory (contains .etc_workspace).",
    )
    p_sync.set_defaults(func=_cli_sync_seams)

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
