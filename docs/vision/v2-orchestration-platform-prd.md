# ETC Orchestration Platform — v2 PRD

**Date:** 2026-02-27
**Status:** Draft
**Author:** Jason Vertrees + Claude
**Input:** `docs/lessons-learned-v1.md`, v1 harness agent library, VenLink field testing

---

## 1. Vision

Replace Claude Code's conversation-based orchestration with a purpose-built platform that runs a synthetic AI engineering team at arbitrary scale. The platform preserves v1's validated intelligence layer (23 agent prompts, 8-phase SDLC, domain fidelity standards) while replacing its orchestration substrate with durable state, event-driven coordination, and enforced guardrails.

**One sentence:** A durable, event-driven orchestration platform that deploys AI agent teams through a full SDLC — with persistence, guardrail enforcement, and recursive decomposition — where "a spec is only a wish if there's no way to enforce it."

---

## 2. Problem Statement

The v1 harness (Claude Code + agent prompts) validated that structured agent teams can execute an SDLC. But Claude Code's architecture imposes fundamental limits:

| Limit | Impact | v2 Requirement |
|-------|--------|---------------|
| No persistent state | SEM forgets decisions across sessions | Durable execution state in Postgres |
| No event-driven coordination | Can't trigger "Layer 2 when Layer 1 completes" | Event bus with LISTEN/NOTIFY |
| No mid-execution guardrails | Anti-pattern rules are advisory, not enforced | Middleware checks on every agent output |
| No shared working memory | Agents can't see each other's progress | Queryable shared state |
| No cross-session continuity | Closing laptop kills orchestration | Persistent state survives any boundary |
| Fan-out ceiling (~15 agents) | Can't scale to VenLink complexity | Managed agent lifecycle with backpressure |
| Manual research plan creation | Human writes multi-layer topologies | First-class recursive decomposition engine |

---

## 3. What We Are Building

### Core Platform
A Python-based orchestration engine that:
- Manages projects through an 8-phase SDLC lifecycle
- Deploys AI agents via the Claude API (Messages API with tool use)
- Persists all state in Postgres
- Enforces guardrails as middleware (not as agent instructions)
- Supports recursive multi-layer agent topologies
- Provides a CLI for human interaction (MVP), Web UI (later)

### What We Are NOT Building
- A general-purpose AI agent framework (this is SDLC-specific)
- A replacement for Claude Code's IDE features (editing, terminal, file management)
- A hosting platform for other people's agents (internal tooling first)
- A new AI model or fine-tune (we use Claude via API as-is)

---

## 4. Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Human Interface Layer                      │
│  CLI (MVP) │ Web UI (future) │ Webhooks (future)            │
└──────────────────────┬──────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────┐
│                   Orchestrator Engine                         │
│                                                              │
│  ┌──────────────┐  ┌───────────────┐  ┌──────────────────┐  │
│  │ Phase Engine  │  │ Topology      │  │ Guardrail        │  │
│  │ - state       │  │ Builder       │  │ Middleware        │  │
│  │   machine     │  │ - recursive   │  │ - anti-pattern   │  │
│  │ - DoD gates   │  │   decomp      │  │   scanning       │  │
│  │ - project     │  │ - layer       │  │ - domain fidelity│  │
│  │   intake      │  │   management  │  │ - coverage gates │  │
│  │              │   │ - fan-out/    │  │ - output schema  │  │
│  │              │   │   reduce      │  │   validation     │  │
│  └──────┬──────┘  └──────┬────────┘  └────────┬─────────┘  │
│         │                │                     │             │
│  ┌──────▼────────────────▼─────────────────────▼──────────┐ │
│  │                   Event Loop                            │ │
│  │  Postgres LISTEN/NOTIFY                                 │ │
│  │  Events: agent_completed, layer_completed,              │ │
│  │          phase_gate_reached, guardrail_violation,       │ │
│  │          human_response_received                        │ │
│  └──────────────────────┬──────────────────────────────────┘ │
└─────────────────────────┼────────────────────────────────────┘
                          │
          ┌───────────────┼───────────────┐
          │               │               │
   ┌──────▼──────┐ ┌─────▼──────┐ ┌──────▼──────┐
   │  Postgres   │ │ Claude API │ │ Filesystem   │
   │  (state +   │ │  (agent    │ │ (artifacts)  │
   │   events)   │ │   brains)  │ │              │
   └─────────────┘ └────────────┘ └──────────────┘
