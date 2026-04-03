#!/bin/bash
# hooks/reinject-context.sh
#
# SessionStart hook (matcher: compact).
# Re-injects critical project context after context compaction.
# When Claude's context window fills up and gets summarized,
# important operational details can be lost. This hook restores them.
#
# Output to stdout becomes additionalContext for Claude.
# Exit code is always 0.

INPUT=$(cat)
CWD=$(echo "$INPUT" | jq -r '.cwd // "."')

echo "## Post-Compaction Context Recovery"
echo ""

# Current SDLC phase
if [[ -f "${CWD}/.sdlc/state.json" ]]; then
  PHASE=$(python3 -c "
import json
with open('${CWD}/.sdlc/state.json') as f:
    state = json.load(f)
print(state.get('current_phase', 'unknown'))
" 2>/dev/null)
  echo "**Current SDLC Phase:** ${PHASE:-unknown}"
  echo ""
fi

# Active tasks
TASK_DIR="${CWD}/.etc_sdlc/tasks"
if [[ -d "$TASK_DIR" ]]; then
  ACTIVE_TASKS=$(grep -l "status:.*in_progress" "$TASK_DIR"/*.yaml 2>/dev/null)
  if [[ -n "$ACTIVE_TASKS" ]]; then
    echo "### Active Tasks"
    for task_file in $ACTIVE_TASKS; do
      TITLE=$(grep "^title:" "$task_file" 2>/dev/null | head -1 | sed 's/title:\s*//')
      echo "- $(basename "$task_file"): $TITLE"
    done
    echo ""
  fi
fi

# Recent git activity (last 5 commits)
if git -C "$CWD" rev-parse --git-dir > /dev/null 2>&1; then
  echo "### Recent Commits"
  echo '```'
  git -C "$CWD" log --oneline -5 2>/dev/null
  echo '```'
  echo ""
fi

# Governance journal (recent entries)
JOURNAL="${CWD}/.etc_sdlc/journal.md"
if [[ -f "$JOURNAL" ]]; then
  echo "### Governance Journal (Recent)"
  tail -30 "$JOURNAL"
  echo ""
fi

# Checkpoint (session state from last save)
CHECKPOINT="${CWD}/.etc_sdlc/checkpoint.md"
if [[ -f "$CHECKPOINT" ]]; then
  echo "### Last Checkpoint"
  cat "$CHECKPOINT"
  echo ""
fi

# Dirty marker status
if [[ -f "${CWD}/.tdd-dirty" ]]; then
  echo "**WARNING:** .tdd-dirty marker present — production code was modified but verification has not run."
  echo ""
fi

# Project invariants reminder
if [[ -f "${CWD}/INVARIANTS.md" ]]; then
  echo "**INVARIANTS.md exists** — all code changes are gated on invariant checks."
  echo ""
fi

echo "**Reminder:** You are operating under the etc harness. TDD is enforced by hooks. Read required files before editing. Fail early and loud."

exit 0
