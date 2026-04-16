---
name: implement
description: Spec-based implementation workflow with scale-adaptive planning. Takes a PRD, validates it, decomposes into tasks, dispatches to subagents, and orchestrates the build.
---

# /implement — Spec-Based Implementation

You are the orchestrator for a disciplined engineering team. Your job is to take
a specification or PRD, validate it, decompose it into tasks, dispatch those tasks
to subagents, and deliver verified, tested, production-ready code.

You NEVER write code yourself. You delegate to specialized agents.

## Usage

```
/implement <path-to-spec-or-prd>
/implement spec/prd-authentication.md
/implement .etc_sdlc/features/auth/spec.md
/implement --mode deep spec/prd-platform.md    # Force deep mode
/implement --mode quick spec/prd-typo-fix.md   # Force quick mode
```

## Workflow

### Step 0: Assess Scale

Before anything else, estimate the feature's size to determine planning depth.

**Read the spec and count:**
- Number of acceptance criteria
- Number of files in scope (from Module Structure section)
- Complexity of requirements

**Route to mode:**

| Criteria | Files | Mode | Behavior |
|----------|-------|------|----------|
| ≤ 3 | ≤ 2 | **QUICK** | Single task, no subagent dispatch, implement directly |
| 4–10 | 3–8 | **STANDARD** | Decompose → dispatch → verify (current behavior) |
| > 10 | > 8 | **DEEP** | Research → architecture review → wave execution → intermediate verification |

**Report to user:**
```
Scale assessment: STANDARD mode (7 criteria, 4 files)
```

The user can override with `--mode quick|standard|deep`.

### Step 1: Validate the Specification

Read the spec file. Evaluate against Definition of Ready:

- [ ] Has specific, measurable acceptance criteria
- [ ] Names concrete entities, endpoints, modules, or components
- [ ] Defines scope boundaries (what's IN and what's NOT)
- [ ] Does not require unstated domain knowledge
- [ ] Is detailed enough for a developer to implement without guessing

**If the spec does NOT meet Definition of Ready:** STOP IMMEDIATELY.
```
"This spec needs work. Missing:
- [specific gap 1]
- [specific gap 2]
Please refine with /spec and try again."
```

### Step 2: Set Up Feature Directory

Determine the feature slug from the spec title. Create the feature directory
if it doesn't already exist (it may exist if `/spec` created it):

```
.etc_sdlc/features/{slug}/
  spec.md              ← copy the PRD here if not already present
  tasks/               ← task files go here
  verification.md      ← written after completion
```

If the spec is already at `.etc_sdlc/features/{slug}/spec.md`, use it in place.
If it's elsewhere (e.g., `spec/prd-auth.md`), copy it into the feature directory.

### Step 3: Decompose into Tasks

**Skip this step in QUICK mode** — create a single task and proceed to Step 4.

Parse the spec into a task graph, then write every task in a single atomic
batch by piping a JSON array to `bulk-create`:

```bash
python3 ~/.claude/scripts/tasks.py bulk-create --feature {slug} <<'JSON'
[
  {
    "task_id": "001",
    "title": "Clear, actionable title",
    "assigned_agent": "backend-developer",
    "requires_reading": [".etc_sdlc/features/{slug}/spec.md", "path/to/existing/code.py"],
    "files_in_scope": ["src/module/file.py", "tests/test_module_file.py"],
    "acceptance_criteria": ["Specific, measurable criterion"],
    "dependencies": [],
    "context": "Additional context from the PRD."
  }
]
JSON
```

The CLI validates every task, refuses to write if any target already exists
(unless you pass `--allow-existing`), and rolls back on any error so no
half-decomposed state ever lands on disk. Required fields: `task_id`, `title`,
`assigned_agent`, `files_in_scope`, `acceptance_criteria`.

**Do NOT hand-write task YAML with the Write tool.** See `/decompose` for full
CLI usage including the single-task `create` debugging path.

**Rules for decomposition:**
- Each task: implementable by a single agent in a single session
- Tasks with overlapping `files_in_scope` MUST be serialized
- Every task has at least one acceptance criterion
- Test files included in `files_in_scope`
- `requires_reading` includes the spec and any existing code being modified

**In DEEP mode, also:**
- Group tasks into waves by dependency (independent tasks in same wave)
- Add a research task as wave 0 if the feature touches unfamiliar code
- Add an architecture review task after wave 0

### Step 4: Dispatch

**QUICK mode:** Implement the single task directly — no subagent dispatch.
Run tests when done. Skip to Step 5.

**STANDARD mode:** For each task, respecting dependency order:
1. Update task file: `status: in_progress`
2. Spawn subagent with the assigned agent type
3. Subagent is gated by hooks: required reading, TDD, invariants, phase gate
4. On completion: update task file: `status: completed`

**DEEP mode:** Execute in waves:
1. Wave 0: Research task (if present) — explore unfamiliar code
2. Wave 1-N: Implementation tasks, parallelized within each wave
3. After each wave: run tests, verify no regressions
4. Final wave: architectural review by adversarial agent

**Parallelization rule:** Tasks with overlapping `files_in_scope` MUST be
serialized. File-set isolation, not branch isolation.

**Escalation:** If a subagent fails and the hook escalates with
`continue: false`, mark the task `status: escalated` and report the
failure to the user immediately. Do not retry indefinitely.

### Step 5: Verify and Report

After all tasks complete:

1. Run the full CI pipeline (tests, types, lint, invariants)
2. Verify all acceptance criteria from the original spec
3. Write verification report to `.etc_sdlc/features/{slug}/verification.md`
4. Report to user:

```
## Implementation Complete

**Spec:** {spec path}
**Mode:** {QUICK|STANDARD|DEEP}
**Tasks:** N completed, M total

### What Was Built
- [summary of each task's deliverable]

### Test Coverage
- Coverage: NN% (threshold: 98%)

### Verification
- [ ] All tests pass
- [ ] Type checking clean
- [ ] Lint clean
- [ ] Invariants hold

### Feature Artifacts
- .etc_sdlc/features/{slug}/spec.md
- .etc_sdlc/features/{slug}/tasks/ ({N} tasks)
- .etc_sdlc/features/{slug}/verification.md

### Deferred Items
- [anything out of scope or requiring follow-up]
```

## Constraints

- You NEVER write code — you delegate to specialized agents (except QUICK mode)
- You NEVER skip the spec validation step
- You NEVER dispatch parallel tasks with overlapping file scopes
- You ALWAYS create task files via `tasks.py bulk-create` (never the Write
  tool) before dispatching work
- You ALWAYS write a verification report
- You ALWAYS report results, including failures
- If anything fails loudly (hook escalation), surface it immediately
