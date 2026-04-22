---
name: checkpoint
description: Save current session state to disk before compaction or session end. Ensures continuity across context resets.
---

# /checkpoint — Session State Persistence

Save all current session state to disk so the session can be safely compacted
or resumed later. Run this before `/compact` or when ending a long session.

## Response Format (Verbosity)

Terse and structured. Use tables for task data, fenced code blocks for the
checkpoint artifact and journal entry, and numbered lists for ordered
procedures. Prose is limited to: (a) step-entry announcements, (b) the final
Step 4 confirmation block, (c) the Post-Completion Guidance block. No
preamble ("I'll...", "Here is..."). No narrative summary. No emoji. Max 200
words per response unless producing the Step 4 confirmation (max 400 words).
Render file contents as fenced code blocks; do not re-describe them in prose.

## Subagent Dispatch (Non-Applicable)

`/checkpoint` does not dispatch subagents. It is a save-state operation —
all work happens in your own context by invoking Read, Write, and Bash
tools directly. You MUST NOT attempt to Agent-dispatch state collection,
file writes, or journal appends; those operations live in this skill.

Your allowed in-context actions are: (a) reading session state via Read
(on `.sdlc/state.json` and existing `.etc_sdlc/checkpoint.md`), (b) reading
task YAML via Bash (`tasks.py list --tree` / `tasks.py status`), (c) writing
`.etc_sdlc/checkpoint.md` via Write, (d) appending to `.etc_sdlc/journal.md`
via Bash (`printf ... >> .etc_sdlc/journal.md`) or Write after a Read,
(e) rendering the Step 4 confirmation and the Post-Completion Guidance
block.

## Before Starting (Non-Negotiable)

Read these sources in order before any Step 1 action, using the named tool
on each exact path:

1. `.sdlc/state.json` via the Read tool — if the file does not exist,
   record `phase = "not initialized"` and continue. Do not skip the Read
   attempt; the absence of the file is itself checkpoint state.
2. `.etc_sdlc/checkpoint.md` via the Read tool, if it exists — the prior
   checkpoint is the baseline you are overwriting. Read it so the new
   checkpoint reflects only deltas, not lost context.
3. Enumerate task YAMLs via Bash:
   `python3 ~/.claude/scripts/tasks.py list --tree` and
   `python3 ~/.claude/scripts/tasks.py status`. If no tasks exist,
   record `tasks: 0` and continue.

If the `.etc_sdlc/` directory does not exist, create it via Bash:
`mkdir -p .etc_sdlc` before Step 2. If `tasks.py` is not found at the
expected path, STOP and report the missing script to the user — state
collection cannot proceed without it.

## Usage

```
/checkpoint
/checkpoint "Finished auth feature, starting payment integration"
```

## Workflow

### Step 1: Gather Current State

Collect the following from the current session and project. For each item,
use the named tool — do not rely on memory of prior reads.

1. **Current objective** — If provided as an argument, use that string
   verbatim. Otherwise, derive a one-sentence summary from the current
   conversation turn and the user's most recent explicit ask.

2. **SDLC phase** — From the `.sdlc/state.json` contents read in the
   Before Starting step. If the file was absent, record
   `"not initialized"`.

3. **Active tasks** — From the `tasks.py list --tree` output captured in
   the Before Starting step. For each task row, record: `task_id`,
   `title`, `status`, `assigned_agent`. Do not re-run the command; reuse
   the output you already have.

4. **Recent decisions** — Enumerate architectural or design decisions
   made during this session that are not already captured in an ADR,
   PRD, or commit message. For each decision: one line stating what was
   decided and the load-bearing reason.

5. **Discovered context** — Enumerate items learned during this session
   that are not yet in the codebase or docs: patterns found, gotchas,
   constraints discovered, assumptions that turned out to be wrong.

6. **Pending items** — Enumerate escalations, reviews, or follow-ups
   that need attention in the next session. Each item states the
   trigger condition that makes it actionable.

### Step 2: Write Checkpoint File

Write the gathered state to `.etc_sdlc/checkpoint.md` using the Write
tool. The file is overwritten each invocation (it represents current
state, not history). Use exactly this structure:

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

Append a single entry to `.etc_sdlc/journal.md` via Bash. Use `printf`
with append redirection so prior entries are preserved byte-for-byte:

```bash
printf '\n### %s — checkpoint\nSession state saved. Objective: %s. Phase: %s. Tasks: %s total, %s active.\n' \
  "{YYYY-MM-DD HH:MM}" "{objective}" "{phase}" "{N}" "{M}" >> .etc_sdlc/journal.md
```

If `.etc_sdlc/journal.md` does not exist, create it with a header via
Write before the first append:

```markdown
# Governance Journal

Append-only log of checkpoints, decisions, and phase transitions.
```

Never open `.etc_sdlc/journal.md` with the Write tool after the initial
creation — that would overwrite the file. Only append via Bash.

### Step 4: Confirm to User

Render the confirmation block verbatim:

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

- NEVER overwrite `.etc_sdlc/journal.md`. Always append via Bash
  redirection. The only Write-tool invocation against the journal is
  the initial creation when the file does not exist.
- The checkpoint file `.etc_sdlc/checkpoint.md` IS overwritten on every
  invocation. It represents current state, not history.
- If the `.etc_sdlc/` directory does not exist, create it via
  `mkdir -p .etc_sdlc` before Step 2.
- If `.sdlc/state.json` does not exist, record the phase as
  `"not initialized"`. Do not invent a phase.
- Keep the checkpoint concise. Every line costs context window space
  after compaction because the reinject-context hook injects the file
  back into the next session.

## Definition of Done

`/checkpoint` is done for a given invocation when ALL of the following
observable artifacts exist and pass:

1. `.etc_sdlc/checkpoint.md` exists and was written during this
   invocation via the Write tool. Its content matches the structure in
   Step 2 exactly (heading order, field names, table columns).
2. `.etc_sdlc/checkpoint.md` contains a `Saved:` timestamp matching the
   current invocation (not a prior checkpoint's timestamp).
3. `.etc_sdlc/journal.md` exists and contains at least one entry with
   the current invocation's timestamp and the string `— checkpoint`.
4. If `.etc_sdlc/journal.md` existed before this invocation, its prior
   content is byte-for-byte preserved (verifiable by reading the file
   and confirming the prior entries are still present).
5. The Step 4 confirmation block has been rendered to the user with
   populated values (no `{placeholder}` tokens remaining).
6. No task YAML, spec file, or source file was modified during this
   invocation. `/checkpoint` is read-only for everything outside
   `.etc_sdlc/checkpoint.md` and `.etc_sdlc/journal.md`.

If any of the six items is not satisfied, the checkpoint is NOT done
regardless of which steps reported success individually. Do not render
the Post-Completion Guidance block unless every item holds.

## Post-Completion Guidance

After the checkpoint is saved, render the guidance block verbatim:

```
Checkpoint saved. Context will be restored automatically after compaction.

  /compact          — safe to compact now, state is preserved
  /build --resume   — after compaction, resume any in-progress build
  /tasks board      — check task status
```
