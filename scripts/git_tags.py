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

import logging
import subprocess

LOGGER = logging.getLogger(__name__)

ETC_TAG_PREFIX = "refs/tags/etc/"
_FOR_EACH_REF_FORMAT = "%(refname:short) %(objectname) %(committerdate:iso8601)"


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
    """
    if not _has_head_commit():
        LOGGER.warning(
            "Cannot write tag %r: not a git repository or repo has no HEAD commit.",
            name,
        )
        return False

    try:
        subprocess.run(
            ["git", "tag", name, ref],
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
