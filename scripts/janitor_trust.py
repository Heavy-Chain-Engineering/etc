#!/usr/bin/env python3
"""janitor_trust.py — sole writer of `.etc_sdlc/janitor/trust.yaml`.

Owns the per-category graduated-trust state for the /janitor skill
(F-2026-05-29-janitor-autonomous-cleanup, task 003). Every fix-category
starts in ``preview`` (janitor opens a DRAFT PR the operator reviews) and
auto-promotes to ``autonomous`` (ready-for-review PR) once its derived
clean-streak reaches ``N`` consecutive clean merges (ADR-005, N=5).

Trust streaks are DERIVED from git/gh history and reconciled lazily at the
start of each run (ADR-003): ``reconcile`` queries
``gh pr list --author <janitor> --state merged|closed``, joins the result to
the ``runs.jsonl`` ledger by branch name to learn each PR's category,
classifies each PR as clean-merged (zero commits after janitor's initial
commit), merged-with-edits, or closed-unmerged, recomputes each category's
consecutive-clean streak newest-first, and persists to ``trust.yaml``.
Git+gh is the system of record; ``trust.yaml`` is a rebuildable cache.

Safety invariants:
    - ``trust ∈ {preview, autonomous}``; ``clean_streak ≥ 0``.
    - ``autonomous`` IFF ``clean_streak ≥ N`` — a corrupt cache that claims
      autonomy below the threshold is read back as ``preview``.
    - Missing OR malformed ``trust.yaml`` → every category ``preview``
      (edge 11 / AC-008): never silently assume ``autonomous``.
    - Any gh-boundary failure (binary absent, non-zero gh exit, or malformed
      gh output) → ``reconcile`` is a no-op; ``trust.yaml`` is left UNTOUCHED
      (never falsely promotes). A non-boundary error still crashes loudly.

All state lives under ``.etc_sdlc/janitor/`` (AC-011). The whole-file write
is atomic (temp file + ``os.replace``). Stdlib + PyYAML only. Every git/gh
call uses an argv-list ``subprocess.run`` — never ``shell=True``, never an
interpolated shell string (command-injection defense).

CLI:
    janitor_trust.py reconcile [--limit N] [--state-dir DIR]
    janitor_trust.py level <category> [--state-dir DIR]   → preview|autonomous
    janitor_trust.py table [--state-dir DIR]
    janitor_trust.py demote <category> [--state-dir DIR]  → preview, streak 0
Exit 0 on success, 1 on error.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import tempfile
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

LOGGER = logging.getLogger(__name__)

SCHEMA_VERSION: int = 1

# ADR-005: a category auto-promotes preview→autonomous once its derived
# consecutive-clean-merge streak reaches N. N is a tunable constant, not a
# permanent contract — raising/lowering it is this one-line change.
N: int = 5

# The trust levels a category may hold. ``autonomous`` IFF streak >= N.
LEVEL_PREVIEW: str = "preview"
LEVEL_AUTONOMOUS: str = "autonomous"

# Filenames under the janitor state directory (AC-011).
TRUST_FILENAME: str = "trust.yaml"
RUNS_FILENAME: str = "runs.jsonl"

# `gh pr list --author <janitor>`: @me resolves to the authenticated user
# the operator runs janitor as (ADR-003 — uses the operator's existing gh
# auth; no new credential surface).
_JANITOR_AUTHOR: str = "@me"

# A clean janitor PR carries exactly the single initial janitor commit; any
# additional commit means the operator edited the branch before merge.
_CLEAN_COMMIT_COUNT: int = 1

# The gh-boundary failure classes that degrade reconcile to the documented
# no-op (module docstring, ADR-003): the binary is absent
# (FileNotFoundError), gh exits non-zero — no remote, auth scope, rate limit
# — (CalledProcessError, since the default runner uses ``check=True``), or gh
# emits malformed output (JSONDecodeError). This tuple is deliberately
# narrow: a non-zero exit, a missing binary, or unparseable JSON is an
# expected environment condition, not a bug in our own code. A failure of any
# OTHER class still propagates and crashes loudly (never widen to
# ``except Exception``).
_GH_BOUNDARY_ERRORS: tuple[type[Exception], ...] = (
    FileNotFoundError,
    subprocess.CalledProcessError,
    json.JSONDecodeError,
)

# The seam every git/gh call flows through: argv list → captured stdout.
# Injectable so tests stay hermetic; the default shells `gh` via subprocess.
GhRunner = Callable[[list[str]], str]


# ── State construction / serialization ──────────────────────────────────


def empty_state() -> dict[str, Any]:
    """Return a fresh, safe-default trust state (no categories yet)."""
    return {"schema_version": SCHEMA_VERSION, "categories": {}}


def _coerce_streak(value: Any) -> int:
    """Coerce a stored ``clean_streak`` to a non-negative int (else 0)."""
    if isinstance(value, bool) or not isinstance(value, int):
        return 0
    return max(value, 0)


def load_trust(path: Path) -> dict[str, Any]:
    """Load trust state, defaulting EVERY category to ``preview`` on any doubt.

    Missing file, unreadable file, malformed YAML, a non-mapping top level,
    or a malformed ``categories`` block all collapse to a safe empty state
    (edge 11 / AC-008). A stored ``autonomous`` entry whose ``clean_streak``
    is below ``N`` is treated as ``preview`` — a corrupt cache never grants
    autonomy.

    The returned state is always normalized: ``schema_version`` set,
    ``categories`` a mapping of ``{trust, clean_streak, promoted_at}`` with
    ``trust`` re-derived from the streak so the in-memory invariant holds.
    """
    raw = _read_raw_trust(path)
    if raw is None:
        return empty_state()

    categories_raw = raw.get("categories")
    if not isinstance(categories_raw, dict):
        return empty_state()

    state = empty_state()
    for name, entry in categories_raw.items():
        streak = _coerce_streak(entry.get("clean_streak")) if isinstance(
            entry, dict
        ) else 0
        promoted_at = entry.get("promoted_at") if isinstance(entry, dict) else None
        state["categories"][str(name)] = _category_record(streak, promoted_at)
    return state


def _read_raw_trust(path: Path) -> dict[str, Any] | None:
    """Read+parse the YAML file; return None on any read/parse/shape problem."""
    if not path.exists():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        LOGGER.warning("Cannot read trust file %s: %s", path, exc)
        return None
    try:
        parsed = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        LOGGER.warning("Malformed trust YAML at %s: %s", path, exc)
        return None
    if not isinstance(parsed, dict):
        LOGGER.warning("Trust file %s is not a mapping; defaulting to preview.", path)
        return None
    return parsed


def _category_record(streak: int, promoted_at: Any) -> dict[str, Any]:
    """Build a normalized category record with trust re-derived from streak.

    Enforces the ``autonomous`` IFF ``streak >= N`` invariant: a record whose
    streak no longer meets the threshold is recorded as ``preview`` with no
    ``promoted_at``, regardless of what was stored.
    """
    if streak >= N:
        kept = promoted_at if isinstance(promoted_at, str) else _now_iso()
        return {
            "trust": LEVEL_AUTONOMOUS,
            "clean_streak": streak,
            "promoted_at": kept,
        }
    return {"trust": LEVEL_PREVIEW, "clean_streak": streak, "promoted_at": None}


def category_level(state: dict[str, Any], category: str) -> str:
    """Return ``preview`` or ``autonomous`` for ``category`` in ``state``.

    Unknown categories are ``preview`` (safe default).
    """
    entry = state["categories"].get(category)
    if not isinstance(entry, dict):
        return LEVEL_PREVIEW
    return LEVEL_AUTONOMOUS if entry.get("trust") == LEVEL_AUTONOMOUS else LEVEL_PREVIEW


def save_trust(path: Path, state: dict[str, Any]) -> None:
    """Atomically write ``state`` to ``path`` (temp file + ``os.replace``).

    Writes to a temp file in the destination directory, fsyncs, then renames
    over the target so a reader never observes a partially-written file. On
    failure the temp file is unlinked.
    """
    body = yaml.safe_dump(state, sort_keys=False, default_flow_style=False)
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
        os.replace(tmp_path, path)
    except OSError:
        try:
            tmp_path.unlink()
        except OSError:  # pragma: no cover — cleanup-of-cleanup, best effort
            pass
        raise


# ── Reconciliation (ADR-003) ────────────────────────────────────────────


def _default_gh_runner(argv: list[str]) -> str:
    """Run a gh/git command via argv-list subprocess; return stdout.

    Raises FileNotFoundError if the binary is absent (the caller treats this
    as "gh unavailable" → no-op). Never uses ``shell=True``.
    """
    completed = subprocess.run(  # noqa: S603 — argv list, no shell
        argv, check=True, capture_output=True, text=True, encoding="utf-8"
    )
    return completed.stdout


def _gh_pr_list(runner: GhRunner, state: str, limit: int) -> list[dict[str, Any]]:
    """Return janitor PR records for one ``--state`` via ``gh pr list --json``."""
    out = runner(
        [
            "gh",
            "pr",
            "list",
            "--author",
            _JANITOR_AUTHOR,
            "--state",
            state,
            "--json",
            "number,headRefName,mergedAt,closedAt",
            "--limit",
            str(limit),
        ]
    )
    parsed = json.loads(out) if out.strip() else []
    return parsed if isinstance(parsed, list) else []


def _gh_branch_commit_count(runner: GhRunner, number: int) -> int:
    """Return the number of commits on the branch behind PR ``number``."""
    out = runner(["gh", "pr", "view", str(number), "--json", "commits"])
    parsed = json.loads(out) if out.strip() else {}
    commits = parsed.get("commits") if isinstance(parsed, dict) else None
    return len(commits) if isinstance(commits, list) else _CLEAN_COMMIT_COUNT


def _load_branch_to_category(runs_path: Path) -> dict[str, str]:
    """Map each janitor branch → its (first) category from ``runs.jsonl``."""
    mapping: dict[str, str] = {}
    if not runs_path.exists():
        return mapping
    for line in runs_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        branch = row.get("branch")
        categories = row.get("categories") or []
        if isinstance(branch, str) and categories:
            mapping.setdefault(branch, str(categories[0]))
    return mapping


def _event_timestamp(pr: dict[str, Any]) -> str:
    """Best-effort recency key: mergedAt if present, else closedAt, else ''."""
    return str(pr.get("mergedAt") or pr.get("closedAt") or "")


def _is_clean_merge(pr: dict[str, Any], runner: GhRunner) -> bool:
    """A merged PR is clean iff it merged with exactly the initial commit."""
    if not pr.get("mergedAt"):
        return False  # closed-unmerged is never clean
    return _gh_branch_commit_count(runner, int(pr["number"])) <= _CLEAN_COMMIT_COUNT


def _streak_for_category(events: list[tuple[str, bool]]) -> int:
    """Count consecutive clean events from newest (first) until a non-clean."""
    streak = 0
    for _ts, is_clean in events:
        if not is_clean:
            break
        streak += 1
    return streak


def _collect_events(
    prs: list[dict[str, Any]],
    branch_to_category: dict[str, str],
    runner: GhRunner,
) -> dict[str, list[tuple[str, bool]]]:
    """Group classified (timestamp, is_clean) events per category, newest-first."""
    by_category: dict[str, list[tuple[str, bool]]] = {}
    for pr in prs:
        branch = pr.get("headRefName")
        category = branch_to_category.get(branch) if isinstance(branch, str) else None
        if category is None:
            continue  # PR has no ledger entry → unknown category, skip
        by_category.setdefault(category, []).append(
            (_event_timestamp(pr), _is_clean_merge(pr, runner))
        )
    for events in by_category.values():
        events.sort(key=lambda item: item[0], reverse=True)
    return by_category


def reconcile(
    trust_path: Path,
    runs_path: Path,
    *,
    limit: int = N,
    gh_runner: GhRunner | None = None,
) -> bool:
    """Recompute trust from gh/git history and persist (ADR-003).

    Returns True if ``trust.yaml`` was (re)written, False if reconciliation
    was skipped because of a gh-boundary failure — ``gh`` absent, a non-zero
    gh exit (no remote, auth scope, rate limit), or malformed gh output. In
    every skip case the file is left UNTOUCHED (never falsely promotes); a
    failure of any other class still propagates and crashes loudly.
    """
    runner = gh_runner or _default_gh_runner
    branch_to_category = _load_branch_to_category(runs_path)
    # The WHOLE gh-deriving span lives in this try: both ``_gh_pr_list`` calls
    # AND ``_collect_events`` (which fans out to ``_gh_branch_commit_count`` →
    # more gh sub-calls). Any gh-boundary failure anywhere in the span — not
    # just the two pr-list calls — degrades to the documented no-op so a
    # sub-call failure can never crash the CLI nor falsely promote a category.
    try:
        merged = _gh_pr_list(runner, "merged", limit)
        closed = _gh_pr_list(runner, "closed", limit)
        events = _collect_events(merged + closed, branch_to_category, runner)
    except _GH_BOUNDARY_ERRORS as exc:
        LOGGER.warning(
            "gh boundary failure (%s); skipping trust reconciliation, "
            "trust.yaml left untouched.",
            type(exc).__name__,
        )
        return False

    state = empty_state()
    for category, category_events in events.items():
        streak = _streak_for_category(category_events)
        state["categories"][category] = _category_record(streak, None)

    save_trust(trust_path, state)
    return True


# ── Mutations ───────────────────────────────────────────────────────────


def demote(trust_path: Path, category: str) -> dict[str, Any]:
    """Return ``category`` to ``preview`` with ``clean_streak`` reset to 0.

    Idempotent for unknown categories (records a fresh preview entry). Writes
    the whole file atomically and returns the updated state.
    """
    state = load_trust(trust_path)
    state["categories"][category] = _category_record(0, None)
    save_trust(trust_path, state)
    return state


# ── Helpers ─────────────────────────────────────────────────────────────


def _now_iso() -> str:
    """UTC timestamp in ISO-8601 with a trailing Z (e.g. promoted_at)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _trust_path(state_dir: Path) -> Path:
    return state_dir / TRUST_FILENAME


