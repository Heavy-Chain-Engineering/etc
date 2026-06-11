#!/bin/bash
# hooks/check-tier-0.sh
#
# PreToolUse hook for Edit|Write operations.
# Blocks code changes when Tier 0 domain context files are missing at repo root.
# Tier 0 = the two files every agent must be able to read to orient:
#   - DOMAIN.md    (what this business is, stakes, canonical terms)
#   - PROJECT.md   (what this codebase is, where resources live)
#
# Read-only exploration (Read, Grep, Bash) is allowed even without Tier 0,
# so agents can investigate. But the first attempt to modify code is blocked
# with a clear message pointing to /init-project.
#
# Exit codes:
#   0 = allow the operation
#   2 = block the operation (with message to stderr)

INPUT=$(cat)
HOOK_DIR="$(cd "$(dirname "$0")" && pwd)"
PAYLOAD_HELPER="${HOOK_DIR}/helpers/hook_payload.py"
CWD=$(printf '%s' "$INPUT" | python3 "$PAYLOAD_HELPER" cwd) || exit 2
EDITED_FILES=$(printf '%s' "$INPUT" | python3 "$PAYLOAD_HELPER" files) || exit 2

# If no edited files, nothing to check
if [[ -z "$EDITED_FILES" ]]; then
  exit 0
fi

# Find the repo root (prefer git top-level; fall back to cwd)
REPO_ROOT=$(cd "$CWD" 2>/dev/null && git rev-parse --show-toplevel 2>/dev/null)
if [[ -z "$REPO_ROOT" ]]; then
  REPO_ROOT="$CWD"
fi

NEEDS_TIER_0=false
while IFS= read -r FILE_PATH; do
  [[ -z "$FILE_PATH" ]] && continue

  # Allow edits to the Tier 0 files themselves — otherwise /init-project
  # could never create them.
  #
  # ARCHITECTURE.md is self-exempt ONLY (F-2026-06-10): it is the brownfield
  # normative tier-0 artifact, created by /init-project --phase=baseline, so
  # its own creation must not be blocked. It is deliberately NOT added to the
  # MISSING block condition below — a missing ARCHITECTURE.md never blocks
  # (brownfield-only artifact, forward-only).
  REL_PATH="$FILE_PATH"
  if [[ "$FILE_PATH" == /* ]]; then
    REL_PATH="${FILE_PATH#$REPO_ROOT/}"
  fi
  case "$REL_PATH" in
    DOMAIN.md|PROJECT.md|CLAUDE.md|ARCHITECTURE.md)
      ;;
    *)
      NEEDS_TIER_0=true
      ;;
  esac
done <<< "$EDITED_FILES"

if [[ "$NEEDS_TIER_0" == false ]]; then
  exit 0
fi

# Check for Tier 0 files at repo root
MISSING=()
if [[ ! -f "$REPO_ROOT/DOMAIN.md" ]]; then
  MISSING+=("DOMAIN.md")
fi
if [[ ! -f "$REPO_ROOT/PROJECT.md" ]]; then
  MISSING+=("PROJECT.md")
fi

if [[ ${#MISSING[@]} -eq 0 ]]; then
  exit 0  # Tier 0 is complete — allow
fi

# Block with a loud, actionable message
{
  echo "BLOCKED: Tier 0 domain context is missing from repo root."
  echo ""
  echo "Missing file(s):"
  for m in "${MISSING[@]}"; do
    echo "  - $REPO_ROOT/$m"
  done
  echo ""
  echo "Why: agents operating without DOMAIN.md fabricate business assumptions,"
  echo "and without PROJECT.md cannot orient on where resources live. Every"
  echo "factual claim an agent makes should be grounded in Tier 0 + docs/sources/."
  echo ""
  echo "Fix: run /init-project to scaffold the Tier 0 files. If the project"
  echo "already has a technical scaffold, run /init-project --phase=domain"
  echo "to generate DOMAIN.md and PROJECT.md only."
  echo ""
  echo "Read-only exploration (Read, Grep, Bash) is still allowed — use it to"
  echo "gather context that will inform the DOMAIN.md you create."
} >&2

exit 2
