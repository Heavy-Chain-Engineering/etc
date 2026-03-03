# ETC Orchestration Platform — How It Works

A durable, event-driven system that deploys AI agent teams through a full SDLC — with persistence, guardrail enforcement, and recursive decomposition.

> "A spec is only a wish if there's no way to enforce it."

## Architectural Constraints

| ID | Constraint | Implementation |
|----|-----------|----------------|
| C1 | Single SEM orchestrator — delegates everything | `orchestrator.py`: SEM never writes code, only makes decisions |
| C2 | SEM context is sacred — stateless between decisions | Each decision cycle loads fresh state from Postgres |
| C3 | Restart from wherever we left off — all state in Postgres | No in-memory state, no file-based state, no Redis |
| C4 | Arbitrary recursive decomposition — tree-based execution graphs | `graph_engine.py`: nodes with parent_node_id + dependencies |

## System Architecture

```
                          ┌──────────────┐
                          │    Human     │
                          │  Operator    │
                          └──────┬───────┘
                                 │ "Start project" / "Approve phase gate"
                                 v
┌─────────────────────────────────────────────────────────────────────────┐
│                             CLI (cli.py)                                │
│  Typer + Rich — project init, phase status, material intake,           │
│  knowledge queries, topology design, metrics dashboard                 │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
                               v
┌─────────────────────────────────────────────────────────────────────────┐
│                    SEM ORCHESTRATOR (orchestrator.py)                   │
│                                                                         │
│  Stateless decision loop (C2):                                         │
│                                                                         │
│    ┌──────────┐    ┌──────────────┐    ┌───────────┐    ┌──────────┐  │
│    │ 1. LISTEN │───>│ 2. LOAD STATE│───>│ 3. DECIDE │───>│4. EXECUTE│  │
│    │  (event)  │    │ (from Postgres)│  │ (PydanticAI)│  │(write DB)│  │
│    └──────────┘    └──────────────┘    └───────────┘    └────┬─────┘  │
│         ^                                                      │       │
│         └──────────────────────────────────────────────────────┘       │
│                         (back to step 1 — fresh context)               │
│                                                                         │
│  Decisions:  DEPLOY_AGENT | ADVANCE_PHASE | CHECK_DOD | WAIT          │
│              REQUEST_HUMAN_INPUT | MARK_NODE_READY | RETRY_FAILED_NODE │
│              DESIGN_TOPOLOGY                                           │
└────────────────────────┬────────────────────────────────────────────────┘
                         │
            ┌────────────┼────────────────┐
            v            v                v
  ┌─────────────┐ ┌──────────────┐ ┌──────────────┐
  │ PHASE ENGINE│ │ GRAPH ENGINE │ │AGENT RUNTIME │
  │ (phases.py) │ │(graph_engine)│ │(agent_runtime)│
  └─────────────┘ └──────────────┘ └──────────────┘
```

## The Three Engines

### Phase Engine (`phases.py`)

SDLC state machine with 8 gated phases:

```
Bootstrap -> Spec -> Design -> Decompose -> Build -> Verify -> Ship -> Evaluate
```

Each phase has Definition of Done items stored as JSONB. Check types: `automatic`, `agent_verified`, `human_confirmed`, `guardrail_verified`. Transitions are gated — `PhaseEngine.advance_phase()` raises `ValueError` if DoD is not 100% passed.

### Graph Engine (`graph_engine.py`)

Execution graphs with fan-out/reduce patterns (C4):

```
        ┌──────────────────────────────┐
        │    Execution Graph            │
        │    (per phase)                │
        └──────────────┬───────────────┘
                       │
          ┌────────────┼────────────┐
          v            v            v
     ┌─────────┐ ┌─────────┐ ┌─────────┐   depth 0 (fan-out)
     │  Leaf   │ │  Leaf   │ │  Leaf   │   parallel agents
     │  Node   │ │  Node   │ │  Node   │
     └────┬────┘ └────┬────┘ └────┬────┘
          │           │           │
          └───────────┼───────────┘
                      v
                ┌───────────┐   depth 1 (reduce)
                │  Reduce   │   waits for all leaves
                │   Node    │
                └───────────┘
```

Node statuses: `pending -> ready -> running -> completed | failed | retrying`

Scheduling: nodes become ready when all dependencies are completed. Nodes can have `parent_node_id` for recursive decomposition (trees within trees).

### Agent Runtime (`agent_runtime.py`)

Lifecycle for each agent execution:

1. Load agent `.md` prompt file from `~/.claude/agents/{type}.md`
2. Build domain context (project classification, source materials, anti-pattern catalog)
3. Inject context into prompt automatically
4. Create PydanticAI `Agent[AgentDeps, AgentResult]` with tools
5. Register tools: `read_file`, `write_file`, `search_files`, `query_knowledge`, `contribute_knowledge`
6. Run `agent.run_sync()` -> structured `AgentResult`
7. Record in `agent_runs` + `agent_outputs` tables
8. Emit `AGENT_COMPLETED` event

## Guardrail Pipeline

Runs on **every agent output** before acceptance. Critical failures mechanically reject the output — no agent can bypass this.

