# PRD: Stacked PRs from /build (F010)

## Summary

F010 adds stacked-PR emission to `/build`'s Step 6 (EXECUTE) so each completed wave commits as a distinct PR layer on a GitHub stack rather than as part of a single monolithic merge. Each `etc/feature/F<NNN>/build/phase-<N>/done` tag now corresponds to one layer in the stack; reviewers read minutes of diff per layer instead of hours per 10K-LOC PR. The wave-planner machinery from F008 (file-set isolation per wave) and the per-phase completion-report machinery from F005 (one report per wave) are reused wholesale — F010 is a thin orchestration change at Step 6d, not a redesign.

The motivating incident: the user spent 4 hours reconciling one merged branch against `main` on 2026-05-07. **AgenticFlict** (arXiv:2604.03551) confirms this is the industry pattern, not private pain — 27.67% merge-conflict rate across 107K agentic PRs, with Claude Code specifically at 25.93%. **DORA's 2025 AI report** shows AI-driven 154% PR-size and 91% review-time inflation. **Cursor 3.3** (2026-05-07) shipped "Build in Parallel + Split Changes into PRs" by default; stacked PRs have rotated from "novel" to "table-stakes parity." **Stripe Minions** architecture (1,300 PRs/week, six layers) is the canonical reference for what this looks like at production scale.

F010 is **R1 of the three-layer merge-discipline plan** (see `memory/project-agentic-integration-research.md` baseline and `memory/project-agentic-integration-delta-2026-05-11.md` delta). F015 (R2-R7: plan-time cross-feature collision detection, Mergiraf adoption, verify-time return-check, submission-vs-merge authority) and F011 (/design phase wrapping impeccable) become parallel-safe on F010's foundation because thin layers reduce file-set collision surface from 10K LOC to ~500 LOC per wave. Without F010 first, F015 and F011 would re-create the 4-hour reconciliation pain on themselves — F010 is the bootstrapping move that breaks that recursion.

**Tooling:** GitHub-native (`gh-stack`); no third-party platform dependency (rationale: `gray-areas-spec.md` GA-004). **Push policy:** no auto-push (GA-005). **LOC threshold:** soft warn at 500 LOC/layer (GA-001). **Commit model:** one squash commit per layer (GA-002). **Single-wave fallback:** skip stacking for builds with `total_waves == 1` (GA-003).

## Scope

### In Scope

- **`skills/build/SKILL.md` Step 6 modification.** After `6d` writes `phase-N/done` tag and `completion-report.md`, add **`6d.7: Emit stack layer`** sub-step: collect all files modified during the wave, squash-commit them on a new branch `<feature-slug>-L<N>` (based off the previous layer, or `main` if `N==1`), then invoke `gh stack` to register the layer.
- **gh-stack integration.** `install.sh` documents `gh-stack` as a prerequisite (preflight check + install instruction). /build invokes it via subprocess argv-list (never shell string, per F008 sanitization precedent).
- **Soft LOC warning.** At Step 6d, after collecting the wave's diff, count net LOC; if `> 500`, emit a single warning line to stderr matching the verbatim contract: `WARNING: layer L<N> contains <K> LOC (target: 500). Consider splitting the wave for review tractability. Proceeding with stack emission.`
- **Single-wave bypass.** When Step 5 produces `total_waves == 1`, skip the stack-creation step at 6d.7 entirely; fall back to the existing single-PR behavior. `state.yaml.build.stacked` records `true` or `false` for resume awareness.
- **`/build --resume` extension.** Resume re-reads `state.yaml.build.waves_completed` and `state.yaml.build.stacked`. If stacked, resume picks up at the next layer; the previously-committed layers remain on their branches.
- **Tests.** `tests/test_build_stacked_prs.py` covers: layer-branch creation per wave, squash-commit per layer, gh-stack invocation contract, soft LOC warning text, single-wave bypass, resume across layer boundary, `state.yaml.build.stacked` write.
- **Forward-only.** F001-F009 shipped builds are NOT retro-converted to stacks. F010-onwards use stacking when `total_waves > 1`.

### Out of Scope

