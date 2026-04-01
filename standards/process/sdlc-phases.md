# SDLC Phases and Agent Activation

## Status: REFERENCE
## Applies to: All agents

## Prerequisites

- **Agent Teams enabled:** `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` in environment or settings
- **TaskMaster MCP server** configured for Decompose phase
- **spec-kit** installed for Spec phase (`/specify` command)

## Phase Definitions

### Bootstrap Phase
**Purpose:** Derive system understanding from existing code (brownfield) or establish initial structure (greenfield).
**Team:** Project Bootstrapper (solo — internally spawns sub-teams per directory)
**Output:** Complete `.meta/` description tree, gap analysis

**How to invoke:**
```
"Bootstrap this codebase — use the project-bootstrapper agent to analyze the existing code and generate .meta/ descriptions."
```

### Spec Phase
**Purpose:** Translate business intent into structured specifications.
**Tool:** spec-kit (`/specify` command)
**Team:** Product Manager (lead), Product Owner, Domain Modeler, Researcher (when domain is unfamiliar)
**Process:**
1. **Project Intake (MANDATORY before any research):** SEM conducts structured intake with human — classify project type (greenfield/brownfield/re-engineering/lift-and-shift/consolidation), inventory and triage source material, produce research plan with anti-pattern catalog if applicable. See SEM agent's "Project Intake" section. Save to `docs/plans/`.
2. **If the domain requires research** (unfamiliar regulations, external APIs, complex data models): Deploy Researcher to analyze source material and produce research reports in `docs/research/`. The research plan from step 1 determines deployment pattern, source material priority, and anti-pattern guards. The research informs all subsequent spec work.
3. PM initiates `/specify` to drive structured requirements gathering loop
4. Iterative refinement with stakeholder until spec is complete and unambiguous
5. Domain Modeler validates domain concepts and relationships (informed by research report if one exists)
6. PO confirms acceptance criteria and prioritization
**Output:** Hierarchical PRDs, acceptance criteria, domain model validation, research reports (if applicable)

