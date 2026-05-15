#!/bin/bash
# hooks/sandbox-bypass-tracker.sh
#
# F019 PreToolUse hook — tracks when an agent invokes Bash with
# `dangerouslyDisableSandbox: true`. Appends one JSONL line per
# bypass event to .etc_sdlc/efficiency/sandbox-bypasses.jsonl for
# the Chief Efficiency Officer Stop hook to consume.
#
# This hook NEVER blocks. Capture is its only side effect. The CEO
# uses bypass-count-per-session as one of its evidence signals.
#
# Schema per appended line:
#   {"event_id", "started_at", "command_snippet", "description"}
#
# command_snippet is truncated to 100 chars; description is captured
# verbatim from the Bash invocation's description field.

INPUT=$(cat)
CWD=$(echo "$INPUT" | jq -r '.cwd // "."' 2>/dev/null || echo ".")

# Only act when this PreToolUse event is for a Bash invocation with
# the bypass flag set. Anything else: silent pass-through.
BYPASS=$(echo "$INPUT" | jq -r '.tool_input.dangerouslyDisableSandbox // false' 2>/dev/null || echo "false")
if [ "$BYPASS" != "true" ]; then
  exit 0
fi

CMD=$(echo "$INPUT" | jq -r '.tool_input.command // ""' 2>/dev/null || echo "")
DESC=$(echo "$INPUT" | jq -r '.tool_input.description // ""' 2>/dev/null || echo "")

# Truncate command to 100 chars (operator-readable; not full forensics)
CMD_SNIPPET=$(printf '%s' "$CMD" | head -c 100)

# Generate a coarse event id from timestamp + pid
EVENT_ID="bypass-$(date +%s)-$$"
STARTED_AT=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

# Output directory: .etc_sdlc/efficiency/
LOG_DIR="${CWD}/.etc_sdlc/efficiency"
LOG_FILE="${LOG_DIR}/sandbox-bypasses.jsonl"

mkdir -p "$LOG_DIR" 2>/dev/null || exit 0

# Build the JSONL line. Use jq if available; otherwise hand-construct.
if command -v jq >/dev/null 2>&1; then
  jq -n -c \
    --arg event_id "$EVENT_ID" \
    --arg started_at "$STARTED_AT" \
    --arg command_snippet "$CMD_SNIPPET" \
    --arg description "$DESC" \
    '{event_id: $event_id, started_at: $started_at, command_snippet: $command_snippet, description: $description}' \
    >> "$LOG_FILE" 2>/dev/null
else
  # Fallback: minimal hand-built JSONL (no full JSON-escape but adequate
  # for our scalar fields. command_snippet and description may have
  # quotes — strip them aggressively to avoid breaking the JSONL line.)
  CMD_ESC=$(printf '%s' "$CMD_SNIPPET" | tr -d '\\"\n')
  DESC_ESC=$(printf '%s' "$DESC" | tr -d '\\"\n')
  printf '{"event_id":"%s","started_at":"%s","command_snippet":"%s","description":"%s"}\n' \
    "$EVENT_ID" "$STARTED_AT" "$CMD_ESC" "$DESC_ESC" >> "$LOG_FILE" 2>/dev/null
fi

# Never block.
exit 0
