# ADR-001: /build conductor owns AC chunking; spec-enforcer agent stays simple

**Date:** 2026-05-22
**Status:** Accepted

**Context:**
F026 build empirically demonstrated that the single-dispatch spec-enforcer
shape hits its 20-tool-call budget on specs with 13+ ACs. The dispatched
agent exhausted its budget on AC-009 (a test-file-split investigation)
and required SendMessage continuation to complete. Future specs with 25+
ACs would fail this gate outright.

The fix is hierarchical chunking. The architectural question: WHO owns
the chunking logic — the /build conductor (orchestrator-side) or the
spec-enforcer agent (agent-side)?

Three candidates:
- (a) **Conductor-side chunking:** /build Step 7 item 3 partitions the
  AC list and dispatches one spec-enforcer per chunk in parallel.
  Aggregates verdicts at the orchestrator.
- (b) **Agent-side chunking:** spec-enforcer receives the full spec
  and self-chunks. Agent definition becomes more complex; agent
  retains internal state across chunks.
- (c) **Hybrid:** chunker helper script + conductor invokes it, but
  agent still receives the full spec and "knows" which chunk it owns
  via a parameter.

**Decision:**
Option (a) — /build conductor owns the chunking logic. Specifically:

1. A new `scripts/spec_enforcer_chunker.py` exposes a `partition`
   subcommand that reads spec.md and emits JSON describing how to
   chunk the ACs.
2. `skills/build/SKILL.md` Step 7 item 3 prose is updated to:
   (i) invoke the chunker, (ii) read the JSON, (iii) construct N
   parallel Agent-tool dispatches in a single turn, (iv) aggregate
   verdicts with OR-semantics.
3. `agents/spec-enforcer.md` is UNCHANGED. Each dispatch receives one
   chunk of ACs and emits one verdict. No agent-side state, no
   inter-chunk awareness.

The chunk size (default 6) and threshold (default 10) are tunable
module-level constants in `scripts/spec_enforcer_chunker.py`; SKILL.md
cites them by reference.

**Consequences:**

- *Easier:*
  - Spec-enforcer agent stays narrow and verifiable. Its 20-tool-call
    budget is sufficient because it only sees one chunk's ACs.
  - Aggregation lives in dispatch-layer prose (SKILL.md), where
    /build's other gates already do similar work (e.g., Step 6c
    verify-green aggregation).
  - Backward-compat fast path: when AC count ≤ threshold, the existing
    single-dispatch shape is used unchanged. F001-F026 single-dispatch
    re-verification produces identical results.
  - Parallel fan-out reuses the established /build Step 6a pattern (N
    Agent calls in one turn). No new orchestration primitive.

- *Harder:*
  - Cross-chunk AC consistency checks (e.g., AC-3 contradicts AC-7
    when they land in different chunks) are not possible with this
    design. Documented as out-of-scope per /spec GA-004.
  - The chunker becomes a new dependency for /build Step 7. If the
    chunker breaks, all builds with >10 ACs fail at Step 7. Mitigation:
    extensive unit tests on the chunker; backward-compat fast path
    preserves the legacy single-dispatch when chunker isn't needed.

- *Deferred:*
  - Cross-chunk consistency checks (operator deferred via /spec
    GA-004).
  - Generalizing the chunking pattern to other long-running dispatches
    (spec-coupling-check, journey-lineage-check, future verifiers).
    Out-of-scope; future PRD candidate if pattern proves valuable.
  - Auto-tuning chunk size based on AC complexity / file count
    estimates. Static defaults sufficient for v1; tuning is a
    one-line diff if needed.

- *Cannot defer:*
  - The aggregation semantics MUST be OR-semantics (any chunk
    NON-COMPLIANT → overall NON-COMPLIANT) — anything else changes
    /build Step 7's binary gate contract.
  - The agent definition `agents/spec-enforcer.md` MUST remain
    unchanged. Modifying the agent would invalidate the conductor's
    single-verdict-per-dispatch assumption.

**Related ADRs:**
- F010-stacked-prs-from-build: parallel fan-out precedent.
- F024-conditional-system-overlay-injection: per-dispatch context
  shaping precedent.
- agents/spec-enforcer.md (not an ADR but the load-bearing agent
  definition this design preserves unchanged).