```

### Key Design Decisions

**Postgres as single backend (MVP).** State, events, and signaling all in Postgres. No Redis, no message queue, no additional infrastructure. Postgres LISTEN/NOTIFY handles agent coordination. Advisory locks handle concurrency. JSONB handles flexible agent outputs. Add Redis Streams only if LISTEN/NOTIFY becomes a bottleneck at scale.

**Claude API direct (not Agent SDK).** Maximum control over agent lifecycle, tool use, and system prompts. The Agent SDK can be evaluated later if it adds value. The v1 agent .md files become system prompts with minimal transformation.

**Filesystem for artifacts.** Research reports, PRDs, code, tests — all written to the project directory as files, same as v1. Postgres tracks metadata (what was written, by whom, when, guardrail results). The files ARE the deliverables.

**CLI-first.** The orchestrator is a Python process controlled via CLI. `etc init`, `etc status`, `etc run`, `etc approve`. Web UI is a future layer on top of the same Postgres state.

---

## 5. Data Model

### Core Tables

```sql
-- Projects
projects (
  id UUID PRIMARY KEY,
  name TEXT NOT NULL,
  root_path TEXT NOT NULL,           -- filesystem path to project
  classification TEXT NOT NULL,       -- greenfield|brownfield|re-engineering|lift-and-shift|consolidation
  status TEXT NOT NULL DEFAULT 'active',
  config JSONB,                       -- project-specific settings
  created_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ
)

-- Source material triage (from project intake)
source_materials (
  id UUID PRIMARY KEY,
  project_id UUID REFERENCES projects,
  name TEXT NOT NULL,
  type TEXT NOT NULL,                 -- pdf|code|export|spreadsheet|document
  classification TEXT NOT NULL,       -- business_operations|requirements|implementation_artifact|domain_truth
  priority TEXT NOT NULL,             -- primary|high|medium|context_only
  path TEXT,                          -- filesystem path
  reading_instructions TEXT,          -- how agents should interpret this source
  created_at TIMESTAMPTZ
)

-- SDLC phase lifecycle
phases (
  id UUID PRIMARY KEY,
  project_id UUID REFERENCES projects,
  name TEXT NOT NULL,                 -- Bootstrap|Spec|Design|Decompose|Build|Verify|Ship|Evaluate
  status TEXT NOT NULL DEFAULT 'pending',  -- pending|active|completed|skipped
  dod_items JSONB NOT NULL,           -- [{text, checked, checked_at, checked_by}]
  entered_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ
)

phase_transitions (
  id UUID PRIMARY KEY,
  project_id UUID REFERENCES projects,
  from_phase TEXT NOT NULL,
  to_phase TEXT NOT NULL,
  reason TEXT,
  approved_by TEXT,                   -- human|auto
  transitioned_at TIMESTAMPTZ
)

-- Execution graphs (recursive decomposition)
execution_graphs (
  id UUID PRIMARY KEY,
  project_id UUID REFERENCES projects,
  phase_id UUID REFERENCES phases,
  name TEXT NOT NULL,                 -- e.g., "research-fanout-round-3"
  topology JSONB,                     -- full topology description
  status TEXT NOT NULL DEFAULT 'pending',  -- pending|running|completed|failed
  created_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ
)

execution_layers (
  id UUID PRIMARY KEY,
  graph_id UUID REFERENCES execution_graphs,
  layer_number INTEGER NOT NULL,
  name TEXT,                          -- e.g., "Domain Research", "CX Workflow Analysis"
  status TEXT NOT NULL DEFAULT 'pending',
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ
)

execution_nodes (
  id UUID PRIMARY KEY,
  layer_id UUID REFERENCES execution_layers,
  agent_type TEXT NOT NULL,           -- researcher|architect|backend-developer|etc
  assignment JSONB NOT NULL,          -- scoped task description, source files, output path
  status TEXT NOT NULL DEFAULT 'pending',  -- pending|running|completed|failed|retrying
  output_path TEXT,                   -- where the agent wrote its results
  max_retries INTEGER DEFAULT 1,
  retry_count INTEGER DEFAULT 0,
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ
)

