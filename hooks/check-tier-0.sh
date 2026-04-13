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
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')
CWD=$(echo "$INPUT" | jq -r '.cwd // "."')

# If no file path, nothing to check
if [[ -z "$FILE_PATH" ]]; then
  exit 0
fi

# Find the repo root (prefer git top-level; fall back to cwd)
REPO_ROOT=$(cd "$CWD" 2>/dev/null && git rev-parse --show-toplevel 2>/dev/null)
if [[ -z "$REPO_ROOT" ]]; then
  REPO_ROOT="$CWD"
fi

# Allow edits to the Tier 0 files themselves — otherwise /init-project
# could never create them. Compare by basename + parent directory to
# handle symlink resolution (macOS /tmp → /private/tmp, etc.).
FILE_BASENAME=$(basename "$FILE_PATH")
FILE_DIR=$(cd "$(dirname "$FILE_PATH")" 2>/dev/null && pwd -P)
REPO_ROOT_RESOLVED=$(cd "$REPO_ROOT" 2>/dev/null && pwd -P)

if [[ "$FILE_DIR" == "$REPO_ROOT_RESOLVED" ]]; then
  case "$FILE_BASENAME" in
    DOMAIN.md|PROJECT.md|CLAUDE.md)
      exit 0
      ;;
  esac
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
