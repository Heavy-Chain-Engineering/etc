#!/bin/bash
# standards/code/profiles/rust/check-test-exists.sh
#
# Rust-profile TDD gate. Edit/Write on a production .rs file under
# src/ is blocked unless one of:
#   (a) The file contains a #[cfg(test)] block (unit tests live next
#       to the code in Rust's convention).
#   (b) A corresponding integration test file exists at tests/<name>.rs.
#
# Contract:
#   Stdin: standard Claude Code hook JSON payload (file_path, cwd)
#   Exit:  0 = allow | 2 = block (no test coverage detected)

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')
CWD=$(echo "$INPUT" | jq -r '.cwd // "."')

REL_PATH="$FILE_PATH"
if [[ "$FILE_PATH" == /* ]]; then
  REL_PATH="${FILE_PATH#$CWD/}"
fi

# Only gate production source under src/
if [[ "$REL_PATH" != src/* ]]; then
  exit 0
fi

BASENAME=$(basename "$FILE_PATH")

# Skip non-.rs
if [[ "$BASENAME" != *.rs ]]; then
  exit 0
fi

# Skip conventional non-test-bearing files
case "$BASENAME" in
  lib.rs|main.rs|mod.rs) exit 0 ;;
esac

MODULE="${BASENAME%.rs}"

# Check (a): file contains a #[cfg(test)] block
if [ -f "$FILE_PATH" ] && grep -qE '^[[:space:]]*#\[cfg\(test\)\]' "$FILE_PATH" 2>/dev/null; then
  exit 0
fi

# Check (b): integration test at tests/<module>.rs
if [ -f "${CWD}/tests/${MODULE}.rs" ]; then
  exit 0
fi

# Check (c): integration test in tests/<module>/mod.rs (organized tests)
if [ -f "${CWD}/tests/${MODULE}/mod.rs" ]; then
  exit 0
fi

echo "[rust/check-test-exists] BLOCKED: No tests found for '${MODULE}'. Add #[cfg(test)] block in-file OR create tests/${MODULE}.rs." >&2
exit 2