-- Node dependencies (within and across layers)
execution_node_dependencies (
  node_id UUID REFERENCES execution_nodes,
  depends_on_node_id UUID REFERENCES execution_nodes,
  PRIMARY KEY (node_id, depends_on_node_id)
)

-- Agent runs (each attempt to execute a node)
agent_runs (
  id UUID PRIMARY KEY,
  node_id UUID REFERENCES execution_nodes,
  agent_type TEXT NOT NULL,
  system_prompt_hash TEXT,            -- hash of the system prompt used
  model TEXT NOT NULL DEFAULT 'claude-opus-4-6',
  status TEXT NOT NULL,               -- running|completed|failed|timeout
  tokens_input INTEGER,
  tokens_output INTEGER,
  turns INTEGER,
  error TEXT,
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ
)

-- Agent outputs (what agents produce)
agent_outputs (
  id UUID PRIMARY KEY,
  run_id UUID REFERENCES agent_runs,
  output_type TEXT NOT NULL,          -- research_report|prd|code|test|adr|review
  file_path TEXT,                     -- where on filesystem
  content_hash TEXT,                  -- hash of file content
  accepted BOOLEAN,                   -- null until guardrails run
  guardrail_results JSONB,            -- [{rule, passed, details}]
  created_at TIMESTAMPTZ
)

-- Guardrail checks
guardrail_checks (
  id UUID PRIMARY KEY,
  output_id UUID REFERENCES agent_outputs,
  rule_name TEXT NOT NULL,            -- anti_pattern_scan|domain_fidelity|coverage_gate|schema_validation
  passed BOOLEAN NOT NULL,
  severity TEXT,                      -- critical|high|medium|low
  violation_details JSONB,
  checked_at TIMESTAMPTZ
)

-- Event log (audit trail)
events (
  id UUID PRIMARY KEY,
  project_id UUID REFERENCES projects,
  event_type TEXT NOT NULL,           -- agent_started|agent_completed|phase_gate_reached|guardrail_violation|human_decision
  actor TEXT,                         -- agent_id|human|system
  payload JSONB,
  created_at TIMESTAMPTZ DEFAULT NOW()
)

-- Domain knowledge (shared working memory)
knowledge_entries (
  id UUID PRIMARY KEY,
  project_id UUID REFERENCES projects,
  scope TEXT NOT NULL,                -- project|phase|graph|node
  scope_id UUID,                      -- references the scoped entity
  key TEXT NOT NULL,                  -- e.g., "entity:VendorType", "decision:compliance-status-computed"
  value JSONB NOT NULL,
  contributed_by UUID REFERENCES agent_runs,
  superseded_by UUID REFERENCES knowledge_entries,
  created_at TIMESTAMPTZ
)
```

### Key Relationships

```
project
  ├── source_materials[]
  ├── phases[]
  │     └── execution_graphs[]
  │           └── execution_layers[] (ordered)
  │                 └── execution_nodes[]
  │                       ├── dependencies[]
  │                       └── agent_runs[]
  │                             └── agent_outputs[]
  │                                   └── guardrail_checks[]
  ├── knowledge_entries[]
  └── events[]
