#!/bin/bash
# hooks/check-profiles-fresh.sh
#
# SessionStart hook. Checks whether .etc_sdlc/profiles.lock is fresh.
#
# Three Pattern B stderr WARN paths (each exits 0 — never blocks):
#   1. Missing lock  → WARN with substrings: "missing"  + "profiles.lock"
#   2. Stale lock    → WARN with substrings: "stale"    + "profiles.lock"
#      (mtime older than PROFILES_LOCK_STALENESS_DAYS, default 7, env-overrideable)
#   3. Drift         → WARN with substrings: "drift"    + "profiles.lock"
#      (locked set ≠ current detect_profiles.py output)
#
# Per BR-005 (F022 spec.md) and Contract 3 (F022 design.md).
# Pattern B format: \n\n---\n\n**▶ Note:** <message>
#
# BR-009: Emits one JSONL row to .etc_sdlc/efficiency/turn-events.jsonl
#   {ts, event_type: "profile_dispatch", hook: "check-profiles-fresh",
#    profiles: [...], outcome: "missing"|"stale"|"drift"|"fresh"}
#
# Exit codes:
#   0 always — SessionStart hooks never block.

INPUT=$(cat)
CWD=$(echo "$INPUT" | jq -r '.cwd // empty' 2>/dev/null)

# If cwd is null/empty or jq is absent, fall back to process cwd.
if [[ -z "$CWD" ]]; then
  CWD="$(pwd)"
fi
PROJECT_ROOT=$(cd "$CWD" 2>/dev/null && git rev-parse --show-toplevel 2>/dev/null || echo "$CWD")  # repo-root anchor (#48)

LOCK="${PROJECT_ROOT}/.etc_sdlc/profiles.lock"

# ── Env-variable sanitization (mirrors F021 DIAGNOSTIC_INVESTIGATION_TURNS) ──
# Accept only a plain non-negative integer; fall back to default 7.
[[ "${PROFILES_LOCK_STALENESS_DAYS:-7}" =~ ^[0-9]+$ ]] \
  || PROFILES_LOCK_STALENESS_DAYS=7
STALENESS_DAYS="${PROFILES_LOCK_STALENESS_DAYS:-7}"

# ── Helper: emit Pattern B stderr warning ────────────────────────────────────
_warn() {
  printf '\n\n---\n\n**▶ Note:** %s\n' "$1" >&2 2>/dev/null || true
}

# ── Helper: emit profile_dispatch audit-log row (best-effort) ────────────────
_emit_audit() {
  local profiles_json="$1"
  local outcome="$2"
  local log_dir="${PROJECT_ROOT}/.etc_sdlc/efficiency"
  local log_file="${log_dir}/turn-events.jsonl"
  local ts
  ts=$(date -u +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null || echo "")

  mkdir -p "$log_dir" 2>/dev/null || return 0

  if command -v jq >/dev/null 2>&1; then
    jq -n -c \
      --arg ts "$ts" \
      --arg hook "check-profiles-fresh" \
      --arg outcome "$outcome" \
      --argjson profiles "$profiles_json" \
      '{ts: $ts, event_type: "profile_dispatch", hook: $hook, profiles: $profiles, outcome: $outcome}' \
      >> "$log_file" 2>/dev/null || true
  else
    # Fallback: hand-built JSONL (safe for scalar fields without special chars)
    local out_escaped
    out_escaped=$(printf '%s' "$outcome" | tr -d '"\\')
    printf '{"ts":"%s","event_type":"profile_dispatch","hook":"check-profiles-fresh","profiles":%s,"outcome":"%s"}\n' \
      "$ts" "$profiles_json" "$out_escaped" >> "$log_file" 2>/dev/null || true
  fi
}

# ── Step 1: Check for missing lock ───────────────────────────────────────────
if [[ ! -f "$LOCK" ]]; then
  _warn "profiles.lock is missing at ${LOCK}. Run 'python3 scripts/detect_profiles.py --write-lock' to generate it."
  _emit_audit "[]" "missing"
  exit 0
fi

# ── Step 2: Check for stale lock (mtime) ─────────────────────────────────────
LOCK_MTIME=$(stat -c '%Y' "$LOCK" 2>/dev/null || stat -f '%m' "$LOCK" 2>/dev/null || echo "0")
NOW_EPOCH=$(date +%s 2>/dev/null || echo "0")
STALENESS_SECS=$(( STALENESS_DAYS * 86400 ))
LOCK_AGE=$(( NOW_EPOCH - LOCK_MTIME ))

# Read locked profiles for audit log
LOCKED_PROFILES=$(grep -v '^\s*$' "$LOCK" 2>/dev/null | sort | tr '\n' ' ' | sed 's/ *$//')
# Build JSON array of locked profiles for audit row
LOCKED_JSON="[]"
if command -v jq >/dev/null 2>&1; then
  LOCKED_JSON=$(grep -v '^\s*$' "$LOCK" 2>/dev/null \
    | jq -Rs 'split("\n") | map(select(length > 0))' 2>/dev/null \
    || echo "[]")
fi

if [[ "$LOCK_AGE" -gt "$STALENESS_SECS" ]]; then
  _warn "profiles.lock is stale (${LOCK_AGE}s old, threshold ${STALENESS_SECS}s). Re-run 'python3 scripts/detect_profiles.py --write-lock' to refresh."
  _emit_audit "$LOCKED_JSON" "stale"
  exit 0
fi

# ── Step 3: Re-run detect_profiles.py and compare sets ───────────────────────
# Locate detect_profiles.py: $CWD/scripts/ then hook-adjacent scripts/
HOOK_DIR="$(cd "$(dirname "$0")" 2>/dev/null && pwd || echo "")"
DETECT_PY=""
if [[ -f "${CWD}/scripts/detect_profiles.py" ]]; then
  DETECT_PY="${CWD}/scripts/detect_profiles.py"
elif [[ -n "$HOOK_DIR" && -f "${HOOK_DIR}/../scripts/detect_profiles.py" ]]; then
  DETECT_PY="${HOOK_DIR}/../scripts/detect_profiles.py"
fi

if [[ -z "$DETECT_PY" ]] || ! command -v python3 >/dev/null 2>&1; then
  # Cannot run detection — degrade gracefully; warn about staleness only if
  # we already know the lock exists (Step 2 passed). Emit fresh outcome since
  # we can't confirm drift.
  _emit_audit "$LOCKED_JSON" "fresh"
  exit 0
fi

# Run detection against CWD repo root
DETECTED=$(python3 "$DETECT_PY" --repo-root "$CWD" 2>/dev/null | sort || echo "")
LOCKED_SORTED=$(grep -v '^\s*$' "$LOCK" 2>/dev/null | sort || echo "")

if [[ "$DETECTED" != "$LOCKED_SORTED" ]]; then
  _warn "profiles.lock has drift: locked set [$(echo "$LOCKED_SORTED" | tr '\n' ' '| sed 's/ *$//')]  ≠  detected set [$(echo "$DETECTED" | tr '\n' ' ' | sed 's/ *$//')]. Re-run 'python3 scripts/detect_profiles.py --write-lock' to sync."
  _emit_audit "$LOCKED_JSON" "drift"
  exit 0
fi

# ── Step 4: Lock is fresh and matches detection ───────────────────────────────
_emit_audit "$LOCKED_JSON" "fresh"
exit 0
