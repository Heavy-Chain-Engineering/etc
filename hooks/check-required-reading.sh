#!/bin/bash
# hooks/check-required-reading.sh
#
# PreToolUse hook for Edit|Write operations.
# Checks whether the agent has read the files declared in the active task's
# requires_reading list before attempting code changes.
#
# This turns "did the agent gather enough context?" from a judgment call
# into a deterministic checklist: task file declares what must be read,
# hook verifies it was read.
#
# Exit codes:
#   0 = allow (all required reading done, or no active task)
#   2 = block (required files not yet read)

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
CLIENT=$(printf '%s' "$INPUT" | "$PYTHON" "$PAYLOAD_HELPER" client) || exit 2
TRANSCRIPT=$(printf '%s' "$INPUT" | "$PYTHON" "$PAYLOAD_HELPER" transcript) || exit 2

# If no edited files are present, nothing is in task scope.
if [[ -z "$EDITED_FILES" ]]; then
  exit 0
fi

# Normalize Windows backslashes to forward slashes so cache-key hashing
# matches the production tests' expectations. No-op on POSIX paths.
CWD="${CWD//\\//}"
TRANSCRIPT="${TRANSCRIPT//\\//}"
PROJECT_ROOT=$(cd "$CWD" 2>/dev/null && git rev-parse --show-toplevel 2>/dev/null || echo "$CWD")  # repo-root anchor (#48)

# --- per-subagent cache prologue ---
CACHE_KEY=""
if [[ -n "$TRANSCRIPT" && -f "$TRANSCRIPT" ]]; then
  CACHE_KEY=$("$PYTHON" -c "import hashlib,sys; print(hashlib.sha256(sys.argv[1].encode()).hexdigest()[:16])" "$TRANSCRIPT" 2>/dev/null)
fi
if [[ -n "$CACHE_KEY" ]]; then
  MARKER_DIR="${PROJECT_ROOT}/.etc_sdlc/.hook-markers"
  MARKER="${MARKER_DIR}/${CACHE_KEY}-required-reading"

  if [[ -L "$MARKER_DIR" ]]; then
    echo "Warning: .hook-markers is a symlink; skipping cache" >&2
    CACHE_KEY=""  # disable caching for this run
  elif [[ -f "$MARKER" ]]; then
    # Cache hit if no task file is newer than the marker
    NEWER=$(find "${PROJECT_ROOT}/.etc_sdlc/tasks" -name "*.yaml" -newer "$MARKER" 2>/dev/null | head -1)
    if [[ -z "$NEWER" ]]; then
      exit 0  # cache hit — this subagent already passed
    fi
    # A task file is newer — fall through to full check
  fi
fi
# --- end cache prologue ---

# Find the active task file (status: in_progress)
TASK_DIR="${PROJECT_ROOT}/.etc_sdlc/tasks"
if [[ ! -d "$TASK_DIR" ]]; then
  exit 0  # No task system active — allow
fi

# Find in-progress task files
ACTIVE_TASK=""
for task_file in "$TASK_DIR"/*.yaml; do
  [[ -f "$task_file" ]] || continue
  if grep -q "status:.*in_progress" "$task_file" 2>/dev/null; then
    ACTIVE_TASK="$task_file"
    break
  fi
done

if [[ -z "$ACTIVE_TASK" ]]; then
  exit 0  # No active task — allow
fi

EDITED_FILES_ENV="$EDITED_FILES" "$PYTHON" "${HOOK_DIR}/helpers/required_reading.py" "$ACTIVE_TASK" "$CLIENT" "$TRANSCRIPT" "$TASK_DIR" "$PROJECT_ROOT"
CHECK_EXIT=$?
if [[ $CHECK_EXIT -ne 0 ]]; then
  exit "$CHECK_EXIT"
fi

# Write marker on success (cache-miss or invalidated-cache path)
if [[ -n "${CACHE_KEY:-}" ]]; then
  mkdir -p "$MARKER_DIR" 2>/dev/null
  touch "$MARKER" 2>/dev/null
fi
exit 0
