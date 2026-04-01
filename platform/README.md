# Platform — v2 Orchestration Engine

**Status:** Research / Future Direction

This directory contains the v2 durable orchestration engine — an event-driven
Python platform that was the original approach to enforcing engineering discipline.
It persists state to Postgres, runs guardrails as middleware, and supports
recursive task decomposition.

## Relationship to the Main Harness

The main harness (hooks + DSL + compiler at the repo root) evolved from the ideas
prototyped here. Key concepts that migrated:

| Platform Concept | Harness Equivalent |
|-----------------|-------------------|
| Guardrail middleware | Pre/post tool hooks + `standards/quality/guardrail-rules.md` |
| Phase state machine | `.sdlc/tracker.py` + DoD gating |
| Agent definitions | `agents/*.md` with frontmatter |
| Spec compliance rule | `ci-pipeline` agent hook (Stop event) |
| Security scan rule | `block-dangerous-commands.sh` + security standards |
| TDD verification | `check-test-exists.sh` hook |
| Retry with context injection | `on_loop: escalate` pattern in DSL |

## Ideas Not Yet Migrated

These concepts exist only in the platform and represent future directions:

- **Execution graphs (DAG)** — Fan-out/reduce patterns for parallel task trees
- **Knowledge graph** — Scoped, versioned inter-agent shared state
- **Source material intake** — Structured document triage and domain briefing generation
- **Event-driven coordination** — Postgres LISTEN/NOTIFY for real-time agent orchestration
- **LLM-based topology design** — Automatic execution graph generation from specs
- **Metrics collection** — Token usage, phase duration, guardrail pass/fail rates

## Architecture

See [HOW-IT-WORKS.md](HOW-IT-WORKS.md) for the full architecture guide.

## Running the Platform

The platform requires Postgres and additional Python dependencies:

```bash
cd platform
docker compose up -d   # Start Postgres
uv sync                # Install dependencies
uv run pytest          # Run platform tests
```

This is independent of the main harness and is not required for using etc.
