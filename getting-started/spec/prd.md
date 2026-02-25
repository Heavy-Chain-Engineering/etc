# SDLC Dashboard — Product Requirements Document

## Overview

A web dashboard that monitors SDLC project progress in real time. It reads from the harness's own state files (`.sdlc/state.json` and `.taskmaster/tasks/tasks.json`) and renders a visual overview of where a project stands.

## Problem

When using the etc coding harness across multiple projects, there's no visual way to see:
- Which SDLC phase a project is in
- How close you are to completing the current phase's definition of done
- The history of phase transitions
- Task completion progress from TaskMaster

The SEM agent can query this via CLI, but humans need a glanceable overview.

## Users

- **Primary:** Engineers using the etc harness who want to monitor project progress
- **Secondary:** Engineering managers tracking multiple harness-driven projects

## Requirements

### P0 — Must Have

1. **Phase indicator** — Show the current SDLC phase prominently (Bootstrap, Spec, Design, Decompose, Build, Ship, Evaluate)
2. **Phase timeline** — Visual timeline showing all 7 phases with the current one highlighted and completed ones marked
3. **DoD checklist** — For the current phase, show each definition-of-done item with checked/unchecked status
4. **DoD progress bar** — Percentage of current phase's DoD items completed
5. **Task summary** — From TaskMaster: total tasks, completed, in-progress, pending, blocked
6. **Auto-refresh** — Dashboard updates when underlying JSON files change (polling every 5s is fine)

### P1 — Should Have

7. **Phase transition history** — Table or timeline of all phase transitions with timestamps and reasons
8. **Task breakdown by status** — Visual chart (bar or pie) of task statuses
9. **Multi-project support** — Point the dashboard at multiple project directories and show a summary card per project
10. **Dark mode** — Because engineers

### P2 — Nice to Have

11. **Agent activity log** — Show which agents were deployed in each phase
12. **Time-in-phase metrics** — How long each phase took
13. **Export** — Download project status as a report

## Technical Constraints

- **Backend:** Python (FastAPI or Flask). Stdlib + one framework, no heavy dependencies.
- **Frontend:** Vanilla HTML + CSS + JavaScript. No React, no build step, no node_modules.
- **Data source:** Read `.sdlc/state.json` and `.taskmaster/tasks/tasks.json` from disk. No database.
- **Deployment:** `python3 app.py` and open browser. That's it.
- **Testing:** pytest for backend, manual verification for frontend (this is a learning exercise, not production).

## Non-Requirements

- Authentication (local tool only)
- Persistent storage beyond the JSON files
- Real-time WebSocket updates (polling is fine)
- Mobile responsive design (desktop browser is the target)

## Acceptance Criteria

- [ ] Dashboard loads and shows current phase from `.sdlc/state.json`
- [ ] Phase timeline renders all 7 phases with correct current/completed states
- [ ] DoD checklist renders and reflects actual state
- [ ] Task summary reads from `.taskmaster/tasks/tasks.json` and shows counts
- [ ] Changing the state files (via `tracker.py` or manually) is reflected on next refresh
- [ ] `python3 app.py` starts the server with no additional setup beyond `pip install fastapi uvicorn`
