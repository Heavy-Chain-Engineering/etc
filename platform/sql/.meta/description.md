# sql/

**Purpose:** PostgreSQL schema migrations defining the complete data model for the ETC Orchestration Platform. Applied in lexicographic order by `db.apply_schema()` and the test `conftest.py` fixture.

## Key Components
- `001_initial_schema.sql` -- Initial schema establishing all 11 tables, indexes, and the event notification trigger. Enables `pgcrypto` extension for UUID generation via `gen_random_uuid()`.
- `002_guardrail_overrides.sql` -- Migration adding override tracking columns (`override_reason`, `overridden_by`, `overridden_at`) to the `guardrail_checks` table.

## Tables (defined in 001)

### Core Entity
- `projects` -- Root entity. Columns: id (UUID PK), name, root_path, classification (CHECK: greenfield/brownfield/re-engineering/lift-and-shift/consolidation), status (CHECK: active/archived/failed), config (JSONB), timestamps. Indexed on status.

### Source Materials
- `source_materials` -- Intake artifacts. FK to projects (CASCADE). Columns: name, type (CHECK: pdf/code/export/spreadsheet/document), classification (CHECK: business_operations/requirements/implementation_artifact/domain_truth), priority (CHECK: primary/high/medium/context_only), path, reading_instructions. Indexed on project_id.

### SDLC Phase Lifecycle
- `phases` -- 8 SDLC phases per project. FK to projects (CASCADE). UNIQUE(project_id, name). Columns: name (CHECK: Bootstrap through Evaluate), status (CHECK: pending/active/completed/skipped), dod_items (JSONB array), entered_at, completed_at. Indexed on project_id and (project_id, status).
- `phase_transitions` -- Audit trail of phase advances. FK to projects. Columns: from_phase, to_phase, reason, approved_by, transitioned_at.

### Execution Graphs (C4)
- `execution_graphs` -- One per phase. FK to projects and phases (CASCADE). Columns: name, description, status (CHECK: pending/running/completed/failed), timestamps. Indexed on project_id and phase_id.
- `execution_nodes` -- Tree-structured nodes. FK to execution_graphs (CASCADE). Self-referential FK parent_node_id (CASCADE). Columns: node_type (CHECK: leaf/composite/reduce), name, agent_type, assignment (JSONB), reduce_inputs (JSONB), status (CHECK: pending/ready/running/completed/failed/retrying), output_path, max_retries (default 1), retry_count (default 0), depth (default 0), timestamps. Indexed on graph_id, (graph_id, status), parent_node_id.
- `execution_node_dependencies` -- DAG edges. Composite PK (node_id, depends_on_node_id). Both FK to execution_nodes (CASCADE).

### Agent Execution
- `agent_runs` -- One per agent execution attempt. FK to execution_nodes (CASCADE). Columns: agent_type, system_prompt_hash, model, status (CHECK: running/completed/failed/timeout), tokens_input, tokens_output, turns, error, timestamps. Indexed on node_id and status.
- `agent_outputs` -- Artifacts from agent runs. FK to agent_runs (CASCADE). Columns: output_type (CHECK: research_report/prd/code/test/adr/review), file_path, content_hash, accepted (boolean), guardrail_results (JSONB). Indexed on run_id.
- `guardrail_checks` -- Per-rule pass/fail results. FK to agent_outputs (CASCADE). Columns: rule_name, passed, severity (CHECK: critical/high/medium/low), violation_details (JSONB), checked_at. Override columns (from 002): override_reason, overridden_by, overridden_at. Indexed on output_id.

### Event System
- `events` -- Audit trail and coordination backbone. FK to projects (CASCADE). Columns: event_type, actor, payload (JSONB), created_at. Indexed on project_id, (project_id, event_type), (project_id, created_at). Has an AFTER INSERT trigger (`events_notify`) that calls `pg_notify('etc_events', ...)` with JSON payload containing id, project_id, event_type, and actor.

### Knowledge System
- `knowledge_entries` -- Shared working memory. FK to projects (CASCADE). Optional FK contributed_by to agent_runs. Self-referential FK superseded_by. Columns: scope (CHECK: project/phase/graph/node), scope_id (UUID), key, value (JSONB), timestamps. Indexed on project_id and (project_id, key).

## Dependencies
- PostgreSQL with `pgcrypto` extension
- Applied by `etc_platform.db.apply_schema()` and `tests/conftest.py`

## Patterns
- **UUID primary keys everywhere:** `gen_random_uuid()` via pgcrypto
- **CASCADE deletes:** All child tables cascade from their parent, ultimately rooting at `projects`
- **JSONB for flexible data:** dod_items, assignment, reduce_inputs, config, payload, violation_details, guardrail_results, value
- **CHECK constraints:** Enums enforced at the database level, not just application level
- **Event-driven trigger:** `notify_event()` PL/pgSQL function fires on every INSERT to `events`, broadcasting via `pg_notify('etc_events', ...)`
- **Timestamptz throughout:** All timestamps use `TIMESTAMPTZ` with `DEFAULT now()`

## Constraints
- Schema files must be applied in lexicographic order (001 before 002)
- Migration 002 uses `IF NOT EXISTS` for idempotent reruns
- No down migrations exist -- schema changes are forward-only
