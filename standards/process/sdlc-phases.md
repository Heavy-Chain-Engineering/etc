# SDLC Phases and Agent Activation

## Status: REFERENCE
## Applies to: All agents

## Phase Definitions

### Bootstrap Phase
**Purpose:** Derive system understanding from existing code (brownfield) or establish initial structure (greenfield).
**Active agents:** Brownfield Bootstrapper
**Output:** Complete `.meta/` description tree, gap analysis

### Spec Phase
**Purpose:** Translate business intent into structured specifications.
**Tool:** spec-kit (`/specify` command)
**Active agents:** Product Manager, Product Owner, Domain Modeler
**Process:**
1. PM initiates `/specify` to drive structured requirements gathering loop
2. Iterative refinement with stakeholder until spec is complete and unambiguous
3. Domain Modeler validates domain concepts and relationships
4. PO confirms acceptance criteria and prioritization
**Output:** Hierarchical PRDs, acceptance criteria, domain model validation

### Design Phase
**Purpose:** Create system architecture and interaction designs.
**Active agents:** Architect, UX Designer, UI Designer
**Output:** ADRs, system boundaries, interaction flows, component designs

### Decompose Phase
**Purpose:** Break PRDs and design artifacts into executable task graphs.
**Tool:** TaskMaster (MCP server)
**Active agents:** Product Manager (task decomposition), Architect (technical refinement)
**Process:**
1. PM feeds PRD into TaskMaster to generate initial task breakdown
2. Architect reviews and refines tasks with dependency mapping and technical detail
3. Tasks are ordered by dependency, each with acceptance criteria and test strategy
**Output:** Ordered task graph with dependencies, acceptance criteria, and implementation guidance

### Build Phase
**Purpose:** Implement features using red/green TDD.
**Active agents:** Backend Developer, Frontend Developer, DevOps Engineer
**Continuous quality loop:** Code Reviewer, Verifier, Security Reviewer
**Output:** Working, tested, reviewed code

### Ship Phase
**Purpose:** Prepare for deployment.
**Active agents:** Technical Writer, DevOps, Verifier (final gate)
**Output:** Updated docs, deployment configs, passing CI

### Evaluate Phase
**Purpose:** Measure outcomes and inform next iteration.
**Active agents:** Process Evaluator (continuous)
**Output:** Metrics reports, trend analysis, recommendations

## Agent Activation Rules

- Agents activate when their phase is current
- Agents stand down when their phase completes
- Quality agents (Code Reviewer, Verifier, Security Reviewer) run continuously during Build
- Process Evaluator runs continuously across all phases
- Brownfield Bootstrapper runs at bootstrap AND after significant changes (reconciliation)
