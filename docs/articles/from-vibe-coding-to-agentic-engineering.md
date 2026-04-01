# From Vibe Coding to Agentic Engineering: 270,000 Lines, One Week, and the Discipline of Constraints

**Jason Vertrees**
**March 2026**

A couple of years ago I saw a phase transition coming — a fundamental shift in how AI would affect knowledge work and our ability to build software. I've been getting up at four in the morning ever since, building and training and learning and getting better along the way. I've learned a great deal building in the trenches, I've started my own company, and I thought I'd share some of what I accomplished this past week.

I'm proud of what I accomplished, and I share it because it advances my two open questions — and because writing is how I think. It forces me to isolate concepts, find the gaps in my understanding, and teach myself what I actually learned versus what I think I learned.

My two open questions right now: First, how do we build larger and larger systems reliably and repeatably at scale? Second, what does this mean for our engineering teams and departments as our ability to deliver continues to accelerate? On client projects, I've been deploying a variety of strategies to try to build better and larger. This article reports on my largest success to date.

I'm going to make a claim that will make experienced engineers deeply skeptical: I laid down roughly 270,000 lines of production code from scratch in one week. A week ago there was zero code. As of now there's a working system — it stands up, it looks good, and it functions. It's still incomplete, but it's a solid foundation. In the past 24 hours alone I've added another 55,333 lines with 9,409 lines deleted. During that period, across all the changes I made, I _never once_ had to touch the core domain model. The discipline and effort I put into the initial design and implementation has paid dividends.

I don't know what I don't know. I fully expect there are edges, seams, and artifacts that haven't surfaced yet. But for the time being, I'm still making successful changes to the system daily — and the core domain model hasn't been touched. The changes happen at the periphery, in the integration layers and UI, while the foundation holds steady. That's the signal I care about.

I know what you're thinking. I would have thought the same thing. "This has to be the biggest pile of crap ever created. There's _no way_ it'll work or be maintainable." And honestly, had I been reading this from someone else's blog, I would have closed the tab.

So let me try to convince you that maybe that's not the case. And then let me tell you what I didn't expect, because that's the part worth reading.

## The Tyranny of State Space

