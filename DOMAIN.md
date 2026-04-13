# ETC — Engineering Team, Codified

This document grounds engineers and AI coding agents in the exact business
domain ETC operates in. It is not marketing material and not a technical
specification. It defines the domain context that shapes all architectural
and product decisions.

## Domain

ETC operates in the **agentic software engineering** domain.

Specifically, it is a harness — a set of hooks, agents, skills, standards,
and enforcement mechanisms — that makes AI coding agents incapable of
producing wrong code. Not less likely; incapable.

The domain is defined by a hard problem: modern LLM-based coding agents are
plausibility engines. They generate code that looks correct, compiles, and
passes happy-path tests, but is structurally wrong — fabricated APIs,
invented business rules, silent fallback paths, premature declarations of
completion. The state space of possible wrong answers is vast, and software
(unlike physics) has no natural gradient pulling broken systems back toward
correctness. Once an agent enters a wrong state, it stays there.

ETC exists because raw model capability is no longer the bottleneck. The
bottleneck is **discipline and grounding**: forcing agents to operate inside
narrow action spaces, with documented authority, against static domain
truth, and with mechanical verification at every decision point.

## Core Problem

An AI coding agent given an ambiguous task, a full repository, and a
permissive tool belt will confidently produce working-looking output that
violates invariants no one told it about. The failure modes:

- **Fabrication.** Agent invents facts about the business, the API, the
  schema, or the intent — and cites nothing because there was nothing to
  cite.
- **Drift.** Agent's local change is correct but violates a cross-boundary
  invariant the repo never made explicit.
- **Premature completion.** Agent marks a task done before the work is
  verified. Tests pass because the tests are also wrong.

Failure results in:

- Silently broken production code that passes review
- Wasted engineering time chasing the agent's bad suggestions
- Loss of trust in AI-assisted development as a practice
- Compounding technical debt as each fabrication becomes load-bearing

ETC makes these failure modes mechanically unreachable.

## Revenue Model

ETC is developed as an internal tool for consulting engagements where the
author (Jason Vertrees, Heavy Chain Engineering) serves as fractional CTO
and AI-acceleration specialist for client teams. The harness is deployed
inside client repositories to accelerate delivery without sacrificing
quality.

Retention depends on:

- Measurable reduction in AI-generated defects escaping into production
- Faster time-to-ship for new features versus unassisted development
- Engineering teams trusting AI output instead of rewriting it

If the harness makes AI agents reliably correct, clients renew engagements
and expand the deployment. If fabrications escape the harness, trust
collapses and the value proposition fails.

## What ETC Does

ETC is a compilable SDLC specification plus an installation pipeline. The
full flow:

- `spec/etc_sdlc.yaml` is the single source of truth for the harness: gates,
  agents, skills, standards, phases
- `compile-sdlc.py` reads the spec and emits `dist/` — hooks, agents, skills,
  settings-hooks.json, standards, SDLC phase templates
- `install.sh` deploys `dist/` into the client's AI coding tool
  (Claude Code via `~/.claude/`, Antigravity via `~/.gemini/antigravity/`)
- Installed hooks fire on every `UserPromptSubmit`, `PreToolUse`, `TaskCreated`,
  `TaskCompleted`, `SubagentStop`, and `Stop` event to enforce discipline
- AI-powered hooks run gate prompts against Claude Sonnet to evaluate
  Definition of Ready, Definition of Done, and adversarial review
- Bash hooks enforce mechanical rules: TDD gate, phase gate, tier-0 preflight,
  dangerous-command blocking, required-reading verification, invariant checks

The harness installs **role manifests** that project context narrowly: an
agent of a given role sees only the files its role declares it consumes,
and must use a structured **discovery protocol** to request additional
context mid-task.

The harness installs **slash commands** (skills) that codify common
workflows: `/spec` for Socratic requirements refinement, `/build` for the
full validate→decompose→execute→verify pipeline, `/init-project` for
bootstrapping new repositories, `/postmortem` for escaped-bug root cause
analysis.

## Operational and Regulatory Constraints

- The harness operates inside client codebases under NDA. It must never
  exfiltrate code, secrets, or business logic.
- Every AI-powered hook spends tokens. Hook costs must scale with work
  done, not with context window size or chat turn count.
- Hooks must **fail early and loud** — silent swallowing of errors is worse
  than blocking with a clear message.
- The harness must be **installable into any Claude Code project** without
  modifying the base tool. All enforcement lives in `~/.claude/settings.json`
  and the hooks directory.
- The SDLC spec (`spec/etc_sdlc.yaml`) is the ONLY source of truth.
  Duplicating gate definitions, model IDs, or hook paths elsewhere is a
  bug — they must be compiled from the spec.
- The harness must survive Claude Code auto-compaction: state lives on disk
  (`.etc_sdlc/features/*/state.yaml`), not in conversation history.

## The Product Core

All architectural reasoning should anchor to these conceptual entities:

- **Gate** — a hook that evaluates an event (Bash command, file edit, task
  created, prompt submitted, agent stop) and returns allow/block with an
  optional reason
