#!/bin/bash
# hooks/inject-standards.sh
#
# SubagentStart hook.
# Injects engineering standards and project constraints into every
# subagent's context at spawn time. The "onboarding packet" for
# new team members.
#
# Output to stdout becomes additionalContext for the subagent.
# Exit code is always 0 (cannot block subagent creation).

INPUT=$(cat)
CWD=$(echo "$INPUT" | jq -r '.cwd // "."')
AGENT_TYPE=$(echo "$INPUT" | jq -r '.agent_type // "unknown"')

# Build the onboarding context
cat <<CONTEXT
## Engineering Standards — Onboarding Context

You are operating under the etc (Engineering Team, Codified) harness.
The following rules are non-negotiable:

### TDD (Red/Green/Refactor)
- Write the failing test FIRST, then implement to make it pass
- Tests must exist before production code can be edited (enforced by hook)
- Coverage threshold: 98%

### Code Standards
- Strict type annotations — no \`Any\` unless unavoidable
- Functions under 20 lines, cyclomatic complexity under 5
- Error handling: fail early and loud, never swallow exceptions

### Architectural Rules
- Respect layer boundaries — dependencies point inward only
- Check INVARIANTS.md before modifying code (enforced by hook)
- Domain fidelity: use ubiquitous language from the domain model

### Process
- Read required files before coding (enforced by hook)
- Mark tasks in_progress when starting, completed when done
- If stuck: escalate to the orchestrator, don't guess
CONTEXT

# Inject active task context if available
TASK_DIR="${CWD}/.etc_sdlc/tasks"
if [[ -d "$TASK_DIR" ]]; then
  for task_file in "$TASK_DIR"/*.yaml; do
    [[ -f "$task_file" ]] || continue
    if grep -q "status:.*in_progress" "$task_file" 2>/dev/null; then
      echo ""
      echo "### Active Task"
      echo '```yaml'
      cat "$task_file"
      echo '```'
      break
    fi
  done
fi

# Inject INVARIANTS.md if it exists
if [[ -f "${CWD}/INVARIANTS.md" ]]; then
  echo ""
  echo "### Project Invariants"
  echo '```markdown'
  cat "${CWD}/INVARIANTS.md"
  echo '```'
fi

# Inject antipatterns if file exists
if [[ -f "${CWD}/.etc_sdlc/antipatterns.md" ]]; then
  echo ""
  echo "### Known Antipatterns"
  echo '```markdown'
  cat "${CWD}/.etc_sdlc/antipatterns.md"
  echo '```'
fi

exit 0
