#!/usr/bin/env python3
"""Journey ID allocator (F017).

POSIX-atomically allocates the next J<NNN> identifier under a target root
(typically `docs/mvp/journeys/`). Mirrors the contract of feature_id.py.

Usage:
  journey_id.py allocate-next <root> <slug>
  journey_id.py list <root>

Stdout shape (allocate-next): "<journey_id> <full_path>"
  e.g. "J007 docs/mvp/journeys/J-007-contract-execution"

Exit codes:
  0 = success
  1 = usage error / IO error
  2 = collision (concurrent allocator beat us; retry)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

JOURNEY_DIR_PATTERN = re.compile(r"^J-?(\d+)(?:-.+)?$")


def slugify(text: str) -> str:
    """Lowercase, hyphens for spaces, strip non-alphanumeric. Mirror
    feature_id.slugify so callers can rely on the same input → output."""
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text or "untitled"


def parse_existing_ids(root: Path) -> list[int]:
    """Return all J-NNN integers already allocated under root (sorted)."""
    if not root.is_dir():
        return []
    ids: list[int] = []
    for entry in root.iterdir():
        # Match both J-NNN-<slug>/ directories AND J-NNN-<slug>.md files
        name = entry.stem if entry.is_file() else entry.name
        match = JOURNEY_DIR_PATTERN.match(name)
        if match:
            ids.append(int(match.group(1)))
    return sorted(ids)


def next_id(existing: list[int]) -> int:
    return (max(existing) + 1) if existing else 1


def format_id(n: int) -> str:
    """J-NNN with 3-digit zero-pad. Aligns with F<NNN> convention but
    keeps the hyphen for readability in prose ("J-007")."""
    return f"J-{n:03d}"


def allocate_next(root: Path, slug: str) -> tuple[str, Path]:
    """POSIX-atomically allocate the next J-NNN. Returns (journey_id, path).

    Uses Path.mkdir(exist_ok=False) as the atomic primitive: if a concurrent
    allocator created the same directory between our scan and mkdir, mkdir
    raises FileExistsError → we retry up to MAX_ATTEMPTS times.
    """
    MAX_ATTEMPTS = 10
    root.mkdir(parents=True, exist_ok=True)
    for _ in range(MAX_ATTEMPTS):
        existing = parse_existing_ids(root)
        n = next_id(existing)
        journey_id = format_id(n)
        slug_clean = slugify(slug)
        target = root / f"{journey_id}-{slug_clean}"
        try:
            target.mkdir(exist_ok=False)
            return journey_id, target
        except FileExistsError:
            # Concurrent allocator beat us; try the next number.
            continue
    msg = f"journey_id: exhausted {MAX_ATTEMPTS} allocation attempts under {root}"
    raise RuntimeError(msg)


def list_journeys(root: Path) -> None:
    """Print every J-NNN-<slug> entry under root, sorted by ID."""
    if not root.is_dir():
        return
    entries: list[tuple[int, str]] = []
    for entry in root.iterdir():
        name = entry.stem if entry.is_file() else entry.name
        match = JOURNEY_DIR_PATTERN.match(name)
        if match:
            entries.append((int(match.group(1)), str(entry)))
    for _, path in sorted(entries):
        print(path)


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        sys.stderr.write(__doc__ or "")
        return 1

    cmd = argv[1]
    if cmd == "allocate-next":
        if len(argv) != 4:
            sys.stderr.write("Usage: journey_id.py allocate-next <root> <slug>\n")
            return 1
        root = Path(argv[2])
        slug = argv[3]
        try:
            journey_id, path = allocate_next(root, slug)
        except RuntimeError as e:
            sys.stderr.write(f"ERROR: {e}\n")
            return 2
        print(f"{journey_id} {path}")
        return 0

    if cmd == "list":
        if len(argv) != 3:
            sys.stderr.write("Usage: journey_id.py list <root>\n")
            return 1
        list_journeys(Path(argv[2]))
        return 0

    sys.stderr.write(f"ERROR: unknown command: {cmd}\n")
    sys.stderr.write(__doc__ or "")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
