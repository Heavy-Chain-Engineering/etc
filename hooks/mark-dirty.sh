#!/bin/bash
# ~/.claude/hooks/mark-dirty.sh
#
# PostToolUse hook for Edit|Write operations.
# Touches a .tdd-dirty marker file when production source code is modified.
# The Stop hook (verify-green.sh) checks for this marker.
#
# This is a zero-cost breadcrumb — it just creates an empty file.
# Exit code is always 0 (never blocks).

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')
CWD=$(echo "$INPUT" | jq -r '.cwd // "."')

if [[ "$FILE_PATH" == */src/* || "$FILE_PATH" == src/* ]]; then
  touch "${CWD}/.tdd-dirty"
fi

exit 0
