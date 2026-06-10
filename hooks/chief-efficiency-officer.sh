#!/bin/bash
# hooks/chief-efficiency-officer.sh
#
# F019 — Chief Efficiency Officer (Stop-hook reflection layer).
#
# Observes every Stop event, computes active-engagement on the current
# task vs operator baseline, writes evidence-cited observations to a
# queue + daily report, and (rarely) emits a threshold-push interrupt
# for the next agent turn.
#
# CRITICAL CONSTRAINTS (from F019 spec):
#   - Subject = OPERATOR, not agent.
#   - Evidence-based ONLY. Every observation cites a data point + baseline + gap.
#     No vibes. No hallucinated narrative.
#   - Active engagement time = sum of inter-turn gaps ≤ CEO_IDLE_THRESHOLD_MINUTES.
#     Larger gaps are sleep/break, not productivity loss.
#   - Hook NEVER blocks the Stop event. Reflection is the side effect.
#     Always exits 0; never propagates internal failures.
#
# Stop-hook ordering: this hook MUST run FIRST among Stop hooks so it
# captures the turn-end timestamp before any other hook can `exit 2`
# and block the Stop. Other Stop hooks (check-completion-discipline,
# auto-checkpoint) run after this one captures.
#
# Exit codes:
#   0 always (reflection is side-effect; never blocks)

INPUT=$(cat)
CWD=$(echo "$INPUT" | jq -r '.cwd // "."' 2>/dev/null || echo ".")
# Anchor .etc_sdlc/.sdlc to the git repo root, not the hook-input cwd (which is
# a subdir when launched from one, or when a subagent inherits it). Falls back
# to CWD when not inside a git repo (#48).
PROJECT_ROOT=$(cd "$CWD" 2>/dev/null && git rev-parse --show-toplevel 2>/dev/null || echo "$CWD")
NOW_ISO=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
NOW_EPOCH=$(date +%s)

# Tunables (env-overrideable)
IDLE_THRESHOLD_MIN="${CEO_IDLE_THRESHOLD_MINUTES:-5}"
SIGMA_PUSH="${CEO_SIGMA_PUSH:-3}"
SIGMA_PROPOSE="${CEO_SIGMA_PROPOSE:-2}"
MIN_BASELINE_FEATURES="${CEO_MIN_BASELINE_FEATURES:-5}"

# Output paths
EFF_DIR="${PROJECT_ROOT}/.etc_sdlc/efficiency"
TURN_EVENTS="${EFF_DIR}/turn-events.jsonl"
PROPOSALS_DIR="${EFF_DIR}/proposals"
DAILY_DIR="${EFF_DIR}/daily"
INJECT_FILE="${EFF_DIR}/inject-on-next-turn.md"
MUTE_FILE="${EFF_DIR}/mute.yaml"
TODAY=$(date -u +"%Y-%m-%d")
DAILY_FILE="${DAILY_DIR}/${TODAY}.md"

mkdir -p "$EFF_DIR" "$PROPOSALS_DIR" "$DAILY_DIR" 2>/dev/null || exit 0

# ── Step 1: Detect current task via cascading fallback ────────────────────
detect_current_task() {
  # 1. Most recently modified state.yaml under features/active/F<NNN>-*/
  local newest
  newest=$(find "${PROJECT_ROOT}/.etc_sdlc/features/active" -maxdepth 2 -name state.yaml -type f 2>/dev/null | head -10)
  if [ -n "$newest" ]; then
    local latest=""
    local latest_mtime=0
    while IFS= read -r f; do
      [ -z "$f" ] && continue
      local mt
      mt=$(stat -c %Y "$f" 2>/dev/null || stat -f %m "$f" 2>/dev/null || echo 0)
      if [ "$mt" -gt "$latest_mtime" ]; then
        latest_mtime=$mt
        latest=$f
      fi
    done <<< "$newest"
    if [ -n "$latest" ]; then
      basename "$(dirname "$latest")"
      return
    fi
  fi

  # 2. Most recently modified state.yaml under features/F<NNN>-*/ (flat path)
  newest=$(find "${PROJECT_ROOT}/.etc_sdlc/features" -maxdepth 2 -name state.yaml -type f 2>/dev/null \
    | grep -v "/active/" | grep -v "/shipped/" | head -10)
  if [ -n "$newest" ]; then
    local latest=""
    local latest_mtime=0
    while IFS= read -r f; do
      [ -z "$f" ] && continue
      local mt
      mt=$(stat -c %Y "$f" 2>/dev/null || stat -f %m "$f" 2>/dev/null || echo 0)
      if [ "$mt" -gt "$latest_mtime" ]; then
        latest_mtime=$mt
        latest=$f
      fi
    done <<< "$newest"
    if [ -n "$latest" ]; then
      basename "$(dirname "$latest")"
      return
    fi
  fi

  # 3-4. TodoWrite + non-cache file mtime: out of scope for v1 (hook can't
  # see TodoWrite state from disk). Fall through to "null".
  echo ""
}

