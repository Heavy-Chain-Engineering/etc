#!/bin/bash
# hooks/check-code-quality.sh
#
# PreToolUse hook for Edit|Write operations.
# Runs AST-based code quality checks on Python files via helper scripts.
#
# Sub-checks:
#   CQ-001: Module-level mutable state (hooks/helpers/check_mutable_globals.py)
#   CQ-002: No-op functions (hooks/helpers/check_noop_functions.py)
#
# Exit codes:
#   0 = allow the operation (no violations, non-Python file, or parse error)
#   2 = block the operation (violations found)

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')
CWD=$(echo "$INPUT" | jq -r '.cwd // "."')

# If no file path provided, allow the operation
if [[ -z "$FILE_PATH" ]]; then
  exit 0
fi

# Only analyze .py files — skip non-Python edits silently (EC-005)
if [[ "$FILE_PATH" != *.py ]]; then
  exit 0
fi

# Resolve absolute path
if [[ "$FILE_PATH" != /* ]]; then
  FILE_PATH="${CWD}/${FILE_PATH}"
fi

# Security: reject paths containing .. or outside the project
if [[ "$FILE_PATH" == *..* ]]; then
  echo "BLOCKED: Suspicious file path containing '..' — ${FILE_PATH}" >&2
  exit 2
fi

# If the file doesn't exist yet (new file being created), allow it
if [[ ! -f "$FILE_PATH" ]]; then
  exit 0
fi

# Locate helper scripts relative to this hook's directory
HOOK_DIR="$(cd "$(dirname "$0")" && pwd)"
HELPERS_DIR="${HOOK_DIR}/helpers"

# Track violations
VIOLATIONS=""
VIOLATION_COUNT=0

# Run CQ-001: Global mutable state detection
if [[ -f "${HELPERS_DIR}/check_mutable_globals.py" ]]; then
  CQ001_OUTPUT=$(python3 "${HELPERS_DIR}/check_mutable_globals.py" "$FILE_PATH" 2>/dev/null)
  CQ001_EXIT=$?
  if [[ $CQ001_EXIT -eq 1 && -n "$CQ001_OUTPUT" ]]; then
    VIOLATIONS="${VIOLATIONS}${CQ001_OUTPUT}\n"
    VIOLATION_COUNT=$((VIOLATION_COUNT + $(echo "$CQ001_OUTPUT" | wc -l | tr -d ' ')))
  fi
fi

# Run CQ-002: No-op function detection
if [[ -f "${HELPERS_DIR}/check_noop_functions.py" ]]; then
  CQ002_OUTPUT=$(python3 "${HELPERS_DIR}/check_noop_functions.py" "$FILE_PATH" 2>/dev/null)
  CQ002_EXIT=$?
  if [[ $CQ002_EXIT -eq 1 && -n "$CQ002_OUTPUT" ]]; then
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
  echo "Fix the violations or add '# cq-exempt: CQ-NNN -- <reason>' to exempt specific lines." >&2
  exit 2
fi

exit 0
