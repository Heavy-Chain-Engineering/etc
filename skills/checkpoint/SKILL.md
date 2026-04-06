---
name: checkpoint
description: Save current session state to disk before compaction or session end. Ensures continuity across context resets.
---

# /checkpoint — Session State Persistence

Save all current session state to disk so the session can be safely compacted
or resumed later. Run this before `/compact` or when ending a long session.

## Usage

```
/checkpoint
/checkpoint "Finished auth feature, starting payment integration"
```

## Workflow

### Step 1: Gather Current State

Collect the following from the current session and project:

1. **Current objective** — What is the human working toward? If provided as
   an argument, use that. Otherwise, summarize from conversation context.

2. **SDLC phase** — Read `.sdlc/state.json` if it exists. Report current phase.

3. **Active tasks** — Read `.etc_sdlc/tasks/*.yaml` files. For each task,
   report: task_id, title, status, assigned_agent.

4. **Recent decisions** — Summarize any architectural or design decisions
   made during this session that aren't yet captured in ADRs or docs.

5. **Discovered context** — Note anything learned during this session that
   isn't yet in the codebase: patterns found, gotchas, constraints discovered.

6. **Pending items** — Any escalations, reviews, or follow-ups that need
   attention in the next session.

### Step 2: Write Checkpoint File

Write the gathered state to `.etc_sdlc/checkpoint.md`:

```markdown
# Session Checkpoint

**Saved:** {YYYY-MM-DD HH:MM}
**Objective:** {current objective}
**SDLC Phase:** {phase or "not initialized"}

## Task Status

| ID | Title | Status | Agent |
|----|-------|--------|-------|
| {id} | {title} | {status} | {agent} |

## Decisions Made This Session

- {decision 1}
- {decision 2}

## Discovered Context

- {finding 1}
- {finding 2}

## Pending Items

- {item 1}
- {item 2}
```

### Step 3: Append to Governance Journal

Append an entry to `.etc_sdlc/journal.md` (create with header if it
doesn't exist):

```markdown
### {YYYY-MM-DD HH:MM} — checkpoint
Session state saved. Objective: {objective}. Phase: {phase}. Tasks: {N total, M active}.
```

### Step 4: Confirm to User

Report:
```
Checkpoint saved to .etc_sdlc/checkpoint.md
Journal entry appended to .etc_sdlc/journal.md

Summary:
  Objective: {objective}
  Phase: {phase}
  Tasks: {N total, M active, K completed}
  Decisions: {count}
  Pending items: {count}

Safe to run /compact. State will be restored via reinject-context hook.
```

## Constraints

- NEVER overwrite the journal — always append
- The checkpoint file IS overwritten each time (it's current state, not history)
- If `.etc_sdlc/` directory doesn't exist, create it
- If `.sdlc/state.json` doesn't exist, report phase as "not initialized"
- Keep the checkpoint concise — it's injected into context after compaction,
  so every line costs context window space

## Post-Completion Guidance

After the checkpoint is saved:

```
Checkpoint saved. Context will be restored automatically after compaction.

  /compact          — safe to compact now, state is preserved
  /build --resume   — after compaction, resume any in-progress build
  /tasks board      — check task status anytime
```
