#!/bin/bash
# hooks/auto-checkpoint.sh
#
# Stop hook — auto-blocks session stop when context utilization is high
# AND the .etc_sdlc/checkpoint.md file is stale (or absent).
#
# F012 (2026-05-13). Source: venlink-platform proposal 2026-05-11.
#
# Trigger conditions (BOTH must hold):
#   1. context_window.used_percentage >= CHECKPOINT_CTX_THRESHOLD (default 85)
#   2. .etc_sdlc/checkpoint.md mtime > CHECKPOINT_STALE_MINUTES (default 30)
#      ago, OR the file is absent
#
# Threshold default of 85 (not 60) is chosen for opus 1M context windows
# where 60% = 600K tokens is overly conservative. Operators on smaller
# context windows (Sonnet, standard Opus 200K) can lower via env var.
#
# The hook cannot invoke /checkpoint directly — hooks run in bash, not
# inside Claude's context. Exit 2 surfaces the stderr message to the
# model and blocks the session stop, giving the model a chance to act.
#
# Field-availability caveat: .context_window.used_percentage is read by
# statusline.sh from the same JSON feed, but the Stop-hook input schema
# is not formally documented in Anthropic public docs as of 2026-05-13.
# The `// 0` default ensures safe-fail: if the field is absent, the
# threshold check fails (0 < 85), the hook exits 0, normal stop allowed.
# Operator should validate first activation by uncommenting the debug
# line below and confirming a non-zero CTX_PCT in a real high-context
# session.
#
# Exit codes:
#   0 = pass through (conditions not met; allow normal stop)
#   2 = block stop; emit AUTO-CHECKPOINT REQUIRED message to stderr

INPUT=$(cat)

# ── 1. Read context utilization from hook input JSON ─────────────────────────
CTX_PCT=$(echo "$INPUT" | jq -r '.context_window.used_percentage // 0 | floor')
# Uncomment for first-activation validation:
# echo "auto-checkpoint: CTX_PCT=${CTX_PCT}" >&2

# ── 2. Bail early if utilization is below threshold ──────────────────────────
THRESHOLD="${CHECKPOINT_CTX_THRESHOLD:-85}"
if [ "$CTX_PCT" -lt "$THRESHOLD" ]; then
  exit 0
fi

# ── 3. Resolve checkpoint path from input cwd ────────────────────────────────
CWD=$(echo "$INPUT" | jq -r '.cwd // "."')
PROJECT_ROOT=$(cd "$CWD" 2>/dev/null && git rev-parse --show-toplevel 2>/dev/null || echo "$CWD")  # repo-root anchor (#48)
CHECKPOINT="${PROJECT_ROOT}/.etc_sdlc/checkpoint.md"
STALE_MINUTES="${CHECKPOINT_STALE_MINUTES:-30}"

# ── 4. Determine staleness ───────────────────────────────────────────────────
AGE_MINUTES="unknown"
if [ ! -f "$CHECKPOINT" ]; then
  IS_STALE=1
else
  # BSD/macOS: stat -f %m. GNU: stat -c %Y. Fall through to 0 on both
  # failing (forces "unknown age", treated as stale to be safe).
  MTIME=$(stat -f %m "$CHECKPOINT" 2>/dev/null || stat -c %Y "$CHECKPOINT" 2>/dev/null || echo 0)
  NOW=$(date +%s)
  AGE_MINUTES=$(( (NOW - MTIME) / 60 ))
  if [ "$AGE_MINUTES" -gt "$STALE_MINUTES" ]; then
    IS_STALE=1
  else
    IS_STALE=0
  fi
fi

# ── 5. Both conditions met → block stop and demand checkpoint ────────────────
if [ "$IS_STALE" -eq 1 ]; then
  if [ ! -f "$CHECKPOINT" ]; then
    AGE_REPORT="checkpoint file absent"
  else
    AGE_REPORT="${AGE_MINUTES} minutes stale (threshold: ${STALE_MINUTES} min)"
  fi
  cat >&2 <<EOF
AUTO-CHECKPOINT REQUIRED

Context utilization is ${CTX_PCT}% (threshold: ${THRESHOLD}%) and
.etc_sdlc/checkpoint.md is ${AGE_REPORT}.

Run /checkpoint NOW before stopping. This saves orchestration state so
the next session can resume without reconstructing context from scratch.

After /checkpoint completes, you may stop normally.
EOF
  exit 2
fi

exit 0
