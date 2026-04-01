# The Modular Success Trap: Why 98% Test Coverage Doesn't Prevent Integration Failures in AI-Built Systems

**Jason Vertrees**
**March 2026**

---

## The Problem No One Warned Us About

We built a 260,000-line production system in roughly five days using AI coding agents. The architecture was clean — bounded contexts, well-defined services, a proper domain model. Every module had 98% test coverage. The application stood up, looked great, and appeared to work.

Then we tried to use it as a real user.

The invitation approval flow didn't complete. Permission checks failed on routes that the admin panel rendered without issue. Workflows routed to groups that didn't exist. Not because any module was broken — every module was correct in isolation — but because the *contracts between modules* had never been tested.

We call this The Modular Success Trap: the phenomenon where individually correct, well-tested components produce a system that fails at integration seams. It is not a testing problem. It is a specification problem.

---

## What Integration Seams Actually Are

Most engineers understand integration testing as "Service A calls Service B and gets the right response." That's necessary but insufficient. The real integration surface is broader and more subtle.

An integration seam is any point where one module's *assumptions* about another module must hold true for the system to function. These assumptions are often implicit:

- **Vocabulary assumptions**: The IAM module defines permissions as CRUD operations (`file:read`, `file:write`). The vendor management module assumes permissions are domain-labeled (`vendor:approve`, `vendor:reject`). Both are internally consistent. Neither is wrong. But they are incompatible.

- **Existence assumptions**: A workflow engine routes tasks to a "compliance-review" group. The routing module supports groups. The membership module supports members. But no one created the "compliance-review" group in the right organizational domain. Every piece is structurally sound.

- **Signal assumptions**: An invitation service emits an approval event. A workflow orchestrator listens for approval events. Both work perfectly in their own test suites. But the bridge between them — the actual event subscription — was never wired.

The common thread: unit tests validate that A works and B works, but nothing validates that A's assumptions about B are correct. Standard integration tests verify the *mechanism* (A can call B) but not the *semantics* (A and B agree on what the words mean).

---

## Why AI-Assisted Development Makes This Worse

This is not an AI-specific problem. Integration seam failures have existed as long as software has had modules. But AI-assisted development amplifies the problem in three specific ways.

**First, velocity outpaces integration.** When a single agent can produce a complete, well-tested module in hours, the rate at which integration seams accumulate far exceeds the rate at which they can be manually verified. In our case, we produced roughly 50,000 lines per day. At that pace, assumptions between modules compound faster than any human reviewer can track.

**Second, AI agents are excellent at local correctness.** Modern coding agents excel at building modules that are internally consistent. They write comprehensive unit tests, achieve high coverage, handle edge cases, and produce clean abstractions. This local excellence creates a false sense of security. The tests are green. The coverage is high. The code reviews pass. Everything *looks* complete.

**Third, AI agents don't share working memory across modules.** When Agent A builds the IAM module and Agent B builds the vendor management module, each agent makes locally reasonable decisions about permission string formats. Neither agent is wrong. But without a shared source of truth, they independently invent incompatible vocabularies for the same concept.

This is not a criticism of AI coding agents — they are genuinely remarkable at modular work. It is an observation about what happens when modular excellence is not paired with integration discipline.

---

## The Invariant Registry: A Structural Solution

The fix is not "write more tests." The fix is to make cross-module contracts explicit, canonical, and testable before implementation begins.

We introduce a new artifact called the **Architecture Invariant Registry**: a single, auditable document that lists every concept defined in one place and reused across the system. It serves the same purpose as a database schema — you would not let each service define its own column types for the same table. The invariant registry extends that principle to domain concepts.

### What the Registry Contains

Each entry in the registry has four fields:

| Field | Purpose | Example |
|-------|---------|---------|
| **Concept** | The shared thing | IAM permission strings |
| **Canonical Definition** | The single source of truth — format, allowed values, constraints | `domain:action` format. Allowed actions: `create`, `read`, `update`, `delete`, `approve`, `reject`. Domain must match bounded context name. |
| **Consuming Contexts** | Which bounded contexts depend on this concept | IAM (defines), Vendor Management (consumes), Document Management (consumes), Workflow Engine (consumes) |
| **Enforcement Method** | How consistency is verified | Shared type definition + variance test that scans all permission references against the canonical list |

### When Entries Are Created

The registry is populated during the design phase, not after implementation. When a PRD defines a concept that other bounded contexts will consume — permission strings, entity status enums, error code families, event type vocabularies, routing identifiers — that concept enters the registry immediately.

