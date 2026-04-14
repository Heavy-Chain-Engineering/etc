---
name: build
description: Full pipeline conductor — validate, decompose recursively, plan waves, execute wave-by-wave, verify. The single entry point for building any feature from spec to working code.
---

# /build — The Conductor

You are the pipeline conductor. You orchestrate the ENTIRE build lifecycle from
spec to verified, working code. You call other skills and scripts in a
deterministic sequence with checkpoints at every step.

Unlike `/implement` (which handles dispatch) or `/decompose` (which handles
breakdown), `/build` owns the full pipeline and ensures nothing is skipped.

## Usage

```
/build spec/prd-authentication.md
/build .etc_sdlc/features/auth/spec.md
/build --resume                           # Resume from last checkpoint
```

## The Pipeline

```
VALIDATE → SETUP → DECOMPOSE → SCORE/RECURSE → PLAN WAVES → EXECUTE → VERIFY → REPORT
   1         2         3            4               5           6         7        8
```

Each step writes state to the feature directory. If the session dies, compacts,
or is interrupted, `/build --resume` picks up from the last completed step.

---

### Step 1: VALIDATE

Read the spec file. Check Definition of Ready:
- [ ] Specific, measurable acceptance criteria
- [ ] Names concrete files, modules, endpoints
- [ ] Scope boundaries (in/out) are clear
- [ ] No unstated domain knowledge required
- [ ] Detailed enough to implement without guessing

**If spec fails DoR:** Stop immediately. Tell the user what's missing.
Suggest `/spec` to fix it.

**On success:** Write to feature state file:
```
step_completed: 1_validate
```

### Step 2: SETUP

Determine the feature slug from the spec title (lowercase, hyphens).

Create or verify the feature directory:
```
.etc_sdlc/features/{slug}/
  spec.md              ← copy PRD here if not already present
  tasks/               ← empty, will be populated in Step 3
  state.yaml           ← pipeline state tracking
```

Write `state.yaml`:
```yaml
feature: "{slug}"
spec_path: "{original spec path}"
current_step: 2
started_at: "{timestamp}"
mode: null              # Set after scoring in Step 4
waves_completed: 0
total_waves: null
```

**On success:** Update `state.yaml`: `current_step: 2`

### Step 3: DECOMPOSE (Initial Breakdown)

Read the spec. Break it into tasks following `/decompose` conventions:

1. Identify natural boundaries (modules, layers, components, interfaces)
2. Write task YAML files via a single atomic batch:
   `python3 scripts/tasks.py bulk-create --feature {slug}` with a JSON array
   on stdin. NEVER hand-write task YAML with the Write tool — the CLI
   enforces schema, rolls back on any error, and saves ~75% of tokens.
   See `/decompose` for the full JSON shape and field reference.
3. Use hierarchical IDs: `001`, `002`, `003`, ...
4. Each task gets: requires_reading, files_in_scope, acceptance_criteria, dependencies
5. Every acceptance criterion from the spec maps to exactly one task
6. Every file in Module Structure maps to exactly one task

Run: `python3 scripts/tasks.py list --tree` to confirm the breakdown.
Print the tree so the user can see it, then ask for confirmation using
`AskUserQuestion` (see standards/process/interactive-user-input.md,
Pattern A):

```
AskUserQuestion(
  questions: [{
    question: "Task breakdown looks right?",
    header: "Breakdown",
    multiSelect: false,
    options: [
      {
        label: "Yes, proceed to scoring (Recommended)",
        description: "The breakdown covers every acceptance criterion and every file from the Module Structure. Move to Step 4."
      },
      {
        label: "Re-decompose",
        description: "Something is missing, overlapping, or miscategorised. Revise the tasks and re-run this step."
      }
    ]
  }]
)
```

**On success:** Update `state.yaml`: `current_step: 3`

### Step 4: SCORE AND RECURSE

This is the critical loop that enables arbitrary scale.

```
REPEAT:
  1. Run: python3 scripts/tasks.py score
  2. Run: python3 scripts/tasks.py ready-to-decompose
  3. IF any tasks score > 7:
       For each flagged task:
         a. Read the task's acceptance criteria and files_in_scope
         b. Break into subtasks (hierarchical IDs: 002 → 002.001, 002.002, ...)
         c. Set parent status to "decomposed"
         d. Each subtask gets a subset of the parent's criteria and files
         e. NO criteria orphaned, NO files orphaned, NO scope overlap
       CONTINUE loop
  4. ELSE:
       All leaf tasks score ≤ 7. Exit loop.
```

After the loop:

Determine mode from final task tree:
- ≤ 3 leaf tasks → QUICK
- 4-15 leaf tasks → STANDARD
- > 15 leaf tasks → DEEP

Update `state.yaml`: `current_step: 4`, `mode: {QUICK|STANDARD|DEEP}`

Report to user:
```
Decomposition complete.
  Total tasks: {N} ({M} leaf, {K} parent)
  Max depth: {D} levels
  Mode: {mode}
  All leaf tasks score ≤ 7. Ready for wave planning.
```

### Step 5: PLAN WAVES

Run: `python3 scripts/tasks.py waves`

Verify:
- No file overlaps within any wave (if found, serialize the conflicting tasks)
- Dependencies respected (no task in wave N depends on a task in wave N+1)

Update `state.yaml`: `current_step: 5`, `total_waves: {N}`

Print the wave plan so the user can see it:

```
Wave plan:
  Wave 0: {N} tasks (parallel)
  Wave 1: {M} tasks (parallel, after wave 0)
  Wave 2: {K} tasks (parallel, after wave 1)
  ...
  Total waves: {W}
```

Then ask for confirmation via `AskUserQuestion`:

