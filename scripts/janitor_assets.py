#!/usr/bin/env python3
"""janitor_assets.py — published-asset deletion guard for the /janitor skill.

A janitor cruft-cleanup deleted a logo under a landing-page repo's
``public/`` because nothing *in that repo* referenced it — but a sibling
project's email templates hotlinked the URL that file served, and every
subscriber email shipped a broken image for three days (canary incident
AP-001). Files under deploy-to-URL roots are a **cross-repo published API
surface**: repo-local reachability scans structurally cannot clear them.

This module supplies the pieces the orchestrator (survey/select) needs to
guard such deletions
(F-2026-06-12-janitor-published-asset-surface, BR-001/BR-002/BR-003):

    classify(path)            — is this path published-asset surface?
    consumer_search(filename) — does any repo in this org consume it?
    evaluate_candidate(path)  — the single composition the skill calls per
                                candidate: classify, then search ONLY if the
                                path is published-asset (AC-6 — an OTHER path
                                clears WITHOUT ever crossing to gh).

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
                   rate-limit, unparseable output, or a malformed org/
                   option-like filename). NOT cleared, NEVER a repo-local
                   fallback (BR-003 / GA-003); distinct from a genuine
                   zero-hit clear. The boundary/rejection cause is named in
                   ``reason`` so the run record and operator-confirm prompt
                   can surface WHY.
    cleared-other — the path is NOT published-asset surface; classification
                   alone clears it with no org search (AC-6). Distinct from
                   ``cleared`` so the skill can tell "search not needed" from
                   "searched, found nothing".

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
import posixpath
import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Protocol, TypedDict

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

# The composition verdict for a non-published-asset path: classification
# alone clears it WITHOUT an org search (AC-6 — a plain dead-code deletion
# like src/helper.py flows exactly as today, no gh crossing). Distinct from
# ``cleared`` (which attests to a completed zero-hit search) so the skill can
# tell "never needed a search" from "searched and found nothing".
CLEARED_OTHER: str = "cleared-other"

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

# GitHub's account/org login charset: alphanumeric or single hyphens, may not
# start with a hyphen, 1–39 chars. A derived owner.login that fails this is a
# malformed/hostile remote (whitespace, newline, injected text) — we refuse to
# search a scope we cannot validate and fail closed rather than attest to it.
_ORG_LOGIN_PATTERN: re.Pattern[str] = re.compile(r"[A-Za-z0-9][A-Za-z0-9\-]{0,38}")


class GhRunner(Protocol):
    """The seam every gh call flows through: argv list → captured stdout.

    Injectable so tests stay hermetic (the ``janitor_trust.py`` ``gh_runner``
    pattern); the default shells ``gh`` via subprocess. A Protocol (structural
    typing) so any plain ``(list[str]) -> str`` callable — including the test
    fakes — satisfies it without importing or subclassing anything.
    """

    def __call__(self, argv: list[str]) -> str: ...


class _CodeSearchHit(TypedDict, total=False):
    """One ``gh search code --json repository,path`` hit record.

    ``total=False``: gh may omit either field on a malformed/partial hit;
    ``_name_consumer`` substitutes a legible placeholder rather than dropping
    the hit (a hit is a hit). ``repository`` is gh's ``{nameWithOwner: ...}``
    shape.
    """

    repository: dict[str, str]
    path: str


class SearchEvidence(TypedDict):
    """The BR-006 audit dict recorded for a COMPLETED org-wide search.

    Pinned shape (skill records it verbatim in the run record): the exact
    query run, the org scope it attests to, an ISO-8601 timestamp, and the
    hit count (non-zero on ``blocked``; zero on ``cleared``).
    """

    query: str
    org_scope: str
    searched_at: str
    hit_count: int


@dataclass(frozen=True)
class ConsumerVerdict:
    """The outcome of evaluating one deletion candidate.

    ``status`` is one of the CLOSED tokens ``cleared`` | ``blocked`` |
    ``fail-closed`` | ``cleared-other``. ``consumers`` are named
    ``"<repo>:<path>"`` (non-empty iff ``blocked``). ``evidence`` carries the
    audit dict on ``cleared`` and ``blocked`` (the searched scope is
    attestable); it is ``None`` on ``fail-closed`` (no search completed) and
    on ``cleared-other`` (no search was needed). ``reason`` names the
    gh-boundary failure class on ``fail-closed`` only.
    """

    status: str
    consumers: list[str] = field(default_factory=list)
    evidence: SearchEvidence | None = None
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

    The path is canonicalized LEXICALLY first (``posixpath.normpath``) so a
    traversal-laden string cannot spoof a published root:
    ``public/../../etc/passwd`` normalizes to ``../etc/passwd`` and classifies
    ``OTHER``, and any path that escapes the repo root (a leading ``..`` after
    normalization, or an absolute ``/...``) is ``OTHER`` by construction —
    those are not repo-relative published-asset surface.
    """
    normalized = posixpath.normpath(path.strip())
    parts = PurePosixPath(normalized).parts
    if not parts or parts[0] in ("..", "/"):
        return OTHER
    if parts[0] in PUBLISHED_ROOTS:
        return PUBLISHED_ASSET
    return OTHER


