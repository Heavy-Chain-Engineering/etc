# ADR-003: /design declares data-fidelity; build (Gap A) executes — the declare-not-execute boundary

**Date:** 2026-05-30
**Status:** Accepted
**Feature:** F-2026-05-30-prototype-as-intent-design (Gap C)

**Context:** The pbj P0 was scaffolding rows ("EMPLOYEE INFO" / "Name Name") in the
prototype's ingestible range being ingested as real CMS worker profiles, and prototype
values that no seed reproduced. Gap C must address this, but `/design` is a
design-phase skill — it does not run builds, seed databases, or stand apps up. The
question: does Gap C reach into the build to enforce data fidelity, or stay in its lane
and declare the requirement for a downstream consumer?

**Decision:** `/design` **declares** the data-fidelity requirement into its output
(`component-specs.md` / `DESIGN.md`): "seed/fixture data must reproduce every value the
prototype displays" + a flag that the ingestible template must be clean (no scaffolding
rows). It does **not** add a build-time executor. The actual seeding and verification are
build-time concerns: **Gap A's behavioral/runtime DoD gate is the consumer** — "displayed
value is backed by real seeded data" is a behavioral claim Gap A can verify, and the
clean-template requirement is checkable at ingest. This is the same producer→consumer
split as Gap B (contract producer) → Gap A (runtime consumer).

**Consequences:**
- *Easier:* Gap C stays a focused `/design`-phase declaration (small blast radius — skill
  prose + a standard, no new executor); the trilogy's lane discipline holds (declare in
  design, verify in build). The clean-template requirement makes the pbj P0 a declared,
  auditable contract rather than a silent ingest.
- *Harder:* full enforcement depends on Gap A's runtime gate (and a build-time
  clean-template check) actually consuming the declaration — Gap C alone declares but does
  not verify. The handoff must be legible (the declaration is grep-able in the design).
- *Constrains:* Gap C adds no Python executor; abstraction-rules (YAGNI) is honored — the
  enforcement surface already exists downstream, so a new gate here would be speculative.
