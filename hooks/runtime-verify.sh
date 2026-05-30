#!/bin/bash
# hooks/runtime-verify.sh
#
# Behavioral / runtime verify dispatcher (Gap A, F-2026-05-30).
#
# Conductor-invoked script (NOT a Stop hook — ADR-001 dissolves the #47
# Stop->SubagentStop gap). Mirrors the F020 structural-gate dispatcher
# hooks/verify-green.sh: repo-root anchoring via git rev-parse, iteration
# over .etc_sdlc/profiles.lock, and the install-dir sibling fallback for
# the per-profile script path.
#
# Contract (ADR-001 / AGA-003), v1 additive-only:
#   stdin  : {"feature_path": <str>, "live_ac_ids": ["AC-3", ...], "cwd": <str>}
#   per-profile stdin  : {"feature_path": <str>, "live_ac_ids": [...]}  (JSON, never shell args)
#   per-profile stdout : {"results": [{"ac_id","status","evidence"}, ...]}
#   stdout : {"results": [...]}  — every active profile's results aggregated
#
# Warn-and-skip (stderr, non-fatal), parity with verify-green BR-008:
#   - profiles.lock absent/empty
#   - a profile's runtime-verify.sh is missing
# Per-profile time cap (AC-11): default 600s, override via RUNTIME_VERIFY_TIMEOUT.
# A profile exceeding the cap records each of its live_ac_ids as
# {status:"fail", evidence:"timeout >Ns"} and continues.
#
# Exit codes:
#   0 = dispatched (always, including warn-and-skip paths); per-AC verdicts live
#       in the aggregated `results`, not the exit code.

set -uo pipefail

# Per-profile time cap (seconds). Module constant; env-overridable (AC-11).
RUNTIME_VERIFY_TIMEOUT="${RUNTIME_VERIFY_TIMEOUT:-600}"

INPUT=$(cat)
CWD=$(echo "$INPUT" | jq -r '.cwd // "."')
PROJECT_ROOT=$(cd "$CWD" 2>/dev/null && git rev-parse --show-toplevel 2>/dev/null || echo "$CWD")  # repo-root anchor (#48)

# Re-emit the thin per-profile stdin contract (JSON on stdin, never shell args).
PROFILE_INPUT=$(echo "$INPUT" | jq -c '{feature_path: .feature_path, live_ac_ids: (.live_ac_ids // [])}')

# Aggregated results array (JSON), built up across profiles.
AGGREGATE='[]'

emit() {
  echo "{\"results\": ${AGGREGATE}}"
}

LOCK="${PROJECT_ROOT}/.etc_sdlc/profiles.lock"
if [ ! -f "$LOCK" ]; then
  echo "[runtime-verify] WARN: no profiles.lock found at ${LOCK}; skipping verification." >&2
  emit
  exit 0
fi

ACTIVE_COUNT=$(grep -c '^[a-z]' "$LOCK" 2>/dev/null || echo 0)
if [ "$ACTIVE_COUNT" -eq 0 ]; then
  echo "[runtime-verify] WARN: profiles.lock is empty; skipping verification." >&2
  emit
  exit 0
fi

# Resolve a profile's runtime-verify.sh, project-scope first then install-dir sibling.
resolve_gate() {
  local profile="$1"
  local gate="${PROJECT_ROOT}/standards/code/profiles/${profile}/runtime-verify.sh"
  if [ ! -f "$gate" ]; then
    local etc_dir
    etc_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
    gate="${etc_dir}/standards/code/profiles/${profile}/runtime-verify.sh"
  fi
  echo "$gate"
}

# Build a fail/timeout results array for every live AC of a timed-out profile (AC-11).
timeout_results() {
  echo "$PROFILE_INPUT" | jq -c \
    --arg evidence "timeout >${RUNTIME_VERIFY_TIMEOUT}s" \
    '[.live_ac_ids[] | {ac_id: ., status: "fail", evidence: $evidence}]'
}

while IFS= read -r PROFILE; do
  PROFILE=$(echo "$PROFILE" | tr -d '[:space:]')
  [ -z "$PROFILE" ] && continue

  GATE="$(resolve_gate "$PROFILE")"
  if [ ! -f "$GATE" ]; then
    echo "[runtime-verify] WARN: profile '${PROFILE}' has no runtime-verify.sh at ${GATE}" >&2
    continue
  fi

  echo "[runtime-verify] Running ${PROFILE} profile (cap ${RUNTIME_VERIFY_TIMEOUT}s)..." >&2
  GATE_OUTPUT=$(echo "$PROFILE_INPUT" | timeout "${RUNTIME_VERIFY_TIMEOUT}s" bash "$GATE" 2>/dev/null)
  GATE_EXIT=$?

  if [ "$GATE_EXIT" -eq 124 ]; then
    # timeout(1) returns 124 when the time cap is exceeded (AC-11).
    echo "[runtime-verify] WARN: profile '${PROFILE}' exceeded ${RUNTIME_VERIFY_TIMEOUT}s cap; recording fail." >&2
    PROFILE_RESULTS="$(timeout_results)"
  else
    # Read per-AC status from the profile's stdout, not its exit code (ADR-001).
    PROFILE_RESULTS=$(echo "$GATE_OUTPUT" | jq -c '.results // empty' 2>/dev/null)
    if [ -z "$PROFILE_RESULTS" ]; then
      echo "[runtime-verify] WARN: profile '${PROFILE}' produced no parseable results; skipping." >&2
      continue
    fi
  fi

  AGGREGATE=$(jq -c -n --argjson a "$AGGREGATE" --argjson b "$PROFILE_RESULTS" '$a + $b')
done < "$LOCK"

emit
exit 0
