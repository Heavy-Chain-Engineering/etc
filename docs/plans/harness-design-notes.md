# Industrial Coding Harness — Design Memory

Reference: `docs/plans/2026-02-25-coding-harness-design.md`

## Core Concept
A synthetic engineering organization — 14 AI agents + engineering standards + mechanical enforcement.
Not "vibe coding" — structured, repeatable, deployable systems.
Designed to be project-agnostic and reusable across any codebase.

## User's Philosophy
- "Slow is smooth, smooth is fast" — guardrails should keep agents on rails without stopping progress
- Human acts as SME + spec author; agents handle expression
- More constraints on agents = fewer ways they'll be incorrectly creative
- The goal: consistently, repeatedly build the right product AND build the product right
- Specification drives everything — declare the system, agents express it into code
- Genotype (spec) → phenotype (running system) via gene expression machinery (agents)

## Architecture Decision: Option B (User-level + Project template)
- User-level (`~/.claude/`): agents, hooks, standards — live, always current, global
- Project-level (`.claude/`, root files): domain standards, CI, pyproject.toml — per-repo
- Improvements to user-level components propagate to ALL projects immediately
- Template repo for project scaffolding (references user-level, doesn't copy)

## Agent Roster (15 agents, full SDLC)

### By Phase
1. Bootstrap: Brownfield Bootstrapper (derives .meta/ from existing code, uses agent teams)
2. Strategy: Product Manager, Product Owner
3. Design: UX Designer, UI Designer
4. Architecture: Architect, Domain Modeler
5. Implementation: Backend Developer, Frontend Developer, DevOps Engineer
6. Quality: Code Reviewer, Verifier, Security Reviewer
7. Evaluation: Process Evaluator
8. Support: Technical Writer

### Key Agent Behaviors
- Socratic but opinionated — ask questions AND make decisions within guardrails
- Phase-activated, not permanent — spin up when needed, stand down when done
- Standards-driven — each agent loads only the standards relevant to its role
- Tool-constrained — read-only agents can't write, spec agents can't edit source

## .meta/ Convention
- Every directory gets `.meta/description.md`
- Ambiguity gradient: top = strategic (PM reads), bottom = precise (developer reads)
- Higher levels summarize lower levels (rollup)
- Spec embedded in source tree (genotype travels with phenotype)
- Agents read .meta/ at their working directory level for instant orientation

## Standards Architecture
- NOT in CLAUDE.md (CLAUDE.md is a concise pointer)
- User-level: `~/.claude/standards/{process,code,testing,architecture,security,quality}/`
- Project-level: `.claude/standards/{domain-constraints,tech-stack,architecture,agent-rules}.md`

## Enforcement Layers
1. CLAUDE.md + agent prompts → enforce process (TDD sequence)
2. PreToolUse hooks → enforce preconditions (test file exists)
3. Stop/TaskCompleted hooks → enforce outcomes (tests pass, coverage 98%)
4. CI pipeline → enforce merge criteria (backstop)

## Testing Requirements
- 98% line + branch coverage (up from 80%)
- Red/green TDD mandatory on every feature
- LLM eval tests as first-class pytest (markers: llm_eval, golden_answer)
- Four tiers: deterministic → retrieval → LLM output → regression
- Retrieval quality tested separately from generation quality
- Token costs are NOT a concern

## Implementation Phases
1. Build user-level platform (~/.claude/)
2. Create project template repo
3. Deploy to first target project
4. Evaluate and improve

## Open Design Questions
1. .meta/ rollup: manual or agent-assisted?
2. Agent team coordination: who creates task breakdowns?
3. Process Evaluator: persistent memory for trend tracking?
4. .meta/ granularity: every directory or only logical modules?
5. Standards format: pure markdown or structured (YAML frontmatter)?
6. Standards conflicts: project overrides user-level?

## Brownfield Bootstrapper (added late in design)
- Spins up agent teams organized by top-level directory
- Each team reads bottom-up: files → module .meta/ → subsystem .meta/
- Creates .meta/description.md at every level with: purpose, components, dependencies, patterns, tech
- After all teams complete, synthesizes root-level .meta/description.md
- Optionally generates gap analysis (missing tests, undocumented APIs, arch concerns)
- Works for greenfield too — creates .meta/ tree after first implementation pass
- This is ISS Phase 0 ("Observe") made concrete

## Formalism Gradient in .meta/ (decision: 2026-02-25)

The ambiguity gradient has two axes, not one:

```
                    Strategic (top)
                         │
    Natural language ────┼──── Formal schema
                         │
                    Tactical (leaf)
```

- Top-level .meta/: natural language only (description.md). Strategic, intentionally ambiguous.
- Leaf-level .meta/: natural language + machine-validatable schema. Precise, enforceable.

### Formalism choice: Pydantic → JSON Schema
- Pydantic models are source of truth (already in the stack for domain objects and API contracts)
- Generated JSON Schema stored in .meta/ at leaf nodes (Pydantic does this natively)
- Schemas visible to agents and hooks, not just Python runtime
- Verifier agent validates against both: natural language intent AND formal constraints

### Why not SHACL (yet)
- SHACL offers inference rules, conditional constraints, semantic validation
- But: heavy dependency, unfamiliar tooling, overkill until proven otherwise
- Upgrade path: if we hit the wall where JSON Schema can't express needed constraints (inference rules, conditional cardinality), migrate leaf schemas to SHACL then
- YAGNI until proven otherwise

### Inspiration
- Kurt Cagle's SHACL article: compact structural blueprints loaded into context, not full knowledge graphs
- Dave (Panoptic Systems): layered enforcement where "an agent has to fail at every single layer to ship a violation"
- Convergence: governance structure (ETC) + formal constraints (SHACL) + verification (Panoptic) are three facets of the same unsolved problem

## Declarative Reconciliation Vision (future, not built now)
- .meta/ = derived state (what IS), PRDs = declared state (what SHOULD BE)
- Delta between them = work units for agents
- Enables: tech stack swaps, architecture migrations, framework upgrades, feature removal
- All driven by changing the spec, not changing the code directly
- The harness infrastructure (.meta/ + PRDs + agents + verification) is the prerequisite
- Example: change PRD from "Python/FastAPI" to "Java/Spring Boot" → agents rewrite subsystem

## ISS Connection
This harness is the first practical instantiation of Jason's Industrialized System Synthesis vision.
- Jason's prior work: "Nature's Code", "Evolution as Product Management", "Tyranny of State Space", "domain.md" blog post
- Collaborator: Jim Snyder (Chief Architect, CS Disco)
- Key academic influences: Piantadosi (ambiguity in communication), Star & Griesemer (boundary objects), Lazebnik (biology needs formalism)
- ISS doc shared in conversation — saved context about notation problem, ambiguity gradient, federated spec topology, brownfield adoption path
