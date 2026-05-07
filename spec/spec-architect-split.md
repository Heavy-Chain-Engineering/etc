# PRD: /spec → /spec + /architect Phase Split (F006)

## Summary

F006 splits the existing `/spec` skill into two phases. `/spec` retains intent-only authorship (Summary, Scope, Requirements, Acceptance Criteria, Edge Cases) — the PM-natural sections. A new `/architect` phase owns architectural design (Architecture overview, Data model, API contracts, Module Structure, Technical Constraints, Security Considerations, Trade-offs) and produces `design.md` + 1–N ADRs in `docs/adrs/`. The existing `architect` agent at `agents/architect.md` becomes /architect's primary phase executor — currently invoked ad-hoc, F006 finally gives it a canonical workflow. /build's input contract widens to accept `spec.md` alone (legacy or non-engineering features) OR `spec.md` + `design.md` (engineering features), with a soft warning at Step 1c when engineering-implied ACs exist but no `design.md` is present.

The trigger is concrete: HCE has PMs, SMEs, engineers, and other roles using etc concurrently. Today's monolithic /spec forces every author to fill all 8 sections, including engineering content they may not have the depth for. PMs guess at Module Structure they can't author authoritatively; engineers reopen intent debates because they want to write Technical Constraints. The role mismatch breaks workflows now.

F006 is part of the longer SDLC vision: `research → ux → ui → spec → architect → build → release`. F006 unblocks position 4→5 of that chain. /ux and /ui phases are deferred to separate PRDs (F011+ when ready). Plugin packaging (`/etc:` namespace, commercial-distribution) is also deferred — etc stays a private commercial product distributed only to HCE customers.

**Coupling between /spec and /architect is soft (per GA-008):** /spec auto-detects engineering implications and recommends /architect; /build warns but proceeds when design.md is absent. Solo authors can skip /architect freely; teams will run it organically. **Solo-flag chains two phases (per GA-009):** `/spec --include-architect` runs /spec to completion then auto-invokes /architect, producing the same two-artifact structure as the team flow. **Each phase captures its own author_role (per GA-010):** value-hypothesis.yaml gains `spec_author_role` + `architect_author_role` fields. **Forward-only:** F001-F009 stay at single-file spec.md.

## Scope

### In Scope

- **Lighten `/spec`:** edit `skills/spec/SKILL.md` Phase 3 section ordering (lines 625-632) to keep sections 1-5 only. Move sections 6 (Technical Constraints), 7 (Security Considerations), 8 (Module Structure) out of /spec's authorship surface. Update Phase 4 DoR check to no longer require these three sections from /spec.
- **/spec auto-detect engineering implications:** at Phase 5 entry, scan ACs for engineering signal tokens (file paths, module names, API endpoints, DB schemas, User-flow sentences). When detected, surface a Pattern A AskUserQuestion: "Engineering implications detected. Run /architect now?" with options [yes-chain-now / yes-but-later / this-is-non-engineering / yes-and-mark-design-mandatory].
- **Create `/architect` skill** at `skills/architect/SKILL.md` mirroring `/spec`'s 5-phase structure: Phase 1 architect-style intent capture, Phase 2 architecture research, Phase 2.5 gray-area resolution, Phase 2.75 three-state classifier, Phase 3 7-section drafting (Architecture overview, Data model, API contracts, Module Structure, Technical Constraints, Security Considerations, Trade-offs), Phase 4 DoR validation, Phase 5 design.md + ADRs output.
- **Compile** `dist/skills/architect/SKILL.md` byte-identical via `compile-sdlc.py`.
- **Update `agents/architect.md`** metadata to declare `/architect` as the primary phase. The agent body (description, examples) stays as-is.
- **Update `/build` input contract** at `skills/build/SKILL.md`: Step 1c (NEW, after Step 1b) detects engineering ACs in spec.md + design.md absent; emits soft warning; PROCEEDS regardless. Step 6 dispatch context includes design.md content when present.
- **Per-phase artifacts in feature directory:** spec.md (lightened), design.md (new, optional), gray-areas-spec.md (new naming), gray-areas-architect.md (new), shared value-hypothesis.yaml + state.yaml with per-phase blocks, research/ subdirectory with per-phase findings.
- **Solo-author flag** `--include-architect` on /spec: chains two phases sequentially per GA-009.
- **Tests** at `tests/test_architect_skill.py` — contract tests for /architect skill structure, /build's Step 1c widening, /spec's auto-detect logic, the chained-flag, schema extensions.
- **Forward-only resolver:** path-resolution helper from F009 handles both legacy `gray-areas.md` (F001-F009) and new `gray-areas-spec.md` + `gray-areas-architect.md` (F010+).

