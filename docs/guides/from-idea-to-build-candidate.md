# From Idea to Build Candidate: An AI-Assisted Software Engineering Process

**Author**: Jason Vertrees + Claude (Architect)
**Status**: Battle-tested on a complex industrial SaaS platform (34 ADRs, 10 PRDs, 16 research reports, zero architectural ambiguity)

---

## Why This Document Exists

We built a complete architecture specification for a complex multi-domain platform in roughly one week of active work. The result was a "Build Candidate" — a tagged commit where every architectural decision is explicit, every scope boundary is documented, and implementation agents can start coding without guessing.

This document captures the process so it can be repeated on any project.

---

## The Big Picture

```
RESEARCH --> PRDs --> STAKEHOLDER REVIEW --> ARCHITECTURE REVIEW --> GAP ANALYSIS --> BUILD CANDIDATE
```

Each phase has a specific shape, specific roles for human vs AI, and specific quality gates. Skip a phase and you pay for it later.

---

## Phase 1: Domain Research

**Goal**: Understand the problem domain deeply before designing anything.

**Shape**: Fan-out/reduce. Multiple AI research agents work in parallel, each analyzing a specific domain area. A synthesis agent combines their findings.

### The Pipeline

```
PLAN --> CONSTRAIN --> CONTEXT --> FAN-OUT --> GATE --> SYNTHESIZE
```

#### 1.1 Plan
- Define the agent topology: which agents, what source material each reads
- Each agent gets a specific domain slice (e.g., "user management", "workflow automation", "reporting")
- Define a standardized output format (same sections across all agents — makes synthesis tractable)

#### 1.2 Constrain (THE MOST CRITICAL STEP)

This is where most AI-assisted projects fail. Without explicit constraints, research agents will:
- Reproduce legacy system patterns as design patterns
- Treat existing implementation as specification
- Copy antipatterns faithfully because they appear authoritative

**What works:**

| Technique | Why |
|-----------|-----|
| WRONG/RIGHT examples | Agents pattern-match on concrete examples better than abstract descriptions |
| "Violations are defects" framing | Sets a hard quality bar; "please avoid" is ignored, "this is a defect" is not |
| Cognitive reframe questions | Forces decomposition before recomposition |
| Context-specific warnings per agent | "This is where it failed before" triggers extra vigilance |

**The cognitive reframe** (critical for migration projects):
1. What BUSINESS NEED does this artifact serve?
2. What LIMITATION of the legacy platform forced this pattern?
3. How would we model this if the legacy system never existed?

This three-question reframe was the single biggest unlock in our process. Same agents, same source data, different framing — dramatically different output quality.

#### 1.3 Context
- Create a domain briefing document that all agents must read first
- Embed the anti-pattern catalog in every agent prompt
- Large context files (>25K tokens): agents read from disk
- Smaller context: embed directly in prompts

#### 1.4 Fan-Out
- Launch all research agents in parallel (background mode)
- Each gets: shared constraints + shared context refs + specific source files + specific warnings
- Track progress (TaskMaster, GitHub Issues, or any tracking tool)
- Wall-clock time is bounded by the slowest agent, not the sum

**Example**: 14 parallel agents, ~7 min wall-clock (11.7x speedup over sequential)

#### 1.5 Gate (NON-NEGOTIABLE)

Before synthesis, run automated checks across all research outputs:
- Grep for known antipattern signatures (boolean flag proliferation, hardcoded enums, 1:1 legacy mappings)
- This gate takes ~10 seconds and prevents hours of wasted synthesis work

#### 1.6 Synthesize
- Single agent reads ALL research reports + reference documents
- Produces unified deliverables (PRDs, domain model, etc.)
- Must normalize: entity names, event names, FK references across outputs
- Must re-verify anti-patterns in synthesis output
- This is the bottleneck (sequential) — Amdahl's Law applies

### Key Lesson: Expect to Fail Before Succeeding

In our first project using this process:

- **Round 1**: Agents misunderstood the domain. A key technology was categorized incorrectly, leading to wrong architectural assumptions. Fix: domain briefing document as mandatory reading.
- **Round 2**: Agents faithfully reproduced legacy platform patterns as design patterns (boolean flag proliferation, fixed enum types, hardcoded statuses). Fix: anti-pattern catalog with WRONG/RIGHT examples + cognitive reframe.
- **Round 3**: Success. Zero anti-pattern violations across 16 agents.

