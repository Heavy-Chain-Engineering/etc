#!/usr/bin/env python3
"""reject_feature_mv.py — Relocate a rejected /spec feature dir from
``features/active/`` to ``.etc_sdlc/rejections/``.

The /spec rejection flow (Phase 2.75 ``rejected`` classification) moves the
feature directory out of the AI-dispatch surface. The symmetric
active→shipped move has had a helper since F022
(``scripts/active_to_shipped_mv.py``); rejection never got one — the skill
carried an inline transcribe-and-run snippet instead, which drifted: it
built the target as ``f"F{nnn:03d}-{slug}"`` with ``nnn`` undefined (the
allocator has issued date-form IDs since 2026-05-22), so a faithful agent
crashed mid-rejection (audit init 7). The target is simply the source
directory's NAME — correct for both ID grammars, no format string needed.

Same three-branch failure shape as active_to_shipped_mv.py:

    (a) git-tracked source → ``git mv`` succeeds, rename canonical in the
        index.
    (b) gitignored source (no tracked files) → ``shutil.move`` fallback;
        a stderr line announces the missing-from-index nature.
    (c) destination already exists → non-zero exit, stderr names both
        paths.
    (d) source missing / other git failure → non-zero exit, git stderr
        surfaced verbatim.

Security: ``subprocess.run`` is invoked argv-style (list, not string), so
operator-controlled feature slugs cannot inject shell metacharacters.

Usage:
    reject_feature_mv.py --src .etc_sdlc/features/active/F-2026-06-09-foo \
        [--rejections-root .etc_sdlc/rejections] [--cwd <repo>]

Public API:
    move_to_rejections(src, rejections_root, cwd, stderr) -> int
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path
from typing import TextIO


def _git_mv(src: Path, dst: Path, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "mv", str(src), str(dst)],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=30,
    )


def move_to_rejections(
    src: Path,
    rejections_root: Path,
    cwd: Path,
    stderr: TextIO = sys.stderr,
) -> int:
    """Move ``src`` to ``rejections_root/<src.name>``. Returns an exit code."""
    if not src.is_dir():
        stderr.write(f"reject_feature_mv: source is not a directory: {src}\n")
        return 1

    rejections_root.mkdir(parents=True, exist_ok=True)
    target = rejections_root / src.name
    if target.exists():
        stderr.write(
            f"reject_feature_mv: target already exists: {target}\n"
            f"(source: {src}) — remediate manually; refusing to overwrite.\n"
        )
        return 1

    result = _git_mv(src, target, cwd)
    if result.returncode == 0:
        return 0

    # gitignored / untracked source: git mv refuses ("source directory is
    # empty"). Fall back to a filesystem move and say so — the move is
    # honest about being invisible to the index.
    if "source directory is empty" in result.stderr:
        try:
            shutil.move(str(src), str(target))
        except (OSError, shutil.Error) as exc:
            stderr.write(
                f"reject_feature_mv: filesystem fallback failed: "
                f"{src} -> {target}\n{exc}\n"
            )
            return 1
        stderr.write(
            f"reject_feature_mv: moved via filesystem fallback (source had no "
            f"git-tracked files; the rename is not in the git index): "
            f"{src} -> {target}\n"
        )
        return 0

    stderr.write(
        f"reject_feature_mv: git mv failed: {src} -> {target}\n"
        f"git stderr: {result.stderr}"
    )
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Move a rejected feature dir to .etc_sdlc/rejections/."
    )
    parser.add_argument("--src", required=True, type=Path)
    parser.add_argument(
        "--rejections-root",
        type=Path,
        default=Path(".etc_sdlc/rejections"),
    )
    parser.add_argument("--cwd", type=Path, default=Path("."))
    args = parser.parse_args(argv)
    return move_to_rejections(args.src, args.rejections_root, args.cwd)


if __name__ == "__main__":
    sys.exit(main())
