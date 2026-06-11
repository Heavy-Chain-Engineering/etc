#!/usr/bin/env python3
"""resolve_agent_profile.py — the manifest placeholder resolver (F-2026-06-01).

The load-bearing first link of profile-driven agent bodies. A profile-aware
agent runs this at start to resolve its inert `${profiles}` /
`${profile_bindings_template}` placeholders against the project's live
`profiles.lock`, so the correct per-profile bindings (and a profile-sourced
toolchain summary) reach the agent instead of a literal placeholder string.

Thin wrapper over `profile_loader.active_profiles()` per ADR-001 (there is no
etc-owned dispatch seam in Claude Code; each agent self-resolves at start).
For each active profile it returns the bindings PATHS under
`standards/code/profiles/<profile>/<rule>-bindings.md` plus a toolchain
summary derived from that profile's own `detection.yaml`. It is read-only over
`profiles.lock` and over the profile dirs: it returns binding paths, it never
opens or executes their contents (the agent reads them) — path-claim, not
path-fetch.

Public API:
    resolve(lock_path: Path | None = None) -> ResolvedProfile

CLI (per design API):
    python3 scripts/resolve_agent_profile.py resolve [--lock PATH] \
        [--format json|text]
    -> {active_profiles: [str], bindings: [path], toolchain_summary: str}

Exit 0 ALWAYS on a completed read. An absent or empty profiles.lock yields the
empty/top-level form (empty active_profiles + a "no active profile; top-level
rules only" note); it never crashes and never leaks a literal placeholder.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

SCRIPTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPTS_DIR.parent

# `scripts/` is deliberately not a package (no __init__.py); every script uses
# flat sibling imports and is installed to ~/.claude/scripts/ + invoked by
# absolute path, so `from scripts.X import ...` is forbidden (see
# scripts/git_tags.py). Put the scripts dir on sys.path so the flat
# `import profile_loader` resolves no matter how this file is invoked — direct
# script, as a `scripts.resolve_agent_profile` module, or via importlib.
if str(SCRIPTS_DIR) not in sys.path:  # pragma: no cover — import-time path bootstrap
    sys.path.insert(0, str(SCRIPTS_DIR))

import profile_loader  # noqa: E402  (path bootstrap above)

PROFILES_DIR = profile_loader.PROFILES_DIR

# The per-rule bindings files each profile ships (F020-ADR-002 rule/binding
# split). Listed in a stable order so output is deterministic.
BINDING_RULES: tuple[str, ...] = (
    "clean-code",
    "error-handling",
    "import-discipline",
)

NO_PROFILE_NOTE = "no active profile; top-level rules only"


@dataclass(frozen=True)
class ResolvedProfile:
    """The resolved form of a manifest's profile placeholders.

    Attributes:
        active_profiles: active profile names from profiles.lock (may be empty).
        bindings: repo-relative POSIX paths to each active profile's
            `*-bindings.md` files; the union across profiles, deterministically
            ordered. Empty when no profile is active.
        toolchain_summary: a short profile-sourced description of the active
            toolchain(s), or the top-level note when no profile is active.
            Never contains a literal `${...}` placeholder.
    """

    active_profiles: list[str]
    bindings: list[str]
    toolchain_summary: str


def _binding_paths(profile: str) -> list[str]:
    """Return repo-relative POSIX paths to a profile's shipped bindings files.

    A binding path is only claimed when its file exists on disk, so a profile
    name with no shipped dir (or a missing rule file) contributes nothing. The
    file is never opened — existence is the only fact read here.
    """
    profile_dir = PROFILES_DIR / profile
    paths: list[str] = []
    for rule in BINDING_RULES:
        relative = profile_dir / f"{rule}-bindings.md"
        if (REPO_ROOT / relative).is_file():
            paths.append(relative.as_posix())
    return paths


def _detection_markers(profile: str) -> list[str]:
    """Return a profile's detection.yaml `markers`, harness-anchored.

    Read against REPO_ROOT (not the caller's cwd) so the toolchain summary is
    identical regardless of where an agent invokes the resolver — the same
    harness-anchoring the binding paths use. Any absence, read error, or
    malformed shape degrades to an empty marker list.
    """
    detection_path = REPO_ROOT / PROFILES_DIR / profile / "detection.yaml"
    if not detection_path.is_file():
        return []
    try:
        data = yaml.safe_load(detection_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return []
    markers = data.get("markers") if isinstance(data, dict) else None
    if not isinstance(markers, list):
        return []
    return [marker for marker in markers if isinstance(marker, str) and marker]


def _toolchain_descriptor(profile: str) -> str:
    """Derive a one-line toolchain descriptor for a profile from its own source.

    Profile-sourced, never hardcoded per language: reads the profile's
    `detection.yaml` markers (e.g. package.json, tsconfig.json) when present.
    Falls back to the bare profile name when detection metadata is absent.
    """
    markers = _detection_markers(profile)
    if markers:
        return f"{profile} (markers: {', '.join(markers)})"
    return profile


def resolve(lock_path: Path | None = None) -> ResolvedProfile:
    """Resolve manifest profile placeholders against profiles.lock.

    Reuses `profile_loader.active_profiles()` for lock parsing. Returns the
    active profile names, the union of their bindings paths, and a
    profile-sourced toolchain summary. On an absent/empty lock returns the
    empty/top-level form. Always returns; never raises on these inputs.
    """
    active = profile_loader.active_profiles(lock_path)
    if not active:
        return ResolvedProfile(
            active_profiles=[],
            bindings=[],
            toolchain_summary=NO_PROFILE_NOTE,
        )

    bindings: list[str] = []
    descriptors: list[str] = []
    for profile in active:
        bindings.extend(_binding_paths(profile))
        descriptors.append(_toolchain_descriptor(profile))

    summary = "; ".join(descriptors)
    return ResolvedProfile(
        active_profiles=active,
        bindings=bindings,
        toolchain_summary=summary,
    )


def _render_text(resolved: ResolvedProfile) -> str:
    """Render the resolved profile as the inline form an agent reads."""
    profiles = ", ".join(resolved.active_profiles) or "(none)"
    lines = [
        f"active_profiles: {profiles}",
        f"toolchain_summary: {resolved.toolchain_summary}",
        "bindings:",
    ]
    if resolved.bindings:
        lines.extend(f"  - {path}" for path in resolved.bindings)
    else:
        lines.append("  (none — top-level rules only)")
    return "\n".join(lines)


def _cli_resolve(args: argparse.Namespace) -> int:
    lock = Path(args.lock) if args.lock else None
    resolved = resolve(lock)
    if args.format == "text":
        print(_render_text(resolved))
    else:
        print(
            json.dumps(
                {
                    "active_profiles": resolved.active_profiles,
                    "bindings": resolved.bindings,
                    "toolchain_summary": resolved.toolchain_summary,
                }
            )
        )
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="resolve_agent_profile.py",
        description=(
            "Resolve a profile-aware agent manifest's ${profiles} / "
            "${profile_bindings_template} placeholders against profiles.lock."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_resolve = sub.add_parser(
        "resolve",
        help="Emit active profiles + bindings paths + toolchain summary.",
    )
    p_resolve.add_argument(
        "--lock",
        default=None,
        help="Path to profiles.lock (default: profile_loader.DEFAULT_LOCK_PATH).",
    )
    p_resolve.add_argument(
        "--format",
        choices=("json", "text"),
        default="json",
        help="Output format: json (default) or text for inline agent reads.",
    )
    p_resolve.set_defaults(func=_cli_resolve)
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. argparse exits with code 2 on usage error."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
