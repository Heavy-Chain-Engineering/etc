#!/bin/bash
# hooks/check-test-exists.sh
#
# PreToolUse hook for Edit|Write operations. Profile-aware TDD-gate
# dispatch (F020).
#
# Routes each file to its responsible profile's check-test-exists.sh.
# Files with no matching profile produce a stderr WARN and pass (BR-008
# warn-and-skip).
#
# Per ADR-F020-001 (profile-as-primitive) and BR-007 (Python migration
# preserves prior behavior).
#
# Exit codes:
#   0 = allow (delegated to profile gate, or no-profile WARN-skip)
#   2 = block (profile gate found a TDD violation)

INPUT=$(cat)

# Locate the dispatch helper; prefer local checkout, fall back to the
# install-dir sibling (../scripts from this hook). Works under any
# --target-dir (default ~/.claude, dual ~/.claude-etc, project-scope).
CWD=$(echo "$INPUT" | jq -r '.cwd // "."' 2>/dev/null || echo ".")
_ETC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DISPATCH=""
if [[ -f "${CWD}/scripts/dispatch_profile.sh" ]]; then
  DISPATCH="${CWD}/scripts/dispatch_profile.sh"
elif [[ -f "${_ETC_DIR}/scripts/dispatch_profile.sh" ]]; then
  DISPATCH="${_ETC_DIR}/scripts/dispatch_profile.sh"
fi

# Graceful degrade: if no dispatch helper available, fall back to the
# pre-F020 Python-only behavior so projects without the F020 install
# still get TDD enforcement on .py files.
if [[ -z "$DISPATCH" ]]; then
  FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')
  REL_PATH="$FILE_PATH"
  if [[ "$FILE_PATH" == /* ]]; then
    REL_PATH="${FILE_PATH#$CWD/}"
  fi
  if [[ "$REL_PATH" != src/* ]]; then exit 0; fi
  BASENAME=$(basename "$FILE_PATH")
  if [[ "$BASENAME" == "__init__.py" || "$BASENAME" == "py.typed" || "$BASENAME" != *.py ]]; then
    exit 0
  fi
  MODULE=$(basename "$FILE_PATH" .py)
  if ! find "${CWD}/tests" -name "test_${MODULE}.py" -o -name "*test*${MODULE}*" 2>/dev/null | grep -q .; then
    echo "BLOCKED: No test file found for '${MODULE}'. Write a failing test first (Red/Green TDD)." >&2
    echo "Expected: tests/**/test_${MODULE}.py" >&2
    exit 2
  fi
  exit 0
fi

# Route through the profile dispatcher
echo "$INPUT" | bash "$DISPATCH" check-test-exists
