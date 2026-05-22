# ADR-F023-004: Phase-N tags written under Ftmp- form are preserved

**Date:** 2026-05-21
**Status:** Accepted

**Context:** During a `/build` wave run, the conductor writes git tags marking phase boundaries: `etc/feature/<feature_id>/build/phase-N/{start,done}`. When F023 is in effect, the feature ID in use at wave time is `Ftmp-<8-char-hex>` — the final `F<NNN>` has not yet been allocated. At `/build` Step 7c the feature is renamed and receives its final sequential ID. The question is what to do with the phase tags already on disk: delete and re-add under the final form, force-update in place, or leave them.

F021 BR-008 establishes an append-only tag discipline: the harness never deletes, force-updates, or rewrites a tag once written. That discipline is the foundation of the audit trail's truthfulness — a tag records what was visible at the time of the action, not a post-hoc restatement.

**Decision:** Phase-N tags written under `Ftmp-<hex>` form during `/build` waves stay in their original form. No retag, no force-update, no delete at release time. The tags `etc/feature/Ftmp-<hex>/build/phase-N/{start,done}` are audit-correct for what was visible when they were written. The release tag at Step 7a is `etc/feature/F<NNN>/release` (the final ID) — these two namespaces coexist without conflict.

`/metrics` reads `state.yaml.id_history` from each shipped feature's directory to map `Ftmp-<hex>` phase tags to their final `F<NNN>` for rollups and process-metric derivations. The `id_history` field (two entries: `form=temp` written at `/spec` allocation time, `form=final` written at Step 7c) is the canonical join key. Implementing that join is a future `/metrics` PRD's work; F023 establishes the data shape and the preservation convention.

**Consequences:** *Positive:* F021 BR-008 append-only discipline is preserved verbatim — the audit trail remains an unbroken, forward-only record. Phase tags reflect the state at the time of writing, which is the correct semantics for an audit log. No destructive git operations at release time. *Negative:* `/metrics` must perform a join through `id_history` to associate `Ftmp-` phase tags with their final `F<NNN>` rollup; this is a one-lookup indirection, not a scan. Phase tags for features that were allocated a temp ID but never shipped (abandoned branches) are orphaned — EC-007 documents `/metrics`' handling: skip with a debug log.

**Alternatives considered:**

*Rewrite phase tags at Step 7c (delete + re-add under F<NNN>).* Rejected. This would violate F021 BR-008 append-only discipline directly. More critically, the rewritten tags would be retroactively false: they would claim `etc/feature/F042/build/phase-0/done` was written at the time of the wave run, when in fact `F042` did not exist at that time. An audit trail that rewrites history to look cleaner is not an audit trail.

*Skip phase tags during /build waves on temp-ID features; write only at Step 7c release.* Rejected. This loses observability during the wave runs: operators cannot audit wave progress mid-build, cannot tell which phase failed, and cannot resume from a named checkpoint. The phase tags exist precisely to provide that mid-flight visibility.

*Maintain a parallel tag namespace (write both `etc/feature/Ftmp-<hex>/build/phase-N/*` and `etc/feature/F<NNN>/build/phase-N/*` at Step 7c).* Rejected. This doubles the tag count for every shipped feature. It encourages `/metrics` to read from either namespace inconsistently — two sources of truth for the same event. The `id_history` join is simpler and has a single canonical read path.