I wrote an article last year called [The Tyranny of State Space](https://heavychain.org/blog?article=the-tyranny-of-state-space) that frames the fundamental problem of software engineering through the lens of statistical mechanics. The core idea: when we're designing systems, we're navigating an effectively infinite-dimensional space of possible implementations. Every flag, every config option, every API choice, every naming convention adds a new axis. Without constraints, you can end up anywhere in that space.

I visualize it as a cube. There's a point where you start and a point where you want to be. In theory, you can get there any number of ways. In practice, without proper governance, guidelines, and enforcement, you won't get there at all. You'll end up in some other corner of the space — a system that compiles and runs but doesn't solve the right problem in the right way.

In physical systems, Boltzmann showed that energy landscapes create statistical pull toward stable configurations. Proteins fold correctly not by brute force but because thermodynamics creates valleys — attractors that guide the system toward function. In software, there are no natural valleys. If your system enters a bad state, it stays there. Nothing nudges it back.

But you can *design* the valleys. You can create attractors — defaults that pull toward good states, enforcement mechanisms that block bad transitions, constraints that narrow the vast state space down to the region where correct implementations live.

That's what the harness is. It's an engineered energy landscape for AI-assisted development.

## The Credibility Problem

First, some context. I've been leading engineering teams for fifteen to twenty years. I've shipped enterprise SaaS platforms, managed teams building complex multi-domain systems, and accumulated the usual scar tissue about what goes wrong when you move fast without discipline.

My number one principle for software engineering is discipline. Not talent, not tooling, not velocity — discipline. Discipline is what lets you scale without pushing against a rope or constantly falling over. It's what separates "fast" from "reckless."

When AI coding agents became capable enough to produce real software, I didn't just turn them loose and hope for the best. I tried to codify everything I know about building software correctly into a system that the agents would be forced to follow. Not guidelines they could ignore. Not best practices they could pattern-match around. Actual enforcement mechanisms with hard gates that block non-compliant work.

The result is what I call a "coding harness" — an engineering governance system that wraps around AI agents the same way guardrails wrap around a highway. You can drive fast, but you can't drive off a cliff. (Interestingly, when the harness is in place, agents take _longer_ to produce code — but the code is orders of magnitude better and rarely needs to be revisited.)

### What Discipline Looks Like in Practice

Before a single line of application code was written, the specification work was already substantial. Here's what the documentation tree looks like for the system I built (a multi-tenant compliance SaaS platform in the vendor management space):

```
docs/
├── research/                    # 17 research reports
│   ├── R01-iam-multitenancy.md
│   ├── R02-relationship-management.md
│   ├── ...through...
│   └── R17-integration-field-mappings.md
│
├── prds/                        # 10 bounded-context PRDs
│   ├── PRD-01-iam.md
│   ├── PRD-02-relationship-management.md
│   ├── ...through...
│   ├── PRD-10-observability.md
│   └── traceability-matrix.md   # Maps every requirement to its PRD + ADR
│
├── adrs/                        # 37 Architecture Decision Records
│   ├── 001-monorepo-layout.md
│   ├── 002-three-layer-schema-pattern.md
│   ├── ...through...
│   ├── 037-frontend-generated-sdk.md
│   └── gap-analysis-report.md   # What we found was still missing after 37 ADRs
│
├── plans/                       # 45 implementation plans
│   ├── build-phases.md          # Master phase sequencing
│   ├── 2026-03-08-phase-1-core-domain.md
│   ├── ...per-phase design + implementation plans...
│   └── 2026-03-11-salesforce-etl-plan.md
│
└── builds/                      # 15 build phase completion reports
    ├── phase-0a/completion-report.md
    ├── phase-0b/completion-report.md
    ├── ...through...
    └── phase-4d0/completion-report.md
```

That's **17 research reports, 10 PRDs, 37 ADRs, 45 plans, and 15 build phase completion reports** — all written before or during implementation, not after. Each build phase completion report includes a tag, commit hash, output criteria verification table, key artifacts, test counts, deferred items, and lessons learned. (A testament to the client's commitment: I compiled the research and PRDs into an 18,000-line, 572-page system specification. The CEO read every single page — it took him about 15 hours. _That_ is impressive.)

This is what discipline looks like. Not "I wrote a lot of code fast." Rather: "I researched the domain thoroughly, specified every bounded context, made every architectural decision explicit, verified completeness with a gap analysis, decomposed implementation into dependency-ordered phases with measurable output criteria, and then built — with enforcement mechanisms that prevented the agents from cutting corners."

The discipline is what allowed the velocity. Not the other way around.

### The Archaeological Dig

The specification work didn't start from a blank page. Before the research agents could run, before the PRDs could be written, I had to understand what I was replacing. This is a migration project — moving an entire organization off of Salesforce onto a modern, purpose-built platform.

That meant an archaeological dig through the existing system. A separate research repository contains the full excavation:

