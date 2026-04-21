---
name: tasks
description: View and manage task status, find next ready task, show dependency tree. Native replacement for Taskmaster.
---

# /tasks — Native Task Tracker

Query and manage task YAML files across features and the global task directory.
No external dependencies — operates directly on your `.etc_sdlc/` task files
via the `tasks.py` CLI at `~/.claude/scripts/tasks.py`. The CLI is the shared
contract for `/build`, `/decompose`, `/implement`, and `/tasks`; every skill
that reads or writes task YAML goes through it.

## Response Format (Verbosity)

Terse and structured. Render CLI output as-is inside fenced code blocks; do
not re-describe it in prose. Use tables only when summarizing across multiple
CLI calls. Prose is limited to: (a) the one-line subcommand confirmation
before each Bash invocation, (b) the Context-Aware Guidance block when a
subcommand's output warrants it, (c) error messages when the CLI exits
non-zero. No preamble ("I'll...", "Here is..."). No narrative summary. No
emoji. Max 150 words per response unless rendering `tasks.py tree`,
`tasks.py board`, or `tasks.py waves` output (max 600 words). If the user
passes `--json` or similar machine-output flags to a subcommand, emit only
the raw CLI output with no surrounding prose.

## Subagent Dispatch (Non-Applicable)

`/tasks` does not dispatch subagents. It is a thin wrapper around the
`tasks.py` CLI — all work happens in your own context by invoking Bash
directly against `python3 ~/.claude/scripts/tasks.py`. You MUST NOT
attempt to Agent-dispatch list/next/status/board/tree/waves/score/create/
bulk-create/set-status operations; those operations are CLI calls, not
agent work.

Your allowed in-context actions are: (a) invoking any `tasks.py`
subcommand via Bash using the exact path `python3 ~/.claude/scripts/tasks.py`,
(b) reading task YAML files via Read only when the user explicitly asks
for file contents (otherwise prefer `tasks.py list` / `tasks.py tree`),
(c) rendering CLI stdout verbatim to the user, (d) rendering the
Context-Aware Guidance block after the CLI returns.

## Before Starting (Non-Negotiable)

Before any subcommand invocation, confirm the CLI is reachable and the
working directory is an etc-enabled repository. Use the named tool on
each step:

1. Verify the CLI path exists via Bash:
   `test -x ~/.claude/scripts/tasks.py && echo OK`. If this prints
   anything other than `OK`, STOP and report that
   `~/.claude/scripts/tasks.py` is missing or not executable — no
   subcommand can run without it.
2. If the subcommand reads state (`list`, `next`, `status`, `board`,
   `tree`, `waves`, `score`, `ready-to-decompose`, `deps`), no further
   preconditions apply. Proceed.
3. If the subcommand writes state (`create`, `bulk-create`,
   `set-status`), confirm the target feature directory exists via Bash:
   `test -d .etc_sdlc/features/{slug}/tasks || test -d .etc_sdlc/tasks`.
   If neither path exists, STOP and report that the repository has no
   `.etc_sdlc/` task directory — task creation requires one. Do not
   invent a feature slug or create directories implicitly.
4. For `bulk-create` with stdin input, confirm the JSON payload is
   non-empty before invocation; piping empty stdin to the CLI is an
   error, not a no-op.

The CLI itself enforces schema, atomicity, and overwrite prevention;
do not reimplement those checks in-context.

## Usage

```
/tasks                  # List all tasks
/tasks next             # What's ready to work on?
/tasks status           # Summary counts
/tasks board            # Kanban view by status
/tasks tree             # Hierarchical view
/tasks waves            # Execution plan
/tasks score            # Complexity scores
/tasks deps {id}        # Show what's blocking a task
```

## Commands

Every subcommand below maps to a `python3 ~/.claude/scripts/tasks.py`
invocation. Invoke via Bash exactly as shown. Do not paraphrase the
command; the CLI path and flag names are load-bearing.

### `/tasks` or `/tasks list`
Show all tasks with ID, title, status, and assigned agent.

```
python3 ~/.claude/scripts/tasks.py list
```

Filter by status:

```
python3 ~/.claude/scripts/tasks.py list --status pending
```

Tree-shaped listing:

```
python3 ~/.claude/scripts/tasks.py list --tree
```

### `/tasks next`
Find the next task that is ready for work — status is `pending` and every
task ID in its `dependencies` list has status `completed`.

```
python3 ~/.claude/scripts/tasks.py next
```

### `/tasks status`
Summary counts: total, pending, in_progress, completed, escalated, blocked.

```
python3 ~/.claude/scripts/tasks.py status
```

### `/tasks board`
Kanban-style view grouped by status column.

```
python3 ~/.claude/scripts/tasks.py board
```

### `/tasks tree`
Render the full hierarchy of parent and subtasks.

```
python3 ~/.claude/scripts/tasks.py tree
```

### `/tasks waves`
Emit the execution plan: which tasks run in which wave, based on
dependency resolution and file-scope disjointness.

```
python3 ~/.claude/scripts/tasks.py waves
```

### `/tasks score`
Show the complexity score for every task. Tasks scoring above 7 are
candidates for `/decompose`.

```
python3 ~/.claude/scripts/tasks.py score
```

### `/tasks ready-to-decompose`
List tasks currently exceeding the complexity threshold and flagged for
further decomposition.

```
python3 ~/.claude/scripts/tasks.py ready-to-decompose
```

