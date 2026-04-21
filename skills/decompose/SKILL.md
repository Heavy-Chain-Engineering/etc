---
name: decompose
description: Recursively decompose complex tasks into implementable subtasks. Reads a PRD or task, scores complexity, and breaks down anything too large for a single agent session.
---

# /decompose — Hierarchical Task Decomposition

Break complex work into right-sized, implementable subtasks. Operates recursively —
if a subtask is still too complex, decompose it again. Continues until every leaf
task is small enough for a single agent session.

This is the intelligence layer that replaces Taskmaster's PRD parsing and task
expansion. It reads specs and tasks, understands dependencies, and generates
the task YAML files that `/implement` dispatches.

## Response Format (Verbosity)

Terse and structured. Use tables for task/score data, numbered lists for
ordered procedures, fenced code blocks for machine-readable artifacts (task
YAML, JSON arrays piped to `tasks.py bulk-create`, tree output). Prose is
limited to: (a) workflow-phase announcements, (b) rejection messages when
a decomposition rule is violated, (c) the Post-Completion Guidance block.
No preamble ("I'll...", "Here is..."). No narrative summary. No emoji. Max
300 words per response unless producing a tree/score report (max 600 words)
or the final Post-Completion block (max 800 words). When displaying the
task tree, render the raw `tasks.py tree` output; do not re-describe it in
prose.

## Subagent Dispatch (Non-Applicable)

`/decompose` does not dispatch subagents. It is the decomposition engine
itself — called by `/build` (Step 3 and Step 4) and `/implement`. All
task-creation work happens in your own context by invoking the `tasks.py`
CLI via Bash. You MUST NOT attempt to Agent-dispatch the creation, scoring,
or tree construction of tasks; those operations live in this skill.

Your allowed in-context actions are: (a) reading specs and parent task
YAML via Read, (b) reading `requires_reading` files referenced by a parent
task, (c) invoking `tasks.py bulk-create`, `tasks.py create`,
`tasks.py score`, `tasks.py ready-to-decompose`, `tasks.py tree`,
`tasks.py waves`, `tasks.py status` via Bash, (d) setting parent status
to `decomposed` via `tasks.py set-status`, (e) rendering the
Post-Completion Guidance block and the `AskUserQuestion` call.

## Before Starting (Non-Negotiable)

Read these files in order before any decomposition action, using the
Read tool on each exact path:

1. The spec file or parent task YAML passed as the argument — full contents.
2. For parent-task expansion: every path listed in the parent's
   `requires_reading` field.
3. `standards/process/interactive-user-input.md` — AskUserQuestion
   Pattern A (used in Post-Completion Guidance).

If the input spec or parent task file does not exist, STOP and report the
missing path. If `standards/process/interactive-user-input.md` does not
exist, STOP and report — the Post-Completion Guidance step cannot
complete without it. Do not proceed to task creation on partial reads.

## Usage

```
/decompose spec/prd-authentication.md     # Decompose a PRD into initial tasks
/decompose 001                            # Decompose a specific task into subtasks
/decompose --auto                         # Auto-decompose all tasks scoring > 7
```

## Workflow

### When decomposing a PRD (initial breakdown):

1. **Read the PRD** — understand requirements, acceptance criteria, module structure
2. **Identify natural boundaries** — modules, layers, components, interfaces
3. **Generate tasks** with hierarchical IDs (`001`, `002`, ...) by piping a JSON
   array to `python3 ~/.claude/scripts/tasks.py bulk-create --feature {slug}`. Do NOT
   hand-write task YAML files with the Write tool — the CLI is ~75% cheaper in
   tokens, enforces schema at write time, and writes atomically (all tasks or
   none). See "Creating Tasks" below for the invocation format.
4. **Score each task** — invoke `python3 ~/.claude/scripts/tasks.py score`
5. **Flag complex tasks** — anything scoring > 7 needs further decomposition
6. **Auto-decompose flagged tasks** — recurse into them immediately

### When decomposing a specific task (subtask expansion):

1. **Read the parent task** YAML file
2. **Read the parent's requires_reading** files for context
3. **Break into subtasks** with hierarchical IDs:
   - Parent: `002`
   - Subtasks: `002.001`, `002.002`, `002.003`