def _runs_path(state_dir: Path) -> Path:
    return state_dir / RUNS_FILENAME


# ── Command-line interface ──────────────────────────────────────────────


def _cli_reconcile(args: argparse.Namespace) -> int:
    state_dir = Path(args.state_dir)
    reconcile(
        _trust_path(state_dir), _runs_path(state_dir), limit=args.limit
    )
    return 0


def _cli_level(args: argparse.Namespace) -> int:
    state = load_trust(_trust_path(Path(args.state_dir)))
    print(category_level(state, args.category))
    return 0


def _cli_table(args: argparse.Namespace) -> int:
    state = load_trust(_trust_path(Path(args.state_dir)))
    categories = state["categories"]
    if not categories:
        print("No categories tracked yet (all default to preview).")
        return 0

    header = f"{'CATEGORY':<28} {'TRUST':<11} {'STREAK':>6}  PROMOTED_AT"
    print(header)
    print("-" * len(header))
    for name in sorted(categories):
        entry = categories[name]
        promoted = entry.get("promoted_at") or "-"
        print(
            f"{name:<28} {entry['trust']:<11} "
            f"{entry['clean_streak']:>6}  {promoted}"
        )
    return 0


def _cli_demote(args: argparse.Namespace) -> int:
    demote(_trust_path(Path(args.state_dir)), args.category)
    print(f"{args.category}: demoted to preview (clean_streak reset to 0).")
    return 0


