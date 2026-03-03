#!/usr/bin/env python3
"""
.meta/ Reconciliation Script

Finds stale .meta/ descriptions in a project and either:
1. Reports which directories need regeneration (default)
2. Clears stale markers after agent regeneration (--clear)
3. Shows detailed stale info (--verbose)

This script handles the bookkeeping. The actual regeneration is done by
the project-bootstrapper agent, which reads directory contents and
produces .meta/description.md files.

Usage:
    python3 scripts/meta-reconcile.py [project_root]          # List stale
    python3 scripts/meta-reconcile.py --verbose [project_root] # Detailed info
    python3 scripts/meta-reconcile.py --clear [project_root]   # Clear all markers
    python3 scripts/meta-reconcile.py --clear path/to/dir      # Clear specific dir
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path


def find_stale_markers(root: Path) -> list[dict]:
    """Walk the project tree and find all .meta/stale.json files."""
    stale = []
    for dirpath, dirnames, filenames in os.walk(root):
        # Skip .git, node_modules, __pycache__, etc.
        dirnames[:] = [
            d for d in dirnames
            if d not in {".git", "node_modules", "__pycache__", "dist", ".venv", "venv"}
        ]
        if os.path.basename(dirpath) == ".meta" and "stale.json" in filenames:
            stale_path = Path(dirpath) / "stale.json"
            try:
                with open(stale_path) as f:
                    data = json.load(f)
                stale.append({
                    "meta_dir": Path(dirpath),
                    "parent_dir": Path(dirpath).parent,
                    "stale_file": stale_path,
                    "marked_at": data.get("marked_at", "unknown"),
                    "changed_files": data.get("changed_files", []),
                })
            except (json.JSONDecodeError, OSError) as e:
                print(f"Warning: Could not read {stale_path}: {e}", file=sys.stderr)
    return stale


def clear_marker(stale_file: Path) -> bool:
    """Remove a stale marker file."""
    try:
        stale_file.unlink()
        return True
    except OSError as e:
        print(f"Warning: Could not remove {stale_file}: {e}", file=sys.stderr)
        return False


def cmd_list(root: Path, verbose: bool = False) -> int:
    """List stale .meta/ directories."""
    markers = find_stale_markers(root)
    if not markers:
        print("No stale .meta/ descriptions found.")
        return 0

    print(f"Found {len(markers)} stale .meta/ description(s):\n")

    for m in markers:
        rel = m["parent_dir"].relative_to(root)
        print(f"  {rel}/.meta/")
        if verbose:
            print(f"    Marked at: {m['marked_at']}")
            print(f"    Changed files ({len(m['changed_files'])}):")
            for cf in m["changed_files"]:
                print(f"      - {cf}")
            print()

    if not verbose:
        print(f"\nRun with --verbose for details, or invoke project-bootstrapper to regenerate.")

    return len(markers)


def cmd_clear(root: Path, target: str | None = None) -> int:
    """Clear stale markers, optionally for a specific directory."""
    markers = find_stale_markers(root)
    if not markers:
        print("No stale markers to clear.")
        return 0

    cleared = 0
    for m in markers:
        if target:
            target_path = Path(target).resolve()
            if m["parent_dir"].resolve() != target_path:
                continue
        if clear_marker(m["stale_file"]):
            rel = m["parent_dir"].relative_to(root)
            print(f"  Cleared: {rel}/.meta/stale.json")
            cleared += 1

    print(f"\nCleared {cleared} marker(s).")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Find and manage stale .meta/ descriptions"
    )
    parser.add_argument(
        "root",
        nargs="?",
        default=".",
        help="Project root directory (default: current directory)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed stale info",
    )
    parser.add_argument(
        "--clear",
        nargs="?",
        const="__all__",
        default=None,
        metavar="DIR",
        help="Clear stale markers (optionally for a specific directory)",
    )

    args = parser.parse_args()
    root = Path(args.root).resolve()

    if not root.is_dir():
        print(f"Error: {root} is not a directory", file=sys.stderr)
        return 2

    if args.clear is not None:
        target = None if args.clear == "__all__" else args.clear
        return cmd_clear(root, target)
    else:
        count = cmd_list(root, args.verbose)
        return 1 if count > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
