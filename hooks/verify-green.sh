#!/bin/bash
# hooks/verify-green.sh
#
# Stop hook. Profile-aware verify-green dispatch (F020).
#
# Runs when an agent is about to finish responding. If .tdd-dirty exists
# (production code was modified), iterates every active profile and runs
# each one's verify-green.sh sequentially. Any failure blocks completion
# (exit 2). All green clears the .tdd-dirty marker.
#
# Per ADR-F020-001 (profile-as-primitive), ADR-F020-003 (warn-and-skip),
# and BR-007 (Python migration preserves prior behavior — when only the
# python profile is active, this script's behavior is byte-equivalent
# to the pre-F020 monolithic hooks/verify-green.sh).
#
# Exit codes:
#   0 = verification passed (or no .tdd-dirty, or no active profiles)
#   2 = verification failed (blocks completion)

INPUT=$(cat)
CWD=$(echo "$INPUT" | jq -r '.cwd // "."')
PROJECT_ROOT=$(cd "$CWD" 2>/dev/null && git rev-parse --show-toplevel 2>/dev/null || echo "$CWD")  # repo-root anchor (#48)

# Only proceed if .tdd-dirty exists (production code was modified)
if [ ! -f "${CWD}/.tdd-dirty" ]; then
  exit 0
fi

LOCK="${PROJECT_ROOT}/.etc_sdlc/profiles.lock"
if [ ! -f "$LOCK" ]; then
  # No profiles configured. Warn and skip per BR-008.
  echo "[verify-green] WARN: no profiles.lock found at ${LOCK}; skipping verification." >&2
  exit 0
fi

# Count active profiles for the summary
ACTIVE_COUNT=$(grep -c '^[a-z]' "$LOCK" 2>/dev/null || echo 0)
if [ "$ACTIVE_COUNT" -eq 0 ]; then
  echo "[verify-green] WARN: profiles.lock is empty; skipping verification." >&2
  exit 0
fi

# Iterate active profiles; each runs its own verify-green
RAN_ANY=0
while IFS= read -r PROFILE; do
  # Strip whitespace; skip empty lines
  PROFILE=$(echo "$PROFILE" | tr -d '[:space:]')
  [ -z "$PROFILE" ] && continue

  GATE="${CWD}/standards/code/profiles/${PROFILE}/verify-green.sh"
  if [ ! -f "$GATE" ]; then
    # Fall back to the install-dir sibling. Works under any --target-dir
    # (default ~/.claude, dual ~/.claude-etc, project-scope).
    _ETC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
    GATE="${_ETC_DIR}/standards/code/profiles/${PROFILE}/verify-green.sh"
  fi
  if [ -f "$GATE" ]; then
    echo "[verify-green] Running ${PROFILE} profile..." >&2
    GATE_OUTPUT=$(echo "$INPUT" | bash "$GATE" 2>&1)
    GATE_EXIT=$?
    if [ $GATE_EXIT -ne 0 ]; then
      echo "$GATE_OUTPUT" >&2
      exit $GATE_EXIT
    fi
    echo "$GATE_OUTPUT" >&2
    RAN_ANY=1
  else
    echo "[verify-green] WARN: profile '${PROFILE}' has no verify-green.sh at ${GATE}" >&2
  fi
done < "$LOCK"

# If no profile gates fired, leave .tdd-dirty in place (nothing was verified)
if [ "$RAN_ANY" -eq 0 ]; then
  echo "[verify-green] WARN: no profile gate fired; .tdd-dirty preserved." >&2
  exit 0
fi

# All profile gates ran green — clear .tdd-dirty
rm -f "${CWD}/.tdd-dirty"
echo "[verify-green] All ${ACTIVE_COUNT} profile(s) green; cleared .tdd-dirty." >&2
exit 0
