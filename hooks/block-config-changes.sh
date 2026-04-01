#!/bin/bash
# hooks/block-config-changes.sh
#
# ConfigChange hook.
# Prevents the agent from modifying its own governance — settings, hooks,
# standards, or constraint configurations. The agent cannot loosen its
# own constraints.
#
# Exit codes:
#   0 = allow (change is safe or user-initiated)
#   2 = block (unauthorized governance modification)

INPUT=$(cat)
SOURCE=$(echo "$INPUT" | jq -r '.source // empty')
FILE_PATH=$(echo "$INPUT" | jq -r '.file_path // empty')

# Allow managed policy changes (admin-controlled)
if [[ "$SOURCE" == "policy_settings" ]]; then
  exit 0
fi

# Block changes to settings files that contain hook wiring
if [[ "$SOURCE" == "user_settings" || "$SOURCE" == "project_settings" || "$SOURCE" == "local_settings" ]]; then
  echo "BLOCKED: Agent cannot modify settings files that control its own governance." >&2
  echo "Settings changes must be made by the human operator or through the SDLC DSL." >&2
  echo "File: $FILE_PATH" >&2
  exit 2
fi

# Block changes to skills (could alter the /implement workflow)
if [[ "$SOURCE" == "skills" ]]; then
  echo "BLOCKED: Agent cannot modify skill definitions during execution." >&2
  echo "Skill changes must be made through the SDLC DSL and recompiled." >&2
  exit 2
fi

exit 0