CURRENT_TASK=$(detect_current_task)

# ── Step 2: Append turn event to JSONL (always — capture is load-bearing) ─
append_turn_event() {
  local event_id="turn-${NOW_EPOCH}-$$"
  if command -v jq >/dev/null 2>&1; then
    jq -n -c \
      --arg event_id "$event_id" \
      --arg ended_at "$NOW_ISO" \
      --arg cwd "$CWD" \
      --arg task "$CURRENT_TASK" \
      '{event_id: $event_id, ended_at: $ended_at, cwd: $cwd, current_task: $task}' \
      >> "$TURN_EVENTS" 2>/dev/null
  else
    printf '{"event_id":"%s","ended_at":"%s","cwd":"%s","current_task":"%s"}\n' \
      "$event_id" "$NOW_ISO" "$CWD" "$CURRENT_TASK" >> "$TURN_EVENTS" 2>/dev/null
  fi
}
append_turn_event

# ── Step 3: Check mute state ──────────────────────────────────────────────
is_muted() {
  [ ! -f "$MUTE_FILE" ] && return 1
  local until
  until=$(grep '^until:' "$MUTE_FILE" 2>/dev/null | head -1 | awk '{print $2}' | tr -d '"')
  [ -z "$until" ] && return 1
  local now_iso="$NOW_ISO"
  [[ "$now_iso" < "$until" ]] && return 0 || return 1
}

# ── Step 4: Compute active engagement on current task ─────────────────────
# Walk back through turn-events.jsonl until either:
#   - the current_task changes (different task before this), OR
#   - a gap > IDLE_THRESHOLD_MIN minutes opens between consecutive events
# Sum the inter-event gaps ≤ threshold to get active engagement time.

active_engagement_seconds=0
prev_iso=""
prev_epoch=0
TASK_START_EPOCH=0

if [ -n "$CURRENT_TASK" ] && [ -f "$TURN_EVENTS" ]; then
  # Read events in reverse-chronological order via tac/`tail -r`
  if command -v tac >/dev/null 2>&1; then
    REV_CMD="tac"
  else
    REV_CMD="tail -r"
  fi

  # We're iterating events most-recent-first. Process substitution (NOT a
  # pipe) is load-bearing: a pipe runs the while-loop in a subshell, so
  # active_engagement_seconds accumulated there was discarded on loop exit
  # and the parent always saw 0 — which made the 3-hour long-engagement
  # proposal (built after the stuck-loop incident) structurally dead
  # (audit init 2).
  while IFS= read -r line; do
    [ -z "$line" ] && continue
    if command -v jq >/dev/null 2>&1; then
      event_task=$(echo "$line" | jq -r '.current_task // ""' 2>/dev/null)
      event_iso=$(echo "$line" | jq -r '.ended_at // ""' 2>/dev/null)
    else
      event_task=$(echo "$line" | sed -n 's/.*"current_task":"\([^"]*\)".*/\1/p')
      event_iso=$(echo "$line" | sed -n 's/.*"ended_at":"\([^"]*\)".*/\1/p')
    fi
    [ -z "$event_iso" ] && continue

    # Stop walking if task changed
    if [ "$event_task" != "$CURRENT_TASK" ] && [ -n "$event_task" ]; then
      break
    fi

    # Compute gap from prev (next event in time) to this event
    if [ -n "$prev_iso" ]; then
      # macOS/BSD `date -j` parses; GNU `date -d` parses too.
      event_epoch=$(date -j -f "%Y-%m-%dT%H:%M:%SZ" "$event_iso" "+%s" 2>/dev/null \
                    || date -d "$event_iso" "+%s" 2>/dev/null || echo 0)
      [ "$event_epoch" -eq 0 ] && continue
      gap=$((prev_epoch - event_epoch))
      idle_threshold_seconds=$((IDLE_THRESHOLD_MIN * 60))
      if [ "$gap" -gt 0 ] && [ "$gap" -le "$idle_threshold_seconds" ]; then
        active_engagement_seconds=$((active_engagement_seconds + gap))
      else
        # Hit a sleep/break gap — stop walking
        break
      fi
    fi
    prev_iso="$event_iso"
    prev_epoch=$(date -j -f "%Y-%m-%dT%H:%M:%SZ" "$event_iso" "+%s" 2>/dev/null \
                 || date -d "$event_iso" "+%s" 2>/dev/null || echo 0)
  done < <($REV_CMD "$TURN_EVENTS" 2>/dev/null)
