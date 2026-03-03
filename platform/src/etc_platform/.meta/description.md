# etc_platform/

**Purpose:** Core Python package implementing the ETC Orchestration Platform. Contains the SEM orchestrator, three engines (phase, graph, agent runtime), guardrail pipeline, event system, CLI, and supporting modules for knowledge management, metrics, topology design, intake, retry, and configuration.

## Key Components

### Orchestration Layer
- `orchestrator.py` -- SEM (Software Engineering Manager) orchestrator. Stateless decision loop (C2): loads scoped state from Postgres, calls PydanticAI for a structured `SEMDecision`, executes the decision. Eight decision types: `DEPLOY_AGENT`, `ADVANCE_PHASE`, `CHECK_DOD`, `WAIT`, `REQUEST_HUMAN_INPUT`, `MARK_NODE_READY`, `RETRY_FAILED_NODE`, `DESIGN_TOPOLOGY`. Contains `SEMOrchestrator` class, `SEMDecision` Pydantic model, `SEMDeps` dataclass, `load_scoped_state()`, `execute_decision()`, and `_build_user_prompt()`. Module-level `sem_agent` singleton for test override support.
- `run_engine.py` -- Mechanical run loop that operates without LLM calls. `RunEngine` class finds ready nodes, deploys agents via `AgentRunner`, checks graph completions, evaluates DoD status. Powers the `etc run` and `etc run --auto` CLI commands.

### Three Engines
- `phases.py` -- SDLC state machine with 8 gated phases: Bootstrap, Spec, Design, Decompose, Build, Verify, Ship, Evaluate. `PhaseEngine` class with static methods: `get_current_phase()`, `activate_phase()`, `add_dod_item()`, `check_dod_item()`, `evaluate_dod()`, `advance_phase()`. DoD items stored as JSONB arrays with check types: `automatic`, `agent_verified`, `human_confirmed`, `guardrail_verified`. Phase transitions require 100% DoD pass rate and are audited in `phase_transitions` table.
- `graph_engine.py` -- Execution graph scheduling with fan-out/reduce patterns (C4). `GraphEngine` class manages graph CRUD, node lifecycle (pending -> ready -> running -> completed | failed | retrying), dependency tracking, and graph completion detection. `build_fanout_graph()` convenience function creates a complete fan-out/reduce graph in one call. Node scheduling: nodes become ready when status is 'ready' (no-dep nodes promoted at graph start) or when all dependencies are completed.
- `agent_runtime.py` -- Agent execution lifecycle manager. `AgentRunner.deploy()` orchestrates: create run record, load prompt from `.md` file, build domain context, create PydanticAI `Agent[AgentDeps, AgentResult]` with tools, run via `run_sync()`, record output, emit `AGENT_COMPLETED` event. Five registered tools: `read_file`, `write_file`, `search_files`, `query_knowledge`, `contribute_knowledge`. `build_domain_context()` injects project classification, source materials briefing, and anti-pattern catalog (for re-engineering projects).

### Guardrail Pipeline
- `guardrails.py` -- Middleware that checks every agent output before acceptance. Seven rule classes inheriting from `GuardrailRule`: `AntiPatternScanRule` (regex: boolean flags, hardcoded enums, legacy mappings -- critical severity, applies to research_report/prd), `OutputSchemaValidationRule` (required sections per output type -- high severity), `SpecComplianceRule` (LLM-based adversarial spec checker -- critical), `DomainFidelityRule` (LLM-based domain axiom checker -- critical), `CoverageGateRule` (pytest coverage threshold -- high), `TDDVerificationRule` (tests alongside implementation -- medium), `SecurityScanRule` (SQL injection, XSS, hardcoded secrets, insecure deserialization -- high). `GuardrailMiddleware` class runs all rules, records results to `guardrail_checks` table, updates `agent_outputs.accepted`, and emits `GUARDRAIL_VIOLATION` events on critical failures. Override support allows humans to flip failed checks with justification.

### Event System
- `events.py` -- Postgres `LISTEN/NOTIFY` based event coordination. `EventType` enum with 8 types: `AGENT_STARTED`, `AGENT_COMPLETED`, `PHASE_GATE_REACHED`, `GUARDRAIL_VIOLATION`, `HUMAN_RESPONSE`, `KNOWLEDGE_UPDATED`, `NODE_READY`, `SEM_DECISION`. `emit_event()` inserts into `events` table (trigger auto-fires `pg_notify`). `EventBus` class listens for notifications and dispatches to registered handlers by event type.

