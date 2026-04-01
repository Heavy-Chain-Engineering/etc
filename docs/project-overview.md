# ETC System Engineering — Full Project Context

**Author**: Jason Vertrees + Claude
**Date**: 2026-03-10
**Purpose**: Complete context document for sharing with other Claude Code sessions. Captures what this project is, what it's achieved, where it's going, and what's unresolved.

---

## 1. What This Project IS

ETC (Engineering Team, Claude) is a **synthetic AI engineering organization** — a system that replicates the discipline of a well-run human software team, applied to Claude Code and other AI coding assistants.

It's not a library. It's not a framework. It's an **operating system for AI-assisted software development**: agent definitions, engineering standards, enforcement hooks, a process methodology, and (eventually) a durable orchestration platform.

The core thesis: AI coding assistants are capable enough to build production software, but only if you give them the same structure that makes human engineering teams effective — role specialization, quality gates, process discipline, domain fidelity, and mechanical enforcement of standards.

---

## 2. What We've Built (v1 — The Harness)

### Intelligence Layer (validated, reusable)
- **23 agent definitions** (`agents/*.md`) — role-specific agents covering the full SDLC: orchestration (SEM), spec/design (PM, PO, architect, UX/UI designers, domain-modeler, researcher), build (backend/frontend developers, devops, code-simplifier, project-bootstrapper), quality gates (verifier, code-reviewer, security-reviewer, architect-reviewer, spec-enforcer), and analysis (process-evaluator, technical-writer)
- **17 engineering standards** across 6 categories (process, code, testing, architecture, security, quality) — these are MANDATORY reading for agents before they produce output
- **8-phase SDLC lifecycle** (Bootstrap, Spec, Design, Decompose, Build, Verify, Ship, Evaluate) with Definition of Done gating at each transition
- **4 TDD enforcement hooks** (check-test-exists, mark-dirty, verify-green, check-invariants) + 2 git hooks — mechanical enforcement, not agent self-discipline
- **Domain fidelity standard** — domain briefing documents, anti-pattern catalogs, cognitive reframe for re-engineering projects
- **Project classification types** (greenfield, brownfield, re-engineering, lift-and-shift, consolidation) that change how every agent interprets source material

### Installation
`install.sh` copies agents, standards, hooks, and SDLC tracker to `~/.claude/` and wires hook triggers into settings. Two-layer architecture: user-level components shared across all projects, project-level components per-repo.

### The SEM Pattern
A single Software Engineering Manager agent owns the SDLC lifecycle, deploys agent teams, and gates phase transitions on Definition of Done checklists. The SEM never writes code — it only makes decisions and delegates. This is constraint C1 and it's non-negotiable.

---

## 3. Field Testing Results

### Projects Tested
| Project | Result | Key Learning |
|---------|--------|-------------|
| **getting-started** (SDLC dashboard) | 31 min, 36 tests, 96% coverage, fully autonomous | Proved the harness works for simple projects |
| **Project Falcon** (compliance engine) | Completed with issues found in review | Exposed need for domain fidelity standard (OPA/Rego misunderstanding) |
| **Acme Corp** (vendor management platform) | 3 rounds of research required | Exposed every orchestration limitation — volume trap, platform artifacts as domain truths, flat fan-out insufficient, SEM context erosion |

### What the Intelligence Layer Gets Right
- Agent specialization works — bounded responsibility, clear inputs/outputs
- Phase gates with DoD prevent premature transitions
- TDD hooks enforce test-first mechanically
- Domain fidelity standard catches category errors before they propagate
- Progressive disclosure (reading context in order) measurably improves output quality
- Iterative hardening — every failure becomes a harness improvement

### What Claude Code's Orchestration Gets Wrong
These are fundamental limits of Claude Code as an orchestrator:
1. No persistent orchestration state (conversations get compacted, sessions end)
2. No event-driven coordination ("when Layer 1 completes, trigger Layer 2" requires polling)
3. No mid-execution guardrail enforcement (rules are advisory, not enforced)
4. No shared working memory between agents during execution
5. No cross-session continuity (closing laptop kills orchestration)
6. Fan-out ceiling (~15 parallel agents before coordination overhead dominates)
7. No backpressure or automatic retry

