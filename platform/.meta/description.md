# platform/

**Purpose:** The ETC Orchestration Platform is a durable, event-driven system that deploys AI agent teams through a full SDLC (Software Development Lifecycle). It persists all state to PostgreSQL, enforces guardrails as middleware on every agent output, and supports recursive task decomposition via tree-structured execution graphs.

## Key Components
- `src/etc_platform/` -- Core Python package containing all platform modules (16 source files). The SEM orchestrator, three engines (phase, graph, agent runtime), guardrail pipeline, event system, CLI, and supporting services.
- `tests/` -- 22 test files plus conftest providing 66+ tests. All tests use a real Postgres database via Docker, with per-test transaction rollback for isolation. No real LLM API calls -- PydanticAI `TestModel` is used throughout.
- `sql/` -- PostgreSQL schema migrations (2 files). Defines all 11 tables, indexes, the NOTIFY trigger, and the guardrail override extension.
- `HOW-IT-WORKS.md` -- Comprehensive architectural documentation with diagrams, data model, agent roster, and constraint explanations.
- `pyproject.toml` -- Project metadata, dependencies, build config (hatchling), tool configuration (ruff, mypy strict mode, pytest, 95% coverage target).
- `docs/vision/v2.1-roadmap.md` -- Future roadmap document.

## Dependencies
- **Runtime:** Python 3.11+, PydanticAI (model-agnostic agent framework), psycopg3 + psycopg-pool (PostgreSQL), Typer + Rich (CLI), Pydantic v2 (data validation)
- **Dev:** pytest, pytest-asyncio, pytest-cov, testcontainers, ruff, mypy (strict)
- **Infrastructure:** PostgreSQL (via Docker Compose, port 5433), configurable LLM backends (never hardcoded)
- **External:** Agent prompt `.md` files loaded from `~/.claude/agents/`, TOML config from `~/.etc/config.toml` and local `etc.toml`

## Patterns
- **Architectural constraints (C1-C4):** Single SEM orchestrator delegates everything (C1). SEM is stateless between decisions -- fresh Postgres load each cycle (C2). All state in Postgres, no in-memory/file/Redis state, enabling restart-from-anywhere (C3). Tree-based execution graphs with parent_node_id for recursive decomposition (C4).
- **Event-driven coordination:** PostgreSQL `LISTEN/NOTIFY` via `events` table trigger. Eight event types drive the SEM decision loop.
- **Guardrail middleware pipeline:** Every agent output passes through configurable guardrail rules before acceptance. Critical failures mechanically reject output -- no agent can bypass this.
- **Fan-out/reduce execution:** Execution graphs use parallel leaf nodes (fan-out) that feed into reduce/synthesis nodes, with dependency-based scheduling.
- **Lazy imports in CLI:** All heavy modules (`db`, `phases`, `intake`, etc.) are imported inside CLI command functions, keeping CLI startup fast.
- **PydanticAI structured output:** Both the SEM orchestrator and individual agents use PydanticAI `Agent[Deps, OutputModel]` with typed structured output. Models are configured via TOML, never hardcoded.

## Constraints
- **No ORM:** All database access is raw SQL via psycopg3 with `dict_row` factory. Tables use UUID primary keys and `TIMESTAMPTZ` timestamps.
- **Coverage target:** 95% code coverage enforced via `pytest-cov`.
- **Type safety:** mypy strict mode enabled across the codebase.
- **Model agnosticism:** LLM model identifiers are always configurable strings (e.g., `"anthropic:claude-sonnet-4-20250514"`). The `defer_model_check=True` flag is used on all PydanticAI agents to avoid import-time validation.
- **Entry point:** `etc` CLI registered via `project.scripts` in pyproject.toml, pointing to `etc_platform.cli:app`.

## Entry Points
- `etc` CLI command (Typer app) -- primary human interface with subcommands: `init`, `status`, `run`, `agents`, `history`, `phase {status,approve,list}`, `dod {status,check,add}`, `knowledge {list,conflicts,resolve}`, `guardrails {status,override}`, `topology {show,approve,reject}`
- `SEMOrchestrator.run()` -- blocking event loop that listens for Postgres NOTIFY and drives the decision cycle
- `RunEngine.run_once()` -- single mechanical cycle (deploy ready nodes, check completions, evaluate DoD) without LLM involvement
