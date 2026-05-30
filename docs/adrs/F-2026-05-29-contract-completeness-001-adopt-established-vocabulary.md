# ADR-001: Adopt established contract vocabulary (DbC / CDC / Specification-by-Example / ISO 29148)

**Date:** 2026-05-29
**Status:** Accepted
**Feature:** F-2026-05-29-contract-completeness-spec-architect

**Context:** The five contract classes this feature adds to `/spec` and `/architect`
(format contracts, response-DTO obligations, source-of-truth conflict rule,
open-question→BLOCKER, per-outcome liveness) are not novel — they map cleanly onto
40 years of named requirements-engineering prior art. Inventing etc-local terms for
them would make etc-built specs illegible to outside engineers and would forfeit the
roadmap clarity the prior art already provides. The pbj retro (the evidence base)
re-derived these concepts from scratch across seven feature tags.

**Decision:** Name and document the lineage explicitly, and keep the feature name
"contract-completeness" (= ISO 29148's *completeness* characteristic applied to
*contracts*). The mapping, cited in `standards/process/contract-completeness.md`:

- **Format contracts + response-DTO obligations = Design by Contract** (Meyer):
  accept-on-input is a precondition (client obligation); storage/wire/display format
  and the response-DTO guarantee are postconditions (supplier guarantee).
- **DTO obligations + the deferred build-time verification = Consumer-Driven
  Contracts** (Pact): the contract reflects what the consumer needs, not what the
  provider implements.
- **Liveness + the "fully-functional" acceptance statement = Specification by
  Example / ATDD** (Adzic): his communication-gap thesis *is* the pbj thesis.
- **The umbrella property = ISO/IEC/IEEE 29148**: complete, unambiguous, verifiable.
- **The gate = Definition of Ready** (Scrum/Agile): we are adding contract criteria
  to an existing named gate, not inventing an SDLC step.

**Consequences:**
- *Easier:* etc-built specs are legible to any engineer; the author-vs-verify split
  gains a name (v1 = DbC/SbE specify; Gap A + a contract-testing follow-up = CDC
  verify); the prior art independently confirms the F006 phase split (data-contracts
  = architecture; acceptance examples = intent).
- *Harder:* contributors must learn the canonical vocabulary; the standards doc must
  keep the citations current.
- *Constrains:* all future etc spec/design language — contract terms use these names.
