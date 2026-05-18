#!/bin/bash
# hooks/check-code-quality.sh
#
# PreToolUse hook for Edit|Write operations. F020 profile-aware dispatch.
#
# Routes the file_path to the active profile's check-code-quality.sh.
# Behavior preserved for Python (BR-007). Adds typescript support via
# F021's profile. Other profiles WARN-skip per ADR-F020-003.
#
# Exit codes:
#   0 = allow (no violations, file outside any profile, or graceful degrade)
#   2 = block (active profile's gate found violations)

INPUT=$(cat)
CWD=$(printf '%s' "$INPUT" | jq -r '.cwd // "."' 2>/dev/null || echo ".")

# Locate dispatcher: prefer local repo, then global install
DISPATCH=""
if [[ -f "${CWD}/scripts/dispatch_profile.sh" ]]; then
  DISPATCH="${CWD}/scripts/dispatch_profile.sh"
elif [[ -f "${HOME}/.claude/scripts/dispatch_profile.sh" ]]; then
  DISPATCH="${HOME}/.claude/scripts/dispatch_profile.sh"
fi

# Graceful degrade: no dispatcher means we're outside an etc-installed
# project. Fall back to pre-F020 Python-only behavior so existing
# repos that haven't reinstalled don't regress (BR-007 zero-regression).
if [[ -z "$DISPATCH" ]]; then
  FILE_PATH=$(printf '%s' "$INPUT" | jq -r '.tool_input.file_path // empty')
  if [[ -z "$FILE_PATH" || "$FILE_PATH" != *.py ]]; then
    exit 0
  fi
  HOOK_DIR="$(cd "$(dirname "$0")" && pwd)"
  HELPERS_DIR="${HOOK_DIR}/helpers"
  if [[ ! -d "$HELPERS_DIR" ]]; then
    exit 0
  fi
  if [[ "$FILE_PATH" != /* ]]; then
    FILE_PATH="${CWD}/${FILE_PATH}"
  fi
  [[ ! -f "$FILE_PATH" ]] && exit 0
  VIOLATIONS=""
  COUNT=0
  for CHECK in check_mutable_globals.py check_noop_functions.py; do
    if [[ -f "${HELPERS_DIR}/${CHECK}" ]]; then
      OUT=$(python3 "${HELPERS_DIR}/${CHECK}" "$FILE_PATH" 2>/dev/null)
      EC=$?
      if [[ $EC -eq 1 && -n "$OUT" ]]; then
        VIOLATIONS="${VIOLATIONS}${OUT}\n"
        COUNT=$((COUNT + $(echo "$OUT" | wc -l | tr -d ' ')))
      fi
    fi
  done
  if [[ $COUNT -gt 0 ]]; then
    echo "" >&2
    echo "CODE QUALITY VIOLATIONS (${COUNT}):" >&2
    echo -e "$VIOLATIONS" | head -10 >&2
    exit 2
  fi
  exit 0
fi

# Normal path: replay stdin to the dispatcher
printf '%s' "$INPUT" | bash "$DISPATCH" check-code-quality
exit $?
