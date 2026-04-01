# tests/

**Purpose:** Test suite for the ETC Orchestration Platform, providing 66+ tests across 22 test files. All tests use a real PostgreSQL database (via Docker on port 5433) with per-test transaction rollback for isolation. No real LLM API calls are made -- PydanticAI `TestModel` and `unittest.mock` are used throughout.

## Key Components

### Test Infrastructure
- `conftest.py` -- Shared pytest fixtures. `pg_dsn` (session-scoped): reads `ETC_TEST_DATABASE_URL` or defaults to `postgresql://etc:etc_dev@localhost:5433/etc_platform_test`. `setup_test_db` (session-scoped): drops/creates the test database, applies all SQL migrations. `db` (function-scoped): provides a psycopg connection with `dict_row` factory, wrapped in BEGIN/ROLLBACK for test isolation.
- `__init__.py` -- Empty package marker.

### Module-Level Tests
- `test_orchestrator.py` -- Tests for SEM orchestrator (largest test file). Classes: `TestSEMDecision` (model validation), `TestSEMSystemPrompt` (prompt content), `TestLoadScopedState` (state loading from Postgres -- phases, DoD, ready nodes, events, graphs), `TestExecuteDecision` (all 8 decision types including deploy, advance, check_dod, wait, request_human_input, mark_node_ready, design_topology), `TestSEMOrchestrator` (init, make_decision with TestModel, handle_event full cycle), `TestSEMDeps`, `TestLoadScopedStateProjectContext` (project info, material summary, conflicts in state), `TestBuildUserPromptProjectContext` (prompt formatting for project context, re-engineering warnings, conflicts), `TestDecisionAuditTrail` (universal sem_decision event recording).
- `test_phases.py` -- Tests for PhaseEngine: phase ordering, activation, DoD item lifecycle (add, check, evaluate), gated phase transitions, transition auditing, edge cases (last phase, no DoD).
- `test_graph_engine.py` -- Tests for GraphEngine and `build_fanout_graph`: graph CRUD, node scheduling (dependency resolution, ready detection), fan-out/reduce pattern, node lifecycle, graph completion detection, and recursive decomposition (C4). Recursive decomposition test classes: `TestCompositeActivation` (root composites activate to 'running' on graph start), `TestParentActivationGate` (composites never in ready nodes, children gated by parent status), `TestCompositeStatusRollup` (auto-complete when all children done, ancestor cascade), `TestCompositeActivationAfterDeps` (composites activate when dependencies resolve), `TestFailurePropagation` (child failure propagates to parent when retries exhausted), `TestSubtreeReset` (recursive CTE resets composite and all descendants), `TestCrossBranchDependencies` (cross-branch, cross-depth dependency verification).
- `test_agent_runtime.py` -- Tests for AgentRunner: deploy lifecycle, prompt loading (file-based and fallback), domain context building, tool registration, run recording, output recording, event emission. Uses `TestModel` to avoid real API calls.
- `test_guardrails.py` -- Tests for all 7 guardrail rules: `AntiPatternScanRule` (boolean flags, enums, legacy mappings, non-applicable types), `OutputSchemaValidationRule` (required sections, code validation), `DomainFidelityRule` (axiom checking with injected `_check_fn`), `CoverageGateRule` (threshold, parsing), `TDDVerificationRule` (test patterns, files_written context), `SecurityScanRule` (SQL injection, secrets, XSS, deserialization), `SpecComplianceRule` (adversarial spec checking with injected `_check_fn`). Also tests `GuardrailMiddleware` (check_and_record, recording, acceptance logic).
- `test_guardrail_override.py` -- Tests for guardrail override support: overriding failed checks, re-evaluation of output acceptance, listing checks with override info.
- `test_guardrail_retry_flow.py` -- Tests for the guardrail -> retry integration: violation event emission, retry with augmented context.
- `test_events.py` -- Tests for event system: `emit_event()`, `EventType` enum, `EventBus` handler registration and dispatch.
- `test_knowledge.py` -- Tests for knowledge module: contribute, query, supersession, scoped entries, history, conflict detection, conflict resolution, deletion.
- `test_knowledge_cli.py` -- Tests for knowledge CLI commands (list, conflicts, resolve) using `CliRunner`.
- `test_intake.py` -- Tests for source material intake: add, list (priority ordering), get, update (with validation), delete, batch_add, triage_summary, domain_briefing_skeleton.
- `test_topology.py` -- Tests for topology module: `assess_topology()` with TestModel, `generate_graph()` plan-to-graph conversion, layer dependencies, reduce strategies, `build_topology()` convenience function.
- `test_topology_cli.py` -- Tests for topology CLI commands (show, approve, reject) using `CliRunner`.
- `test_config.py` -- Tests for configuration loading: default values, TOML file parsing, env var override, config file discovery.
- `test_db.py` -- Tests for database module: DSN resolution, pool creation, connection context manager, schema application.
- `test_metrics.py` -- Tests for ProjectMetrics: token usage, agent velocity, phase durations, guardrail stats, project summary.
- `test_retry.py` -- Tests for retry module: should_retry eligibility, prepare_retry context building, execute_retry full flow, get_failed_nodes, retry_all_eligible.
- `test_run_engine.py` -- Tests for RunEngine: run_once cycle, deploy_ready_nodes, check_graph_completions, get_status, get_pending_actions. `TestRunEngineCompositeFiltering` verifies composites are excluded from deployment and pending actions queries. Mocks `AgentRunner.deploy` to avoid real API calls.
- `test_schema.py` -- Tests that verify SQL schema constraints (CHECK constraints, FK relationships, NOT NULL, UNIQUE).
- `test_cli.py` -- Tests for CLI commands (version, help, init, status) using Typer `CliRunner`.
- `test_cli_phase.py` -- Tests for phase-related CLI commands (phase status, phase approve, phase list, dod status, dod check, dod add).
- `test_integration.py` -- End-to-end integration tests. `TestFullProjectLifecycle`: init-to-bootstrap, source material triage, fanout graph lifecycle, knowledge sharing with conflict resolution, guardrail pipeline, run engine cycle, event audit trail. `TestResilience`: status queryable after partial run, pending actions discoverable after restart (C3 verification).