- **R2 plan-time cross-feature collision detection** — `/spec` and `/architect` scanning `features/active/` for overlapping file-sets. Deferred to F015.
- **R3 Mergiraf adoption** + continuous-rebase posture. Deferred to F015.
- **R6 verification-time return-check** (Anthropic Auto Mode two-stage classifier pattern). Deferred to F015.
- **R7 submission-vs-merge authority distinction** (Stripe Minions vocabulary). Deferred to F015.
- **Cross-PR daemon** (always-on agent watching all branches). Deferred indefinitely.
- **F011 /design phase wrapping impeccable.** Separate PRD; lands on the stacked-PR foundation F010 provides.
- **Auto-push during build.** Operator controls push timing (GA-005).
- **Per-task commits within layer.** GA-002 chose one squash commit per wave.
- **Hard LOC cap that halts builds.** GA-001 chose soft warning.
- **Adaptive or per-feature configurable LOC threshold.** GA-001 chose a fixed soft target.
- **Always-stack mode for single-wave builds.** GA-003 chose skip-stacking when `total_waves == 1`.
- **Graphite, GitButler, Sapling, or other third-party platforms.** GA-004 chose gh-stack.
- **Stack rebase coordination across concurrent feature builds.** Covered by R3 Mergiraf in F015.
- **Migration of legacy flat-path feature directories** (F001-F009 era). F009 forward-only convention applies.

## Requirements

### BR-001: Stack layer creation at Step 6d.7

`/build`'s Step 6 (EXECUTE) gains a new sub-step **6d.7** that runs after `6d` (phase-N/done tag + completion-report.md write) and before `6e` (proceed to next wave or finish). The sub-step collects every file modified during wave N, squash-commits them on a new git branch `<feature-slug>-L<N>`, and registers the branch as a stack layer via `gh stack`. The previous layer's branch is the base of layer N (or `main` when `N == 1`). The phase-N/done tag is written BEFORE 6d.7 fires; if 6d.7 fails, the tag remains (append-only per F005 edge case 4) and `state.yaml.build.stacked_failure` records the failure for `--resume` recovery.

### BR-002: gh-stack as the stack tool

