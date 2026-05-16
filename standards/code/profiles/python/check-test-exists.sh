#!/bin/bash
# standards/code/profiles/python/check-test-exists.sh
#
# Python-profile TDD gate. Migrated from the pre-F020 monolithic
# hooks/check-test-exists.sh. Body is byte-equivalent for Python files;
# the .py-extension filter at the top-level dispatch makes the .py check
# here redundant but kept for defense-in-depth.
#
# Contract:
#   Stdin: standard Claude Code hook JSON payload (file_path, cwd)
#   Exit:  0 = allow | 2 = block (test missing for production .py source)

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')
CWD=$(echo "$INPUT" | jq -r '.cwd // "."')

# Make path relative to project root
REL_PATH="$FILE_PATH"
if [[ "$FILE_PATH" == /* ]]; then
  REL_PATH="${FILE_PATH#$CWD/}"
fi

# Only gate production source code (files under project's src/)
if [[ "$REL_PATH" != src/* ]]; then
  exit 0
fi

# Skip __init__.py, py.typed, and non-.py files
BASENAME=$(basename "$FILE_PATH")
if [[ "$BASENAME" == "__init__.py" || "$BASENAME" == "py.typed" || "$BASENAME" != *.py ]]; then
  exit 0
fi

MODULE=$(basename "$FILE_PATH" .py)

# Look for a corresponding test file
if ! find "${CWD}/tests" -name "test_${MODULE}.py" -o -name "*test*${MODULE}*" 2>/dev/null | grep -q .; then
  echo "[python/check-test-exists] BLOCKED: No test file found for '${MODULE}'. Write a failing test first (Red/Green TDD)." >&2
  echo "Expected: tests/**/test_${MODULE}.py" >&2
  exit 2
fi

exit 0
