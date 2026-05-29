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
#
# F024: Three sections are conditional on agent_type + task properties.
# Safe-default policy (design.md §Data Model):
#   - agent_type absent/null/"unknown": Git Commit Discipline over-injects;
#     Stub-Marker Grep Contract under-injects.
#   - task YAML absent/malformed: User-Flow Completeness over-injects.

INPUT=$(cat)
CWD=$(echo "$INPUT" | jq -r '.cwd // "."')
PROJECT_ROOT=$(cd "$CWD" 2>/dev/null && git rev-parse --show-toplevel 2>/dev/null || echo "$CWD")  # repo-root anchor (#48)
AGENT_TYPE=$(echo "$INPUT" | jq -r '.agent_type // "unknown"')

# Normalize absent/null to "unknown"
[[ -z "$AGENT_TYPE" || "$AGENT_TYPE" == "null" ]] && AGENT_TYPE="unknown"

# F024: Developer-role allow-list for Git Commit Discipline (BR-002).
# When agent_type is unknown, Git Commit Discipline still emits (safe-default
# over-inject — cheap section, covers a real parallel-git-index race class).
# To add a future role, append to this array and update standards/process/conditional-onboarding.md.
_DEVELOPER_ROLES=("backend-developer" "frontend-developer" "devops-engineer")

_emit_git_commit=false
if [[ "$AGENT_TYPE" == "unknown" ]]; then
  _emit_git_commit=true
else
  for _role in "${_DEVELOPER_ROLES[@]}"; do
    if [[ "$AGENT_TYPE" == "$_role" ]]; then
      _emit_git_commit=true
      break
    fi
  done
fi

# F024: Stub-Marker Grep Contract (BR-003).
# Emitted ONLY for spec-enforcer. All other roles, including unknown,
# suppress it (safe-default under-inject — verbose, clearly role-specific).
_emit_stub_marker=false
[[ "$AGENT_TYPE" == "spec-enforcer" ]] && _emit_stub_marker=true

