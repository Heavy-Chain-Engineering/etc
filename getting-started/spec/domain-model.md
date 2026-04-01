# Domain Model — SDLC Dashboard

## Core Entities

### Phase
- **Name:** One of Bootstrap, Spec, Design, Decompose, Build, Ship, Evaluate
- **Status:** pending | active | completed
- **DoD Items:** List of definition-of-done checklist items
- **Entered At:** ISO timestamp when phase was entered (nullable)
- **Completed At:** ISO timestamp when phase was completed (nullable)

### DoD Item
- **Description:** Text description of the criterion
- **Done:** Boolean — whether this item is checked off

### Phase Transition
- **From Phase:** Phase name
- **To Phase:** Phase name
- **Reason:** Text explanation
- **Timestamp:** ISO timestamp

### Task (from TaskMaster)
- **ID:** Unique task identifier
- **Title:** Task title
- **Status:** One of: pending, in-progress, done, blocked, deferred, cancelled
- **Dependencies:** List of task IDs this task depends on
- **Priority:** high, medium, low
- **Description:** Task description

### Dashboard State (computed)
- **Current Phase:** The active phase
- **Phase Timeline:** Ordered list of all 7 phases with their statuses
- **DoD Progress:** Fraction of current phase's DoD items that are done
- **Task Summary:** Aggregated counts by task status
- **Transition History:** Ordered list of past phase transitions

## Relationships

```
DashboardState
├── current_phase: Phase (exactly one active)
├── phases: Phase[7] (always exactly 7)
│   └── dod_items: DoDItem[N]
├── transitions: PhaseTransition[0..N]
└── task_summary: TaskSummary
    └── derived from: Task[0..N]
```

## Data Sources

| Entity | Source File | Access |
|--------|-----------|--------|
| Phase, DoD Item, Transition | `.sdlc/state.json` | Read-only |
| Task | `.taskmaster/tasks/tasks.json` | Read-only |

## Invariants
- Exactly one phase is active at any time
- Phases are ordered: Bootstrap < Spec < Design < Decompose < Build < Ship < Evaluate
- A phase can only be active if all prior phases are completed (or skipped)
- State files are NEVER written to by the dashboard (INV-003)