```

---

## 6. Core Components

### 6.1 Phase Engine

The SDLC state machine. Manages phase lifecycle exactly as the v1 SEM does, but with durable state.

**Responsibilities:**
- Track current phase per project
- Evaluate DoD criteria (programmatic checks + human confirmations)
- Gate transitions — refuse to advance until all DoD items are met
- Record transition history with rationale

**DoD evaluation types:**
- **Automatic:** "All tests passing" → run `pytest`, check exit code
- **Agent-verified:** "Code reviewed" → check that a code-reviewer agent_run exists with status=completed for all outputs
- **Human-confirmed:** "Stakeholder reviewed PRD" → requires explicit human approval via CLI

### 6.2 Topology Builder

The recursive decomposition engine. Takes a project classification, source material inventory, and scope assessment, then produces an execution graph.

**Responsibilities:**
- Assess scope (source file count, domain count, analysis dimensions)
- Select deployment pattern (single agent → recursive decomposition)
- Build execution graph with layers, nodes, and dependencies
- Generate agent assignments (scoped briefs with source material, output paths, anti-pattern guards)
- Present topology to human for approval before execution

**The key innovation:** This component does what the human did manually for VenLink Round 3 — it reads the source material inventory, classifies it by dimension, determines how many agents and layers are needed, and produces a research plan. For MVP, this can be a Claude API call itself (an "orchestrator agent" that produces the topology). Long-term, it could be rule-based.

### 6.3 Agent Runtime

Manages the lifecycle of individual agent executions.

**Responsibilities:**
- Convert agent `.md` files into Claude API system prompts
- Deploy agents as Claude API calls (Messages API with tool use)
- Provide agents with filesystem access (read/write to project directory)
- Inject mandatory context (domain briefing, research plan, anti-pattern catalog)
- Collect agent outputs (files written, structured results)
- Handle timeouts, errors, and retries
- Track token usage and turn counts

**Agent tool use:** Agents interact with the filesystem via Claude API tool use. The platform provides tools:
- `read_file(path)` — read a file
- `write_file(path, content)` — write a file (output goes through guardrails)
- `search_files(pattern)` — glob/grep
- `run_command(cmd)` — execute shell commands (sandboxed)
- `query_knowledge(key)` — read from shared knowledge graph
- `contribute_knowledge(key, value)` — write to shared knowledge graph

### 6.4 Guardrail Middleware

Automated enforcement layer that checks every agent output before acceptance.

**Responsibilities:**
- Run configured guardrail rules on every `agent_output`
- Mark outputs as accepted/rejected based on rule results
- Notify orchestrator of violations (which can trigger re-spawn, human review, or blocking)
- Rules are composable and project-configurable

**Built-in guardrail rules (from v1 standards):**

| Rule | What It Checks | Severity |
|------|---------------|----------|
| `anti_pattern_scan` | For re-engineering projects: scans for boolean flag sets, hardcoded enums, 1:1 legacy mappings in research reports/PRDs | Critical |
| `domain_fidelity_check` | Verifies agent output doesn't contradict domain briefing axioms | Critical |
| `output_schema_validation` | Research reports have all required sections (entity map, relationships, etc.) | High |
| `coverage_gate` | Test coverage meets project threshold | High |
| `security_scan` | Basic OWASP checks on generated code | High |
| `tdd_verification` | Tests exist and were written before implementation (check git history) | Medium |

**Guardrail execution model:**
```
Agent writes file → output recorded → guardrails run →
  IF all pass → output accepted, node marked complete
  IF critical fails → output rejected, agent re-spawned with violation details
  IF high fails → output flagged, human notified, execution paused
```

### 6.5 Event Loop

Central coordination via Postgres LISTEN/NOTIFY.

**Event types:**
- `agent_completed` — an agent run finished (success or failure)
- `layer_completed` — all nodes in a layer are done
- `phase_gate_reached` — a phase's DoD may be met
- `guardrail_violation` — a critical guardrail failed
- `human_response` — human provided input via CLI
- `knowledge_updated` — shared knowledge graph changed

**Event handlers:**
- `agent_completed` → check if all nodes in layer are complete → if yes, emit `layer_completed`
- `layer_completed` → start next layer in execution graph → if last layer, start reduce/synthesis
- `phase_gate_reached` → evaluate DoD → if met, notify human for transition approval
- `guardrail_violation` → depending on severity: re-spawn agent, pause execution, notify human
- `human_response` → unblock waiting phase gate or agent decision

### 6.6 Knowledge Graph

Shared working memory that agents can read from and write to during execution.

**Design:**
- Key-value store in Postgres (the `knowledge_entries` table)
- Scoped: project-level, phase-level, graph-level, or node-level
- Agents read via `query_knowledge` tool, write via `contribute_knowledge` tool
- Entries are versioned (superseded_by chain)
- The synthesis agent can query ALL knowledge entries from Layer 1 agents to resolve conflicts

**Example entries:**
```json
{"key": "entity:VendorType", "value": {"fields": [...], "relationships": [...], "contributed_by": "R03"}}
{"key": "decision:compliance-status-computed", "value": {"rationale": "...", "contributed_by": "R04"}}
{"key": "conflict:insurance-type-modeling", "value": {"R03_says": "...", "R08_says": "...", "resolved": false}}
```

---

## 7. CLI Interface (MVP)

```bash
# Project management
etc init <name> --type re-engineering    # Create project, run intake interview
etc status                               # Show current phase, DoD progress, active agents
etc projects                             # List all projects

