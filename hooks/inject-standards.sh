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

### Research Discipline
- When a third-party framework or library isn't behaving as expected,
  consult current docs FIRST. Query the \`context7\` MCP server, check
  the framework's official reference, and grep the public repo before
  reading built artifacts or disassembling bundles.
- Ordering: context7 (30s) → official docs (2min) → public repo grep
  (5min) → framework test suite (5min) → source/bundles (last resort).
- If you find yourself reverse-engineering framework internals through
  \`dist/**/*.js\` or tracing transpiled output, STOP and re-query docs.
  The supported API you're looking for is almost always two lines of
  docs away. Reading source before docs inverts the cost gradient.
- Escape hatch: if you have reason to believe the docs are wrong,
  missing, or lagging the code, read source — but state the reason
  first. "I'll just check the source real quick" is not a valid reason;
  "the context7 docs for version X don't mention Y and the last commit
  on that file was 3 months ago" is.
- See standards/process/research-discipline.md for the full rule and
  the origin story.
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
