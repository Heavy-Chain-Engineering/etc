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

Public surface (the contract later waves — init / ratify / append-rule /
render-doc / sync-seams — compose):
    SCHEMA_VERSION, REQUIRED_FIELDS
    LEGAL_STATUSES, LEGAL_CLASSIFICATIONS, LEGAL_CONFIDENCE_SCORES
    NAME_MAX_LEN, FREEFORM_MAX_LEN, BASELINE_RELATIVE_PATH
    load(path) -> dict | None
    validate_schema(d) -> None
    status_token(repo_root) -> str
    sanitize_freeform(value, *, max_len) -> str
    atomic_dump(path, data) -> None

CLI exit codes (house style per GA-A06): 0 = success, 1 = could-not-evaluate
(usage/IO/missing/malformed-for-status), 2 = domain failure (schema
violation). ``status`` always exits 0 when evaluable and emits one token;
callers branch on the TOKEN, never the code.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import tempfile
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
_OPTIONAL_FIELDS: frozenset[str] = frozenset(
    {"ratified_by", "ratified_at", "exemplars", "do_not_copy"}
)

_KNOWN_FIELDS: frozenset[str] = frozenset(REQUIRED_FIELDS) | _OPTIONAL_FIELDS

# Closed enums (design.md Data Model). Stored values outside these sets are
# schema violations, surfaced as `malformed` by status_token — never coerced.
LEGAL_STATUSES: frozenset[str] = frozenset({"unratified", "ratified"})
LEGAL_CLASSIFICATIONS: frozenset[str] = frozenset(
    {"VERIFIED", "STALE", "ASPIRATIONAL", "CONTRADICTED"}
)
LEGAL_CONFIDENCE_SCORES: frozenset[str] = frozenset({"low", "medium", "high"})

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
