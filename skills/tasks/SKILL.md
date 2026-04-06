---
name: tasks
description: View and manage task status, find next ready task, show dependency tree. Native replacement for Taskmaster.
---

# /tasks — Native Task Tracker

Query and manage task YAML files across features and the global task directory.
No external dependencies — operates directly on your `.etc_sdlc/` task files.

## Usage

```
/tasks                  # List all tasks
/tasks next             # What's ready to work on?
/tasks status           # Summary counts
/tasks board            # Kanban view by status
```

## Commands

### `/tasks` or `/tasks list`
Show all tasks with ID, title, status, and assigned agent.

Run: `python3 scripts/tasks.py list`

Filter by status: `python3 scripts/tasks.py list --status pending`

### `/tasks next`
Find the next task that's ready for work — status is `pending` and all
dependencies have status `completed`.

Run: `python3 scripts/tasks.py next`

### `/tasks status`
Summary counts: total, pending, in_progress, completed, escalated.

Run: `python3 scripts/tasks.py status`

### `/tasks board`
Kanban-style view grouped by status column.

Run: `python3 scripts/tasks.py board`

## Task File Locations

The tracker searches two locations:
1. `.etc_sdlc/features/*/tasks/*.yaml` — per-feature tasks (preferred)
2. `.etc_sdlc/tasks/*.yaml` — global tasks (backward compatible)

## Task Lifecycle

```
pending → in_progress → completed
                      → escalated (hook killed the agent)
          blocked     (dependency not met)
```

To update status: `python3 scripts/tasks.py set-status {task_id} {status}`

## Dependency Resolution

A task is "ready" when:
- Status is `pending`
- Every task ID in its `dependencies` list has status `completed`

`/tasks next` automatically resolves this.