# Phase management
etc phase approve                        # Approve phase transition
etc phase reject "reason"                # Reject with feedback
etc dod check <index>                    # Manually check a DoD item
etc dod status                           # Show DoD checklist

# Execution
etc run                                  # Run next action (deploy agents, check gates, etc.)
etc run --auto                           # Autonomous mode: run until phase gate or blocker
etc run --phase spec                     # Run a specific phase

# Agent management
etc agents                               # Show running/completed/failed agents
etc agent <id> logs                      # Show agent conversation log
etc agent <id> output                    # Show agent output files
etc agent <id> retry                     # Re-run a failed agent

# Research
etc research plan                        # Generate/view research plan
etc research plan --approve              # Approve research plan
etc research status                      # Show research progress by layer

# Guardrails
etc guardrails status                    # Show guardrail results for current phase
etc guardrails override <id> "reason"    # Override a guardrail violation (with justification)

# Knowledge
etc knowledge list                       # Show shared knowledge entries
etc knowledge conflicts                  # Show unresolved conflicts between agents

# History
etc history                              # Full event log
etc history --phase build                # Events for a specific phase
etc metrics                              # Token usage, agent counts, velocity
```

---

## 8. Agent Prompt Migration

v1 agent `.md` files map to v2 system prompts with minimal transformation:

```python
# v1: agents/researcher.md (Claude Code agent)
# v2: loaded as system prompt for Claude API call

def load_agent_prompt(agent_type: str, project: Project) -> str:
    """Load agent .md, strip frontmatter, inject project context."""
    raw = read_file(f"agents/{agent_type}.md")
    prompt = strip_frontmatter(raw)

    # Inject project-scoped context
    if project.domain_briefing_path:
        briefing = read_file(project.domain_briefing_path)
        prompt = f"MANDATORY CONTEXT:\n{briefing}\n\n{prompt}"

    if project.research_plan_path:
        plan = read_file(project.research_plan_path)
        prompt = f"RESEARCH PLAN:\n{plan}\n\n{prompt}"

    if project.classification == "re-engineering" and project.anti_pattern_catalog:
        prompt = f"ANTI-PATTERN CATALOG:\n{project.anti_pattern_catalog}\n\n{prompt}"

    return prompt
