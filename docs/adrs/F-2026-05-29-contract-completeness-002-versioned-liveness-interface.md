# ADR-002: Version the liveness block as a published producer interface

**Date:** 2026-05-29
**Status:** Accepted
**Feature:** F-2026-05-29-contract-completeness-spec-architect

**Context:** The per-outcome liveness declaration is written by this feature
(`/spec`) into `state.yaml.spec_phase.contract_completeness.liveness[]` and consumed,
later, by the behavioral/runtime DoD gate (Gap A, tracker #51 — named, tracked, and
explicitly `blocked-by` this feature). Producer and consumer ship at different times.
This is exactly the boundary the whole feature exists to protect: a contract whose
consumer does not yet exist. Leaving the block unversioned would commit, inside the
anti-contract-gap feature, the precise failure it prevents.

**Decision:** Put `schema_version: 1` on the liveness block and adopt the
`value-hypothesis.yaml` forward-compatibility contract: a consumer reading a block
whose `schema_version` is higher than it knows MUST warn-and-skip, never crash.
Format/DTO contracts do **not** get a machine block — they remain canonical sentences
in `design.md` (DbC-style, human + grep), because per YAGNI they have no known machine
consumer; only liveness does. The asymmetry is deliberate: machine-readability is
added when a consumer appears, not speculatively.

**Consequences:**
- *Easier:* Gap A can evolve the liveness shape (add deferral-reason or
  verification-method fields) without breaking on features specced today at v1; old
  features stay readable by a future consumer.
- *Harder:* the liveness block is now a versioned interface that cannot be casually
  reshaped — changing it means a version bump + the warn-and-skip path. This is the
  deliberate cost of BR-009.
- *Constrains:* Gap A and any future liveness consumer; the schema-version discipline
  is now part of the producer contract.
