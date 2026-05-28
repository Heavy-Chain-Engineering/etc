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
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')
CWD=$(echo "$INPUT" | jq -r '.cwd // "."')
TRANSCRIPT=$(echo "$INPUT" | jq -r '.transcript_path // empty')

# Normalize Windows backslashes to forward slashes so cache-key hashing
# matches the production tests' expectations. No-op on POSIX paths.
FILE_PATH="${FILE_PATH//\\//}"
CWD="${CWD//\\//}"
TRANSCRIPT="${TRANSCRIPT//\\//}"

# Detect the Python interpreter; on Windows bare `python3` may resolve to
# the Microsoft Store stub. Fall back to `python`; empty means no Python.
PYTHON=""
python3 -c "" 2>/dev/null && PYTHON=python3
if [[ -z "$PYTHON" ]]; then
  python -c "" 2>/dev/null && PYTHON=python
fi

# If no transcript available, allow (can't verify reading history)
if [[ -z "$TRANSCRIPT" || ! -f "$TRANSCRIPT" ]]; then
  exit 0
fi

# --- per-subagent cache prologue ---
if [[ -n "$PYTHON" ]]; then
  CACHE_KEY=$("$PYTHON" -c "import hashlib,sys; print(hashlib.sha256(sys.argv[1].encode()).hexdigest()[:16])" "$TRANSCRIPT" 2>/dev/null)
else
  CACHE_KEY=""
fi
MARKER_DIR="${CWD}/.etc_sdlc/.hook-markers"
MARKER="${MARKER_DIR}/${CACHE_KEY}-required-reading"

if [[ -L "$MARKER_DIR" ]]; then
  echo "Warning: .hook-markers is a symlink; skipping cache" >&2
  CACHE_KEY=""  # disable caching for this run
elif [[ -f "$MARKER" ]]; then
  # Cache hit if no task file is newer than the marker
  NEWER=$(find "${CWD}/.etc_sdlc/tasks" -name "*.yaml" -newer "$MARKER" 2>/dev/null | head -1)
  if [[ -z "$NEWER" ]]; then
    exit 0  # cache hit — this subagent already passed
  fi
  # A task file is newer — fall through to full check
fi
# --- end cache prologue ---

# Find the active task file (status: in_progress)
TASK_DIR="${CWD}/.etc_sdlc/tasks"
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

# Check if the file being edited is in this task's files_in_scope
# (If not, this edit might be from a different context — allow it)
REL_PATH="$FILE_PATH"
if [[ "$FILE_PATH" == /* ]] || [[ "$FILE_PATH" =~ ^[A-Za-z]:/ ]]; then
  REL_PATH="${FILE_PATH#$CWD/}"
fi

# IN_SCOPE check via awk YAML scan (sidesteps the Windows python3 PATH
# question — awk ships with Git for Windows). Matches the prior Python
# logic: each `files_in_scope` entry is either an exact match or a
# directory prefix on REL_PATH.
IN_SCOPE=no
while IFS= read -r scope_entry; do
  [[ -z "$scope_entry" ]] && continue
  scope_clean="${scope_entry%/}"
  if [[ "$REL_PATH" == "$scope_entry" || "$REL_PATH" == "${scope_clean}/"* ]]; then
    IN_SCOPE=yes
    break
  fi
done < <(awk '/^files_in_scope:/{flag=1;next} /^[a-zA-Z_]/{flag=0} flag && /^[[:space:]]*-/{sub(/^[[:space:]]*-[[:space:]]*/,""); print}' "$ACTIVE_TASK" 2>/dev/null)

if [[ "$IN_SCOPE" != "yes" ]]; then
  exit 0  # File not in task scope — allow (might be a different task)
fi

# Extract requires_reading from the active task — also via awk.
REQUIRED=$(awk '/^requires_reading:/{flag=1;next} /^[a-zA-Z_]/{flag=0} flag && /^[[:space:]]*-/{sub(/^[[:space:]]*-[[:space:]]*/,""); print}' "$ACTIVE_TASK" 2>/dev/null)

if [[ -z "$REQUIRED" ]]; then
  exit 0  # No required reading list — allow
fi

# Check the transcript for Read tool calls matching required files
# The transcript is JSONL — each line is a JSON object
MISSING=()
while IFS= read -r required_file; do
  [[ -z "$required_file" ]] && continue

  # Check if this file appears in a Read tool call in the transcript
  # Look for tool_name: "Read" with file_path matching
  if ! grep -q "\"file_path\".*$(echo "$required_file" | sed 's/[.[\*]/\\&/g')" "$TRANSCRIPT" 2>/dev/null; then
    MISSING+=("$required_file")
  fi
done <<< "$REQUIRED"

if [[ ${#MISSING[@]} -gt 0 ]]; then
  echo "BLOCKED: Task requires reading these files first:" >&2
  for m in "${MISSING[@]}"; do
    echo "  - $m" >&2
  done
  echo "" >&2
  echo "Read the required files before modifying code. The task file is: $ACTIVE_TASK" >&2
  exit 2
fi

# Write marker on success (cache-miss or invalidated-cache path)
if [[ -n "${CACHE_KEY:-}" ]]; then
  mkdir -p "$MARKER_DIR" 2>/dev/null
  touch "$MARKER" 2>/dev/null
fi
exit 0