# F024: User-Flow Completeness (BR-004).
# Emitted when the first in_progress task YAML contains the User-flow
# sentence pattern ("As " ... ", navigate from").
# When task YAML is absent/malformed, emit as safe-default over-inject.
_emit_user_flow=true  # default: over-inject
TASK_DIR="${PROJECT_ROOT}/.etc_sdlc/tasks"
if [[ -d "$TASK_DIR" ]]; then
  _found_task=false
  for _task_file in "$TASK_DIR"/*.yaml; do
    [[ -f "$_task_file" ]] || continue
    if grep -q "status:.*in_progress" "$_task_file" 2>/dev/null; then
      _found_task=true
      # Parse acceptance_criteria field and check for User-flow pattern.
      # Uses Python yaml.safe_load for robust multi-line YAML handling (EC-002).
      # Malformed YAML: fall through to safe-default (emit).
      _has_user_flow=$(python3 - "$_task_file" <<'PYEOF'
import sys, yaml
try:
    with open(sys.argv[1]) as f:
        data = yaml.safe_load(f)
    acs = data.get("acceptance_criteria", []) or []
    for ac in acs:
        ac_str = str(ac)
        if "As " in ac_str and ", navigate from" in ac_str:
            print("yes")
            sys.exit(0)
    print("no")
except Exception:
    # Malformed YAML — safe-default: emit (will be handled below)
    print("error")
PYEOF
)
      if [[ "$_has_user_flow" == "no" ]]; then
        _emit_user_flow=false
      fi
      # "yes" → _emit_user_flow stays true
      # "error" → malformed YAML → _emit_user_flow stays true (safe-default)
      break
    fi
  done
  # No in_progress task found → safe-default: emit
  # (_emit_user_flow remains true from initialization)
fi

# ── Base sections (always emitted — BR-006) ─────────────────────────────────
cat <<CONTEXT
## Engineering Standards — Onboarding Context

You are operating under the etc (Engineering Team, Codified) harness.
The following rules are non-negotiable:

### User Interaction (subagents escalate; do not invoke directly)
- You are a subagent. User interaction is owned by the orchestrator that dispatched you.
- Do NOT invoke \`AskUserQuestion\` or render Pattern B markers in your output.
- If you need operator input (clarification, missing context, ambiguous AC), report
  the question to the orchestrator in your completion summary — name what you need
  and why. The orchestrator will surface it via Pattern A or B.
- See standards/process/interactive-user-input.md for the orchestrator's rules.

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

# ── F024: Git Commit Discipline (conditional — BR-002) ──────────────────────
if [[ "$_emit_git_commit" == "true" ]]; then
cat <<CONTEXT

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
CONTEXT
fi

# ── Base section: Research Discipline (always emitted — BR-006) ─────────────
cat <<CONTEXT

### Research Discipline
- When a third-party framework or library misbehaves, consult docs FIRST.
- Ordering: context7 MCP (30s) → official docs (2min) → public repo grep (5min)
  → framework test suite (5min) → source/bundles (last resort).
- Escape hatch: read source only with a stated reason ("context7 docs for vX
  don't mention Y, last commit on file was N months ago"). "I'll just check
  the source real quick" is NOT a valid reason.
- See standards/process/research-discipline.md for the origin story.
CONTEXT

# ── F024: User-Flow Completeness (conditional — BR-004) ─────────────────────
if [[ "$_emit_user_flow" == "true" ]]; then
cat <<CONTEXT

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
CONTEXT
fi

# ── F024: Stub-Marker Grep Contract (conditional — BR-003) ──────────────────
if [[ "$_emit_stub_marker" == "true" ]]; then
cat <<CONTEXT

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
fi

# ── Base sections: Completion, Diagnostic, Sandbox (always emitted — BR-006) ─
cat <<CONTEXT

### Completion Discipline
- Do not quit conversationally. Phrases like "good place to pause," "approaching
  context limit," or "we've made good progress" while work is unfinished are
  forbidden. They mask incomplete work behind soothing language.
- Do not under-scope. Read every acceptance criterion in full before estimating.
  A claim of "done" is a factual assertion about system state. A false claim
  loses operator trust at a cost larger than the work saved.
- Mark tasks \`completed\` only when all ACs pass and tests are green.
- The Stop hook enforces this contract at session end.
See standards/process/completion-discipline.md for the full rule.

### Diagnostic Discipline
- When a quality-enforcement tool emits a diagnostic (via \`<new-diagnostics>\`
  reminders, verify-green output, lefthook output, or any equivalent signal),
  you MUST emit a parseable YAML evidence block before dismissing it.
- Required fields (all four, all non-empty): \`tool_rerun_command\`,
  \`tool_rerun_output\`, \`attribution\`, \`evidence_type\`.
- \`evidence_type\` enum: \`interpreter-diff\` | \`version-diff\` |
  \`upstream-issue\` | \`repro\` | \`error-is-real\`.
- Investigation window: \`DIAGNOSTIC_INVESTIGATION_TURNS=5\` turns (env-overrideable).
- If \`evidence_type: error-is-real\`, this is not a dismissal — fix the error now.
- Forbidden phrases (illustrative, not exhaustive): "host-env false positive,"
  "stale cache," "noise," "tooling drift." Paraphrasing does not bypass the
  structural contract — only a valid evidence block does.
See standards/process/diagnostic-discipline.md for the full rule and examples.

### Sandbox Discipline
- Do NOT set \`dangerouslyDisableSandbox: true\` preemptively "to save time."
  Every bypass requires an explicit prompt approval from the operator.
  Preemptive bypass optimizes locally while consuming operator attention globally.
- Acceptable reason: a command just failed and sandbox restrictions are the
  evident cause (operation not permitted, access denied to an allowed path).
- Unacceptable reason: "it'll probably need it" or "to avoid a potential block."
- If uncertain whether sandbox will block, try within the sandbox first.
  Disable only on confirmed failure, not on anticipated failure.
See memory/feedback-sandbox-bypass-discipline.md for the origin story.
CONTEXT

# Inject active task context if available
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
if [[ -f "${PROJECT_ROOT}/.etc_sdlc/antipatterns.md" ]]; then
  echo ""
  echo "### Known Antipatterns"
  echo '```markdown'
  cat "${PROJECT_ROOT}/.etc_sdlc/antipatterns.md"
  echo '```'
fi

exit 0
