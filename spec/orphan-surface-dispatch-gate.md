# PRD: Layer 3 — Dispatch-time Wiring Contract for /build Agents

## Summary

The `/build` skill is the harness's wave-by-wave conductor: it dispatches one agent per leaf task via the Agent tool, with a strict prompt contract (`requires_reading` + `files_in_scope` + acceptance criteria + the standard "Dispatch hooks will enforce TDD, invariants, required reading, and phase gate" instruction). The dispatched agents are scoped: they may only read/edit files explicitly listed in `files_in_scope`, and they shouldn't escalate scope without telling the orchestrator. This scoping discipline is load-bearing for parallel-agent safety and context budget. But it has a structural blind spot for one specific class of work: **creating a new user-facing surface** (a route, modal, wizard step, sidebar entry, settings rail) typically requires editing TWO files — the new component AND the parent file that wires the user's affordance to it. When `/decompose` produces a task whose `files_in_scope` lists only the new component, the dispatched agent has no scope to make the wiring edit and no instruction telling it to. It ships the component, writes a passing unit test that imports the component directly, and reports success. The contract permits an unreachable surface to exist in main.

This was the structural cause of the F4 capability-entitlements failure — 7 of 36 leaf tasks (19%) shipped orphan surfaces past a verified-COMPLIANT spec-enforcer pass. F001 (Layer 1 — done) addresses this at AC authorship time by requiring User-flow sentences in the AC. F002 (Layer 2 — done) addresses it at verify time by requiring spec-enforcer to find reachability evidence for User-flow-sentenced ACs. **F003 (Layer 3 — this PRD) addresses it at dispatch time, which is the moment of creation: when `/build` is about to invoke an agent on a task whose AC carries a User-flow sentence, it inspects `files_in_scope`, runs a heuristic to identify the parent wiring file, and either auto-adds the parent file to scope or prompts the operator if the heuristic is ambiguous.** The dispatched agent now sees both files in scope and a wiring-contract clause in the prompt explaining that user-visible surfaces are not done until they're wired into the parent navigation graph in the same commit.

This PRD has three pieces. (a) A new "Dispatch-time Wiring Contract" section appended to the existing F001+F002 standards doc at `standards/process/user-flow-completeness.md` — co-locating all three layers in one canonical doc continues the established pattern. (b) An edit to `skills/build/SKILL.md` Step 6 dispatcher (lines 369-376) that adds the auto-add-parent-file heuristic, the operator-prompt fallback for ambiguous cases, and the wiring-contract clause appended to every Agent dispatch prompt for tasks with User-flow-sentenced ACs. (c) A contract test file `tests/test_orphan_surface_dispatch_gate.py` with grep-based assertions that the heuristic logic is documented in the skill body, the standards doc has the new section, and the dispatcher prompt cites the standards doc by path. **The trigger condition is F001-aware**: only tasks whose AC contains the canonical `As {role}, navigate from` prefix activate the wiring check; legacy specs pass through unchanged. **The strictness mode is auto-add-with-prompt-on-ambiguity**: the heuristic resolves obvious cases (sidebar-nav, parent-route, barrel exports) without operator interaction; it prompts only when the candidate set is empty or has multiple plausible matches. This completes the three-layer orphan-surface defense: F001 catches at AC time, F002 catches at verify time, F003 catches at the moment of creation.

## Scope

