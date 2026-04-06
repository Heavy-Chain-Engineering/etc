# PRD: etc v1.3 — Per-Feature Artifacts, Native Task Tracker, Gray Areas, Scale-Adaptive Planning

## Summary

Four capabilities that eliminate the Taskmaster dependency and improve
specification quality: (1) per-feature artifact directories for traceability,
(2) a native task tracker built on our existing YAML task files, (3) gray
area identification in `/spec`, and (4) scale-adaptive planning depth in
`/implement`.

## Motivation

1. **Taskmaster dependency risk.** TM is being commercialized and may stagnate
   as open source. We already have task YAML files — we need a thin native
   layer to track status, resolve dependencies, and show what's next.

2. **Scattered artifacts.** A feature's PRD is in `spec/`, tasks in
   `.etc_sdlc/tasks/`, and there's no verification report or execution
   summary. Per-feature directories group everything for traceability.

3. **Unstated assumptions.** `/spec` asks questions but doesn't systematically
   identify decisions that could go either way. GSD's "gray area" pattern
   forces these to the surface before the spec is written.

4. **One-size-fits-all planning.** A typo fix gets the same decomposition
   ceremony as a platform rewrite. The changeset budget is in the DSL but
   nothing uses it to route planning depth.

## Scope

### In Scope
- Feature 1: Per-feature artifact directories
- Feature 2: Native task tracker (replaces Taskmaster dependency)
- Feature 3: Gray area identification in `/spec`
- Feature 4: Scale-adaptive planning in `/implement`

### Out of Scope
- Taskmaster migration tool (manual transition)
- Git worktree per execution lane (future)
- Event-log-based status (future — YAML status is fine for now)
- Dashboard UI (future)

---

## Feature 1: Per-Feature Artifact Directories

### Problem

A feature's artifacts are scattered: PRD in `spec/`, tasks in `.etc_sdlc/tasks/`,
no verification report. When reviewing what was built or why, you have to
piece together files from multiple locations.

### Solution

Group all artifacts for a feature under `.etc_sdlc/features/{slug}/`.

### Directory Structure

```
.etc_sdlc/features/{slug}/
  spec.md              ← the PRD (or symlink to spec/{slug}.md)
  tasks/
    001-{task}.yaml
    002-{task}.yaml
  research/            ← codebase + web research findings
    codebase.md
    web.md
  gray-areas.md        ← resolved gray areas from /spec
  verification.md      ← final verification report from /implement
  journal.md           ← feature-scoped governance events
```

### Integration

- `/spec` writes to `.etc_sdlc/features/{slug}/spec.md` and also
  copies to `spec/{slug}.md` for backward compatibility
- `/implement` reads from `.etc_sdlc/features/{slug}/spec.md`,
  creates tasks in `.etc_sdlc/features/{slug}/tasks/`,
  writes verification report to `.etc_sdlc/features/{slug}/verification.md`
- The `inject-standards.sh` hook includes the active feature's
  gray-areas.md and research/ when injecting subagent context

### Acceptance Criteria

1. `/spec` creates `.etc_sdlc/features/{slug}/` directory structure
2. `/spec` writes spec.md, research/, and gray-areas.md to the feature dir
3. `/implement` creates tasks under the feature dir (not global `.etc_sdlc/tasks/`)
4. `/implement` writes verification.md after completion
5. Backward compat: spec also written to `spec/{slug}.md`
6. `inject-standards.sh` includes feature-scoped research and gray areas

---

## Feature 2: Native Task Tracker

### Problem

Taskmaster is an external dependency at risk of stagnation. We already have
task YAML files with status, dependencies, acceptance criteria. We just need
a thin layer to query and manage them.

### Solution

A `tasks.py` script and `/tasks` skill that operates on our existing YAML
task files. No new database, no external dependency — just Python reading YAML.

### Commands

```
/tasks                    # List all tasks with status
/tasks next               # Show the next task ready for work (dependencies met)
/tasks status             # Summary: N pending, M in_progress, K completed
/tasks board              # Kanban-style view grouped by status
```

### Script: tasks.py

```bash
python3 tasks.py list                          # All tasks
python3 tasks.py list --status pending         # Filter by status
python3 tasks.py next                          # Next ready task
python3 tasks.py status                        # Summary counts
python3 tasks.py board                         # Kanban view
python3 tasks.py set-status 001 in_progress    # Update status
python3 tasks.py set-status 001 completed      # Mark done
python3 tasks.py deps 001                      # Show dependency tree
```

### Dependency Resolution

A task is "ready" when:
- Its status is `pending`
- All tasks in its `dependencies` list have status `completed`

### Task Discovery

`tasks.py` searches for task YAML files in:
1. `.etc_sdlc/features/*/tasks/*.yaml` (per-feature, preferred)
2. `.etc_sdlc/tasks/*.yaml` (global, backward compat)

### Acceptance Criteria

