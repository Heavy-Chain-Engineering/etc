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

PYTHON=""
python3 -c "" 2>/dev/null && PYTHON=python3
if [[ -z "$PYTHON" ]]; then
  python -c "" 2>/dev/null && PYTHON=python
fi
[[ -z "$PYTHON" ]] && exit 0

HOOK_DIR="$(cd "$(dirname "$0")" && pwd)"
PAYLOAD_HELPER="${HOOK_DIR}/helpers/hook_payload.py"
CWD=$(printf '%s' "$INPUT" | "$PYTHON" "$PAYLOAD_HELPER" cwd) || exit 2
EDITED_FILES=$(printf '%s' "$INPUT" | "$PYTHON" "$PAYLOAD_HELPER" files) || exit 2
TRANSCRIPT=$(printf '%s' "$INPUT" | "$PYTHON" "$PAYLOAD_HELPER" transcript) || exit 2

# Normalize Windows backslashes to forward slashes so prefix-stripping and
# cache-key hashing match the production tests' expectations. No-op on POSIX.
CWD="${CWD//\\//}"
TRANSCRIPT="${TRANSCRIPT//\\//}"
PROJECT_ROOT=$(cd "$CWD" 2>/dev/null && git rev-parse --show-toplevel 2>/dev/null || echo "$CWD")  # repo-root anchor (#48)

# If no edited files, nothing to gate
if [[ -z "$EDITED_FILES" ]]; then
  exit 0
fi

# Check if .sdlc/state.json exists — if not, harness not initialized, allow all
STATE_FILE="${PROJECT_ROOT}/.sdlc/state.json"
if [[ ! -f "$STATE_FILE" ]]; then
  exit 0
fi

# --- per-subagent cache prologue ---
if [[ -n "$TRANSCRIPT" && -n "$PYTHON" ]]; then
  CACHE_KEY=$("$PYTHON" -c "import hashlib,sys; print(hashlib.sha256(sys.argv[1].encode()).hexdigest()[:16])" "$TRANSCRIPT" 2>/dev/null)
  MARKER_DIR="${PROJECT_ROOT}/.etc_sdlc/.hook-markers"
  MARKER="${MARKER_DIR}/${CACHE_KEY}-phase-gate"

  if [[ -L "$MARKER_DIR" ]]; then
    echo "Warning: .hook-markers is a symlink; skipping cache" >&2
    CACHE_KEY=""  # disable caching for this run
  elif [[ -f "$MARKER" && "$STATE_FILE" -ot "$MARKER" ]]; then
    exit 0  # cache hit — phase hasn't changed since last pass
  fi
fi
# --- end cache prologue ---

# Extract current_phase from state.json via jq (sidesteps the Windows
# python3 PATH question — jq is required by other hooks too).
PHASE=$(jq -r '.current_phase // ""' "$STATE_FILE" 2>/dev/null)
if [[ -z "$PHASE" ]]; then
  PHASE=$("$PYTHON" -c "
import json, sys
with open(sys.argv[1]) as f:
    state = json.load(f)
print(state.get('current_phase', ''))
" "$STATE_FILE" 2>/dev/null)
fi

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

while IFS= read -r FILE_PATH; do
  [[ -z "$FILE_PATH" ]] && continue
  FILE_PATH="${FILE_PATH//\\//}"

  # Make path relative to project root
  REL_PATH="$FILE_PATH"
  if [[ "$FILE_PATH" == /* ]] || [[ "$FILE_PATH" =~ ^[A-Za-z]:/ ]]; then
    REL_PATH="${FILE_PATH#$PROJECT_ROOT/}"
    REL_PATH="${REL_PATH#$CWD/}"
  fi

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
done <<< "$EDITED_FILES"

# Write marker on success — mtime must exceed state.json's so the next
# cache-hit check (-ot) sees the marker as strictly newer.
if [[ -n "${CACHE_KEY:-}" ]]; then
  mkdir -p "$MARKER_DIR" 2>/dev/null
  if [[ -n "$PYTHON" ]]; then
    "$PYTHON" -c "
import os, sys, time
marker, state = sys.argv[1], sys.argv[2]
open(marker, 'a').close()
now = time.time()
dep_mt = os.path.getmtime(state) if os.path.exists(state) else 0
ts = max(now, dep_mt) + 0.01
os.utime(marker, (ts, ts))
" "$MARKER" "$STATE_FILE" 2>/dev/null
  else
    # No Python available — fall back to plain touch; we lose the
    # mtime-bump-past-state-file invariant but keep the marker for caching.
    touch "$MARKER" 2>/dev/null
  fi
fi
exit 0
