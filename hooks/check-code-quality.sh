#!/bin/bash
# hooks/check-code-quality.sh
#
# PreToolUse hook for Edit|Write operations. F020 profile-aware dispatch.
#
# Routes each edited file to the active profile's check-code-quality.sh.
# Supports legacy Claude payloads and Codex apply_patch payloads through the
# normalized hook payload helper.
#
# Exit codes:
#   0 = allow (no violations, file outside any profile, or graceful degrade)
#   2 = block (active profile's gate found violations)

set -o pipefail

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
CWD="${CWD//\\//}"

# If no edited files were provided, allow the operation.
if [[ -z "$EDITED_FILES" ]]; then
  exit 0
fi

# Locate dispatcher: prefer local repo, then sibling install dir.
# The hook lives at <install_dir>/hooks/check-code-quality.sh, so
# ../scripts/ is the installed scripts dir regardless of where the
# operator installed (default ~/.claude, dual ~/.claude-etc, etc).
_ETC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DISPATCH=""
if [[ -f "${CWD}/scripts/dispatch_profile.sh" ]]; then
  DISPATCH="${CWD}/scripts/dispatch_profile.sh"
elif [[ -f "${_ETC_DIR}/scripts/dispatch_profile.sh" ]]; then
  DISPATCH="${_ETC_DIR}/scripts/dispatch_profile.sh"
fi

synth_file_payload() {
  local file_path="$1"
  FILE_PATH="$file_path" "$PYTHON" -c '
import json
import os
import sys

payload = json.load(sys.stdin)
tool_input = payload.get("tool_input")
if not isinstance(tool_input, dict):
    tool_input = {}
tool_input["file_path"] = os.environ["FILE_PATH"]
payload["tool_input"] = tool_input
payload["tool_name"] = payload.get("tool_name") or "Edit"
print(json.dumps(payload))
' <<< "$INPUT"
}

run_python_fallback() {
  local file_path="$1"
  file_path="${file_path//\\//}"

  if [[ "$file_path" != *.py ]]; then
    return 0
  fi

  if [[ "$file_path" != /* ]] && [[ ! "$file_path" =~ ^[A-Za-z]:/ ]]; then
    file_path="${CWD}/${file_path}"
  fi

  if [[ "$file_path" == *..* ]]; then
    echo "BLOCKED: Suspicious file path containing '..' — ${file_path}" >&2
    return 2
  fi

  if [[ ! -f "$file_path" ]]; then
    return 0
  fi

  local helpers_dir="${HOOK_DIR}/helpers"
  if [[ ! -d "$helpers_dir" ]]; then
    return 0
  fi

  local violations=""
  local violation_count=0
  local output=""
  local exit_code=0

  for check in check_mutable_globals.py check_noop_functions.py; do
    if [[ -f "${helpers_dir}/${check}" ]]; then
      output=$("$PYTHON" "${helpers_dir}/${check}" "$file_path" 2>/dev/null)
      exit_code=$?
      if [[ $exit_code -eq 1 && -n "$output" ]]; then
        violations="${violations}${output}\n"
        violation_count=$((violation_count + $(echo "$output" | wc -l | tr -d ' ')))
      fi
    fi
  done

  if [[ $violation_count -gt 0 ]]; then
    echo "" >&2
    echo "CODE QUALITY VIOLATIONS (${violation_count}):" >&2
    echo -e "$violations" | head -10 >&2
    if [[ $violation_count -gt 10 ]]; then
      echo "  ... and $((violation_count - 10)) more" >&2
    fi
    echo "" >&2
    return 2
  fi

  return 0
}

while IFS= read -r FILE_PATH; do
  [[ -z "$FILE_PATH" ]] && continue
  FILE_PATH="${FILE_PATH//\\//}"

  if [[ -n "$DISPATCH" ]]; then
    synth_file_payload "$FILE_PATH" | bash "$DISPATCH" check-code-quality
    status=$?
    if [[ $status -ne 0 ]]; then
      exit $status
    fi
  else
    run_python_fallback "$FILE_PATH" || exit $?
  fi
done <<< "$EDITED_FILES"

exit 0
