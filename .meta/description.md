# etc-system-engineering

**Purpose:** A synthetic AI engineering organization -- 23 agent definitions, 17 engineering standards, TDD enforcement hooks, an SDLC workflow tracker, and a durable orchestration platform -- that replicates the discipline of a well-run human software team, applied to Claude Code and other AI coding assistants.

## Key Components
- `agents/` -- 23 agent markdown definitions covering the full SDLC: orchestration (SEM), spec/design (PM, PO, architect, UX/UI designers, domain-modeler, researcher), build (backend/frontend developers, devops, code-simplifier, project-bootstrapper), quality gates (verifier, code-reviewer, security-reviewer, architect-reviewer, spec-enforcer), and analysis (gemini-analyzer, multi-tenant-auditor, process-evaluator, technical-writer).
- `standards/` -- 17 engineering standards across 6 categories (process, code, testing, architecture, security, quality) that agents read before producing any output.
- `hooks/` -- 4 TDD enforcement scripts (check-test-exists, mark-dirty, verify-green, check-invariants) plus 2 git hooks (post-commit stale marking, pre-push stale warning) wired via `settings-hooks.json`.
- `.sdlc/` -- SDLC workflow tracker with phase state machine, Definition of Done gating, and transition audit log.
- `platform/` -- v2 durable orchestration engine: event-driven Python platform (PydanticAI, psycopg3, Typer) that persists all state to PostgreSQL, enforces guardrails as middleware, and supports recursive task decomposition.
- `docs/` -- Design documents, implementation plans, research reports, vision documents, and lessons learned from v1 field testing.
- `scripts/` -- Utility scripts for `.meta/` reconciliation and maintenance.
- `getting-started/` -- Onboarding exercise: a spec for a project progress dashboard that demonstrates the harness building a project end-to-end.
- `install.sh` -- Bootstrap installer that copies agents, standards, hooks, and SDLC tracker to `~/.claude/` (or `~/.gemini/`) and wires hook triggers into settings.
- `settings-hooks.json` -- Hook wiring template merged into the AI assistant's settings during install.

## Dependencies
- Claude Code (or Antigravity/Gemini) as the AI coding assistant runtime
- Claude Code Agent Teams feature (`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`)
- For v2 platform: Python 3.11+, PostgreSQL, Docker Compose, PydanticAI, psycopg3, Typer, Rich
- TaskMaster MCP server for Decompose phase
- spec-kit for Spec phase (`/specify` command)

## Patterns
- **Two-layer architecture:** User-level components (`~/.claude/`) are shared across all projects; project-level components (`.claude/`, root files) are per-repo. Improvements to user-level propagate to all projects immediately.
- **SEM orchestrator pattern:** A single Software Engineering Manager agent owns the SDLC lifecycle, deploys agent teams, and gates phase transitions on Definition of Done checklists. The SEM never writes code -- it only makes decisions and delegates.
- **Watchdog pattern:** During Build phase, one implementation agent works in the foreground while three quality agents (code-reviewer, verifier, security-reviewer) run in the background as watchdogs.
- **Mechanical enforcement:** TDD hooks fire on every Edit/Write operation. Invariant checks run before file modifications. The verify-green hook runs tests, type checking, and linting before an agent can finish responding.
- **Industrialized System Synthesis (ISS):** Specs act as genotype; agent teams express them into running systems (phenotype). The harness is the first practical instantiation of this vision.

## Constraints
- The SEM is the sole orchestrator -- no other agent decides phase transitions or deploys teams.
- All engineering standards are MANDATORY unless explicitly marked REFERENCE.
- TDD is non-negotiable: test-first (red/green/refactor) with 98% coverage threshold enforced by hooks and CI.
- Agent definitions use YAML frontmatter + markdown format with `name`, `description` (including usage examples), `model`, `tools`, and `maxTurns`.
- The v2 platform enforces four architectural constraints: C1 (single SEM), C2 (stateless SEM), C3 (all state in Postgres), C4 (recursive decomposition).
