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
# Normalize Windows backslashes; no-op on POSIX paths.
CWD="${CWD//\\//}"

# Detect the Python interpreter; on Windows bare `python3` may resolve to
# the Microsoft Store stub. The fallback block below needs it.
PYTHON=""
python3 -c "" 2>/dev/null && PYTHON=python3
if [[ -z "$PYTHON" ]]; then
  python -c "" 2>/dev/null && PYTHON=python
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

# Graceful degrade: no dispatcher means we're outside an etc-installed
# project. Fall back to pre-F020 Python-only behavior so existing
# repos that haven't reinstalled don't regress (BR-007 zero-regression).
if [[ -z "$DISPATCH" ]]; then
  # No Python available means the AST helpers below can't run — degrade
  # silently (Python-only fallback hits its safety floor on Windows).
  [[ -z "$PYTHON" ]] && exit 0
  FILE_PATH=$(printf '%s' "$INPUT" | jq -r '.tool_input.file_path // empty')
  FILE_PATH="${FILE_PATH//\\//}"
  if [[ -z "$FILE_PATH" || "$FILE_PATH" != *.py ]]; then
    exit 0
  fi
  HOOK_DIR="$(cd "$(dirname "$0")" && pwd)"
  HELPERS_DIR="${HOOK_DIR}/helpers"
  if [[ ! -d "$HELPERS_DIR" ]]; then
    exit 0
  fi
  if [[ "$FILE_PATH" != /* ]] && [[ ! "$FILE_PATH" =~ ^[A-Za-z]:/ ]]; then
    FILE_PATH="${CWD}/${FILE_PATH}"
  fi
  [[ ! -f "$FILE_PATH" ]] && exit 0
  VIOLATIONS=""
  COUNT=0
  for CHECK in check_mutable_globals.py check_noop_functions.py; do
    if [[ -f "${HELPERS_DIR}/${CHECK}" ]]; then
      OUT=$("$PYTHON" "${HELPERS_DIR}/${CHECK}" "$FILE_PATH" 2>/dev/null)
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
