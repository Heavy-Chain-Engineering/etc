#!/usr/bin/env python3
"""Janitor write-boundary veto (F-2026-05-29 / BR-005, defense-in-depth).

Scans a unified git diff for the set of changed file paths and matches them
against the machine-parseable write-boundary standard. Aborts (exit 2) if any
changed path matches a forbidden glob (AC-004), escapes the repo root, or the
diff touches more files than the published ceiling (AC-005). The forbidden-glob
list AND the integer ceiling are read FROM the standard file on every run; this
script holds no hardcoded copy (AC-013) and fails closed (exit 1) on any
absent/empty/malformed block.

Exit codes:
  0 = clean (no forbidden path, within ceiling)
  1 = usage error, IO error, or malformed/absent boundary block (fail-closed)
  2 = violation (orchestrator aborts the run, opens no PR)

Usage:
  janitor_boundary_check.py --diff <file|-> --boundary <standard-path>

stdout (JSON):
  {"verdict": "clean"}
  {"verdict": "violation", "rule": "<rule-name>", "paths": [...]}
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path, PurePosixPath

FORBIDDEN_INFO_STRING = "janitor-forbidden-globs"
CEILING_INFO_STRING = "janitor-ceiling"
CEILING_KEY = "max_files"

# `diff --git a/<path> b/<path>` — the authoritative source of the changed path,
# robust to added/deleted files where one side is /dev/null.
_DIFF_GIT_HEADER = re.compile(r"^diff --git a/(.+?) b/(.+)$")


class BoundaryError(Exception):
    """A fail-closed condition: the standard is unparseable or absent."""


def extract_fenced_block(text: str, info_string: str) -> list[str] | None:
    """Return the lines of the single fenced block whose info string matches.

    Returns None if no such block exists. Raises BoundaryError if more than one
    block carries the same info string (ambiguous → fail-closed).
    """
    blocks: list[list[str]] = []
    current: list[str] | None = None
    for line in text.splitlines():
        stripped = line.strip()
        if current is None:
            if stripped == f"```{info_string}":
                current = []
            continue
        if stripped == "```":
            blocks.append(current)
            current = None
            continue
        current.append(line)
    if len(blocks) > 1:
        raise BoundaryError(f"multiple '{info_string}' blocks; ambiguous")
    return blocks[0] if blocks else None


def parse_forbidden_globs(text: str) -> list[tuple[str, str]]:
    """Parse the forbidden-glob block into (rule_name, glob) pairs.

    Per the standard's parsing contract: drop blank lines and comments, split
    each remaining line on its first run of whitespace. Fail closed if the block
    is absent, empty, or any line is not `<rule><ws><glob>`.
    """
    lines = extract_fenced_block(text, FORBIDDEN_INFO_STRING)
    if lines is None:
        raise BoundaryError(f"'{FORBIDDEN_INFO_STRING}' block absent")
    rules: list[tuple[str, str]] = []
    for line in lines:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        parts = line.split(maxsplit=1)
        if len(parts) != 2 or not parts[1].strip():
            raise BoundaryError(f"malformed forbidden-glob line: {line!r}")
        rules.append((parts[0], parts[1].strip()))
    if not rules:
        raise BoundaryError(f"'{FORBIDDEN_INFO_STRING}' block empty")
    return rules


def parse_ceiling(text: str) -> int:
    """Parse the ceiling block into the integer `max_files` value.

    Fail closed if the block is absent, holds a non-integer, lacks the
    `max_files` key, or carries any other key.
    """
    lines = extract_fenced_block(text, CEILING_INFO_STRING)
    if lines is None:
        raise BoundaryError(f"'{CEILING_INFO_STRING}' block absent")
    entries = [line for line in lines if line.strip() and not line.lstrip().startswith("#")]
    if len(entries) != 1:
        raise BoundaryError("ceiling block must hold exactly one entry")
    key, sep, value = entries[0].partition("=")
    if not sep or key.strip() != CEILING_KEY:
        raise BoundaryError(f"ceiling block must define '{CEILING_KEY} = <int>'")
    try:
        return int(value.strip())
    except ValueError as exc:
        raise BoundaryError(f"ceiling value not an integer: {value.strip()!r}") from exc


def extract_changed_paths(diff_text: str) -> list[str]:
    """Extract the ordered, de-duplicated set of changed paths from a git diff.

    Reads the post-image path from each `diff --git a/<x> b/<y>` header (the
    `b/` side), which is present for adds, deletes, renames, and edits alike.
    """
    seen: dict[str, None] = {}
    for line in diff_text.splitlines():
        match = _DIFF_GIT_HEADER.match(line)
        if match is None:
            continue
        post_image = match.group(2)
        seen.setdefault(post_image, None)
    return list(seen)


def canonicalize(path: str, root: Path) -> PurePosixPath | None:
    """Resolve `path` under `root`; return the root-relative POSIX path.

    Returns None if the resolved path escapes `root` (`..`/symlink escape), so
    the caller can flag it as a path-escape violation. Pure `.`-segment
    normalization (e.g. `spec/./foo.md`) collapses to a normal in-root path.
    """
    resolved = (root / path).resolve()
    root_resolved = root.resolve()
    try:
        relative = resolved.relative_to(root_resolved)
    except ValueError:
        return None
    return PurePosixPath(relative.as_posix())


def matches_glob(candidate: PurePosixPath, glob: str) -> bool:
    """Match a root-relative POSIX path against a glob where `**` spans any depth.

    Translates the glob to a regex so `**` means zero-or-more path segments and
    `*` means any run within a single segment.
    """
    regex = _glob_to_regex(glob)
    return regex.match(str(candidate)) is not None


def _glob_to_regex(glob: str) -> re.Pattern[str]:
    out: list[str] = ["^"]
    index = 0
    length = len(glob)
    while index < length:
        char = glob[index]
        if char == "*" and index + 1 < length and glob[index + 1] == "*":
            # `**/` or `**` → zero or more path segments.
            if index + 2 < length and glob[index + 2] == "/":
                out.append("(?:[^/]+/)*")
                index += 3
            else:
                out.append(".*")
                index += 2
            continue
        if char == "*":
            out.append("[^/]*")
            index += 1
            continue
        out.append(re.escape(char))
        index += 1
    out.append("$")
    return re.compile("".join(out))


def evaluate(
    diff_text: str, rules: list[tuple[str, str]], ceiling: int, root: Path
) -> dict[str, object]:
    """Return the verdict dict for a diff against the parsed boundary."""
    raw_paths = extract_changed_paths(diff_text)

    escaped = [p for p in raw_paths if canonicalize(p, root) is None]
    if escaped:
        return {"verdict": "violation", "rule": "path-escape", "paths": escaped}

    for rule_name, glob in rules:
        hits = [
            raw
            for raw in raw_paths
            if matches_glob(_require(canonicalize(raw, root)), glob)
        ]
        if hits:
            return {"verdict": "violation", "rule": rule_name, "paths": hits}

    if len(raw_paths) > ceiling:
        return {
            "verdict": "violation",
            "rule": "file-count-ceiling",
            "paths": raw_paths,
        }

    return {"verdict": "clean"}


def _require(value: PurePosixPath | None) -> PurePosixPath:
    """Narrow a known-non-None canonical path (escapes are handled upstream)."""
    assert value is not None
    return value


def read_diff(source: str) -> str:
    """Read the diff text from a file path or stdin (`-`)."""
    if source == "-":
        return sys.stdin.read()
    return Path(source).read_text(encoding="utf-8")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="janitor_boundary_check.py",
        description="Mechanical janitor write-boundary veto.",
    )
    parser.add_argument("--diff", required=True, help="unified diff file, or '-' for stdin")
    parser.add_argument("--boundary", required=True, help="path to the boundary standard")
    try:
        args = parser.parse_args(argv[1:])
    except SystemExit:
        return 1

    try:
        diff_text = read_diff(args.diff)
        standard_text = Path(args.boundary).read_text(encoding="utf-8")
    except OSError as exc:
        sys.stderr.write(f"ERROR: {exc}\n")
        return 1

    try:
        rules = parse_forbidden_globs(standard_text)
        ceiling = parse_ceiling(standard_text)
    except BoundaryError as exc:
        sys.stderr.write(f"ERROR: boundary standard unparseable (fail-closed): {exc}\n")
        return 1

    root = Path.cwd()
    verdict = evaluate(diff_text, rules, ceiling, root)
    print(json.dumps(verdict))
    return 2 if verdict["verdict"] == "violation" else 0


if __name__ == "__main__":  # pragma: no cover - thin CLI entrypoint
    sys.exit(main(sys.argv))
