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

# Tee stdin to a temp file so the per-profile gate sees the same payload
INPUT_FILE="$(mktemp -t dispatch-profile.XXXXXX)"
trap 'rm -f "$INPUT_FILE"' EXIT
cat > "$INPUT_FILE"

# Extract the file path from the payload
FILE_PATH=$(jq -r '.tool_input.file_path // empty' < "$INPUT_FILE" 2>/dev/null || true)
CWD=$(jq -r '.cwd // "."' < "$INPUT_FILE" 2>/dev/null || echo ".")

# If no file path provided, allow the operation (consistent with existing hooks)
if [[ -z "$FILE_PATH" ]]; then
  exit 0
fi

# Resolve repo root from CWD
REPO_ROOT="$CWD"

# Locate the profile loader CLI; prefer local checkout, fall back to ~/.claude/
LOADER=""
if [[ -f "${REPO_ROOT}/scripts/profile_loader.py" ]]; then
  LOADER="${REPO_ROOT}/scripts/profile_loader.py"
elif [[ -f "${HOME}/.claude/scripts/profile_loader.py" ]]; then
  LOADER="${HOME}/.claude/scripts/profile_loader.py"
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

# Locate the per-profile gate script
GATE_SCRIPT="${REPO_ROOT}/standards/code/profiles/${PROFILE}/${GATE_NAME}.sh"
if [[ ! -f "$GATE_SCRIPT" ]]; then
  echo "[${GATE_NAME}] WARN: profile '${PROFILE}' does not implement gate '${GATE_NAME}' at ${GATE_SCRIPT}" >&2
  exit 0
fi

# Delegate; the gate script reads the same stdin payload via the temp file
exec bash "$GATE_SCRIPT" < "$INPUT_FILE"
