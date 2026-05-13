#!/usr/bin/env python3
"""Journey-lineage gate for /build Step 7.4 (F017).

Reads <feature_dir>/state.yaml and verifies that the feature either:
  (a) declares journey_refs: [J-NNN, ...] AND each referenced journey
      file exists at <repo_root>/docs/mvp/journeys/J-NNN-*.md, OR
  (b) declares infrastructure_only: true AND a non-empty
      infrastructure_reason: "<text>".

Date-check (F017 backward compatibility): features filed BEFORE the F017
release tag pass automatically. Detected by comparing
state.yaml.spec_phase.completed_at against the F017 release tag's commit
date. If F017 release tag is missing OR feature predates it, the gate
returns 0 (pass) with no message.

Exit codes:
  0 = lineage OK (or legacy feature; gate skipped)
  1 = usage / IO error
  2 = lineage missing — block release tag

Usage:
  journey_lineage_check.py <feature_dir>
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import yaml


def repo_root_from(feature_dir: Path) -> Path:
    """Walk up until we find .git/. Best-effort fallback to feature_dir.parent."""
    cur = feature_dir.resolve()
    while cur != cur.parent:
        if (cur / ".git").exists():
            return cur
        cur = cur.parent
    return feature_dir.parent


def read_state_yaml(feature_dir: Path) -> dict:
    state_path = feature_dir / "state.yaml"
    if not state_path.exists():
        return {}
    try:
        with state_path.open(encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except (OSError, yaml.YAMLError):
        return {}
    return data if isinstance(data, dict) else {}


def f017_release_tag_date(repo: Path) -> str | None:
    """Return ISO-8601 commit date of the F017 release tag, or None if absent."""
    tag = "etc/feature/F017/release"
    try:
        result = subprocess.run(
            [
                "git", "-C", str(repo),
                "log", "-1", "--format=%cI", tag,
            ],
            capture_output=True, text=True, timeout=5,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def feature_predates_f017(state: dict, repo: Path) -> bool:
    """Return True if this feature's spec_phase.completed_at predates the
    F017 release tag, OR if F017 release tag does not yet exist. In both
    cases the journey-lineage gate is skipped."""
    f017_date = f017_release_tag_date(repo)
    if f017_date is None:
        # F017 hasn't shipped yet. No legacy features to gate.
        return True
    completed_at = (state.get("spec_phase") or {}).get("completed_at")
    if not completed_at:
        # No completed_at means we can't compare; default to "pre-F017" to
        # avoid blocking on features with incomplete state.yaml.
        return True
    return str(completed_at) < f017_date


def check_journey_refs(
    journey_refs: list[str], repo: Path
) -> tuple[list[str], list[str]]:
    """Return (found, missing) lists of journey IDs. Each referenced ID
    must have a matching docs/mvp/journeys/J-NNN-*.md file."""
    journeys_dir = repo / "docs" / "mvp" / "journeys"
    found: list[str] = []
    missing: list[str] = []
    if not journeys_dir.is_dir():
        return [], list(journey_refs)
    for ref in journey_refs:
        # Normalize: accept "J-007", "J007", "J-7"
        match = re.match(r"^J-?(\d+)$", ref.strip(), re.IGNORECASE)
        if not match:
            missing.append(ref)
            continue
        n = int(match.group(1))
        candidates = list(journeys_dir.glob(f"J-{n:03d}-*.md")) + list(
            journeys_dir.glob(f"J-{n}-*.md")
        )
        if candidates:
            found.append(ref)
        else:
            missing.append(ref)
    return found, missing


def print_block_report(missing: list[str], feature_dir: Path) -> None:
    print("JOURNEY LINEAGE MISSING")
    print()
    if not missing:
        print(
            "This feature has no captured user journey AND is not marked "
            "as infrastructure-only."
        )
    else:
        print("The following journey references could not be resolved:")
        for ref in missing:
            print(f"  {ref}")
    print()
    print(
        "Every shipped feature must trace to a customer's lived experience"
    )
    print("OR be explicitly marked as infrastructure-only.")
    print()
    print("Resolution:")
    print("  A) Run /journey to capture a journey, then update")
    print(f"     {feature_dir}/state.yaml")
    print("     under spec_phase.journey_refs: [J-NNN, ...]")
    print("  B) If this is infrastructure work (library upgrade, harness")
    print("     internals, CI tooling), update state.yaml to add:")
    print("       spec_phase:")
    print("         infrastructure_only: true")
    print("         infrastructure_reason: \"<one-line reason>\"")
    print()
    print("Override (logged to verification.md + release-notes.md):")
    print('  /build --skip-journey-check="<reason>"')


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        sys.stderr.write(__doc__ or "")
        return 1

    feature_dir = Path(argv[1])
    if not feature_dir.is_dir():
        sys.stderr.write(f"ERROR: feature_dir not found: {feature_dir}\n")
        return 1

    state = read_state_yaml(feature_dir)
    spec_phase = state.get("spec_phase") or {}
    repo = repo_root_from(feature_dir)

    # Backward-compat: skip gate for features filed before F017 shipped.
    if feature_predates_f017(state, repo):
        return 0

    # Infrastructure escape hatch (must have BOTH the sentinel AND a reason).
    if spec_phase.get("infrastructure_only") is True:
        reason = spec_phase.get("infrastructure_reason")
        if not isinstance(reason, str) or not reason.strip():
            sys.stderr.write(
                "ERROR: infrastructure_only: true requires a non-empty "
                "infrastructure_reason in state.yaml.spec_phase.\n"
            )
            return 2
        return 0

    # Customer-facing path: journey_refs must be non-empty AND each
    # referenced journey must exist.
    refs = spec_phase.get("journey_refs") or []
    if not isinstance(refs, list) or not refs:
        print_block_report([], feature_dir)
        return 2

    refs_str = [str(r) for r in refs]
    _, missing = check_journey_refs(refs_str, repo)
    if missing:
        print_block_report(missing, feature_dir)
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
