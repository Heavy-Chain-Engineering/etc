# etc — Engineering Team, Codified

An industrial-grade coding harness that establishes a synthetic engineering organization for AI-driven software development using Claude Code.

## Quick Start

```bash
git clone <this-repo>
cd etc-system-engineering
./install.sh
```

Then in `~/.claude/settings.json`, ensure agent teams are enabled:
```json
{
  "env": {
    "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"
  }
}
```

Launch Claude Code in any project. The full harness is active.

## How to Use

The harness is driven by the **SEM** (Software Engineering Manager) agent — the conductor that knows your SDLC phases, deploys the right agent teams, and enforces quality gates between phases.

### Starting a Project

**Brownfield (existing codebase):**
```
"Use the sem agent to bootstrap this codebase. We need to understand what's here before we start."
```
The SEM deploys the brownfield-bootstrapper to analyze your code and generate `.meta/` descriptions.

**Greenfield (new feature or project):**
```
"Use the sem agent. We're building [feature description]. Start from the Spec phase."
```
The SEM kicks off the Spec phase, deploying the product-manager with spec-kit's `/specify` to gather requirements.

### The SDLC Workflow

The SEM walks you through seven phases. Each phase has a **definition of done** that must be met before moving forward.

| Phase | What Happens | Agents Deployed | Key Tool |
|-------|-------------|-----------------|----------|
| **Bootstrap** | Analyze existing code, generate `.meta/` tree | brownfield-bootstrapper | — |
| **Spec** | Gather requirements, write PRDs | product-manager, product-owner, domain-modeler | spec-kit `/specify` |
| **Design** | Create architecture, ADRs, interaction flows | architect, ux-designer, ui-designer | — |
| **Decompose** | Break PRDs into task graph | product-manager, architect | TaskMaster |
| **Build** | Implement with TDD + continuous quality | backend/frontend-developer + watchdogs | TDD hooks |
| **Ship** | Docs, deployment config, final verification | technical-writer, devops-engineer, verifier | — |
| **Evaluate** | Retrospective, metrics, recommendations | process-evaluator | — |

### During Build: The Watchdog Pattern

Build phase is special. The SEM deploys:
- **One implementation agent** in the foreground (backend-developer, frontend-developer, or devops-engineer) working on the current task
- **Three quality agents** in the background as watchdogs:
  - **code-reviewer** — reviews each completed unit of work
  - **verifier** — runs tests and checks coverage
  - **security-reviewer** — scans for vulnerabilities

Plus the TDD hooks fire automatically on every file edit — checking that tests exist before allowing code changes.

### Asking the SEM Questions

```
"What phase are we in?"
"Are we ready to move to Build?"
"What's left before we can ship?"
"Deploy the build team for task 5."
```

The SEM checks the definition of done, gates transitions, and deploys teams. You focus on the product decisions.

## What Is This?

A complete set of AI agents, engineering standards, enforcement hooks, and workflow conventions that replicate the discipline of a well-run human software team — applied to Claude Code's agent teams.

**22 specialized agents** covering the full SDLC — including the SEM orchestrator that manages the entire lifecycle.

**17 engineering standards as files** — TDD workflow, clean code, testing standards, security checklists, architecture rules. Each independently maintainable and versionable.

**Mechanical enforcement** via hooks — TDD compliance checked on every edit. The system self-corrects.

## What Gets Installed

The installer copies three categories of assets to `~/.claude/`:

| Directory | Contents | Count |
|-----------|----------|-------|
| `agents/` | Specialized SDLC agent definitions | 22 |
| `standards/` | Engineering standards across 6 categories | 17 |
| `hooks/` | TDD enforcement scripts | 3 |

It also wires hook triggers into `~/.claude/settings.json` so enforcement is automatic.

## Architecture

Two-layer platform:

- **User-level (`~/.claude/`)** — Agents, standards, hooks. Installed from this repo. Reusable across all projects.
- **Project-level (`.claude/`, root files)** — Project-specific CLAUDE.md, test runner config, CI pipeline. Per-repo, checked into version control.

### Agent Hierarchy

```
Human (stakeholder, SME, final authority)
  └── SEM (orchestrator, phase manager)
        ├── Phase agents (foreground — do the work)
        └── Watchdog agents (background — enforce quality)
```

### SDLC Phases

Bootstrap → Spec → Design → Decompose → Build → Ship → Evaluate

Each phase has a definition of done. The SEM gates transitions.

## Repo Structure

```
agents/              22 agent definitions (source of truth)
standards/           17 engineering standards
  process/             SDLC phases, TDD workflow, code review, definition of done
  code/                Clean code, error handling, typing, Python conventions
  testing/             Test naming, testing standards, LLM evaluation
  architecture/        Abstraction rules, ADR process, layer boundaries
  security/            Data handling, OWASP checklist
  quality/             Metrics
hooks/               3 TDD enforcement scripts
settings-hooks.json  Hook wiring template for settings.json
install.sh           Bootstrap installer
docs/                Design documents and plans
```

## Connection to ISS

This harness is the first practical instantiation of [Industrialized System Synthesis](docs/plans/2026-02-25-coding-harness-design.md#connection-to-industrialized-system-synthesis) — a declarative approach where specs act as genotype and agent swarms express them into running systems (phenotype).

## Status

Phase 1 complete. User-level platform installed and verified.

- [Full Design Document](docs/plans/2026-02-25-coding-harness-design.md)
- [Implementation Plan](docs/plans/2026-02-25-phase1-user-level-platform.md)
- [Design Notes](docs/plans/harness-design-notes.md)
