# PRD: User-Flow Completeness for User-Facing Acceptance Criteria

## Summary

The `/spec` skill currently produces acceptance criteria phrased from a system perspective ("response is 201 with row X", "migration produces N rows"). This phrasing is necessary for backend assertions but creates a hidden failure mode for user-facing surfaces: an AC can be SATISFIED by a unit test that imports the target component directly while the navigation path that's supposed to lead a real user to that component is never wired up. The component compiles, its tests pass, and `spec-enforcer` returns COMPLIANT — but a user opening the app cannot reach the surface. This bug class shipped seven times in venlink-platform's F4 capability-entitlements build (19% of leaf tasks delivered orphan surfaces) and was caught only when the user opened the running app and tried to navigate to one of the new features.

This refactor adds a spec-time guardrail: every user-facing acceptance criterion must include a "User flow" sentence in the form `"As {role}, navigate from {parent route} via {affordance label}, complete {happy path}, observe {outcome}."` This sentence is a forcing function — it requires the spec author to mentally trace the user's path to the surface before the spec is finalized, which surfaces orphan-route gaps at AC authorship rather than at post-build manual testing. The intervention has three pieces: (a) a new process standard at `standards/process/user-flow-completeness.md` that defines the contract, the user-flow sentence form, and the surface-detection signals; (b) auto-detection logic added to `/spec` Phase 3 Acceptance Criteria drafting, which scans drafted ACs for user-facing signals (route paths, UI nouns, user verbs) and presents prefilled user-flow sentence drafts for the spec author to accept, refine, or mark not-user-facing; and (c) a Phase 4 Definition-of-Ready gate that warns when user-facing ACs lack user-flow sentences and requires an explicit YES/NO confirmation to proceed (allowing intentionally-deferred surfaces to ship without breaking the gate).

This PRD is **layer 1 of a three-layer defense in depth**. Layer 2 (verify-time spec-enforcer reachability evidence) and layer 3 (`/build` agent-dispatch wiring contract — `docs/agent-prompt-template.md`) are sibling PRDs that are explicitly out of scope here; this PRD's intervention is necessary but not sufficient on its own, and the other two layers will be specced separately. This PRD touches only the spec-authoring surface: `skills/spec/SKILL.md`, the new standards doc, `hooks/inject-standards.sh`, and a new contract test. No other skills, no spec-enforcer changes, no backfill of legacy PRDs.

## Scope

