# Getting Started with etc

This is a hands-on exercise that teaches you the etc coding harness by using it to build something real.

## What You'll Build

A web dashboard that monitors SDLC project progress — showing phase status, definition-of-done checklists, task completion, and transition history. It reads from the same state files that the harness itself produces.

## What You'll Learn

By the end of this exercise, you'll have experienced:

1. **The SEM orchestrator** managing the full SDLC lifecycle
2. **spec-kit /specify** driving structured requirements gathering
3. **TaskMaster** decomposing a PRD into an executable task graph
4. **TDD hooks** enforcing test-first development on every edit
5. **Watchdog agents** (code-reviewer, verifier, security-reviewer) running quality checks
6. **Phase gates** — the SEM blocking transitions until definition of done is met

## Prerequisites

1. **Install the harness** (if you haven't already):
   ```bash
   cd /path/to/etc-system-engineering
   ./install.sh
   ```

2. **Verify Claude Code has agent teams enabled** in `~/.claude/settings.json`:
   ```json
   {
     "env": {
       "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"
     }
   }
   ```

3. **Python 3.11+** installed

## The Exercise

### Step 1: Enter the project directory

```bash
cd getting-started
```

### Step 2: Initialize the SDLC workflow tracker

```bash
python3 ../.sdlc/tracker.py init
```

This creates `.sdlc/state.json` in this directory, starting you at the Bootstrap phase.

### Step 3: Open Claude Code

```bash
claude
```

### Step 4: Tell the SEM to take over

Say this (or something like it):

```
Use the sem agent to build this project. The PRD is in spec/prd.md.
We're starting from Bootstrap. Walk me through each SDLC phase.
```

### Step 5: Watch and learn

The SEM will:
- **Bootstrap** — Analyze what exists in this directory
- **Spec** — Review the PRD, possibly refine requirements with you
- **Design** — Have the architect agent create the system design
- **Decompose** — Use TaskMaster to break the PRD into tasks
- **Build** — Deploy developers with TDD hooks + watchdog agents
- **Ship** — Generate docs and verify everything works
- **Evaluate** — Run a retrospective on the process

At each phase gate, the SEM will check definition of done before proceeding. You'll see exactly how the harness enforces quality at every step.

### Step 6: Run the dashboard

When Build is complete:

```bash
pip install fastapi uvicorn
python3 app.py
```

Open your browser to `http://localhost:8000` — you'll see the dashboard showing this project's own SDLC progress.

## What's Provided vs. What Gets Built

**Provided (in this directory):**
- `spec/prd.md` — The product requirements document
- `.claude/CLAUDE.md` — Project-level harness configuration
- This README

**Built by the harness (during the exercise):**
- Everything else — the backend, frontend, tests, all of it

That's the point. You provide the spec. The harness builds the system.