### `/tasks deps {id}`
Show the dependency graph for a specific task — which tasks block it and
which tasks it blocks.

```
python3 ~/.claude/scripts/tasks.py deps {task_id}
```

### `/tasks set-status {task_id} {status}`
Update a task's status. Valid statuses: `pending`, `in_progress`,
`completed`, `escalated`, `blocked`, `decomposed`.

```
python3 ~/.claude/scripts/tasks.py set-status {task_id} {status}
```

### `/tasks create` and `/tasks bulk-create`
`/decompose`, `/build`, and `/implement` write task YAML files through
the CLI, not the Write tool. This enforces schema at write time and gives
atomic all-or-nothing semantics for bulk writes.

**Bulk (normal path):** JSON array on stdin.

```
python3 ~/.claude/scripts/tasks.py bulk-create --feature {slug} < tasks.json
python3 ~/.claude/scripts/tasks.py bulk-create --feature {slug} --json '[...]'
python3 ~/.claude/scripts/tasks.py bulk-create --feature {slug} --json-file tasks.json
```

**Single (debugging):** repeated flags.

```
python3 ~/.claude/scripts/tasks.py create --feature {slug} \
  --task-id 001 --title "..." --agent backend-developer \
  --file src/foo.py --ac "criterion" [--dep 000] [--read path]
```

Required fields (rejected at write time if missing): `task_id`, `title`,
`assigned_agent`, `files_in_scope`, `acceptance_criteria`. The whole batch
rolls back on any failure. Pass `--allow-existing` for idempotent re-runs.
There is no `--force`; overwrites are never allowed.

See `skills/decompose/SKILL.md` for the full JSON schema and examples.

## Task File Locations

The tracker searches two locations in this order:
1. `.etc_sdlc/features/*/tasks/*.yaml` — per-feature tasks (preferred)
2. `.etc_sdlc/tasks/*.yaml` — global tasks (retained for repositories
   that were initialized before the per-feature layout)

## Task Lifecycle

```
pending → in_progress → completed
                      → escalated (hook killed the agent)
          blocked     (dependency not met)
          decomposed  (parent task; children carry the scope)
```

To update status, use `/tasks set-status` above.

## Dependency Resolution

A task is "ready" when both conditions hold:
1. Status is `pending`.
2. Every task ID in its `dependencies` list has status `completed`.

`/tasks next` resolves this directly from YAML; do not compute it
in-context.

## Context-Aware Guidance

After rendering CLI output, emit one of the following guidance blocks
verbatim, based on the observed state:

**If there are tasks ready to work on:**
```
{N} tasks ready. Next up: {task_id} — {title}
  /build --resume    to continue the pipeline
  /decompose {id}    if any tasks need further breakdown
```

**If all tasks are completed:**
```
All {N} tasks complete.
  /build --resume    to run final verification
```

**If tasks are escalated or blocked:**
```
{N} tasks escalated, {M} blocked.
  /tasks deps {id}   to see what is blocking
  /postmortem        if an escalation reveals a systemic issue
```

**If tasks scoring above 7 are found:**
```
{N} tasks score > 7 (too complex for a single agent).
  /decompose {id}    to break them down
  /tasks score       to see all complexity scores
```

Do not emit a guidance block when the subcommand output is itself the
artifact the user asked for. The two cases that suppress guidance are:
(1) `tasks.py tree` output being piped to a file, (2) `tasks.py list`
invoked with a `--json` flag for machine consumption. In both cases,
emit only the raw CLI output.

## Constraints

- NEVER hand-write task YAML with the Write tool. Always route through
  `tasks.py bulk-create` or `tasks.py create`. The CLI is the single
  write surface for task state.
- NEVER invoke `tasks.py` through any path other than
  `python3 ~/.claude/scripts/tasks.py`. Other skills (`/build`,
  `/decompose`, `/implement`) use this exact invocation; divergence
  breaks the shared contract.
- NEVER pass `--force` to `tasks.py`; the flag does not exist. Use
  `--allow-existing` for idempotent re-runs.
- NEVER modify task YAML files via Edit or Write. Status changes go
  through `tasks.py set-status`.
- ALWAYS render CLI stdout verbatim. Do not reformat, summarize, or
  translate CLI output into prose.

## Definition of Done

`/tasks` is done for a given invocation when ALL of the following hold:

1. The CLI was invoked via Bash using the exact path
   `python3 ~/.claude/scripts/tasks.py` with the subcommand matching
   the user's request.
2. The CLI exited with status 0, OR the CLI's non-zero exit message
   was rendered verbatim to the user (no silent failure, no
   paraphrased error).
3. The CLI stdout was rendered to the user inside a fenced code block,
   unchanged. No prose re-description of the output.
4. For write subcommands (`create`, `bulk-create`, `set-status`), the
   corresponding task YAML change is observable by a follow-up
   `tasks.py list` or `tasks.py tree` invocation. If the expected row
   is absent after a successful write, STOP and report the discrepancy.
5. The Context-Aware Guidance block was emitted for read subcommands
   whose output matches one of the four states (ready / all complete /
   escalated-or-blocked / over-threshold). For other subcommands, no
   guidance block is emitted.
6. No task YAML, spec file, or source file outside the CLI's write
   surface was modified during the invocation.

If any item fails, the invocation is NOT done. Do not claim success
until every item holds.