---

## 4. The Vision: Industrialized System Synthesis (ISS)

The long-term vision goes beyond a coding harness:

**The biological parallel:**
- DNA (genotype) = Declarative system spec
- Gene expression machinery = Agent swarms (spun up to reconcile state, not permanent residents)
- Cells = Components/services (interfaces hiding implementation)
- Organism (phenotype) = Running system
- Natural selection = Tests, observability, user feedback

**Key insight**: Agents are the PROCESS, not the ARCHITECTURE. They come into existence in response to a spec delta, do their work, and the system converges. The spec is the control plane.

**The notation problem**: Natural language specs are too ambiguous. Code is too implementation-bound. We need something in between — an ambiguity gradient that's precise at execution depth, strategically ambiguous at communication depth, and functions as a boundary object across product, engineering, ops, and agent viewpoints.

This vision is documented in `docs/vision/VISION.md`. It's research-stage, not implemented.

---

## 5. The Process: From Idea to Build Candidate

We developed and documented a repeatable process for AI-assisted architecture:

```
RESEARCH → PRDs → STAKEHOLDER REVIEW → ARCHITECTURE REVIEW → GAP ANALYSIS → BUILD CANDIDATE
```

### Key Process Innovations
- **Fan-out/reduce research**: Parallel AI agents with anti-pattern constraints, followed by synthesis
- **Cognitive reframe for re-engineering**: Three questions that prevent agents from copying legacy patterns: (1) What BUSINESS NEED does this serve? (2) What LIMITATION forced this pattern? (3) How would we model this from scratch?
- **Anti-pattern catalog with WRONG/RIGHT examples**: Agents pattern-match on concrete examples better than abstract descriptions
- **One-at-a-time architecture Q&A loop**: AI presents context + options + opinion, human decides, AI writes ADR. Focused attention, no decision fatigue.
- **Gap analysis before implementation**: Cheap (~30 min) and always finds blockers you thought you'd covered

This process was battle-tested on Acme Corp: 17 research reports, 10 PRDs, 34 ADRs, traceability matrix, gap analysis, build phases plan. The result was a tagged Build Candidate where every architectural decision was explicit and implementation agents could start coding without guessing.

Full process doc: `docs/process/from-idea-to-build-candidate.md`

---

## 6. v2 — The Orchestration Platform (IN PROGRESS)

### The Problem
The v1 harness validated the intelligence layer but exposed the orchestration layer as inadequate. v2 aims to replace Claude Code's conversation-based orchestration with something durable.

### Four Non-Negotiable Constraints
- **C1**: Single SEM orchestrator — delegates everything, never writes code
- **C2**: SEM context is sacred — stateless between decisions (each decision is a fresh, scoped context load, not a growing conversation)
- **C3**: Restart from wherever we left off — all state in Postgres, crash recovery is trivial
- **C4**: Arbitrary recursive decomposition — execution graphs are trees, not flat layers

### Current Status: Back to Phase 1
We have an existing v2 PRD (`docs/vision/v2-orchestration-platform-prd.md`) and 16 Python modules in `platform/src/etc_platform/`. But:
1. The v2 PRD assumed raw Claude API billing — Jason wants to use his Claude Code subscription instead
2. The Claude Agent SDK arrived, potentially changing the build strategy
3. Agent Teams (Claude Code feature) are now available for parallel coordination
4. The PRD is an architecture sketch, not bounded-context PRDs with numbered business rules, entity schemas, and acceptance criteria

**We're resetting to Phase 1 of the Build Candidate process** and doing it to the Acme Corp standard: proper research, proper PRDs, proper ADRs, gap analysis, build phases with I/O criteria.

### The Billing Constraint (Critical)
- **Agent SDK requires API key billing** — cannot use Claude Code subscription
- **Agent Teams work on subscription** but are experimental, lack Postgres persistence, can't nest
- **Subagents work on subscription** but are sequential, no inter-agent communication
- This constraint fundamentally reshapes the v2 architecture. The original PRD's model (a Python process making Claude API calls) may not be the right approach.