fi

# ── Step 5: Compute sandbox-bypass count since session start ──────────────
# "Session start" = most recent gap > IDLE_THRESHOLD_MIN in turn events, or
# the start of the file if no such gap exists. For v1 we use a simpler
# heuristic: bypasses today (since midnight UTC).
SANDBOX_BYPASS_FILE="${EFF_DIR}/sandbox-bypasses.jsonl"
bypass_count_today=0
if [ -f "$SANDBOX_BYPASS_FILE" ]; then
  bypass_count_today=$(grep -c "\"started_at\":\"${TODAY}T" "$SANDBOX_BYPASS_FILE" 2>/dev/null || echo 0)
fi

# ── Step 6: Update the daily report ───────────────────────────────────────
update_daily() {
  local engagement_min=$((active_engagement_seconds / 60))
  if [ ! -f "$DAILY_FILE" ]; then
    cat > "$DAILY_FILE" <<EOF
# Efficiency report — $TODAY

## Turn events
EOF
  fi
  cat >> "$DAILY_FILE" <<EOF

### Stop event @ $NOW_ISO
- current_task: ${CURRENT_TASK:-null}
- active_engagement_on_task: ${engagement_min}m (${active_engagement_seconds}s)
- sandbox_bypasses_today: $bypass_count_today
EOF
}
update_daily

# ── Step 7: Threshold-push decision (only when NOT muted + baseline ready) ─
# v1 keeps this conservative. Without a real baseline (< 5 features
# shipped), skip threshold-push entirely. With one, only fire when active
# engagement on current task significantly exceeds the operator's
# inter-ship gap p90 (sdlc_timing.py baseline). v1 leaves the actual
# z-score computation in a follow-up; for now, a simple absolute-threshold
# fallback: if active engagement > 3 hours on the SAME task without a new
# turn event recording task change, propose.

if is_muted; then
  exit 0
fi

if [ -z "$CURRENT_TASK" ]; then
  exit 0
fi

if [ "$active_engagement_seconds" -gt 10800 ]; then  # 3 hours
  PROPOSAL_PATH="${PROPOSALS_DIR}/${TODAY}-long-engagement-${CURRENT_TASK}.md"
  if [ ! -f "$PROPOSAL_PATH" ]; then
    engagement_h_m=$(awk -v s="$active_engagement_seconds" 'BEGIN{printf "%dh %02dm", int(s/3600), int((s%3600)/60)}')
    cat > "$PROPOSAL_PATH" <<EOF
---
proposal_id: ${TODAY}-long-engagement-${CURRENT_TASK}
observed_at: $NOW_ISO
current_task: $CURRENT_TASK
proposal_type: long_engagement
voice: chief_of_staff
---

# Long engagement on $CURRENT_TASK

## Data points

| Metric | Value | Baseline |
|---|---|---|
| Active engagement on $CURRENT_TASK | $engagement_h_m | — (3h threshold) |
| Sandbox bypasses today | $bypass_count_today | — |

## Observation

Active engagement on \`$CURRENT_TASK\` has reached $engagement_h_m. This
crosses the v1 absolute-threshold (3 hours). v1 uses a fixed threshold;
v2 will compare against sdlc_timing.py operator baseline.

## Suggested next move

Chief-of-Staff voice — these are observations, not directives:

- Step back: kill any in-flight processes, re-establish state.
- Re-read the spec for this task to confirm goal alignment.
- If stuck on diagnosis: invoke Codex adversarial review or run \`py-spy\` / \`pytest-timeout\` / \`pytest --junit-xml=\` to surface real failures.
- If progress is genuinely happening but slow: continue.

Dismiss this proposal via \`/efficiency review\` if it's a false positive.
EOF
  fi
fi

exit 0