```

**What changes:** Context injection is now done by the platform (guaranteed), not by agent self-discipline (hoped for).

**What stays:** The prompt content itself. The researcher's heuristics, the PM's checklist, the architect's ADR format — all reusable.

---

## 9. MVP Scope (v2.0)

### Must Have (P0)
1. **Project initialization** with classification and source material triage
2. **Postgres state management** — projects, phases, execution graphs, agent runs, outputs
3. **Phase Engine** — state machine with DoD evaluation and gated transitions
4. **Single-layer fan-out/reduce** — deploy N agents in parallel, synthesize results
5. **Agent runtime** — deploy agents via Claude API with tool use, collect outputs
6. **Basic guardrails** — anti-pattern scan and output schema validation
7. **CLI** — `etc init`, `etc status`, `etc run`, `etc phase approve`, `etc agents`
8. **Event-driven coordination** — LISTEN/NOTIFY for agent completion and layer transitions
9. **Agent prompt loading** from `.md` files with context injection

### Should Have (P1)
10. **Recursive decomposition** — multi-layer topologies with automatic layer management
11. **Knowledge graph** — shared working memory with conflict detection
12. **Full guardrail suite** — domain fidelity, coverage gates, security scan, TDD verification
13. **Autonomous mode** — `etc run --auto` loops until phase gate or blocker
14. **Research plan generation** — orchestrator agent that assesses scope and produces topology
15. **Agent retry with context** — failed agents re-spawned with violation details

### Nice to Have (P2)
16. **Web UI** — dashboard showing project state, agent status, guardrail results
17. **Webhook integrations** — notify Slack/email on phase gates and critical violations
18. **Multi-project management** — switch between projects, share domain briefings
19. **Token usage analytics** — cost tracking per project, per phase, per agent
20. **Topology templates** — save and reuse execution graph patterns

### Future (v2.x)
21. **Multi-tenant** — multiple users/orgs, RLS, billing
22. **Agent marketplace** — community-contributed agent prompts
23. **Custom guardrail rules** — user-defined rules in Python
24. **CI/CD integration** — trigger builds from platform, report results back
25. **Model flexibility** — swap Claude for other LLMs per agent (cost optimization)

---

## 10. Success Criteria

### The VenLink Test
The platform passes its acceptance test when it can execute the VenLink Round 3 research plan autonomously:
- Human does project intake (classification, source material triage)
- Platform generates the 3-layer research topology (or human provides it)
- Platform deploys Layer 1 (10 domain researchers) in parallel
- Guardrails check each output for anti-patterns before acceptance
- Platform waits for Layer 1 completion, then deploys Layer 2 (4 CX agents)
- Platform waits for Layer 2, then deploys synthesis agent
- Human reviews synthesis output at the phase gate
- All of this persists across sessions — human can close laptop, reopen tomorrow, `etc status` shows exactly where things stand

### Quantitative Targets
- Support 20+ concurrent agents per project
- Agent deployment latency < 5 seconds
- Phase state queryable < 100ms
- Full project state recoverable from Postgres alone (no conversation dependency)
- Zero guardrail bypasses — every output checked before acceptance

---

## 11. Technical Risks

| Risk | Mitigation |
|------|-----------|
| Claude API rate limits at 20+ concurrent agents | Implement backpressure — queue agent deployments, respect rate limits |
| Agent tool use for filesystem access is slow | Batch file reads, cache frequently-read context docs |
| Guardrail false positives block valid work | Override mechanism with human justification (`etc guardrails override`) |
| Postgres LISTEN/NOTIFY drops events under load | Event table as backup — poll on startup to catch missed events |
| Agent outputs too large for JSONB | Store content on filesystem, metadata + hash in Postgres |
| Research plan generation quality varies | Human approval gate before execution; improve prompt iteratively |
| Context window limits for synthesis agents with 14+ inputs | Two-stage reduce (sub-synthesis per layer → final synthesis) |

---

## 12. Non-Functional Requirements

- **Persistence:** All state in Postgres. `docker-compose down && docker-compose up` loses nothing.
- **Observability:** Every agent run logged with tokens, turns, duration. Every guardrail check recorded.
- **Idempotency:** Re-running `etc run` after a crash resumes from last known state, doesn't duplicate work.
- **Configuration:** Project-level config in `etc.toml` (or similar). Global config in `~/.etc/config.toml`.
- **Testing:** Platform itself built with TDD. 95% coverage. Integration tests with real Postgres (testcontainers).
- **Dependencies:** Minimal. Python 3.11+, Postgres 15+, anthropic SDK, psycopg3, click (CLI). No heavy frameworks.

---

## 13. Relationship to v1

The v1 harness IS the domain model for v2. Specifically:

| v1 Artifact | v2 Role |
|-------------|---------|
| Agent `.md` files | System prompt library (loaded by Agent Runtime) |
| `standards/process/*.md` | Guardrail rule definitions (enforced by Middleware) |
| `.sdlc/dod-templates.json` | Phase gate criteria (enforced by Phase Engine) |
| `tracker.py` state machine | Phase Engine in Python (backed by Postgres) |
| SEM orchestration logic | Orchestrator Engine decision logic |
| Domain fidelity standard | `domain_fidelity_check` guardrail rule |
| Project classification types | `projects.classification` column + behavior switch |
| Recursive decomposition pattern | Topology Builder with execution_layers |
| Research plan format | Input to Topology Builder |
| Fan-out briefing template | Agent assignment generator |

v1 doesn't get deprecated — it continues to work for simple projects in Claude Code. v2 is for projects that exceed Claude Code's orchestration capacity.
