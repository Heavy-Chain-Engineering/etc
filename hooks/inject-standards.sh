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

### User Interaction (MANDATORY — applies to every question you ask the user)
- **Pattern A** — Use the \`AskUserQuestion\` tool for any decision with
  2–4 enumerable options. The tool renders a picker UI outside the text
  stream that the user cannot miss. Put the recommended option first
  with "(Recommended)" suffix. Never pair Pattern A with a prose version
  of the same question.
- **Pattern B** — Use the visual marker for free-form ("what / why / how /
  describe") questions. Render exactly:
    \`\`\`

    ---

    **▶ Your answer needed:** <one-line question>

    \`\`\`
  Ask ONE question per turn in Pattern B. Wait for the answer before
  proceeding. Never answer your own open-ended question.
- **Never** embed questions inline in prose. No "Want me to…?", no
  "Should I…?", no "Let me know if…" tails, no "?" terminators on a
  message that lacks Pattern A or Pattern B framing. Inline questions
  get skimmed past — users miss them or respond to the wrong thing.
- See \`standards/process/interactive-user-input.md\` for the full rule,
  anti-patterns, and client-compatibility fallback.

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

### Git Commit Discipline (parallel-agent safety)
- When dispatched by /build or any parallel-agent orchestrator, use
  \`git commit -m "..." -- <your-paths>\` instead of \`git add && git commit\`.
  The shared git index races otherwise — another agent's staged files
  silently become yours.
- NEVER run \`git add .\`, \`git add -u\`, or any glob pattern. The index
  is shared across all parallel agents in the same worktree, so globs
  sweep in everyone's work.
- For deletes, use \`git rm --cached <path>\` then \`git commit <path>\`
  — plain \`git rm\` also touches the shared index.
- High-collision work (3+ files per agent across a wave): run each
  agent in a git worktree via \`isolation: "worktree"\` on the Agent
  call. Per-agent worktrees have their own index.
- See standards/git/commit-discipline.md for the full rule and the
  venlink-platform origin story.

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

### User-Flow Completeness for User-Facing ACs
- Every user-facing AC in a /spec PRD must include a "User flow" sentence
  in the canonical form: "As {role}, navigate from {parent route} via
  {affordance label}, complete {happy path}, observe {outcome}."
- The rule applies at AC authorship time. /spec Phase 3 auto-detects
  user-facing ACs (by route paths, UI nouns, and user verbs) and elicits
  the User-flow sentence per AC — author may accept, refine, or mark
  the AC backend-only.
- Phase 4 Definition of Ready warns when any user-facing AC lacks the
  sentence and gates with a YES/NO prompt. Selecting YES records a
  surface_status: deferred line per offending AC so future readers can
  audit the deferral. The gate does not hard-block.
- Forward-only: legacy specs are unaffected until resumed under /spec.
See standards/process/user-flow-completeness.md for the full rule.

### Stub-Marker Grep Contract for spec-enforcer
- spec-enforcer runs a verify-time stub-marker grep on every cited evidence
  file of a SATISFIED AC. Hits downgrade the verdict to INSUFFICIENT_EVIDENCE;
  the post-pass only DOWNGRADES, never promotes.
- Universal hard-fail patterns (case-sensitive): feature-id-prefixed TODO
  (e.g., \`TODO(F007-001)\`), \`FIXME\`, \`XXX\`. Any match overrides SATISFIED.
- Universal warning patterns (case-insensitive): \`stub until task N\`,
  \`placeholder until task N\`, \`until task N lands\`. Any match downgrades
  with a "warning-class" evidence note.
- Per-project hard-fail tokens live in \`.etc_sdlc/stub-tokens.txt\` (one
  regex per line, \`#\` for comments, blank lines skipped, hard-fail semantics).
- Files whose paths contain \`tests/\`, \`__tests__/\`, \`.test.\`, or \`.spec.\`
  are skipped entirely (no grep run, no hits recorded).
See standards/process/stub-marker-grep.md for the full contract.
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