## Dependencies
- **Internal:** All modules under `etc_platform` (imported directly in test files)
- **External:** pytest, pytest-asyncio, pytest-cov, psycopg3, pydantic-ai (TestModel), typer (CliRunner), unittest.mock
- **Infrastructure:** PostgreSQL running on `localhost:5433` with user `etc` / password `etc_dev`

## Patterns
- **Real database, fake LLM:** Every test that touches the database uses the `db` fixture (real Postgres with rollback). Every test that would call an LLM uses PydanticAI `TestModel` or injects a `_check_fn` callable.
- **Per-test isolation via rollback:** The `db` fixture wraps each test in `BEGIN/ROLLBACK`, so tests never pollute each other's data.
- **Helper functions for FK chains:** Most test files define `_create_project()`, `_create_all_phases()`, and `_setup_output_chain()` helpers that build the required foreign key chains (project -> phase -> graph -> node -> run -> output).
- **Class-based test organization:** Tests are organized into classes by concern (e.g., `TestSEMDecision`, `TestLoadScopedState`, `TestFullProjectLifecycle`).
- **Mock at the boundary:** `unittest.mock.patch` is used to mock `AgentRunner.deploy()` in RunEngine tests and `assess_topology()` in orchestrator tests -- always at the boundary where LLM calls would happen.

## Constraints
- Tests require a running PostgreSQL instance (typically via Docker Compose)
- The test database (`etc_platform_test`) is dropped and recreated each session
- No async tests are currently used despite `pytest-asyncio` being in dev dependencies
- Coverage target is 95% (`tool.coverage.report.fail_under = 95` in pyproject.toml)
