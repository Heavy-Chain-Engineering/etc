#!/bin/bash
# hooks/check-baseline-fresh.sh
#
# SessionStart hook (F-2026-06-10 brownfield architecture baseline; design.md
# Module Structure + "Risks/Sensitivity"). Cloned from check-profiles-fresh.sh.
#
# Surfaces, advisory-only, the state of .etc_sdlc/architecture-baseline.yaml so
# an agent never runs a whole session against a stale or absent baseline. It
# NEVER blocks — verdicts are stderr WARNs; the hard three-state gate lives in
# /build (baseline.py status).
#
# Three Pattern B stderr WARN paths (each exits 0):
#   1. Missing  → only on a BROWNFIELD-SHAPED repo (DOMAIN.md + PROJECT.md
#      present but no baseline). A repo with no etc tier-0 artifacts is "not yet
#      onboarded at all" → skip SILENTLY (no cry-wolf on greenfield/non-etc
#      repos). Substrings: "missing" + "architecture-baseline".
#   2. Stale    → baseline mtime older than BASELINE_STALENESS_DAYS (default 30,
#      env-overridable). Substrings: "stale" + "architecture-baseline".
#   3. Drift    → baseline file older than the workspace seam-map mirror source
#      (<workspace>/.etc_workspace/seam-map.yaml) — the mirror was regenerated
#      after the baseline, so the per-repo mirror may be out of sync (ADR-005).
#      Substrings: "drift" + "architecture-baseline".
#
# Every WARN names the exact backfill / refresh command:
#   /init-project --phase=baseline
#
# Pattern B format (design.md Contract / check-profiles-fresh precedent):
#   \n\n---\n\n**▶ Note:** <message>
#
# Telemetry: emits one JSONL row to .etc_sdlc/efficiency/turn-events.jsonl
#   {ts, event_type: "baseline_freshness", hook: "check-baseline-fresh",
#    outcome: "missing"|"stale"|"drift"|"fresh"|"skip"}  (best-effort).
#
# Exit codes:
#   0 always — SessionStart hooks never block.

# set -u: every variable is assigned before use (CWD/PROJECT_ROOT/BASELINE/
# SEAM_MAP/the mtime + age locals), env-knob reads use ${VAR:-default}, and the
# helper positionals ($1) are always supplied by their callers — no unset-var
# abort can fire. pipefail: the few pipelines either feed a fallback (`CWD=...||
# [[ -z ]]`) or carry `|| true`, so a failed pipe never aborts; pipefail only
# tightens `$?` reporting and is safe here.
set -uo pipefail

INPUT=$(cat)
CWD=$(printf '%s' "$INPUT" | jq -r '.cwd // empty' 2>/dev/null)

# If cwd is null/empty or jq is absent, fall back to process cwd.
if [[ -z "$CWD" ]]; then
  CWD="$(pwd)"
fi
PROJECT_ROOT=$(cd "$CWD" 2>/dev/null && git rev-parse --show-toplevel 2>/dev/null || echo "$CWD")  # repo-root anchor

BASELINE="${PROJECT_ROOT}/.etc_sdlc/architecture-baseline.yaml"
SEAM_MAP="${PROJECT_ROOT}/.etc_workspace/seam-map.yaml"

# ── Env-variable sanitization (mirrors PROFILES_LOCK_STALENESS_DAYS) ──────────
# Accept only a plain non-negative integer; fall back to default 30.
[[ "${BASELINE_STALENESS_DAYS:-30}" =~ ^[0-9]+$ ]] \
  || BASELINE_STALENESS_DAYS=30
STALENESS_DAYS="${BASELINE_STALENESS_DAYS:-30}"

# ── Helper: emit Pattern B stderr warning ────────────────────────────────────
_warn() {
  printf '\n\n---\n\n**▶ Note:** %s\n' "$1" >&2 2>/dev/null || true
}

