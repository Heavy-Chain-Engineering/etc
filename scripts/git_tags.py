#!/usr/bin/env python3
"""git_tags.py — Append-only git tag helper for the etc/feature/* namespace.

Implements BR-007 (canonical tag points), BR-008 (append-only — no delete/
retag/force-update API exists by design), AC-007 through AC-010, plus edge
cases 1 (non-git directory) and 2 (no-HEAD repo) from the metrics-and-
release-notes spec.

Public API:
    write_tag(name, ref="HEAD") -> bool
    list_etc_tags() -> list[tuple[str, str, str]]

Both functions degrade gracefully on non-git directories and repos with no
HEAD commit by logging a warning and returning a benign value (False / [])
rather than raising.
"""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys

LOGGER = logging.getLogger(__name__)

ETC_TAG_PREFIX = "refs/tags/etc/"
# Prefer taggerdate (set by `git tag -a` at tag-creation time) over the commit's
# committerdate. This is what makes per-phase timing measurable when /build
# squashes multiple waves to a single commit: each annotated phase tag carries
# its own creation timestamp, independent of the commit it points at.
# Lightweight tags (legacy, pre-progressive-phase-timing) have an empty
# taggerdate field; we fall back to committerdate so old features still report.
_FOR_EACH_REF_FORMAT = (
    "%(refname:short) %(objectname) "
    "%(if)%(taggerdate)%(then)%(taggerdate:iso8601)"
    "%(else)%(committerdate:iso8601)%(end)"
)


def _has_head_commit() -> bool:
    """Return True iff the current working directory is inside a git repo with HEAD."""
    try:
        subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False
    return True


def write_tag(name: str, ref: str = "HEAD") -> bool:
    """Create a git tag pointing at `ref` (default HEAD).

    Degrades gracefully:
      - If cwd is not a git repository, log a warning and return False.
      - If the repository has no HEAD commit, log a warning and return False.
      - If the underlying `git tag` invocation fails for any other reason,
        log a warning and return False.

    Returns True on successful tag creation. Never raises on these expected
    failure modes; unexpected exceptions (e.g. permission errors on the
    filesystem) propagate.

    Note: this helper is intentionally append-only. There is no companion
    delete/retag/force-update function; tag history is the audit trail
    (BR-008, AC-010).

    Tags are created ANNOTATED (`git tag -a`) so each carries its own
    creation timestamp via `taggerdate`. This is what makes per-phase
    /metrics deltas measurable when /build squashes multiple waves to one
    commit: phase-N/start and phase-N/done both point at the same commit
    but their taggerdates differ by the wave's wall-clock duration. The
    annotation message records the tag name verbatim so it shows up in
    `git log --decorate` output without an opaque "tag: foo" prefix.
    """
    if not _has_head_commit():
        LOGGER.warning(
            "Cannot write tag %r: not a git repository or repo has no HEAD commit.",
            name,
        )
        return False

    try:
        subprocess.run(
            ["git", "tag", "-a", name, "-m", name, ref],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        LOGGER.warning(
            "git tag %r failed (exit %d): %s",
            name,
            exc.returncode,
            exc.stderr.strip() if exc.stderr else "",
        )
        return False
    return True


def list_etc_tags() -> list[tuple[str, str, str]]:
    """Return (tag_name, commit_sha, iso8601_date) triples for every etc/* tag.

    Uses `git for-each-ref refs/tags/etc/` so non-etc tags (release versions,
    user-applied marks) are filtered out at the git level rather than in
    Python. Returns an empty list if the directory is not a git repo, the
    repo has no etc tags, or the underlying git invocation fails.
    """
    try:
        completed = subprocess.run(
            [
                "git",
                "for-each-ref",
                f"--format={_FOR_EACH_REF_FORMAT}",
                ETC_TAG_PREFIX,
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        LOGGER.warning("Cannot list etc tags: %s", exc)
        return []

    triples: list[tuple[str, str, str]] = []
    for line in completed.stdout.splitlines():
        if not line.strip():
            continue
        # Format: "<refname> <sha> <iso8601-with-spaces>"
        # Split into 3 parts: tag, sha, then everything else as the date.
        parts = line.split(" ", 2)
        if len(parts) != 3:
            LOGGER.warning("Skipping malformed for-each-ref line: %r", line)
            continue
        name, sha, date = parts
        triples.append((name, sha, date))
    return triples


# ── CLI ─────────────────────────────────────────────────────────────────
#
# Skills (/spec, /build, /hotfix) invoke git_tags.py via absolute path so
# they work from any working directory — `from scripts.git_tags import ...`
# only resolves inside this checkout. The CLI mirrors the public API:
#
#     python3 .../scripts/git_tags.py write-tag <name> [--ref REF]
#     python3 .../scripts/git_tags.py list-etc-tags
#
# Exit codes for `write-tag`:
#     0 — tag created
#     1 — graceful-degrade failure (non-git dir, no-HEAD repo, git tag rc≠0)
#     2 — hard error (unexpected exception)
# `list-etc-tags` always exits 0; empty list yields no output.


def _cmd_write_tag(args: argparse.Namespace) -> int:
    """Run `write_tag` and translate its bool return into a process exit code."""
    try:
        ok = write_tag(args.name, args.ref)
    except Exception as exc:  # pragma: no cover — hard error path
        print(f"error: write_tag raised: {exc}", file=sys.stderr)
        return 2
    if not ok:
        print(
            f"error: failed to write tag {args.name!r} "
            "(not a git repo, no HEAD commit, or git tag failed)",
            file=sys.stderr,
        )
        return 1
    return 0


def _cmd_list_etc_tags(_args: argparse.Namespace) -> int:
    """Print each etc/* tag as `<name>\\t<sha>\\t<date>`."""
    for name, sha, date in list_etc_tags():
        print(f"{name}\t{sha}\t{date}")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="git_tags.py",
        description="Append-only git tag helper for the etc/feature/* namespace.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_write = sub.add_parser(
        "write-tag",
        help="Create a git tag pointing at REF (default HEAD).",
    )
    p_write.add_argument("name", help="Tag name, e.g. etc/feature/F001/spec")
    p_write.add_argument(
        "--ref",
        default="HEAD",
        help="Git ref the tag should point at (default: HEAD)",
    )
    p_write.set_defaults(func=_cmd_write_tag)

    p_list = sub.add_parser(
        "list-etc-tags",
        help="List etc/* tags as tab-separated <name>\\t<sha>\\t<date> lines.",
    )
    p_list.set_defaults(func=_cmd_list_etc_tags)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