4. **Set parent status** to `decomposed` (it's no longer a leaf — its children are)
5. **Distribute the parent's scope** among subtasks:
   - Each file in `files_in_scope` goes to exactly one subtask
   - Each acceptance criterion maps to at least one subtask
   - No orphaned criteria or files
6. **Set dependencies** between subtasks where order matters
7. **Score subtasks** — if any still score > 7, decompose again

### When auto-decomposing (batch mode):

1. Invoke `python3 ~/.claude/scripts/tasks.py ready-to-decompose`
2. For each flagged task, apply the subtask expansion workflow
3. Continue until no tasks exceed the threshold

## Creating Tasks

**Always use the `tasks.py` CLI. Never hand-write task YAML with the Write tool.**

The CLI enforces schema at write time, produces byte-identical YAML, and writes
atomically — either every task in a batch hits disk or none does, so no
half-decomposed state ever leaks through.

### Bulk create (the normal path)

Pipe a JSON array of task objects to `bulk-create`:

```bash
python3 ~/.claude/scripts/tasks.py bulk-create --feature {slug} <<'JSON'
[
  {
    "task_id": "002.001",
    "title": "Implement auth data models",
    "assigned_agent": "backend-developer",
    "parent_task": "002",
    "requires_reading": [
      ".etc_sdlc/features/auth/spec.md",
      "src/models/base.py"
    ],
    "files_in_scope": [
      "src/auth/models.py",
      "tests/test_auth_models.py"
    ],
    "acceptance_criteria": [
      "User model has id, email, password_hash, created_at fields",
      "Password hashing uses argon2id"
    ],
    "dependencies": [],
    "context": "Subtask of 002 (Implement authentication system). Handles only the data models — handlers and middleware are in sibling tasks 002.002 and 002.003."
  },
  { "task_id": "002.002", "...": "..." }
]
JSON
```

Alternate inputs: `--json '[...]'` for inline, `--json-file path.json` for a file.

### Single create (debugging path)

For one-off tasks during debugging, flags are more discoverable than JSON:

```bash
python3 ~/.claude/scripts/tasks.py create --feature {slug} \
  --task-id 002.001 \
  --title "Implement auth data models" \
  --agent backend-developer \
  --parent 002 \
  --read .etc_sdlc/features/auth/spec.md --read src/models/base.py \
  --file src/auth/models.py --file tests/test_auth_models.py \
  --ac "User model has id, email, password_hash, created_at fields" \
  --ac "Password hashing uses argon2id" \
  --context "Subtask of 002..."
```

### Required vs optional fields

Required (rejected at write time if missing): `task_id`, `title`,
`assigned_agent`, `files_in_scope`, `acceptance_criteria`.

Optional with defaults: `status` → `pending`, `dependencies` → `[]`,
`requires_reading` → `[]`, `parent_task` → null, `context` → null.

### Atomicity and idempotency

- Default: if ANY task in the batch is invalid OR any target file already
  exists, the whole batch is rejected and nothing is written.
- Pass `--allow-existing` for idempotent re-runs (skips existing files,
  reports which were skipped). Never use `--force`; there is no overwrite.

## Hierarchical ID Convention

```
001                    # Top-level task
001.001                # Subtask of 001
001.001.001            # Sub-subtask of 001.001
001.002                # Second subtask of 001
002                    # Second top-level task
```

This allows arbitrary depth. The tree command (`python3 ~/.claude/scripts/tasks.py tree`)
renders the hierarchy visually.

## Complexity Scoring

Automatic scoring formula:
- Base score: 1
- +1.5 per acceptance criterion (above 1)
- +1.0 per file in scope (above 1)
- Capped at 10

| Score | Meaning | Action |
|-------|---------|--------|
| 1-3 | Simple | Implement directly (QUICK mode) |
| 4-7 | Moderate | Implement as-is (STANDARD mode) |
| 8-10 | Complex | **Decompose into subtasks** |

The threshold of 7 comes from the DSL's `changeset_budget`. A task scoring 8+
likely touches too many files or has too many criteria for a single agent session.

## Decomposition Rules

1. **Every acceptance criterion from the parent must appear in exactly one subtask.**
   No orphaned criteria. Verify: `count(parent.criteria) == sum(subtask.criteria)`.

2. **Every file from the parent's scope must appear in exactly one subtask.**
   No overlapping file scopes (enables parallel execution). No orphaned files.

3. **Subtasks must have clear boundaries.** Each subtask should be a coherent
   unit — a model, a handler, a test suite — not an arbitrary slice.

4. **Dependencies flow from data → logic → integration.**
   Models before handlers, handlers before middleware, unit tests before integration tests.

5. **Test files belong with their implementation.** `src/auth/models.py` and
   `tests/test_auth_models.py` go in the same subtask.

6. **Context carries forward.** Each subtask's `context` field explains its
   relationship to siblings and the parent task.

## Verification

After decomposition, verify:
```bash
python3 ~/.claude/scripts/tasks.py tree          # Visual hierarchy
python3 ~/.claude/scripts/tasks.py score         # All leaves score ≤ 7
python3 ~/.claude/scripts/tasks.py waves         # No file overlaps within waves
python3 ~/.claude/scripts/tasks.py status        # Correct counts
```

## Integration with /implement

`/implement` calls `/decompose` during Step 3 (Decompose into Tasks):
- QUICK mode: skip decomposition entirely
- STANDARD mode: single-level decomposition
- DEEP mode: recursive decomposition until all leaves score ≤ 7

After decomposition, `/implement` uses `python3 ~/.claude/scripts/tasks.py waves` to
determine execution order and `python3 ~/.claude/scripts/tasks.py next` to find
what's ready for dispatch.

## Constraints

- NEVER hand-write task YAML with the Write tool. Always use
  `tasks.py bulk-create` (batch) or `tasks.py create` (single). The CLI
  exists to eliminate transcription errors and save tokens — bypassing it
  reintroduces both.
- NEVER create subtasks with overlapping `files_in_scope`
- NEVER leave acceptance criteria unassigned to a subtask
- ALWAYS set the parent task status to `decomposed` after creating subtasks
- ALWAYS verify the tree after decomposition
- If a task can't be decomposed further (already 1-2 criteria, 1-2 files),
  leave it as-is even if complexity is high — some tasks are irreducibly complex

## Definition of Done

`/decompose` is done for a given invocation when ALL of the following
observable artifacts exist and pass:

1. For PRD decomposition: at least one task YAML file exists under
   `.etc_sdlc/features/{slug}/tasks/`, created via
   `python3 ~/.claude/scripts/tasks.py bulk-create`. No task YAML was
   written with the Write tool.
2. For parent-task expansion: the parent task's `status` field equals
   `decomposed`, set via `python3 ~/.claude/scripts/tasks.py set-status`.
3. `python3 ~/.claude/scripts/tasks.py score` reports every leaf task
   with a complexity score less than or equal to 7. If any leaf still
   scores greater than 7, recurse into it — decomposition is not done.
4. Every acceptance criterion from the parent (or from every spec
   section, for PRD decomposition) appears in exactly one leaf task.
   No orphaned criteria. Verifiable via a diff between parent AC set
   and the union of child AC sets.
5. Every file from the parent's `files_in_scope` (or every file in the
   spec's Module Structure, for PRD decomposition) appears in exactly
   one leaf task. No orphaned files. No two leaf tasks share a file in
   `files_in_scope`.
6. `python3 ~/.claude/scripts/tasks.py tree` renders a valid hierarchy
   with parent tasks marked `decomposed` and every leaf marked
   `pending`.
7. `python3 ~/.claude/scripts/tasks.py waves` returns successfully and
   reports no file overlaps within any wave.
8. The Post-Completion Guidance block has been rendered and the
   `AskUserQuestion` call has been issued.

If any of the eight items fails, `/decompose` is NOT done regardless of
how many subtasks were created. Do not return control to `/build` or
`/implement` until every item holds.

## Post-Completion Guidance

After decomposition is complete, prompt the user:

```
Decomposition complete.
  {N} leaf tasks, max depth {D}, all scoring ≤ 7.

  /tasks tree     — view the full hierarchy
  /tasks waves    — see the execution plan
  /tasks board    — kanban view of all tasks

Ready to execute?
  /build {spec_path}
    → Picks up from the decomposition (skips Steps 1-4, goes straight to wave planning)
```

Then ask via `AskUserQuestion` (see standards/process/interactive-user-input.md):

```
AskUserQuestion(
  questions: [{
    question: "Decomposition complete. Start the build now?",
    header: "Start build?",
    multiSelect: false,
    options: [
      {
        label: "Yes, start /build (Recommended)",
        description: "Hand the decomposition to /build. It will skip Steps 1-4 and go straight to wave planning and execution."
      },
      {
        label: "Not yet — review first",
        description: "Leave the tasks where they are. You can inspect them with /tasks list or /tasks board before invoking /build manually."
      }
    ]
  }]
)
```