### In Scope
- Append a new `## Dispatch-time Wiring Contract` section to `standards/process/user-flow-completeness.md` (the existing F001+F002 doc) defining: the trigger condition (User-flow sentence presence on a task's AC), the wiring-contract clause that gets injected into the dispatched agent's prompt, the auto-add-parent-file heuristic and its preference order, the operator-prompt fallback on ambiguity, and the parent-file-detection signal list (sidebar-nav files, parent-route files, barrel exports, settings-rail config files).
- Edits to `skills/build/SKILL.md` Step 6 dispatcher (lines 336-423, specifically the per-task dispatch block at lines 367-376) to:
  - Detect tasks whose AC contains a User-flow sentence (canonical prefix `As {role}, navigate from`).
  - For detected tasks, run the parent-file heuristic against the deliverable directory tree to identify candidate wiring files.
  - If heuristic finds exactly one strong candidate, auto-add it to the task's `files_in_scope` and document the addition in the dispatch prompt.
  - If heuristic finds zero or multiple plausible candidates with no clear winner, prompt the operator via Pattern A `AskUserQuestion` to select the parent file.
  - Append the wiring-contract clause to every dispatched agent prompt for User-flow-sentenced tasks, citing the standards doc by path.
  - Preserve existing dispatch shape (Agent-tool call, post-dispatch handling, parallel fan-out).
- A new contract test file `tests/test_orphan_surface_dispatch_gate.py` with grep-based assertions over the standards doc + compiled `dist/skills/build/SKILL.md` confirming the new section exists, the heuristic is documented, and the dispatcher prompt cites the standards doc by path.
- Compile pipeline integration via existing `python3 compile-sdlc.py spec/etc_sdlc.yaml` — no compiler edits.
- Forward-only behavior: legacy tasks without User-flow sentences pass through unchanged.

### Out of Scope
- **Layer 1 (F001 — done).** AC authorship gate. Sibling.
- **Layer 2 (F002 — done).** Verify-time spec-enforcer reachability evidence. Sibling. `agents/spec-enforcer.md` MUST stay untouched.
- **Editing `docs/agent-prompt-template.md`.** That file is a venlink-platform convention; it does not exist in the etc repo. The brief's literal proposal is replaced by GA-001's research-decided alternative (extend the F001+F002 standards doc).
- **Modifications to `/decompose`.** GA-003 decided dispatch-time-only enforcement; /decompose stays unchanged.
- **Heuristic that runs without User-flow sentence.** GA-004 decided F001-aware trigger only; tasks with structural-but-not-AC-flagged user-facing files do NOT trigger this layer. Layer 3 catches what F001 declared user-facing.
- **Backfill of legacy tasks in flight.** Forward-only per harness convention.
- **A retroactive scanner across `.etc_sdlc/features/*/spec.md`** to retroactively re-flag tasks. The PRD adds no such scanner.
- **Modifications to other agent definitions.** sem, technical-writer, frontend-developer, backend-developer, etc. are unchanged.
- **Modifications to other skills.** /spec, /implement, /metrics, /hotfix, /postmortem, /retrospective, /discovery, /roadmap, /init-project, /tasks are unchanged.
- **Modifications to F001's User-flow sentence form, signal lists, conflict-default rule.** Layer 3 reads them; doesn't change them.
- **Modifications to F002's reachability evidence taxonomy** in the standards doc. Layer 3 lives alongside it as a peer section.
- **Changes to `/build` Steps 1-5, 7, 8.** Only Step 6 (the dispatcher) is touched.
- **Changes to the Agent-tool dispatch shape.** Same `subagent_type` + `prompt` arguments; just the prompt content is augmented.
- **Heuristic implementation in pure Python.** /build's Step 6 is Markdown agent-instruction prose; the heuristic is described as a procedure the dispatcher follows, not a Python function.
- **Tier reorganization of `standards/`.** New content lands as an appended section to the existing F001+F002 doc.
- **Windows install bug fixes.** Separate stream (captured in memory).

## Requirements

### BR-001: Dispatch-time Wiring Contract Section in user-flow-completeness.md
A new section MUST be appended to `standards/process/user-flow-completeness.md` titled `## Dispatch-time Wiring Contract` (or equivalent header reflecting the same concept). The section MUST define:

- The trigger: a task's acceptance criterion contains a User-flow sentence (canonical prefix `As {role}, navigate from`) — this is the only condition that activates the wiring check.
- The wiring contract: when an agent is dispatched on a User-flow-sentenced task, the dispatched agent receives an additional clause in its prompt stating that creating a route, modal, tab, sidebar entry, settings rail entry, or multi-step form step is incomplete until it has been wired into the parent navigation graph in the same commit.
- The auto-add-parent-file heuristic with its preference order:
  1. **Sidebar-nav config files** matching paths like `**/layout/sidebar-nav.*` or `**/nav/sidebar.*`
  2. **Parent-route files** matching the new component's route prefix (e.g., new file at `routes/_auth/admin/orgs/new/...` → parent at `routes/_auth/admin/orgs/index.*`)
  3. **Barrel exports** (`index.ts`, `index.tsx`, `mod.rs`) that already export sibling components in the same dir
  4. **Settings-rail / tab-array config files** matching `**/tabs/*` or `**/settings/*` config patterns
- The operator-prompt fallback: when the heuristic finds zero candidates, OR multiple candidates with comparable confidence, /build prompts the operator via Pattern A `AskUserQuestion` to select the parent wiring file from the candidate set (or "skip — this surface is intentionally orphaned" as an explicit deferral option).
- The parent-file-detection signal list MUST appear verbatim in the standards doc and MUST be referenced by name from the skill body (not duplicated inline, per the F001/F002 single-source-of-truth pattern).
- A scope note that backend-only ACs and ACs without User-flow sentences pass through unchanged.

### BR-002: User-Flow Sentence Detection in /build Step 6
`skills/build/SKILL.md` Step 6 (specifically the per-task dispatch block at lines 367-376) MUST be extended with an explicit detection step that recognizes the canonical User-flow sentence prefix (`As ` followed later in the same sentence by `, navigate from`) in each task's AC list. Detected tasks trigger the wiring check; non-detected tasks dispatch unchanged.

### BR-003: Auto-Add Parent File Heuristic
For each detected user-facing task, /build Step 6 MUST run the parent-file heuristic in BR-001's prescribed preference order, stopping at the first form found. The heuristic operates by inspecting the deliverable directory tree (the user's project, not the etc repo) using `Glob` and `Grep` against the patterns in BR-001's signal list. When the heuristic finds:
- **Exactly one strong candidate** → /build auto-adds it to the task's `files_in_scope` (mutates the task YAML on disk via `tasks.py` or in-memory via the dispatcher), notes the addition in a status message, and proceeds with dispatch.
- **Zero candidates** → /build invokes the operator prompt (BR-004).
- **Multiple plausible candidates** (more than one match in the same heuristic tier with no clear winner) → /build invokes the operator prompt (BR-004).