### Out of Scope

- `/ux` phase (user flows, accessibility, journey maps) — separate PRD F011+ when ready.
- `/ui` phase (visual design, component variants, design tokens) — separate PRD F012+ when ready.
- Plugin packaging (`/etc:` namespace prefix, install.sh refactor) — separate PRD when commercial-distribution model crystallizes.
- Migration of F001-F009 specs to the new split (forward-only convention per BR-007 of F001).
- Renaming `agents/architect.md` (it stays at the same path; only metadata changes).
- Multi-design-alternative support (3 design candidates against same /spec, pick one). Future enhancement.
- ADR template invention — use `standards/architecture/adr-process.md` as-is per GA-002.
- Auto-generation of design.md from spec.md (LLM-derived design without operator interaction). /architect is interactive.
- Cross-feature ADR linking (one feature's ADR references another's). Future.
- Tunable per-phase `FILL_RATIO_*` constants — start matched per GA-005, divergence is future work.
- `--include-ux` / `--include-ui` flags on /spec — those land with their respective phase PRDs.

## Requirements

### BR-001: /spec section lightening

`skills/spec/SKILL.md` Phase 3 section ordering (lines 625-632) is reduced from 8 sections to 5: Summary, Scope (In/Out), Requirements (BR-NNN), Acceptance Criteria, Edge Cases. Sections 6 (Technical Constraints), 7 (Security Considerations), 8 (Module Structure) are removed from /spec's authorship surface. Phase 4 DoR check no longer requires these three sections in spec.md.

### BR-002: /spec engineering-implication detection

At Phase 5 entry (after Phase 4 DoR passes, before value-hypothesis.yaml write), /spec scans the accumulated ACs for engineering-signal tokens: explicit file paths (`src/`, `scripts/`, `agents/`, `skills/`), module names (camelCase or snake_case identifiers paired with import/use verbs), API endpoint patterns (`/api/`, HTTP method verbs), DB schema language (table, column, index, migration), or any AC carrying a User-flow sentence per F001 BR-002. When detected, /spec surfaces a Pattern A AskUserQuestion: "Engineering implications detected — run /architect now?" with options [yes-chain-now, yes-but-later, this-is-non-engineering, yes-and-mark-design-mandatory]. Operator answer is recorded in state.yaml.

### BR-003: /architect skill structure

A new skill at `skills/architect/SKILL.md` mirrors /spec's 5-phase structure:
- **Phase 1: Intent capture (architecture mode).** Read spec.md, ask 6 architect-style questions one at a time via Pattern B: (1) data flow, (2) module boundaries, (3) integration patterns, (4) non-functional requirements, (5) technology selection trade-offs, (6) author_role per GA-010.
- **Phase 2: Research.** Codebase exploration (existing patterns, prior ADRs in `docs/adrs/`, INVARIANTS.md if present, layer-boundaries.md, abstraction-rules.md), web research for architectural patterns, antipatterns check, research-fill of identified gaps.
- **Phase 2.5: Gray-area resolution.** One AskUserQuestion per gray area, sequential. Save to `gray-areas-architect.md`.
- **Phase 2.75: Three-state classifier.** Reuse `FILL_RATIO_RESEARCH_ASSIST_MAX = 0.20`, `FILL_RATIO_REJECT_MIN = 0.50`, `UNFILLABLE_GAP_REJECT_CAP = 3` constants from /spec. States: `well-architected | research-assisted | rejected`. Rejection writes `rejected-architect.md`.
- **Phase 3: Section drafting.** Iteratively draft 7 sections — Architecture overview, Data model, API contracts, Module Structure, Technical Constraints, Security Considerations, Trade-offs.
- **Phase 4: DoR validation.** Architect-specific checklist.
- **Phase 5: Output.** Write design.md to feature directory. Write 1–N ADRs to `docs/adrs/F<NNN>-<adr-slug>.md`. Append architect_author_role to value-hypothesis.yaml. Write git tags `etc/feature/F<NNN>/architect/{start,done}`.

### BR-004: /architect output artifacts

