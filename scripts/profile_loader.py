#!/usr/bin/env python3
"""profile_loader.py — file-to-profile resolution for F020.

Given a file path, return the profile responsible for it (or None if no
profile matches). Used by the bash dispatch helper at hook fire time.

Public API:
    profile_for(file_path: str, lock_path: Path | None = None) -> str | None
    active_profiles(lock_path: Path | None = None) -> list[str]

CLI:
    python3 scripts/profile_loader.py profile-for <file>   # print profile or empty
    python3 scripts/profile_loader.py active               # print active profiles

Always exits 0; "no profile matches" is empty stdout (not non-zero).
This is what makes the bash dispatch logic clean.
"""

from __future__ import annotations

import argparse
import fnmatch
import sys
from pathlib import Path
from typing import Any

DEFAULT_LOCK_PATH = Path(".etc_sdlc/profiles.lock")
PROFILES_DIR = Path("standards/code/profiles")


def active_profiles(lock_path: Path | None = None) -> list[str]:
    """Return the sorted list of active profile names from profiles.lock."""
    lp = lock_path or DEFAULT_LOCK_PATH
    if not lp.is_file():
        return []
    try:
        text = lp.read_text(encoding="utf-8")
    except OSError:
        return []
    return [line.strip() for line in text.splitlines() if line.strip()]


def _load_detection(profile: str) -> dict[str, Any] | None:
    """Read a profile's detection.yaml. Return None on missing/malformed."""
    yaml_path = PROFILES_DIR / profile / "detection.yaml"
    if not yaml_path.is_file():
        return None
    try:
        import yaml
        with yaml_path.open("rb") as f:
            data = yaml.safe_load(f)
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _match_specificity(pattern: str) -> int:
    """Return a specificity score for a glob — more literal chars = more specific.

    Used to break ties when multiple profiles claim the same file. The
    profile with the more-specific path match wins; equally specific
    profiles break ties alphabetically (handled by the caller).
    """
    return sum(1 for c in pattern if c not in "*?[]")


def profile_for(
    file_path: str,
    lock_path: Path | None = None,
) -> str | None:
    """Return the active profile responsible for file_path, or None."""
    active = active_profiles(lock_path)
    if not active:
        return None

    # Normalize file_path to a forward-slash relative form for fnmatch
    # consistency across platforms
    fp_str = str(Path(file_path).as_posix())

    # Score each active profile by best matching glob specificity
    best: tuple[int, str] | None = None  # (specificity, profile_name)
    for profile in active:
        detection = _load_detection(profile)
        if detection is None:
            continue

        # exclude_globs: if any matches, this profile doesn't claim the file
        exclude_globs = detection.get("exclude_globs") or []
        if isinstance(exclude_globs, list):
            excluded = False
            for pat in exclude_globs:
                if isinstance(pat, str) and fnmatch.fnmatch(fp_str, pat):
                    excluded = True
                    break
            if excluded:
                continue

        # file_globs: any-of match claims the file
        file_globs = detection.get("file_globs") or []
        if not isinstance(file_globs, list):
            continue
        for pat in file_globs:
            if isinstance(pat, str) and fnmatch.fnmatch(fp_str, pat):
                score = _match_specificity(pat)
                # Tie-break: prefer higher specificity, then alphabetical
                # (lexicographically smaller profile name wins on tie)
                if best is None:
                    best = (score, profile)
                elif score > best[0]:
                    best = (score, profile)
                elif score == best[0] and profile < best[1]:
                    best = (score, profile)
                break  # one match per profile is enough

    return best[1] if best else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Resolve file → profile")
    sub = parser.add_subparsers(dest="cmd", required=True)

    pf = sub.add_parser("profile-for", help="resolve a single file path")
    pf.add_argument("file_path")
    pf.add_argument("--lock-path", default=str(DEFAULT_LOCK_PATH))

    ap = sub.add_parser("active", help="print active profiles, one per line")
    ap.add_argument("--lock-path", default=str(DEFAULT_LOCK_PATH))

    args = parser.parse_args(argv)
    lock = Path(args.lock_path)

    if args.cmd == "profile-for":
        result = profile_for(args.file_path, lock)
        if result:
            print(result)
        return 0

    if args.cmd == "active":
        for p in active_profiles(lock):
            print(p)
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