### The Open Question
Should v2 be:
**(A)** A hardened v1 — Claude Code subscription, Agent Teams + subagents, state in files/git, human in the loop (this is what actually worked for Acme Corp's 200K+ lines)
**(B)** A hybrid — subscription for interactive work, small API budget for autonomous fan-out bursts
**(C)** The original v2 PRD — full API billing, Postgres persistence, autonomous orchestration

This decision hasn't been made yet. It's the first architecture decision (ADR-01) once we have the research.

---

## 7. What This Repo Contains

```
etc-system-engineering/
├── agents/              # 23 agent .md definitions (SDLC roles)
├── standards/           # 17 engineering standards (6 categories)
├── hooks/               # TDD enforcement scripts + git hooks
├── .sdlc/               # SDLC workflow tracker (state machine, DoD)
├── platform/            # v2 orchestration engine (16 Python modules, UNDER REVIEW)
├── docs/
│   ├── vision/          # ISS vision doc + v2 PRD
│   ├── process/         # Build Candidate process + PRD writing guide
│   ├── research/        # Agent hardening, recursive decomposition, SHACL, governance
│   ├── plans/           # Implementation plans, design notes
│   └── lessons-learned-v1.md
├── getting-started/     # Onboarding exercise (dashboard built in 31 min)
├── scripts/             # .meta/ reconciliation utilities
├── install.sh           # Bootstrap installer
└── settings-hooks.json  # Hook wiring template
```

---

## 8. Canonical Terminology

| Term | Definition |
|------|-----------|
| **SEM** | Software Engineering Manager — the sole orchestrator agent. Delegates everything, writes nothing. |
| **Execution graph** | A tree of nodes representing work to be done. Nodes can be leaf (one agent task), composite (contains sub-nodes), or reduce (synthesis after fan-out). |
| **Phase gate** | A Definition of Done checkpoint between SDLC phases. All items must be met before transition. |
| **Guardrail** | An enforcement rule checked against agent output. Advisory in v1 (agent instructions), middleware in v2 (automated checks). |
| **Domain briefing** | A foundational document that all agents read first, establishing domain understanding, anti-patterns, and canonical vocabulary. |
| **Build Candidate** | A tagged commit where the specification is complete enough to build from. If an implementation agent needs to guess, you're not done. |
| **Anti-pattern catalog** | WRONG/RIGHT examples that agents pattern-match against. Critical for re-engineering projects where old-system patterns must not be reproduced. |
| **Fan-out/reduce** | Parallel agent deployment (fan-out) followed by synthesis (reduce). The basic orchestration primitive. |
| **Recursive decomposition** | Breaking work into sub-graphs of arbitrary depth until each leaf fits in one agent's context. C4 constraint. |
| **Intelligence layer** | Agent prompts, standards, domain fidelity rules — the WHAT of agent behavior. Validated and reusable. |
| **Orchestration layer** | State management, agent coordination, guardrail enforcement — the HOW of running agents. What v2 replaces. |
| **ISS** | Industrialized System Synthesis — the long-term vision where specs are declarative control planes and agent swarms reconcile running systems to match. |

---

## 9. Key Design Principles

1. **"A spec is only a wish if there's no way to enforce it."** — Guardrails must be middleware, not instructions.
2. **"If an implementation agent would need to guess, you're not done."** — The Build Candidate test.
3. **"The project type determines how EVERY agent interprets source material."** — A Salesforce export in a re-engineering project is an anti-pattern catalog. The same export in a lift-and-shift is the spec.
4. **"AI proposes, human disposes."** — Strong AI opinions, human decisions. Not a democracy, a consultation.
5. **"Wrong domain understanding → wrong everything downstream."** — Domain fidelity is the foundation, not a nice-to-have.
6. **"Agents are the process, not the architecture."** — They come into existence, do work, and the system converges. They're gene expression machinery, not cells.

---

## 10. What We Need Help With

We're looking for observations on:
- Whether the v2 architecture should stay as a Postgres-backed orchestrator (API billing) or evolve into a hardened v1 (subscription, human in the loop)
- How the Build Candidate process could be improved based on real-world usage
- Whether the agent definitions, standards, and hooks are the right level of abstraction
- What's missing from the process that would prevent scaling to larger projects
- How the ISS vision connects to practical near-term work
