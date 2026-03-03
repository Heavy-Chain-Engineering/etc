# docs/

**Purpose:** Design documents, implementation plans, research reports, vision documents, and operational lessons learned that record the thinking, decisions, and field-testing results behind the ETC engineering harness and v2 orchestration platform.

## Key Components

### Root-Level Documents
- `extending-the-harness.md` -- Guide for adding new capabilities: adding agents (file format, frontmatter, examples), hardening existing agents, extending the SDLC workflow, adding hooks, standards, and invariants.
- `lessons-learned-v1.md` -- Post-mortem from v1 field testing across three projects (getting-started, Bald Eagle, VenLink). Key insight: the harness validated the intelligence layer (agent prompts, domain fidelity, quality gates) but exposed limitations in the orchestration layer (state management, agent coordination, guardrail enforcement, multi-session persistence).

### plans/
- `2026-02-25-coding-harness-design.md` -- Original design document for the industrial coding harness. Describes the synthetic engineering organization concept and its connection to Industrialized System Synthesis (ISS). Architecture decision: user-level + project template (Option B).
- `2026-02-25-phase1-user-level-platform.md` -- Implementation plan for Phase 1: user-level platform. Task-by-task plan for building agents, standards, hooks, and SDLC tracker in `~/.claude/`.
- `2026-02-28-spec-enforcer-design.md` -- Design for the dual-mode spec enforcer: a `SpecComplianceRule` guardrail (middleware pipeline) and a standalone `spec-enforcer.md` agent. Addresses spec drift, acceptance gaps, and cross-phase corruption.
- `harness-design-notes.md` -- Design memory: quick-reference notes on core concepts, user philosophy, architecture decisions, and agent roster from the design document.

### research/
- `agent-hardening-research.md` -- Research findings for hardening 22 agent definitions. Covers Claude Code agent best practices, community patterns, senior engineering heuristics, TDD enforcement, and gap analysis of all agents and standards.
- `agent-hardening-research-v2.md` -- Follow-up research (untracked).
- `from-dave.md` -- External input (untracked).

### vision/
- `VISION.md` -- Industrialized System Synthesis vision document. The thesis: specs act as genotype (DNA), agent swarms act as gene expression machinery, and running systems are the phenotype. Authored by Jason Vertrees with Jim Snyder.
- `v2-orchestration-platform-prd.md` -- v2 PRD. Replace Claude Code's conversation-based orchestration with a durable, event-driven platform that persists state to Postgres, enforces guardrails as middleware, and supports recursive decomposition. Defines the four architectural constraints (C1-C4).

## Dependencies
- Vision and PRD documents drive the `platform/` implementation
- Design documents are referenced by the SEM agent and Phase 1 implementation
- Lessons learned informed the v2 PRD requirements
- Research documents informed agent hardening improvements in `agents/`

## Patterns
- **Date-prefixed filenames:** Plan documents use `YYYY-MM-DD-` prefix for chronological ordering.
- **Status tracking:** Each document has a Status field (Draft, Approved, Design approved, etc.).
- **Traceability:** Documents cross-reference each other (e.g., v2 PRD references lessons-learned-v1, design notes reference the full design document).

## Constraints
- Design documents and ADRs are immutable once accepted -- changes are recorded as new documents.
- The `plans/` subdirectory contains actionable implementation plans; `vision/` contains strategic direction; `research/` contains analysis and findings.
- Untracked files (`agent-hardening-research-v2.md`, `from-dave.md`) are work-in-progress and not yet committed.
