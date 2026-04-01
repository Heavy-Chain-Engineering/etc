# Conversation Summary: Context Hibernation & Fractal Delegation
**Date**: 2026-03-10
**Author**: Jason Vertrees (with Claude, claude.ai)
**Purpose**: Exhaustive handoff document for continuation in Claude Code. Captures all observations, named patterns, architectural insights, open decisions, and planned work products from this session.

---

## 1. The Triggering Achievement

Jason completed a 3-day agentic coding session producing:
- 200,000+ lines of code, greenfield to production-grade
- 98% test coverage, 3,000+ tests
- 180 API routes
- 31 custom email templates
- Temporal workflow integration
- Full Docker Compose stack with observability
- Distributed outbox patterns
- React / DaisyUI UI skeleton (~10% wired up)
- Spec was 600 pages long

This was accomplished entirely via agentic AI engineering (Claude Code). The session surfaced two major architectural insights now named and formalized below.

---

## 2. Named Pattern: Context Hibernation

### What It Is
A deliberate protocol for preserving agent continuity across context compaction events.

**The problem it solves**: In large-scale projects, the Claude Code main thread accumulates history (project state + task history + post-compaction state) that grows unbounded. Compaction degrades continuity over time as important context gets squeezed out.

**The protocol**:
1. Before compaction is triggered, the agent writes a verbose hibernation record to disk — as detailed as needed, unlimited size
2. The hibernation record captures: what was done, current state, open decisions, next steps, relevant file paths, key constraints
3. During/after compaction, the agent wakes with a *minimal* payload — just enough to pick up where it left off
4. The asymmetry is the key insight: **write verbosely, wake minimally**

**Why it works**: The main context stays clean for far more iterations. Continuity across compaction events is structurally guaranteed, not hoped for. The agent isn't managing a growing history — it's managing a clean handoff record.

**Analogy**: True hibernation, not checkpointing. The agent externalizes its working memory, sleeps, and wakes lean.

**Relationship to ETC v2 Constraint C2**: C2 states "SEM context is sacred — stateless between decisions." Context Hibernation is the *mechanism* that implements C2. The SEM doesn't accumulate history across decisions; each decision is preceded by a structured wake from the hibernation record. C2 was the requirement; Context Hibernation is the implementation.

---

## 3. Named Pattern: Fractal Delegation

### What It Is
The recursive application of Context Hibernation through a hierarchy of agents, where each node in the tree protects its own context by delegating to sub-agents rather than executing directly.

**The protocol**:
1. The top-level orchestrator (SEM / CTO-equivalent) receives a large task
2. It does NOT execute the work — it delegates to a worker agent
3. The worker agent evaluates: "Can I do this directly within my context budget?"
   - **Yes**: Execute ephemerally, produce output, die off
   - **No**: Become the orchestrator for this subtree — apply Context Hibernation to protect your own context, decompose the work, fan out to sub-workers
4. Sub-workers apply the same decision recursively
5. Recursion terminates naturally at leaves (tasks small enough to execute directly)

**Why "Fractal"**: The pattern is self-similar at every level of the tree. Each node behaves identically: protect context, delegate or execute. The org chart metaphor maps precisely:
- CTO → strategic delegation only (Jason / main orchestrator)
- VP Engineering → breaks large initiatives into bounded programs
- Director → decomposes programs into team-level work
- Engineering Manager → owns sprint-level delivery
- IC → leaf node, executes directly

**Key constraint**: The main orchestrator thread is NEVER used for execution. Its sole purpose is dispatch and context protection. This is non-negotiable (maps to ETC Constraint C1: SEM never writes code).

**Relationship to ETC v2 Constraint C4**: C4 requires "arbitrary recursive decomposition — execution graphs are trees, not flat layers." Fractal Delegation is the operational protocol that makes C4 work. The doc had the constraint without the mechanism; Fractal Delegation is the mechanism.

---

## 4. How These Patterns Resolve ETC v2's Open Architecture Question (ADR-01)

The ETC context document frames ADR-01 as a choice between:
- **(A)** Hardened v1 — Claude Code subscription, Agent Teams + subagents, state in files/git
- **(B)** Hybrid — subscription for interactive, API budget for autonomous fan-out
- **(C)** Full v2 PRD — API billing, Postgres persistence, autonomous orchestration

### The New Analysis
The v2 PRD was designed to solve context erosion in the SEM. But Context Hibernation solves context erosion *at the protocol level*, without Postgres, without API billing, without a custom runtime.