### BR-004: Operator-Prompt Fallback
When the heuristic in BR-003 cannot resolve, /build MUST prompt the operator via Pattern A `AskUserQuestion` with options:
- Each candidate parent file from the heuristic, listed as a separate option (when there are 2-3 candidates)
- "None of the above — let me name a custom parent file" (uses `AskUserQuestion`'s automatic Other escape hatch)
- "Skip this check — this surface is intentionally orphaned (e.g., not yet user-reachable, deferred for later)" — selecting this records a `surface_status: deferred` line on the task YAML before dispatch and proceeds without a parent file.

The operator's selection is recorded in the task's `files_in_scope` (or noted as deferred). /build then dispatches the agent with the augmented scope.

### BR-005: Wiring-Contract Clause in Dispatched Agent Prompts
When /build Step 6 dispatches an agent on a User-flow-sentenced task (whether the parent file was auto-added or operator-selected), the prompt sent to the agent MUST include the wiring-contract clause:

> Your task creates a user-facing surface (route/modal/tab/sidebar entry/wizard step) per the User-flow sentence in your AC. The surface is NOT done until it is wired into the parent navigation graph in the SAME commit as the new surface. Your `files_in_scope` includes the parent wiring file at `<path>` for this purpose. Before reporting success, run `grep -rn "<your-route-or-component-name>" <project>/frontend/src` (or the equivalent for your stack) and confirm at least one parent surface references it via `<Link>`, `<Tab>`, sidebar-config entry, or equivalent. If the parent file does not contain a working reference after your edits, do not report success. See `standards/process/user-flow-completeness.md` (Dispatch-time Wiring Contract section) for the full rule.

The clause MUST cite `standards/process/user-flow-completeness.md` by path and MUST NOT duplicate the heuristic logic inline.

### BR-006: Skill-Body Citation of Standards Doc
`skills/build/SKILL.md` Step 6 MUST reference `standards/process/user-flow-completeness.md` (specifically the new Dispatch-time Wiring Contract section) by path in the new detection + heuristic + clause-injection logic. The signal lists and contract details MUST NOT be duplicated inline; the standards doc is the single source of truth.

### BR-007: Forward-Only Behavior
The wiring check fires only on tasks whose AC contains a User-flow sentence (per GA-004 + F001 BR-007). Tasks without User-flow sentences (legacy specs predating F001, backend-only ACs, or ACs explicitly marked `surface_status: backend_only`) pass through dispatch unchanged. The PRD adds no validator, scanner, or skill step that retroactively flags legacy specs in `.etc_sdlc/features/*/spec.md`.

### BR-008: Preservation of Dispatch Shape
The `Agent({...})` invocation shape, the `subagent_type` argument, the post-dispatch result handling (Step 6b "Wait for wave completion"), the per-wave parallel fan-out discipline, the task-status updates via `tasks.py set-status`, and the phase-N/start + phase-N/done tag writes are ALL unchanged. Only the prompt text content is augmented for User-flow-sentenced tasks.

### BR-009: Contract Test Coverage
A new test file `tests/test_orphan_surface_dispatch_gate.py` MUST exist and pass, containing at minimum:
- `test_standard_doc_has_dispatch_wiring_section` — confirms `standards/process/user-flow-completeness.md` contains a `## Dispatch-time Wiring Contract` section (or equivalent) and the canonical User-flow sentence prefix `As {role}, navigate from` referenced verbatim.
- `test_standard_doc_documents_heuristic_signal_list` — greps the standards doc for the four-tier preference order (sidebar-nav, parent-route, barrel-exports, settings-rail/tab-array config).
- `test_standard_doc_documents_operator_prompt_fallback` — greps for the AskUserQuestion fallback language and the `surface_status: deferred` deferral option.
- `test_build_skill_documents_dispatch_detection` — greps `dist/skills/build/SKILL.md` Step 6 region for the User-flow sentence detection step (literal `As ` + `, navigate from` references).
- `test_build_skill_documents_heuristic_invocation` — greps the compiled skill for the heuristic procedure description and the auto-add-with-prompt-fallback logic.
- `test_build_skill_documents_wiring_contract_clause` — greps the compiled skill for the wiring-contract clause text that gets injected into dispatched agent prompts.
- `test_build_skill_cites_standards_doc` — greps the compiled skill for `standards/process/user-flow-completeness.md` by path in the Step 6 region.
- `test_build_skill_preserves_existing_dispatch_shape` — confirms the existing Step 6 dispatch construction (Agent-tool call shape, subagent_type, post-dispatch handling) is preserved verbatim around the new logic.

### BR-010: Compile Pipeline Integration
`python3 compile-sdlc.py spec/etc_sdlc.yaml` MUST complete without error after the standards-doc and skill edits. The compiled `dist/skills/build/SKILL.md` and `dist/standards/process/user-flow-completeness.md` MUST be byte-identical to their sources. No edits to `compile-sdlc.py` are required.

### BR-011: Pattern A / Pattern B Compliance
The operator-prompt fallback (BR-004) uses Pattern A `AskUserQuestion` per `standards/process/interactive-user-input.md`. No prompts added by this PRD may be buried in prose. The wiring-contract clause injected into dispatched agent prompts (BR-005) is NOT a user-facing prompt — it's text the dispatcher includes in its `Agent({prompt: ...})` payload, addressed to the dispatched agent. Pattern A/B rules apply only to user-facing prompts.

## Acceptance Criteria

1. `standards/process/user-flow-completeness.md` contains a new `## Dispatch-time Wiring Contract` section appended after the F002 Reachability Evidence section, naming the trigger condition (User-flow sentence presence on a task's AC) verbatim.
2. The Dispatch-time Wiring Contract section documents the wiring-contract clause that gets injected into dispatched agent prompts, with verbatim text matching BR-005's clause.
3. The Dispatch-time Wiring Contract section enumerates the four-tier auto-add heuristic preference order: (1) sidebar-nav config files, (2) parent-route files matching the new component's route prefix, (3) barrel exports, (4) settings-rail / tab-array config files. The four tier names appear verbatim.
4. The Dispatch-time Wiring Contract section documents the operator-prompt fallback contract (per BR-004): the prompt is a Pattern A `AskUserQuestion` listing each candidate parent file as a separate option, plus an "intentional orphan" deferral option that records `surface_status: deferred`.
5. `dist/skills/build/SKILL.md` Step 6 contains a User-flow sentence detection step that recognizes the canonical prefix `As ` + `, navigate from` in each task's AC list. Detected tasks trigger the wiring check; non-detected tasks dispatch unchanged.
6. `dist/skills/build/SKILL.md` Step 6 documents the auto-add heuristic procedure in BR-001's prescribed preference order and the three resolution outcomes (exactly-one → auto-add; zero → operator prompt; multiple → operator prompt).
7. `dist/skills/build/SKILL.md` Step 6 contains the verbatim wiring-contract clause from BR-005 that the dispatcher appends to the prompt of every dispatched agent on a User-flow-sentenced task.
8. `dist/skills/build/SKILL.md` Step 6 references `standards/process/user-flow-completeness.md` by path in the new dispatch logic. The signal lists and contract details are NOT duplicated inline.
9. `dist/skills/build/SKILL.md` Step 6's existing dispatch shape is preserved: the `Agent({...})` invocation form, the `subagent_type` argument from the task's `assigned_agent` field, the per-wave parallel fan-out, the post-dispatch result handling at Step 6b, the task-status updates, and the phase-N/start + phase-N/done tag writes all match the pre-edit state byte-equivalently around the new logic.
10. The wiring-contract clause cites `standards/process/user-flow-completeness.md` by path within the clause body. The dispatched agent reading the clause sees a path it can Read for the full rule.
11. The PRD adds no validator, scanner, or skill step that retroactively scans `.etc_sdlc/features/*/spec.md` for wiring compliance. Legacy specs and ACs marked `surface_status: backend_only` pass through dispatch unchanged. Verified by absence of a retroactive scanner in the changeset.
12. `tests/test_orphan_surface_dispatch_gate.py` exists with at minimum the eight tests enumerated in BR-009. Running `pytest tests/test_orphan_surface_dispatch_gate.py -q` reports all tests passing.
13. `python3 compile-sdlc.py spec/etc_sdlc.yaml` completes without error after the standards-doc and skill edits. The compiled `dist/skills/build/SKILL.md` and `dist/standards/process/user-flow-completeness.md` are byte-identical to their sources.
14. The operator-prompt fallback (BR-004) uses Pattern A (`AskUserQuestion(`) per `standards/process/interactive-user-input.md`. No prompts added by this PRD are buried in prose; verified by a grep-based contract test in `tests/test_orphan_surface_dispatch_gate.py` (folded into `test_build_skill_documents_heuristic_invocation` or its own assertion).
15. Existing tests in the repository continue to pass after the changes. Running `pytest tests/ -q` reports no new failures introduced by this refactor (regression baseline; should be 677 + 8 = 685 after F001 + F002 + F003).
16. `agents/spec-enforcer.md` is NOT modified by this PRD. F002's verify-time logic is untouched; Layer 3 is dispatch-time only. Verified by inspecting the changed-file set.
17. `skills/decompose/SKILL.md` is NOT modified by this PRD. GA-003 chose dispatch-time-only enforcement; /decompose stays unchanged. Verified by inspecting the changed-file set.
18. The Layer 3 dispatch-time check fires correctly when a task's AC contains a User-flow sentence and dispatches normally (without firing) when the AC does NOT contain one. Verified by the contract tests' detection-step assertions; behavioral test of /build itself is out of scope (interactive skill).

## Edge Cases

1. **User-flow-sentenced task with empty `files_in_scope`.** Possible if /spec or /decompose produced a malformed task. /build Step 6 detects User-flow sentence but has nothing to inspect for parent-file heuristics. Behavior: invoke operator prompt (BR-004) with the full deliverable directory tree as the candidate set; operator selects parent file from the tree or selects "skip — intentionally orphan." If operator selects skip, the dispatched agent receives the wiring-contract clause but has no parent file in scope — the clause still informs the agent that wiring is part of the deliverable. The dispatched agent should escalate when it discovers it can't make the wiring edit.
2. **`files_in_scope` already includes a parent wiring file.** /build's heuristic detects a candidate that's already listed. Behavior: skip auto-add (no-op), append the wiring-contract clause to the prompt, and dispatch normally. Idempotent: re-running /build on the same task tree doesn't double-add.
3. **Heuristic finds a candidate but the file doesn't exist on disk.** E.g., heuristic predicts `frontend/src/components/layout/sidebar-nav.tsx` exists but the deliverable uses `Sidebar.tsx` instead. Behavior: heuristic gracefully degrades by checking each candidate's existence with `Glob`/`Bash` before adding. Non-existent candidates are filtered from the result set; if zero remain, fall through to operator prompt.
4. **Operator selects "intentional orphan" deferral.** The task records `surface_status: deferred` and proceeds. Future readers (and Layer 2's spec-enforcer at verify time) can audit why a user-facing AC was deliberately not wired. Layer 2's `## Reachability Evidence` already supports this state via the `surface_status: deferred` line in Edge Cases.
5. **User-flow sentence prefix appears in a non-AC context.** E.g., the task's `requires_reading` includes a doc that contains the literal prefix `As {role}, navigate from`. /build's detection only inspects the `acceptance_criteria` field, not the entire task YAML, so this is not a false-positive trigger.
6. **Multiple User-flow sentences in one task's AC list.** Possible if a single task implements multiple user-facing surfaces (e.g., a wizard that adds both a route and a sidebar entry). Behavior: heuristic runs once per User-flow sentence in the task's AC list; each surface gets a parent-file check. If the heuristic finds the same parent file for multiple sentences (e.g., one sidebar-nav covers both routes), de-dupe. If different parent files, all are added to `files_in_scope`.
7. **Parallel-wave dispatches with shared parent file.** Wave 0 has tasks 003 and 005, both User-flow-sentenced, both heuristics resolving to the same `sidebar-nav.tsx`. Auto-add would put `sidebar-nav.tsx` in both tasks' `files_in_scope`. Wave-planner's file-set isolation rule (per `tasks.py waves`) detects the overlap and serializes the two tasks across waves. This is correct behavior — concurrent edits to the same file from parallel agents would corrupt the shared git index. The heuristic's auto-add can therefore lengthen the wave plan; this is a documented tradeoff.
8. **Pyright / ESLint / Compilation breaks because parent file imports the new component.** Adding a `<Link to="/admin/orgs/new">` edit requires the new wizard component to actually exist. If the agent ships the parent edit before the component, the build breaks. The dispatched agent's TDD discipline + `requires_reading` guard the order: tests must exist before the parent wiring edit, and the wiring edit references a component that's now in scope.
9. **Heuristic candidate is a file the agent doesn't have permission to edit.** E.g., a sidebar-nav file in a `frontend/src/components/layout/` directory that's gitignored or owned by another team. Behavior: the heuristic doesn't know about ownership or gitignore — it adds the candidate. The dispatched agent's pre-edit hooks (block-config-changes, INVARIANTS) catch ownership/gitignore violations and refuse the edit, escalating to the orchestrator.
10. **Operator dismissal cascade.** Operator hits the prompt for task 1, selects "intentional orphan." Same prompt fires for task 2. Operator may want to bulk-dismiss. The PRD does NOT support bulk dismiss — each prompt is individual. If the harness later needs bulk dismissal for large multi-orphan PRDs, that's a future PRD.
11. **Compile pipeline fails after edits.** `compile-sdlc.py` is required to succeed (AC13). Treat compile failure as a P0 blocker per F001/F002 precedent.
12. **The wiring-contract clause exceeds the dispatched agent's context budget.** /build's existing prompt already includes `requires_reading` paths + ACs + `files_in_scope`. Adding ~100 words of wiring-contract text on top is negligible. The clause cites the standards doc by path so the agent doesn't need the full evidence taxonomy inline.
13. **AC contains "As " but not ", navigate from" (false-negative trigger).** E.g., AC reads "As an admin, the system updates the database." That's NOT a User-flow sentence (no navigation), so detection correctly skips. The dispatcher passes through unchanged.
14. **AC contains ", navigate from" but no "As " prefix (malformed User-flow sentence).** E.g., "When the user clicks the button, navigate from /a to /b." That's not in the canonical form. F001 would have caught this at /spec time and prompted the author to rewrite. By the time /build sees it, the AC either has a proper User-flow sentence or doesn't. Behavior: no detection, no trigger — same as Edge Case 13.
15. **Standards-doc section header drifts from what the skill cites.** /build cites `standards/process/user-flow-completeness.md` by path, not by section anchor. If a future edit moves the Dispatch-time Wiring Contract section content elsewhere in the file, the citation still resolves. Acceptable: file path is the contract.
16. **Task is auto-decomposed by /decompose's recursive split (parent → 002 → 002.001).** The User-flow sentence may live on the parent's AC list, not on the leaf. Behavior: when /build dispatches the leaf, it inspects the leaf's AC list only. If the User-flow sentence wasn't propagated to the leaf during decomposition, the dispatch passes through without the wiring check. This is a documented limitation: /decompose's existing behavior of propagating ACs to leaves needs to preserve User-flow sentences. If decomposition strips them, Layer 3 silently fails to fire. (Layer 1's auto-detection at /spec time still operates on the parent, so this only affects later resume / re-dispatch scenarios.)
17. **/build is run in `--resume` mode after Layer 3 ships.** A previously-decomposed feature whose tasks pre-date Layer 3 may have User-flow-sentenced ACs but no parent files in scope. /build --resume will detect them and run the heuristic / prompt cycle. Existing in-progress dispatches are unaffected (they were already dispatched without the wiring check); future waves will use the new dispatch path.

## Technical Constraints

- **File touchpoints (small, surgical):** the refactor edits two existing files (`standards/process/user-flow-completeness.md`, `skills/build/SKILL.md`) and creates one new file (`tests/test_orphan_surface_dispatch_gate.py`). No Python source changes outside the new test file. No edits to `compile-sdlc.py`, `feature_id.py`, `git_tags.py`, `value_hypothesis.py`, `tasks.py`, or any other script under `scripts/`.
- **Compile pipeline:** `python3 compile-sdlc.py spec/etc_sdlc.yaml` already recursively copies `skills/<name>/` → `dist/skills/<name>/` and `standards/<name>/` → `dist/standards/<name>/`. Running the compiler after the edits ships both modified files without compiler changes.
- **Skill body is prose, not code:** /build is a Markdown skill loaded by the runtime. The "auto-add heuristic" + "operator-prompt fallback" + "wiring-contract clause" are all described as agent procedures the dispatcher follows during its turn, not Python functions. Same convention as F001's auto-detection step in /spec and F002's per-AC reachability check in spec-enforcer.
- **Single source of truth for the rule:** `standards/process/user-flow-completeness.md` is authoritative for all three layers (F001 + F002 + F003). The skill body cites the doc by path; the heuristic signal lists, the contract clause text, and the operator-prompt structure all live in the standards doc. Doc-first updates keep the system in sync.
- **Pattern A / Pattern B compliance:** the operator-prompt fallback uses Pattern A (`AskUserQuestion`) per `standards/process/interactive-user-input.md`. The wiring-contract clause injected into dispatched agent prompts is NOT a user-facing prompt; it's text the dispatcher includes in its `Agent({prompt: ...})` payload, addressed to the dispatched agent. Pattern A/B rules apply only to user-facing prompts; agent-to-agent communication is unconstrained.
- **Backward compatibility:**
  - The existing eight-step /build pipeline structure (VALIDATE / SETUP / DECOMPOSE / SCORE / PLAN WAVES / EXECUTE / VERIFY / REPORT) is unchanged.
  - The Step 6 sub-step structure (6a Dispatch / 6b Wait / 6c Verify / 6d Checkpoint / 6e Proceed) is unchanged.
  - The `Agent({...})` invocation shape is unchanged; only the prompt content is augmented for User-flow-sentenced tasks.
  - The post-dispatch result handling, the parallel fan-out discipline, the task-status update contract via `tasks.py set-status`, and the phase-tag write contract are all unchanged.
  - F001 + F002 standards-doc sections are unchanged; the new Dispatch-time Wiring Contract section appends after them.
- **Forward-only application:** the wiring check fires only on User-flow-sentenced ACs. Tasks without User-flow sentences (legacy specs, backend-only ACs, or ACs explicitly marked `surface_status: backend_only`) pass through dispatch unchanged. The PRD adds no validator, scanner, or hook that retroactively flags legacy specs.
- **Test precedent:** contract tests follow `tests/test_user_flow_completeness.py` (F001) and `tests/test_spec_enforcer_reachability.py` (F002) — grep-based assertions over the compiled `dist/skills/build/SKILL.md` and `dist/standards/process/user-flow-completeness.md`. Same compile-fixture pattern (autouse session-scoped fixture invoking `compile-sdlc.py`) with the explicit `_ = _compile_sdlc` reference workaround for Pyright's "is not accessed" hint.
- **F001 + F002 dependency:** this PRD assumes F001 and F002 have shipped (the User-flow sentence form, the standards doc, the Phase 3/4 /spec edits, the spec-enforcer reachability check are all live). If F001 is reverted, no AC carries a User-flow sentence and Layer 3 silently does nothing — degrading gracefully to no-op. If F002 is reverted, Layer 3 still operates at dispatch time but verify-time checks fall back to F002's pre-edit behavior.
- **Heuristic operates on the deliverable directory tree, not the etc repo:** when /build runs against a project's PRD, the heuristic uses Glob/Grep against the project's source files, not against etc-system-engineering itself. Path patterns (`**/layout/sidebar-nav.*`, etc.) are framework-agnostic but biased toward common React/TypeScript conventions; non-standard project structures may yield zero candidates and fall through to operator prompt. That's the intended graceful degradation.
- **Tool budget for /build itself:** /build is the conductor agent; it has different tool budget characteristics than spec-enforcer (which has a hard 16-call cap from F002). /build's budget is implicit — it runs the pipeline as a sequential procedure and dispatches Agent calls one per task. The heuristic's Glob/Grep calls are part of /build's normal operation, not a per-AC sub-budget. Adding the heuristic does increase /build's Glob/Grep usage by ~1-3 calls per User-flow-sentenced task; for typical PRDs (5-15 user-facing ACs) this is unobjectionable.
- **Missing infrastructure:** `INVARIANTS.md` and `.etc_sdlc/antipatterns.md` do not exist in this repo. Both reads are conditional per /spec's "Before Starting"; absence is recorded in research notes, not blocked on.
- **Scope boundary marker:** F001 + F002 are siblings, both shipped. Windows install bug (separate stream, captured in memory) is unrelated. /design phase split (Stream 3) is a separate Loop 1 SDLC restructure, also unrelated. Layer 3 completes the orphan-surface defense trio and produces a closed three-layer system.

## Security Considerations

This feature does not handle authentication, user input validation at system boundaries, data storage, file uploads, external APIs, or authorization. It is a documentation refactor of an existing skill body and an appended section to an existing standards doc, plus a new contract test. None of the auto-populate categories from the /spec security table apply directly. The security-relevant considerations are:

- **The auto-add heuristic mutates task YAML on disk.** When /build determines a parent file should be added to a task's `files_in_scope`, it writes the augmented file list back to the task YAML (or holds it in memory through dispatch). The mutation must be idempotent, atomic, and bounded to the specific task being dispatched. Cross-task corruption (modifying task A's YAML while dispatching task B) is forbidden. The implementation uses `tasks.py` CLI (or in-memory state) per the existing harness convention; concurrent /build runs on the same feature directory are out of scope per existing `/build` discipline.
- **Heuristic uses Glob/Grep against the deliverable directory tree.** The heuristic patterns are author-controlled (defined in the standards doc); the deliverable tree is the user's project. There is no shell-eval of file content; Glob/Grep operate on filenames and grep patterns only. Pathological project layouts (deeply nested, symlinked) cause heuristic timeouts at worst, not security issues.
- **Operator prompt input flows verbatim into task YAML when "custom file" option is selected.** When the operator types a custom parent file path, that path is recorded into the task's `files_in_scope` list. Path sanitization (control-char strip + length cap) MUST follow the F001/F002 convention: strip control characters (regex `[\x00-\x1f\x7f]`) and cap the path string at a reasonable limit (256 chars matches Linux PATH_MAX conventions). The skill body MUST document this. Mitigates path-traversal attempts where an operator could try to add `../../../../etc/passwd` to the scope — the path-walk discipline of the dispatched agent's hooks (block-config-changes, INVARIANTS) catches the actual edit attempt; sanitization just keeps the recorded value clean.
- **The wiring-contract clause is static text, not user-controlled.** The clause injected into dispatched agent prompts is defined in the standards doc and copied verbatim. No user input flows into the clause. No injection vector.
- **No automatic Read of operator-supplied paths.** /build does NOT `Read` the operator-supplied parent file before dispatching the agent — it only adds the path string to `files_in_scope`. The dispatched agent then has authority (per its own hooks) to Read or refuse to Read the file. This matches F002's `## Security Constraints` rule: never automatically Read paths that arrived via user input.
- **No secret material.** The PRD does not read, write, or embed credentials, tokens, API keys, or secrets. The new standards-doc section, the skill edit, and the contract test are public-style content.
- **Citation integrity.** Skill-body and dispatched-agent-prompt references to `standards/process/user-flow-completeness.md` are free-form text strings, not runtime-fetched URLs. Misspelled paths fail the contract test; security risk is none.
- **Forward-only is a security-adjacent property.** Because legacy tasks are not modified retroactively (BR-007), there is no risk of the rule corrupting historical artifacts or invalidating audit trails. Pre-existing task YAMLs and `etc/feature/F<NNN>/*` git tags retain their original content.
- **Contract test is read-only.** `tests/test_orphan_surface_dispatch_gate.py` performs grep-style assertions over committed repository files and the compiled `dist/` outputs. No network calls, no shell escapes, no file writes outside the pytest temp-dir fixtures.
- **/build dispatcher's existing parallel-agent safety is preserved.** The wave-planner's file-set isolation rule already prevents two parallel agents from editing the same file. The auto-add heuristic CAN cause the wave-planner to serialize previously-parallel tasks (if multiple Wave 0 tasks all have the same parent file added). This is correct — concurrent same-file edits would corrupt the shared git index. The serialization is a feature, not a bug.
- **No new network surface.** Phase 2 web research is already part of /spec, not /build. /build does not make network calls; the heuristic operates on local filesystem only.

## Module Structure

Files to create or modify:

- **Modified:** `standards/process/user-flow-completeness.md` — append a new `## Dispatch-time Wiring Contract` section after the F002 Reachability Evidence section. Defines the trigger (User-flow sentence presence on a task's AC), the wiring-contract clause, the four-tier auto-add heuristic preference order (sidebar-nav, parent-route, barrel exports, settings-rail/tab-array config), the operator-prompt fallback contract (with the `surface_status: deferred` deferral option), the parent-file-detection signal list, the operator-path sanitization rule (control-char strip + 256-char cap), and the no-automatic-Read constraint.
- **Modified:** `skills/build/SKILL.md` — Step 6 (specifically the per-task dispatch block at lines 367-376) gets: the User-flow sentence detection step (BR-002), the auto-add heuristic invocation (BR-003), the operator-prompt fallback (BR-004) using Pattern A `AskUserQuestion`, the wiring-contract clause appended to dispatched agent prompts (BR-005), and the citation of the standards doc by path (BR-006). Existing dispatch shape (Agent({...}) form, subagent_type, post-dispatch handling, parallel fan-out, phase-tag writes) preserved verbatim.
- **Created:** `tests/test_orphan_surface_dispatch_gate.py` — the eight grep-based contract tests enumerated in BR-009. Uses the same autouse session-scoped compile fixture pattern as `tests/test_user_flow_completeness.py` and `tests/test_spec_enforcer_reachability.py` (with the explicit `_ = _compile_sdlc` reference workaround for Pyright's "is not accessed" hint).
- **Created:** `.etc_sdlc/features/F003-orphan-surface-dispatch-gate/spec.md` — this PRD.
- **Created:** `.etc_sdlc/features/F003-orphan-surface-dispatch-gate/value-hypothesis.yaml` — outcome contract.
- **Created:** `.etc_sdlc/features/F003-orphan-surface-dispatch-gate/state.yaml` — Phase 2.75 classification (`research-assisted`) + author_role: SME/PM.
- **Created:** `.etc_sdlc/features/F003-orphan-surface-dispatch-gate/gray-areas.md` — 4 entries (1 research-decided, 3 user-decided per Phase 2.5).
- **Created:** `.etc_sdlc/features/F003-orphan-surface-dispatch-gate/research/` — at least `codebase.md` capturing Phase 2 codebase findings.
- **Created (byte-identical copy):** `spec/orphan-surface-dispatch-gate.md` — for browsability and backward compatibility.
- **Regenerated (not hand-edited):** `dist/skills/build/SKILL.md`, `dist/standards/process/user-flow-completeness.md` — outputs of `python3 compile-sdlc.py spec/etc_sdlc.yaml` after the source edits.

Files explicitly NOT touched:

- `compile-sdlc.py` — the recursive copy already handles edited files; no compiler changes are required.
- `agents/spec-enforcer.md` — Layer 2's territory; F002 owns it; preserved verbatim. (AC16)
- `skills/decompose/SKILL.md` — GA-003 chose dispatch-time-only enforcement; /decompose stays unchanged. (AC17)
- Any other agent — sem, technical-writer, frontend-developer, backend-developer, devops-engineer, code-reviewer, security-reviewer, verifier, architect-reviewer, etc. are unchanged.
- Any other skill — /spec, /implement, /metrics, /tasks, /hotfix, /postmortem, /retrospective, /discovery, /roadmap, /init-project, /harness-feedback are unchanged.
- Any other doc under `standards/process/`, `standards/architecture/`, `standards/code/`, `standards/git/`, `standards/quality/`, `standards/security/`, or `standards/testing/` — read-only references.
- F001 + F002 standards-doc sections are unchanged (Phase 3 detection, Phase 4 gate, Worked Example, Reachability Evidence, Verdict Mapping, F002 Security Constraints) — Layer 3 appends as a new peer section.
- F001's `hooks/inject-standards.sh` HEREDOC section — unchanged.
- `docs/agent-prompt-template.md` — does not exist in this repo (per Phase 2 research); GA-001 chose the F001+F002 standards doc as the canonical location instead.
- `/build` Steps 1-5, 7, 8 — only Step 6 (dispatcher) is touched.
- The `Agent({...})` invocation shape and the post-dispatch result handling — preserved verbatim.
- Legacy specs in `.etc_sdlc/features/*/spec.md` and their tasks — forward-only (BR-007 / AC11).
- `spec/etc_sdlc.yaml` — the skill is hand-authored Markdown, not YAML-generated.
- `templates/*.tmpl` — these are /init-project's templates; unrelated to dispatch-time behavior.

## Research Notes

**Codebase (Phase 2):**
- `docs/agent-prompt-template.md` does NOT exist in this repo. Brief described it as a venlink-platform convention. GA-001 research-decided to extend `standards/process/user-flow-completeness.md` instead (continues F001+F002 single-doc pattern).
- `skills/build/SKILL.md` Step 6 is at lines 336-423, with sub-steps 6a-6e. The per-task dispatch block at lines 367-376 is the natural insertion point for the detection + heuristic + clause logic.
- `skills/decompose/SKILL.md` exists (334 lines); GA-003 chose dispatch-time-only enforcement so /decompose stays untouched.
- `standards/process/user-flow-completeness.md` is currently 268 lines with F001 (Phase 3 detection / Phase 4 gate / Worked Example) and F002 (Reachability Evidence / Verdict Mapping / Security Constraints) sections. Adding a new `## Dispatch-time Wiring Contract` section after F002 places all three layers in one canonical doc.
- F001's `tests/test_user_flow_completeness.py` and F002's `tests/test_spec_enforcer_reachability.py` provide the contract-test precedent (grep-based, autouse session-scoped compile fixture, explicit `_ = _compile_sdlc` Pyright workaround).
- `templates/agent.md.tmpl` exists but is for /init-project to deploy new agent definitions, NOT a dispatch-prompt template.
- Compile pipeline (`compile-sdlc.py`) recursively copies `skills/<name>/` → `dist/skills/<name>/` and `standards/<name>/` → `dist/standards/<name>/`. F003 requires no compiler edit.
- INVARIANTS.md and `.etc_sdlc/antipatterns.md` are absent in this repo (expected, conditional reads).

**Best practices (light pass — proposal grounded in F001/F002 + venlink F4 origin trace):**
- "Wiring is part of the deliverable" framing maps to standard agent-orchestration patterns where task scope is bounded but cross-cutting concerns (like wiring) need explicit recognition. The pattern is established in CI/CD task contracts (e.g., "build a feature flag" requires updating both the flag definition AND the consumer code). F003's contribution is making the cross-cutting concern explicit at dispatch time rather than relying on the agent to infer it.
- Auto-add-with-prompt-fallback is a standard interactive-search-with-disambiguation pattern (e.g., LSP code-action menus, IDE refactor prompts).

**Antipatterns:** No `.etc_sdlc/antipatterns.md`. Nothing to incorporate.

**Three-layer defense status:**
- F001 (Layer 1, AC-time, shipped): User-flow sentence required at AC authorship.
- F002 (Layer 2, verify-time, shipped): spec-enforcer requires reachability evidence for User-flow-sentenced ACs.
- F003 (Layer 3, dispatch-time, this PRD): /build auto-adds parent wiring file or prompts operator; appends wiring-contract clause to dispatched agent prompts.

After F003 ships, the F4-class orphan-surface defect is structurally impossible to ship: it must evade all three independent gates. Each layer catches the failure mode at a different harness phase with a different forcing function.

**Process standards consulted:**
- `standards/process/interactive-user-input.md` — Pattern A (`AskUserQuestion`) used in BR-004 operator-prompt fallback.
- `standards/process/user-flow-completeness.md` — F001/F002 deliverable, F003's append target.
- `standards/process/harness-feedback-loop.md` — defines the harness-feedback emission contract that produced F001/F002/F003's inputs.