**The lesson**: Don't assume agents understand what "good" looks like. Show them. Concretely. With examples of wrong vs right.

---

## Phase 2: PRD Writing

**Goal**: Translate research into structured product requirements.

**Shape**: Sequential synthesis from research reports, one PRD per bounded context.

### What a PRD Contains
- Feature overview and user stories
- Entity definitions (schema-level detail)
- Business rules (numbered, testable)
- API endpoints
- Domain events published/consumed
- Non-functional requirements (performance, storage, security)
- Acceptance criteria

### Key Principles
- **PRDs describe WHAT, not HOW.** Entity schemas, business rules, API contracts — yes. Technology choices, implementation patterns, library selections — no. Those belong in ADRs.
- **One PRD per bounded context.** Keep them focused. Cross-context concerns (search, audit, notifications) get their own PRD.
- **Business rules are numbered and testable.** Example: `PRD-04-BR-07: "Status is COMPUTED from evidence + policies + exceptions. Never stored as an editable field."` An implementation agent can write a test directly from this.
- **Seed data is specified.** If there are catalog tables (types, capability definitions, workflow stages), the PRD lists the seed values. This prevents agents from inventing their own.
- **Cross-cutting concepts are explicitly declared.** Each PRD must include a "Cross-Cutting Concepts Consumed" section listing which shared concepts this bounded context uses (e.g., permission strings, entity statuses, error code families, event types) and what it expects from them. This makes integration seams visible *before* code is written and feeds the invariant registry (see Phase 6).

---

## Phase 3: Stakeholder Review

**Goal**: Get domain expert and business owner sign-off before investing in architecture.

**Shape**: Human review. AI assists with formatting/compilation but humans make the decisions.

### What Happens
- Compile PRDs into a reviewable format (a single compiled document works well)
- Domain experts (SMEs) review for correctness
- Business owner (CEO/product owner) reviews for scope and priority
- Feedback is captured and incorporated