- **Agent** — a spawned subprocess with a specific role, model, context
  projection, and tool set; bounded by its role manifest
- **Role** — a declarative description of what an agent of this type sees,
  does, produces, and escalates; the unit of POLA
- **Role Manifest** — a YAML file at `roles/<role>.yaml` declaring the
  role's `default_consumes`, `discovery.allowed_requests`, `required_outputs`,
  and `escalation_triggers`
- **Skill** — a hand-authored markdown prompt at `skills/<name>/SKILL.md`
  that the agent follows when a slash command is invoked
- **Phase** — a stage in the SDLC lifecycle (spec, decompose, build, verify,
  ship, evaluate) with its own allowed file modification scope
- **Task** — a unit of work produced by `/decompose` as a YAML file with
  `task_id`, `files_in_scope`, `acceptance_criteria`, `requires_reading`,
  and `assigned_agent`
- **Wave** — a group of tasks that can run in parallel because their
  `files_in_scope` sets don't overlap and their dependencies are satisfied
- **Feature** — a spec-defined work item with its own directory at
  `.etc_sdlc/features/<slug>/` containing `spec.md`, `tasks/`, `state.yaml`,
  and `verification.md`
- **Invariant** — a cross-boundary contract in `docs/invariants/<theme>.md`
  with frontmatter declaring `affects_contexts`
- **Tier** — a layer of the domain artifact tree: Tier 0 (DOMAIN.md /
  PROJECT.md / CLAUDE.md), Tier 1 (docs/prds/, docs/plans/, docs/sources/,
  docs/standards/, docs/guides/), Tier 2 (docs/adrs/, docs/contexts/,
  docs/invariants/), Tier 3 (regulated domain artifacts — opt-in)
- **Discovery Request** — a structured ask emitted by an agent to widen its
  default context projection mid-task, with `{kind, target, justification,
  blocking}`

## What ETC Is Not

ETC is not:

- A model wrapper or a fine-tuned coding model
- A prompt library or a collection of "better prompts"
- An IDE plugin or editor integration
- A code formatter, linter, or static analyzer
- A generic automation framework or workflow orchestrator
- A replacement for human engineering judgment on architectural decisions
- A CI/CD system (it composes with CI; it is not CI)
- A product sold to end users — it is an internal tool and consulting
  deliverable

It is specifically a **discipline enforcement harness for AI coding agents**
that composes with existing tooling without replacing any of it.

## Risk Posture

Primary risks:

- **Silent fabrication escaping hooks.** An agent generates wrong code that
  looks right and gets past every gate. This is the worst failure mode
  because it erodes trust in the entire harness.
- **Hook misfire blocking legitimate work.** A gate rejects a valid request
  because its input shape check is wrong. Visible but recoverable; still
  costs engineering time and user patience.
- **Context projection leaks.** A role manifest grants wider access than
  intended, enabling cross-context drift.
- **Installation inconsistency.** A bug in `install.sh` or
  `compile-sdlc.py` causes hooks to deploy incorrectly. The harness appears
  installed but isn't enforcing its rules.
- **Stale memory / stale artifacts.** Agent reads an out-of-date memory
  file or a DOMAIN.md from before a pivot and produces code against the
  old reality.

The harness must favor **correctness and auditability** over ergonomics.
Every gate should fail early and loud. Every successful edit should be
grounded in a cited source. Every escalation should produce a log line.

## Design Implications

Architectural and product decisions should assume:

- **POLA (Principle of Least Authority) is non-negotiable.** Every agent
  starts with a narrow default projection and widens only via logged
  discovery requests.
- **Hooks are the enforcement mechanism, not suggestions.** A rule without
  a hook is a norm, not a rule.
- **Grounding is mechanical.** Every factual claim an agent makes must be
  cited to a file under `docs/sources/` or `DOMAIN.md`. The
  "cite, never invent" rule is enforceable.
- **Tests are the spec.** TDD is enforced by the tdd-gate hook. Production
  code cannot be edited without a corresponding test file.
- **Discipline > Capability.** The harness assumes the model is smart
  enough. The failure mode is action-space breadth, not reasoning depth.
- **Every AI-powered hook must have a shape-check early-exit.** The hook
  should allow input that doesn't match the shape it was designed to
  evaluate, not block. Structured invocations (slash commands, built-in
  todos) bypass natural-language gates.
- **Slow the individual action to accelerate the system.** Governance
  overhead (prompts, hooks, verification) costs tokens and time on every
  action but prevents cascading rework. The whole-system throughput
  optimization is what matters.
- **"Move fast and break things" is incompatible with this domain.**
  Moving fast in agentic engineering means moving through a correct
  pipeline quickly, not skipping steps.

---

**Note on authorship.** This file was drafted during an extensive rigor
pass on the `/init-project` build, dogfooding the tier-0-preflight hook.
It represents the working understanding of ETC's domain as of 2026-04-13
and should be refined whenever the harness's fundamental orientation shifts.
The canonical flow for producing DOMAIN.md is `/init-project` Phase 2.