Each subsequent PRD includes a "Cross-Cutting Concepts Consumed" section that references specific registry entries. This makes integration seams visible in the specification, before any code exists.

### When Entries Are Enforced

Enforcement happens at two points:

**At design time**, when a new module's specification is written, we check it against the registry. If the module consumes a registered concept, its specification must use the canonical vocabulary. If the module introduces a new cross-cutting concept, that concept is added to the registry before the module proceeds to implementation.

**At coding time**, when a module is built, the implementation agent reads the relevant registry entries as part of its context. After the module is complete, a verification step scans the code for references to registered concepts and confirms they match the canonical definitions. This can be a hook, a watchdog agent, or a phase gate — the mechanism matters less than the discipline.

---

## The Detection Problem: Why Superusers Miss Everything

There is a second, orthogonal problem that the invariant registry does not solve on its own: the detection methodology.

In our system, the admin account worked flawlessly. Every route rendered. Every action completed. Every workflow executed. The failures only surfaced when we tested as a regular user — one without superuser privileges, without pre-seeded data, without bypassed permission checks.

This is because superuser accounts mask three categories of integration failure:

1. **Permission catalog gaps.** Admin accounts bypass permission checks entirely. A route can guard itself with a permission string that doesn't exist in the IAM catalog, and the admin will never notice — the check is skipped.

2. **Configuration gaps.** Pre-seeded development data often includes configuration that a real deployment would need to create from scratch. Routing groups, default workflows, catalog entries — if the seed data includes them, tests pass. If a real tenant has to create them, the gap is invisible.

3. **Role-capability mismatches.** Roles are assigned capabilities. Routes require capabilities. But if the intersection of "capabilities a role has" and "capabilities a route requires" is empty for non-admin roles, only non-admin users will experience the failure.

The corrective is straightforward: end-to-end tests must run as a non-privileged user persona. Not as a supplementary check, but as the *primary* testing identity. If the system works for a regular user, it works for everyone. The reverse is not true.

---

## Implementing This in Practice

For teams using AI-assisted development with a structured SDLC, the invariant registry fits into the existing process at well-defined points.

### During Specification (Design Phase)

When writing product requirements:

1. Each bounded context's specification includes a section declaring which cross-cutting concepts it defines and which it consumes.
2. Newly defined concepts are added to the registry with their canonical definition.
3. Consumed concepts must reference the registry entry by name. If the specification uses different vocabulary than the registry, this is a defect, not a style preference.

### During Gap Analysis

The gap analysis phase (which already scans for missing architectural decisions, ambiguous specifications, and contradictions between documents) adds a new check:

- For every cross-cutting concept in the registry, verify that all consuming contexts use the canonical definition.
- Flag any concept that appears in code or specifications with inconsistent vocabulary.

### During Build (Post-Module Completion)

After each module is implemented:

1. The implementation agent's watchdog agents (code reviewer, verifier) include an invariant check: scan the module's code for references to registered concepts and verify conformance.
2. End-to-end tests for the module run as a non-privileged user persona.
3. The module is not marked complete until both checks pass.

### During Build Candidate Tagging

The invariant registry is a required artifact in the Build Candidate — the tagged commit that represents "specification complete, ready to build." If the registry has entries without enforcement methods, or if consuming contexts reference concepts not in the registry, the Build Candidate gate fails.

---

## What This Is Not

The invariant registry is not a type system, though shared type definitions are one enforcement mechanism. It is not a service mesh or API gateway, though those can enforce some of the same contracts at runtime. It is not a replacement for integration tests, which remain necessary for verifying behavior.

It is a *specification artifact* — a document that makes implicit assumptions explicit, gives them canonical definitions, and creates a reference point for both human reviewers and automated checks. Its value is in shifting the discovery of integration failures from testing time (expensive, late) to design time (cheap, early).

---

## The Broader Lesson

The Modular Success Trap is ultimately a communication problem. In a traditional development team, integration assumptions are communicated through conversation, code review, and shared context. When AI agents replace some of that work, the communication channel between modules narrows to whatever is written in the specification.

If the specification does not explicitly enumerate cross-module contracts, those contracts exist only as implicit assumptions — and implicit assumptions are where integration failures hide. The invariant registry makes them explicit.

The lesson is not that AI-assisted development is fragile. It is remarkably capable — 260,000 lines of working, well-tested code in five days is not an outcome that should be dismissed. The lesson is that the discipline required shifts. Less time writing code, more time specifying contracts. Less emphasis on per-module coverage, more emphasis on cross-module invariants. Less testing as the superuser, more testing as the person who will actually use the system.

The modules will be correct. The question is whether they will be correct *together*.
