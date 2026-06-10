#!/usr/bin/env python3
"""Cross-feature collision detection (F016 / R2).

Scans .etc_sdlc/features/F*/tasks/*.yaml and
.etc_sdlc/features/active/F*/tasks/*.yaml for `files_in_scope` entries.
Compares the union of OTHER in-flight features' file sets against the
current feature's. Reports overlaps so the operator (or /build Step 5)
can cancel, proceed with risk acknowledged, or serialize.

Excludes:
  - The current feature (identified by directory name)
  - .etc_sdlc/features/shipped/ (already done, won't collide)
  - .etc_sdlc/features/rejections/ (not in flight)
  - Any feature with a terminal build.completed_at in its state.yaml —
    i.e. one that shipped IN PLACE (flat/active layout) without being
    moved into shipped/ (#56)

Exit codes:
  0 = no collisions
  1 = usage / IO error
  2 = collisions detected (block or warn depending on caller)

Usage:
  cross_feature_collision_check.py <current_feature_dir>
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

# Legacy sequential form: the feature id is the F<NNN> PREFIX (slug stripped).
_LEGACY_ID_PATTERN = re.compile(r"^(F\d+)-")
# Date-based form (current scheme): the directory NAME *is* the feature id —
# there is no separate -<slug> suffix to strip. Mirror scripts/feature_id.py.
_DATED_ID_PATTERN = re.compile(r"^F-\d{4}-\d{2}-\d{2}-.+$")


def parse_feature_id(feature_dir: Path) -> str | None:
    """Extract the feature id from a directory name, accepting both grammars.

    - Legacy sequential ``F016-foo-bar`` → ``"F016"`` (the prefix; slug stripped).
    - Date-based ``F-2026-06-02-build-review-agent-gate`` → the FULL directory
      name (the name itself is the id — no slug suffix to strip). This is the
      form scripts/feature_id.py::allocate_temp now produces and the form the
      git tag namespace ``etc/feature/<id>/spec`` is built on.

    Returns ``None`` when the name matches neither grammar.
    """
    name = feature_dir.name
    if _DATED_ID_PATTERN.match(name):
        return name
    legacy = _LEGACY_ID_PATTERN.match(name)
    return legacy.group(1) if legacy else None


def features_root_from(feature_dir: Path) -> Path:
    """Resolve the .etc_sdlc/features/ root from any feature_dir path
    (handles both flat-path and active/ subdirectory layouts)."""
    cur = feature_dir.resolve()
    # Walk up until we hit a parent named 'features'
    while cur != cur.parent:
        if cur.name == "features" and cur.parent.name == ".etc_sdlc":
            return cur
        cur = cur.parent
    return feature_dir.parent  # best-effort fallback


def load_files_in_scope(task_yaml: Path) -> list[str]:
    """Read a single task YAML and return its files_in_scope list.
    Returns [] on any read or parse error."""
    try:
        with task_yaml.open(encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except (OSError, yaml.YAMLError):
        return []
    if not isinstance(data, dict):
        return []
    files = data.get("files_in_scope") or []
    if not isinstance(files, list):
        return []
    return [str(f) for f in files if isinstance(f, str)]


def is_released(feature_dir: Path) -> bool:
    """Return True when the feature has already shipped/released.

    A feature that completed /build carries a terminal ``build.completed_at``
    timestamp in its ``state.yaml`` (written when /build reaches its final
    step). Such a feature is done and cannot generate new cross-feature
    conflicts, so it must be excluded from the active-collision scan — even
    when it shipped IN PLACE (flat or active layout) without being moved into
    ``shipped/`` (#56). Path-based ``shipped/`` exclusion alone misses these.

    Returns False on any missing/unreadable state.yaml so an unknown-status
    feature is treated as in-flight (fail-safe toward flagging, not hiding).
    """
    state_yaml = feature_dir / "state.yaml"
    if not state_yaml.is_file():
        return False
    try:
        with state_yaml.open(encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except (OSError, yaml.YAMLError):
        return False
    if not isinstance(data, dict):
        return False
    build = data.get("build")
    if not isinstance(build, dict):
        return False
    return bool(build.get("completed_at"))


def feature_files(feature_dir: Path) -> set[str]:
    """Aggregate files_in_scope across every tasks/*.yaml in a feature dir."""
    tasks_dir = feature_dir / "tasks"
    if not tasks_dir.is_dir():
        return set()
    files: set[str] = set()
    for task_yaml in tasks_dir.glob("*.yaml"):
        files.update(load_files_in_scope(task_yaml))
    return files


def enumerate_in_flight_features(
    features_root: Path, current_feature_id: str | None
) -> dict[str, tuple[Path, set[str]]]:
    """Return {feature_id: (path, files_set)} for all in-flight features
    excluding shipped/, rejections/, and the current feature.

    Scans:
      - features_root / F<NNN>-*  (flat path, F009 workaround layout)
      - features_root / active / F<NNN>-*  (F009 lifecycle layout)
    """
    results: dict[str, tuple[Path, set[str]]] = {}

    def _add_dirs(parent: Path) -> None:
        if not parent.is_dir():
            return
        for child in parent.iterdir():
            if not child.is_dir():
                continue
            fid = parse_feature_id(child)
            if fid is None:
                continue
            if fid == current_feature_id:
                continue
            # #56 — a feature released in place (flat/active layout, never
            # moved into shipped/) is done and cannot collide. Skip it.
            if is_released(child):
                continue
            files = feature_files(child)
            if not files:
                continue
            # If we've already seen this feature_id at flat path AND active,
            # union the files. The flat path takes precedence for the path
            # field (it's where tasks.py operates).
            if fid in results:
                existing_path, existing_files = results[fid]
                results[fid] = (existing_path, existing_files | files)
            else:
                results[fid] = (child, files)

    _add_dirs(features_root)
    _add_dirs(features_root / "active")
    # Explicitly do NOT walk shipped/ or rejections/
    return results


def find_collisions(
    current_files: set[str],
    in_flight: dict[str, tuple[Path, set[str]]],
) -> dict[str, list[str]]:
    """Return {colliding_file_path: [feature_id, feature_id, ...]}
    listing every other in-flight feature that touches each shared file."""
    collisions: dict[str, list[str]] = {}
    for fid, (_, files) in in_flight.items():
        overlap = current_files & files
        for f in overlap:
            collisions.setdefault(f, []).append(fid)
    # Sort feature_ids for stable output
    for f in collisions:
        collisions[f].sort()
    return collisions


def print_collision_report(
    collisions: dict[str, list[str]], current_feature_id: str | None
) -> None:
    """AC-05: emit a structured stdout report."""
    fid_str = current_feature_id or "(unknown)"
    print(f"CROSS-FEATURE COLLISION DETECTED ({fid_str})")
    print()
    print("The following files are claimed by the current feature AND by")
    print("other in-flight features:")
    print()
    for filepath in sorted(collisions):
        others = ", ".join(collisions[filepath])
        print(f"  {filepath} ← [{others}]")
    print()
    print("Resolution options:")
    print("  A) Cancel this /build; coordinate with the other feature(s).")
    print("  B) Proceed with risk acknowledged — operator owns the eventual")
    print("     merge resolution.")
    print("  C) Serialize via dependency: add a task dependency to the other")
    print("     feature's final wave so this feature builds AFTER it.")
    print()
    print("Under /build --autonomous (F014), the equivalent of (B) is auto-")
    print("selected and the collisions are written to")
    print("state.yaml.build.cross_feature_collisions for the audit trail.")


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        sys.stderr.write(__doc__ or "")
        return 1

    feature_dir = Path(argv[1])
    if not feature_dir.is_dir():
        sys.stderr.write(f"ERROR: feature_dir not found: {feature_dir}\n")
        return 1

    current_feature_id = parse_feature_id(feature_dir)
    features_root = features_root_from(feature_dir)
    current_files = feature_files(feature_dir)

    if not current_files:
        # No files declared yet (likely pre-Step-3); nothing to collide with.
        return 0

    in_flight = enumerate_in_flight_features(features_root, current_feature_id)
    collisions = find_collisions(current_files, in_flight)

    if not collisions:
        return 0

    print_collision_report(collisions, current_feature_id)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