def _add_state_dir(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--state-dir",
        default=".etc_sdlc/janitor",
        help="Directory holding trust.yaml + runs.jsonl (default .etc_sdlc/janitor).",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="janitor_trust.py",
        description="Sole writer of .etc_sdlc/janitor/trust.yaml (per-category trust).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_reconcile = sub.add_parser(
        "reconcile", help="Recompute trust from gh/git history (no-op if gh absent)."
    )
    p_reconcile.add_argument(
        "--limit", type=int, default=N, help=f"Max PRs per gh query (default {N})."
    )
    _add_state_dir(p_reconcile)
    p_reconcile.set_defaults(func=_cli_reconcile)

    p_level = sub.add_parser(
        "level", help="Print a category's trust level (preview|autonomous)."
    )
    p_level.add_argument("category", help="Fix-category name.")
    _add_state_dir(p_level)
    p_level.set_defaults(func=_cli_level)

    p_table = sub.add_parser("table", help="Print a human-readable trust table.")
    _add_state_dir(p_table)
    p_table.set_defaults(func=_cli_table)

    p_demote = sub.add_parser(
        "demote", help="Return a category to preview (clean_streak → 0)."
    )
    p_demote.add_argument("category", help="Fix-category name to demote.")
    _add_state_dir(p_demote)
    p_demote.set_defaults(func=_cli_demote)

    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns the desired process exit code.

    Argparse exits directly (code 2) on unknown subcommands / missing args.
    Application-level errors return 1.
    """
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except OSError as exc:
        print(f"janitor_trust error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