### Supporting Modules
- `config.py` -- TOML configuration loader. `EtcConfig` dataclass with defaults for database_url, default_model, agents_dir, standards_dir, log_level, max_concurrent_agents, agent_timeout_seconds, workspace settings. Loads from `~/.etc/config.toml` (global) then `./etc.toml` (local override). `ETC_DATABASE_URL` env var takes final precedence.
- `db.py` -- psycopg3 connection pool management. `get_pool()` creates a singleton `ConnectionPool` (min=2, max=10, dict_row factory). `get_conn()` context manager yields connections. `apply_schema()` runs all SQL migrations in order. `get_dsn()` reads from `ETC_DATABASE_URL` env var or falls back to default.
- `knowledge.py` -- Shared working memory with scoping, versioning, and conflict detection. `contribute_knowledge()` auto-supersedes previous entries for the same key+scope+scope_id. `query_knowledge()` returns latest non-superseded entry. `detect_conflicts()` finds keys with multiple non-superseded entries from different contributors. `resolve_conflict()` marks losing entries as superseded. Four scope levels: project, phase, graph, node.
- `intake.py` -- Source material CRUD and triage. Validates type (pdf, code, export, spreadsheet, document), classification (business_operations, requirements, implementation_artifact, domain_truth), and priority (primary, high, medium, context_only). `batch_add_materials()`, `triage_summary()`, `generate_domain_briefing_skeleton()`.
- `topology.py` -- LLM-based topology design. Two-stage process: `assess_topology()` analyzes source materials via PydanticAI to produce a `TopologyPlan` (layers, nodes, reduce strategy), then `generate_graph()` converts the plan into an execution graph with nodes and dependencies. `build_topology()` combines both stages.
- `metrics.py` -- Read-only aggregate queries for observability. `ProjectMetrics` class with static methods: `get_token_usage()`, `get_agent_velocity()`, `get_phase_duration()`, `get_guardrail_stats()`, `get_project_summary()`.
- `retry.py` -- Exponential backoff retry with violation context injection. `should_retry()` checks eligibility (status=failed, retry_count < max_retries). `prepare_retry()` increments count, builds augmented context with "PREVIOUS ATTEMPT FAILED: ..." message. `execute_retry()` full flow: check eligibility, prepare, deploy agent with augmented assignment. `retry_all_eligible()` batch retries all failed nodes.
- `__init__.py` -- Package marker with `__version__ = "0.1.0"`.

### CLI
- `cli.py` -- Typer + Rich command interface. Root `app` with subcommand groups: `phase_app`, `dod_app`, `knowledge_app`, `guardrails_app`, `topology_app`. Uses lazy imports for all heavy modules. Helper functions `_get_active_project()` and `_require_active_project()` for common project lookup pattern.

## Dependencies
- **Internal (inter-module):** `orchestrator` imports `config`, `events`, `phases`, `knowledge`, `agent_runtime`, `retry`, `topology`. `run_engine` imports `agent_runtime`, `config`, `events`, `graph_engine`, `phases`. `agent_runtime` imports `config`, `events`, `intake`, `knowledge`. `guardrails` imports `events`. `retry` imports `agent_runtime`. `topology` imports `graph_engine`, `intake`. `phases` imports `events`. `cli` imports all modules via lazy imports.
- **External:** psycopg3/psycopg-pool, pydantic/pydantic-ai, typer/rich, tomllib (stdlib 3.11+)

## Patterns
- **Static method classes:** `PhaseEngine`, `GraphEngine`, `ProjectMetrics` use exclusively `@staticmethod` methods that accept a `psycopg.Connection` as first argument -- no instance state, pure functions over the database.
- **PydanticAI Agent pattern:** `Agent[DepsType, OutputType]` with `deps_type`, `output_type`, `system_prompt`, and `defer_model_check=True`. Tools registered via `@agent.tool` decorator with `RunContext[DepsType]`.
- **Test injection points:** `_check_fn` attribute on LLM-based guardrail rules for injecting test doubles. `model_override` parameter on agent/topology functions for PydanticAI `TestModel`. Module-level `sem_agent` singleton with `.override()` context manager.
- **Lazy CLI imports:** Every CLI command function imports its dependencies at call time, not module level, keeping `typer` startup fast.

## Constraints
- **C1 (Single SEM):** `SEMOrchestrator` is the sole decision-maker. It never writes code or does research -- only delegates.
- **C2 (Stateless SEM):** Each decision cycle in `make_decision()` loads fresh state via `load_scoped_state()`. No state carried between calls.
- **C3 (All state in Postgres):** No in-memory state, no file-based state, no Redis. `RunEngine` can be instantiated fresh after a crash and find all pending work.
- **C4 (Recursive decomposition):** `execution_nodes.parent_node_id` supports trees within trees. Graph scheduling respects dependency DAGs.
