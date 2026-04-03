# PRD: etc v1.2 — Templates, Governance Journal, Checkpoint, Changeset Budget

## Summary

Add four capabilities inspired by Armature: (1) a templates directory for
consistent artifact generation, (2) an append-only governance journal for
audit trail, (3) a `/checkpoint` skill for session state persistence before
compaction, and (4) a changeset budget in the DSL defaults.

## Scope

### In Scope
- Templates directory with ADR, agent, task, and invariant templates
- Governance journal (`.etc_sdlc/journal.md`) — append-only log
- `/checkpoint` skill — save session state before compaction
- Changeset budget in DSL defaults
- Compiler updates to include templates in dist/
- Install updates to deploy templates

### Out of Scope
- Structured YAML invariant registry (future — keep markdown+verify for now)
- Scoped agents.md per directory (future)
- Routing table in CLAUDE.md (future)
- `/armature-init` equivalent project bootstrapper (future)

## Feature 1: Templates Directory

### Problem

When users create ADRs, agent definitions, task files, or invariant entries,
there's no structured starting point. Each is created from scratch or by
copying an existing example. This leads to inconsistency.

### Solution

A `templates/` directory with `.tmpl` files that the compiler copies to `dist/`.

### Files to Create

#### templates/adr.md.tmpl

```markdown
# ADR-{NNNN}: {Title}

**Status:** Proposed | Accepted | Superseded | Deprecated
**Date:** {YYYY-MM-DD}

## Context

{Why this decision is needed.}

## Decision

{What was decided. Be specific.}

## Consequences

{What follows. Both positive and negative.}

## Invariants

{Hard rules from this decision. Each maps to INVARIANTS.md.}

- **INV-NNN:** {rule — use "must", "must not", "always", "never"}

## Acceptance Criteria

- [ ] {testable criterion}
- [ ] {testable criterion}
```

#### templates/agent.md.tmpl

```markdown
---
name: {agent-name}
description: {one-line description}
tools: [Read, Write, Edit, Bash, Grep, Glob]
model: sonnet
---

# {Agent Name}

{2-3 sentences: role, responsibility, scope.}

## Behavioral Directives

- **Must:** {directive}
- **Must not:** {directive}
- **Always:** {directive}
- **Never:** {directive}

## Reporting

When you complete your task, report:
- **Files modified:** {list}
- **Tests run:** {results}
- **Concerns:** {uncertainties or scope issues}
```

#### templates/task.yaml.tmpl

```yaml
task_id: "{NNN}"
title: "{Clear, actionable title}"
assigned_agent: backend-developer
status: pending
requires_reading:
  - spec/{prd}.md
files_in_scope:
  - src/{module}.py
  - tests/test_{module}.py
acceptance_criteria:
  - "{Specific, measurable criterion}"
dependencies: []
context: |
  {Additional context from the PRD.}
```

#### templates/invariant.md.tmpl

```markdown
## INV-{NNN}: {Short description}

- **Layers:** {hook | test | ci | agent-instructions}
- **Verify:** `{command that returns non-empty on violation}`
- **Fail action:** Block edit | Block merge | Warn
- **Rationale:** {Why this invariant exists.}
```

### Acceptance Criteria

1. `templates/` directory exists with 4 `.tmpl` files
2. Compiler copies `templates/` to `dist/templates/`
3. Install deploys `dist/templates/` to `~/.claude/templates/`
4. Each template has clear placeholder markers ({NNNN}, {Title}, etc.)
5. ADR template includes: Context, Decision, Consequences, Invariants, Acceptance Criteria
6. Agent template includes: frontmatter, directives, reporting format
7. Task template matches the format `/implement` expects
8. Invariant template matches the format `check-invariants.sh` parses

## Feature 2: Governance Journal

### Problem

When hooks block actions, when tasks escalate, when postmortems are filed —
there's no persistent log. The history lives in conversation context and
disappears after compaction or session end.

### Solution

