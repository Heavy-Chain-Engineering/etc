#!/usr/bin/env python3
"""active_to_shipped_mv.py — Relocate a /build feature dir from
``features/active/`` to ``features/shipped/`` at terminal-phase close.

Implements F009 BR-005 (active->shipped transition) and the three-branch
failure shape pinned by tests/test_build_step_7c_active_to_shipped.py:

    (a) git-tracked source -> ``git mv`` succeeds, rename canonical in
        the index, ``git log --follow`` traces the directory history.
    (b) gitignored source (no tracked files in the source dir) ->
        ``shutil.move`` fallback fires. The fallback is filesystem-only;
        a stderr line announces the missing-from-index nature so the
        audit-trail observation is honest.
    (c) destination already exists -> non-zero exit; git's stderr is
        surfaced verbatim so the operator can remediate (preserves
        edge-case-6 from skills/build/SKILL.md).
    (d) source missing / any other git mv failure -> non-zero exit; git's
        stderr is surfaced verbatim.

Background: ``.etc_sdlc/`` is gitignored in client projects (and in etc
itself, gated on the ``incidents/`` and ``4.7-audit/`` whitelist). When
the source directory has no tracked files, ``git mv`` fails with::

    fatal: source directory is empty, source=…, destination=…

This bug fired on F021's build (2026-05-20) and again on F022's build
(2026-05-21). Pre-fix, the conductor fell back to plain ``mv`` manually
each time. This helper formalizes the fallback so the skill body
documents real behavior.

Security: ``subprocess.run`` is invoked argv-style (list, not string), so
operator-controlled feature slugs cannot inject shell metacharacters.

Public API:
    move_active_to_shipped(src, dst, cwd, stderr) -> int
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path
from typing import TextIO

# Exact substring git emits when the source directory has zero tracked
# files. Detecting this exact substring is what distinguishes the
# gitignored-source case from a genuine destination-collision or
# missing-source failure.
_GIT_MV_EMPTY_SOURCE_MARKER = "source directory is empty"


def move_active_to_shipped(
    *,
    src: Path,
    dst: Path,
    cwd: Path,
    stderr: TextIO,
) -> int:
    """Move ``src`` -> ``dst`` for the /build terminal-phase close.

    Tries ``git mv`` first (branch a). On the specific "source directory
    is empty" failure, falls back to ``shutil.move`` (branch b) and writes
    an audit-trail line to ``stderr``. On any other ``git mv`` failure
    (branches c/d), surfaces git's stderr verbatim and returns non-zero.

    Args:
        src: Absolute path to the feature dir under
            ``<repo>/.etc_sdlc/features/active/F<NNN>-<slug>/``.
        dst: Absolute path to the target under
            ``<repo>/.etc_sdlc/features/shipped/F<NNN>-<slug>/``.
        cwd: Repo root the spawned ``git mv`` should run inside.
        stderr: Stream the helper writes diagnostic lines to (real
            ``sys.stderr`` in production, ``io.StringIO`` in tests).

    Returns:
        ``0`` on success (either branch a or branch b). Non-zero on any
        failure (branches c/d). Mirrors ``int`` exit-code convention so
        the helper composes with subprocess invocation patterns elsewhere
        in scripts/.
    """
    git_mv_cmd = [
        "git",
        "mv",
        str(src),
        str(dst),
    ]
    result = subprocess.run(
        git_mv_cmd,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode == 0:
        # Branch (a): canonical git-tracked rename.
        return 0

    if _GIT_MV_EMPTY_SOURCE_MARKER in result.stderr:
        # Branch (b): the gitignored-source case. .etc_sdlc/ is gitignored
        # in this repo so the source dir has no tracked files. git mv
        # refuses; fall back to shutil.move so the audit-trail directory
        # transition still happens.
        if not src.exists():
            # Defensive: git mv reported "source directory is empty" but
            # the source path itself is missing on disk. shutil.move
            # would raise FileNotFoundError; surface git's stderr instead.
            stderr.write(result.stderr)
            return result.returncode if result.returncode != 0 else 1
        shutil.move(str(src), str(dst))
        # Audit-trail honesty: the rename is filesystem-only, NOT in
        # git's index. Operators reading the log must know.
        stderr.write(
            f"[build] {src} -> {dst} "
            "(filesystem-only; .etc_sdlc/ is gitignored, "
            "git mv refused on empty-source)\n"
        )
        return 0

    # Branches (c) and (d): destination exists, source missing entirely,
    # or any other git mv failure. Preserve edge-case-6 behavior: surface
    # git's stderr verbatim and return non-zero so /build aborts cleanly.
    stderr.write(result.stderr)
    return result.returncode if result.returncode != 0 else 1


def _main(argv: list[str]) -> int:
    """CLI entry point. Argv-style invocation only.

    Usage:
        active_to_shipped_mv.py --src <path> --dst <path> [--cwd <path>]
    """
    parser = argparse.ArgumentParser(
        description=(
            "Move a feature dir from features/active/ to features/shipped/. "
            "Tries git mv first; falls back to shutil.move when "
            ".etc_sdlc/ is gitignored."
        ),
    )
    parser.add_argument("--src", required=True, type=Path)
    parser.add_argument("--dst", required=True, type=Path)
    parser.add_argument(
        "--cwd",
        type=Path,
        default=Path.cwd(),
        help="Repo root the spawned git mv should run inside.",
    )
    args = parser.parse_args(argv)
    return move_active_to_shipped(
        src=args.src,
        dst=args.dst,
        cwd=args.cwd,
        stderr=sys.stderr,
    )


if __name__ == "__main__":  # pragma: no cover
    sys.exit(_main(sys.argv[1:]))
