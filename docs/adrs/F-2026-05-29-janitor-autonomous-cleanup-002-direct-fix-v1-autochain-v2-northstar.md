# ADR-002: v1 fixes are direct; the SDLC-autochain is a documented v2 north star

**Date:** 2026-05-29
**Status:** Accepted
**Context:** The CTO's vision for janitor includes a fully hands-off pipeline
that could autochain `/goal → /spec → /architect → /build --autonomous` to make
improvements with no operator involvement. But v1's scope is the minimal-safe
category set (lint/format, test-proven dead-code, whitespace/EOF/import-order) —
mechanical fixes. Routing a trailing-whitespace fix through spec-enforcer, ADRs,
and wave-planning is massive overhead and, worse, ADDS failure surface to
exactly the work that is supposed to be flawless. "Hands-off" (no prompts) and
"autochain the full SDLC" are separable requirements; only the former is
load-bearing for v1.
**Decision:** v1 janitor dispatches a fix-subagent that performs the mechanical
fix DIRECTLY in the worktree (run the configured formatter; delete test-proven
dead code) — no /spec, /architect, or /build. Both interactive and `--autonomous`
modes are hands-off (autonomous = zero prompts). The
`/goal → /spec → /architect → /build --autonomous` autochain is recorded as the
intended v2 capability for when janitor graduates to feature-sized work
(overlaps the closed-loop-ticket-pipeline vision); it is NOT built in v1.
**Consequences:**
- *Easier:* v1 stays small, fast, and reliably flawless; fewer moving parts ⇒
  fewer ways to break; mechanical fixes incur no SDLC ceremony.
- *Harder:* janitor cannot yet take on feature-sized work; two execution models
  (direct v1, autochain v2) will eventually coexist and must be reconciled.
- *Deferred deliberately:* the autochain is a genuine later capability; building
  it now would directly contradict the flawless-only guarantee (BR-004).
