#!/bin/bash
# hooks/block-dangerous-commands.sh
#
# PreToolUse hook for Bash operations.
# Blocks destructive shell commands that could cause irreversible damage.
# The equivalent of "production access requires approval."
#
# Exit codes:
#   0 = allow the command
#   2 = block the command (with reason to stderr)

INPUT=$(cat)
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty')

if [[ -z "$COMMAND" ]]; then
  exit 0
fi

# ── Destructive file operations ──────────────────────────────────────────
# Block rm with recursive flag (-r, -rf, -fr, --recursive) on broad targets.
# Single file rm (even with -f) is allowed — -f just suppresses "not found" warnings.
if echo "$COMMAND" | grep -qE '^\s*rm\s+(-[a-zA-Z]*r[a-zA-Z]*\s|--recursive)'; then
  # Allow rm -rf on known-safe targets (build artifacts, caches)
  if echo "$COMMAND" | grep -qE 'rm\s+.*\b(node_modules|__pycache__|\.tdd-dirty|dist/|build/|\.pytest_cache|\.mypy_cache|\.ruff_cache)\b'; then
    exit 0
  fi
  echo "BLOCKED: Recursive rm command. Specify exact files or ask the user for confirmation." >&2
  exit 2
fi

# ── Destructive git operations ───────────────────────────────────────────
if echo "$COMMAND" | grep -qE 'git\s+push\s+.*--force|git\s+push\s+-f\b'; then
  echo "BLOCKED: Force push can destroy remote history. Use --force-with-lease or ask the user." >&2
  exit 2
fi

if echo "$COMMAND" | grep -qE 'git\s+reset\s+--hard'; then
  echo "BLOCKED: Hard reset discards uncommitted work. Stash first or ask the user." >&2
  exit 2
fi

if echo "$COMMAND" | grep -qE 'git\s+clean\s+.*-f'; then
  echo "BLOCKED: git clean -f permanently deletes untracked files. Ask the user." >&2
  exit 2
fi

if echo "$COMMAND" | grep -qE 'git\s+checkout\s+--\s+\.|git\s+restore\s+--\s+\.'; then
  echo "BLOCKED: Discarding all unstaged changes. Ask the user." >&2
  exit 2
fi

# ── Database destruction ─────────────────────────────────────────────────
if echo "$COMMAND" | grep -qiE 'DROP\s+(TABLE|DATABASE|SCHEMA|INDEX)|TRUNCATE\s+TABLE|DELETE\s+FROM\s+\w+\s*;?\s*$'; then
  echo "BLOCKED: Destructive database operation. This requires explicit user approval." >&2
  exit 2
fi

# ── System-level danger ──────────────────────────────────────────────────
if echo "$COMMAND" | grep -qE '>\s*/dev/sd|mkfs\.|dd\s+if=|chmod\s+-R\s+777|chown\s+-R'; then
  echo "BLOCKED: System-level destructive operation. Ask the user." >&2
  exit 2
fi

# ── Undisciplined git staging ─────────────────────────────────────────────
if echo "$COMMAND" | grep -qE 'git\s+add\s+(-A\b|--all\b|\.(\s|$))'; then
  echo "BLOCKED: 'git add -A' / 'git add .' stages everything blindly — including secrets, junk, and unintended files." >&2
  echo "Stage specific files by name: git add file1.py file2.py" >&2
  exit 2
fi

# ── Skip hooks / bypass safety ───────────────────────────────────────────
if echo "$COMMAND" | grep -qE -- '--no-verify|--skip-hooks|--dangerously'; then
  echo "BLOCKED: Attempting to bypass safety checks. The harness exists for a reason." >&2
  exit 2
fi

exit 0
