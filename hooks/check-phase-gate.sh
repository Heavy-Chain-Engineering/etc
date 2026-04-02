#!/bin/bash
# hooks/check-phase-gate.sh
#
# PreToolUse hook for Edit|Write operations.
# Reads the current SDLC phase from .sdlc/state.json and blocks edits
# to files that are inappropriate for that phase.
#
# Phase rules enforce discipline: during Spec you write specs, not code.
# During Build you write code, not specs. Phase gating, mechanically enforced.
#
# Exit codes:
#   0 = allow the operation
#   2 = block the operation (with message to stderr)

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')
CWD=$(echo "$INPUT" | jq -r '.cwd // "."')

# If no file path, nothing to gate
if [[ -z "$FILE_PATH" ]]; then
  exit 0
fi

# Check if .sdlc/state.json exists — if not, harness not initialized, allow all
STATE_FILE="${CWD}/.sdlc/state.json"
if [[ ! -f "$STATE_FILE" ]]; then
  exit 0
fi

# Make path relative to project root
REL_PATH="$FILE_PATH"
if [[ "$FILE_PATH" == /* ]]; then
  REL_PATH="${FILE_PATH#$CWD/}"
fi

# Extract current_phase from state.json using python3
PHASE=$(python3 -c "
import json, sys
with open('$STATE_FILE') as f:
    state = json.load(f)
print(state.get('current_phase', ''))
" 2>/dev/null)

if [[ -z "$PHASE" ]]; then
  exit 0  # Could not determine phase — allow
fi

# Normalize phase to lowercase for matching
PHASE_LOWER=$(echo "$PHASE" | tr '[:upper:]' '[:lower:]')

# Check if path matches a pattern (prefix match on relative path)
matches() {
  local path="$1"
  shift
  for pattern in "$@"; do
    if [[ "$path" == ${pattern}* ]]; then
      return 0
    fi
  done
  return 1
}

# Phase-to-blocked-paths rules
# Each phase has a list of path prefixes that are BLOCKED.
BLOCKED=false
case "$PHASE_LOWER" in
  bootstrap)
    if matches "$REL_PATH" "src/" "tests/"; then
      BLOCKED=true
    fi
    ;;
  spec)
    if matches "$REL_PATH" "src/" "tests/"; then
      BLOCKED=true
    fi
    ;;
  design)
    if matches "$REL_PATH" "src/" "tests/"; then
      BLOCKED=true
    fi
    ;;
  decompose)
    if matches "$REL_PATH" "src/" "tests/" "spec/"; then
      BLOCKED=true
    fi
    ;;
  build)
    if matches "$REL_PATH" "spec/"; then
      BLOCKED=true
    fi
    ;;
  verify)
    if matches "$REL_PATH" "spec/" "src/"; then
      BLOCKED=true
    fi
    ;;
  ship)
    if matches "$REL_PATH" "src/" "tests/" "spec/"; then
      BLOCKED=true
    fi
    ;;
  evaluate)
    if matches "$REL_PATH" "src/" "tests/" "spec/"; then
      BLOCKED=true
    fi
    ;;
esac

if [[ "$BLOCKED" == "true" ]]; then
  echo "Phase '${PHASE}' does not allow edits to '${REL_PATH}'. Transition to the appropriate phase first." >&2
  exit 2
fi

exit 0
