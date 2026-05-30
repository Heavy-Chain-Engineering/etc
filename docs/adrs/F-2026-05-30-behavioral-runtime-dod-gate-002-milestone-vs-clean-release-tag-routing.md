# ADR-002: Milestone-vs-clean release tag routing (the anti-gaming distinction)

**Date:** 2026-05-30
**Status:** Accepted
**Feature:** F-2026-05-30-behavioral-runtime-dod-gate (Gap A)

**Context:** The declaration-gated design (operator refinement, 2026-05-29) allows
outcomes to be deferred — a half-built wave is a legal state — but F001's sin was
shipping a stub *while claiming a clean done*. The gate must let deferral happen yet make
it impossible to claim a clean release while outcomes are unverified. etc already encodes
provenance in git tags (`etc/feature/<id>/spec`, `/architect/{start,done}`,
`/build/phase-P/wave-W/{start,done}`, `/release`). F025 hit a git-ref-hierarchy wall:
`etc/feature/<id>/release/<extend_id>` collides with the existing `etc/feature/<id>/release`
LEAF tag (a ref cannot be both a file and a directory).

**Decision:** At Step 7.6 totalization, route the terminal tag by outcome:

- **All declared-live user-outcome ACs verified-live** → the clean
  `etc/feature/<id>/release` tag (existing path). Feature moves to `shipped/`.
- **≥1 user-outcome AC declared `deferred` (non-empty reason) + the rest verified** →
  `etc/feature/<id>/milestone/<NNN>` (zero-padded sequential, append-only) **instead of**
  the clean release tag. The deferred set is surfaced loudly in `verification.md` and
  `release-notes.md` (never aggregated to a count). Done-as-milestone, not failed.
- **≥1 declared-live AC failing or `no-test`** → hard block (exit 2; no tag; no `shipped/`
  move), routed to remediation like the 7.4/7.5 gates.

`milestone/` is a directory sibling of the `release` leaf — valid because the existing
`architect/start`+`architect/done` and `build/phase-P/wave-W/start` tags prove
multi-level ref nesting works. The F025 collision is avoided structurally: we never nest
under the `release` leaf, and a **bare `etc/feature/<id>/milestone` tag is forbidden** (it
would prevent `milestone/` from being a directory). `git_tags.py` writes annotated,
append-only tags; both a milestone tag and a later clean release tag can coexist over a
feature's life (a deferred outcome going live later cuts a new clean release).

**Consequences:**
- *Easier:* a clean `release` tag now *means* behavioral completeness — `/metrics` and
  any auditor can trust the tag; deferral stays legal but conspicuous; the milestone tag
  is the audit trail F001 lacked.
- *Harder:* the tag namespace gains a milestone tier; consumers reading "is this feature
  done?" must distinguish `release` from `milestone/*`.
- *Constrains:* `git_tags.py` must reject a bare `.../milestone` write; the milestone
  sequence is monotonic and never reused.
