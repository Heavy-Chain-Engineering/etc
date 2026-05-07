"""value_hypothesis.py — read, write, validate, and transition v1 hypotheses.

Implements the on-disk schema described by BR-005 and BR-006 of the
metrics-and-release-notes feature, plus the BR-011 status state machine
used by `tasks.py validate` and the `/metrics` skill.

Schema (v1):
    schema_version: int (currently 1)
    feature_id:     str
    author_role:    str  (legacy F001-F009; SME | Engineer | PM | Designer
                          | Other:<free-form>)
    spec_author_role:      str  (F010+; F006 BR-007 dual-role schema)
    architect_author_role: str  (F010+; F006 BR-007, optional)
    who:            str  (target user / cohort)
    current_cost:   str  (baseline pain in human terms)
    predicted:      mapping (metric, direction, threshold, window_days)
    how_we_know:    str  (measurement plan)
    status:         str  (pending | validated | invalidated | unmeasured)
    validation:     mapping {measured_at, measured_value, evidence}

Per F006 BR-007, at least ONE of ``author_role`` or ``spec_author_role``
must be present; ``architect_author_role`` is independently optional.
Unknown top-level fields are rejected. All three author-role variants
are sanitized at load time (cap 64 chars, strip control chars
``[\\x00-\\x1f\\x7f]``) per the F001 sanitization contract.

Status state machine (BR-011):
    pending -> validated
    pending -> invalidated
    pending -> unmeasured
All other transitions are rejected.

Public surface:
    SCHEMA_VERSION
    REQUIRED_FIELDS
    LEGAL_STATUSES
    load(path)
    dump(path, hypothesis)
    validate_schema(d)
    transition_status(d, new_status, evidence=None)

Errors:
    ValueError on malformed YAML, missing required fields, unknown
    status values, illegal transitions, or non-integer schema_version.
    Unknown future schema_version values are treated as warn-and-skip:
    `load` returns None and emits a logging.WARNING.
"""

from __future__ import annotations

import argparse
import copy
import json
import logging
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

SCHEMA_VERSION: int = 1

REQUIRED_FIELDS: tuple[str, ...] = (
    "schema_version",
    "feature_id",
    "author_role",
    "who",
    "current_cost",
    "predicted",
    "how_we_know",
    "status",
    "validation",
)

# F006 BR-007: optional author-role fields for the new dual-role schema.
# At least one of {author_role, spec_author_role} must be present;
# architect_author_role is independently optional.
_AUTHOR_ROLE_FIELDS: frozenset[str] = frozenset(
    {"author_role", "spec_author_role", "architect_author_role"}
)

# All top-level field names the validator recognises. Anything outside
# this set is rejected (Security Considerations item 6 of F006).
_KNOWN_FIELDS: frozenset[str] = frozenset(REQUIRED_FIELDS) | _AUTHOR_ROLE_FIELDS

# F001 sanitization contract: cap free-form author-role values at 64
# characters and strip every control-character codepoint matching the
# regex ``[\x00-\x1f\x7f]``. Implemented via str.translate to keep this
# module dependency-free (no new imports beyond the existing stdlib +
# yaml set).
_AUTHOR_ROLE_MAX_LEN: int = 64
_CONTROL_CHAR_TRANSLATION: dict[int, None] = {
    code: None for code in (*range(0x00, 0x20), 0x7F)
}

LEGAL_STATUSES: frozenset[str] = frozenset(
    {"pending", "validated", "invalidated", "unmeasured"}
)

# BR-011: pending is the only legal source state.
_LEGAL_TRANSITIONS: frozenset[tuple[str, str]] = frozenset(
    {
        ("pending", "validated"),
        ("pending", "invalidated"),
        ("pending", "unmeasured"),
    }
)