The stack-management tool is `gh-stack` (GitHub-native; documented at https://www.infoq.com/news/2026/04/github-stacked-prs/). /build invokes it via `subprocess.run` with an argv list, never a shell string — mirrors F003's operator-supplied path sanitization and F008's `git mv` invocation pattern. The exact invocation is `gh stack push --base <previous_layer_branch>` from inside the layer branch worktree.

### BR-003: Layer branch naming

Layer branches are named `<feature-slug>-L<N>` where `<feature-slug>` is the kebab-case slug from `state.yaml.build.feature` and `<N>` is the 1-indexed wave number. Example: F010's wave 0 produces branch `stacked-prs-from-build-L1`; wave 1 produces `stacked-prs-from-build-L2`. Branch names match the regex `^[a-z][a-z0-9-]+-L[0-9]+$`; slugs containing characters outside `[a-z0-9-]` are sanitized at branch-creation time (replace non-matching chars with `-`).

### BR-004: Soft LOC threshold warning

At Step 6d.7, after collecting the wave's net diff, /build counts net LOC (additions + deletions per `git diff --shortstat`). When `net_loc > 500`, emit this VERBATIM warning to stderr (one line, the test contract greps for the exact prefix):

```
WARNING: layer L<N> contains <K> LOC (target: 500). Consider splitting the wave for review tractability. Proceeding with stack emission.
```

The warning is non-blocking. /build proceeds with layer emission unconditionally. The 500 LOC target is a module-level constant `LAYER_LOC_SOFT_TARGET` in whatever script owns the check, so future tuning is a one-line edit.

### BR-005: Single-wave bypass

When Step 5 produces `total_waves == 1`, /build skips Step 6d.7 entirely and falls back to the existing single-PR behavior (no stack, no layer branch, no `gh stack` invocation). `state.yaml.build.stacked` is set to `false` for the build. Step 7's terminal release-tag + release-notes.md + active→shipped move runs unchanged. The `gh stack` tool is NOT invoked; install.sh's preflight check does NOT fire as a hard requirement when total_waves will be 1.

### BR-006: `/build --resume` across layer boundaries

When `state.yaml.build.stacked == true`, `/build --resume` reads `waves_completed` and resumes at the next layer. Layer branches from completed waves remain in place; resume re-invokes Step 6d.7 starting at `wave_num = waves_completed + 1` and bases the new layer's branch on the most recent completed layer's branch. When `state.yaml.build.stacked == false` (single-wave bypass), resume behavior is unchanged from current /build.

### BR-007: install.sh preflight check for gh-stack

`install.sh` adds a preflight check after the existing `claude-code` detection: `command -v gh-stack` (or `gh stack --help` exit code 0). If absent, the installer surfaces this message (verbatim, the test contract greps for the prefix):

```
INFO: gh-stack not detected. Stacked-PR builds (etc F010+) require gh-stack. Install via: gh extension install github/gh-stack (or equivalent). Single-wave builds work without it.
```

The check is INFO-level, NOT a hard blocker — install.sh continues. The user can install gh-stack later; only multi-wave builds need it.

### BR-008: Forward-only convention

F001-F009 builds (already shipped as single PRs) are NOT retro-converted to stacks. The stacking behavior applies to feature builds where `state.yaml.build` is written by a post-F010 `/build` invocation. Legacy `state.yaml` files without a `stacked` field are treated as `stacked: false` (single-PR behavior preserved). Matches F001 BR-007's forward-only convention reaffirmed across F002-F009.

### BR-009: Test contract

A new test file `tests/test_build_stacked_prs.py` covers: (a) Step 6d.7 fires after phase-N/done tag; (b) layer branch is created with the correct name; (c) squash-commit contains the wave's diff and no other content; (d) `gh stack` is invoked via argv-list with the expected arguments; (e) LOC warning fires verbatim at >500 LOC and not at ≤500 LOC; (f) `state.yaml.build.stacked` is `true` for multi-wave builds and `false` for single-wave; (g) `--resume` picks up at the correct layer; (h) install.sh preflight INFO message appears when gh-stack is absent. Tests use `pytest tmp_path` + `subprocess.run cwd=tmp_path` per F005's pattern; tests construct synthetic git repos via `subprocess.run(["git", "init", ...])` rather than mocking. The full pytest suite must pass: ≥ 770 baseline + the new F010 tests, no regressions.

### BR-010: No auto-push

`/build` does NOT invoke `git push` or `gh stack submit` at any step. The stack is committed and registered locally only. Operator pushes the stack manually after `/build` terminal close (typically `gh stack submit` from the top layer). Matches the existing operator-controlled push discipline (GA-005 citation: `skills/build/SKILL.md` Steps 6d and 7.5).

## Acceptance Criteria

1. **Step 6d.7 sub-step exists.** `skills/build/SKILL.md` contains a sub-step header `**6d.7: Emit stack layer**` positioned between Step 6d (phase-done tag + completion-report) and Step 6e (proceed to next wave).
2. **Step 6d.7 body documents the contract.** The sub-step body documents: squash-commit operation, layer-branch naming convention, gh-stack invocation, and the relationship to phase-N/done tags (tag written FIRST; layer emission after).
3. **gh-stack invocation is argv-list.** `skills/build/SKILL.md` Step 6d.7 documents the `subprocess.run` invocation with an argv list (NOT a shell string). The documented pattern matches F008's `git mv` invocation precedent.
4. **Layer branch naming regex.** Layer branches match `^[a-z][a-z0-9-]+-L[0-9]+$`. Sanitization at branch-creation strips characters outside `[a-z0-9-]` from the slug. Skill body documents the regex verbatim.
5. **LOC warning text verbatim.** `skills/build/SKILL.md` documents the warning line verbatim: `WARNING: layer L<N> contains <K> LOC (target: 500). Consider splitting the wave for review tractability. Proceeding with stack emission.` The test contract greps for the prefix `WARNING: layer L`.
6. **LOC threshold constant.** The implementing script defines `LAYER_LOC_SOFT_TARGET = 500` as a module-level constant. Future tuning is a one-line edit.
7. **Single-wave bypass condition documented.** `skills/build/SKILL.md` documents that Step 6d.7 is SKIPPED when `total_waves == 1`. The skip path writes `state.yaml.build.stacked = false`; the multi-wave path writes `state.yaml.build.stacked = true`.
8. **state.yaml schema extension.** `skills/build/SKILL.md` documents the `build.stacked: bool` field as part of Step 2's merge-preserve dict shape.
9. **`/build --resume` semantics documented.** `skills/build/SKILL.md` documents that when `state.yaml.build.stacked == true`, resume picks up at `waves_completed + 1` with the new layer based on the previous completed layer's branch.
10. **install.sh preflight message verbatim.** `install.sh` contains the INFO line verbatim: `INFO: gh-stack not detected. Stacked-PR builds (etc F010+) require gh-stack. Install via: gh extension install github/gh-stack (or equivalent). Single-wave builds work without it.` Test contract greps for `INFO: gh-stack not detected`.
11. **install.sh preflight is non-blocking.** install.sh continues installation when gh-stack is absent. The INFO message does not cause exit-non-zero.
12. **Test file with required contract tests.** `tests/test_build_stacked_prs.py` exists with at least 8 test functions covering BR-009 items (a)–(h): Step 6d.7 ordering, layer-branch creation, squash-commit contents, gh-stack argv invocation, LOC warning at and below 500 LOC, single-wave bypass, state.yaml.build.stacked write, --resume behavior, install.sh preflight INFO.
13. **All tests use tmp_path.** No test in `tests/test_build_stacked_prs.py` writes to or reads from real `.etc_sdlc/features/*/tasks/` directories or the project's real git repo. Tests construct synthetic git repos via `subprocess.run(["git", "init", str(tmp_path), ...])` per F005 + F008 precedent.
14. **Regression baseline.** Full pytest suite passes (≥ 770 baseline tests + the new F010 tests, no regressions) when running `python3 -m pytest --tb=short -q` from the project root.
15. **Changeset scope + preservation.** No F001-F009 release-notes.md, verification.md, task YAML, or other shipped artifacts are modified. The changeset is exactly: `skills/build/SKILL.md`, `install.sh`, `tests/test_build_stacked_prs.py`, plus the F010 PRD copy at `spec/stacked-prs-from-build.md`, plus the `.etc_sdlc/features/active/F010-stacked-prs-from-build/` artifacts.

## Edge Cases

1. **Empty wave (zero file changes).** Test-only or documentation-only wave that produces no net diff. Behavior: skip layer emission at Step 6d.7, log a note (`note: wave <N> produced no file changes; skipping layer emission`). Layer `N-1` remains the head; wave `N` has no corresponding layer branch. Subsequent layers base off `N-1`.

2. **Deletion-only wave.** Net diff is negative (refactor that removes more than it adds). Behavior: valid layer; squash-commit captures the deletions; LOC warning uses absolute value (`abs(net_loc) > 500`) so large-deletion layers still warn.

3. **Squash-commit fails.** `git commit` returns non-zero (e.g., pre-commit hook rejection, unstaged tree corruption). Behavior: STOP the build, do not proceed to next wave, write `state.yaml.build.stacked_failure = <wave_num>` for resume diagnosis. The phase-N/done tag from Step 6d remains (append-only per F005 edge case 4). Operator must remediate manually then run `/build --resume`.

4. **gh-stack absent at multi-wave build time.** Operator skipped the install.sh preflight INFO and started a multi-wave build. Behavior: STOP at Step 6d.7's first invocation with the operator-friendly error `gh-stack required for stacked builds but not found. Install via: gh extension install github/gh-stack, then /build --resume`. /build does NOT fall back to monolithic-PR mode silently.

5. **gh-stack invocation fails.** `gh stack push` returns non-zero (e.g., merge conflict on rebase, GitHub rate limit, network failure). Behavior: STOP, surface gh-stack stderr verbatim to operator, write `state.yaml.build.stacked_failure`. The phase-N/done tag remains. Operator remediates and runs `/build --resume`.

6. **Layer branch already exists.** Re-running /build on the same feature without `--resume` finds `<feature-slug>-L1` already present. Behavior: FAIL FAST at Step 6d.7's first invocation with `error: branch <name> already exists; use /build --resume to continue, or git branch -D <name> to discard`. /build does NOT clobber existing branches.

7. **Feature slug contains non-canonical characters.** Slug like `Add_User_Auth_v2` (underscores, uppercase) lands in `state.yaml.build.feature`. Behavior: sanitize to `add-user-auth-v2` for branch naming (lowercase + dashes), log the sanitized name once at Step 6d.7's first invocation (`note: branch name sanitized from "<input>" to "<sanitized>"`). The on-disk feature slug is NOT modified.

8. **Mid-build re-decomposition changes total_waves.** /build --resume invokes Step 3 (DECOMPOSE) and the wave plan changes (different `total_waves` than the in-progress build). Behavior: resume ABORTS with `error: wave plan changed during resume (expected <old> waves, got <new>); cancel and re-run /build from scratch, or revert spec changes`. /build --resume assumes wave plan stability.

9. **Cross-feature concurrent builds.** Feature A and Feature B both running /build in parallel. Their stacks land on `feature-a-L1, L2, ...` and `feature-b-L1, L2, ...` respectively — no branch-name collision. Behavior: F010 does NOT detect or coordinate cross-feature `main`-content collisions; that is F015's R2 territory. Operator running both concurrently accepts the risk of post-build conflict on merge.

10. **`/build --resume` after gh-stack uninstall.** state.yaml.build.stacked == true but gh-stack is missing on resume. Behavior: FAIL FAST at the first Step 6d.7 invocation with the install instruction (same message as edge case 4). /build does NOT degrade to monolithic mode mid-build — the in-progress layers are committed and a regression mid-feature would be worse than the halt.

11. **Legacy state.yaml without `build.stacked` field.** Feature was started by a pre-F010 `/build`. Behavior: treated as `stacked: false`; resume uses legacy single-PR semantics. Forward-only convention per BR-008 of F001 reaffirmed across F002-F009.

12. **Operator manually modifies layer branch between /build invocations.** Operator force-pushes, rebases, or hand-edits commits on `<slug>-L<N>` outside /build. Behavior: /build does NOT audit external branch modifications. Operator is trusted; if their manual modifications break the stack chain, `gh stack push` will surface the git error verbatim at the next layer's invocation. The auditability is in the phase-N/done tags (append-only) and completion-report.md files (per-wave); operator can inspect those to reconstruct intent.
