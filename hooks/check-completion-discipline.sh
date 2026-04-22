#!/bin/bash
# hooks/check-completion-discipline.sh
#
# Stop hook — enforces standards/process/completion-discipline.md
# via system-state inspection (not language matching).
#
# Blocks the stop if either of two signals indicates unfinished work:
#
#   1. .tdd-dirty marker is present
#      → code was modified but ci-gate.sh hasn't verified it
#
#   2. Any task in .etc_sdlc/features/*/tasks/*.yaml has
#      status: in_progress
#      → formal work was started and not closed
#
# If neither signal fires, the session is either conversational
# or formally completed; allow the stop silently.
#
# If a signal fires, block with a message that tells the agent the
# valid paths out: complete the work, formally escalate, or
# formally block via tasks.py set-status.
#
# This hook is language-agnostic — it does NOT regex on quit-phrases.
# The model can phrase its stop however it wants; what matters is
# whether the state of work is finished or formally handed off.
#
# Exit codes:
#   0 = allow stop (no unfinished-work signals)
#   2 = block stop (signals present; stderr has remediation)

INPUT=$(cat)
CWD=$(echo "$INPUT" | jq -r '.cwd // "."')

# If we can't determine cwd, allow — we can't evaluate state without it.
if [[ -z "$CWD" || "$CWD" == "." ]]; then
  exit 0
fi

# ── Signal 1: TDD dirty marker ──────────────────────────────────────────

DIRTY="${CWD}/.tdd-dirty"
SIGNAL_DIRTY=false
if [[ -f "$DIRTY" ]]; then
  SIGNAL_DIRTY=true
fi

# ── Signal 2: in_progress tasks ─────────────────────────────────────────
#
# Scan .etc_sdlc/features/*/tasks/*.yaml for 'status: in_progress'.
# Use grep instead of tasks.py because this hook must work even when
# the user has no tasks.py installed or when the path varies.

SIGNAL_INPROGRESS_COUNT=0
TASKS_GLOB="${CWD}/.etc_sdlc/features"
if [[ -d "$TASKS_GLOB" ]]; then
  SIGNAL_INPROGRESS_COUNT=$(grep -rhE '^status:[[:space:]]*in_progress[[:space:]]*$' \
    "$TASKS_GLOB"/*/tasks/*.yaml 2>/dev/null | wc -l | tr -d ' ')
fi

SIGNAL_INPROGRESS=false
if [[ "$SIGNAL_INPROGRESS_COUNT" -gt 0 ]]; then
  SIGNAL_INPROGRESS=true
fi

# ── Decision ────────────────────────────────────────────────────────────

if [[ "$SIGNAL_DIRTY" == "false" && "$SIGNAL_INPROGRESS" == "false" ]]; then
  # No unfinished-work signals; allow the stop.
  exit 0
fi

# ── Block with actionable message ───────────────────────────────────────

echo "" >&2
echo "COMPLETION DISCIPLINE: Unfinished work detected." >&2
echo "" >&2
echo "Signals:" >&2

if [[ "$SIGNAL_DIRTY" == "true" ]]; then
  echo "  - .tdd-dirty is present (code modified but not verified)" >&2
fi

if [[ "$SIGNAL_INPROGRESS" == "true" ]]; then
  echo "  - ${SIGNAL_INPROGRESS_COUNT} task(s) have status: in_progress" >&2
fi

echo "" >&2
echo "You cannot stop the session while work is mid-flight." >&2
echo "Valid paths out (pick one):" >&2
echo "" >&2
echo "  1. Complete the work." >&2
echo "     - Verify tests pass (ci-gate.sh will clear .tdd-dirty)" >&2
echo "     - Update task status to 'completed' via:" >&2
echo "         python3 ~/.claude/scripts/tasks.py set-status <id> completed" >&2
echo "" >&2
echo "  2. Formally escalate." >&2
echo "     - Produce an ## ESCALATION block per" >&2
echo "       standards/process/completion-discipline.md rule 2" >&2
echo "     - Mark affected task(s) escalated:" >&2
echo "         python3 ~/.claude/scripts/tasks.py set-status <id> escalated" >&2
echo "" >&2
echo "  3. Formally block on an external dependency." >&2
echo "     - python3 ~/.claude/scripts/tasks.py set-status <id> blocked" >&2
echo "" >&2
echo "You do not quit conversationally. See" >&2
echo "standards/process/completion-discipline.md for the full standard." >&2
echo "" >&2

exit 2
