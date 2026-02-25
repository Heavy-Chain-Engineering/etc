# etc — Engineering Team, Codified

An industrial-grade coding harness that establishes a synthetic engineering organization for AI-driven software development.

## Quick Start

```bash
git clone <this-repo>
cd etc-system-engineering
./install.sh
```

That's it. Launch Claude Code in any project and the full harness is active.

## What Is This?

A complete set of AI agents, engineering standards, enforcement hooks, and workflow conventions that replicate the discipline of a well-run human software team — applied to Claude Code.

**21 specialized agents** covering the full SDLC: product management, UX/UI design, architecture, domain modeling, backend/frontend development, code review, QA verification, security review, DevOps, technical writing, process evaluation, brownfield bootstrapping, and more.

**17 engineering standards as files** — not buried in prompts. TDD workflow, clean code, testing standards, security checklists, architecture rules — each independently maintainable and versionable.

**Mechanical enforcement** via hooks — not just documentation. TDD compliance checked on every edit. The system self-corrects.

## What Gets Installed

The installer copies three categories of assets to `~/.claude/`:

| Directory | Contents | Count |
|-----------|----------|-------|
| `agents/` | Specialized SDLC agent definitions | 21 |
| `standards/` | Engineering standards across 6 categories | 17 |
| `hooks/` | TDD enforcement scripts | 3 |

It also wires hook triggers into `~/.claude/settings.json` so enforcement is automatic.

## Architecture

Two-layer platform:

- **User-level (`~/.claude/`)** — Agents, standards, hooks. Installed from this repo. Reusable across all projects.
- **Project-level (`.claude/`, root files)** — Project-specific CLAUDE.md, test runner config, CI pipeline. Per-repo, checked into version control.

### SDLC Phases

Bootstrap → Spec → Design → **Decompose** → Build → Ship → Evaluate

The **Decompose** phase uses [TaskMaster](https://github.com/task-master-ai/task-master-ai) to break PRDs into executable task graphs before implementation begins.

## Repo Structure

```
agents/           21 agent definitions (source of truth)
standards/        17 engineering standards
  process/          SDLC phases, TDD workflow, code review, definition of done
  code/             Clean code, error handling, typing, Python conventions
  testing/          Test naming, testing standards, LLM evaluation
  architecture/     Abstraction rules, ADR process, layer boundaries
  security/         Data handling, OWASP checklist
  quality/          Metrics
hooks/            3 TDD enforcement scripts
settings-hooks.json   Hook wiring template for settings.json
install.sh        Bootstrap installer
docs/             Design documents and plans
```

## Connection to ISS

This harness is the first practical instantiation of [Industrialized System Synthesis](docs/plans/2026-02-25-coding-harness-design.md#connection-to-industrialized-system-synthesis) — a declarative approach where specs act as genotype and agent swarms express them into running systems (phenotype).

## Status

Phase 1 complete. User-level platform installed and verified.

- [Full Design Document](docs/plans/2026-02-25-coding-harness-design.md)
- [Implementation Plan](docs/plans/2026-02-25-phase1-user-level-platform.md)
- [Design Notes](docs/plans/harness-design-notes.md)