/architect Phase 5 produces (in feature directory):
- `design.md` — 7-section architecture document.
- 1–N ADRs at `docs/adrs/F<NNN>-<adr-slug>.md` (one per major architectural decision).
- `gray-areas-architect.md` — Phase 2.5 resolutions.
- `research/architect-codebase.md` — Phase 2 codebase findings.
- Updates to `state.yaml` (architect_phase block) and `value-hypothesis.yaml` (architect_author_role field).

### BR-005: /build Step 1c widening

`skills/build/SKILL.md` Step 1 grows a new sub-step Step 1c (after Step 1b's inline DoR check). Step 1c detects: "spec.md has engineering-signal tokens (per BR-002 list) + design.md is absent in the feature directory". When detected, /build emits a stderr warning of the form: `WARNING: spec.md implies engineering work but design.md is absent. Consider running /architect first. Proceeding with build using spec.md alone.` Build PROCEEDS regardless. When design.md IS present, /build Step 6 dispatch context includes design.md content alongside spec.md.

### BR-006: Per-phase artifacts in feature directory

The feature directory schema for new features (post-F006) contains: spec.md (intent-only), design.md (optional), gray-areas-spec.md, gray-areas-architect.md (optional), value-hypothesis.yaml (single file with both author_role fields), state.yaml (per-phase blocks), research/codebase.md + research/architect-codebase.md, verification.md, release-notes.md. Forward-only: F001-F009 retain single-file gray-areas.md and don't have design.md.

### BR-007: value-hypothesis.yaml schema extension

The `value-hypothesis.yaml` schema (per `scripts/value_hypothesis.py`) gains two new fields: `spec_author_role` and `architect_author_role`. The legacy `author_role` field is preserved for F001-F009 backward compatibility but deprecated for new features. Schema validator accepts both shapes.

### BR-008: state.yaml schema extension

The `state.yaml` schema gains per-phase blocks. /spec writes `spec_phase: { classification, phase_2_75_metrics, completed_at }`. /architect writes `architect_phase: { classification, phase_2_75_metrics, completed_at }`. /build's existing `build:` block from F005 is unchanged. Each phase merges its block via the merge-preserve pattern.

### BR-009: gray-areas naming + resolver compatibility

New features (post-F006) write `gray-areas-spec.md` and `gray-areas-architect.md`. F001-F009 retain `gray-areas.md`. The path-resolution helper at `scripts/feature_id.py::resolve_feature_path` (F009) is unchanged. /metrics SKILL.md is updated to look for both filename patterns.

### BR-010: Solo-flag --include-architect chains two phases

`/spec --include-architect` invocation runs /spec to completion (writes spec.md, value-hypothesis.yaml with spec_author_role, gray-areas-spec.md, state.yaml.spec_phase). On successful exit, /spec auto-invokes /architect with the just-written spec.md as input. /architect runs its 5 phases and writes design.md + ADRs + gray-areas-architect.md + state.yaml.architect_phase + value-hypothesis.yaml.architect_author_role. Two separate Phase 2.75 classifications. Two separate git tag pairs.

### BR-011: Test contract

A new test file `tests/test_architect_skill.py` mirrors F005/F008/F009 pattern. Tests cover: /architect skill body has all 5 phase headers, classifier constants present, /architect's PRD output format defines the 7 sections, ADR write path is correct, /build Step 1c warning fires when design.md is absent and engineering ACs present, /spec auto-detect logic recognizes the documented engineering-signal tokens, chained-flag invocation produces both spec.md and design.md, value-hypothesis.yaml schema validator accepts both legacy and new author-role shapes. ALL tests use pytest tmp_path; no real `.etc_sdlc/features/` touched.

### BR-012: Forward-only convention

F001-F009 specs continue to work unchanged. /build Step 1a still recognizes legacy single-file spec.md. F006 itself is authored using legacy `gray-areas.md`. New features after F006 ships use the new layout. Resolver handles both layouts gracefully.

## Acceptance Criteria

1. **/spec section count** — `skills/spec/SKILL.md` Phase 3 section ordering lists exactly 5 sections.
2. **/spec auto-detect step exists** — `skills/spec/SKILL.md` Phase 5 contains the engineering-implication detection AskUserQuestion.
3. **/architect skill exists with 5 phases** — `skills/architect/SKILL.md` exists at the source path with all 5 phase headers verbatim.
4. **/architect classifier constants** — `skills/architect/SKILL.md` declares the three `FILL_RATIO_*` constants.
5. **/architect Phase 3 sections** — `skills/architect/SKILL.md` Phase 3 documents the 7-section ordering.
6. **/architect Phase 5 outputs** — `skills/architect/SKILL.md` Phase 5 specifies all required write paths.
7. **architect agent declares /architect as primary phase** — `agents/architect.md` frontmatter contains `primary_phase: architect`.
8. **/build Step 1c widening** — `skills/build/SKILL.md` Step 1 contains the new Step 1c with the documented warning text.
9. **/build dispatch context includes design.md when present** — Step 6 dispatch prompts include design.md content alongside spec.md.
10. **value-hypothesis.yaml schema extension** — `scripts/value_hypothesis.py` accepts both legacy and new schemas.
11. **state.yaml schema extension** — Per-phase blocks `spec_phase:` and `architect_phase:` are written by their respective skills.
12. **gray-areas naming for new features** — /spec writes to `gray-areas-spec.md`, /architect writes to `gray-areas-architect.md`.
13. **Solo-flag --include-architect** — `/spec --include-architect` chains two phases sequentially.
14. **Compile parity** — All three SKILL.md source/dist diffs exit 0 after compile-sdlc.py.
15. **Test file with required coverage** — `tests/test_architect_skill.py` exists with at least 8 test functions covering the BR-011 list.
16. **Forward-only invariant** — F001-F009 paths and schemas continue to work unchanged.
17. **Regression baseline** — full pytest suite passes (≥ 749 baseline + new F006 tests, no regressions).
18. **Preservation + changeset scope** — Only the documented files modified.

## Edge Cases

1. **F006 itself uses the legacy schema.** F006's own /spec run writes `gray-areas.md` because F006 hasn't shipped yet — the new naming convention applies to features authored AFTER F006 ships.
2. **Spec with no engineering implications.** /spec's Phase 5 auto-detect finds no signals; doesn't surface "Run /architect?" question. /build proceeds normally.
3. **Operator picks "this-is-non-engineering."** /spec records the answer; /build's Step 1c still warns but proceeds.
4. **/architect on a rejected /spec.** /architect Phase 1 finds spec.md absent → exits non-zero with stderr.
5. **/architect Phase 2.75 rejected.** Produces `rejected-architect.md`; design.md NOT written; /build warns but proceeds.
6. **/architect rejected after /spec already shipped.** Operator can re-run /architect or proceed without it.
7. **/spec --include-architect with /spec rejection.** Chain breaks at /spec rejection.
8. **/spec --include-architect with /architect rejection.** spec.md preserved; operator can re-run /architect or proceed.
9. **F001-F009 spec.md format with new /build.** Step 1c warning fires (cosmetic) but build proceeds.
10. **Mixed legacy + new features.** Resolver handles both layouts gracefully.
11. **Concurrent /spec and /architect on different features.** Allocator atomicity guarantees distinct F<NNN>.
12. **Repeat /architect on same feature.** Second run overwrites design.md; ADRs are append-only.
13. **F006's solo-flag during F006's own /spec.** Auto-detect doesn't fire because /architect doesn't exist yet.
14. **Legacy single-author_role on a new feature.** Validator accepts; field coexists with new fields.
15. **state.yaml without spec_phase block.** F001-F009 use top-level fields; new features use per-phase blocks; both coexist.

## Technical Constraints

- **Forward-only convention** (BR-007 of F001 + reaffirmed across F002-F009).
- **`git mv` mandate** (per F009) for state transitions.
- **Sonnet/Opus-1M child-dispatch workaround** — `model: opus` override on every Agent-tool call.
- **Pure Python stdlib** for scripts.
- **Byte-identical compile invariant** via `compile-sdlc.py`.
- **F002 standards-doc citation pattern** — /architect cites adr-process.md, abstraction-rules.md, layer-boundaries.md by path.
- **F002 test fixture pattern** — autouse compile fixture + Pyright workaround.
- **PEP 686 future-proofing** — `encoding="utf-8"` explicit.
- **Pyright workaround inventory** — accumulated across F005/F007/F009.
- **Solo-flag in-session chain** (not subprocess).
- **Soft-default warning text exact** for /build Step 1c (test contract).
- **No INVARIANTS.md, no `.etc_sdlc/antipatterns.md`** — both absent.

## Security Considerations

1. **Engineering-signal regex DoS posture.** Simple regexes (no nested quantifiers, no backreferences). No catastrophic-backtracking risk.
2. **Per-phase author_role sanitization.** Cap at 64 chars, strip control chars (regex `[\x00-\x1f\x7f]`). Mirrors F001 contract.
3. **ADR file path constructor uses argv-style invocation.** Path constructed via `Path(...) / f"F{nnn}-{slug}.md"`; slug sanitized via `feature_id.py::slugify`.
4. **/build Step 1c warning text passthrough.** Operator-controlled spec content sanitized (control chars + 256-char cap) before stderr emit.
5. **Solo-flag chain doesn't escalate privilege.** Skill-tool invocation reuses /spec's auth context.
6. **value-hypothesis.yaml validator rejects unknown fields.** Backward compat preserves legacy `author_role`; new spec_/architect_ fields added to known-fields set.
7. **/architect's gray-area resolution is operator-driven.** Pattern A AskUserQuestion; never auto-resolved.
8. **No ADR cross-feature linking yet.** Per Out-of-Scope.
9. **Test fixture isolation.** pytest tmp_path; no real `.etc_sdlc/features/` or `docs/adrs/` touched.

## Module Structure

### Created

- `skills/architect/SKILL.md` — new ~1200-line skill body mirroring /spec's 5-phase structure.
- `dist/skills/architect/SKILL.md` — compiled output via `compile-sdlc.py` (byte-identical).
- `tests/test_architect_skill.py` — new contract test module (~350-450 lines).

### Modified

- `skills/spec/SKILL.md` — Phase 3 section reduction (8→5), Phase 5 auto-detect, schema-write updates.
- `skills/build/SKILL.md` — Step 1c added; Step 6 dispatch context expanded.
- `agents/architect.md` — frontmatter `primary_phase: architect` field added.
- `scripts/value_hypothesis.py` — schema extension for both legacy and new author_role shapes.
- `dist/skills/spec/SKILL.md`, `dist/skills/build/SKILL.md`, `dist/agents/architect.md` — compiled outputs (byte-identical).

### Created at /spec time (already exist)

- `.etc_sdlc/features/F006-spec-architect-split/spec.md` — this PRD.
- `.etc_sdlc/features/F006-spec-architect-split/value-hypothesis.yaml` — outcome contract (LEGACY single-`author_role` schema).
- `.etc_sdlc/features/F006-spec-architect-split/state.yaml` — Phase 2.75 classification + author_role (legacy schema).
- `.etc_sdlc/features/F006-spec-architect-split/gray-areas.md` — 10 entries (7 research + 3 user). LEGACY single-file naming.
- `.etc_sdlc/features/F006-spec-architect-split/research/codebase.md` — Phase 2 codebase findings.
- `spec/spec-architect-split.md` — byte-identical copy.

### NOT in scope (do not touch)

- `agents/*.md` other than `architect.md` (frontmatter only).
- `skills/*.md` other than `spec`, `architect` (NEW), `build`.
- `hooks/*.sh`, `standards/process/*.md`, other scripts.
- `.etc_sdlc/features/F001-F009*` directories — forward-only.
- `install.sh` — no changes needed.
- Cross-feature ADR linking, multi-design alternatives, /ux, /ui, plugin packaging — all deferred.

## Research Notes

**Codebase findings (Phase 2):**
- `skills/spec/SKILL.md:625-632` is the section ordering line range for /spec lightening.
- `agents/architect.md` is a fully-defined agent ready as /architect's primary executor (description + 3 examples).
- `standards/architecture/adr-process.md` exists; F006 cites it. Sibling docs `abstraction-rules.md`, `layer-boundaries.md` also exist.
- `skills/build/SKILL.md:100,115` is the Step 1a + Step 1b region; F006 inserts Step 1c after.
- `scripts/value_hypothesis.py` schema validator extends to accept both schemas (backward compat for F001-F009).

**Best Practices (precedent):**
- F002 standards-doc citation pattern.
- Forward-only convention (BR-007 of F001).
- F009 path-resolution helper handles multi-location lookup.
- F005/F008/F009 test pattern (pytest tmp_path + subprocess).

**Antipatterns:** No `.etc_sdlc/antipatterns.md` file exists; absence noted.