```
system-research/
├── domain_model/
│   └── SPECIFICATION_PLAN.md        # "What are we actually building?"
│
├── salesforce/
│   ├── exports/                     # Full Salesforce data export
│   ├── metadata/                    # Org metadata extraction
│   ├── analysis/                    # Automated analysis of flows + objects
│   ├── ACTIVE_FLOW_DOCUMENTATION.md # Every active automation documented
│   ├── BUSINESS_LOGIC_INVENTORY.md  # Where logic lives (Apex, flows, formulas)
│   ├── SALESFORCE_AUTOMATION_CATALOG.md  # Complete catalog of automations
│   └── UNIFIED_ANALYSIS.md          # Synthesized findings
│
├── src-audit/                       # 10 legacy repositories audited
│   ├── architecture-overview.md     # What exists today
│   ├── service-catalog.md           # Every service mapped
│   ├── salesforce-integrations.md   # Integration points documented
│   ├── lambda-analysis.md           # AWS Lambda functions cataloged
│   ├── apex-deep-dive.md            # Salesforce Apex code analyzed
│   └── code-quality-assessment.md   # Honest assessment of legacy quality
│
├── legacy_discovery/
│   ├── salesforce_docs/             # Extracted documentation
│   └── salesforce_domain_analysis/  # Domain model derived from data
│
├── migration/
│   ├── SALESFORCE_TO_MODERN_STACK.md # Migration strategy
│   └── LESSONS.md                   # What we learned
│
└── deliverables/
    ├── acme-corp-business-context.md  # Business context for stakeholders
    ├── migration-strategy.md        # How we're getting out
    └── organizational-design.md     # Team structure for the new world
```

A full Salesforce data export. Metadata extraction. Ten legacy repositories audited. Every automation cataloged. Every integration point documented. The domain model derived from actual data, not from what people *thought* the system did.

(A useful technique: when researching existing systems, don't just ask AI to read the code and describe it. Instead, ask it to discover what *actually exists* versus what the code *claims to be*. People often had difficulty creating the initial version of what they built, and the code frequently masks or masquerades an alternative architecture underneath. I've used this technique successfully to take a client project from the wrong architecture to the right one.)

This is the upstream discipline that made the specification phase possible, which in turn made the build phase possible. The chain is: **archaeological dig → domain understanding → research reports → PRDs → ADRs → gap analysis → Build Candidate → disciplined implementation**. Skip any link and the downstream work suffers.

The result is not just a working platform. It's a repeatable strategic pattern for getting a fully functioning organization out of Salesforce — from discovery through migration. That pattern, honestly, might be more valuable than the code itself.

### A Note on Smaller Scale Builds