def load(path: Path) -> dict[str, Any] | None:
    """Read and validate a value-hypothesis YAML file.

    Args:
        path: Path to the value-hypothesis.yaml file.

    Returns:
        The parsed hypothesis dict, or None if the file declares a
        schema_version newer than this reader supports (BR-006/AC-006:
        warn-and-skip).

    Raises:
        ValueError: If the file is missing, the YAML is malformed, the
            top level is not a mapping, schema_version is not an integer,
            or a required field is missing.
    """
    if not path.exists():
        msg = f"value-hypothesis file not found: {path}"
        raise ValueError(msg)

    raw = path.read_text(encoding="utf-8")
    try:
        parsed = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        msg = f"malformed YAML in {path}: {exc}"
        raise ValueError(msg) from exc

    if not isinstance(parsed, dict):
        msg = (
            f"value-hypothesis at {path} must be a YAML mapping; "
            f"got {type(parsed).__name__}"
        )
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

    # F006 BR-007 + F001 sanitization contract. Apply at the input-handling
    # site so downstream consumers (validator, /metrics, /spec) see clean
    # values regardless of which author-role field(s) are present.
    _sanitize_author_role_fields(parsed)

    validate_schema(parsed)
    return parsed


def dump(path: Path, hypothesis: dict[str, Any]) -> None:
    """Write a value-hypothesis dict to disk in canonical YAML form.

    Args:
        path: Destination file path.
        hypothesis: Hypothesis dict. Not validated here; callers that
            require schema enforcement should call validate_schema first.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(hypothesis, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )


def validate_schema(d: dict[str, Any]) -> None:
    """Enforce BR-005 (required fields) and F006 BR-007 (dual author-role).

    Also enforces that ``predicted`` is a mapping containing a positive
    integer ``window_days``. The /metrics skill reads
    ``predicted.window_days`` unconditionally to drive the
    ``pending → unmeasured`` auto-transition (AC-014); a hypothesis that
    passes this validator must therefore guarantee the field is usable.

    F006 BR-007: ``author_role`` is no longer strictly required. The rule
    is now "at least one of ``{author_role, spec_author_role}`` must be
    present"; ``architect_author_role`` is independently optional. Any
    top-level field outside the documented set is rejected (Security
    Considerations item 6 of F006).

    Args:
        d: Hypothesis dict to validate.

    Raises:
        ValueError: If `d` is not a mapping, a required field is missing,
            neither ``author_role`` nor ``spec_author_role`` is present,
            an unknown top-level field is present, ``status`` is not one
            of the legal values, ``predicted`` is not a mapping, or
            ``predicted.window_days`` is missing, of the wrong type, or
            non-positive.
    """
    if not isinstance(d, dict):  # pyright: ignore[reportUnnecessaryIsInstance]
        msg = f"value-hypothesis must be a mapping; got {type(d).__name__}"  # pyright: ignore[reportUnreachable]
        raise ValueError(msg)  # pyright: ignore[reportUnreachable]

    # author_role is in REQUIRED_FIELDS for backward compat with the
    # public tuple, but per F006 BR-007 it satisfies the missing-field
    # check via either author_role OR spec_author_role.
    missing = [
        field
        for field in REQUIRED_FIELDS
        if field != "author_role" and field not in d
    ]
    if "author_role" not in d and "spec_author_role" not in d:
        missing.append("author_role")
    if missing:
        msg = f"value-hypothesis missing required field(s): {', '.join(missing)}"
        raise ValueError(msg)

    unknown = sorted(set(d.keys()) - _KNOWN_FIELDS)
    if unknown:
        msg = (
            f"value-hypothesis has unknown top-level field(s): "
            f"{', '.join(unknown)}"
        )
        raise ValueError(msg)

    status = d["status"]
    if status not in LEGAL_STATUSES:
        msg = (
            f"value-hypothesis status {status!r} is not legal; "
            f"expected one of: {sorted(LEGAL_STATUSES)}"
        )
        raise ValueError(msg)

    _validate_predicted_window_days(d["predicted"])


def _sanitize_author_role_fields(d: dict[str, Any]) -> None:
    """Sanitize every author-role variant present in ``d`` in place.

    F001 contract: cap each value at ``_AUTHOR_ROLE_MAX_LEN`` characters
    (truncate excess) and strip every control-character codepoint
    (matches regex ``[\\x00-\\x1f\\x7f]``). Applied at the input-handling
    site by ``load`` so downstream consumers see clean values regardless
    of which author-role field(s) the file uses (legacy ``author_role``
    or F010+ ``spec_author_role`` / ``architect_author_role``).

    Non-string values are left untouched here; the validator surfaces
    type problems separately. Missing fields are skipped silently —
    presence-of-at-least-one is enforced by ``validate_schema``.
    """
    for field in _AUTHOR_ROLE_FIELDS:
        value = d.get(field)
        if isinstance(value, str):
            d[field] = value.translate(_CONTROL_CHAR_TRANSLATION)[
                :_AUTHOR_ROLE_MAX_LEN
            ]


def _validate_predicted_window_days(predicted: Any) -> None:
    """Enforce that ``predicted.window_days`` is a positive int.

    Split out so the main ``validate_schema`` body stays linear and
    readable. Booleans are rejected explicitly because ``bool`` is a
    subclass of ``int`` in Python and ``True``/``False`` would otherwise
    slip through an ``isinstance(..., int)`` check.
    """
    if not isinstance(predicted, dict):
        msg = (
            f"value-hypothesis predicted must be a mapping; "
            f"got {type(predicted).__name__}"
        )
        raise ValueError(msg)

    if "window_days" not in predicted:
        msg = "value-hypothesis missing required field: predicted.window_days"
        raise ValueError(msg)

    window_days = predicted["window_days"]
    if isinstance(window_days, bool) or not isinstance(window_days, int):
        msg = (
            f"value-hypothesis predicted.window_days must be an integer; "
            f"got {window_days!r} ({type(window_days).__name__})"
        )
        raise ValueError(msg)

    if window_days <= 0:
        msg = (
            f"value-hypothesis predicted.window_days must be a positive "
            f"integer; got {window_days}"
        )
        raise ValueError(msg)


def transition_status(
    d: dict[str, Any],
    new_status: str,
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Apply a status transition under the BR-011 state machine.

    Returns a new dict; the input is not mutated.

    Args:
        d: Hypothesis dict in its current state.
        new_status: Target status value.
        evidence: Optional replacement for the `validation` block,
            attached to the returned dict on a legal transition.

    Returns:
        A new hypothesis dict with `status` set to `new_status` and, if
        provided, `validation` replaced by `evidence`.

    Raises:
        ValueError: If `new_status` is not a legal status value or the
            transition from the current status is not permitted.
    """
    if new_status not in LEGAL_STATUSES:
        msg = (
            f"unknown status {new_status!r}; "
            f"expected one of: {sorted(LEGAL_STATUSES)}"
        )
        raise ValueError(msg)

    current = d.get("status")
    if (current, new_status) not in _LEGAL_TRANSITIONS:
        msg = (
            f"illegal status transition {current!r} -> {new_status!r}; "
            f"only pending -> {{validated, invalidated, unmeasured}} is permitted"
        )
        raise ValueError(msg)

    updated = copy.deepcopy(d)
    updated["status"] = new_status
    if evidence is not None:
        updated["validation"] = copy.deepcopy(evidence)
    return updated


