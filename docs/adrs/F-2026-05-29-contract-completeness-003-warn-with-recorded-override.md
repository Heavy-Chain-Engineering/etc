# ADR-003: WARN + recorded-override, reusing the user-flow-gate machinery

**Date:** 2026-05-29
**Status:** Accepted
**Feature:** F-2026-05-29-contract-completeness-spec-architect

**Context:** All five contract-completeness checks need an enforcement model. The
options are hard-block (refuse to proceed until pinned), warn-with-recorded-override
(flag, let the operator proceed with an audited reason), or a hybrid. etc's
gate-vs-friction lesson (#36) warns that over-forcing a gate produces the wrong
feature even at full AC-compliance. Legitimate exceptions exist: backend-only ACs,
genuinely-internal logic, `infrastructure_only` features, intentionally-deferred
surfaces. A near-identical precedent already exists — the user-flow-completeness gate
(F017) — implementing detect-class → per-AC elicitation → Phase 4 WARN+defer →
forward-only → sanitization.

**Decision:** All five checks are **WARN + recorded-override**, never hard-block, and
reuse the user-flow-gate code paths rather than a forked module (BR-010). Each
override is recorded in `state.yaml.spec_phase.contract_completeness.overrides[]` with
a non-empty reason and surfaced downstream into `verification.md`/`release-notes`.
Detection is skill-prose against signal lists in the standard (no new Python detector).
The discipline is forward-only: legacy specs/designs are never auto-mutated.

**Consequences:**
- *Easier:* the gate guides without strangling incremental builds; legitimate
  exceptions proceed; the implementation rides proven machinery (low blast radius).
- *Harder:* WARN+override is gameable by mass-deferral — mitigated by making the
  override audit *loud* in `verification.md` (Edge Case 4: silent aggregation would
  re-enable the F001 green-but-broken failure), but only *eliminated* by Gap A
  totalizing liveness at release. The soft gate is a deliberate division of labor:
  authoring-time WARN here, release-time hard-totalize in Gap A.
- *Constrains:* the enforcement precedent for all five contract classes and any
  future contract-completeness check.
