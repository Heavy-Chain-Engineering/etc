# ADR-F-2026-05-26-phase-wave-001: Phase = top-level WBS group; nested build tags are additive and forward-only

**Date:** 2026-05-26
**Status:** Accepted

**Context:** The `/build` pipeline fused two concepts that should be distinct. A "phase" was identical to a "wave" — Step 6a literally said *"Treat the current wave as phase-N for tag-naming purposes (the build does not yet maintain an explicit phase→wave mapping)."* The execution hierarchy was therefore two levels: `feature → wave(≡phase) → task(+subtasks)`. Tasks already decompose to arbitrary depth (`parent_task`: `001 → 001.001`), but that WBS hierarchy was invisible to the execution organization, so a large feature (e.g. a 50-task WBS) could not be organized into human-meaningful milestones each containing several dependency-ordered waves. Tracker #35 asked for "multi-level hierarchical organization (3-5 levels) for waves/phases/slices." The operator scoped the first increment (2026-05-26) to **phase/wave decoupling only** — add ONE real grouping level above waves; defer "slices" and arbitrary 3-5-level configurable nesting to a follow-up.

Two load-bearing decisions had to be made: (1) where does the phase grouping come from, and (2) how do the protected build tags (`etc/feature/<id>/build/phase-N/{start,done}`, 178 live tags read by `sdlc_timing.py` and `/metrics`) change without breaking history.

**Decision (1) — Phase = top-level WBS group.** A phase is the depth-1 ancestor of a leaf task. Each top-level task with descendants defines one phase containing that subtree's leaf tasks; a top-level leaf task is a single-task phase. **Flat-fallback:** if every task is a depth-1 leaf (an undecomposed feature), the whole build is exactly one `phase-0` containing the waves `compute_waves` already produces — preserving today's behavior with zero regression. Waves are computed *within* each phase (the same dependency algorithm, scoped to the phase's leaf tasks, treating earlier-phase tasks as satisfied). Phases are emitted in cross-phase dependency order; cycles fall back to ancestor-id order (mirroring `compute_waves`' circular-dep handling). `compute_phase_plan(tasks)` in `scripts/tasks.py` implements this; `compute_waves` and the `waves` command are preserved unchanged (a regression test pins this).

The phase grouping is derived from the WBS the operator *already authored* during decomposition — no new authoring surface, no new schema for the operator to fill in. This is the minimum that delivers real "multi-level" while reusing existing structure.

**Decision (2) — Nested tags are additive and forward-only.** New builds write `etc/feature/<id>/build/phase-<P>/wave-<W>/{start,done}` plus `phase-<P>/{start,done}` at phase boundaries. `git_tags.py` needs no change — it is tag-agnostic (`write_tag(name)` writes any name). The 178 existing flat `build/phase-<N>/{start,done}` tags are NOT migrated; legacy features keep them. The two readers — `sdlc_timing.py` and the `/metrics` process layer — parse BOTH forms (an optional `/wave-<W>` segment), so they produce correct output for legacy flat tags and new nested tags alike.

**Consequences:** *Positive:* the operator's WBS becomes the build's phase structure for free; large builds are organized into named milestones with phase- and wave-granularity progress/resumability/timing; the change is additive (no risky re-tagging of 178 protected tags); flat features are bit-for-bit unchanged (the riskiest regression surface is a no-op path); `compute_waves` is untouched so every existing caller is safe. *Negative:* two tag forms now coexist, so every future reader of build tags must handle both (mitigation: the dual-form parse lives in `sdlc_timing.py` + the metrics categorizer, both test-covered; the ADR documents the contract); a wave can no longer span two top-level ancestors (waves are computed per-phase) — acceptable because cross-ancestor parallelism was never an explicit guarantee and per-phase computation is what makes the mapping total and deterministic.

**Alternatives considered:**

*Global waves, then group into phases* (rejected). Compute waves globally as today, then partition them into phases. *Negative:* a global wave can mix tasks from different top-level ancestors, so a wave would belong to multiple phases — the (phase, wave) mapping would not be total/deterministic. Per-phase wave computation avoids this entirely (EC-6).

*Rewrite the tag hierarchy and migrate the 178 flat tags* (rejected). Re-key every legacy `phase-N` tag to the nested form. *Negative:* mutates the protected tag namespace history; high blast radius; a reconciliation like the #30 split-namespace incident. Forward-only additivity gets the new structure with none of that risk.

*Explicit operator-authored phase plan* (rejected for MVP). Let the operator declare phases in the spec. *Negative:* new authoring surface and schema; the WBS already encodes the grouping. Deferred to the full-nesting follow-up if richer control is needed.

**Related:**
- Tracker #35 (this feature is the MVP increment; slices + 3-5-level nesting deferred).
- F009 two-state lifecycle + F010/F006 state.yaml merge discipline (`build.phase_plan` is merge-preserved).
- F021 per-wave verify-green gate (preserved, now expressed at phase→wave granularity).
- The dated-ID gap in `sdlc_timing.py`'s `FEATURE_TAG_PATTERN` (`^etc/feature/(F\d+)/`) is pre-existing and explicitly out of scope here.
