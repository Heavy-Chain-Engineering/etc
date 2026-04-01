# Lessons Learned — v1 Coding Harness (Claude Code)

**Date:** 2026-02-27
**Author:** Jason Vertrees + Claude
**Projects tested:** getting-started (SDLC dashboard), Project Falcon (compliance engine), Acme Corp (vendor management platform)

## Executive Summary

The v1 coding harness — 23 agents, 8 SDLC phases, 3 hooks, standards, and an SDLC tracker — successfully demonstrated that a structured agent team can execute a full software development lifecycle. The getting-started project was built autonomously in 31 minutes (36 tests, 96% coverage). But real-world testing on Project Falcon and Acme Corp exposed fundamental limitations in Claude Code's orchestration model that require a purpose-built platform to overcome.

**Key insight:** The harness validated the INTELLIGENCE layer (agent prompts, domain fidelity, process standards, quality gates). What it exposed as inadequate is the ORCHESTRATION layer (state management, agent coordination, guardrail enforcement, multi-session persistence).

---

## What Worked

### 1. Agent Specialization
Decomposing the SDLC into role-specific agents (PM, Architect, Developer, Reviewer, etc.) worked well. Each agent has a bounded responsibility and clear inputs/outputs. The agent prompts are reusable regardless of orchestration substrate.

### 2. Phase Gates with Definition of Done
The SDLC tracker + DoD templates prevented premature phase transitions. The SEM checking "are all DoD items met?" before allowing transition caught incomplete work.

### 3. TDD Hooks
Pre/post tool-use hooks that enforce test-first development worked reliably. The hooks fire on every Edit/Write operation, which means TDD is enforced mechanically, not by agent self-discipline.

### 4. Domain Fidelity Standard
After the OPA/Rego incident (Project Falcon), the domain fidelity standard — domain briefing documents, mandatory verification step, cascade risk awareness — caught a category of errors that would otherwise propagate through every downstream phase.

### 5. Progressive Disclosure
Reading context in order (domain briefing → domain context → project context → research request → source material) measurably improved agent output quality compared to dumping everything at once.

### 6. Iterative Hardening
Every real-world failure became a harness improvement within the same session:
- SEM ran uvicorn directly → Verify phase + Docker Compose guardrails
- Researcher misunderstood OPA/Rego → Domain fidelity standard
- PRD missed multi-tenancy → Common concerns checklist
- Research overwhelmed by scope → Recursive decomposition pattern
- Researchers copied Salesforce patterns → Project classification + source material triage

---

## What Failed (and Why)

### 1. The Volume Trap — Researchers Drowned in Implementation Artifacts
**Project:** Acme Corp
**What happened:** 10 source code repos + Salesforce export = massive volume of implementation artifacts. A 66-row workflow spreadsheet = the actual business truth. Researchers gravitated toward the largest corpus and modeled Salesforce's data structures instead of the business workflows.
**Root cause:** No source material triage. All source material treated as equal. Volume determined priority, not relevance.
**Fix applied:** Project classification + source material triage as mandatory pre-research step. "The volume trap" warning in researcher agent.
**Lesson:** Source material priority must be explicitly set by a human before any research begins. Agents cannot determine what matters from volume alone.

### 2. Platform Artifacts Mistaken for Domain Truths
**Project:** Acme Corp (Rounds 1 and 2)
**What happened:** Researchers read Salesforce exports and faithfully reproduced SF patterns — boolean flag sets, hardcoded enums, fixed queue types, 1:1 permission mappings. This was the opposite of the project goal (re-engineer away from SF limitations).
**Root cause:** No project type classification. Agents didn't know this was a re-engineering project where old-system artifacts are anti-patterns.
**Fix applied:** 5 project classification types that change how agents interpret source material. Anti-pattern catalog pattern. Three design mindset questions for re-engineering projects.
**Lesson:** "What kind of project is this?" is the single most important question. A re-engineering project and a lift-and-shift read identical source material with opposite conclusions.

### 3. Missing Core Documents
**Project:** Acme Corp Round 1
**What happened:** Missed the 66 CX workflow spreadsheet entirely. This document described the manual operational workflows that the SaaS platform needed to automate — it was the most important input in the corpus.
**Root cause:** No structured source material inventory. Researchers found what they found. A spreadsheet buried in a docs/ folder was easy to miss among 10 repos.
**Fix applied:** Source material inventory as a mandatory pre-research step with human validation of completeness and priority.
**Lesson:** A human doing a 5-minute inventory of "what source material do we have and what's most important?" prevents days of wasted research.

### 4. Flat Fan-Out Insufficient for Complex Domains
**Project:** Acme Corp
**What happened:** The domain had multiple analysis dimensions — 10 bounded contexts AND 66 CX workflows AND a legacy migration concern. A single fan-out level couldn't cover all dimensions. Required 3 layers: domain research → CX workflow analysis → synthesis.
**Root cause:** Only one fan-out/reduce pattern. No recursive decomposition.
**Fix applied:** Pattern 6 (Recursive Decomposition) with multi-layer topologies, sequential inter-layer execution, parallel intra-layer execution, and review checkpoints at boundaries.
**Lesson:** For complex domains, one pass of parallel analysis is not enough. The SEM needs to assess how many dimensions a problem has and build a multi-layer topology.