# ── Helper: emit baseline_freshness telemetry row (best-effort) ──────────────
_emit_audit() {
  local outcome="$1"
  local log_dir="${PROJECT_ROOT}/.etc_sdlc/efficiency"
  local log_file="${log_dir}/turn-events.jsonl"
  local ts
  ts=$(date -u +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null || echo "")

  mkdir -p "$log_dir" 2>/dev/null || return 0

  if command -v jq >/dev/null 2>&1; then
    jq -n -c \
      --arg ts "$ts" \
      --arg hook "check-baseline-fresh" \
      --arg outcome "$outcome" \
      '{ts: $ts, event_type: "baseline_freshness", hook: $hook, outcome: $outcome}' \
      >> "$log_file" 2>/dev/null || true
  else
    # Fallback: hand-built JSONL (outcome is a closed-set scalar token).
    local out_escaped
    out_escaped=$(printf '%s' "$outcome" | tr -d '"\\')
    printf '{"ts":"%s","event_type":"baseline_freshness","hook":"check-baseline-fresh","outcome":"%s"}\n' \
      "$ts" "$out_escaped" >> "$log_file" 2>/dev/null || true
  fi
}

# ── Helper: mtime in epoch seconds (GNU stat then BSD stat) ──────────────────
_mtime() {
  stat -c '%Y' "$1" 2>/dev/null || stat -f '%m' "$1" 2>/dev/null || echo "0"
}

# The exact backfill command every WARN names.
BACKFILL_CMD="/init-project --phase=baseline"

# ── Step 1: Missing baseline ─────────────────────────────────────────────────
if [[ ! -f "$BASELINE" ]]; then
  # Only warn on a BROWNFIELD-SHAPED repo: it has etc tier-0 artifacts
  # (DOMAIN.md + PROJECT.md) but never had the baseline phase run. A repo with
  # no tier-0 artifacts is not onboarded at all — skip silently (no cry-wolf).
  if [[ -f "${PROJECT_ROOT}/DOMAIN.md" && -f "${PROJECT_ROOT}/PROJECT.md" ]]; then
    _warn "architecture-baseline is missing at ${BASELINE}. This repo is onboarded (DOMAIN.md + PROJECT.md present) but has no verified architecture baseline. Run '${BACKFILL_CMD}' to backfill it."
    _emit_audit "missing"
  else
    # Not an etc-onboarded repo — silent skip.
    _emit_audit "skip"
  fi
  exit 0
fi

# ── Step 2: Stale baseline (mtime older than the staleness window) ───────────
BASELINE_MTIME=$(_mtime "$BASELINE")
NOW_EPOCH=$(date +%s 2>/dev/null || echo "0")
STALENESS_SECS=$(( STALENESS_DAYS * 86400 ))
BASELINE_AGE=$(( NOW_EPOCH - BASELINE_MTIME ))

if [[ "$BASELINE_AGE" -gt "$STALENESS_SECS" ]]; then
  _warn "architecture-baseline is stale (${BASELINE_AGE}s old, threshold ${STALENESS_SECS}s). Re-verify it with '${BACKFILL_CMD}' so agents are not building against a drifted model."
  _emit_audit "stale"
  exit 0
fi

# ── Step 3: Drift — baseline older than the workspace seam-map source ────────
# In workspace mode the canonical seam-map.yaml is the editable source; each
# repo carries a regenerated read-only mirror inside its baseline. If the
# seam-map was edited after this baseline was written, the per-repo mirror is
# potentially out of sync until 'baseline.py sync-seams' regenerates it.
if [[ -f "$SEAM_MAP" ]]; then
  SEAM_MTIME=$(_mtime "$SEAM_MAP")
  if [[ "$SEAM_MTIME" -gt "$BASELINE_MTIME" ]]; then
    _warn "architecture-baseline has drift: the workspace seam-map (${SEAM_MAP}) is newer than this repo's baseline, so the per-repo seam mirror may be out of sync. Re-run '${BACKFILL_CMD}' (or 'baseline.py sync-seams') to refresh."
    _emit_audit "drift"
    exit 0
  fi
fi

# ── Step 4: Baseline present, fresh, and not behind the seam-map source ──────
_emit_audit "fresh"
exit 0
