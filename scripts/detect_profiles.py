#!/usr/bin/env python3
"""detect_profiles.py — profile detection for F020 language-agnostic harness.

Walks the repo root looking for marker files declared by each profile's
detection.yaml. Returns a sorted list of activated profile names.

Per F020 BR-003 (deterministic detection), BR-004 (monorepo activates
every detected profile), BR-005 (operator override file is honored),
BR-011 (detection runs at install time AND per session).

Public API:
    detect(repo_root: Path) -> list[str]

CLI:
    python3 scripts/detect_profiles.py                # print profiles, one per line
    python3 scripts/detect_profiles.py --json         # print JSON list
    python3 scripts/detect_profiles.py --check-stale  # exit 0 fresh, 1 stale

Stdlib only — no third-party dependencies (PyYAML is project-wide for
override-file parsing only, isolated to the cold-path
_load_override_yaml function).
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger(__name__)

PROFILES_DIR_NAME = "standards/code/profiles"
PROFILES_LOCK_NAME = ".etc_sdlc/profiles.lock"
OVERRIDE_YAML_NAME = ".etc_sdlc/profiles.yaml"

# Strict identifier regex — profile names are filesystem dir names AND
# shell tokens; we whitelist [a-z][a-z0-9_-]*
_VALID_PROFILE_NAME = re.compile(r"^[a-z][a-z0-9_-]*$")


def _load_profile_detection(profile_dir: Path) -> dict[str, Any] | None:
    """Read a profile's detection.yaml. Return None on missing/malformed.

    The detection.yaml schema is:
        profile: <name>              (must match the directory name)
        markers: [list of filenames] (any-of activates the profile)
        file_globs: [list]           (which files this profile owns)
        exclude_globs: [list]        (paths to exclude)
        canonical_sources: [list]    (URLs cited by bindings.md files)
    """
    yaml_path = profile_dir / "detection.yaml"
    if not yaml_path.is_file():
        return None
    try:
        import yaml  # cold-path import; only when at least one profile exists
        with yaml_path.open("rb") as f:
            data = yaml.safe_load(f)
    except Exception as exc:
        LOGGER.warning(
            "Cannot read %s: %s. Skipping this profile.", yaml_path, exc
        )
        return None
    if not isinstance(data, dict):
        LOGGER.warning(
            "%s is not a mapping. Skipping this profile.", yaml_path
        )
        return None
    # Sanity: profile name must match directory name
    declared = data.get("profile")
    if declared != profile_dir.name:
        LOGGER.warning(
            "%s declares profile=%r but lives in directory %r. Skipping.",
            yaml_path, declared, profile_dir.name,
        )
        return None
    return data


def _enumerate_profile_dirs(repo_root: Path) -> list[Path]:
    """Return every standards/code/profiles/<profile>/ subdirectory."""
    profiles_root = repo_root / PROFILES_DIR_NAME
    if not profiles_root.is_dir():
        return []
    return sorted(
        p for p in profiles_root.iterdir()
        if p.is_dir() and _VALID_PROFILE_NAME.match(p.name)
    )


def _marker_present(repo_root: Path, marker: str) -> bool:
    """Check if a marker file exists at the repo root.

    Markers are filenames (e.g., 'pyproject.toml') or shallow glob
    patterns (e.g., '*.tf'). Pattern matching uses Path.glob.
    """
    if any(c in marker for c in ("*", "?", "[")):
        try:
            return any(repo_root.glob(marker))
        except Exception:
            return False
    return (repo_root / marker).exists()


def _load_override(repo_root: Path) -> dict[str, Any]:
    """Load .etc_sdlc/profiles.yaml. Return empty dict if absent.

    Schema:
        pin: [list of profile names]      # overrides auto-detect
        add: [list of profile names]      # added to auto-detect
        exclude_paths:                    # per-profile path exclusions
          <profile>: [list of paths]
    """
    override_path = repo_root / OVERRIDE_YAML_NAME
    if not override_path.is_file():
        return {}
    try:
        import yaml
        with override_path.open("rb") as f:
            data = yaml.safe_load(f)
    except Exception as exc:
        LOGGER.warning(
            "Cannot read %s: %s. Treating as absent.", override_path, exc
        )
        return {}
    if not isinstance(data, dict):
        LOGGER.warning(
            "%s is not a mapping. Treating as absent.", override_path
        )
        return {}
    # Validate profile-name values against the strict regex (security)
    for key in ("pin", "add"):
        if key in data and isinstance(data[key], list):
            data[key] = [
                name for name in data[key]
                if isinstance(name, str) and _VALID_PROFILE_NAME.match(name)
            ]
    return data


def detect(repo_root: Path) -> list[str]:
    """Return the sorted list of activated profile names for this repo.

    Algorithm:
    1. Enumerate profile dirs at standards/code/profiles/<profile>/.
    2. For each, read detection.yaml; skip malformed entries.
    3. Load .etc_sdlc/profiles.yaml (operator override) if present.
    4. If `pin:` is set, that's the result (intersected with valid
       profiles).
    5. Otherwise: every profile with at least one marker present is
       activated; then merge in `add:` (intersected with valid).
    6. Return sorted alphabetically (BR-003 determinism).
    """
    profile_dirs = _enumerate_profile_dirs(repo_root)
    valid_profiles: dict[str, dict[str, Any]] = {}
    for pd in profile_dirs:
        detection = _load_profile_detection(pd)
        if detection is not None:
            valid_profiles[pd.name] = detection

    if not valid_profiles:
        return []

    override = _load_override(repo_root)

    # Pin overrides auto-detect entirely
    if "pin" in override and isinstance(override["pin"], list):
        pinned = [p for p in override["pin"] if p in valid_profiles]
        return sorted(set(pinned))

    # Auto-detect: marker-present check
    activated: set[str] = set()
    for name, detection in valid_profiles.items():
        markers = detection.get("markers") or []
        if not isinstance(markers, list):
            continue
        for marker in markers:
            if isinstance(marker, str) and _marker_present(repo_root, marker):
                activated.add(name)
                break

    # Merge add: (intersected with valid profiles)
    if "add" in override and isinstance(override["add"], list):
        for name in override["add"]:
            if name in valid_profiles:
                activated.add(name)

    return sorted(activated)


def _write_lock(lock_path: Path, profiles: list[str]) -> None:
    """Atomically write profiles.lock via .tmp + os.replace."""
    import os
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = lock_path.with_suffix(lock_path.suffix + ".tmp")
    tmp.write_text("".join(p + "\n" for p in profiles), encoding="utf-8")
    os.replace(tmp, lock_path)


def _is_stale(repo_root: Path, lock_path: Path) -> bool:
    """Check if profiles.lock is older than any marker file."""
    if not lock_path.is_file():
        return True
    lock_mtime = lock_path.stat().st_mtime
    profile_dirs = _enumerate_profile_dirs(repo_root)
    for pd in profile_dirs:
        detection = _load_profile_detection(pd)
        if detection is None:
            continue
        markers = detection.get("markers") or []
        if not isinstance(markers, list):
            continue
        for marker in markers:
            if not isinstance(marker, str):
                continue
            for candidate in repo_root.glob(marker):
                try:
                    if candidate.stat().st_mtime > lock_mtime:
                        return True
                except OSError:
                    continue
    return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Detect language profiles active in this repo.",
    )
    parser.add_argument("--repo-root", default=".", help="repo root (default: cwd)")
    parser.add_argument("--json", action="store_true", help="emit JSON")
    parser.add_argument(
        "--check-stale", action="store_true",
        help="exit 0 if profiles.lock is fresh, 1 if stale",
    )
    parser.add_argument(
        "--write-lock", action="store_true",
        help="write detection result to .etc_sdlc/profiles.lock",
    )
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    lock_path = repo_root / PROFILES_LOCK_NAME

    if args.check_stale:
        return 1 if _is_stale(repo_root, lock_path) else 0

    try:
        profiles = detect(repo_root)
    except Exception as exc:
        sys.stderr.write(f"detect_profiles: detection failed: {exc}\n")
        return 2

    if args.write_lock:
        _write_lock(lock_path, profiles)

    if args.json:
        print(json.dumps(profiles))
    else:
        for p in profiles:
            print(p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
