#!/bin/bash
# scripts/dispatch_profile.sh
#
# F020 dispatch helper. Called by each generalized hook (verify-green,
# check-test-exists, check-code-quality, check-seam-evidence,
# check-completion-discipline) to route a single file event to the
# profile-specific gate script.
#
# Per ADR-F020-002 (centralized dispatch helper — earns its keep at 5
# duplicated patterns).
#
# Contract:
#   Stdin: the standard Claude Code hook JSON payload
#   Argv:  <gate-name>  (e.g., "verify-green", "check-test-exists")
#   Exit: 0 (success or WARN-skip) | 2 (gate found a violation and is blocking)

set -uo pipefail

GATE_NAME="${1:-}"
if [[ -z "$GATE_NAME" ]]; then
  echo "[dispatch_profile] FATAL: gate name required as argv[1]" >&2
  exit 2
fi

# Read stdin once into a variable so we can both parse it (for file_path)
# AND replay it to the per-profile gate. Avoids mktemp + temp-file pattern
# (sandbox-friendlier, simpler, no cleanup race).
INPUT=$(cat)

# Extract the file path from the payload
FILE_PATH=$(printf '%s' "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null || true)
CWD=$(printf '%s' "$INPUT" | jq -r '.cwd // "."' 2>/dev/null || echo ".")

# If no file path provided, allow the operation (consistent with existing hooks)
if [[ -z "$FILE_PATH" ]]; then
  exit 0
fi

# Resolve repo root from CWD
REPO_ROOT="$CWD"

# Install-dir locator. This script lives at <install_dir>/scripts/, so
# ../scripts is itself and ../standards is the install-time sibling
# regardless of --target-dir.
_ETC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Locate the profile loader CLI; prefer local checkout, fall back to the
# install-dir sibling. Works under any --target-dir.
LOADER=""
if [[ -f "${REPO_ROOT}/scripts/profile_loader.py" ]]; then
  LOADER="${REPO_ROOT}/scripts/profile_loader.py"
elif [[ -f "${_ETC_DIR}/scripts/profile_loader.py" ]]; then
  LOADER="${_ETC_DIR}/scripts/profile_loader.py"
fi

# Graceful degrade: if no loader available, allow the operation (running
# outside an etc-installed project)
if [[ -z "$LOADER" ]]; then
  exit 0
fi

LOCK_PATH="${REPO_ROOT}/.etc_sdlc/profiles.lock"

# Resolve file -> profile (empty stdout means no match)
PROFILE=$(python3 "$LOADER" profile-for "$FILE_PATH" --lock-path "$LOCK_PATH" 2>/dev/null || echo "")

# Per ADR-F020-003: warn-and-skip when no profile matches
if [[ -z "$PROFILE" ]]; then
  echo "[${GATE_NAME}] WARN: no profile matches ${FILE_PATH}" >&2
  exit 0
fi

# Locate the per-profile gate script — try repo-local first, then the
# install-dir sibling (../standards from this dispatcher).
GATE_SCRIPT="${REPO_ROOT}/standards/code/profiles/${PROFILE}/${GATE_NAME}.sh"
if [[ ! -f "$GATE_SCRIPT" ]]; then
  GATE_SCRIPT="${_ETC_DIR}/standards/code/profiles/${PROFILE}/${GATE_NAME}.sh"
fi
if [[ ! -f "$GATE_SCRIPT" ]]; then
  echo "[${GATE_NAME}] WARN: profile '${PROFILE}' does not implement gate '${GATE_NAME}' (looked under ${REPO_ROOT}/standards/code/profiles/${PROFILE}/ and ${_ETC_DIR}/standards/code/profiles/${PROFILE}/)" >&2
  exit 0
fi

# Delegate; replay stdin payload to the gate
printf '%s' "$INPUT" | bash "$GATE_SCRIPT"
exit $?
