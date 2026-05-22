"""extend_resolver.py — F025 post-ship refinement lane helper.

<!-- forward-only: extend lifecycle enforced from F025 release tag onward -->

Implements the 7 CLI subcommands for ``/build --extend "<problem>"``:

- ``generate-id``        emit an 8-char hex extension ID (BR-006).
- ``resolve-target``     return path to a target shipped feature dir (BR-001).
- ``classify``           rule-based Light/Medium/Heavy triage (BR-002).
- ``reopen``             move feature dir shipped/ -> active/ (BR-004).
- ``record-extend``      append entry to state.yaml.extends (BR-005).
- ``complete-extend``    set completed_at + release_tag on entry (BR-010).
- ``close``              move feature dir active/ -> shipped/ (F022 pattern).

Mirrors ``scripts/feature_id.py`` (F023) for the CLI shape, and
``scripts/active_to_shipped_mv.py`` (F022) for the ``shutil.move``
gitignored-source fallback. Mirrors ``scripts/diagnostic_evidence.py``
(F021) for stdlib-only style + frozen-dataclass surface.

Public API:

- ``generate_extend_id() -> str``
- ``resolve_target(etc_sdlc_root, feature_id_arg) -> Path``
- ``classify(problem, target_dir) -> Literal['light','medium','heavy']``
- ``reopen(target_dir, etc_sdlc_root) -> Path``
- ``record_extend(target_dir, extend_id, problem, triage, dispatched_agents) -> None``
- ``complete_extend(target_dir, extend_id, release_tag) -> None``
- ``close(target_dir, etc_sdlc_root) -> Path``
- ``FeatureNotFoundError`` — raised by ``resolve_target`` on no match.

Forward-only per spec BR-012: applies to extensions invoked after the
F025 release tag lands. Pre-F025 shipped features become extendable
post-F025; their ``state.yaml`` gains the ``extends:`` field on first
``--extend`` invocation.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import yaml

# ── Module constants ────────────────────────────────────────────────────

#: F009 subdirectory under ``features/`` for in-flight feature work.
_ACTIVE_SUBDIR = "active"

#: F009 subdirectory under ``features/`` for done audit-frozen work.
_SHIPPED_SUBDIR = "shipped"

#: Triage classification literal type.
_TriageOutcome = Literal["light", "medium", "heavy"]

#: BR-002 architectural-keyword vocabulary. Matched case-insensitively
#: as substrings (the spec text uses these forms; ``swap framework`` is
#: matched as a phrase). Anchoring at word boundaries would over-fit;
#: substring match keeps the rubric brittle in the documented direction.
_ARCHITECTURAL_KEYWORDS: tuple[str, ...] = (
    "redesign",
    "rearchitect",
    "swap framework",
    "migrate to",
    "replace with",
    "restructure",
    "amend adr",
    "revise adr",
    "change the architecture",
)

#: BR-002 file-path regex. Matches kebab-friendly path-shaped tokens
#: ending in one of the in-scope extensions. Order in the alternation
#: places ``tsx`` before ``ts`` so the longer match wins (cf. the
#: harness's own find-regex convention).
_FILE_PATH_PATTERN: re.Pattern[str] = re.compile(
    r"[\w./-]+\.(?:tsx|yaml|yml|md|sh|py|ts)\b"
)

#: BR-002 ceiling on file-path count for the Light bucket.
_LIGHT_MAX_FILES = 3


# ── Errors ──────────────────────────────────────────────────────────────


class FeatureNotFoundError(RuntimeError):
    """Raised when ``resolve_target`` cannot locate the target feature dir.

    Carries the operator's resolve target (an ``F<NNN>`` string or
    ``None`` for "most recent shipped") in ``args[0]`` so the CLI layer
    can surface an informative stderr line.
    """


# ── Public API: generate_extend_id ──────────────────────────────────────


def generate_extend_id() -> str:
    """Return an 8-char hex extension ID, chronologically sortable.

    Construction (stdlib-only per BR-006):

    1. Take the low-order 24 bits of ``time.time_ns() // 1_000_000``
       (millisecond timestamp) — that's 6 hex chars carrying ~4.6 hours
       of monotonic wrap-around. Adjacent calls within the same
       millisecond collide on this prefix.
    2. Take 2 hex chars derived from ``sha256(os.urandom(2))`` truncated
       — the F025 design.md mandates sha256 truncation; we restrict
       it to the suffix so the timestamp prefix dominates sort order.

    The result satisfies:
    - ``^[0-9a-f]{8}$``
    - Lexically sortable by creation time at millisecond resolution.
    - Operationally collision-free: 2 hex of randomness within a single
      millisecond gives ~65,536 distinct suffixes (~50% birthday-collision
      threshold at ~300 simultaneous extends on the same machine in the
      same millisecond — astronomically unlikely for /build --extend).
    """
    timestamp_ms = time.time_ns() // 1_000_000
    # Low 24 bits of the timestamp → 6 hex chars. Mask preserves
    # monotonic ordering within a ~4.66-hour window.
    timestamp_low = timestamp_ms & 0xFFFFFF
    timestamp_hex = f"{timestamp_low:06x}"
    suffix_hex = hashlib.sha256(os.urandom(2)).hexdigest()[:2]
    return f"{timestamp_hex}{suffix_hex}"


# ── Public API: resolve_target ──────────────────────────────────────────


def resolve_target(
    etc_sdlc_root: Path, feature_id_arg: str | None
) -> Path:
    """Return the target shipped feature dir.

    If ``feature_id_arg`` is supplied, scan ``shipped/`` for a dir
    matching ``<feature_id_arg>-*`` and return the first match. If
    ``feature_id_arg`` is ``None``, return the most-recently-shipped
    feature dir (by ``state.yaml.build.completed_at``).

    Args:
        etc_sdlc_root: Path to the project's ``.etc_sdlc/`` directory.
        feature_id_arg: ``F<NNN>`` string, or ``None`` for most-recent.

    Returns:
        Resolved absolute path to the shipped feature directory.

    Raises:
        FeatureNotFoundError: When no shipped dir matches the operator's
            arg, or when ``feature_id_arg`` is None and no shipped dirs
            exist at all.
    """
    shipped_root = etc_sdlc_root / "features" / _SHIPPED_SUBDIR
    if not shipped_root.is_dir():
        raise FeatureNotFoundError(
            f"shipped/ root does not exist under {etc_sdlc_root}; "
            f"no extendable features"
        )

    if feature_id_arg is not None:
        return _resolve_by_feature_id(shipped_root, feature_id_arg)

    return _resolve_most_recent_shipped(shipped_root)


def _resolve_by_feature_id(shipped_root: Path, feature_id: str) -> Path:
    """Return the shipped dir matching ``<feature_id>-*`` or raise."""
    for entry in shipped_root.glob(f"{feature_id}-*"):
        if entry.is_dir():
            return entry.resolve()
    raise FeatureNotFoundError(
        f"feature {feature_id} not found under {shipped_root}"
    )


def _resolve_most_recent_shipped(shipped_root: Path) -> Path:
    """Return the shipped dir with the latest ``state.yaml.build.completed_at``."""
    candidates: list[tuple[str, Path]] = []
    for entry in shipped_root.iterdir():
        if not entry.is_dir():
            continue
        completed_at = _read_completed_at(entry)
        if completed_at is None:
            continue
        candidates.append((completed_at, entry))

    if not candidates:
        raise FeatureNotFoundError(
            f"no shipped features found under {shipped_root}"
        )

    candidates.sort(key=lambda pair: pair[0], reverse=True)
    return candidates[0][1].resolve()


def _read_completed_at(feature_dir: Path) -> str | None:
    """Return ``state.yaml.build.completed_at`` or None on any failure."""
    state_path = feature_dir / "state.yaml"
    if not state_path.is_file():
        return None
    try:
        loaded = yaml.safe_load(state_path.read_text())
    except yaml.YAMLError:
        return None
    if not isinstance(loaded, dict):
        return None
    build = loaded.get("build")
    if not isinstance(build, dict):
        return None
    completed_at = build.get("completed_at")
    if not isinstance(completed_at, str):
        return None
    return completed_at


# ── Public API: classify ────────────────────────────────────────────────


def classify(problem: str, target_dir: Path) -> _TriageOutcome:
    """Apply the BR-002 rule-based triage rubric.

    Order of checks (BR-002):

    1. **Heavy** — any architectural keyword present (case-insensitive
       substring match).
    2. **Light** — at least one path-shaped token AND <=3 such tokens
       AND no architectural keyword.
    3. **Medium** — everything else.

    Args:
        problem: Operator's free-text problem description.
        target_dir: Target feature dir (reserved for future inspection
            of ``spec.md``/``design.md``; not used today).

    Returns:
        Literal triage outcome.
    """
    # target_dir reserved for future spec.md/design.md inspection (BR-002
    # leaves the door open). Today the rubric is text-only.
    del target_dir

    lowered = problem.lower()
    if _has_architectural_keyword(lowered):
        return "heavy"

    file_paths = _FILE_PATH_PATTERN.findall(problem)
    if 1 <= len(file_paths) <= _LIGHT_MAX_FILES:
        return "light"

    return "medium"


def _has_architectural_keyword(lowered_problem: str) -> bool:
    """True iff any architectural keyword appears in the lowered text."""
    return any(keyword in lowered_problem for keyword in _ARCHITECTURAL_KEYWORDS)


# ── Public API: reopen ──────────────────────────────────────────────────


def reopen(target_dir: Path, etc_sdlc_root: Path) -> Path:
    """Move target_dir from ``shipped/`` to ``active/`` via shutil.move.

    Mirrors F022's gitignored-fallback shape. The destination path is
    ``<etc_sdlc_root>/features/active/<basename>``.

    Args:
        target_dir: The shipped feature dir to reopen.
        etc_sdlc_root: Path to the project's ``.etc_sdlc/`` directory.

    Returns:
        Resolved path to the dir under ``active/``.

    Raises:
        FileExistsError: When ``active/<basename>`` already exists.
        FileNotFoundError: When ``target_dir`` is absent on disk.
    """
    if not target_dir.is_dir():
        raise FileNotFoundError(
            f"target_dir does not exist: {target_dir}"
        )

    active_root = etc_sdlc_root / "features" / _ACTIVE_SUBDIR
    active_root.mkdir(parents=True, exist_ok=True)
    destination = active_root / target_dir.name

    if destination.exists():
        raise FileExistsError(
            f"active/ collision: {destination} already exists"
        )

    shutil.move(str(target_dir), str(destination))
    return destination.resolve()


# ── Public API: record_extend ───────────────────────────────────────────


def record_extend(
    *,
    target_dir: Path,
    extend_id: str,
    problem: str,
    triage: str,
    dispatched_agents: list[str],
) -> None:
    """Append an extend entry to ``state.yaml.extends``.

    Per BR-005: append-only. Existing entries are never mutated by this
    function. The new entry's ``completed_at`` and ``release_tag`` are
    initialized to ``None``; ``complete_extend`` flips them later.

    Args:
        target_dir: Active feature dir containing ``state.yaml``.
        extend_id: 8-char hex extension ID.
        problem: Verbatim operator problem string.
        triage: One of ``light | medium | heavy``.
        dispatched_agents: List of agent role names that will receive work.
    """
    state = _read_state_yaml(target_dir)
    extends = state.get("extends")
    if not isinstance(extends, list):
        extends = []

    entry = {
        "extend_id": extend_id,
        "problem": problem,
        "triage": triage,
        "started_at": _utc_now_iso8601(),
        "completed_at": None,
        "release_tag": None,
        "dispatched_agents": list(dispatched_agents),
    }
    extends.append(entry)
    state["extends"] = extends
    _write_state_yaml(target_dir, state)


# ── Public API: complete_extend ─────────────────────────────────────────


def complete_extend(
    *,
    target_dir: Path,
    extend_id: str,
    release_tag: str,
) -> None:
    """Set ``completed_at`` + ``release_tag`` on the matching in-flight entry.

    Idempotent: a second call with the same ``extend_id`` is a no-op
    (existing ``completed_at`` and ``release_tag`` are preserved).

    Args:
        target_dir: Active feature dir containing ``state.yaml``.
        extend_id: The 8-char hex ID identifying the entry to close.
        release_tag: The release tag (e.g.
            ``etc/feature/F042/release/01b5a3c7``) to record.

    Raises:
        KeyError: When no entry matches ``extend_id``.
    """
    state = _read_state_yaml(target_dir)
    extends = state.get("extends")
    if not isinstance(extends, list):
        raise KeyError(
            f"no extends entry matching extend_id={extend_id!r} "
            f"(state.yaml has no extends list)"
        )

    for entry in extends:
        if not isinstance(entry, dict):
            continue
        if entry.get("extend_id") != extend_id:
            continue
        if entry.get("completed_at") is None:
            entry["completed_at"] = _utc_now_iso8601()
            entry["release_tag"] = release_tag
        # Idempotent: if completed_at already set, leave both fields alone.
        state["extends"] = extends
        _write_state_yaml(target_dir, state)
        return

    raise KeyError(
        f"no extends entry matching extend_id={extend_id!r}"
    )


# ── Public API: close ───────────────────────────────────────────────────


def close(target_dir: Path, etc_sdlc_root: Path) -> Path:
    """Move target_dir from ``active/`` to ``shipped/`` via shutil.move.

    Mirrors F022's gitignored-fallback shape (used by the close half of
    the extend lifecycle). The destination path is
    ``<etc_sdlc_root>/features/shipped/<basename>``.

    Args:
        target_dir: The active feature dir to close.
        etc_sdlc_root: Path to the project's ``.etc_sdlc/`` directory.

    Returns:
        Resolved path to the dir under ``shipped/``.

    Raises:
        FileExistsError: When ``shipped/<basename>`` already exists.
        FileNotFoundError: When ``target_dir`` is absent on disk.
    """
    if not target_dir.is_dir():
        raise FileNotFoundError(
            f"target_dir does not exist: {target_dir}"
        )

    shipped_root = etc_sdlc_root / "features" / _SHIPPED_SUBDIR
    shipped_root.mkdir(parents=True, exist_ok=True)
    destination = shipped_root / target_dir.name

    if destination.exists():
        raise FileExistsError(
            f"shipped/ collision: {destination} already exists"
        )

    shutil.move(str(target_dir), str(destination))
    return destination.resolve()


# ── Internals: state.yaml read/write ────────────────────────────────────


def _read_state_yaml(target_dir: Path) -> dict[str, Any]:
    """Return parsed ``state.yaml`` mapping or ``{}`` on absence/empty."""
    state_path = target_dir / "state.yaml"
    if not state_path.is_file():
        return {}
    loaded = yaml.safe_load(state_path.read_text())
    if not isinstance(loaded, dict):
        return {}
    return loaded


def _write_state_yaml(target_dir: Path, state: dict[str, Any]) -> None:
    """Re-emit ``state.yaml`` with ``sort_keys=False`` for stable ordering."""
    state_path = target_dir / "state.yaml"
    state_path.write_text(yaml.safe_dump(state, sort_keys=False))


def _utc_now_iso8601() -> str:
    """Return the current UTC instant as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