**Implication**: Option A (hardened v1) is architecturally sufficient for the orchestration problem. The orchestration IS the file system. Postgres was solving a problem that's better solved with protocol discipline.

This does NOT mean no runtime is needed — see Section 6. But the motivation for a heavy runtime changes significantly.

**Recommendation going into ADR-01**: Start with Option A hardened by Context Hibernation + Fractal Delegation protocols. Defer Option C unless subscription-based orchestration proves insufficient at scale.

---

## 5. State of the Art — What Else Exists

### Partial prior art (confirmed during conversation):
- **LangGraph**: Stateful agent graphs with checkpointing. Closest analog to Context Hibernation at the infrastructure level. But it's framework-locked, heavier, and doesn't encode the *deliberate cognitive intent* (verbose write / minimal wake asymmetry).
- **AutoGen / CrewAI / Swarm**: Multi-agent delegation with ad-hoc context management ("summarize when full"). Reactive, not first-class.
- **OpenAI Swarm**: Lightweight, explicit handoffs. Worth studying for the delegation layer.
- **Google Agent Development Kit (ADK)**: New, first-class hierarchical agent trees, native Gemini support. Relevant since Jason wants LLM agnosticism.
- **Hierarchical RL agents** (academic): Recursive decomposition but not applied to LLM context budgeting.
- **Claude Code subagent spawning**: Native task delegation, but no formalized context protection layer on top.

### What is genuinely novel in Jason's formulation:
1. Context Hibernation as a *deliberate, asymmetric* protocol — not just compaction
2. Fractal Delegation as *recursive application* of that protocol at every delegation boundary
3. The org-chart as a *design constraint* (not just a metaphor) — enforcing cognitive scope limits that mirror why real orgs have hierarchy
4. Pre/post hooks as *culture invariants* that don't degrade with scale — this framing is new and precise

---

## 6. Runtime Architecture — What's Actually Needed

Even with Context Hibernation replacing the Postgres-backed orchestrator, a thin runtime layer is still warranted. Here's what it needs to do:

### Required Runtime Responsibilities:
1. **Agent Lifecycle Management** — spawn, running, hibernating, waking, terminated states
2. **Context Hibernation Protocol** — trigger conditions, write format standardization, wake payload construction
3. **Memory Store** — structured files with a schema (versioned, queryable — NOT freeform markdown)
4. **Task Graph** — inspectable DAG of work with delegation boundaries marked; not implicit in spawning order
5. **LLM Adapter Layer** — abstract interface for Claude Code (OAuth/subscription), Anthropic API, Gemini API. This is the primary reason a runtime is needed.
6. **Hook Engine** — fire pre/post hooks at hibernation/wake boundaries in addition to task boundaries

### LLM Adapter Notes:
- Claude Code Max subscription uses OAuth, not API key billing — should be used where possible
- Agent SDK requires API key billing — cannot use subscription
- Gemini API is a completely different invocation model
- The adapter layer is what enables LLM agnosticism and protects the rest of the system from provider-specific concerns

### What the Runtime Does NOT Need:
- Postgres (file system + git is sufficient for state at v1 scale)
- A heavy orchestration framework (LangGraph etc.)
- Always-on daemon processes (agents are ephemeral by design)

---

## 7. Pre/Post Hook Integration — Expanded Scope

ETC v1 already has 4 TDD enforcement hooks (check-test-exists, mark-dirty, verify-green, check-invariants) + 2 git hooks.

**New insight from this session**: Hooks should fire at hibernation/wake boundaries, not just task boundaries. Specifically:
- **Pre-hibernate hook**: Validate hibernation record completeness before write
- **Post-wake hook**: Verify agent has loaded required context before executing
- This extends the "culture invariants don't degrade with scale" property to the hibernation lifecycle

---

## 8. Documents to Produce (Planned Work)

Three documents were agreed upon as the immediate next work products:

### Doc 1: `docs/research/context-hibernation-fractal-delegation.md`
- Full formalization of both patterns with precise definitions
- Protocol specifications (hibernation record format, wake payload spec)
- Decision tree for "execute vs. delegate" (the Fractal Delegation leaf condition)
- Org-chart mapping with role-to-agent correspondence
- Relationship to existing ETC constraints (C1, C2, C4)
- Prior art comparison (LangGraph, ADK, Swarm, AutoGen)
- Named vocabulary integrated into ETC canonical terminology

