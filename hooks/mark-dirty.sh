#!/bin/bash
# hooks/mark-dirty.sh
#
# PostToolUse hook for Edit|Write operations.
# Touches a .tdd-dirty marker file when production source code is modified.
# The Stop hook (verify-green.sh) checks for this marker.
#
# This is a zero-cost breadcrumb — it just creates an empty file.
# Exit code is always 0 (never blocks).

INPUT=$(cat)
HOOK_DIR="$(cd "$(dirname "$0")" && pwd)"
PAYLOAD_HELPER="${HOOK_DIR}/helpers/hook_payload.py"
CWD=$(printf '%s' "$INPUT" | python3 "$PAYLOAD_HELPER" cwd) || exit 0
EDITED_FILES=$(printf '%s' "$INPUT" | python3 "$PAYLOAD_HELPER" files) || exit 0

while IFS= read -r FILE_PATH; do
  [[ -z "$FILE_PATH" ]] && continue
  if [[ "$FILE_PATH" == */src/* || "$FILE_PATH" == src/* ]]; then
    touch "${CWD}/.tdd-dirty"
    break
  fi
done <<< "$EDITED_FILES"

exit 0
