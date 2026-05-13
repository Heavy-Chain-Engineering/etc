"""Feature-directory path resolution helpers (the F009-lifecycle-gap fix — F009 lifecycle gap fix).

The F009 two-state lifecycle puts allocator output under
`.etc_sdlc/features/active/F<NNN>-<slug>/` (in-flight) and moves shipped
features to `.etc_sdlc/features/shipped/F<NNN>-<slug>/`. Legacy F001-F009
features stayed at `.etc_sdlc/features/F<NNN>-<slug>/` (flat path) for
backwards compatibility.

Without a central resolver, every consumer (tasks.py, hooks, skills,
release_notes) constructed `features_dir / feature_name` ad-hoc, which
only honored the flat path. the F009-lifecycle-gap fix introduces this module so callers use
a single lifecycle-aware lookup.

Public API:
  - find_feature_dir(repo_root, name) — return the feature dir wherever
    it lives, or None if absent. Search order: active/ → flat → shipped/.
  - iter_in_flight_feature_dirs(repo_root) — yield Path for every
    feature currently in flight (active/ + flat path; excludes shipped/
    and rejections/).
  - iter_all_feature_dirs(repo_root) — yield Path for every feature
    including shipped/ (excludes rejections/).
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

# Match F<NNN>-<slug> directory names (e.g. "F042-add-user-auth").
_FEATURE_DIR_PATTERN = re.compile(r"^F\d+(-.+)?$")


def features_root(repo_root: Path) -> Path:
    """Return the .etc_sdlc/features/ directory under a repo root."""
    return repo_root / ".etc_sdlc" / "features"


def find_feature_dir(repo_root: Path, name: str) -> Path | None:
    """Locate a feature directory by name across the F009 lifecycle states.

    Search order (first match wins):
      1. .etc_sdlc/features/active/<name>/   (F009 active state — preferred)
      2. .etc_sdlc/features/<name>/          (F009 legacy flat path)
      3. .etc_sdlc/features/shipped/<name>/  (F009 shipped state)

    Returns None if `name` is not found in any of the three locations.
    Callers that need to distinguish active vs shipped should walk
    these paths explicitly; for the common "find any feature by name"
    case, this resolver is sufficient.
    """
    root = features_root(repo_root)
    candidates = [
        root / "active" / name,
        root / name,
        root / "shipped" / name,
    ]
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return None


def iter_in_flight_feature_dirs(repo_root: Path) -> Iterator[Path]:
    """Yield every feature directory currently in flight.

    Includes:
      - .etc_sdlc/features/active/F<NNN>-<slug>/
      - .etc_sdlc/features/F<NNN>-<slug>/   (legacy flat-path features)

    Excludes:
      - .etc_sdlc/features/shipped/  (already done)
      - .etc_sdlc/features/rejections/  (not in flight)
      - .etc_sdlc/features/active/, shipped/, rejections/ themselves
        (these are lifecycle directories, not feature directories)
    """
    root = features_root(repo_root)
    if not root.is_dir():
        return

    active = root / "active"
    if active.is_dir():
        for child in active.iterdir():
            if _is_feature_dir(child):
                yield child

    # Flat path: scan immediate children of features/, excluding the
    # three lifecycle subdirectories (active/, shipped/, rejections/).
    excluded_names = {"active", "shipped", "rejections"}
    for child in root.iterdir():
        if not _is_feature_dir(child):
            continue
        if child.name in excluded_names:
            continue
        yield child


def iter_all_feature_dirs(repo_root: Path) -> Iterator[Path]:
    """Yield every feature directory across all lifecycle states.

    Same as iter_in_flight_feature_dirs() plus shipped/ features.
    Excludes rejections/ (rejected specs are not features).
    """
    yield from iter_in_flight_feature_dirs(repo_root)

    shipped = features_root(repo_root) / "shipped"
    if shipped.is_dir():
        for child in shipped.iterdir():
            if _is_feature_dir(child):
                yield child


def _is_feature_dir(path: Path) -> bool:
    """A feature directory's name matches F<NNN>[-<slug>]. Slug-only
    legacy names (e.g. 'hotfix', 'tasks-cli') from pre-F-numbering days
    DO NOT match this pattern and are excluded from iteration; they're
    still findable via find_feature_dir() if a caller knows the exact
    name."""
    return path.is_dir() and bool(_FEATURE_DIR_PATTERN.match(path.name))
