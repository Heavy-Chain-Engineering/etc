#!/usr/bin/env python3
"""profile_loader.py — file-to-profile resolution for F020 + F022 overrides.

Given a file path, return the profile responsible for it (or None if no
profile matches). Used by the bash dispatch helper at hook fire time.

Public API:
    profile_for(file_path: str, lock_path: Path | None = None) -> str | None
    active_profiles(lock_path: Path | None = None) -> list[str]
    load_profiles_with_overrides(cwd: Path) -> OverrideMergeResult     # F022

CLI:
    python3 scripts/profile_loader.py profile-for <file>   # print profile or empty
    python3 scripts/profile_loader.py active               # print active profiles

Always exits 0; "no profile matches" is empty stdout (not non-zero).
This is what makes the bash dispatch logic clean.

F022 BR-006: The override-merge path reads .etc_sdlc/profiles.yaml if
present and layers pin/exclude/add over detection output. Detection-first
invariant from F020-ADR-002 is preserved — overrides MODIFY detection;
never REPLACE it.
"""

from __future__ import annotations

import argparse
import fnmatch
import sys
from pathlib import Path
from typing import Any, NamedTuple

DEFAULT_LOCK_PATH = Path(".etc_sdlc/profiles.lock")
PROFILES_DIR = Path("standards/code/profiles")
OVERRIDE_YAML_NAME = ".etc_sdlc/profiles.yaml"
_ALLOWED_TOP_LEVEL_KEYS = frozenset({"pin", "exclude", "add"})


class OverrideMergeResult(NamedTuple):
    """Result of merging detection output with .etc_sdlc/profiles.yaml.

    Attributes:
        active: union(detection, pin, add[].profile) — alphabetically sorted.
        excludes: path globs the active profile's verify-green should skip.
        added_sources: mapping profile_name -> source dir for add[] entries
            that passed validation. Empty when no add[] entries provided.
    """

    active: list[str]
    excludes: list[str]
    added_sources: dict[str, str]


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


def _warn(message: str) -> None:
    """Emit a Pattern B stderr WARN. Best-effort: silent on stderr failure."""
    try:
        sys.stderr.write(f"WARN: profile_loader: {message}\n")
    except OSError:
        pass  # degrade silently if stderr is unwriteable


def _safe_read_override_yaml(override_path: Path) -> dict[str, Any] | None:
    """Read and parse .etc_sdlc/profiles.yaml. Return None on any failure.

    Failure modes emit stderr WARN and return None so the caller falls
    back to detection-only behavior. Per BR-006 the loader MUST NOT raise.
    """
    try:
        import yaml
    except ImportError:
        _warn("PyYAML not installed; ignoring override file")
        return None
    try:
        with override_path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as exc:
        _warn(f"malformed YAML in {override_path}: {exc}; falling back to detection")
        return None
    except OSError as exc:
        _warn(f"cannot read {override_path}: {exc}; falling back to detection")
        return None
    if data is None:
        # Empty file is valid YAML but conveys no overrides; treat as
        # no-op (NOT a failure — detection result is unchanged).
        return {}
    if not isinstance(data, dict):
        _warn(
            f"{override_path} top-level is not a mapping; "
            "falling back to detection"
        )
        return None
    return data


def _validate_top_level_keys(
    data: dict[str, Any],
    override_path: Path,
) -> bool:
    """Reject unknown top-level keys. Return True if schema is acceptable.

    Per BR-006: unknown keys emit stderr WARN and fall back to
    detection-only behavior. The literal substring "unknown key" must
    appear in the WARN message (the spec-enforcer test greps for it).
    """
    unknown = set(data.keys()) - _ALLOWED_TOP_LEVEL_KEYS
    if unknown:
        _warn(
            f"{override_path} contains unknown key(s): "
            f"{sorted(unknown)}; falling back to detection-only"
        )
        return False
    return True


