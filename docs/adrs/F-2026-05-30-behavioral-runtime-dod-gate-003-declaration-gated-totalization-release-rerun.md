# ADR-003: Declaration-gated totalization with an authoritative release-time re-run

**Date:** 2026-05-30
**Status:** Accepted
**Feature:** F-2026-05-30-behavioral-runtime-dod-gate (Gap A)

**Context:** Building in waves means a half-built system is a legal intermediate state, so
the runtime gate must be conditional, not blanket. But pbj's failure was the *assembled*
app being broken — and a wave that passes against a partially-assembled app can mask an
integration break that only appears in the whole (`lessons-nc-integration-gaps`:
module-green, integration-broken; `lessons-fake-client-fidelity`: mock-only seams). The
gate therefore needs two firing points with different authority, and a relevance signal
that says *what* to check *when*.

**Decision:** Two firing points, one relevance signal.

- **Relevance signal:** Gap B's `state.yaml.spec_phase.contract_completeness.liveness[]`
  (`live_at` per user-outcome AC, `schema_version:1`). The wave-planner *maps*
  wave→live-AC-set from `live_at`; it never re-declares liveness (single source of truth).
  Read tolerantly: a higher `schema_version` warns-and-skips (Gap B ADR-002).
- **Per-wave (Step 6c sibling, fast-feedback):** at a wave close, runtime-check only the
  ACs whose `live_at == <that wave>`. A live AC returning `fail`/`no-test` blocks the wave
  close (zero-tolerance, like verify-green).
- **Release (Step 7.6, authoritative):** **re-run every declared-live user-outcome AC
  against the fully-assembled app**, regardless of per-wave passes — this is the
  integration-gap catch. Then totalize: every user-outcome AC must be verified-live OR
  declared `deferred (reason)`. The clean-vs-milestone routing (ADR-002) follows.
- **Opt-out hatches (reuse, not fork):** `infrastructure_only: true` exempts the whole
  feature; per-AC `live_at: deferred (reason)` is granular; F007/F008 stub-detection gains
  a live-vs-deferred classification. A per-profile time cap (default 600s) bounds the
  re-run; exceed → `fail`. Forward-only: legacy features with no liveness block are
  ungated.
- **Results** persist to `state.yaml.build.runtime_verification` (audit + /metrics +
  resume) and surface in `verification.md`/`release-notes`.

Prior art: this is Build-Verification / pre-promotion smoke testing plus Pact's
`can-i-deploy` (release gated on all required consumers verified-or-excused).

**Consequences:**
- *Easier:* a clean release tag carries an authoritative behavioral guarantee at the
  assembled state; per-wave stays cheap; every opt-out rides an existing mechanism.
- *Harder:* the release-time re-run costs wall-clock (bounded by the time cap); the
  assembled app must be stand-up-able at release (the profile's job).
- *Constrains:* per-wave results are advisory, not authoritative — the release re-run is
  the source of truth; the time cap must be tuned per stack so a slow but correct stand-up
  is not falsely failed.
