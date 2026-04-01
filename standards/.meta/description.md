# standards/

**Purpose:** 17 engineering standards across 6 categories that codify the rules, conventions, and quality expectations for all agent-produced work. Every agent reads applicable standards before producing output. Standards are installed to `~/.claude/standards/` by `install.sh` and apply globally across all projects.

## Key Components
- `process/` -- 6 process standards: SDLC phase definitions and agent activation rules, TDD workflow (red/green/refactor), code review checklist and process, Definition of Done checklist, project invariants enforcement, and domain fidelity rules.
- `code/` -- 4 code standards: clean code (size limits, complexity, naming, principles), error handling (exception hierarchy, logging, API errors), Python conventions (naming, imports, structure, Pydantic, FastAPI, async), and typing standards (mypy strict, annotation rules, Protocol over ABC).
- `testing/` -- 3 testing standards: testing standards (98% coverage, test tiers, AAA pattern, mocking rules, async testing), test naming convention (`test_should_<behavior>_when_<condition>`), and LLM evaluation standards (golden answer tests, failure mode separation, cost awareness).
- `architecture/` -- 3 architecture standards: abstraction rules (YAGNI, twice-before-abstracting), ADR process (when and how to write Architecture Decision Records), and layer boundary standards (dependency direction, no reverse dependencies, framework isolation).
- `security/` -- 2 security standards: data handling (classification, sanitization, database, logging), and OWASP checklist (input validation, auth, secrets management, injection prevention, data protection, dependencies).
- `quality/` -- 1 quality standard: metrics definitions for code quality (coverage, type safety, lint, complexity), process quality (spec fidelity, defect rate, TDD compliance), and velocity tracking.

## Dependencies
- Referenced by all 23 agent definitions in `agents/` -- agents read standards before producing output
- Enforced by hooks in `hooks/` (TDD workflow, invariants)
- Enforced by the verifier agent (coverage, types, lint)
- Enforced by the code-reviewer agent (code review process, clean code)
- Enforced by the SEM agent (SDLC phases, Definition of Done)
- Enforced by the guardrail pipeline in `platform/` (spec compliance, domain fidelity, security scan)

## Patterns
- **Consistent format:** Every standard has `Status` (MANDATORY or REFERENCE), `Applies to` (which agents must follow it), and structured sections with rules, examples, and "What NOT to Do" anti-patterns.
- **Hierarchical organization:** Standards are grouped by concern area (process, code, testing, architecture, security, quality) into subdirectories.
- **Mechanical enforcement over documentation:** Standards that can be mechanically checked are backed by hooks, CI gates, or guardrail rules -- they are not merely advisory.

## Constraints
- Standards marked MANDATORY are non-negotiable -- agents must not deviate without explicit human override.
- Standards marked REFERENCE are informational guidance (currently only `quality/metrics.md` and `process/sdlc-phases.md`).
- Standards are project-agnostic and designed to be reusable across any Python/FastAPI codebase (or adaptable to other stacks).
- Changes to standards propagate immediately to all projects because they live at the user level (`~/.claude/standards/`).
