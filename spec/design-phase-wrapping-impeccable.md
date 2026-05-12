# PRD: /design Phase Wrapping Impeccable (F011)

## Summary

F011 introduces `/design` as a discrete phase in etc's 6-phase SDLC pipeline (`strategy → research → (design | strategy) → spec → architect → build → release`). `/design` wraps **pbakaus/impeccable** (Apache 2.0, v3.0.7+) wholesale — the existing tool implements the same four-stage architectural pattern etc uses everywhere else: Socratic intent capture (`/impeccable teach`) → root-markdown persistence (PRODUCT.md + DESIGN.md) → load-on-every-command (`load-context.mjs`) → match-and-refuse output (27 anti-pattern rules + 7 reference domains). Two independent projects converged on the same shape; F011 wires them together rather than reinventing.

The motivating gap: **designers cannot onboard to etc today.** `/spec` is engineering-oriented; no discrete design phase exists. PMs hand off vague UI direction to engineers; engineers produce generic AI-mockup aesthetics (purple-to-blue gradients, nested cards, gray-on-coloured text — all in impeccable's match-and-refuse rules). Without `/design`, designers stay outside the harness. With `/design` wrapping impeccable, designers get a live browser-extension iteration loop + structured intent capture + deterministic anti-pattern enforcement, all under etc's audit trail and phase-gate discipline.

`/design` runs **BEFORE `/spec`** on the design side of the `(design | strategy)` mid-funnel branch. `/design` ALLOCATES the feature directory (first phase to touch `features/`); `/spec` inherits the `feature_id` from `/design`'s `state.yaml` (mirroring how `/architect` inherits from `/spec`). `/design`'s etc-native contributions: phase entry check (dispatch `/impeccable teach` if PRODUCT.md/DESIGN.md absent; accept-or-refine if present), `gray-areas-design.md` for concerns impeccable doesn't natively cover (WCAG floor, motion-reduction respect, responsive breakpoint targets, user-flow state machines), file-watch contract for the designer iteration loop, and **conditional tier-0 promotion** of PRODUCT.md + DESIGN.md when the feature has a user-facing surface. Output: design tokens + component specs that `/spec` consumes during AC authoring.

F011 **deprecates the existing homeless `ux-designer` and `ui-designer` agents** — their entire scope is subsumed by impeccable + `/design`. Forward-only: F001-F010 unchanged. License: Apache 2.0 (impeccable) wraps cleanly with etc's private-commercial distribution per `memory/project-plugin-packaging-strategy.md`.

## Scope

### In Scope

- **New skill at `skills/design/SKILL.md`.** ~600-800 lines, mirrors `/architect`'s 5-phase Socratic structure (intent capture → research → gray-area resolution → 2.75 classification → section drafting → output) adapted for the design domain. Wraps `/impeccable teach` via the Skill tool at phase entry.
- **Skill registration in `spec/etc_sdlc.yaml`.** Adds `design` to the skills section with proper description, role-tier, model defaults.
- **`/design` phase entry logic.** Detect PRODUCT.md + DESIGN.md at repo root. If absent, dispatch `/impeccable teach` via Skill tool (wrap-and-invoke). If present, surface for accept-or-refine via Pattern A picker.
- **`gray-areas-design.md` schema.** Mirrors `gray-areas-spec.md` + `gray-areas-architect.md` patterns. Captures etc-specific concerns impeccable does not natively cover: WCAG conformance floor, motion-reduction respect, responsive breakpoint targets, user-flow state machines.
- **File-watch contract for designer iteration loop.** Documented JSON path (likely `<feature_path>/design-iteration.json` or `~/.impeccable/last-session.json`) + `/design --sync` command. Exact schema deferred to `/architect` phase; F011 specifies the contract is file-watch.
- **Conditional tier-0 promotion** of PRODUCT.md + DESIGN.md. When `state.yaml.design_phase` block is present, tier-0-preflight (or its successor) blocks edits until both files exist. Backend-only features (no `design_phase` block) skip the requirement.
- **`state.yaml.design_phase` block.** Schema mirrors `spec_phase` + `architect_phase`: `classification`, `phase_2_75_metrics`, `design_author_role`, `completed_at`, `impeccable_version_pinned`, `tier_0_promoted: bool`.
- **`value-hypothesis.yaml.design_author_role` field** (mirrors `spec_author_role` + `architect_author_role` per F006 BR-007).
- **Git tags.** `etc/feature/F<NNN>/design/start` and `etc/feature/F<NNN>/design/done` written by `/design` Phase 5.
- **Output handoff to `/spec`.** `/design` writes `design-tokens.json` + `component-specs.md` to `<feature_path>/`. `/spec` Phase 2 research reads these when present.
- **Unified agent at `agents/design.md`.** Replaces the two deprecated homeless agents with one unified agent for ad-hoc Agent-tool invocations from other skills.
- **Deprecation of `ux-designer` + `ui-designer` agents.** `agents/ux-designer.md` and `agents/ui-designer.md` marked deprecated; spec/etc_sdlc.yaml entries updated to redirect to `agents/design.md`. Files remain on disk for forward-only compatibility (existing references in F001-F010 specs continue to work).
- **Tests at `tests/test_design_skill.py`.** ~10-12 grep-based contract tests for skill body structure, classifier constants, gray-areas-design schema, state.yaml.design_phase shape, agent metadata, file-watch contract documentation.
- **README.md update.** `/design` entry added to skill catalog, F011 added to "What has been shipping" table, lifecycle diagram clarified (impeccable wrap noted).
- **install.sh preflight INFO for impeccable.** Non-blocking detect-or-suggest (matches F010's gh-stack pattern). Continues installation if impeccable absent.

### Out of Scope

- **Implementing impeccable itself.** We wrap-and-invoke (GA-001); impeccable upstream owns its skill body, anti-pattern rules, reference domains, browser extension, `load-context.mjs`.
- **Building impeccable's browser extension.** Impeccable owns this; F011 specifies the file-watch contract that bridges to /design's state.yaml.
- **Detailed JSON schema for the file-watch handoff.** F011 specifies the *contract* (file-watch); `/architect` phase specifies the *schema*.
- **`/strategy` phase** (the other branch of `(design | strategy)`). Separate future PRD.
- **Re-architecting DOMAIN.md or PROJECT.md.** Orthogonal-with-cross-reference per GA-007.
- **Retroactive migration of F001-F010** to use `/design`. Forward-only.
- **Customizing impeccable's anti-pattern rules.** Operator can override locally; /design treats impeccable's rules as authoritative by default.
- **MCP server, polling REST, or manual sync** browser-extension contracts. Per GA-006, file-watch chosen.
- **Always-tier-0** for PRODUCT.md + DESIGN.md. Per GA-005, conditional only.
- **Forking impeccable.** Per GA-001, wrap-and-invoke.
- **Hard dependency on impeccable in install.sh.** Preflight INFO (non-blocking), matching F010's gh-stack pattern.
- **`/init-project` changes beyond a single "See also" cross-reference line.** Larger changes (e.g., interactive offer to dispatch `/impeccable teach` after creating DOMAIN.md) deferred to a follow-on PRD.
- **`/metrics` integration with `design_author_role`.** `/metrics` already reads role enums; "Designer" will surface naturally without F011 changes.
- **Hooks/discipline rewrites.** tier-0-preflight extension is additive; no breaking changes to existing hook contracts.

## Requirements

### BR-001: Pipeline position and feature-directory allocation

`/design` is registered in `spec/etc_sdlc.yaml` as a phase skill running on the design side of the `(design | strategy)` mid-funnel branch, positioned BEFORE `/spec` in the 6-phase pipeline. `/design`'s Phase 2 Step 0 invokes `python3 ~/.claude/scripts/feature_id.py allocate-next .etc_sdlc/features "<slug>"` — the first phase to touch `features/`. `/spec` and `/architect` (when subsequently invoked on the same feature) inherit `feature_id` + `feature_path` from `state.yaml` rather than re-allocating. Backward-compat: `/spec` can still be invoked first when no `/design` phase exists for the feature (e.g., backend-only features routed through the `strategy` branch); `/spec` then allocates as today.

### BR-002: skills/design/SKILL.md — 5-phase Socratic mirror of /architect

A new skill body at `skills/design/SKILL.md` (~600-800 lines) mirrors `skills/architect/SKILL.md`'s 5-phase structure verbatim: Phase 1 intent capture (5 Pattern-B questions adapted for design context: visual identity, brand voice, user-flow shape, accessibility floor, role), Phase 2 research (codebase + web + antipatterns + impeccable's reference domains), Phase 2.5 gray-area resolution, Phase 2.75 three-state classifier with the same `FILL_RATIO_*` constants, Phase 3 section drafting (Summary, Scope, Requirements, ACs, Edge Cases), Phase 4 DoR validation, Phase 5 output. The skill body cites `standards/process/interactive-user-input.md` for Pattern A/B usage. Frontmatter: `name: design`, `description` mentions "design phase wrapping impeccable", and `primary_phase: design`.

### BR-003: Phase entry — detect PRODUCT.md/DESIGN.md, wrap-and-invoke /impeccable teach

`/design` Phase 1 first checks repo root for PRODUCT.md AND DESIGN.md. Decision matrix:

- **Both absent.** Dispatch `/impeccable teach` via the Skill tool (NOT subprocess; preserves auth context per F006 BR-010 chain semantics). Impeccable's `teach` runs its full Socratic capture and writes PRODUCT.md + DESIGN.md. `/design` resumes Phase 1 after `/impeccable teach` completes.
- **Both present.** Surface a Pattern A picker: `Accept current PRODUCT.md + DESIGN.md` / `Refine PRODUCT.md (re-run teach)` / `Refine DESIGN.md (re-run teach)` / `Start over with /impeccable teach`. Selected outcome routes to either accept-and-proceed or dispatch `/impeccable teach` with a refinement flag.
- **One present, one absent.** Surface Pattern B status asking which is the intended state. Most likely a project that ran `/impeccable teach` partially or has a legacy DESIGN.md without PRODUCT.md.

Impeccable version pinning: invoke via Skill tool with version-resolution accepting ≥v3.0.7 minor-patch (per GA-004). On version mismatch, surface Pattern B warning and halt.

### BR-004: /design's etc-native artifact set

`/design` writes the following artifacts under `<feature_path>` at Phase 5:

- `gray-areas-design.md` — extended-schema gray areas covering etc-specific concerns impeccable does not natively capture: WCAG conformance floor, motion-reduction respect, responsive breakpoint targets, user-flow state machines, error/empty/loading state coverage. Schema mirrors `gray-areas-spec.md` and `gray-areas-architect.md` (Decided by enum, Citation, Resolution rationale).
- `state.yaml.design_phase` block — merge-preserve pattern (read existing state.yaml, mutate only `design_phase`, write back). Schema: `classification`, `phase_2_75_metrics`, `design_author_role`, `impeccable_version_pinned`, `tier_0_promoted: bool`, `completed_at`.
- `value-hypothesis.yaml.design_author_role` field — captures the designer's role (Designer / Other) per Phase 1 Q6. Mirrors the F006 BR-007 dual-author-role schema.
- `research/design-codebase.md` — Phase 2 codebase findings (existing design patterns, design-system files, component inventory).
- Git tags: `etc/feature/F<NNN>/design/start` (written at Phase 5 entry per F010 phase-tag precedent) and `etc/feature/F<NNN>/design/done` (written at Phase 5 successful close).
- `design-tokens.json` and `component-specs.md` at `<feature_path>/` — the design output `/spec` consumes during AC authoring (see BR-007).

### BR-005: File-watch contract for designer iteration loop

`/design` documents a file-watch contract for the impeccable browser-extension iteration loop. The contract: impeccable's browser extension writes designer-decision deltas to a known JSON path. `/design` reads at Phase 5 entry and on operator command `/design --sync`. The exact path and JSON schema are specified at `/architect` phase (BR-005 stipulates the contract is *file-watch*, not the schema); F011 documents one of two reasonable default paths in the skill body:

- `~/.impeccable/last-session.json` (cross-feature; designer iterates against one project at a time)
- `<feature_path>/design-iteration.json` (per-feature; multiple concurrent designers possible)

`/design` reads at most one of these paths (operator-selectable via `--sync-from` flag). MCP server, polling REST, and manual sync are explicitly NOT supported (per GA-006).

### BR-006: Conditional tier-0 promotion of PRODUCT.md + DESIGN.md

When `state.yaml.design_phase.tier_0_promoted == true`, the `tier-0-preflight` hook (or its successor in `hooks/`) blocks Edit/Write operations under the feature directory until BOTH PRODUCT.md AND DESIGN.md exist at repo root. `tier_0_promoted` is set to `true` automatically when `/design` Phase 5 completes successfully on a feature with a user-facing surface (i.e., one or more ACs classified `user-facing` per F001's signal list). Features without a user-facing surface (no design_phase block OR `tier_0_promoted: false`) skip the tier-0 check. Always-tier-0 mode is NOT supported (per GA-005). The hook citation for this contract lives in `standards/process/sdlc-phases.md` (or appropriate standards file); `/design` cites the standard by path (F002 standards-doc citation pattern), not by duplicating the rule inline.

### BR-007: /design output handoff to /spec

`/design` writes `<feature_path>/design-tokens.json` (impeccable-style design tokens — colors, typography, spacing, motion, breakpoints) and `<feature_path>/component-specs.md` (per-component specs with variants, states, accessibility attributes — mirrors `agents/ui-designer.md`'s output format adapted for impeccable's token vocabulary). `/spec` Phase 2 codebase research detects these files and incorporates them into the spec.md's `Acceptance Criteria` section (e.g., "AC-3 success criterion references token `--color-text-primary` from design-tokens.json"). `/build` Step 6 dispatch context includes design-tokens.json + component-specs.md alongside spec.md (mirrors F006 BR-005's design.md inclusion pattern).

### BR-008: Unified agent at agents/design.md replaces ux-designer + ui-designer

A new agent definition at `agents/design.md` replaces the two homeless `agents/ux-designer.md` and `agents/ui-designer.md`. The new agent has `primary_phase: design`, model `opus`, tools `Read, Grep, Glob, Write, Edit`, and a description spanning the union of the two deprecated agents' scopes (user flows + visual specs + design tokens + accessibility + interaction patterns). The agent body cites `skills/design/SKILL.md` for the canonical interactive workflow and explains the unified-agent rationale (impeccable-anchor convergence). `spec/etc_sdlc.yaml` registers the new agent and marks `ux-designer` + `ui-designer` as deprecated with a redirect note. The deprecated agent files remain on disk for forward-only compatibility — F001-F010 specs referencing them continue to work, but new specs should reference `agents/design.md`.

### BR-009: install.sh preflight INFO for impeccable (non-blocking)

`install.sh` adds a non-blocking preflight check for impeccable after the existing line-67 client-detection block AND after F010's gh-stack preflight (chain order: client-detect → gh-stack → impeccable). If impeccable is not detected (POSIX-portable: `command -v impeccable` or check for the Claude Code skill at `~/.claude/skills/impeccable/`), surface this verbatim INFO message:

```
INFO: impeccable not detected. /design phase requires impeccable (etc F011+). Install via: npm install -g impeccable (or equivalent). Features without a /design phase work without it.
```

The check is INFO-level — `install.sh` continues regardless. Matches F010's gh-stack preflight pattern.

### BR-010: Forward-only convention and test contract

F001-F010 builds (already shipped) are NOT retro-converted to use `/design`. The `/design` phase applies only to feature builds where `state.yaml.design_phase` is written by a post-F011 `/design` invocation. Legacy `state.yaml` without a `design_phase` block is treated as `design_phase_required: false` (skipping tier-0 check, no `/design` invocation expected). A new test file `tests/test_design_skill.py` covers: (a) skill body 5-phase structure (header greps), (b) `FILL_RATIO_*` constants documented, (c) Phase 1 6-question shape, (d) impeccable wrap-and-invoke contract documented, (e) gray-areas-design schema, (f) state.yaml.design_phase block schema, (g) git tag pattern `etc/feature/F<NNN>/design/{start,done}`, (h) agent metadata at `agents/design.md` (primary_phase, tools, model), (i) install.sh preflight INFO verbatim, (j) deprecation notes on agents/ux-designer.md and agents/ui-designer.md. Tests use pytest `tmp_path` + grep-based assertions per F010 / F008 / F005 precedent. Full pytest suite must pass: ≥ 787 baseline + the new F011 tests, no regressions.

## Acceptance Criteria

1. **Skill registered in `spec/etc_sdlc.yaml`.** A `design` entry exists under the skills section with name, description mentioning impeccable wrap, role-tier, model defaults, and `primary_phase: design`. The entry indicates `/design` runs on the design side of the `(design | strategy)` mid-funnel branch, before `/spec`.
2. **`skills/design/SKILL.md` exists with correct frontmatter.** The file exists at `skills/design/SKILL.md` with frontmatter containing `name: design`, `primary_phase: design`, and a description mentioning "design phase wrapping impeccable" or equivalent.
3. **Five phase headers verbatim.** `skills/design/SKILL.md` contains the verbatim phase headers: `### Phase 1: Intent Capture`, `### Phase 2: Research`, `### Phase 2.5: Gray Area Resolution`, `### Phase 2.75: Threshold Check and Classification`, `### Phase 3: Iterative Spec Writing`, `### Phase 4: Validation`, `### Phase 5: Output`.
4. **Classifier constants identical to /spec and /architect.** `skills/design/SKILL.md` declares `FILL_RATIO_RESEARCH_ASSIST_MAX = 0.20`, `FILL_RATIO_REJECT_MIN = 0.50`, `UNFILLABLE_GAP_REJECT_CAP = 3` in a Tunable Constants section.
5. **Phase 1 documents 6 Socratic questions.** `skills/design/SKILL.md` Phase 1 documents 6 Pattern-B questions adapted for the design domain (e.g., visual identity, brand voice, user-flow shape, accessibility floor, hard constraints, role). Questions render via Pattern B (`---\n\n**▶ Your answer needed:**`) one at a time per `standards/process/interactive-user-input.md`.
6. **Phase 2 Step 0 allocator invocation.** `skills/design/SKILL.md` Phase 2 Step 0 documents the feature-id allocation: `python3 ~/.claude/scripts/feature_id.py allocate-next .etc_sdlc/features "<slug>"`. /design is the first phase to allocate `features/F<NNN>` when invoked first; /spec and /architect on the same feature inherit from state.yaml.
7. **Wrap-and-invoke contract documented.** `skills/design/SKILL.md` Phase 1 documents the contract: detect PRODUCT.md + DESIGN.md at repo root; if absent, dispatch `/impeccable teach` via the Skill tool (NOT subprocess); if present, surface a Pattern A picker with options Accept / Refine PRODUCT / Refine DESIGN / Start over. Documents impeccable version pinning ≥v3.0.7 with minor-patch tolerance.
8. **Phase 5 documents 6 output artifacts.** `skills/design/SKILL.md` Phase 5 documents writing: `gray-areas-design.md`, `state.yaml.design_phase` block (merge-preserve pattern), `value-hypothesis.yaml.design_author_role` field, `research/design-codebase.md`, `design-tokens.json`, `component-specs.md` — all under `<feature_path>/`.
9. **Git tag pattern documented.** `skills/design/SKILL.md` Phase 5 documents writing two git tags: `etc/feature/F<NNN>/design/start` (at Phase 5 entry) and `etc/feature/F<NNN>/design/done` (at Phase 5 successful close), via `python3 ~/.claude/scripts/git_tags.py write-tag`.
10. **File-watch contract documented.** `skills/design/SKILL.md` documents the file-watch contract for the impeccable browser-extension iteration loop: known JSON path (`~/.impeccable/last-session.json` OR `<feature_path>/design-iteration.json`, operator-selectable via `--sync-from`); reads at Phase 5 entry and on `/design --sync` operator command. MCP server, polling REST, and manual sync are explicitly NOT supported (cites GA-006).
11. **Conditional tier-0 contract documented.** `skills/design/SKILL.md` documents the conditional tier-0 promotion: `state.yaml.design_phase.tier_0_promoted: bool` is set to `true` when `/design` completes successfully on a feature with a user-facing surface (≥1 AC classified user-facing per F001's signal list). Cites the standards doc governing the tier-0 hook contract by path (F002 standards-doc citation pattern), not by duplicating inline. Documents that always-tier-0 mode is NOT supported (per GA-005).
12. **/design → /spec handoff documented.** `skills/design/SKILL.md` documents the handoff: `design-tokens.json` + `component-specs.md` written under `<feature_path>/`; `/spec` Phase 2 codebase research reads these when present; `/build` Step 6 dispatch context includes them alongside `spec.md` (mirrors F006 BR-005's design.md inclusion pattern).
13. **Unified `agents/design.md` exists.** A new agent definition at `agents/design.md` with frontmatter `primary_phase: design`, `model: opus`, `tools: Read, Grep, Glob, Write, Edit`, and a description spanning user-flow design + visual specs + design tokens + accessibility + interaction patterns (union of the two deprecated agents' scopes).
14. **`ux-designer` and `ui-designer` deprecation.** `agents/ux-designer.md` and `agents/ui-designer.md` retain their files on disk (forward-only — F001-F010 references continue to work) but gain a top-level `deprecated: true` frontmatter field with a redirect note pointing to `agents/design.md`. `spec/etc_sdlc.yaml` agent entries for both are updated with deprecation comments redirecting to `design`.
15. **install.sh impeccable preflight INFO.** `install.sh` contains the verbatim INFO line: `INFO: impeccable not detected. /design phase requires impeccable (etc F011+). Install via: npm install -g impeccable (or equivalent). Features without a /design phase work without it.` Check uses POSIX-portable detection (`command -v impeccable` or skill-directory existence check). Non-blocking — installation continues. Positioned AFTER F010's gh-stack preflight and AFTER the existing line-67 client-detection block.
16. **Test contract.** `tests/test_design_skill.py` exists with at least 10 grep-based contract tests covering BR-010 items (a)-(j): skill body 5-phase structure, classifier constants, Phase 1 6-question shape, wrap-and-invoke contract, gray-areas-design schema, state.yaml.design_phase block schema, git tag pattern, agent metadata at `agents/design.md`, install.sh preflight INFO verbatim, deprecation notes on `agents/ux-designer.md` and `agents/ui-designer.md`. Tests use pytest `tmp_path` + grep-based assertions per F005/F008/F010 precedent.
17. **Full pytest + compile + preservation + README.** Full pytest suite passes: ≥ 787 baseline tests + new F011 tests, no regressions. `python3 compile-sdlc.py spec/etc_sdlc.yaml` succeeds and emits byte-identical `dist/skills/design/SKILL.md` + `dist/agents/design.md`. NO F001-F010 release-notes.md, verification.md, task YAML, or other shipped artifacts modified. README.md updated with /design skill catalog entry, F011 in "What has been shipping" table at top, and lifecycle diagram + repo-structure mentions of the impeccable wrap.

## Edge Cases

1. **User-facing feature, operator skipped /design.** Operator runs `/spec` directly on a feature with user-facing surface, without invoking `/design` first. Behavior: `state.yaml.design_phase` block absent; `tier_0_promoted` defaults to `false`; tier-0 hook does NOT block edits. `/spec` Phase 1 surfaces a soft Pattern B warning: "User-facing signals detected but no `design_phase` in state.yaml — consider running `/design` first." Non-blocking; operator can proceed. Later `/design --retrofit <feature_path>` adds `design_phase` to the existing feature.

2. **impeccable not installed at `/design` invocation.** Detection at Phase 1 fails (no `impeccable` executable, no skill at `~/.claude/skills/impeccable/`). `/design` halts with operator-friendly Pattern B error: `impeccable not detected. /design requires impeccable. Install via: npm install -g impeccable (or equivalent). See install.sh preflight INFO from BR-009.` Same install instruction as BR-009.

3. **PRODUCT.md present, DESIGN.md absent (or vice versa).** Phase 1 detection finds one but not the other. Behavior: surface Pattern B status: "PRODUCT.md present, DESIGN.md missing. Dispatch `/impeccable teach` to generate the missing file, or confirm intentional asymmetry?" Operator chooses; legacy projects with partial impeccable setup accept the asymmetry by declining the dispatch.

4. **impeccable version too low.** `impeccable --version` returns < v3.0.7 (or a manifest indicating major version 2.x). `/design` halts with Pattern B upgrade instruction: `impeccable v<version> detected; /design requires ≥v3.0.7. Upgrade via: npm install -g impeccable@latest.` No auto-upgrade — operator runs manually.

5. **impeccable major-version bump post-F011 ship (e.g., v4.0).** `/design` Phase 1 detects major bump; halts with Pattern B warning: "impeccable v4.x detected; /design specced under v3.x. Per F011 GA-004, major-version bumps require re-spec to verify architectural alignment. Pin to >=3.0.7,<4.0.0 in your project lockfile, or re-spec F011 to validate v4 alignment." Forward-only: F011 does NOT auto-handle v4 since it shipped under v3.

6. **Designer iterates in browser extension but never invokes `/design --sync`.** Designer's decisions stay in `~/.impeccable/last-session.json` (or per-feature path) but never propagate to /design's state.yaml or feed into /spec. `/design` completes Phase 5 with the pre-sync impeccable state. **UX trap.** Mitigation: `/design` Phase 5 prints an explicit "If you iterated in the browser extension since last sync, run `/design --sync` and re-invoke /design before /spec runs" reminder.

7. **Re-invoking `/design` on a feature with existing `design_phase` block.** Operator runs `/design` on a feature where state.yaml already records `design_phase`. Surface Pattern A: `Resume from last accepted section` / `Start over (overwrite design_phase block)` / `Show current state and abort`. Mirrors /spec's draft-handling pattern. Default: resume.

8. **Cross-feature concurrent `/design` + `/spec` invocations.** Two operators run `/design` on Feature A and `/spec` on Feature B simultaneously. The POSIX-atomic allocator (per F001 BR-003) ensures each gets a distinct `F<NNN>`. No collision at the directory level. `/build`-time cross-feature collision detection is F015's R2 territory; F011 does not attempt it.

9. **Strategy-routed feature accidentally getting `/design` run.** A non-user-facing feature (routed through the `(design | strategy)` branch's strategy side) has `/design` invoked anyway. `/design` runs successfully but Phase 5's user-facing-surface detection finds no ACs with user-flow signals. `tier_0_promoted` is set to `false`. Result: harmless over-application; PRODUCT.md + DESIGN.md get written, but tier-0 hook doesn't enforce. Operator can manually delete the `design_phase` block from state.yaml to "undo" the routing if needed.

10. **Deprecated `ux-designer` or `ui-designer` agent gets Agent-tool-dispatched after F011 ships.** The deprecated agents still resolve (forward-only). Their bodies remain accessible on disk. Behavior: dispatch succeeds; agent runs its legacy workflow. Future PRD may add a runtime warning ("deprecated agent; consider `/design` or `agents/design.md`"). F011 explicitly does NOT remove the files.

11. **F009 lifecycle gap (active/ path resolution) hits F011.** The allocator creates `features/active/F011-...` but downstream `tasks.py` doesn't honor `active/` (per F010's verification.md follow-up #1). Workaround during /build: move feature directory from `active/` to flat path `features/F011-...` so `tasks.py` finds it. Same workaround F010 used; same harness-feedback item pending. Documented as a known limitation; not blocking for F011's spec phase.

12. **`/design` writes design-tokens.json + component-specs.md but `/spec` is run on a different feature.** Operator runs `/design` on Feature A, then runs `/spec "Build feature B"` on a completely unrelated feature. `/spec` Phase 2 codebase research checks for `<feature_path>/design-tokens.json` (Feature B's path) and finds it absent. Behavior: /spec proceeds without design context, exactly as it would for any non-/design-preceded feature. The Feature A artifacts stay in Feature A's directory and don't leak.