**Scaling the research step:** The SEM must assess the scope of research needed and choose the right deployment pattern (see SEM agent's Team Deployment Architecture):
- **Small scope** (1 domain, few docs): 1 researcher agent
- **Large scope** (multiple bounded contexts, large corpus): Fan-out N researchers in parallel, each scoped to a domain, then reduce with a synthesis agent
- **Massive scope** (50+ source files, multiple analysis dimensions): Recursive Decomposition — multiple fan-out layers, each covering a different dimension, with layer boundaries as review checkpoints. Produces a research plan in `docs/plans/` before deploying any agents.
- **When in doubt:** Ask the human. "This corpus has N domains. Want me to fan out N research agents, or handle it sequentially?"

**How to invoke:**
```
"We need to spec out [feature]. Start the Spec phase — use the product-manager agent with /specify to gather requirements, then have domain-modeler validate the domain model."
```

**If research is needed (small scope):**
```
"We need to spec out [feature] but we don't understand the domain well enough yet. Start with the researcher agent — have it analyze the documents in [path] and produce a research report. Then proceed with spec."
```

**If research is needed (large scope, fan-out):**
```
"This is a large domain with multiple bounded contexts. Fan out [N] research agents across [domains], then synthesize findings into bounded-context PRDs. See the research corpus in [path]."
```

### Design Phase
**Purpose:** Create system architecture and interaction designs.
**Team:** Architect (lead), UX Designer, UI Designer, Multi-Tenant Auditor (when SaaS/multi-tenant)
**Process:**
1. Architect creates ADRs, system boundaries, and component interfaces
2. UX/UI designers produce interaction flows and component designs
3. **If the PRD indicates multi-tenancy or SaaS:** Deploy multi-tenant-auditor to review the proposed architecture for tenant isolation, RBAC, data residency, and org hierarchy. The auditor's findings feed back into ADRs before Decompose.
**Output:** ADRs, system boundaries, interaction flows, component designs, multi-tenant audit (if applicable)

**How to invoke:**
```
"Design the architecture for [feature]. Use the architect agent to create ADRs and system boundaries, and ux-designer for interaction flows."
```

**If multi-tenant:**
```
"This is a multi-tenant SaaS product. After the architect designs the system, deploy the multi-tenant-auditor to review tenant isolation and RBAC before we decompose."
```

### Decompose Phase
**Purpose:** Break PRDs and design artifacts into executable task graphs.
**Tool:** TaskMaster (MCP server)
**Team:** Product Manager (task decomposition), Architect (technical refinement)
**Process:**
1. PM feeds PRD into TaskMaster to generate initial task breakdown
2. Architect reviews and refines tasks with dependency mapping and technical detail
3. Tasks are ordered by dependency, each with acceptance criteria and test strategy
4. **T-shirt sizing required:** Every task MUST have a size estimate (XS/S/M/L/XL → 1/2/3/5/8 points). This feeds the velocity metric in release notes during Evaluate.
5. **Infrastructure task required:** Every project MUST include a task for docker-compose setup (or equivalent run command) early in the dependency chain, before any integration testing tasks. This ensures the stack can be stood up for the Verify phase.
**Output:** Ordered task graph with dependencies, acceptance criteria, t-shirt sizes, and implementation guidance

**How to invoke:**
```
"Decompose the PRD into tasks. Use TaskMaster to break it down, then have the architect agent refine dependencies and technical detail."
```

### Build Phase
**Purpose:** Implement features using red/green TDD.
**Team composition:**
- **Implementation agents** (foreground, one at a time per task): Backend Developer, Frontend Developer, DevOps Engineer
- **Watchdog agents** (background, continuous): Code Reviewer, Verifier, Security Reviewer
**Enforcement:** TDD hooks run automatically on every Edit/Write (PreToolUse → PostToolUse)

**Scaling the build:** The SEM should assess task dependencies to determine parallelization:
- **Sequential:** Tasks with dependencies must be built in order (default, safest)
- **Parallel:** Independent tasks with **no overlapping file sets** can be built by separate agents simultaneously (use worktree isolation)
- **Pipeline + Watchdogs:** Every implementation agent gets a background code-reviewer + verifier regardless of parallel/sequential

**⚠️ File-Set Isolation Rule:** Before parallelizing tasks, identify which files each task will touch. If any two tasks share a file, they MUST be serialized. Worktrees isolate the filesystem, not the file set — two agents modifying the same file on different branches will produce merge conflicts. This includes indirect overlaps (e.g., two agents both adding to the same `__init__.py`). When merging parallel results back to main, merge one branch at a time in dependency order and run integration tests after each merge.

**Output:** Working, tested, reviewed code

**How to invoke:**
```
"Start the Build phase for task [N]. Deploy the backend-developer agent for implementation. Run code-reviewer and verifier as background watchdogs."
```

**Watchdog pattern:** During Build, quality agents should be spawned as background tasks that review each completed unit of work. The implementation agent works in foreground; after each task completion, watchdogs review before proceeding to the next task.

### Verify Phase
**Purpose:** Stand up the running system for human acceptance testing. The SEM offers to bring up the stack so the human can test the feature in a real environment before shipping.
**Team:** DevOps Engineer (stands up the stack), SEM (orchestrates human interaction)
**Process:**
1. SEM announces: "Build is complete. Would you like to test the feature? I can stand up the stack for you."
2. If human accepts: SEM deploys devops-engineer to stand up the stack via docker-compose (or project-appropriate run command)
3. DevOps engineer brings up services, verifies health checks, reports access URL
4. SEM tells the human: what URL to open, what to test, what the expected behavior is (from acceptance criteria)
5. Human tests and provides feedback
6. If issues found: SEM loops back to Build to fix, then returns to Verify
7. If accepted: SEM transitions to Ship
**Output:** Running system, human acceptance, feedback log

**How to invoke:**
```
"Stand up the stack for testing. Use devops-engineer to bring up docker-compose, then tell me how to access and test the feature."
```

**Stack-up requirements:**
- MUST use docker-compose (or project-defined run command) — never raw `python3 app.py` or `uvicorn` directly
- MUST use mapped volumes for source code (hot reload)
- MUST verify health checks before reporting ready
- MUST provide: access URL, credentials (if any), what to test, expected behavior

### Ship Phase
**Purpose:** Prepare for deployment.
**Team:** Technical Writer (lead), DevOps Engineer, Verifier (final gate)
**Output:** Updated docs, deployment configs, passing CI

**How to invoke:**
```
"Prepare to ship. Use technical-writer for docs, devops-engineer for deployment config, and verifier for final gate checks."
```

### Evaluate Phase
**Purpose:** Measure outcomes and inform next iteration.
**Team:** Process Evaluator (solo, continuous)
**Output:** Metrics reports, trend analysis, recommendations

**How to invoke:**
```
"Run a retrospective on this sprint. Use the process-evaluator agent to analyze outcomes and generate recommendations."
```

## Agent Activation Rules

- Agents activate when their phase is current
- Agents stand down when their phase completes
- **Watchdog agents** (Code Reviewer, Verifier, Security Reviewer) run as background tasks during Build
- Process Evaluator runs continuously across all phases
- Project Bootstrapper runs at bootstrap (one-time onboarding)

## Team Deployment via Agent Teams

All agents are deployed using Claude Code's agent teams feature (Task tool). The pattern:

1. **Leader** is the main conversation — it reads the SDLC phase and decides which agents to deploy
2. **Foreground agents** are spawned for the primary work of the phase (one at a time)
3. **Background agents** are spawned with `run_in_background: true` for watchdog/quality roles
4. **Handoff** between phases: leader transitions by spawning the next phase's team

### Team Composition Summary

| Phase | Foreground | Background | Tools |
|-------|-----------|------------|-------|
| Bootstrap | project-bootstrapper | — | — |
| Spec | product-manager, product-owner, domain-modeler, researcher | — | spec-kit /specify |
| Design | architect, ux-designer, ui-designer, multi-tenant-auditor (if SaaS) | — | — |
| Decompose | product-manager, architect | — | TaskMaster MCP |
| Build | backend-developer OR frontend-developer OR devops-engineer | code-reviewer, verifier, security-reviewer | TDD hooks |
| Verify | devops-engineer | — | docker-compose |
| Ship | technical-writer, devops-engineer | verifier | — |
| Evaluate | process-evaluator | — | — |
