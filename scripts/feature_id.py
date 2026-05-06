"""feature_id.py — Atomic F<NNN> feature-ID allocator and slug helper.

Allocates per-project feature IDs of the form ``F<NNN>`` (3-digit zero-padded)
using POSIX-atomic ``os.mkdir`` with EEXIST retry. This is the canonical
race-free allocation pattern (see ``.etc_sdlc/features/metrics-and-release-
notes/gray-areas.md`` GA-006: POSIX.1 mkdir(2) atomicity).

Public API:

- ``allocate_next(features_dir, slug) -> (feature_id, feature_path)``
- ``resolve_feature_path(feature_id, etc_sdlc_root) -> Path | None``
- ``slugify(title) -> str``
- ``FeatureIdExhaustedError`` — raised when the project hits the v1 F999 ceiling.

Behavior is forward-only: existing slug-only directories (grandfathered per
GA-002) are ignored when computing the maximum F-ID. ID gaps are acceptable;
ID reuse is not (BR-002).

F009 layout (forward-only):
    .etc_sdlc/
        features/
            F001-…/                   # legacy flat (F001-F008 + F006)
            active/F<NNN>-…/          # in-flight work (new allocations)
            shipped/F<NNN>-…/         # done audit-frozen work
        rejections/F<NNN>-…/          # /spec three-state classifier rejects
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

# ── Module constants ────────────────────────────────────────────────────

#: Regex matching a feature directory name. Group 1 captures the integer ID.
_FEATURE_DIR_PATTERN = re.compile(r"^F(\d{3})(?:-.*)?$")

#: Maximum feature ID supported by the v1 schema (3-digit zero-padded).
#: Hitting this ceiling raises FeatureIdExhaustedError rather than overflowing
#: silently. Upgrade to 4-digit IDs is deferred to a future PRD.
_MAX_FEATURE_ID = 999

#: Length cap for slugs. Mirrors scripts/tasks.py::_slugify_title (80 chars).
_SLUG_MAX_LEN = 80

#: Fallback slug when the input title contains no alphanumeric characters.
_SLUG_FALLBACK = "task"

#: Subdirectory under ``features/`` for in-flight feature work (F009 BR-002).
_ACTIVE_SUBDIR = "active"

#: Subdirectory under ``features/`` for done audit-frozen feature work.
_SHIPPED_SUBDIR = "shipped"

#: Sibling directory of ``features/`` under ``.etc_sdlc/`` for rejection
#: trails written by /spec's three-state classifier.
_REJECTIONS_DIR = "rejections"


# ── Errors ──────────────────────────────────────────────────────────────


class FeatureIdExhaustedError(RuntimeError):
    """Raised when the project has consumed every available F<NNN> slot."""


# ── Public API ──────────────────────────────────────────────────────────


def slugify(title: str) -> str:
    """Convert a free-form title into a kebab-case feature-directory slug.

    Mirrors ``scripts/tasks.py::_slugify_title`` for cross-tool parity:

    1. Lowercase.
    2. Replace runs of non-alphanumeric characters with a single hyphen.
    3. Strip leading/trailing hyphens.
    4. Truncate to ``_SLUG_MAX_LEN`` characters; re-strip trailing hyphens
       so a truncation never leaves a dangling separator.
    5. Fall back to ``_SLUG_FALLBACK`` if the result would be empty.
    """
    lowered = title.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
    if not slug:
        return _SLUG_FALLBACK
    if len(slug) > _SLUG_MAX_LEN:
        slug = slug[:_SLUG_MAX_LEN].rstrip("-") or _SLUG_FALLBACK
    return slug


def allocate_next(features_dir: Path, slug: str) -> tuple[str, Path]:
    """Allocate the next available F<NNN> feature directory atomically.

    Args:
        features_dir: Project-scoped features root (e.g. ``.etc_sdlc/features``).
            The ``active/`` subdirectory under this root is created if absent
            (F009 BR-002); new feature dirs land at
            ``<features_dir>/active/F<NNN>-<slug>/``.
        slug: Already-slugified suffix appended to the F-ID directory name.

    Returns:
        ``(feature_id, feature_path)`` where ``feature_id`` is ``"F<NNN>"`` and
        ``feature_path`` is the freshly-created directory under ``active/``.

    Raises:
        FeatureIdExhaustedError: When all F001–F999 slots are consumed.

    Concurrency:
        Uses ``os.mkdir`` which is POSIX-atomic for the F<NNN>-<slug> child.
        On ``FileExistsError`` the function re-reads the maximum existing
        F-ID and retries at +1, so two racing callers receive distinct IDs
        (BR-003 / AC-002).

    Layout (F009 BR-002):
        Max-ID scan rglobs across ``features_dir``'s parent (``.etc_sdlc/``)
        so legacy flat F001-F008 plus ``active/``, ``shipped/``, and
        ``rejections/`` all contribute. New dirs land under ``active/`` only.
    """
    active_dir = features_dir / _ACTIVE_SUBDIR
    active_dir.mkdir(parents=True, exist_ok=True)

    while True:
        next_id = _scan_max_feature_id(features_dir) + 1
        if next_id > _MAX_FEATURE_ID:
            raise FeatureIdExhaustedError(
                f"Project has reached the v1 feature ID ceiling "
                f"({_MAX_FEATURE_ID})"
            )

        feature_id_str = f"F{next_id:03d}"
        candidate = active_dir / f"{feature_id_str}-{slug}"

        try:
            os.mkdir(candidate)
        except FileExistsError:
            # Lost the race — another writer won this slot. Re-scan and retry.
            continue

        return feature_id_str, candidate


def resolve_feature_path(feature_id: str, etc_sdlc_root: Path) -> Path | None:
    """Return the directory for ``feature_id`` under ``etc_sdlc_root``, or None.

    Checks four locations in priority order (F009 BR-003):

    1. ``<etc_sdlc_root>/features/F<NNN>-*/``         (legacy flat — F001-F008 + F006)
    2. ``<etc_sdlc_root>/features/active/F<NNN>-*/``  (in-flight work)
    3. ``<etc_sdlc_root>/features/shipped/F<NNN>-*/`` (done audit-frozen work)
    4. ``<etc_sdlc_root>/rejections/F<NNN>-*/``       (rejection trails)

    Args:
        feature_id: F-ID without slug (e.g. ``"F042"``). MUST match
            ``_FEATURE_DIR_PATTERN``; otherwise this function returns ``None``
            without touching the filesystem (path-traversal guard per F009
            Security Considerations item 1).
        etc_sdlc_root: Path to the project's ``.etc_sdlc/`` directory.

    Returns:
        The first matching directory as a resolved ``Path``, or ``None`` if
        no F<NNN>-* directory exists at any of the four locations.

    Read-only contract:
        Does not open, read contents of, or modify any file.
    """
    if not _FEATURE_DIR_PATTERN.match(feature_id):
        return None

    features_root = etc_sdlc_root / "features"
    search_locations = (
        features_root,
        features_root / _ACTIVE_SUBDIR,
        features_root / _SHIPPED_SUBDIR,
        etc_sdlc_root / _REJECTIONS_DIR,
    )
    glob_pattern = f"{feature_id}-*"

    for location in search_locations:
        if not location.is_dir():
            continue
        for match in location.glob(glob_pattern):
            if match.is_dir():
                return match.resolve()

    return None


# ── Internals ───────────────────────────────────────────────────────────


def _scan_max_feature_id(features_dir: Path) -> int:
    """Return the highest F<NNN> id present under ``.etc_sdlc/``, or 0.

    F009 BR-001 update: scan rglobs across the ``.etc_sdlc/`` root (derived
    from ``features_dir.parent`` when ``features_dir.name == "features"``)
    so the legacy flat path, ``features/active/``, ``features/shipped/``,
    and ``rejections/`` all contribute to the max-id calculation.

    Non-feature directories (legacy slug-only entries grandfathered per
    GA-002, plus any unrelated content) are ignored.

    Args:
        features_dir: Project-scoped features root passed by ``allocate_next``.
            Backward-compat: when this path's basename is ``features``, the
            ``.etc_sdlc/`` root is derived as ``features_dir.parent``;
            otherwise the path itself is treated as the scan root. If the
            scan root does not exist on disk, the function returns ``0``.
    """
    scan_root = (
        features_dir.parent if features_dir.name == "features" else features_dir
    )
    if not scan_root.is_dir():
        return 0

    highest = 0
    for entry in scan_root.rglob("F*"):
        if not entry.is_dir():
            continue
        match = _FEATURE_DIR_PATTERN.match(entry.name)
        if match is None:
            continue
        value = int(match.group(1))
        if value > highest:
            highest = value
    return highest


# ── CLI ─────────────────────────────────────────────────────────────────


def _cmd_allocate_next(features_dir: str, slug: str) -> int:
    """Allocate the next F<NNN> directory and print ``<id> <path>`` to stdout.

    Returns a process exit code: 0 on success, non-zero with a stderr
    message on failure. Skills invoke this as
    ``python3 scripts/feature_id.py allocate-next <features_dir> <slug>``
    so the contract is intentionally narrow: one line, space-separated,
    newline-terminated.
    """
    try:
        feature_id_str, feature_path = allocate_next(Path(features_dir), slug)
    except FeatureIdExhaustedError as exc:
        print(f"feature-id exhausted: {exc}", file=sys.stderr)
        return 2
    except (OSError, FileNotFoundError, NotADirectoryError) as exc:
        print(f"failed to allocate feature dir under {features_dir!r}: {exc}",
              file=sys.stderr)
        return 1

    print(f"{feature_id_str} {feature_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Entry point for the feature_id CLI.

    Subcommands:
        allocate-next <features_dir> <slug>
            Allocate the next available F<NNN> directory under
            ``<features_dir>`` and print ``<feature_id> <feature_path>``
            to stdout.
    """
    parser = argparse.ArgumentParser(
        prog="feature_id.py",
        description="Atomic F<NNN> feature-ID allocator.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    alloc = sub.add_parser(
        "allocate-next",
        help="Allocate the next F<NNN> feature directory.",
    )
    alloc.add_argument(
        "features_dir",
        help="Path to the project-scoped features root "
             "(e.g. .etc_sdlc/features).",
    )
    alloc.add_argument(
        "slug",
        help="Already-slugified suffix appended to the F-ID directory name.",
    )

    args = parser.parse_args(argv)

    if args.command == "allocate-next":
        return _cmd_allocate_next(args.features_dir, args.slug)

    # argparse with required=True should never let us reach here.
    parser.print_help(sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
