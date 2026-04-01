# standards/process/

**Purpose:** 6 process standards that define the SDLC workflow, TDD discipline, code review rigor, completion criteria, invariant enforcement, and domain fidelity rules. These are the most frequently referenced standards -- every agent reads at least `sdlc-phases.md` and `definition-of-done.md` before starting work.

## Key Components
- `sdlc-phases.md` -- (Status: REFERENCE) Defines the 8 SDLC phases (Bootstrap, Spec, Design, Decompose, Build, Verify, Ship, Evaluate) with team compositions, activation rules, tool requirements, and invocation patterns. Includes the project intake protocol, domain-first research process, and the watchdog pattern for Build phase.
- `tdd-workflow.md` -- (Status: MANDATORY) The red/green/refactor cycle. Rules: never skip RED, never write production code without a failing test, one behavior per test, 98% line and branch coverage enforced by hooks and CI. Applies to backend-developer, frontend-developer, code-reviewer, verifier.
- `definition-of-done.md` -- (Status: MANDATORY) Checklist for task completion: implementation matches spec, all tests pass, 98% coverage, mypy strict passes, linter clean, code reviewed, security reviewed, `.meta/` updated, API docstrings on all public interfaces, backward-compatible. Enforced by the verifier agent.
- `code-review-process.md` -- (Status: MANDATORY) Code review checklist with three severity levels: Critical (security, silent error swallowing, data corruption, test gaps), Warning (naming, function size, dead code, layer violations), Suggestion (naming clarity, duplication, performance, documentation). Output format: file/line, what, why, how to fix.
- `invariants.md` -- (Status: ACTIVE) Project invariants standard. Invariants are non-negotiable, machine-verifiable rules enforced by multiple independent layers (hooks, tests, agent instructions, CI). Defines the `INVARIANTS.md` file format with `## INV-NNN:` headings and `**Verify:** \`command\`` patterns. Component-level invariants are additive -- they never override project-level.
- `domain-fidelity.md` -- (Status: MANDATORY) The most important constraint in Spec/Design phases. Every agent must understand the domain correctly before producing artifacts. Defines domain briefing documents (domain axioms, core entities, glossary), mandatory verification step, cascade risk awareness. Born from an incident on a client project where wrong domain understanding cascaded through every downstream phase.

## Dependencies
- Read by every agent definition in `agents/` (especially `sdlc-phases.md` and `definition-of-done.md`)
- `sdlc-phases.md` is the SEM's primary reference for phase management
- `tdd-workflow.md` is enforced by hooks (`check-test-exists.sh`, `verify-green.sh`)
- `invariants.md` is enforced by `hooks/check-invariants.sh`
- `domain-fidelity.md` is enforced by the domain-modeler agent and `DomainFidelityRule` guardrail in the v2 platform

## Patterns
- **Standards as contracts:** Each standard declares who it applies to and whether it is MANDATORY or REFERENCE.
- **Anti-patterns alongside rules:** Each standard includes a "What NOT to Do" section with specific anti-patterns to avoid.
- **Layered enforcement:** Rules are enforced at multiple levels (documentation, agent prompts, hooks, CI, guardrail middleware) so that violating all layers simultaneously is improbable.

## Constraints
- MANDATORY standards cannot be overridden by agents -- only by explicit human decision.
- The 98% coverage threshold in `tdd-workflow.md` and `definition-of-done.md` is enforced mechanically and has no exceptions without a linked justification.
- Domain fidelity verification must occur before any specification work -- skipping it risks cascading errors through all downstream phases.