For PRDs up to a couple thousand lines, I've found a simpler pattern that's been repeatedly successful: define the domain, define the problem, apply the same discipline described in this article — and use [Task Master](https://github.com/eyaltoledano/claude-task-master). It's an open source project that organizes work into dependency-ordered task graphs. The way it structures work and guides Claude through implementation is genuinely impressive.

## What the Harness Actually Contains

This isn't a single prompt or a clever CLAUDE.md file. It's a multi-layered enforcement system with over two dozen specialized agent types, four shell hooks, twenty written standards, a phase-gated SDLC, and a formal specification process. Here's the structure:

```
engineering-harness/
│
├── 📋 Process (the "what happens when")
│   ├── docs/process/
│   │   └── from-idea-to-build-candidate.md     # 6-phase spec process
│   │       RESEARCH → PRDs → STAKEHOLDER REVIEW
│   │       → ARCHITECTURE REVIEW → GAP ANALYSIS
│   │       → BUILD CANDIDATE
│   │
│   ├── standards/process/
│   │   ├── sdlc-phases.md          # 8-phase SDLC with agent teams per phase
│   │   │   Bootstrap → Spec → Design → Decompose
│   │   │   → Build → Verify → Ship → Evaluate
│   │   ├── tdd-workflow.md         # Red/Green/Refactor — mandatory, not suggested
│   │   ├── definition-of-done.md   # Checklist gating every task completion
│   │   ├── code-review-process.md  # Structured review with agent reviewers
│   │   ├── domain-fidelity.md      # Domain briefing docs, anti-pattern catalogs
│   │   └── invariants.md           # Machine-verifiable project rules
│   │
│   └── .sdlc/
│       ├── tracker.py              # Phase state machine with DoD gating
│       ├── dod-templates.json      # Definition of Done per phase
│       └── state.json              # Persistent phase state + transition history
│
├── 🔒 Enforcement (the "you can't skip this")
│   ├── hooks/
│   │   ├── check-test-exists.sh    # PreToolUse: blocks code edits without tests
│   │   ├── check-invariants.sh     # PreToolUse: validates INVARIANTS.md rules
│   │   ├── mark-dirty.sh           # PostToolUse: flags production code changes
│   │   └── verify-green.sh         # Stop: blocks completion unless tests/types/lint pass
│   │
│   └── INVARIANTS.md (per-project)
│       ├── Machine-verifiable rules with shell verify commands
│       ├── Cascading: global → project → component-level
│       ├── Multi-layer enforcement: hooks + tests + CI + agent instructions
│       └── "A spec that nothing enforces is just a wish"
│
├── 📏 Standards (the "what good looks like")
│   ├── standards/code/
│   │   ├── clean-code.md           # SOLID, no dead code, no premature abstraction
│   │   ├── error-handling.md       # Fail fast, structured errors, no silent swallowing
│   │   ├── python-conventions.md   # Language-specific idioms and patterns
│   │   └── typing-standards.md     # Strict mypy, no Any escape hatches
│   │
│   ├── standards/testing/
│   │   ├── testing-standards.md    # 98% coverage, test naming, test isolation
│   │   ├── test-naming.md          # "should <behavior> when <condition>"
│   │   └── llm-evaluation.md       # How to test AI/LLM components
│   │
│   ├── standards/architecture/
│   │   ├── layer-boundaries.md     # Dependency direction: API → Service → Domain
│   │   ├── abstraction-rules.md    # When (and when not) to abstract
│   │   └── adr-process.md          # Nygard template, cross-references, code examples
│   │
│   ├── standards/security/
│   │   ├── owasp-checklist.md      # Injection, auth, secrets, data protection
│   │   └── data-handling.md        # PII, encryption, retention policies
│   │
│   └── standards/quality/
│       └── metrics.md              # Coverage trends, defect rates, velocity tracking
│
├── 🤖 Agents (the "who does what")
│   └── agents/                        # 23 specialized agent definitions
│       │
│       ├── Orchestration
│       │   └── sem.md                 # Software Engineering Manager — the conductor
│       │       Owns SDLC lifecycle, deploys teams, enforces phase gates
│       │       Deployment patterns: solo, fan-out, fan-out/reduce,
│       │       sequential pipeline, pipeline+watchdogs, recursive decomposition
│       │
│       ├── Strategy & Specification
│       │   ├── product-manager.md     # PRD writing, prioritization, scope
│       │   ├── product-owner.md       # Acceptance criteria, spec validation
│       │   ├── domain-modeler.md      # Ubiquitous language, bounded contexts
│       │   └── researcher.md          # Deep-dive analysis with anti-pattern guards
│       │
│       ├── Design
│       │   ├── architect.md           # System boundaries, ADRs, data flow
│       │   ├── ux-designer.md         # User flows, interaction patterns
│       │   └── ui-designer.md         # Component specs, design tokens
│       │
│       ├── Implementation
│       │   ├── backend-developer.md   # Red/green TDD, strict typing, clean code
│       │   ├── frontend-developer.md  # Accessible, component-driven, TDD
│       │   └── devops-engineer.md     # Docker, CI/CD, infrastructure-as-code
│       │
│       ├── Quality
│       │   ├── code-reviewer.md       # Standards compliance, pattern checks
│       │   ├── architect-reviewer.md  # Module boundaries, coupling analysis
│       │   ├── security-reviewer.md   # OWASP, dependency audit, secrets scan
│       │   ├── verifier.md            # Hard gate: tests + coverage + types + lint
│       │   └── multi-tenant-auditor.md # Tenant isolation, data leakage checks
│       │
│       ├── Support
│       │   ├── code-simplifier.md     # Post-implementation cleanup
│       │   ├── spec-enforcer.md       # Validates specs against standards
│       │   ├── technical-writer.md    # API docs, .meta/ descriptions
│       │   └── project-bootstrapper.md # Brownfield onboarding, .meta/ generation
│       │
│       └── Evaluation
│           └── process-evaluator.md   # Metrics, baselines, retrospectives
│
└── 🔬 Research
    ├── docs/research/
    │   ├── agent-hardening-research.md       # How to prevent agent prompt drift
    │   ├── agent-hardening-research-v2.md    # Revised hardening strategies
    │   ├── recursive-decomposition-research.md # Task graph execution patterns
    │   └── shacl-meta-descriptions.md        # Metadata validation approaches
    │
    └── docs/process/
        └── from-idea-to-build-candidate.md   # The full spec-to-BC pipeline
            6 phases, battle-tested on a 34-ADR industrial platform
```

This is not decoration. Every piece exists because something went wrong without it.

## How Enforcement Actually Works

The tree above is just structure. What matters is how these pieces interact to strip away the portions of state space I don't want to sample. Each enforcement layer eliminates a different region of bad outcomes, and an agent has to fail at every single layer to produce a violation.

### Layer 1: Agent Instructions

Every agent reads the standards relevant to its role before producing any work. The backend developer reads TDD workflow, clean code, typing standards, and error handling before writing a single line. The architect reads layer boundaries, ADR process, and abstraction rules. This is the "soft" layer — it relies on the agent following instructions, which they usually do, but not always.

### Layer 2: Shell Hooks (Hard Gates)

This is where it gets real. Four shell scripts execute automatically on specific tool operations:

**Before any code edit**, `check-test-exists.sh` verifies that a test file exists for the module being modified. If you try to write production code without a test, the edit is blocked. Not warned — blocked. This enforces the "Red" step of TDD at the tool level. The agent cannot skip writing the failing test first.

**Before any code edit**, `check-invariants.sh` reads the project's `INVARIANTS.md` file, extracts machine-verifiable rules, runs their shell verify commands, and blocks the edit if any invariant is violated. Invariants cascade — project-level rules apply everywhere, component-level rules add additional constraints for specific directories.

**After any code edit**, `mark-dirty.sh` touches a `.tdd-dirty` marker file. This is a zero-cost breadcrumb that tells the next hook something changed.

**When the agent finishes**, `verify-green.sh` checks for that dirty marker. If production code was modified, it runs the full verification suite — pytest with 98% coverage threshold, mypy strict type checking, ruff linting. If any check fails, the agent's completion is blocked. It cannot claim "done" with failing tests, type errors, or lint violations.

The result: an agent literally cannot produce code that doesn't have tests, doesn't type-check, and doesn't pass lint. These aren't suggestions. They're hard gates.

### Layer 3: Watchdog Agents

During the build phase, the SEM (orchestrator agent) deploys implementation agents in the foreground and watchdog agents in the background — code reviewer, verifier, and security reviewer running in parallel. After each task completes, the watchdog results are checked. If any issues are found, the implementation agent is re-spawned with fix instructions. The task is not marked done until all watchdogs are clean.

### Layer 4: Phase Gates

The SDLC tracker maintains a state machine with Definition of Done checklists per phase. You cannot transition from Design to Build without completing all Design DoD items. You cannot transition from Build to Verify without completing all Build DoD items. The SEM enforces these gates — it checks every DoD item and blocks the transition if anything is incomplete.

## The Build Process

I didn't one-shot the system. That isn't how this works.

Before any code was written, the system went through a structured specification process: domain research (parallel AI agents analyzing the problem space), PRD writing (one per bounded context), stakeholder review, architecture review (one-by-one Q&A loop producing ADRs for every decision), gap analysis, and finally a tagged Build Candidate — a concept I developed analogous to a release candidate, but for the *design* phase. It's a tagged commit that says "this specification is complete enough to build from."

Once the Build Candidate was tagged, implementation followed the SDLC phases: the SEM decomposed PRDs into task graphs, deployed implementation agents with watchdog quality agents running in parallel, and enforced Definition of Done gates at phase boundaries.

One choice that paid enormous dividends: since I was confident the core domain model was correct, I leveraged FastAPI's type system to auto-generate OpenAPI/Swagger documentation for all 180+ endpoints. Then I used [Orval](https://orval.dev) to auto-generate type-safe TypeScript client code and service hooks from that spec. When frontend agents went to work, none of them had to guess at API shapes, parameter types, or endpoint URLs — they just imported the generated services and used them directly. The backend was the single source of truth, and the frontend was mechanically derived from it. This eliminated an entire category of integration errors and meant that every API change automatically propagated to the frontend types.

I couldn't walk away entirely. It required babysitting — roughly half-effort for the week. Agents need guidance when they hit ambiguity, when integration points don't line up, when a design decision at the spec level doesn't translate cleanly to code. I was the human in the loop, not the human writing the code.

The result: the system works. Not "kind of works." Works well. The UI is polished. The business logic is correct. The test coverage exceeds 98%.

## Here Are Some Things I Didn't Expect

This is the part worth reading. Everything above is the success story. What follows is what I learned *despite* all that governance.

### The Modular Success Trap

Every module was correct in isolation. 98% test coverage proved it. The architecture was clean — bounded contexts, proper layer boundaries, dependency injection at the seams. And then I tried to use the system as a regular user (not the admin superuser), and things started falling apart.

The invitation approval flow didn't complete — not because the invitation service was broken or the workflow orchestrator was broken, but because the bridge between them was never built. Both modules passed all their tests.

Routes guarded themselves with `:read` permissions. Roles were assigned business capabilities (`:approve`). But nobody verified that the capabilities assigned to roles actually matched the permissions the routes required. Every component was correct per its own specification. The *intersection* was empty.

Workflows routed tasks to organizational groups. Groups could contain members. But the group the workflow expected didn't exist in the right domain. Every piece was structurally sound.

**The pattern**: unit tests validate that A works and B works, but nothing validated that A's assumptions about B are correct. Service integration tests verified the *mechanism* (A can call B) but not the *semantics* (A and B agree on what the words mean).

I completely missed the end-to-end tests. As the system was being built modularly, with each module having nothing else to talk to yet, it never occurred to me to test the integration seams that didn't exist yet. But this taught me something new and valuable. My testing taxonomy now has four levels: unit tests, integration tests, end-to-end tests, and what I'm calling "architectural invariance tests." Read on.

### Why AI Makes This Worse

This isn't a new problem — integration seam failures are as old as modular software. But AI-assisted development amplifies it in three ways.

**Velocity outpaces integration.** When agents produce 50,000 lines per day, cross-module assumptions accumulate faster than any human can track. The seams pile up silently while the tests stay green.

**Agents excel at local correctness.** Modern coding agents are remarkably good at building internally consistent modules — comprehensive tests, high coverage, clean abstractions. This creates false confidence. Everything looks complete because everything *locally* is complete.

**Agents don't share working memory.** When Agent A builds the IAM module and Agent B builds vendor management, each makes locally reasonable decisions about permission string formats. Neither is wrong. But without a shared canonical definition, they independently invent incompatible vocabularies for the same concept.

### The Detection Problem

Here's what really caught me off guard: the admin account worked perfectly. Every route rendered. Every action completed. Every workflow executed.

The failures only surfaced when I tested as a regular user — one without superuser privileges, without pre-seeded data, without bypassed permission checks.

Superuser accounts mask integration failures because they bypass permission checks entirely. Pre-seeded development data masks configuration gaps that a real deployment would need to create from scratch. Admin roles paper over capability-catalog mismatches that non-admin users hit immediately.

The lesson: **test as the user who will actually use the system, not the user who built it.**

There was a silver lining, though: when the system failed, it failed for the right reasons. The dependency-injected permission checks were all running perfectly — they correctly prevented unauthorized actions. The *mechanism* was sound. The *configuration* (which permissions mapped to which roles) was what needed fixing. That's a much better class of problem to have.

## What I'm Adding to the System

These failures weren't a process failure — they were a process *gap*. The harness was excellent at per-module quality. What it lacked was enforcement at the integration seams.

### The Architecture Invariant Registry

I'm adding a new artifact to the Build Candidate: a canonical registry of every concept that is defined in one place and reused throughout the system. Permission string formats. Entity status vocabularies. Error code families. Event type definitions. Routing identifiers.

Through further analysis, the registry evolved from a simple vocabulary list into something more rigorous: formal contracts with **preconditions, postconditions, and invariants** — Bertrand Meyer's Design by Contract applied to cross-module integration seams.

Each registry entry specifies:

- **Owner**: Which bounded context defines the concept (the provider owns the contract)
- **Preconditions**: What must be true before consuming this concept (the caller's obligation)
- **Postconditions**: What the owning module guarantees after execution (the provider's guarantee)
- **Invariants**: What must always hold across all contexts
- **Inside vs. outside**: What's the public contract (stable, versioned) vs. internal implementation (can change freely)

The dependency direction is explicit: **if A depends on B, B owns the contract and makes the rules.** This prevents the failure where consumers independently invent expectations about a provider's behavior — which is exactly how our RBAC permission vocabulary drifted.

The contracts also compose hierarchically. A platform-level guarantee is traceable down to the specific child contracts that fulfill it. If a child contract is missing or incompatible, the parent's guarantee cannot hold — and that gap is detectable at design time, not at integration time.

**At design time**, when a PRD defines a new cross-cutting concept, it enters the registry as a formal contract. Subsequent modules declare which contracts they consume and must satisfy the preconditions. If the specification uses different vocabulary or assumes different postconditions than the registry, that's a defect.

**At coding time**, the implementation agent reads the relevant contracts before building the module. After completion, a verification step checks that preconditions are satisfied at call sites, postconditions hold in the provider, and invariants are maintained everywhere. The module isn't done until it's conformant.

### End-to-End Contract Tests

The existing test infrastructure verified that modules worked internally and that service calls went to the right place. What was missing: tests that validate the full chain produces the expected outcome with a non-privileged user.

These aren't traditional integration tests. They're contract tests at the integration seams — proving that Service B actually does what Service A assumes it does, with the permissions a real user actually has.

## What I'd Tell You If You're Starting This

Build the governance first. The harness existed before the first line of application code. That ordering matters. If the governance comes after the code, it's archaeology. If it comes before, it's engineering.

Enforce mechanically, not verbally. Agent instructions are the weakest enforcement layer. Hooks that block non-compliant work are the strongest. If a rule matters, make it a hook. If it doesn't matter enough to be a hook, ask yourself if it matters at all.

Invest in the specification phase disproportionately. The week of coding was preceded by substantial specification work — research, PRDs, ADRs, gap analysis. Every ambiguity resolved before implementation is a wrong guess prevented during implementation.

Test as the user, not the builder. This one cost me debugging time. Superuser accounts are useful for development. They are actively harmful for testing.

And finally: the modules will be correct. That's the easy part now. The hard part — the part that still requires human judgment — is making sure they're correct *together*. That's the integration seam problem, and it's the frontier of AI-assisted engineering.

## Shaping the Energy Landscape

Coming back to the state space metaphor: every enforcement mechanism I described is a constraint that eliminates a region of the implementation space.

| Mechanism | State Space It Eliminates |
|-----------|--------------------------|
| Domain briefing + research reports | Implementations that solve the wrong problem |
| PRDs with numbered business rules | Implementations that miss requirements |
| ADRs for every architectural decision | Implementations where agents guess differently |
| `check-test-exists.sh` hook | Code without test coverage (untested state space) |
| `check-invariants.sh` hook | Code that violates project rules |
| `verify-green.sh` stop hook | Code with failing tests, type errors, or lint violations |
| Watchdog agents (reviewer, security) | Code with quality or security issues |
| Phase gates with DoD checklists | Premature transitions that skip verification |
| Domain fidelity standard | Implementations built on wrong domain understanding |
| Layer boundary standard | Architectural violations (reverse dependencies, skip-layer imports) |
| Auto-generated TypeScript SDK from OpenAPI | Frontend agents guessing at API shapes, parameter types, endpoint URLs |
| **Invariant registry with DbC contracts** *(new)* | Cross-module vocabulary drift, broken assumptions at integration seams, compositional hierarchy gaps |

Each row narrows the space. Together, they create a valley — an attractor in the implementation space that pulls agents toward correct, well-tested, well-architected solutions. The agents aren't constrained in what they can *build*. They're constrained away from what they shouldn't build.

And that's why 270,000 lines in a week doesn't have to be a pile of crap. Not because the agents are superhuman. Not because I'm superhuman. But because the governance structure, the domain-driven design discipline, the research pipeline, the enforcement hooks, the watchdog agents, the phase gates, and the specification artifacts all work together to keep the system in the valley — sampling from the region of state space where good implementations live.

The data models are in proper normal form in Postgres. The transactional outbox pattern is in place. There are a dozen services running in Docker Compose locally. The test coverage exceeds 98%. The types check. The lint passes. The UI is polished. The business logic reflects the domain, not the legacy system.

The good news: I continue to successfully modify the system hour after hour, day after day. The foundation holds. Here's my status line from today:

[[INSERT IMAGE]]

I've never come close to anything like this before. And I'm just getting started.

---

## The Bigger Picture: A Strategic Migration Pattern

Beyond the engineering story, this project demonstrates something with significant business implications: a repeatable pattern for migrating organizations off of Salesforce onto a custom application stack — rapidly, reliably, and with full architectural discipline.

The chain of work described in this article — archaeological discovery of the existing Salesforce org, domain model extraction from actual data, structured specification, disciplined implementation — isn't just how I built one platform. It's a strategic playbook. The same process that produced 270,000 lines of well-tested code in a week also produced the research artifacts, migration strategies, and organizational design documents that make the transition viable as a business operation.

For organizations that have outgrown Salesforce — or never fit it well in the first place — this approach offers a path from "trapped in a platform we've customized beyond recognition" to "running on a system built for exactly what we do."

If that's a problem you're facing, [I'd like to hear from you](https://heavychain.org).

---

## Where This Is Going

I'm not the only person thinking about this. I've started a community of engineers exploring these ideas, and I see more people writing about agentic engineering patterns every week. The field is moving fast.

My next step is to take the harness described in this article and give it an actual runtime — a system that orchestrates an arbitrary set of underlying agents through a formal execution model. I've looked at other approaches (Griptape, multi-agent frameworks with elaborate mythological naming conventions), and while they're in the right neighborhood, I think the metaphors are wrong. This isn't a pantheon of autonomous gods. It's a software engineering organization.

You're the CTO. You dispatch work to a VP of Engineering, who breaks it down and dispatches to directors, who break it down and dispatch to engineering managers, who dispatch to individual contributors. The hierarchy exists because it works — it's how humans have successfully managed complex engineering at scale for decades. The agents aren't peers in a flat network. They have roles, reporting lines, escalation paths, and domains of authority. The SEM orchestrator in my harness is already structured this way, and the natural evolution is to make that structure a first-class runtime rather than a set of conventions encoded in markdown files.

I'd be surprised if the leading AI companies aren't developing their own versions of this. The pattern is too obvious and too valuable to stay in the hands of individual practitioners forever. But for now, this is where I am — building in the open, learning as I go, and sharing what works.

If you're working on similar problems, [I'd like to compare notes](https://heavychain.org).
