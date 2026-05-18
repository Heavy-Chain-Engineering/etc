#!/bin/bash
# standards/code/profiles/python/check-code-quality.sh
#
# Python-profile code-quality gate. Migrated from the pre-F020 monolithic
# hooks/check-code-quality.sh. Runs AST-based sub-checks via the same
# helper scripts under hooks/helpers/. Behavior is byte-equivalent for
# Python files (BR-007 zero-regression).
#
# Sub-checks:
#   CQ-001: Module-level mutable state (check_mutable_globals.py)
#   CQ-002: No-op functions (check_noop_functions.py)
#
# Contract:
#   Stdin: standard Claude Code hook JSON payload (file_path, cwd)
#   Exit:  0 = allow | 2 = block (violations found)

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')
CWD=$(echo "$INPUT" | jq -r '.cwd // "."')

# Defensive: profile dispatch should already filter by .py glob, but
# keep the explicit guard so this gate is safe to call directly.
if [[ "$FILE_PATH" != *.py ]]; then
  exit 0
fi

# Resolve absolute path
if [[ "$FILE_PATH" != /* ]]; then
  FILE_PATH="${CWD}/${FILE_PATH}"
fi

# Security: reject paths containing ..
if [[ "$FILE_PATH" == *..* ]]; then
  echo "BLOCKED: Suspicious file path containing '..' — ${FILE_PATH}" >&2
  exit 2
fi

# If the file doesn't exist yet (new file being created), allow it
if [[ ! -f "$FILE_PATH" ]]; then
  exit 0
fi

# Locate helpers — try repo-local first, then global install (~/.claude/)
HELPERS_DIR=""
if [[ -d "${CWD}/hooks/helpers" ]]; then
  HELPERS_DIR="${CWD}/hooks/helpers"
elif [[ -d "${HOME}/.claude/hooks/helpers" ]]; then
  HELPERS_DIR="${HOME}/.claude/hooks/helpers"
fi

# Graceful degrade: no helpers available means we can't run AST checks.
# Allow the operation rather than block (this is a non-etc-installed env).
if [[ -z "$HELPERS_DIR" ]]; then
  exit 0
fi

VIOLATIONS=""
VIOLATION_COUNT=0

# CQ-001: Global mutable state detection
if [[ -f "${HELPERS_DIR}/check_mutable_globals.py" ]]; then
  CQ001_OUTPUT=$(python3 "${HELPERS_DIR}/check_mutable_globals.py" "$FILE_PATH" 2>/dev/null)
  if [[ $? -eq 1 && -n "$CQ001_OUTPUT" ]]; then
    VIOLATIONS="${VIOLATIONS}${CQ001_OUTPUT}\n"
    VIOLATION_COUNT=$((VIOLATION_COUNT + $(echo "$CQ001_OUTPUT" | wc -l | tr -d ' ')))
  fi
fi

# CQ-002: No-op function detection
if [[ -f "${HELPERS_DIR}/check_noop_functions.py" ]]; then
  CQ002_OUTPUT=$(python3 "${HELPERS_DIR}/check_noop_functions.py" "$FILE_PATH" 2>/dev/null)
  if [[ $? -eq 1 && -n "$CQ002_OUTPUT" ]]; then
    VIOLATIONS="${VIOLATIONS}${CQ002_OUTPUT}\n"
    VIOLATION_COUNT=$((VIOLATION_COUNT + $(echo "$CQ002_OUTPUT" | wc -l | tr -d ' ')))
  fi
fi

if [[ $VIOLATION_COUNT -gt 0 ]]; then
  echo "" >&2
  echo "CODE QUALITY VIOLATIONS (${VIOLATION_COUNT}):" >&2
  echo -e "$VIOLATIONS" | head -10 >&2
  if [[ $VIOLATION_COUNT -gt 10 ]]; then
    echo "  ... and $((VIOLATION_COUNT - 10)) more" >&2
  fi
  echo "" >&2
  exit 2
fi

exit 0