### Doc 2: `docs/research/adr-01-architecture-decision.md`
- Formal ADR resolving the Option A/B/C question
- Decision: Option A (hardened v1) with Context Hibernation + Fractal Delegation
- Rationale: context erosion solved by protocol, not infrastructure
- Consequences: runtime scope narrows to LLM adapter + lifecycle management
- Alternatives considered and rejected

### Doc 3: `docs/plans/v2-revised-implementation-plan.md`
- Updated implementation plan replacing Postgres orchestration with protocol-based orchestration
- Phased: validate core Context Hibernation loop first, then add Fractal Delegation, then LLM adapter
- Hook integration points for hibernation lifecycle
- Memory schema design (structured, versioned, queryable)

---

## 9. Open Questions / Unresolved Decisions

1. **Memory schema format**: What's the right structure for hibernation records? Needs to be machine-readable (for runtime), human-readable (for debugging), and versionable. JSON? YAML? Structured markdown with frontmatter?

2. **Task graph representation**: What format for the execution tree? Needs to be inspectable mid-run. JSON DAG? YAML? Live file updated as delegation happens?

3. **Leaf condition formalization**: How does an agent *determine* whether it can execute directly vs. must delegate? Token budget estimate? Task complexity heuristic? Explicit size classification?

4. **Hook trigger mechanism at hibernation boundaries**: How does the hook engine know a hibernation event is occurring? Signal from the agent? File system watch? Explicit hook invocation in the hibernation protocol?

5. **LLM adapter interface**: What's the minimal abstract interface that covers Claude Code OAuth, Anthropic API, and Gemini? Tool call abstraction? Streaming? Context window reporting?

6. **Gemini integration specifics**: Google ADK is relevant — evaluate whether it should be the Gemini adapter layer or whether a direct Gemini API wrapper is preferable.

---

## 10. Updated Canonical Terminology (Additions to ETC Glossary)

| Term | Definition |
|------|-----------|
| **Context Hibernation** | A deliberate protocol where an agent writes a verbose state record to disk before context compaction, then wakes with a minimal payload. Asymmetric by design: write verbosely, wake minimally. Implements ETC Constraint C2. |
| **Hibernation Record** | The structured file written during a Context Hibernation event. Contains: work completed, current state, open decisions, next steps, relevant paths, key constraints. Verbose by design. |
| **Wake Payload** | The minimal context loaded post-hibernation to resume execution. Derived from the Hibernation Record but deliberately compressed. |
| **Fractal Delegation** | The recursive application of Context Hibernation through an agent hierarchy. Each node decides: execute directly (leaf) or become an orchestrator and protect its own context by delegating. Self-similar at every level. Implements ETC Constraint C4. |
| **Leaf Condition** | The decision gate in Fractal Delegation: can this task be completed within a single agent's context budget? If yes, execute. If no, delegate. |
| **Synthetic Org** | The organizational structure emergent from Fractal Delegation. Maps to: CTO (main orchestrator) → VP Eng → Director → EM → IC (leaf agent). Each level holds only its own cognitive scope. |
| **LLM Adapter** | The abstraction layer that normalizes Claude Code (OAuth), Anthropic API (key billing), and Gemini API into a consistent interface for the runtime. Primary reason a thin runtime is warranted. |

---

## 11. Immediate Next Steps for Claude Code Session

**First task**: Create the three documents listed in Section 8, starting with Doc 1 (research formalization). Doc 1 is the research artifact that informs the ADR and the plan.

**Starting command for Claude Code**:
> "Read `docs/research/context-hibernation-fractal-delegation-summary.md` [this file]. Your first task is to produce Doc 1: `docs/research/context-hibernation-fractal-delegation.md` — the full formalization of both patterns per Section 8. Write to publishable research depth. Then await review before proceeding to ADR-01."

**Key files to reference in the Claude Code session**:
- `docs/vision/VISION.md` — ISS vision
- `docs/vision/v2-orchestration-platform-prd.md` — existing v2 PRD (now being revised)
- `docs/lessons-learned-v1.md` — v1 field testing results
- `agents/*.md` — 23 agent definitions
- `standards/` — 17 engineering standards
- `.sdlc/` — SDLC lifecycle tracker

---

*This document is itself an example of Context Hibernation — it externalizes the full working memory of the claude.ai session so the Claude Code session can wake lean with complete continuity.*