1. `tasks.py list` shows all tasks with id, title, status, agent
2. `tasks.py next` shows the first pending task with all dependencies met
3. `tasks.py next` returns nothing when all tasks are completed or blocked
4. `tasks.py set-status {id} {status}` updates the YAML file
5. `tasks.py board` groups tasks by status (pending, in_progress, completed, escalated)
6. `tasks.py deps {id}` shows the dependency chain
7. Searches both feature dirs and global task dir
8. `/tasks` skill wraps the script with natural language interface
9. No external dependencies beyond PyYAML (already in pyproject.toml)
10. Tests cover: list, next with deps, set-status, board output

---

## Feature 3: Gray Area Identification in /spec

### Problem

`/spec` asks clarifying questions and does research, but doesn't systematically
surface decisions that could go either way. These unstated assumptions become
bugs during implementation.

### Solution

Add a "Gray Area Resolution" step between research and spec writing in `/spec`.

### Workflow Addition

After Phase 2 (Research), before Phase 3 (Iterative Spec Writing):

**Phase 2.5: Gray Area Resolution**

The skill identifies decisions that are ambiguous based on research findings:

```
I found 4 gray areas that need your input before I write the spec:

1. **Authentication strategy**: JWT vs session cookies?
   Research found: JWT is stateless but can't be revoked. Sessions need
   server-side storage but support revocation.
   → Which approach?

2. **Error response format**: Structured JSON vs RFC 7807 Problem Details?
   Research found: RFC 7807 is more standard but adds complexity.
   → Which format?

3. **Rate limiting**: Per-user vs per-IP vs both?
   → Which strategy?

4. **Password hashing**: bcrypt vs argon2id?
   Research found: argon2id is newer and recommended by OWASP 2024.
   → Which algorithm?
```

The user resolves each gray area. Resolutions are saved to
`.etc_sdlc/features/{slug}/gray-areas.md`:

```markdown
# Gray Areas — Resolved Decisions

## GA-001: Authentication strategy
- **Options:** JWT vs session cookies
- **Decision:** JWT with short expiry + refresh tokens
- **Rationale:** Stateless fits our microservice architecture
- **Decided by:** Jason, 2026-04-06

## GA-002: Error response format
- **Options:** Structured JSON vs RFC 7807
- **Decision:** RFC 7807 Problem Details
- **Rationale:** Industry standard, better tooling support
```

These resolutions are:
1. Incorporated into the PRD's Technical Constraints section
2. Injected into subagent context via `inject-standards.sh`
3. Referenced by acceptance criteria ("must use JWT with refresh tokens")

### Acceptance Criteria

1. `/spec` identifies at least 2 gray areas per feature (or explicitly states none found)
2. Each gray area has: options, research context, decision, rationale
3. Resolutions saved to `.etc_sdlc/features/{slug}/gray-areas.md`
4. Resolved gray areas appear in the PRD's Technical Constraints section
5. `inject-standards.sh` includes gray-areas.md in subagent context

---

## Feature 4: Scale-Adaptive Planning in /implement

### Problem

A typo fix gets the same 10-task decomposition as a platform rewrite.
The changeset_budget is in the DSL but `/implement` doesn't use it.

### Solution

Before decomposition, `/implement` estimates feature size and routes to
the appropriate planning depth.

### Routing Logic

```
Estimate expected LOC change from the PRD:
  - Count acceptance criteria
  - Count files in scope
  - Assess complexity from requirements

Route:
  ≤ 3 acceptance criteria, ≤ 2 files → QUICK mode
  4-10 criteria, 3-8 files            → STANDARD mode (current behavior)
  > 10 criteria or > 8 files          → DEEP mode
```

### Mode Behaviors

**QUICK mode** — Minimal ceremony:
- Single task, no decomposition
- Skip subagent dispatch — implement directly
- Run CI at the end
- Good for: typo fixes, config changes, small bug fixes

**STANDARD mode** — Current `/implement` behavior:
- Decompose into tasks
- Dispatch to subagents
- Full verification

**DEEP mode** — Maximum rigor:
- Research phase before decomposition (codebase + web)
- Architecture review step (what patterns to follow?)
- Wave-based parallel execution (group by dependency, parallelize within wave)
- Intermediate verification after each wave
- Final architectural review by adversarial agent

### Acceptance Criteria

1. `/implement` estimates feature size before decomposition
2. Quick mode: single task, no subagent dispatch, direct implementation
3. Standard mode: current behavior unchanged
4. Deep mode: adds research phase and wave-based execution
5. Mode selection is reported to the user: "Estimated: STANDARD mode (6 criteria, 4 files)"
6. User can override: `/implement --mode deep spec/prd.md`

---

## Implementation Order

1. **tasks.py + /tasks skill** — foundation, replaces Taskmaster
2. **Per-feature directories** — update /spec and /implement to use them
3. **Gray area identification** — update /spec skill
4. **Scale-adaptive planning** — update /implement skill

## Dependencies

- Feature 2 (per-feature dirs) uses Feature 1 (task tracker) for status management
- Feature 3 (gray areas) updates /spec which also gets Feature 2's directory changes
- Feature 4 (scale-adaptive) updates /implement which also gets Feature 2's directory changes
- Serialize: tasks.py first, then features 2-4 can be partially parallel
