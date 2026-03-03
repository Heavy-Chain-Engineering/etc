# etc — Engineering Team, Codified

An experiment in structured AI-driven software development. Can a set of agents, standards, and enforcement hooks replicate the discipline of a well-run engineering team — applied to Claude Code?

This repo is the test. Everything here is working theory.

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

Launch Claude Code in any project. The harness is active.

## How to Use

The harness is driven by the **SEM** (Software Engineering Manager) agent — an orchestrator that tracks SDLC phases, deploys agent teams, and gates transitions on definition-of-done checklists.

### Starting a Project

**Brownfield (existing codebase):**
```
"Use the sem agent to bootstrap this codebase. We need to understand what's here before we start."
```
The SEM deploys the project-bootstrapper to analyze your code and generate `.meta/` descriptions.

**Greenfield (new feature or project):**
```
"Use the sem agent. We're building [feature description]. Start from the Spec phase."
```
The SEM kicks off the Spec phase, deploying the product-manager with spec-kit's `/specify` to gather requirements.

### The SDLC Workflow

The SEM walks through seven phases. Each has a definition of done that must be met before moving forward.

| Phase | What Happens | Agents Deployed | Key Tool |
|-------|-------------|-----------------|----------|
| **Bootstrap** | Analyze existing code, generate `.meta/` tree | project-bootstrapper | — |
| **Spec** | Gather requirements, write PRDs | product-manager, product-owner, domain-modeler | spec-kit `/specify` |
| **Design** | Create architecture, ADRs, interaction flows | architect, ux-designer, ui-designer | — |
| **Decompose** | Break PRDs into task graph | product-manager, architect | TaskMaster |
| **Build** | Implement with TDD + continuous quality | backend/frontend-developer + watchdogs | TDD hooks |
| **Ship** | Docs, deployment config, final verification | technical-writer, devops-engineer, verifier | — |
| **Evaluate** | Retrospective, metrics, recommendations | process-evaluator | — |

### During Build: The Watchdog Pattern

Build phase deploys:
- **One implementation agent** in the foreground working on the current task
- **Three quality agents** in the background as watchdogs:
  - **code-reviewer** — reviews each completed unit of work
  - **verifier** — runs tests and checks coverage
  - **security-reviewer** — scans for vulnerabilities

TDD hooks fire automatically on every file edit — checking that tests exist before allowing code changes.

### Asking the SEM Questions

```
"What phase are we in?"
"Are we ready to move to Build?"
"What's left before we can ship?"
"Deploy the build team for task 5."
```

The SEM checks definition of done, gates transitions, and deploys teams. You focus on the product decisions.

### Try It: Onboarding Exercise

The `getting-started/` directory contains a spec for a project progress dashboard. Follow the README there to watch the harness build it end-to-end — that's the best way to understand how everything fits together.

## What's In the Box

| Category | Count | Description |
|----------|-------|-------------|
| Agents | 23 | SDLC role definitions (SEM orchestrator, PM, architect, developers, reviewers, etc.) |
| Standards | 17 | Engineering standards across 6 categories (process, code, testing, architecture, security, quality) |
| Hooks | 3 | TDD enforcement scripts (test-exists check, dirty marker, verification gate) |
| Tracker | 1 | SDLC phase state tracker with DoD gating |

The installer copies these to `~/.claude/` and wires hook triggers into `settings.json`.

## Architecture

Two layers:

- **User-level (`~/.claude/`)** — Agents, standards, hooks. Installed from this repo. Shared across all projects.
- **Project-level (`.claude/`, root files)** — Project-specific CLAUDE.md, test runner config, CI pipeline. Per-repo.

```
Human (stakeholder, SME, final authority)
  └── SEM (orchestrator, phase manager)
        ├── Phase agents (foreground — do the work)
        └── Watchdog agents (background — enforce quality)
```

## Repo Structure

```
agents/              23 agent definitions (source of truth)
standards/           17 engineering standards
  process/             SDLC phases, TDD workflow, code review, definition of done
  code/                Clean code, error handling, typing, Python conventions
  testing/             Test naming, testing standards, LLM evaluation
  architecture/        Abstraction rules, ADR process, layer boundaries
  security/            Data handling, OWASP checklist
  quality/             Metrics
hooks/               3 TDD enforcement scripts
.sdlc/               Workflow tracker (phase state + DoD gating)
getting-started/     Onboarding exercise (spec only — implementation is the exercise)
settings-hooks.json  Hook wiring template
install.sh           Bootstrap installer
platform/            v2 orchestration engine (Python, PydanticAI, Postgres)
  src/etc_platform/    Core modules (orchestrator, graph engine, guardrails, etc.)
  sql/                 Postgres schema migrations
  tests/               24 test files, 66+ tests
docs/                Design documents, PRDs, and plans
```

## Background

This explores ideas from [Industrialized System Synthesis](docs/plans/2026-02-25-coding-harness-design.md#connection-to-industrialized-system-synthesis) — the notion that specs act as genotype and agent teams express them into running systems. Whether that holds up in practice is what we're finding out.

## v2: Orchestration Platform

The `platform/` directory contains the v2 durable orchestration engine — an event-driven Python platform that persists all state to Postgres, enforces guardrails as middleware (not advice), and supports recursive task decomposition.

**[How It Works](platform/HOW-IT-WORKS.md)** — full architecture guide with data flow diagrams.

## Status

Phase 1 complete. User-level platform built and verified. v2 orchestration platform under active development.

- [Design Document](docs/plans/2026-02-25-coding-harness-design.md)
- [Implementation Plan](docs/plans/2026-02-25-phase1-user-level-platform.md)
- [v2 PRD](docs/vision/v2-orchestration-platform-prd.md)
- [Spec Enforcer Design](docs/plans/2026-02-28-spec-enforcer-design.md)
