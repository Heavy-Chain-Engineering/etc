-- ETC Orchestration Platform — Initial Schema
-- Implements PRD Section 5: Data Model

-- Enable UUID generation
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ============================================================================
-- Projects
-- ============================================================================
CREATE TABLE projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    root_path TEXT NOT NULL,
    classification TEXT NOT NULL CHECK (classification IN (
        'greenfield', 'brownfield', 're-engineering', 'lift-and-shift', 'consolidation'
    )),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'archived', 'failed')),
    config JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_projects_status ON projects (status);

-- ============================================================================
-- Source materials (from project intake)
-- ============================================================================
CREATE TABLE source_materials (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects ON DELETE CASCADE,
    name TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('pdf', 'code', 'export', 'spreadsheet', 'document')),
    classification TEXT NOT NULL CHECK (classification IN (
        'business_operations', 'requirements', 'implementation_artifact', 'domain_truth'
    )),
    priority TEXT NOT NULL CHECK (priority IN ('primary', 'high', 'medium', 'context_only')),
    path TEXT,
    reading_instructions TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_source_materials_project ON source_materials (project_id);

-- ============================================================================
-- SDLC phase lifecycle
-- ============================================================================
CREATE TABLE phases (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects ON DELETE CASCADE,
    name TEXT NOT NULL CHECK (name IN (
        'Bootstrap', 'Spec', 'Design', 'Decompose', 'Build', 'Verify', 'Ship', 'Evaluate'
    )),
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'active', 'completed', 'skipped')),
    dod_items JSONB NOT NULL DEFAULT '[]',
    entered_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    UNIQUE (project_id, name)
);

CREATE INDEX idx_phases_project ON phases (project_id);
CREATE INDEX idx_phases_status ON phases (project_id, status);

CREATE TABLE phase_transitions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects ON DELETE CASCADE,
    from_phase TEXT NOT NULL,
    to_phase TEXT NOT NULL,
    reason TEXT,
    approved_by TEXT,
    transitioned_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_phase_transitions_project ON phase_transitions (project_id);

-- ============================================================================
-- Execution graphs (recursive decomposition — C4)
-- ============================================================================
CREATE TABLE execution_graphs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects ON DELETE CASCADE,
    phase_id UUID NOT NULL REFERENCES phases ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN (
        'pending', 'running', 'completed', 'failed'
    )),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ
);

CREATE INDEX idx_execution_graphs_project ON execution_graphs (project_id);
CREATE INDEX idx_execution_graphs_phase ON execution_graphs (phase_id);

CREATE TABLE execution_nodes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    graph_id UUID NOT NULL REFERENCES execution_graphs ON DELETE CASCADE,
    parent_node_id UUID REFERENCES execution_nodes ON DELETE CASCADE,
    node_type TEXT NOT NULL CHECK (node_type IN ('leaf', 'composite', 'reduce')),
    name TEXT NOT NULL,
    agent_type TEXT,
    assignment JSONB,
    reduce_inputs JSONB,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN (
        'pending', 'ready', 'running', 'completed', 'failed', 'retrying'
    )),
    output_path TEXT,
    max_retries INTEGER NOT NULL DEFAULT 1,
    retry_count INTEGER NOT NULL DEFAULT 0,
    depth INTEGER NOT NULL DEFAULT 0,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ
);

CREATE INDEX idx_execution_nodes_graph ON execution_nodes (graph_id);
CREATE INDEX idx_execution_nodes_status ON execution_nodes (graph_id, status);
CREATE INDEX idx_execution_nodes_parent ON execution_nodes (parent_node_id);

CREATE TABLE execution_node_dependencies (
    node_id UUID NOT NULL REFERENCES execution_nodes ON DELETE CASCADE,
    depends_on_node_id UUID NOT NULL REFERENCES execution_nodes ON DELETE CASCADE,
    PRIMARY KEY (node_id, depends_on_node_id)
);

-- ============================================================================
-- Agent runs
-- ============================================================================
CREATE TABLE agent_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    node_id UUID NOT NULL REFERENCES execution_nodes ON DELETE CASCADE,
    agent_type TEXT NOT NULL,
    system_prompt_hash TEXT,
    model TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('running', 'completed', 'failed', 'timeout')),
    tokens_input INTEGER,
    tokens_output INTEGER,
    turns INTEGER,
    error TEXT,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ
);

CREATE INDEX idx_agent_runs_node ON agent_runs (node_id);
CREATE INDEX idx_agent_runs_status ON agent_runs (status);

-- ============================================================================
-- Agent outputs
-- ============================================================================
CREATE TABLE agent_outputs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL REFERENCES agent_runs ON DELETE CASCADE,
    output_type TEXT NOT NULL CHECK (output_type IN (
        'research_report', 'prd', 'code', 'test', 'adr', 'review'
    )),
    file_path TEXT,
    content_hash TEXT,
    accepted BOOLEAN,
    guardrail_results JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_agent_outputs_run ON agent_outputs (run_id);

-- ============================================================================
-- Guardrail checks
-- ============================================================================
CREATE TABLE guardrail_checks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    output_id UUID NOT NULL REFERENCES agent_outputs ON DELETE CASCADE,
    rule_name TEXT NOT NULL,
    passed BOOLEAN NOT NULL,
    severity TEXT CHECK (severity IN ('critical', 'high', 'medium', 'low')),
    violation_details JSONB,
    checked_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_guardrail_checks_output ON guardrail_checks (output_id);

-- ============================================================================
-- Event log (audit trail)
-- ============================================================================
CREATE TABLE events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    actor TEXT,
    payload JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_events_project ON events (project_id);
CREATE INDEX idx_events_type ON events (project_id, event_type);
CREATE INDEX idx_events_created ON events (project_id, created_at);

-- ============================================================================
-- Knowledge entries (shared working memory)
-- ============================================================================
CREATE TABLE knowledge_entries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects ON DELETE CASCADE,
    scope TEXT NOT NULL CHECK (scope IN ('project', 'phase', 'graph', 'node')),
    scope_id UUID,
    key TEXT NOT NULL,
    value JSONB NOT NULL,
    contributed_by UUID REFERENCES agent_runs,
    superseded_by UUID REFERENCES knowledge_entries,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_knowledge_project ON knowledge_entries (project_id);
CREATE INDEX idx_knowledge_key ON knowledge_entries (project_id, key);

-- ============================================================================
-- Notify function for event-driven coordination
-- ============================================================================
CREATE OR REPLACE FUNCTION notify_event() RETURNS TRIGGER AS $$
BEGIN
    PERFORM pg_notify('etc_events', json_build_object(
        'id', NEW.id,
        'project_id', NEW.project_id,
        'event_type', NEW.event_type,
        'actor', NEW.actor
    )::text);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER events_notify
    AFTER INSERT ON events
    FOR EACH ROW EXECUTE FUNCTION notify_event();
