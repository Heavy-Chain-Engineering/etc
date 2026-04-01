# .sdlc/

**Purpose:** SDLC workflow tracker that manages phase state, Definition of Done gating, and transition audit logging. Provides the state machine that the SEM agent uses to track which phase a project is in and whether it is ready to advance. Installed to `~/.claude/sdlc/` by `install.sh`.

## Key Components
- `tracker.py` -- Python CLI for SDLC state management. Commands: `init` (create state.json from DoD templates), `current` (print current phase), `status` (print phase + DoD checklist with progress), `check <index>` (mark DoD item complete), `uncheck <index>` (mark DoD item incomplete), `transition <phase> [reason]` (advance to a new phase, gated on 100% DoD completion), `history` (print phase transition log). Uses atomic file writes (write to temp, then rename) for state safety. State file lives in the project directory (`CWD/.sdlc/state.json`), while templates live next to the script.
- `dod-templates.json` -- Definition of Done templates for all 8 SDLC phases. Bootstrap (3 items: .meta/ tree, gap analysis, project structure documented), Spec (9 items: project intake, domain briefing, domain fidelity, research plan, PRD, architecture concerns, acceptance criteria, domain model validated, edge cases), Design (4 items: ADRs, interfaces, UX flows, technical risks), Decompose (5 items: tasks decomposed, dependencies mapped, acceptance criteria per task, t-shirt sizing, architect review), Build (7 items: TDD implementation, tests passing, coverage, code review, security review, Docker/run config, no blocking issues), Verify (4 items: stack stood up, access provided, human acceptance testing, feedback addressed), Ship (4 items: documentation updated, deployment config, CI passing, verifier approval), Evaluate (5 items: metrics collected, release notes, retrospective, improvement recommendations, lessons learned).

## Dependencies
- Invoked by the SEM agent (`sem.md`) via `python3 ~/.claude/sdlc/tracker.py status`
- DoD templates define the exit criteria that the SEM checks before allowing phase transitions
- State file (`state.json`) is per-project, created in `CWD/.sdlc/` on `init`
- Python standard library only (json, os, sys, tempfile, datetime) -- no external dependencies

## Patterns
- **Per-project state, global templates:** Templates (`dod-templates.json`) live with the tracker script (user-level), but state (`state.json`) is created per-project in the working directory's `.sdlc/` folder.
- **Gated transitions:** `transition` command refuses to advance if any DoD item is unchecked -- this is a hard gate, not a warning.
- **Atomic writes:** State is written to a temp file then renamed, preventing corruption from interrupted writes.
- **Ordered phases:** Phase order is fixed (Bootstrap -> Spec -> Design -> Decompose -> Build -> Verify -> Ship -> Evaluate), though forward jumps are allowed if DoD is satisfied.

## Constraints
- `state.json` must not already exist when running `init` -- delete it first to reinitialize.
- Phase transitions require 100% DoD completion -- no partial advancement.
- The tracker uses exit codes: 0 = success, 1 = validation failure (e.g., incomplete DoD), 2 = error (e.g., missing file, bad index).
- No database or external service dependencies -- pure filesystem state management via JSON files.
