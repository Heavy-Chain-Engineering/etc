#!/usr/bin/env python3
"""janitor_assets.py — published-asset deletion guard for the /janitor skill.

A janitor cruft-cleanup deleted a logo under a landing-page repo's
``public/`` because nothing *in that repo* referenced it — but a sibling
project's email templates hotlinked the URL that file served, and every
subscriber email shipped a broken image for three days (canary incident
AP-001). Files under deploy-to-URL roots are a **cross-repo published API
surface**: repo-local reachability scans structurally cannot clear them.

This module supplies the two pure pieces the orchestrator (survey/select)
needs to guard such deletions
(F-2026-06-12-janitor-published-asset-surface, BR-001/BR-002/BR-003):

    classify(path)            — is this path published-asset surface?
    consumer_search(filename) — does any repo in this org consume it?

``classify`` is by path against a CLOSED glob set anchored at the path root
(``public/``, ``static/``, ``www/``); non-matching paths pass through
untouched. ``consumer_search`` derives the org from the repo's remote owner
(``gh repo view --json owner``) and runs an org-wide code search
(``gh search code <filename> --owner <org> --json repository,path``) through
an INJECTED runner seam (the ``janitor_trust.py`` ``gh_runner`` pattern), so
tests stay hermetic and the orchestrator owns the single gh trust crossing.

Verdict vocabulary (CLOSED — load-bearing for the skill/agent wiring; the
skill records this token in the run record and the agent aborts on it):

    cleared      — org search succeeded with ZERO consumers; safe to delete.
                   Carries an evidence dict {query, org_scope, searched_at
                   ISO-8601, hit_count} for the audit trail (BR-006).
    blocked      — at least one consumer found; deletion rejected upstream,
                   each consumer named "<repo>:<path>" (BR-002).
    fail-closed  — the search could not run (gh absent, non-zero exit,
                   rate-limit, unparseable output). NOT cleared, NEVER a
                   repo-local fallback (BR-003 / GA-003); distinct from a
                   genuine zero-hit clear. The boundary failure class is
                   named in ``reason`` so the run record and operator-confirm
                   prompt can surface WHY.

The gh-boundary failure set is deliberately NARROW (binary absent, non-zero
exit, unparseable JSON), mirroring ``janitor_trust.py``'s degrade suite: an
expected environment condition degrades to ``fail-closed``; any OTHER error
class still propagates and crashes loudly (never widen to
``except Exception``).

CLI (machine-parseable stdout; exit 0 = success, 1 = error, 2 = argparse):
    janitor_assets.py classify <path>
        → one token on stdout: ``published-asset`` | ``other``
    janitor_assets.py consumer-search <filename> [--repo-root R]
        → one JSON verdict on stdout:
          {status, consumers[], evidence{}|null, reason|null}
Stdlib only (no PyYAML needed). Every gh call uses an argv-list
``subprocess.run`` — never ``shell=True``, never an interpolated shell
string (command-injection defense).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Any

# ── Classification vocabulary (AC-1) ─────────────────────────────────────

# GA-004: the CLOSED v1 published-asset root set. Tight on purpose;
# extendable later only via the write-boundary standard's machine-parseable
# list (nested deploy roots like apps/*/public are an explicit, documented
# list-extension — NOT silently inferred here). A module constant because
# the skill wiring reads it as the single source of truth.
PUBLISHED_ROOTS: tuple[str, ...] = ("public", "static", "www")

# classify() return tokens (also the CLI's stdout tokens).
PUBLISHED_ASSET: str = "published-asset"
OTHER: str = "other"

# ── Verdict vocabulary (AC-2 / AC-3) ─────────────────────────────────────
#
# CLOSED set — load-bearing for the skill/agent wiring (documented above).

CLEARED: str = "cleared"
BLOCKED: str = "blocked"
FAIL_CLOSED: str = "fail-closed"

# The gh-boundary failure classes that degrade ``consumer_search`` to the
# fail-closed verdict (NOT a repo-local fallback): the binary is absent
# (FileNotFoundError), gh exits non-zero — no remote, auth scope, rate
# limit — (CalledProcessError, since the default runner uses ``check=True``),
# or gh emits unparseable output (JSONDecodeError). Deliberately narrow:
# these are expected environment conditions, not bugs in our own code. Any
# OTHER class still propagates and crashes loudly (never widen to
# ``except Exception``). Mirrors janitor_trust.py's ``_GH_BOUNDARY_ERRORS``.
_GH_BOUNDARY_ERRORS: tuple[type[Exception], ...] = (
    FileNotFoundError,
    subprocess.CalledProcessError,
    json.JSONDecodeError,
)

# The seam every gh call flows through: argv list → captured stdout.
# Injectable so tests stay hermetic; the default shells `gh` via subprocess.
GhRunner = Callable[[list[str]], str]


@dataclass(frozen=True)
class ConsumerVerdict:
    """The outcome of an org-wide consumer search for one asset filename.

    ``status`` is one of the CLOSED tokens ``cleared`` | ``blocked`` |
    ``fail-closed``. ``consumers`` are named ``"<repo>:<path>"`` (non-empty
    iff ``blocked``). ``evidence`` carries the audit dict on ``cleared`` and
    ``blocked`` (the searched scope is attestable); it is ``None`` on
    ``fail-closed`` (no search completed, so nothing is attested).
    ``reason`` names the gh-boundary failure class on ``fail-closed`` only.
    """

    status: str
    consumers: list[str] = field(default_factory=list)
    evidence: dict[str, Any] | None = None
    reason: str | None = None


# ── Classification (AC-1) ────────────────────────────────────────────────


def classify(path: str) -> str:
    """Classify ``path`` as published-asset surface or pass-through.

    Returns ``PUBLISHED_ASSET`` iff the FIRST path segment is one of the
    closed ``PUBLISHED_ROOTS`` (``public`` / ``static`` / ``www``), anchored
    at the path root: ``public/logo.png`` matches; ``publicity/x``,
    ``my-public/x``, and the nested ``app/public/x`` do NOT (v1 anchors to
    the documented top-level roots). A leading ``./`` is normalized away.
    Every other path returns ``OTHER`` and is left untouched by the guard.
    """
    parts = PurePosixPath(path.strip()).parts
    if parts and parts[0] in PUBLISHED_ROOTS:
        return PUBLISHED_ASSET
    return OTHER


# ── Consumer search (AC-2 / AC-3) ────────────────────────────────────────


def consumer_search(
    filename: str,
    *,
    repo_root: str = ".",
    gh_runner: GhRunner | None = None,
) -> ConsumerVerdict:
    """Search the repo's org for consumers of ``filename``; return a verdict.

    Derives the org from the repo's remote owner (``gh repo view --json
    owner``, GA-002), then runs an org-wide code search (``gh search code
    <filename> --owner <org> --json repository,path``) through the injected
    ``gh_runner`` seam. A consumer hit → ``blocked`` (each consumer named);
    zero hits → ``cleared`` with the evidence dict recorded (BR-002/BR-006).

    Any gh-boundary failure — gh absent, non-zero exit, rate-limit, or
    unparseable output — degrades to ``fail-closed`` (NOT cleared, never a
    repo-local fallback; BR-003 / GA-003), naming the failure class in
    ``reason``. A non-boundary error propagates and crashes loudly.
    """
    runner = gh_runner or _default_gh_runner
    searched_at = _now_iso()
    try:
        org = _derive_org(runner, repo_root)
        hits = _search_code(runner, filename, org)
    except _GH_BOUNDARY_ERRORS as exc:
        return ConsumerVerdict(
            status=FAIL_CLOSED,
            reason=f"{type(exc).__name__}: {exc}",
        )

    consumers = [_name_consumer(hit) for hit in hits]
    evidence = _build_evidence(filename, org, searched_at, len(hits))
    if consumers:
        return ConsumerVerdict(status=BLOCKED, consumers=consumers, evidence=evidence)
    return ConsumerVerdict(status=CLEARED, evidence=evidence)


def _derive_org(runner: GhRunner, repo_root: str) -> str:
    """Return the org login from the repo's remote owner (GA-002).

    Raises ``CalledProcessError`` (gh boundary, handled by the caller) when
    the response has no usable ``owner.login`` — an org we cannot name is a
    scope we cannot attest to, so it must fail closed rather than search a
    blank or guessed scope.
    """
    out = runner(["gh", "repo", "view", repo_root, "--json", "owner"])
    parsed = json.loads(out) if out.strip() else {}
    owner = parsed.get("owner") if isinstance(parsed, dict) else None
    login = owner.get("login") if isinstance(owner, dict) else None
    if not isinstance(login, str) or not login:
        raise subprocess.CalledProcessError(
            1, ["gh", "repo", "view"], "owner.login missing from gh output"
        )
    return login


def _search_code(runner: GhRunner, filename: str, org: str) -> list[dict[str, Any]]:
    """Return the org-wide code-search hit records for ``filename``.

    ``gh search code`` supports ``--json repository,path`` (verified against
    the installed gh); the default output is JSON when ``--json`` is given,
    so we parse it directly. A non-list parse is treated as zero hits.
    """
    out = runner(
        [
            "gh",
            "search",
            "code",
            filename,
            "--owner",
            org,
            "--json",
            "repository,path",
        ]
    )
    parsed = json.loads(out) if out.strip() else []
    return parsed if isinstance(parsed, list) else []


def _name_consumer(hit: dict[str, Any]) -> str:
    """Name one consumer ``"<repo>:<path>"`` from a gh search-code hit.

    ``repository`` is the ``{nameWithOwner: ...}`` shape gh returns; falls
    back to a literal placeholder for either missing half so a malformed hit
    still produces a non-empty, operator-legible consumer line (a hit is a
    hit — never silently dropped).
    """
    repository = hit.get("repository") if isinstance(hit, dict) else None
    repo_name = repository.get("nameWithOwner") if isinstance(repository, dict) else None
    path = hit.get("path") if isinstance(hit, dict) else None
    return f"{repo_name or '<unknown-repo>'}:{path or '<unknown-path>'}"


def _build_evidence(filename: str, org: str, searched_at: str, hit_count: int) -> dict[str, Any]:
    """Build the BR-006 evidence dict recorded for a completed search."""
    return {
        "query": f"gh search code {filename} --owner {org}",
        "org_scope": org,
        "searched_at": searched_at,
        "hit_count": hit_count,
    }


def _default_gh_runner(argv: list[str]) -> str:
    """Run a gh command via argv-list subprocess; return stdout.

    Raises FileNotFoundError if the binary is absent (the caller treats this
    as a gh-boundary failure → fail-closed). Never uses ``shell=True``.
    """
    completed = subprocess.run(  # noqa: S603 — argv list, no shell
        argv, check=True, capture_output=True, text=True, encoding="utf-8"
    )
    return completed.stdout


def _now_iso() -> str:
    """UTC timestamp in ISO-8601 with a trailing Z (evidence searched_at)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ── Command-line interface ───────────────────────────────────────────────