def _coerce_str_list(value: Any) -> list[str]:
    """Coerce a YAML value to list[str], filtering non-str entries."""
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _validate_add_entry(
    entry: Any,
    cwd: Path,
) -> tuple[str, str] | None:
    """Validate one add[] entry. Return (profile, source) or None.

    Security:
        - reject non-mapping entries
        - reject missing or non-str 'profile' / 'source'
        - reject absolute paths in source
        - reject path-traversal ('..') in source
    """
    if not isinstance(entry, dict):
        _warn(f"add[] entry must be a mapping, got {type(entry).__name__}")
        return None
    profile = entry.get("profile")
    source = entry.get("source")
    if not isinstance(profile, str) or not profile:
        _warn(f"add[] entry missing or non-str 'profile' field: {entry!r}")
        return None
    if not isinstance(source, str) or not source:
        _warn(f"add[] entry missing or non-str 'source' field: {entry!r}")
        return None
    # Path-traversal guard: reject absolute paths and any '..' segment.
    source_path = Path(source)
    if source_path.is_absolute():
        _warn(
            f"add[] entry rejected: 'source' is absolute path "
            f"({source!r}); must be relative to cwd"
        )
        return None
    if ".." in source_path.parts:
        _warn(
            f"add[] entry rejected: 'source' contains path traversal "
            f"({source!r})"
        )
        return None
    # Defensive: resolve against cwd and confirm we did not escape it.
    try:
        resolved = (cwd / source_path).resolve()
        resolved.relative_to(cwd.resolve())
    except (ValueError, OSError):
        _warn(
            f"add[] entry rejected: resolved 'source' escapes cwd "
            f"({source!r})"
        )
        return None
    return profile, source


def load_profiles_with_overrides(cwd: Path) -> OverrideMergeResult:
    """Return active profile set after merging detection + operator overrides.

    Read order: profiles.lock (detection output) -> .etc_sdlc/profiles.yaml.
    Override application: union(detection, pin, add[].profile);
    excludes accumulate into the returned glob list.

    Detection-first invariant (F020-ADR-002): overrides MODIFY detection;
    never REPLACE it. An empty override file MUST NOT disable detection.

    Failure modes (malformed YAML, unknown top-level key, non-mapping
    top-level, path-traversal in add[].source) emit stderr WARN and fall
    back to detection-only behavior. The loader MUST NOT raise.

    Args:
        cwd: repo root. profiles.lock is read at
            <cwd>/.etc_sdlc/profiles.lock; override file at
            <cwd>/.etc_sdlc/profiles.yaml.

    Returns:
        OverrideMergeResult with active list, excludes, and added_sources.
    """
    detection_set: set[str] = set(
        active_profiles(cwd / DEFAULT_LOCK_PATH)
    )

    override_path = cwd / OVERRIDE_YAML_NAME
    if not override_path.is_file():
        # Detection-only path — no overrides to merge.
        return OverrideMergeResult(
            active=sorted(detection_set),
            excludes=[],
            added_sources={},
        )

    data = _safe_read_override_yaml(override_path)
    if data is None:
        # Read/parse failed — fall back to detection-only.
        return OverrideMergeResult(
            active=sorted(detection_set),
            excludes=[],
            added_sources={},
        )

    if not _validate_top_level_keys(data, override_path):
        # Unknown top-level key — fall back to detection-only.
        return OverrideMergeResult(
            active=sorted(detection_set),
            excludes=[],
            added_sources={},
        )

    # Schema is valid (or empty). Apply each section.
    active_set = set(detection_set)

    # pin: force-include profile names.
    for name in _coerce_str_list(data.get("pin")):
        active_set.add(name)

    # exclude: accumulate path globs for dispatch context.
    excludes = _coerce_str_list(data.get("exclude"))

    # add: operator-supplied profile additions with source paths.
    added_sources: dict[str, str] = {}
    add_entries = data.get("add") or []
    if isinstance(add_entries, list):
        for entry in add_entries:
            result = _validate_add_entry(entry, cwd)
            if result is None:
                continue
            profile_name, source = result
            active_set.add(profile_name)
            added_sources[profile_name] = source

    return OverrideMergeResult(
        active=sorted(active_set),
        excludes=excludes,
        added_sources=added_sources,
    )


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
