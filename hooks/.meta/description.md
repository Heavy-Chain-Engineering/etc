# hooks/

**Purpose:** 4 Claude Code hook scripts that mechanically enforce TDD discipline and project invariants on every file operation, plus 2 git hooks that track `.meta/` description staleness. Installed to `~/.claude/hooks/` by `install.sh` and wired into settings via `settings-hooks.json`.

## Key Components

### Claude Code Hooks (wired via settings-hooks.json)
- `check-test-exists.sh` -- PreToolUse hook for Edit/Write. Blocks edits to production source files (under `src/`) unless a corresponding test file (`tests/**/test_<module>.py`) exists. Enforces "write test first" in the TDD cycle. Skips `__init__.py`, `py.typed`, and non-Python files. Exit code 2 blocks the operation with a message to stderr.
- `check-invariants.sh` -- PreToolUse hook for Edit/Write. Reads `INVARIANTS.md` from the project root and component directories, extracts `**Verify:** \`command\`` patterns, runs each verify command, and blocks operations if any invariant is violated (non-empty stdout = violation). Walks up from the edited file's directory to collect component-level invariants. Exit code 2 blocks the operation.
- `mark-dirty.sh` -- PostToolUse hook for Edit/Write. Touches a `.tdd-dirty` marker file when production source code (under `src/`) is modified. Zero-cost breadcrumb for the verify-green Stop hook. Always exits 0 (never blocks).
- `verify-green.sh` -- Stop hook (runs when agent finishes responding). If `.tdd-dirty` exists, runs full verification: pytest with 98% coverage threshold, mypy type checking on `src/`, ruff linting on `src/` and `tests/`. Cleans up the dirty marker on success. Exit code 2 blocks agent completion. Uses `uv run` for all tool invocations.

### Git Hooks
- `git/post-commit` -- Post-commit git hook. Marks `.meta/description.md` files as stale when code in their directory tree changes. Writes `.meta/stale.json` with timestamp and list of changed files. Must complete in <100ms -- no network calls, no AI. Skips changes to `.meta/` files themselves.
- `git/pre-push` -- Pre-push git hook. Warns if any `.meta/description.md` files are stale (have `stale.json` markers). Does NOT block push by default -- set `META_BLOCK_PUSH=1` to block. Suggests running `scripts/meta-reconcile.py` or the project-bootstrapper to update.

## Dependencies
- Requires `jq` for JSON parsing in Claude Code hooks (reads tool_input and cwd from hook input)
- Requires `uv` for running pytest, mypy, and ruff in `verify-green.sh`
- Requires `python3` for `post-commit` stale marker JSON manipulation
- Wired into Claude Code via `settings-hooks.json` (PreToolUse, PostToolUse, Stop matchers)
- `check-invariants.sh` depends on `INVARIANTS.md` files following the format defined in `standards/process/invariants.md`
- Git hooks installed by `install.sh` to `.git/hooks/`

## Patterns
- **Three-phase TDD enforcement:** PreToolUse gates (test must exist before editing production code), PostToolUse tracking (dirty marker on production file changes), Stop verification (full test/type/lint suite before agent finishes).
- **Non-blocking vs. blocking:** `mark-dirty.sh` always exits 0 (informational), while `check-test-exists.sh`, `check-invariants.sh`, and `verify-green.sh` exit 2 to mechanically block operations.
- **Staleness tracking:** Git hooks create lightweight JSON markers that track which `.meta/` descriptions are out of date, enabling the reconciliation workflow without blocking development.

## Constraints
- Hook exit code semantics: 0 = allow, 2 = block. No other exit codes are used.
- `verify-green.sh` coverage threshold is 98% -- this matches the testing standards.
- `check-invariants.sh` has a 10-second timeout configured in `settings-hooks.json`. Verify commands in `INVARIANTS.md` should be fast (grep-based).
- Git hooks must complete fast (<100ms for post-commit) -- no network calls or AI invocations.
- All hooks read their input as JSON from stdin, extracting `tool_input.file_path` and `cwd` via `jq`.