def _cli_classify(args: argparse.Namespace) -> int:
    """``classify <path>`` — print one token (published-asset|other)."""
    print(classify(args.path))
    return 0


def _cli_consumer_search(args: argparse.Namespace) -> int:
    """``consumer-search <filename> [--repo-root R]`` — print a JSON verdict.

    The verdict is the machine contract the skill records in the run record;
    ``status`` is one of the closed tokens. Always exits 0 when the verdict
    was produced (including ``fail-closed`` — that is a VALID verdict, not a
    tool error); the caller branches on ``status``, never the exit code.
    """
    verdict = consumer_search(args.filename, repo_root=args.repo_root)
    print(json.dumps(asdict(verdict), sort_keys=True))
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="janitor_assets.py",
        description=(
            "Published-asset deletion guard: classify deploy-root paths and "
            "run the org-wide consumer search (used by /janitor survey/select)."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_classify = sub.add_parser(
        "classify",
        help="Print published-asset|other for a path (closed glob set).",
    )
    p_classify.add_argument("path", help="Repo-relative path to classify.")
    p_classify.set_defaults(func=_cli_classify)

    p_search = sub.add_parser(
        "consumer-search",
        help="Org-wide consumer search; prints a JSON verdict (fail-closed).",
    )
    p_search.add_argument("filename", help="Asset filename to search for.")
    p_search.add_argument(
        "--repo-root",
        default=".",
        help="Repo to derive the org from (default current dir).",
    )
    p_search.set_defaults(func=_cli_consumer_search)

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
        print(f"janitor_assets error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
