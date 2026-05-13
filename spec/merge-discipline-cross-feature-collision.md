# F016 — Merge discipline: cross-feature collision detection + Mergiraf preflight + submission/merge schema

**Status:** spec
**Author role:** Engineer (Jason / HCE)
**Date:** 2026-05-13
**Source:** memory/project-agentic-integration-research.md (baseline) + memory/project-agentic-integration-delta-2026-05-11.md (delta)

## Problem

A 10-developer team running etc at scale hits the integration-pain ceiling. AgenticFlict (arXiv:2604.03551) measured 27.67% agentic-PR merge-conflict rates industry-wide; Claude Code is at 25.93%. DORA shows 154% PR-size inflation + 91% review-time inflation. The post-F010 stacked-PR architecture is necessary but not sufficient — thin PRs still collide if two features touch the same files.

The session's load-bearing observation from the delta memo: "R2 (plan-time cross-feature collision detection) is still the structural differentiator — nobody surveyed has shipped cross-feature scanning." This is etc's distinctive market position.

## Solution

Ship three carve-outs of the merge-discipline R2-R7 bundle:

### R2 — Cross-feature collision detection at wave-plan time

`scripts/cross_feature_collision_check.py` scans `.etc_sdlc/features/*/tasks/*.yaml` (active + flat-path features, **excluding** the current feature and the `shipped/` archive) for `files_in_scope` entries. Compares the union to the current feature's `files_in_scope`. Reports overlaps with `feature_id:file_path:other_feature_id`. Invoked from `/build` Step 5 (PLAN WAVES) after the wave plan is built, BEFORE the operator confirmation.

- In interactive mode: surface the overlaps in a Pattern A `AskUserQuestion` with options (cancel / proceed with risk acknowledged / serialize via dependency).
- In `--autonomous` mode (F014): log overlaps to stderr + `state.yaml.build.cross_feature_collisions[]` and continue with risk acknowledged (the autonomous-mode philosophy is "fail forward + audit-trail," not "halt for human").

### R3 — Mergiraf preflight INFO

`install.sh` emits a non-blocking INFO line (mirroring gh-stack / impeccable preflights) about Mergiraf availability. Mergiraf is a semantic-merge tool that resolves trivial conflicts automatically — useful for the stacked-PR rebase chain F010 emits.

```
INFO: Mergiraf not detected. Semantic merge conflicts (etc F016+) are resolved manually without it. Install via: brew install mergiraf (macOS) | cargo install mergiraf | https://mergiraf.org for other platforms.
```

### R7 — Submission/merge authority schema

state.yaml.build gains two new optional fields documented in `skills/build/SKILL.md`:

- `submission`: { `submitted_at`, `submitted_by`, `target_branch`, `pr_url` } — populated when the build pushes to the `internal/main` (or equivalent submission target).
- `merged`: { `merged_at`, `merged_by`, `commit_sha` } — populated when a human approves and merges to public `main` (etc's etc-internal → etc/origin/main flow).

Schema only in F016. Behavior wiring (auto-populate fields when push / merge happens) is deferred — F016 just documents the schema slot so future features can populate it. Pairs with the Stripe Minions submission-vs-merge distinction.

## Acceptance Criteria

- **AC-01:** `scripts/cross_feature_collision_check.py` CLI: `python3 cross_feature_collision_check.py <feature_dir>` exits 0 if no overlaps, exits 2 if overlaps with other in-flight features detected. Exit 1 on usage error.
- **AC-02:** Detector scans `.etc_sdlc/features/F*/tasks/*.yaml` and `.etc_sdlc/features/active/F*/tasks/*.yaml`. EXCLUDES `.etc_sdlc/features/shipped/F*/` (already done — won't collide). EXCLUDES `.etc_sdlc/features/rejections/F*/`.
- **AC-03:** Detector reads each task YAML's `files_in_scope` field (a YAML list of strings). Skips tasks missing the field.
- **AC-04:** Detector identifies the current feature by directory name (`F<NNN>-<slug>`) and excludes it from the comparison set.
- **AC-05:** Collision report (stdout) on exit-2: lists each colliding `file:path` → `[F<NNN>, F<NNN>, ...]`. One line per file.
- **AC-06:** `skills/build/SKILL.md` Step 5 (PLAN WAVES) is amended: collision-check runs AFTER wave-planner builds the plan and BEFORE the operator-confirmation Pattern A. Exit 2 → present collisions in a new Pattern A with options (Cancel, Proceed with risk acknowledged, Serialize via dependency).
- **AC-07:** Under `--autonomous` mode (F014), the collision check still runs but exit-2 routes to: log collisions to stderr + write `state.yaml.build.cross_feature_collisions: [...]` + continue with the equivalent of "Proceed with risk acknowledged".
- **AC-08:** `install.sh` emits a non-blocking INFO line about Mergiraf after the impeccable preflight. Pattern matches F010 gh-stack and F011 impeccable preflights.
- **AC-09:** `skills/build/SKILL.md` documents the `state.yaml.build.submission` and `state.yaml.build.merged` schema slots. F016 does NOT implement auto-population — that's deferred.
- **AC-10:** `tests/test_cross_feature_collision.py` covers AC-01 through AC-05 with synthetic feature directory layouts under pytest tmp_path.
- **AC-11:** README adds F016 row in the shipping table mentioning all three carve-outs.

## Out of Scope

- **R6 (verification-time return-check / Anthropic Auto Mode pattern).** Deferred. Conceptually deeper than R2/R3/R7 combined; needs its own /spec.
- **Auto-population of submission/merged fields.** Schema only in F016; population wiring deferred to a future feature.
- **Mergiraf invocation in the rebase chain.** Preflight INFO only; runtime invocation deferred.
- **Cross-feature collision RESOLUTION** beyond reporting. The detector reports overlaps; resolution (serialize, coordinate, or split) is operator-driven.
- **Backporting collision-check to /spec or /architect.** F016 hooks it into /build Step 5. /spec doesn't know files_in_scope yet (that's set during decomposition), so /spec is the wrong layer.

## Technical Notes

- The collision check uses POSIX-portable Python; no third-party deps beyond PyYAML (already required).
- Active path: `.etc_sdlc/features/active/F<NNN>-*/tasks/*.yaml` (per F009 lifecycle).
- Flat path: `.etc_sdlc/features/F<NNN>-*/tasks/*.yaml` (per F009 workaround when allocator output gets moved). Both scanned.
- Self-exclusion via the feature_id parsed from the input `<feature_dir>` argument.
- Per-task files_in_scope is read as-is from YAML; no normalization (relative vs absolute paths). Operators authoring tasks should be consistent.

## Dependencies

- PyYAML (already required).
- No external tool dependencies (Mergiraf preflight is non-blocking advisory only).

## Sequencing

- F016 ships now (this PRD).
- R6 (verification-time return-check) gets its own /spec when scope and design crystallize. Likely a small feature.
- Multi-feature autonomous queue (R3 from memory/project-goal-feature-integration.md, distinct from this PRD's R3) is unlocked by F016 R2 because cross-feature isolation is now mechanically detectable; queueing without it would multiply collisions.