# ── Guard composition (AC-6) ─────────────────────────────────────────────


def evaluate_candidate(
    path: str,
    *,
    repo_root: str = ".",
    gh_runner: GhRunner | None = None,
) -> ConsumerVerdict:
    """Decide one deletion candidate: classify, then search ONLY if needed.

    This is the single, obvious entry point the /janitor survey/select step
    calls per candidate — the composition the skill wires against:

        OTHER           → ``cleared-other`` immediately, with NO org search
                          (AC-6: a plain dead-code deletion like
                          ``src/helper.py`` flows exactly as today — the gh
                          crossing is never reached).
        PUBLISHED_ASSET → delegate to ``consumer_search`` on the filename
                          (the asset's basename), returning its
                          cleared/blocked/fail-closed verdict verbatim.

    Keeping the classify→search decision in ONE function makes the AC-6
    "never search an OTHER path" invariant structurally true (and testable
    with an exploding runner) rather than a convention each caller must
    re-implement.
    """
    if classify(path) == OTHER:
        return ConsumerVerdict(status=CLEARED_OTHER)
    filename = PurePosixPath(path.strip()).name
    return consumer_search(filename, repo_root=repo_root, gh_runner=gh_runner)


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

    A ``filename`` that begins with ``-`` is rejected BEFORE any runner call
    (``fail-closed``): it cannot be a legitimate basename and could otherwise
    be parsed by gh as an option (argv-option injection). The search argv also
    carries the ``--`` end-of-options sentinel as belt-and-braces.
    """
    runner = gh_runner or _default_gh_runner
    if filename.startswith("-"):
        return ConsumerVerdict(
            status=FAIL_CLOSED,
            reason=f"refusing option-like filename: {filename!r}",
        )
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
    the response has no usable ``owner.login``, or when the login is not a
    well-formed GitHub org name (``_ORG_LOGIN_PATTERN``) — an org we cannot
    name OR cannot validate is a scope we cannot attest to, so it must fail
    closed rather than search a blank, guessed, or hostile scope (a login
    carrying whitespace / newlines / injected text never reaches an argv).
    """
    out = runner(["gh", "repo", "view", repo_root, "--json", "owner"])
    parsed = json.loads(out) if out.strip() else {}
    owner = parsed.get("owner") if isinstance(parsed, dict) else None
    login = owner.get("login") if isinstance(owner, dict) else None
    if not isinstance(login, str) or not _ORG_LOGIN_PATTERN.fullmatch(login):
        raise subprocess.CalledProcessError(
            1, ["gh", "repo", "view"], f"unusable owner.login: {login!r}"
        )
    return login


def _search_code(runner: GhRunner, filename: str, org: str) -> list[_CodeSearchHit]:
    """Return the org-wide code-search hit records for ``filename``.

    ``gh search code`` supports ``--json repository,path`` (verified against
    the installed gh); the default output is JSON when ``--json`` is given,
    so we parse it directly. A non-list parse is treated as zero hits; each
    list element is trusted to be a (possibly partial) ``_CodeSearchHit`` and
    defensively destructured by ``_name_consumer``.

    The ``--`` end-of-options sentinel precedes the ``filename`` positional so
    a value gh would otherwise read as a flag is forced to be the search term
    (argv-option-injection defense; the caller also rejects ``-``-prefixed
    filenames up front).
    """
    out = runner(
        [
            "gh",
            "search",
            "code",
            "--owner",
            org,
            "--json",
            "repository,path",
            "--",
            filename,
        ]
    )
    parsed = json.loads(out) if out.strip() else []
    return parsed if isinstance(parsed, list) else []


def _name_consumer(hit: _CodeSearchHit) -> str:
    """Name one consumer ``"<repo>:<path>"`` from a gh search-code hit.

    ``repository`` is the ``{nameWithOwner: ...}`` shape gh returns; falls
    back to a literal placeholder for either missing half so a malformed hit
    still produces a non-empty, operator-legible consumer line (a hit is a
    hit — never silently dropped). Destructured defensively because the parsed
    JSON's runtime shape is only as trustworthy as gh's output.
    """
    repository = hit.get("repository") if isinstance(hit, dict) else None
    repo_name = repository.get("nameWithOwner") if isinstance(repository, dict) else None
    path = hit.get("path") if isinstance(hit, dict) else None
    return f"{repo_name or '<unknown-repo>'}:{path or '<unknown-path>'}"


def _build_evidence(filename: str, org: str, searched_at: str, hit_count: int) -> SearchEvidence:
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