# ── Command-line interface ──────────────────────────────────────────────
#
# Skills (/spec, /metrics) need to invoke this module from arbitrary
# working directories without making `scripts/` an importable package.
# The CLI is the runtime contract used by those callers; the in-process
# helpers above remain the contract used by tests and by `tasks.py`.


def _atomic_dump(path: Path, hypothesis: dict[str, Any]) -> None:
    """Atomic on-disk write used by the ``transition`` subcommand.

    Writes to a temp file in the same directory, fsyncs, then renames
    over the target. On any failure the temp file is unlinked so callers
    never see a partially-written value-hypothesis. The original
    ``dump`` is intentionally left non-atomic to preserve byte-for-byte
    behaviour for existing callers in scripts/tasks.py and the metrics
    skill that relies on its current output.
    """
    body = yaml.safe_dump(hypothesis, sort_keys=False, default_flow_style=False)

    target_dir = path.parent
    target_dir.mkdir(parents=True, exist_ok=True)

    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(target_dir)
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        tmp_path.replace(path)
    except OSError:
        try:
            tmp_path.unlink()
        except OSError:
            pass
        raise


def _cli_validate(args: argparse.Namespace) -> int:
    """``validate <yaml_path>`` — load + validate_schema.

    Returns 0 on success, 1 on any ValueError raised by ``load``. The
    error message is written to stderr verbatim so callers (skills) can
    surface the missing field name.
    """
    try:
        load(Path(args.yaml_path))
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