An append-only governance journal at `.etc_sdlc/journal.md`. Updated by
hooks, skills, and the orchestrator.

### Format

```markdown
# Governance Journal

Append-only log of governance events. Do not edit or delete entries.

### {YYYY-MM-DD HH:MM} — {event_type}
{details}
```

Event types:
- `initialization` — project scaffolded
- `phase-transition` — SDLC phase changed
- `escalation` — hook killed an agent, surfaced to human
- `postmortem` — bug traced, antipattern recorded
- `build-candidate` — verified state tagged
- `invariant-added` — new invariant created
- `gate-override` — human overrode a hook block

### Integration Points

1. **`/postmortem` skill** — appends a journal entry when an antipattern is recorded
2. **`/implement` skill** — appends when implementation starts and completes
3. **`/checkpoint` skill** — appends when session state is saved
4. **`reinject-context.sh`** — reads the last 10 journal entries during compaction recovery

### Acceptance Criteria

1. `/postmortem` appends to `.etc_sdlc/journal.md` when recording an antipattern
2. `reinject-context.sh` includes last 10 journal entries in recovery context
3. Journal entries have timestamp, event type, and details
4. Journal is append-only — skills never edit or delete existing entries
5. Test: `reinject-context.sh` output includes journal content when file exists

## Feature 3: `/checkpoint` Skill

### Problem

Before context compaction, important session state is lost — current objective,
active tasks, pending reviews, decisions made. The `reinject-context.sh` hook
recovers git log and task status, but not the narrative context.

### Solution

A `/checkpoint` skill that saves comprehensive session state to
`.etc_sdlc/checkpoint.md` before compaction.

### Workflow

1. Write current state to `.etc_sdlc/checkpoint.md`:
   - Current objective (what the human is working toward)
   - SDLC phase (from `.sdlc/state.json`)
   - Active tasks and their statuses
   - Decisions made this session
   - Discovered context not yet in docs
   - Any pending escalations or reviews

2. Append to governance journal:
   ```
   ### {timestamp} — checkpoint
   Session state saved. Objective: {objective}. Phase: {phase}. Tasks: {N active}.
   ```

3. Confirm to user: "Checkpoint saved. Safe to run /compact."

### Integration with reinject-context.sh

Update `reinject-context.sh` to include `.etc_sdlc/checkpoint.md` content
in the recovery context, right after the journal entries.

### Acceptance Criteria

1. Skill file exists at `skills/checkpoint/SKILL.md`
2. Skill writes to `.etc_sdlc/checkpoint.md`
3. Skill appends to `.etc_sdlc/journal.md`
4. `reinject-context.sh` includes checkpoint content when file exists
5. Test: `reinject-context.sh` output includes checkpoint content

## Feature 4: Changeset Budget in DSL

### Problem

Nothing prevents a single task from producing a 2000-line change. Large
changesets are harder to review, more likely to contain bugs, and break
the principle of small, focused commits.

### Solution

Add changeset budget defaults to the DSL that downstream tools can reference.

### DSL Addition

```yaml
defaults:
  model: sonnet
  on_failure: block
  on_loop: escalate
  max_retries: 2
  coverage_threshold: 98
  changeset_budget:
    target_loc: 300    # Ideal lines of code per task
    warn_loc: 500      # Warn if task exceeds this
    max_loc: 1000      # Block if task exceeds this
```

### Acceptance Criteria

1. `changeset_budget` section exists in `spec/etc_sdlc.yaml` defaults
2. Compiler passes the values through to compiled output
3. Test: compiled `dod-templates.json` or `settings-hooks.json` includes budget values

## Implementation Order

1. Templates directory + compiler/install updates (foundation)
2. Governance journal + reinject-context.sh update (logging)
3. `/checkpoint` skill + reinject-context.sh update (session persistence)
4. Changeset budget in DSL (smallest change)

## Dependencies

- Features 2-3 both modify `reinject-context.sh` — serialize them
- Feature 1 modifies compiler and install — independent of 2-4
- Feature 4 modifies DSL only — independent
