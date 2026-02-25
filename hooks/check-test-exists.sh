#!/bin/bash
# ~/.claude/hooks/check-test-exists.sh
#
# PreToolUse hook for Edit|Write operations.
# Blocks edits to production source files unless a corresponding test file exists.
# This enforces the "write test first" part of red/green TDD.
#
# Exit codes:
#   0 = allow the operation
#   2 = block the operation (with message to stderr)

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')
CWD=$(echo "$INPUT" | jq -r '.cwd // "."')

# Make path relative to project root to avoid false matches
# (e.g. /Users/jason/src/ containing /src/ in the user's home path)
REL_PATH="$FILE_PATH"
if [[ "$FILE_PATH" == /* ]]; then
  REL_PATH="${FILE_PATH#$CWD/}"
fi

# Only gate production source code (files under project's src/)
if [[ "$REL_PATH" == src/* ]]; then
  # Skip __init__.py, py.typed, and non-Python files
  BASENAME=$(basename "$FILE_PATH")
  if [[ "$BASENAME" == "__init__.py" || "$BASENAME" == "py.typed" || "$BASENAME" != *.py ]]; then
    exit 0
  fi

  # Extract module name (without .py extension)
  MODULE=$(basename "$FILE_PATH" .py)

  # Look for a corresponding test file
  if ! find "${CWD}/tests" -name "test_${MODULE}.py" -o -name "*test*${MODULE}*" 2>/dev/null | grep -q .; then
    echo "BLOCKED: No test file found for '${MODULE}'. Write a failing test first (Red/Green TDD)." >&2
    echo "Expected: tests/**/test_${MODULE}.py" >&2
    exit 2
  fi
fi

exit 0
