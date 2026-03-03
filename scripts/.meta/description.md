# scripts/

**Purpose:** Utility scripts for maintaining the `.meta/` description tree. Currently contains a single reconciliation script that finds and manages stale `.meta/` descriptions across a project.

## Key Components
- `meta-reconcile.py` -- Python CLI for `.meta/` staleness management. Three modes: list stale directories (default), show detailed stale info (`--verbose`), and clear stale markers (`--clear [DIR]`). Walks the project tree to find `.meta/stale.json` markers created by the `hooks/git/post-commit` hook. Skips `.git`, `node_modules`, `__pycache__`, `dist`, `.venv`, and `venv` directories. The script handles bookkeeping only -- actual regeneration of `.meta/description.md` files is done by the `project-bootstrapper` agent. Returns exit code 0 if no stale markers found, 1 if stale markers exist (for CI gating).

## Dependencies
- Python standard library only (argparse, json, os, sys, datetime, pathlib) -- no external dependencies
- Reads `.meta/stale.json` files created by `hooks/git/post-commit`
- Referenced by `hooks/git/pre-push` which suggests running this script when stale markers are found
- Works in conjunction with the `project-bootstrapper` agent which performs the actual `.meta/` regeneration

## Patterns
- **Separation of concerns:** The script handles detection and marker management; the project-bootstrapper agent handles content generation. This keeps the script fast and deterministic.
- **CI-friendly exit codes:** Exit code 1 when stale markers exist allows CI pipelines to gate on `.meta/` freshness.

## Constraints
- Does not generate or modify `.meta/description.md` files -- only manages `stale.json` markers.
- Skips common non-source directories (`.git`, `node_modules`, `__pycache__`, etc.) to avoid false positives.
- Requires `stale.json` files to follow the format: `{"marked_at": "<ISO timestamp>", "changed_files": ["<path>", ...]}`.
