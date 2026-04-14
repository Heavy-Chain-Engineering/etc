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
   array to `python3 scripts/tasks.py bulk-create --feature {slug}`. Do NOT
   hand-write task YAML files with the Write tool — the CLI is ~75% cheaper in
   tokens, enforces schema at write time, and writes atomically (all tasks or
   none). See "Creating Tasks" below for the invocation format.
4. **Score each task** — run `python3 scripts/tasks.py score`
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

1. Run `python3 scripts/tasks.py ready-to-decompose`
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
python3 scripts/tasks.py bulk-create --feature {slug} <<'JSON'
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
python3 scripts/tasks.py create --feature {slug} \
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

This allows arbitrary depth. The tree command (`python3 scripts/tasks.py tree`)
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
python3 scripts/tasks.py tree          # Visual hierarchy
python3 scripts/tasks.py score         # All leaves score ≤ 7
python3 scripts/tasks.py waves         # No file overlaps within waves
python3 scripts/tasks.py status        # Correct counts
```

## Integration with /implement

`/implement` calls `/decompose` during Step 3 (Decompose into Tasks):
- QUICK mode: skip decomposition entirely
- STANDARD mode: single-level decomposition
- DEEP mode: recursive decomposition until all leaves score ≤ 7

After decomposition, `/implement` uses `python3 scripts/tasks.py waves` to
determine execution order and `python3 scripts/tasks.py next` to find
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