### In Scope
- A new process standard at `standards/process/user-flow-completeness.md` defining the user-facing-AC contract, the user-flow sentence form, the surface-detection signal list, the conflict-default rule (when signals conflict, default to user-facing), and the WARN-with-YES/NO-gate enforcement model.
- Edits to `skills/spec/SKILL.md` Phase 3 Acceptance Criteria drafting (Section #4 of the iterative spec writing flow): after the AC section is initially drafted, scan ACs for user-facing signals, present each detected user-facing AC with a prefilled user-flow sentence drafted from surrounding PRD prose, and prompt the author per AC to accept, refine, or mark not-user-facing.
- Edits to `skills/spec/SKILL.md` Phase 4 Definition of Ready: add a check that every user-facing AC has a User-flow sentence; on miss, present the offending AC list and prompt a YES/NO continue gate (default NO). The DoR check warns rather than hard-blocks so intentionally-deferred surfaces can ship.
- Citation of the new standard from the existing DoR checklist item "Has measurable acceptance criteria" by content anchor, not line number.
- A new HEREDOC section in `hooks/inject-standards.sh` titled "User-Flow Completeness for User-Facing ACs" placed alongside the existing process disciplines (after "Research Discipline"), with a 5-10 line summary and a "See `standards/process/user-flow-completeness.md` for the full rule" pointer.
- A new contract test file `tests/test_user_flow_completeness.py` with grep-based assertions over the compiled `dist/skills/spec/SKILL.md`, the new standards doc, and `hooks/inject-standards.sh`, verifying the standard exists, the user-flow sentence form is documented verbatim, the surface-detection signal list is present, the Phase 3 detection logic is documented in the skill, the Phase 4 gate is documented in the skill, and the citation from inject-standards.sh exists.
- Use of Pattern A (`AskUserQuestion`) for the per-AC accept/refine/not-user-facing decision and the Phase 4 YES/NO gate. Use of Pattern B (visual marker) for free-form refinements.
- Compile pipeline integration via existing `python3 compile-sdlc.py spec/etc_sdlc.yaml` — no compiler code changes; the recursive copy already ships edited skills and standards.

### Out of Scope
- **Layer 2 (verify-time):** spec-enforcer changes to require reachability evidence during the adversarial pass. A sibling PRD owns this.
- **Layer 3 (dispatch-time):** the "Wiring is part of the deliverable" clause for `docs/agent-prompt-template.md` and the `/build` Step 6 wiring pre-validation. A sibling PRD owns this. (The concomitant Block 3 harness feedback from 2026-05-01 belongs to Layer 3.)
- Backfill of legacy PRDs under `.etc_sdlc/features/*/spec.md`. The rule is forward-only; existing PRDs without user-flow sentences are unaffected. The user will hand-update legacy specs as needed.
- Build-time reachability lints, route-graph linters, or static analysis that mechanically verifies a route has callers.
- Runtime verification that the AC's `{affordance label}` matches actual UI text. The label is authored intent, not a runtime-checked string.
- Changes to other skills (`/build`, `/decompose`, `/implement`, `/init-project`, `/hotfix`).
- Changes to the `spec.md` output format. `/build` and `/implement` see the same artifact shape; only `/spec`'s production mechanism is extended.
- Reorganization of the `standards/` directory tier structure. The new doc lands in the existing flat `standards/process/` directory.
- Modifications to other process standards (`interactive-user-input.md`, `harness-feedback-loop.md`, etc.). They are read-only references.
- A taxonomy lock on what counts as a "user-facing surface" beyond the signal list documented in the new standard. The signal list is starter guidance; refinement happens through later /spec dogfood, not in this PRD.

## Requirements

### BR-001: User-Flow Completeness Standard Document
A new standards document MUST be created at `standards/process/user-flow-completeness.md`. The document MUST define:

- The contract: every user-facing acceptance criterion in a `/spec`-produced PRD includes a User-flow sentence in the canonical form `"As {role}, navigate from {parent route} via {affordance label}, complete {happy path}, observe {outcome}."`
- The surface-detection signal list (BR-002).
- The conflict-default rule: when an AC mixes user-facing and backend-only signals (e.g., "When the wizard submits, the API returns 201 with X"), it defaults to user-facing. The orphan-route failure mode lives precisely at this boundary.
- The WARN-with-YES/NO-gate enforcement model defined in BR-004.
- A worked example transforming the F4 AC-44 from system-perspective to a User-flow sentence.

The document MUST follow the existing `standards/process/` formatting convention (plain `# Title` and `##` headers; an optional "Status: MANDATORY" / "Applies to:" preamble matching `interactive-user-input.md`).

### BR-002: Phase 3 Auto-Detection of User-Facing ACs
`skills/spec/SKILL.md` Phase 3 Section #4 (Acceptance Criteria) MUST be extended with an auto-detection step that runs after the initial AC draft is produced and before the section-approval `AskUserQuestion`. The step scans each drafted AC for user-facing signals:

- **Strong user-facing signals:** route paths matching `/[a-z][a-z0-9/_$-]*` shape; UI nouns (`modal`, `page`, `wizard step`, `tab`, `button`, `drawer`, `menu`, `dialog`, `form`, `screen`, `panel`, `sidebar`, `link`, `card`); user verbs (`navigate`, `click`, `submit`, `see`, `view`, `open`, `select`, `enter`).
- **Strong backend-only signals:** ACs whose only assertions are HTTP status codes, database row counts, background-job behaviors, or pure migration outcomes — and which contain no UI noun and no user verb.
- **Conflict-default:** if any user-facing signal is present alongside backend-only signals, the AC is classified user-facing.

The signal list MUST appear verbatim in the new standards doc (BR-001) and MUST be referenced by name in the skill body (not duplicated inline).

### BR-003: Phase 3 User-Flow Sentence Elicitation
For each AC classified user-facing in BR-002, the skill MUST present the AC alongside a *prefilled draft* User-flow sentence inferred from PRD prose:

- `{role}` from the AC's grammatical subject or the PRD's stated user persona.
- `{parent route}` from Module Structure entries or adjacent ACs that name a route.
- `{affordance label}` from UI nouns mentioned in the AC text (e.g., a "Create Organization" button if the AC mentions the action).
- `{happy path}` from the AC's success criterion.
- `{outcome}` from the AC's measurable claim.

The author chooses one of three actions per AC via `AskUserQuestion` (Pattern A): **accept the draft** (sentence appended verbatim to the AC); **refine** (Pattern B free-form follow-up to capture changes, then re-prompt); **mark not-user-facing** (AC is recorded as `surface_status: backend_only` and no User-flow sentence is required). Every accepted or refined User-flow sentence MUST be appended to its parent AC in the final spec.

### BR-004: Phase 4 Definition-of-Ready Gate
`skills/spec/SKILL.md` Phase 4 (Validation) MUST add a check after the existing six DoR items: enumerate ACs flagged user-facing in Phase 3; if any user-facing AC lacks a User-flow sentence, the DoR check enters a gated WARN. The skill presents the offending AC list and prompts via `AskUserQuestion`:

- **No, fix the missing sentences first** (default; recommended) — the skill returns to Phase 3 AC editing.
- **Yes, ship without — these surfaces are intentionally deferred** — the skill records the deferral in the spec's Edge Cases section as a `surface_status: deferred` line per AC and proceeds to Phase 5.

The gate MUST NOT hard-block — backend-only or intentionally-unreleased surfaces are legitimate exceptions, but the YES selection is recorded so future readers can audit.

### BR-005: AC Checklist Anchor Citation
The DoR checklist in Phase 4 MUST reference the new standard from the existing item "Has measurable acceptance criteria" using a **content anchor** (no line numbers). The augmented checklist item MUST read: "Has measurable acceptance criteria. Every user-facing AC also includes a User-flow sentence per `standards/process/user-flow-completeness.md`."

### BR-006: hooks/inject-standards.sh Citation
`hooks/inject-standards.sh` MUST receive a new HEREDOC section titled `### User-Flow Completeness for User-Facing ACs` placed immediately after the existing `### Research Discipline` section. The new section is 5-10 lines summarizing the rule, ending with: `See standards/process/user-flow-completeness.md for the full rule.` The section MUST match the existing discipline-section format (paragraph or short bullet list, no special escaping).

### BR-007: Forward-Only Compatibility
The rule applies only to PRDs produced by `/spec` *after* this PRD ships. Legacy PRDs in `.etc_sdlc/features/*/spec.md` without User-flow sentences MUST NOT be flagged by `/spec` resume sessions, and MUST NOT cause the new Phase 4 gate to trigger when re-running `/spec` on a legacy slug. The user retains responsibility for hand-updating legacy specs.

### BR-008: Contract Test Coverage
A new test file `tests/test_user_flow_completeness.py` MUST exist and pass, containing at minimum:

- `test_standard_doc_exists` — confirms `standards/process/user-flow-completeness.md` exists and contains the canonical sentence form verbatim.
- `test_standard_documents_signal_list` — greps the standard for the strong-user-facing and strong-backend-only signal lists from BR-002.
- `test_skill_documents_phase_3_detection` — greps `dist/skills/spec/SKILL.md` for the Phase 3 detection step and the per-AC accept / refine / not-user-facing branch.
- `test_skill_documents_phase_4_gate` — greps the compiled skill for the WARN-with-YES/NO gate and the `surface_status: deferred` deferral path.
- `test_skill_cites_standard_in_dor_item` — greps the compiled skill for the augmented DoR checklist item per BR-005.
- `test_inject_standards_cites_new_doc` — greps `hooks/inject-standards.sh` for the new section title and the `standards/process/user-flow-completeness.md` pointer.
- `test_skill_uses_interactive_input_patterns` — greps the new Phase 3 / Phase 4 sections for `AskUserQuestion(` and the Pattern B marker `**▶ Your answer needed:**`.

### BR-009: Compile Pipeline Integration
`python3 compile-sdlc.py spec/etc_sdlc.yaml` MUST complete without error after the skill, standards, and hook edits. The compiled `dist/skills/spec/SKILL.md` MUST contain the new Phase 3 detection step and Phase 4 gate verbatim. No edits to `compile-sdlc.py` itself are required — the existing recursive copy already ships edited skills, standards, and hooks.

### BR-010: Interactive Input Standard Compliance
Every user-facing prompt added by this refactor MUST follow `standards/process/interactive-user-input.md`: per-AC accept / refine / not-user-facing decisions use Pattern A (`AskUserQuestion`); free-form refinements use Pattern B (visual marker); the Phase 4 YES/NO gate uses Pattern A. No prompt added by this PRD may be buried in prose.

## Acceptance Criteria

1. `standards/process/user-flow-completeness.md` exists at the named path and contains the canonical User-flow sentence form `"As {role}, navigate from {parent route} via {affordance label}, complete {happy path}, observe {outcome}."` verbatim.
2. The standards document enumerates the strong-user-facing signals (route paths matching `/[a-z][a-z0-9/_$-]*`; UI nouns including `modal`, `page`, `wizard step`, `tab`, `button`, `drawer`, `menu`, `dialog`, `form`, `screen`, `panel`, `sidebar`, `link`, `card`; user verbs including `navigate`, `click`, `submit`, `see`, `view`, `open`, `select`, `enter`) and the strong-backend-only signals (HTTP status codes only, DB rows only, background jobs only, no UI noun, no user verb).
3. The standards document states the conflict-default rule explicitly: when an AC mixes user-facing and backend-only signals (e.g., "When the wizard submits, the API returns 201 with X"), it defaults to user-facing.
4. The standards document includes a worked example transforming the F4 AC-44 from system-perspective to a User-flow sentence, citing venlink-platform's capability-entitlements feature directory as the origin of the rule.
5. `skills/spec/SKILL.md` Phase 3 Section #4 (Acceptance Criteria) contains an auto-detection step that runs after the initial AC draft is produced and references the signal list in `standards/process/user-flow-completeness.md` by name (not duplicated inline).
6. `skills/spec/SKILL.md` Phase 3 contains a per-AC `AskUserQuestion` with options "Accept the draft User-flow sentence (Recommended)", "Refine — I have changes", and "Mark this AC not-user-facing". The Refine branch dispatches a Pattern B (`**▶ Your answer needed:**`) follow-up.
7. `skills/spec/SKILL.md` Phase 4 contains a check that enumerates ACs flagged user-facing during Phase 3 and verifies each has a User-flow sentence appended; on miss, it presents the offending AC list as prose status output and prompts an `AskUserQuestion` with options "No, fix the missing sentences first (Recommended)" and "Yes, ship without — these surfaces are intentionally deferred".
8. `skills/spec/SKILL.md` Phase 4 documents the deferral path: when the author selects "Yes, ship without", the skill appends a `surface_status: deferred` line for each offending AC to the spec's Edge Cases section before proceeding to Phase 5, so future readers can audit the deferral.
9. `skills/spec/SKILL.md` Phase 4 DoR checklist item "Has measurable acceptance criteria" is augmented to read exactly: `Has measurable acceptance criteria. Every user-facing AC also includes a User-flow sentence per `standards/process/user-flow-completeness.md`.`
10. `hooks/inject-standards.sh` contains a new HEREDOC section titled `### User-Flow Completeness for User-Facing ACs` placed immediately after the existing `### Research Discipline` section. The new section is 5-10 lines and ends with the literal string `See standards/process/user-flow-completeness.md for the full rule.`
11. The PRD does NOT add any validator, hook, scanner, or skill step that retroactively scans `.etc_sdlc/features/*/spec.md` for User-flow compliance. Legacy specs without User-flow sentences are unaffected on disk. /spec resume sessions on legacy specs run the new Phase 3 detection, but the user retains per-AC dismissal and the Phase 4 deferral gate; no auto-modification of legacy spec.md content occurs without user approval. Verified by the absence of a retroactive scanner in the changed-file set.
12. A new test file `tests/test_user_flow_completeness.py` exists and contains, at minimum, the seven tests enumerated in BR-008. Running `pytest tests/test_user_flow_completeness.py -q` reports all tests passing.
13. `python3 compile-sdlc.py spec/etc_sdlc.yaml` completes without error after the skill, standards-doc, and hook edits. The compiled `dist/skills/spec/SKILL.md` contains the new Phase 3 detection step and Phase 4 gate verbatim. The compiled `dist/standards/process/user-flow-completeness.md` is byte-identical to the source.
14. Every user-facing prompt added by this refactor is attributable to either Pattern A (`AskUserQuestion(`) or Pattern B (`**▶ Your answer needed:**`). No new prompt is buried in prose; verified by a grep-based contract test in `tests/test_user_flow_completeness.py::test_skill_uses_interactive_input_patterns`.
15. Existing tests in the repository that touch `skills/spec/`, `hooks/inject-standards.sh`, or `standards/process/` continue to pass. Running `pytest tests/ -q` reports no new failures introduced by this refactor (regression baseline).

## Edge Cases

1. **PRD with zero user-facing ACs** — Phase 3 auto-detection finds no user-facing signals (e.g., a pure backend or migration PRD). The per-AC elicitation step is skipped entirely. Phase 4 gate evaluates "zero user-facing ACs" → trivially passes. Spec finalizes normally.
2. **PRD with all ACs flagged user-facing, all dismissed by author** — e.g., a backend-only PRD where the auto-detector raised false positives on UI-shaped vocabulary. The author marks every detected AC as not-user-facing during Phase 3 elicitation. Each AC records `surface_status: backend_only`. Phase 4 gate doesn't fire (no offending ACs).
3. **Author iteratively refines a User-flow sentence** — the Refine branch can be invoked multiple times for the same AC. Each refinement is a fresh Pattern B prompt; the latest accepted sentence overwrites prior drafts in the spec. There is no audit log of intermediate drafts (consistent with how /spec handles section refinement today).
4. **Conflict-default false positive on metaphor** — an AC mentions a UI-noun word in a non-UI sense (e.g., "mental *model*", "decision *menu*"). The signal scan flags the AC user-facing; the author marks not-user-facing during elicitation. The rule degrades cleanly to author judgment when signals are wrong.
5. **No clear parent route (top-level surface)** — for a brand-new top-level entry point (e.g., a new app section reachable from global nav, with no prior parent), the prefilled `{parent route}` is `/` or the app root. The author refines as needed during elicitation.
6. **Multiple parent routes for one surface** — a surface reachable from two affordances (e.g., main nav AND contextual menu). The canonical User-flow sentence covers one path; the author may either add multiple ACs (one per entry point) or use a single User-flow sentence with the most common entry path and a free-text note in the AC body about alternates. The standards doc documents both patterns.
7. **Legacy spec resumed under the new rule** — `/spec` resume on a feature directory whose spec.md predates this PRD runs Phase 3 detection on whatever ACs exist. If detection flags ACs as user-facing, the author has per-AC dismissal options and the Phase 4 deferral gate. No auto-modification of legacy spec.md content occurs without explicit author action. Per AC11, the PRD adds no retroactive scanner.
8. **Intentional gate bypass** — author selects "Yes, ship without — these surfaces are intentionally deferred" at the Phase 4 gate. The spec proceeds to Phase 5 with `surface_status: deferred` per offending AC. Future maintainers can audit the deferral lines and add User-flow sentences when the surface is actually wired up.
9. **AC already contains a manually-authored User-flow sentence** — the auto-detector should recognize the canonical `"As {role}, navigate from {parent route} via..."` prefix and skip the per-AC elicitation prompt for already-compliant ACs. Idempotency: re-running /spec on a fully-compliant spec adds nothing and prompts for nothing on this dimension. The skill body documents this idempotency rule.
10. **Compile pipeline fails after edits** — `python3 compile-sdlc.py spec/etc_sdlc.yaml` is required to succeed (AC13). If it fails, the source and dist/ are out of sync — the dist skill would not have the new Phase 3/4 logic, and the rule would silently not fire in installed harnesses. Treat compile failure as a P0 blocker; the PR cannot merge until compile passes.
11. **Non-web user-facing surface (email, webhook, CLI)** — emails the user receives, webhook payloads the user reads, CLI command flows. These are user-facing in a broader sense but lack web-UI navigation paths and clickable affordances. The standards doc explicitly scopes the rule to **web/app UI surfaces** and notes that analogous rules for other surface types are out of scope (future PRDs can extend the framework).
12. **Author refuses to run the new detection** — the author skips the AC section refinement entirely (existing /spec section-approval flow allows "Refine — I have changes" with the change being "remove the detection"). The skill follows author instruction; if the author later runs Phase 4, the gate fires on whatever user-facing signals remain. No silent suppression of the rule.

## Technical Constraints

- **File touchpoints (small, surgical):** the refactor edits two existing files (`skills/spec/SKILL.md`, `hooks/inject-standards.sh`) and creates two new files (`standards/process/user-flow-completeness.md`, `tests/test_user_flow_completeness.py`). No Python source changes outside the new test file. No edits to `compile-sdlc.py`, `feature_id.py`, `git_tags.py`, `value_hypothesis.py`, or any other script under `scripts/`.
- **Compile pipeline:** `python3 compile-sdlc.py spec/etc_sdlc.yaml` already recursively copies `skills/<name>/` → `dist/skills/<name>/` and `standards/<name>/` → `dist/standards/<name>/`. Running the compiler after the edits ships the new and modified files without compiler code changes.
- **Skill body is prose, not code:** `/spec` is a Markdown skill loaded by the runtime. "Auto-detection logic" and "Phase 4 gate" are agent instructions written in prose, not Python functions. The signal-list scan, the prefilled-sentence draft, and the per-AC prompt are all described as agent procedures the skill follows during the user's session.
- **Single source of truth for the rule:** `standards/process/user-flow-completeness.md` is the authoritative document for the canonical sentence form, the signal list, and the conflict-default rule. The skill body and `hooks/inject-standards.sh` reference the doc by path and MUST NOT duplicate the signal list inline; doc-first updates keep the two-and-a-half places in sync.
- **Pattern A / Pattern B compliance:** every new user-facing prompt added by this refactor follows `standards/process/interactive-user-input.md`. Per-AC accept/refine/not-user-facing decisions use Pattern A (`AskUserQuestion`); free-form refinements use Pattern B (visual marker); the Phase 4 YES/NO gate uses Pattern A.
- **Backward compatibility:**
  - The eight existing Phase 3 section names and their order are unchanged. The new detection step is added *within* Section #4 (Acceptance Criteria), after the initial draft and before the section-approval `AskUserQuestion`.
  - The six existing DoR checklist items in Phase 4 are unchanged in count and order. Only the wording of item #3 ("Has measurable acceptance criteria") is augmented with a citation to the new standard.
  - The `gray-areas.md` schema is unchanged; this PRD does not touch it.
  - The `spec.md` output format is unchanged; ACs simply contain User-flow sentences as additional content.
- **Forward-only application:** the rule applies only to new `/spec` runs. The PRD adds no validator, scanner, or hook that retroactively flags legacy specs in `.etc_sdlc/features/*/spec.md`. /spec resume on a legacy spec runs the new detection but the user retains per-AC dismissal and the Phase 4 deferral gate.
- **Test precedent:** contract tests follow `tests/test_spec_three_state.py` and `tests/test_init_project.py::TestSkillMdContract` — grep-based assertions over the compiled `dist/skills/spec/SKILL.md` and other repository files. No fixture-PRD interactive testing (Phase 4 is interactive; the contract tests verify skill *content*, not skill *behavior*).
- **Missing infrastructure:** `INVARIANTS.md` and `.etc_sdlc/antipatterns.md` do not exist in this repo. Both reads are conditional per the /spec skill's "Before Starting" section; absence is recorded in research notes, not blocked on.
- **Scope boundary marker:** the worked example in the standards doc cites venlink-platform F4 as the origin of the rule. Sibling PRDs for Layer 2 (spec-enforcer) and Layer 3 (`docs/agent-prompt-template.md` + `/build` Step 6) MUST be tracked outside this PRD's task list — this PRD's `Module Structure` enumerates only Layer 1 files.

## Security Considerations

This feature does not handle authentication, user input validation at system boundaries, data storage, file uploads, external APIs, or authorization. It is a documentation refactor of a developer-facing agent skill plus a new standards doc, a hook script edit, and a new contract test. None of the auto-populate categories from the `/spec` security table apply directly. The security-relevant considerations are:

- **Free-form refinement input flows verbatim into `spec.md`.** When the author refines a prefilled User-flow sentence via Pattern B, the input is appended to its parent AC in the spec.md file. Spec.md is plain Markdown consumed by `/build` and other agents — no markup interpretation, no `eval`, no template substitution. The same input sanitization the existing /spec flow applies to Pattern B free-form input (control-character strip; reasonable length cap consistent with the Phase 1 "Other" sanitization contract — cap the whole sentence at 512 chars and strip `\x00-\x1f\x7f`) MUST apply to User-flow sentence refinements. The skill body MUST document this.
- **No secret material.** The PRD does not read, write, or embed credentials, tokens, API keys, or secrets. The new standards doc is public-style content meant for repo and skill distribution.
- **Hook injection content is static.** `hooks/inject-standards.sh` adds a HEREDOC section with a fixed pointer string (`See standards/process/user-flow-completeness.md for the full rule.`). No user-controlled content flows into the hook output. The hook's existing `exit 0` / "cannot block subagent creation" guarantee is preserved.
- **Contract test is read-only.** `tests/test_user_flow_completeness.py` performs grep-style assertions over committed repository files. No network calls, no shell escapes, no file writes outside the pytest temp-dir fixtures.
- **Forward-only is a security-adjacent property.** Because legacy specs are not modified retroactively (AC11), there is no risk of the rule corrupting historical artifacts or invalidating audit trails. Pre-existing `spec.md` files retain their original content and `etc/feature/F<NNN>/spec` git tags. Audit reviewers can compare a pre-rule spec against a post-rule spec by file timestamp without ambiguity.
- **The signal-list scan is on author-supplied AC text.** Phase 3 detection scans AC prose for UI nouns and route-shaped strings. The AC text is authored by the spec author in their own /spec session — no untrusted external input enters this scan. Pathological inputs (an AC containing many UI nouns deliberately to trigger the detector) lead at most to the author dismissing the AC during elicitation; there is no execution of AC content, no parsing into a runtime structure.
- **No external network calls beyond the existing `/spec` web-research tool usage.** Phase 2 web research is unchanged by this refactor.
- **Citation integrity for the new standard.** Skill-body and inject-standards.sh references to `standards/process/user-flow-completeness.md` are free-form text strings, not runtime-fetched URLs. A misspelled path leads to a missing-file error if a downstream agent attempts to read the doc, not to a security issue.

## Module Structure

Files to create or modify:

- **Created:** `standards/process/user-flow-completeness.md` — the new tier-1 process standard (BR-001). Defines the canonical User-flow sentence form, the strong-user-facing and strong-backend-only signal lists, the conflict-default rule, the WARN-with-YES/NO-gate enforcement model, and a worked F4 AC-44 example.
- **Modified:** `skills/spec/SKILL.md` — Phase 3 Section #4 (Acceptance Criteria) gets a new auto-detection step + per-AC elicitation `AskUserQuestion` (BR-002, BR-003); Phase 4 Validation gets a new gate after the existing six DoR items (BR-004); the existing DoR checklist item #3 ("Has measurable acceptance criteria") gets the citation augmentation in BR-005; new prompts follow Pattern A / Pattern B per BR-010.
- **Modified:** `hooks/inject-standards.sh` — a new HEREDOC section titled `### User-Flow Completeness for User-Facing ACs` placed after the existing `### Research Discipline` section, ending with the literal pointer string `See standards/process/user-flow-completeness.md for the full rule.` (BR-006).
- **Created:** `tests/test_user_flow_completeness.py` — the seven grep-based contract tests enumerated in BR-008.
- **Created:** `.etc_sdlc/features/F001-user-flow-completeness/spec.md` — this PRD.
- **Created:** `.etc_sdlc/features/F001-user-flow-completeness/value-hypothesis.yaml` — outcome contract for the metrics layer (Phase 5 step 2).
- **Created:** `.etc_sdlc/features/F001-user-flow-completeness/state.yaml` — Phase 2.75 classification (`well-specified`) + `author_role: SME/PM`.
- **Created:** `.etc_sdlc/features/F001-user-flow-completeness/gray-areas.md` — sentinel file with the literal line "No gray areas identified — research findings are unambiguous."
- **Created:** `.etc_sdlc/features/F001-user-flow-completeness/research/` — at least `codebase.md` capturing the Phase 2 codebase exploration findings.
- **Created (byte-identical copy):** `spec/user-flow-completeness.md` — for browsability and backward compatibility.
- **Regenerated (not hand-edited):** `dist/skills/spec/SKILL.md`, `dist/standards/process/user-flow-completeness.md`, `dist/hooks/inject-standards.sh` — outputs of `python3 compile-sdlc.py spec/etc_sdlc.yaml` after the source edits.

Files explicitly NOT touched:

- `compile-sdlc.py` — the recursive copy already handles new and edited files; no compiler changes are required.
- Any skill other than `/spec` — `/build`, `/decompose`, `/implement`, `/init-project`, `/hotfix`, `/postmortem`, `/retrospective`, `/discovery`, `/roadmap` are unchanged.
- Any other doc under `standards/process/`, `standards/architecture/`, `standards/code/`, `standards/git/`, `standards/quality/`, `standards/security/`, or `standards/testing/` — read-only references.
- Spec-enforcer agent files and any verify-time logic — out of scope; Layer 2 sibling PRD.
- `docs/agent-prompt-template.md` — out of scope; Layer 3 sibling PRD.
- `/build` skill and its Step 6 wiring pre-validation — out of scope; Layer 3 sibling PRD.
- Legacy specs in `.etc_sdlc/features/*/spec.md` — forward-only (AC11).
- The `gray-areas.md` schema and surrounding /spec phases (Phase 2.5, Phase 2.75) — unchanged.
- `spec/etc_sdlc.yaml` — the skill is hand-authored Markdown, not YAML-generated.

## Research Notes

Key findings from Phase 2 research:

**Codebase:**
- `/spec` source: `skills/spec/SKILL.md` (single-file Markdown skill, ~957 lines). Phase 3 drafts 8 sections; Acceptance Criteria is slot #4. Phase 4 DoR checklist has 6 items; "Has measurable acceptance criteria" is item #3 — that's the natural anchor for the new check.
- `hooks/inject-standards.sh` is a HEREDOC of curated discipline sections (TDD / Code Standards / Architectural Rules / Process / Git Commit Discipline / Research Discipline). Each section is 5-15 lines plus a "See standards/<path>" pointer. Adding the new doc means adding one new HEREDOC section in the same shape.
- `standards/process/` is a flat tier — 12 docs, hyphen-cased filenames, plain `# Title` + `##` headers (no frontmatter except for `interactive-user-input.md`'s "Status: MANDATORY" preamble, which this new doc should match for parity).
- **Direct precedent:** `.etc_sdlc/features/spec-three-state-classification/spec.md` — same intervention class (doc edit to `skills/spec/SKILL.md` + new `tests/test_*.py` contract test + `compile-sdlc.py` ships it). This PRD's Module Structure mirrors it.
- Contract tests live in `tests/test_init_project.py::TestSkillMdContract` and `tests/test_spec_three_state.py` — grep-based assertions over compiled `dist/skills/spec/SKILL.md`. Same pattern fits here.
- `INVARIANTS.md` absent. `.etc_sdlc/antipatterns.md` absent. Both noted, neither blocks.

**Best Practices (light web pass — proposal is well-grounded in lived F4 experience):**
- The user-flow sentence form is a navigation-context augmentation of standard user-story acceptance criteria (Patton's story mapping; Cohn's user-story format). Industry-aligned.
- "Reachability vs implementation correctness" is a recognized class — Kent C. Dodds' testing trophy and the "orphan route" pattern in SPA codebases. This PRD's intervention sits one phase earlier than E2E tests would: at AC authorship.

**Antipatterns:** No `.etc_sdlc/antipatterns.md` file exists in this repo. Nothing to incorporate.

**Three-block context (from concomitant feedback):**
- This PRD is **Layer 1** of a three-layer defense in depth.
- **Layer 2** (verify-time): a sibling PRD will modify `spec-enforcer` to require reachability evidence during the adversarial pass — refusing COMPLIANT verdicts on user-facing ACs whose only evidence is a unit test that imports the target component directly.
- **Layer 3** (dispatch-time): a sibling PRD will add a "Wiring is part of the deliverable" clause to `docs/agent-prompt-template.md` and add a `/build` Step 6 pre-validation that confirms user-facing tasks list both the new file AND the parent wiring file in `files_in_scope`. Block 3 from the 2026-05-01 concomitant harness feedback belongs here.
- The three layers are complementary: Layer 1 catches missing user-flow contracts at spec-time; Layer 2 catches escapes at verify-time; Layer 3 catches agent drift at dispatch-time. Each catches a different failure mode; all three are needed.

**Process standards consulted:**
- `standards/process/interactive-user-input.md` — source of Pattern A and Pattern B rules; BR-010 enforces compliance.
- `standards/process/harness-feedback-loop.md` — defines the harness-feedback emission contract that produced this PRD's input.
- The skill's own existing Phase 3 and Phase 4 sections — source of the existing section-approval and DoR-checklist shapes that this refactor extends without breaking.

**Forward propagation note:**
- The "AI detects → presents → user confirms" pattern that this PRD uses for Phase 3 surface detection is a generally-applicable spec-time AI-assist pattern. It could later apply to gray-area surfacing, security consideration auto-population, edge-case enumeration, etc. Out of scope for this PRD; noted here for posterity.