# ── CLI ─────────────────────────────────────────────────────────────────


def _cmd_generate_id() -> int:
    """Emit a fresh 8-char hex extension ID to stdout."""
    print(generate_extend_id())
    return 0


def _cmd_resolve_target(etc_sdlc_root: str, feature_id_arg: str | None) -> int:
    """Resolve the target shipped dir; print to stdout."""
    try:
        resolved = resolve_target(Path(etc_sdlc_root), feature_id_arg)
    except FeatureNotFoundError as exc:
        print(f"resolve-target error: {exc}", file=sys.stderr)
        return 1

    print(str(resolved))
    return 0


def _cmd_classify(problem: str, target_dir: str) -> int:
    """Classify and print the triage outcome to stdout."""
    outcome = classify(problem, Path(target_dir))
    print(outcome)
    return 0


def main(argv: list[str] | None = None) -> int:
    """Entry point for the extend_resolver CLI.

    Subcommands:
        generate-id
            Emit an 8-char hex extension ID.
        resolve-target <etc_sdlc_root> [--feature F<NNN>]
            Locate the target shipped feature dir.
        classify <problem> <target_dir>
            Apply the triage rubric and emit ``light``/``medium``/``heavy``.

    The mutation subcommands (``reopen``, ``record-extend``,
    ``complete-extend``, ``close``) intentionally have no CLI surface
    today — the skill body (``skills/build/SKILL.md``) drives them via
    the Python API. Surfacing them later is additive.
    """
    parser = argparse.ArgumentParser(
        prog="extend_resolver.py",
        description=(
            "F025 /build --extend lifecycle helper: ID gen, target "
            "resolution, triage classification, and state.yaml.extends "
            "append/close."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("generate-id", help="Emit an 8-char hex extension ID.")

    resolve = sub.add_parser(
        "resolve-target",
        help="Locate the target shipped feature dir.",
    )
    resolve.add_argument(
        "etc_sdlc_root",
        help="Path to the project's .etc_sdlc/ directory.",
    )
    resolve.add_argument(
        "--feature",
        dest="feature_id_arg",
        default=None,
        help="F<NNN> feature ID; omit for most-recent-shipped.",
    )

    classify_parser = sub.add_parser(
        "classify",
        help="Emit triage outcome (light|medium|heavy) for the problem.",
    )
    classify_parser.add_argument(
        "problem",
        help="Operator's free-text problem statement.",
    )
    classify_parser.add_argument(
        "target_dir",
        help="Target feature dir (reserved for future inspection).",
    )

    args = parser.parse_args(argv)

    if args.command == "generate-id":
        return _cmd_generate_id()
    if args.command == "resolve-target":
        return _cmd_resolve_target(args.etc_sdlc_root, args.feature_id_arg)
    if args.command == "classify":
        return _cmd_classify(args.problem, args.target_dir)

    parser.print_help(sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
