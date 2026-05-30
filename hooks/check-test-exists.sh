#!/bin/bash
# hooks/check-test-exists.sh
#
# PreToolUse hook for Edit|Write operations. Profile-aware TDD-gate
# dispatch (F020).
#
# Routes each edited file to its responsible profile's check-test-exists.sh.
# Supports legacy Claude payloads and Codex apply_patch payloads through the
# normalized hook payload helper.
#
# Exit codes:
#   0 = allow (delegated to profile gate, or no-profile WARN-skip)
#   2 = block (profile gate found a TDD violation)

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

# Locate the dispatch helper; prefer local checkout, fall back to the
# install-dir sibling (../scripts from this hook). Works under any
# --target-dir (default ~/.claude, dual ~/.claude-etc, project-scope).
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

has_pending_test() {
  local module="$1"
  local changed_file=""

  while IFS= read -r changed_file; do
    [[ -z "$changed_file" ]] && continue
    changed_file="${changed_file//\\//}"
    local changed_base
    changed_base=$(basename "$changed_file")
    if [[ "$changed_file" == tests/* && ( "$changed_base" == "test_${module}.py" || "$changed_base" == *test*"${module}"* ) ]]; then
      return 0
    fi
  done <<< "$EDITED_FILES"

  return 1
}

has_existing_test() {
  local module="$1"
  find "${CWD}/tests" \( -name "test_${module}.py" -o -name "*test*${module}*" \) 2>/dev/null | grep -q .
}

is_python_src_without_test_gap() {
  local file_path="$1"
  file_path="${file_path//\\//}"
  local rel_path="$file_path"
  if [[ "$file_path" == /* ]] || [[ "$file_path" =~ ^[A-Za-z]:/ ]]; then
    rel_path="${file_path#$CWD/}"
  fi

  if [[ "$rel_path" != src/* ]]; then
    return 1
  fi

  local basename
  basename=$(basename "$file_path")
  if [[ "$basename" == "__init__.py" || "$basename" == "py.typed" || "$basename" != *.py ]]; then
    return 1
  fi

  local module
  module=$(basename "$file_path" .py)
  if has_existing_test "$module" || has_pending_test "$module"; then
    return 1
  fi

  echo "BLOCKED: No test file found for '${module}'. Write a failing test first (Red/Green TDD)." >&2
  echo "Expected: tests/**/test_${module}.py" >&2
  return 0
}

has_pending_test_for_python_src() {
  local file_path="$1"
  file_path="${file_path//\\//}"
  local rel_path="$file_path"
  if [[ "$file_path" == /* ]] || [[ "$file_path" =~ ^[A-Za-z]:/ ]]; then
    rel_path="${file_path#$CWD/}"
  fi

  if [[ "$rel_path" != src/* ]]; then
    return 1
  fi

  local basename
  basename=$(basename "$file_path")
  if [[ "$basename" == "__init__.py" || "$basename" == "py.typed" || "$basename" != *.py ]]; then
    return 1
  fi

  local module
  module=$(basename "$file_path" .py)
  has_pending_test "$module"
}

while IFS= read -r FILE_PATH; do
  [[ -z "$FILE_PATH" ]] && continue
  FILE_PATH="${FILE_PATH//\\//}"

  if is_python_src_without_test_gap "$FILE_PATH"; then
    exit 2
  fi

  if has_pending_test_for_python_src "$FILE_PATH"; then
    continue
  fi

  if [[ -n "$DISPATCH" ]]; then
    synth_file_payload "$FILE_PATH" | bash "$DISPATCH" check-test-exists
    status=$?
    if [[ $status -ne 0 ]]; then
      exit $status
    fi
  fi
done <<< "$EDITED_FILES"

exit 0