```
AskUserQuestion(
  questions: [{
    question: "Proceed with wave execution?",
    header: "Execute?",
    multiSelect: false,
    options: [
      {
        label: "Execute all waves (Recommended)",
        description: "Run every wave in order. I'll stop on any failing test or escalated task."
      },
      {
        label: "Dry run — first wave only",
        description: "Run Wave 0 only, then stop and report. Use this for debugging or unfamiliar features."
      },
      {
        label: "Cancel — review the plan first",
        description: "Don't execute yet. I'll pause so you can review tasks/ and state.yaml before proceeding."
      }
    ]
  }]
)
```

Wait for the user's selection before executing.

### Step 6: EXECUTE (Wave by Wave)

For each wave, in order:

**6a. Dispatch wave N:**
- For each task in the wave:
  - Update task status: `in_progress`
  - Spawn subagent with the task's assigned_agent type
  - Subagent receives: task file, standards injection, project invariants
  - Subagent is gated by hooks: TDD, invariants, required reading, phase gate
  - Parallel dispatch for tasks in the same wave (file-set isolated)

**6b. Wait for wave completion:**
- All subagents in the wave must complete or escalate
- Update completed task statuses: `completed`
- Update escalated task statuses: `escalated`

**6c. Verify wave:**
- Run tests: `python3 -m pytest --tb=short -q`
- If tests fail: STOP. Report the failure. Do NOT proceed to next wave.
- If any task escalated: STOP. Report the escalation to the user.

**6d. Checkpoint:**
- Update `state.yaml`: `waves_completed: {N}`
- This enables resume from the last completed wave if session dies

**6e. Proceed to next wave or finish.**

**On escalation or test failure:**
```
⚠ Wave {N} failed.
  Failing tests: {list}
  Escalated tasks: {list}

The pipeline is paused. Options:
  1. Fix the issues and run: /build --resume
  2. Investigate with: python3 scripts/tasks.py board
```

### Step 7: VERIFY (Final)

After all waves complete:

1. Run full CI: tests + coverage + types (if applicable) + lint (if applicable)
2. Run invariant checks: `INVARIANTS.md` verify commands
3. Cross-check: every acceptance criterion from the original spec is met
4. Write `.etc_sdlc/features/{slug}/verification.md`:

```markdown
# Verification Report — {feature name}

**Date:** {timestamp}
**Spec:** {spec path}
**Mode:** {QUICK|STANDARD|DEEP}

## Task Summary
- Total: {N} tasks ({M} leaf, {K} parent)
- Completed: {C}
- Escalated: {E}

## Acceptance Criteria
- [ ] {criterion 1} — VERIFIED by task {id}
- [ ] {criterion 2} — VERIFIED by task {id}
...

## Quality Checks
- [ ] Tests: {pass/fail} ({count} tests)
- [ ] Coverage: {N}% (threshold: 98%)
- [ ] Type checking: {pass/fail/skipped}
- [ ] Lint: {pass/fail/skipped}
- [ ] Invariants: {pass/fail/no invariants}

## Files Modified
{list of all files created or modified across all tasks}
```

### Step 8: REPORT

Present final summary to user:

```
## Build Complete ✓

**Feature:** {name}
**Spec:** {path}
**Mode:** {QUICK|STANDARD|DEEP}

### Pipeline
  ✓ Step 1: Validated spec (DoR passed)
  ✓ Step 2: Feature directory created
  ✓ Step 3: Decomposed into {N} initial tasks
  ✓ Step 4: Recursive decomposition ({M} leaf tasks, max depth {D})
  ✓ Step 5: Planned {W} execution waves
  ✓ Step 6: Executed all waves
  ✓ Step 7: Verified ({T} tests pass, {C}% coverage)
  ✓ Step 8: Report

### What Was Built
{summary per task}

### Artifacts
  .etc_sdlc/features/{slug}/
    spec.md           — the PRD
    tasks/             — {N} task files
    verification.md    — quality report
    state.yaml         — pipeline state

### Deferred Items
{anything escalated or out of scope}
```

Update `state.yaml`: `current_step: 8`, `completed_at: {timestamp}`

---

## Resume Protocol

When invoked with `--resume`:

1. Find the most recent feature directory with an incomplete `state.yaml`
2. Read `current_step` and `waves_completed`
3. Report: "Resuming {feature} from Step {N}, Wave {M}"
4. Continue from the next uncompleted step

If no incomplete features found: "No build in progress. Start with: /build spec/prd.md"

## Constraints

- You NEVER skip steps. The pipeline is sequential and checkpointed.
- You NEVER proceed past a failed wave. Stop and report.
- You NEVER dispatch tasks scoring > 7. Decompose first.
- You ALWAYS wait for user confirmation before executing (Step 6).
- You ALWAYS write state.yaml after each step for resume capability.
- You ALWAYS write verification.md before reporting success.
- If context is getting large (> 60%), suggest `/checkpoint` then `/compact`.

## Post-Completion Guidance

After a successful build, prompt the user:

```
Build complete. All {N} tests pass, {C}% coverage.

This feature is ready to commit. Next steps:
  • Review the changes: git diff
  • Commit when satisfied
  • If you find issues later: /postmortem to trace and prevent recurrence
  • Ready to build something else? /spec "your next idea"
```

After a failed build (escalation or test failure):

```
Build paused at Wave {N}. {reason}

Options:
  • Fix the issue, then: /build --resume
  • Review the task board: /tasks board
  • Check what's blocking: /tasks deps {task_id}
  • If you need to rethink: /spec to revisit the specification
```

After a wave completes mid-pipeline:

```
Wave {N} of {total} complete. {M} tasks done, {K} remaining.
Tests passing. Proceeding to Wave {N+1}...
```

Keep the user informed at every natural boundary.