def _cli_load(args: argparse.Namespace) -> int:
    """``load <yaml_path>`` — print parsed YAML as JSON.

    Output uses ``json.dumps(d, indent=2, sort_keys=True)`` so callers
    can rely on a stable key order regardless of YAML insertion order.
    """
    try:
        parsed = load(Path(args.yaml_path))
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if parsed is None:
        # Future schema_version: load() already logged a warning. Emit a
        # diagnostic on stderr and exit non-zero so callers do not treat
        # an empty stdout as a valid hypothesis.
        print(
            f"{args.yaml_path}: unsupported future schema_version; refusing to print",
            file=sys.stderr,
        )
        return 1

    print(json.dumps(parsed, indent=2, sort_keys=True))
    return 0


def _cli_transition(args: argparse.Namespace) -> int:
    """``transition <yaml_path> <new_status> [--measured-value V] [--evidence E]``.

    Loads, applies the BR-011 transition, and atomically rewrites the
    file. ``--measured-value`` is parsed as int when possible, else
    float, matching tasks.py's ``--measured`` behaviour. ``--evidence``
    is recorded verbatim — canonicalisation against a project root is
    the caller's responsibility (see tasks.py validate for that flow).
    """
    yaml_path = Path(args.yaml_path)

    try:
        hypothesis = load(yaml_path)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if hypothesis is None:
        print(
            f"{yaml_path}: unsupported future schema_version; refusing to transition",
            file=sys.stderr,
        )
        return 1

    evidence_block: dict[str, Any] | None = None
    if args.measured_value is not None or args.evidence is not None:
        evidence_block = dict(hypothesis.get("validation") or {})
        if args.measured_value is not None:
            try:
                evidence_block["measured_value"] = _parse_measured_cli(
                    args.measured_value
                )
            except ValueError as exc:
                print(str(exc), file=sys.stderr)
                return 1
        if args.evidence is not None:
            evidence_block["evidence"] = args.evidence

    try:
        updated = transition_status(hypothesis, args.new_status, evidence_block)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    try:
        _atomic_dump(yaml_path, updated)
    except OSError as exc:
        print(f"failed to write {yaml_path}: {exc}", file=sys.stderr)
        return 1

    return 0


def _parse_measured_cli(raw: str) -> int | float:
    """Numeric parse of ``--measured-value``; raises ValueError otherwise.

    Tries int first, then float. Hex/octal/binary literals, ``inf``,
    and ``nan`` are rejected so the on-disk representation stays
    boring — same contract as tasks.py's ``--measured`` parser.
    """
    text = raw.strip()
    lowered = text.lower().lstrip("+-")
    if not text or lowered in {"inf", "infinity", "nan"} or lowered.startswith(
        ("0x", "0o", "0b")
    ):
        msg = f"--measured-value {raw!r} is not a finite numeric (int or float)"
        raise ValueError(msg)

    try:
        return int(text)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError as exc:
        msg = f"--measured-value {raw!r} is not numeric (int or float)"
        raise ValueError(msg) from exc


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="value_hypothesis.py",
        description=(
            "Read, validate, and transition value-hypothesis.yaml files. "
            "Used by /spec and /metrics at runtime."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_validate = sub.add_parser(
        "validate", help="Load a YAML file and run validate_schema."
    )
    p_validate.add_argument("yaml_path", help="Path to value-hypothesis.yaml.")
    p_validate.set_defaults(func=_cli_validate)

    p_load = sub.add_parser(
        "load", help="Load a YAML file and print it as sorted-key JSON."
    )
    p_load.add_argument("yaml_path", help="Path to value-hypothesis.yaml.")
    p_load.set_defaults(func=_cli_load)

    p_transition = sub.add_parser(
        "transition",
        help=(
            "Apply a BR-011 status transition and atomically rewrite the "
            "YAML file."
        ),
    )
    p_transition.add_argument("yaml_path", help="Path to value-hypothesis.yaml.")
    p_transition.add_argument(
        "new_status",
        choices=sorted(LEGAL_STATUSES),
        help="Target status (must be a legal value).",
    )
    p_transition.add_argument(
        "--measured-value",
        default=None,
        help="Numeric measurement to record in the validation block.",
    )
    p_transition.add_argument(
        "--evidence",
        default=None,
        help="Evidence URL or path to record in the validation block.",
    )
    p_transition.set_defaults(func=_cli_transition)

    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns the desired process exit code.

    Argparse exits the process directly on parse errors (exit code 2),
    which is the desired behaviour for unknown subcommands and missing
    required arguments. Application-level errors return 1.
    """
    parser = _build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