```
Agent Output
     │
     v
┌─────────────────────────────────────────────────────────┐
│ GuardrailMiddleware.check_and_record()                   │
│                                                           │
│  1. AntiPatternScan      CRITICAL   regex: boolean flags, │
│     (prd, research only)             hardcoded enums,     │
│                                      legacy mappings      │
│                                                           │
│  2. OutputSchemaValidation  HIGH     required sections    │
│     (all types)                      per output type      │
│                                                           │
│  3. SpecCompliance        CRITICAL   LLM-based: compares  │
│     (when context has                output vs PRD        │
│      prd + criteria)                 acceptance criteria.  │
│                                      Adversarial — finds  │
│                                      violations, doesn't  │
│                                      confirm compliance.  │
│                                                           │
│  Also available (not in defaults):                        │
│  4. DomainFidelity        CRITICAL   LLM vs domain axioms │
│  5. CoverageGate          HIGH       pytest coverage >= N% │
│  6. TDDVerification       MEDIUM     tests exist with impl │
│  7. SecurityScan          HIGH       SQL injection, XSS,  │
│                                      hardcoded secrets     │
└──────────────────────────────┬────────────────────────────┘
                               │
             ┌─────────────────┼──────────────────┐
             v                                     v
    Any CRITICAL failure?                    All passed?
             │                                     │
             v                                     v
    Output REJECTED                       Output ACCEPTED
    accepted = false                      accepted = true
    GUARDRAIL_VIOLATION event
             │
             v
    SEM sees event -> RETRY_FAILED_NODE
```

### The Retry Loop

When guardrails reject an output:

1. `GUARDRAIL_VIOLATION` event emitted
2. SEM receives event, decides `RETRY_FAILED_NODE`
3. `retry.py` increments `retry_count`, builds augmented context with violation details
4. Same agent re-executes with feedback: "PREVIOUS ATTEMPT FAILED: {violation details}"
5. Guardrail middleware runs again (loop until pass or `max_retries` exhausted)

## Event-Driven Coordination

All coordination uses Postgres `LISTEN/NOTIFY`. Events are inserted into the `events` table; a trigger fires `pg_notify('etc_events', payload)` automatically.

| Event | Meaning |
|-------|---------|
| `AGENT_STARTED` | SEM deployed an agent to a node |
| `AGENT_COMPLETED` | Agent finished, output recorded |
| `PHASE_GATE_REACHED` | DoD evaluated or phase transition |
| `GUARDRAIL_VIOLATION` | Critical guardrail failure |
| `HUMAN_RESPONSE` | SEM needs human input |
| `KNOWLEDGE_UPDATED` | Knowledge entry contributed |
| `NODE_READY` | Node dependencies satisfied |
| `SEM_DECISION` | Every SEM decision (audit trail) |

## Data Model

```
projects
  +-- source_materials        (intake: PDFs, code, exports)
  +-- phases                  (8 SDLC phases with DoD items)
  |   +-- phase_transitions   (audit trail of phase advances)
  +-- execution_graphs        (one per phase, fan-out/reduce)
  |   +-- execution_nodes     (leaf/composite/reduce, with dependencies)
  |       +-- agent_runs      (one agent execution per node attempt)
  |           +-- agent_outputs   (structured output, accepted flag)
  |               +-- guardrail_checks  (per-rule pass/fail + details)
  +-- knowledge_entries       (shared working memory, scoped + versioned)
  +-- events                  (audit trail, triggers NOTIFY)
```

All tables use UUID primary keys. All timestamps are `TIMESTAMPTZ`. Schema lives in `sql/001_initial_schema.sql`.

## Agent Roster

23 agent definitions in `agents/`:

| Category | Agents |
|----------|--------|
| Orchestration | sem |
| Spec / Design | product-manager, product-owner, researcher, architect, ux-designer, ui-designer, domain-modeler |
| Build | backend-developer, frontend-developer, frontend-dashboard-refactorer, devops-engineer, code-simplifier, project-bootstrapper |
| Quality Gates | verifier, code-reviewer, security-reviewer, architect-reviewer, spec-enforcer |
| Analysis | gemini-analyzer, multi-tenant-auditor, process-evaluator, technical-writer |

### Quality Gate Taxonomy

Each quality agent answers a different question:

| Agent | Question |
|-------|----------|
| **spec-enforcer** | Does this match the PRD? |
| **domain-modeler** | Does it speak the domain? |
| **architect-reviewer** | Is the structure sound? |
| **code-reviewer** | Is the code good? |
| **security-reviewer** | Is it safe? |
| **verifier** | Do tests pass? |

## Supporting Modules

| Module | Purpose |
|--------|---------|
| `config.py` | TOML config loading (`~/.etc/config.toml` + local `etc.toml`) |
| `db.py` | psycopg3 connection pool (2-10 connections, dict_row) |
| `metrics.py` | Read-only aggregate queries: tokens, velocity, phase durations, guardrail stats |
| `topology.py` | LLM-based topology design: source materials -> TopologyPlan -> execution graph |
| `intake.py` | Source material CRUD + triage (PDF, code, exports -> classified + prioritized) |
| `knowledge.py` | Shared working memory: scoped (project/phase/graph/node), versioned, conflict detection |
| `retry.py` | Exponential backoff retry with violation context injection |

## Tech Stack

- **Language:** Python 3.11+
- **Agent Framework:** PydanticAI (model-agnostic, dependency injection, structured output)
- **Database:** PostgreSQL via psycopg3 (no ORM)
- **CLI:** Typer + Rich
- **Models:** Completely swappable — configured in `etc.toml`, never hardcoded
- **Testing:** pytest (66+ tests across 23 test files)