### Why This Can't Be Skipped
No amount of AI research replaces domain expert validation. SMEs catch nuances that research agents miss. Business owner review confirms scope boundaries (what's MVP, what's v2, what's excluded entirely).

**Expected outputs**: Stakeholder review response, scope confirmations, roadmap documents establishing version boundaries.

---

## Phase 4: Architecture Review (THE CORE LOOP)

**Goal**: Make every architectural decision explicit in ADRs so implementation agents have zero ambiguity.

**Shape**: One-by-one Q&A loop between architect (AI) and decision-maker (human).

### The Q&A Loop

This is the heart of the process and the part that produces the most value:

```
For each architectural topic:
  1. AI presents CONTEXT (what needs deciding, why it matters)
  2. AI presents OPTIONS (2-3 approaches with trade-offs)
  3. AI states OPINION (recommended approach with reasoning)
  4. Human DECIDES (agrees, modifies, or picks different option)
  5. AI writes ADR capturing the decision
```

**Critical rules:**
- **One topic at a time.** Don't present 8 decisions in a wall of text. Focused attention produces better decisions.
- **AI proposes, human disposes.** The AI should have a strong opinion and state it clearly, but the human makes the call. This is not a democracy — it's a consultation.
- **Capture everything in ADRs.** If it was discussed, it gets written down. "We'll figure it out later" is not an acceptable outcome — that's exactly where implementation agents will guess wrong.
- **The human's domain knowledge overrides AI's technical preferences.** When a stakeholder says "No polling, that consumes too many resources" — that's a constraint, not a discussion point.

### What Makes a Good ADR

We use Michael Nygard's template:
- **Context**: Why this decision needs to be made
- **Decision**: What we decided (numbered sub-decisions for complex topics)
- **Consequences**: What follows from this decision (both positive and negative)

Plus:
- **Cross-references** to related ADRs
- **Code examples** where the pattern isn't obvious from description alone
- **Explicit scope boundaries** ("NOT building X for MVP", "deferred to v2")

### Batching and Parallelism

While the Q&A loop is sequential (each decision may inform the next), the ADR *writing* can be parallelized:
- After deciding 3-4 related topics, dispatch parallel agents to write the ADRs
- Human continues the Q&A loop on the next topic while ADRs are being written
- This keeps the human's time fully utilized

**Pattern**: Discuss 2-4 topics --> dispatch background agents to write ADRs --> continue discussing --> agents complete --> review and commit --> repeat.

### Example Topics (in rough order)

1. Monorepo layout
2. Schema patterns (DTOs, services, models)
3. Context isolation (events vs imports)
4. Bounded context boundaries
5. API design patterns
6. Frontend architecture
7. Workflow runtime selection
8. AI/agent architecture
9. Error handling philosophy
10. Logging and observability
11. Data architecture (DB, modeling, tenant isolation)
12. Security architecture (auth, authorization, trust boundaries)
13. Testing strategy
14. Integration framework
15. Caching strategy
16. Deployment architecture
17. Database migrations

The specific list varies by project. The point is: every decision an implementation agent would need gets its own ADR.

---

## Phase 5: Gap Analysis

**Goal**: Verify completeness. Find every remaining decision that an implementation agent would need to guess about.

**Shape**: Automated analysis + human triage.

### The Process

1. **Deploy an architect review agent** against all research, PRDs, and ADRs
2. Agent produces a structured report: missing ADRs, ambiguous decisions, pattern gaps, PRD contradictions
3. **Categorize findings** into:
   - **Phase 0 blockers**: Must resolve before any code is written (scaffolding depends on these)
   - **Phase 1 items**: Must resolve before the relevant feature is built
   - **Phase 2+ deferrals**: Can wait
4. **Resolve blockers** using the same Q&A loop from Phase 4

### What Gap Analysis Typically Finds

- Missing ADRs for infrastructure decisions (object storage, migrations, connection pooling)
- Ambiguous decisions in existing ADRs (two valid interpretations)
- Pattern gaps (code-level patterns not yet documented)
- PRD contradictions (PRDs still referencing decisions that ADRs overrode)
- **Cross-cutting invariant drift** — the same concept (e.g., IAM permissions) defined differently across bounded contexts. One module uses CRUD-style permissions (`file_read`, `file_write`), another uses domain-labeled permissions (`vendor_approve`). The gap analysis must check that every cross-cutting concept declared in PRDs uses a consistent vocabulary.

### Why This Step Matters

The gap analysis is one of the highest-value steps. In our first project, after 21 ADRs we thought we were done. The analysis found 9 Phase 0 blockers that would have caused implementation agents to guess or stall. Examples:
- No object storage pattern decided (where do files go?)
- No migration conventions (multiple agents writing migrations = conflicts)
- Permission string format inconsistent between two documents
- A key table schema never specified (just described conceptually)

**Without the gap analysis, implementation would have started with hidden ambiguity.**

---

## Phase 6: Build Candidate

**Goal**: Tag a commit that represents "architecture complete, ready to build."

### What a Build Candidate Contains
- All ADRs written and accepted
- All PRDs reviewed and consistent with ADRs
- Gap analysis complete, all blocking gaps resolved
- Contradictions between documents fixed
- Scope boundaries explicit (what's MVP, what's deferred, what's excluded)
- **Invariant registry** — a canonical, auditable list of every cross-cutting concept in the system

### The Invariant Registry

The invariant registry is a single artifact (file or table) that lists every concept shared across bounded contexts, structured as formal contracts with Design by Contract principles.

#### Contract Structure

Each registry entry is a **contract** with four parts:

| Field | Purpose |
|-------|---------|
| **Concept** | The shared thing (e.g., "IAM permission strings") |
| **Owner** | The bounded context that defines this concept |
| **Preconditions** | What must be true before consuming this concept (caller's obligation) |
| **Postconditions** | What the owning module guarantees after execution (provider's guarantee) |
| **Invariants** | What must always be true about this concept across all contexts |
| **Consuming contexts** | Which bounded contexts depend on this concept |
| **Enforcement** | How consistency is verified (variance test, shared type, seed data) |

#### Dependency Direction

**The provider owns the contract.** If Module A depends on Module B, then B defines the contract and makes the rules. A must satisfy B's preconditions. B guarantees its postconditions. This prevents the common failure where consumers independently invent their own expectations about a provider's behavior.

Example:
```
Concept: IAM Permission Strings
Owner: IAM context (defines the canonical permission format)
Preconditions: Permission strings must be in `domain:action` format
Postconditions: IAM resolves any valid permission string to a boolean grant/deny
Invariants: Permission vocabulary is a closed set — only values in the
            IAM catalog are valid. No context may invent new permissions.
Consuming contexts: Vendor Management, Document Management, Workflow Engine
  → Each consumer MUST use permissions from the IAM catalog
  → Each consumer MUST NOT define its own permission strings
```

#### Inside vs. Outside

Each contract must make the boundary between a component's internals and its public surface explicit:

- **Outside (public contract)**: The preconditions, postconditions, and invariants that other modules depend on. These are stable and versioned. Breaking changes require coordination across all consumers.
- **Inside (implementation)**: How the module fulfills its contract. This can change freely as long as the contract holds. No other module should depend on internal implementation details.

This distinction prevents the common coupling failure where Module A depends on Module B's internal data structures rather than its public contract.

#### Compositional Hierarchy

Contracts compose hierarchically. A higher-level subsystem's contract is built from its children's contracts:

```
Platform Contract
├── IAM Subsystem Contract
│   ├── Permission Resolution Contract
│   ├── Role Assignment Contract
│   └── Tenant Isolation Contract
├── Vendor Management Subsystem Contract
│   ├── Invitation Lifecycle Contract (consumes: IAM permissions)
│   ├── Relationship Lifecycle Contract (consumes: IAM permissions, Workflow routing)
│   └── Compliance Evaluation Contract
└── Workflow Subsystem Contract
    ├── Task Routing Contract (consumes: IAM permissions, Org group membership)
    └── Signal Bridge Contract (consumes: Domain events from Vendor Management)
```

Each level in the hierarchy composes the contracts of its children. When a parent subsystem makes a guarantee, that guarantee is traceable down to the specific child contracts that fulfill it. This makes it possible to verify completeness: if a child contract is missing or incompatible, the parent's guarantee cannot hold.

**Why this exists**: Without it, each bounded context independently invents vocabulary for shared concepts. Unit tests pass — every module is internally consistent — but the system fails at integration seams because Module A's assumptions about Module B were never validated. This is "The Modular Success Trap" (see Anti-Patterns). The contract structure (preconditions, postconditions, invariants, dependency direction, compositional hierarchy) transforms the registry from a vocabulary list into a verifiable specification of cross-module behavior.

The registry is both a human-readable document and the source-of-truth for automated variance tests during build phases. Build phase output criteria should include:
- **E2E tests** that validate cross-module contracts (not just "A calls B" but "the full chain produces the expected outcome, with preconditions satisfied and postconditions verified")
- **Variance tests** that check every consuming context against the registry's canonical definitions
- **Contract conformance tests** that verify each module satisfies its preconditions as a consumer and upholds its postconditions as a provider
- **Real-user persona testing** — e2e tests must run as a non-superuser persona to catch permission and configuration gaps that admin/superuser accounts mask

### What a Build Candidate Does NOT Contain
- Implementation code
- Code-level pattern templates (these emerge from scaffolding)
- Perfect PRDs (some contradictions may remain in non-blocking areas)

### The Tag
```
git tag -a bc-1 -m "Build Candidate 1: Architecture complete, ready for implementation"
```

A BC is like an RC (release candidate) but for the *design* phase. It says: "This specification is complete enough to build from. If an implementation agent needs to guess, we missed something."

---

## Roles: Human vs AI

| Activity | Human | AI |
|----------|-------|-----|
| Domain research | Reviews, validates | Executes (parallel agents) |
| PRD writing | Reviews, approves | Drafts |
| Stakeholder review | Decides | Formats, compiles |
| Architecture Q&A | Decides | Proposes, writes ADRs |
| Gap analysis | Triages | Executes analysis |
| ADR writing | Reviews | Writes (parallel agents) |
| Scope decisions | Decides | Presents options |

**The human's irreplaceable contributions:**
- Domain knowledge that agents can't infer from documents
- Scope judgment (what's MVP, what's excluded)
- Priority decisions (what IS the product)
- Constraint setting ("no polling", "fail fast and loud", "98% coverage")
- Taste — recognizing when a technically valid solution is wrong for the product

**The AI's irreplaceable contributions:**
- Parallel research at scale (16+ agents simultaneously)
- Exhaustive gap analysis (humans miss things in 30+ document sets)
- Consistent ADR writing (same format, cross-references, consequences)
- Holding the full context (no human can hold 30+ ADRs + 10 PRDs in working memory)

---

## Anti-Patterns (What Goes Wrong)

### 1. "Let's Just Start Coding"
Skipping the specification phase means every implementation agent makes independent guesses about architecture. You get inconsistent patterns, duplicated infrastructure, and expensive rework.

### 2. "The AI Knows Best"
AI proposes, human disposes. When agents run without human checkpoints, they produce technically sound but domain-wrong decisions (like caching data that must always be fresh, or mirroring backend structure in frontend pages).

### 3. "We'll Figure It Out Later"
Every "later" becomes an implementation agent guessing NOW. If it's worth discussing, it's worth writing down. If it's not worth writing down, it's not worth discussing.

### 4. "Review Everything at Once"
Decision fatigue is real. One topic at a time, one decision at a time. The Q&A loop works because it's focused.

### 5. "The PRDs Are the Spec"
PRDs describe WHAT. ADRs describe HOW. You need both. PRDs without ADRs leave implementation decisions to chance. ADRs without PRDs leave scope to interpretation.

### 6. "Copy the Legacy System"
This is the #1 failure mode for migration projects. Legacy implementations are constrained by the legacy platform. Reproducing those constraints in a new system is sabotage. The cognitive reframe (business need --> limitation --> clean-sheet design) is essential.

### 7. "We Don't Need a Gap Analysis"
You do. The gap analysis is cheap (~30 min) and prevents expensive implementation stalls. You will always find blockers you thought you'd already covered.

### 8. "The Modular Success Trap"
Every component passes its unit tests. 98% coverage. The app even looks great. But the contracts *between* components — the permissions that routes expect vs. what the catalog provides, the signals that services should send vs. what they actually wire up, the routing groups that workflows need vs. what gets seeded — those seams are where the bugs hide.

This trap is especially dangerous at high velocity. When parallel agents build 260K lines in days, integration seams accumulate faster than they can be tested. The fix isn't "write more tests" — it's:
1. **Explicitly enumerate cross-module contracts** and test them as first-class artifacts (the invariant registry)
2. **Run e2e tests as a real user**, not the superuser — admin accounts bypass permission checks, pre-seeded data masks configuration gaps
3. **Include invariant audits** in build phase output criteria, not just per-module coverage targets

Concrete examples from a real project:
- **Approval signal bridge**: InvitationService and Temporal both worked perfectly alone. The connection between them was never built.
- **RBAC catalog gap**: Routes guarded with `:read` permissions, roles assigned capabilities, but the intersection never matched.
- **Routing group configuration**: Workflows route to groups, groups contain members, but no group existed in the right domain.

---

## Reproducing This Process

### Prerequisites
- Source material (existing system docs, stakeholder interviews, domain research)
- A human decision-maker with domain knowledge
- AI agents capable of: reading files, writing files, web search, parallel execution
- A version-controlled repository for outputs

### Minimum Viable Process
1. **Research**: Fan-out agents with anti-pattern constraints --> synthesize into PRDs
2. **Review**: Domain experts validate PRDs
3. **Architecture**: One-by-one Q&A loop --> ADRs
4. **Gap analysis**: Architect agent reviews everything --> resolve blockers
5. **Tag**: Build Candidate

### Scaling Down
For smaller projects, the process compresses:
- Research might be a single agent reading existing docs
- PRDs might be a single document
- Architecture review might be 5-10 ADRs instead of 30+
- Gap analysis might be a quick review instead of a formal report

The shape stays the same: understand --> specify --> decide --> verify --> tag.

### Scaling Up
For larger projects:
- More research agents, more domain slices
- Multiple PRD synthesis agents (parallel drafting, sequential normalization)
- Architecture review split across multiple sessions
- Multiple gap analysis passes (one per subsystem)
- Multiple Build Candidates (bc-1 for core, bc-2 for extensions)

---

## The One Rule

**If an implementation agent would need to guess, you're not done.**

Every guess is a coin flip. Some land right, most land wrong, and wrong guesses compound. The Build Candidate is the point where guessing stops and building starts.