### 5. SEM Context Window Erosion
**What happened:** By the time the SEM reached Build phase, it had lost nuance from Spec phase decisions due to context compaction. Earlier design rationale and trade-offs were summarized away.
**Root cause:** The SEM's "memory" is a conversation that gets compacted. State files capture what was decided but not why.
**Fix applied:** (Partial) tracker.py + state.json persist phase state. But decision rationale is still lost.
**Lesson:** Orchestration state needs durable persistence that survives context compaction and session boundaries. This is a fundamental limitation of Claude Code's conversation model.

### 6. No Mid-Execution Guardrail Enforcement
**What happened:** Domain fidelity and anti-pattern rules are written in agent prompts as "MANDATORY" steps. But nothing prevents an agent from ignoring them. The SEM only discovers violations when it reads the final output.
**Root cause:** Claude Code has hooks for tool use (TDD works because it hooks Edit/Write) but not for agent reasoning. You can't hook on "agent is about to model a data structure" and check it against the anti-pattern catalog.
**Fix applied:** (None in v1) The Acme Corp research plan included the anti-pattern catalog in agent prompts, but enforcement is still advisory.
**Lesson:** "A spec is only a wish if there's no way to enforce it." Guardrails must be middleware that checks outputs, not instructions that agents may or may not follow.

### 7. No Cross-Agent Knowledge Sharing During Execution
**What happened:** Research agents in a fan-out each read source material independently. Agent R03's entity model isn't visible to Agent R13 during R13's execution. Conflicts and inconsistencies are only discovered at synthesis time.
**Root cause:** Agents communicate through files on disk, written when they complete. There's no shared working memory during execution.
**Fix applied:** (None in v1) The synthesis agent resolves conflicts, but that's reactive.
**Lesson:** Agents need a shared knowledge graph or queryable state that updates as they work, not just file outputs after completion.

### 8. Manual Orchestration for Complex Topologies
**What happened:** The Acme Corp 3-layer research topology was designed and written by the human, not by the SEM. The SEM can execute a simple fan-out but can't assess a 50+ file corpus, classify it across dimensions, and produce a multi-layer research plan.
**Root cause:** The SEM would burn its context window just doing the assessment. The cognitive load of "read everything, classify it, design a topology" exceeds what one agent can do in one conversation.
**Fix applied:** (Partial) Project Intake formalizes the process, but the human still does the thinking.
**Lesson:** Research plan generation for complex domains needs to be a first-class capability of the orchestration layer, not a prompt in the SEM.

---

## Fundamental Limits of Claude Code as Orchestrator

These are not fixable within Claude Code's architecture:

1. **No persistent orchestration state.** Conversations get compacted. Sessions end. The SEM forgets.
2. **No event-driven coordination.** "When all Layer 1 agents complete, trigger Layer 2" requires polling, not events.
3. **No mid-execution intervention.** Can't inject guardrails while an agent is running (only before or after).
4. **No shared working memory.** Agents are isolated. No real-time knowledge sharing.
5. **No cross-session continuity.** Closing the laptop kills the orchestration. Resuming means re-bootstrapping.
6. **Fan-out ceiling.** ~10-15 parallel agents before coordination overhead dominates.
7. **No backpressure or retry.** Failed agents aren't automatically retried. No circuit breaking.

---

## What We're Taking to v2

### Intelligence Layer (validated, reusable)
- 23 agent system prompts (role definitions, heuristics, boundaries)
- 8-phase SDLC model with Definition of Done
- Domain fidelity standard and domain briefing pattern
- Project classification types and source material triage
- Progressive disclosure for context loading
- Anti-pattern catalog pattern for re-engineering projects
- Common architectural concerns checklist
- Research report and PRD output formats
- T-shirt sizing and velocity metrics
- Recursive decomposition topology patterns

### Orchestration Layer (needs replacement)
- Phase state machine → Postgres with durable execution graphs
- Agent deployment → Claude API calls managed by a proper job scheduler
- Agent signaling → Postgres LISTEN/NOTIFY (or Redis Streams at scale)
- Guardrail enforcement → Middleware that checks outputs before acceptance
- Cross-agent knowledge → Shared queryable state updated during execution
- Multi-session persistence → Durable state that survives any session boundary
- Research plan generation → First-class orchestration capability

---

## Metrics from v1

| Project | Phases | Tasks | Tests | Coverage | Duration | Rounds |
|---------|--------|-------|-------|----------|----------|--------|
| getting-started | 7/7 | 29/29 | 36 | 96% | 31 min | 1 |
| Project Falcon | 7/7 | — | — | — | ~2 hrs | 1 (issues found in review) |
| Acme Corp (research) | Spec (partial) | 16 agents | — | — | ~3 sessions | 3 rounds required |

---

## Key Quotes (Design Principles for v2)

> "A spec is only a wish if there's no way to enforce it."

> "Research and specification exist to establish 100% fidelity to the domain and model — NOT to rush to implementation."

> "Source documents describe business INTENT, not implementation patterns. Salesforce's booleans, enums, and fixed queues are artifacts of SF's platform constraints, not domain truths."

> "The volume trap: implementation artifacts are typically the LARGEST corpus but the LEAST important for design."

> "The project type determines how EVERY agent interprets source material. A Salesforce export in a re-engineering project is an ANTI-PATTERN catalog. The same export in a lift-and-shift is THE SPEC."

> "Wrong domain understanding → wrong research → wrong PRD → wrong architecture → wrong implementation → system that solves the wrong problem."
