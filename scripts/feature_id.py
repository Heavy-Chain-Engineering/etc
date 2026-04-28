"""feature_id.py — Atomic F<NNN> feature-ID allocator and slug helper.

Allocates per-project feature IDs of the form ``F<NNN>`` (3-digit zero-padded)
using POSIX-atomic ``os.mkdir`` with EEXIST retry. This is the canonical
race-free allocation pattern (see ``.etc_sdlc/features/metrics-and-release-
notes/gray-areas.md`` GA-006: POSIX.1 mkdir(2) atomicity).

Public API:

- ``allocate_next(features_dir, slug) -> (feature_id, feature_path)``
- ``slugify(title) -> str``
- ``FeatureIdExhaustedError`` — raised when the project hits the v1 F999 ceiling.

Behavior is forward-only: existing slug-only directories (grandfathered per
GA-002) are ignored when computing the maximum F-ID. ID gaps are acceptable;
ID reuse is not (BR-002).
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
            Created if it does not already exist.
        slug: Already-slugified suffix appended to the F-ID directory name.

    Returns:
        ``(feature_id, feature_path)`` where ``feature_id`` is ``"F<NNN>"`` and
        ``feature_path`` is the freshly-created directory.

    Raises:
        FeatureIdExhaustedError: When all F001–F999 slots are consumed.

    Concurrency:
        Uses ``os.mkdir`` which is POSIX-atomic. On ``FileExistsError`` the
        function re-reads the maximum existing F-ID and retries at +1, so two
        racing callers receive distinct IDs (BR-003 / AC-002).
    """
    features_dir.mkdir(parents=True, exist_ok=True)

    while True:
        next_id = _scan_max_feature_id(features_dir) + 1
        if next_id > _MAX_FEATURE_ID:
            raise FeatureIdExhaustedError(
                f"Project has reached the v1 feature ID ceiling "
                f"({_MAX_FEATURE_ID})"
            )

        feature_id_str = f"F{next_id:03d}"
        candidate = features_dir / f"{feature_id_str}-{slug}"

        try:
            os.mkdir(candidate)
        except FileExistsError:
            # Lost the race — another writer won this slot. Re-scan and retry.
            continue

        return feature_id_str, candidate


# ── Internals ───────────────────────────────────────────────────────────


def _scan_max_feature_id(features_dir: Path) -> int:
    """Return the highest F<NNN> id present under ``features_dir``, or 0.

    Non-feature directories (legacy slug-only entries grandfathered per
    GA-002, plus any unrelated content) are ignored.
    """
    highest = 0
    for entry in features_dir.iterdir():
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
