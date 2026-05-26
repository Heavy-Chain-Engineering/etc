# PRD: F-2026-05-23 (Ftmp-19e49f7c) — Dispatch Prompt Assembler

## Summary

`/build` Step 6a constructs the per-dispatch prompt (layer 3 of the 4-layer subagent context model) by hand-authored prose in `skills/build/SKILL.md`. Every dispatch re-derives the same 7-section structure (feature intent, task intent, required reading, files in scope, acceptance criteria, cross-task awareness, report-back format). The result is prose drift between waves and across features, dispatches that exceed the ~1,000-token target documented in `standards/process/subagent-dispatch.md` (current measured baseline: ~1,400 tokens for substantial work, ~600 for simple), and a standards doc that cannot evolve without parallel SKILL.md edits.

F-2026-05-23 ships `scripts/dispatch_prompt.py` — a stdlib-only Python CLI that mechanizes the standards doc. The conductor invokes `python3 ~/.claude/scripts/dispatch_prompt.py assemble --feature-path <path> --task-id <id>` and receives the assembled prompt on stdout. Section ordering, content sourcing, and conditional clauses (User-flow wiring contract) are embedded in code and cite the standards doc. `skills/build/SKILL.md` Step 6a's prose collapses to a single-line invocation.

Forward-only: applies to dispatches authored from the F-2026-05-23 release tag onward. F024-and-earlier features keep the legacy prose path; their captured dispatch examples at `.etc_sdlc/incidents/2026-05-22-dispatch-examples/` become the assembler's snapshot test targets.

This composes on F022's stdlib-only helper convention, F024's conditional-emission idiom (layer 1), and F025's CLI shape. It does NOT replace F024's system-overlay logic — F024 owns layer 1 (invariant discipline); this PRD owns layer 3 (per-dispatch delta).

## Scope

### In Scope

- **CLI script** `scripts/dispatch_prompt.py` with one subcommand `assemble` that takes `--feature-path <path>` and `--task-id <id>` and emits the assembled dispatch prompt to stdout.
- **Eight-section assembly** matching `standards/process/subagent-dispatch.md` §Required dispatch sections: feature intent (1), task intent (2, optional), task identifier (3), required reading (4), files in scope (5), acceptance criteria (6), cross-task awareness (7), report-back format (8).
- **Feature intent** sourced from the first paragraph of `spec.md`'s `## Summary` section (up to the first blank line after the heading). Per GA-006.
- **Task intent** sourced from task YAML's `intent:` field when present; section omitted when absent. Per standards doc item 2.
- **Required reading** sourced verbatim from task YAML's `requires_reading` field with its existing path + commentary. Per GA-007.
- **Files in scope** sourced verbatim from task YAML's `files_in_scope` field, one per line.
- **Acceptance criteria** sourced verbatim from task YAML's `acceptance_criteria` field. No paraphrase, no narrative restatement (anti-pattern #3 in standards doc).
- **Cross-task awareness** computed from the wave-plan: enumerate other tasks in the same wave, their files_in_scope, and any declared dependencies. Names the wave-planner's file-set isolation guarantee.
- **Report-back format** templated standardized text from standards doc item 8.
- **Conditional wiring-contract clause** appended verbatim from `skills/build/SKILL.md` Step 6a (lines 1103-1124) when the task's acceptance_criteria contain the User-flow sentence prefix (`As ` ... `, navigate from`). The parent wiring file path is substituted from task YAML's `files_in_scope` (the entry added by Step 6a.5/6a.6). Per GA-004.
- **Token-budget warning** emitted to stderr (NOT stdout) when assembled prompt length > 1000 tokens. Counted via stdlib heuristic (4 chars/token approximation); precise counting deferred. Per GA-002.
- **SKILL.md Step 6a update** replacing the existing hand-construction prose (lines 903-909) with a one-line invocation of the assembler + a brief pointer to the standards doc.
- **Standards doc update** to `standards/process/subagent-dispatch.md` adding an "Implementation" section pointing at `scripts/dispatch_prompt.py` and removing the deferred-PRD pointer at line 96 (the deferral resolves with this PRD).
- **Test suite** at `tests/test_dispatch_prompt_assembler.py` covering: (a) each AC below has at least one dedicated test, (b) snapshot tests against the two ground-truth dispatches at `.etc_sdlc/incidents/2026-05-22-dispatch-examples/`, (c) edge-case tests for absent task intent, absent design.md, User-flow conditional clause, malformed task YAML, missing feature path, token-budget warning emission, and zero-AC tasks.

### Out of Scope

- **Precise token counting via tiktoken or model-specific tokenizer.** Stdlib heuristic (4 chars/token) suffices for the warn threshold. Precise counts are a deferred enhancement.
- **Operator-facing dispatch-prompt customization** (hand-edit per dispatch, per-feature overrides). The assembler is deterministic from inputs; customization would defeat the discipline.
- **Caching / memoization** of assembled prompts. Each /build invocation re-assembles; the cost is small (single-file reads + string concatenation).
- **Replacement of F024's conditional system-overlay logic.** F024 owns layer 1; this PRD owns layer 3. No edits to `hooks/inject-standards.sh`.
- **Per-subagent model selection or maxTurns tuning.** These belong in agent manifests (`agents/<role>.md` frontmatter).
- **Multi-task batched assembly** (one CLI call → N dispatch prompts). The conductor invokes once per task in parallel; assembler is per-task.
- **Retroactive re-authoring of F001-F024 dispatches.** Forward-only.

## Requirements

### BR-001: CLI entry point

`scripts/dispatch_prompt.py` provides one subcommand: `assemble --feature-path <path> --task-id <id>`. On success, prints the assembled dispatch prompt to stdout and exits 0. On usage error (missing args, invalid feature-path, unknown task-id), exits 2 with stderr explaining the cause. On IO error (file not found, permission denied), exits 1.

### BR-002: Feature-intent extraction from spec.md

The assembler reads `<feature-path>/spec.md` and extracts the first paragraph of the first `## Summary` section. "First paragraph" means the contiguous non-blank lines following the heading, terminated by the first blank line. The extracted paragraph is prepended with `**Feature intent (<feature_id>):** ` where `<feature_id>` is read from `<feature-path>/state.yaml`'s `build.feature` or top-level `feature_id` field (whichever is present; fall back to the feature directory basename if neither is present).

### BR-003: Task-intent extraction from task YAML

The assembler reads `<feature-path>/tasks/<task-id>*.yaml` (glob; one match expected). If the YAML contains a top-level `intent:` field with non-empty value, the assembler emits a `**Task intent:** ` section with the value. If the field is absent or empty, the task-intent section is OMITTED (the assembled prompt skips directly from feature intent to task identifier).

### BR-004: Required-reading section format

The assembler emits a numbered list of paths from task YAML's `requires_reading` field. Each entry is rendered as `<N>. <path> — <commentary>` where `<commentary>` is the YAML's authored commentary (string after the path in the YAML's structured form). When commentary is absent, the entry renders as just `<N>. <path>`. The standards doc's ≤8-word commentary target is documented but NOT enforced by the assembler (lint concern, not assembly concern).

### BR-005: Files-in-scope section format

The assembler emits one path per line from task YAML's `files_in_scope` field, prefixed by a `**Files in scope:**` heading. Paths are emitted verbatim (no `(NEW)` / `(MODIFIED)` tags — those are the subagent's job after filesystem read).

### BR-006: Acceptance-criteria section verbatim

The assembler emits each AC from task YAML's `acceptance_criteria` field verbatim, numbered. Cross-reference IDs (BR-NNN, EC-NNN, ADR-NNN) in the source are preserved exactly — no paraphrase, no narrative restatement, no markdown re-formatting.

### BR-007: Cross-task awareness computation

The assembler reads `<feature-path>/state.yaml`'s wave-plan (the field name TBD by /architect; current convention is `build.wave_plan` or equivalent). For the target task-id, it identifies the wave the task belongs to, enumerates the other tasks in that same wave by id + brief name + their files_in_scope file count. If no wave-plan is present in state.yaml, the section emits a single line: `(wave plan not yet computed; assume serial execution within feature)`.

### BR-008: Report-back format standardized

The assembler emits the report-back section using verbatim text from `standards/process/subagent-dispatch.md` §Required dispatch sections item 8 lines 43-46:

```
Report back with: (a) <pytest/verify output>; (b) <key artifact path or diff>;
(c) <one architectural decision you made beyond the spec>; (d) <any gaps>.
```

The angle-bracket placeholders are NOT substituted by the assembler (the subagent reads them as instructions for what to surface).

### BR-009: Conditional wiring-contract clause for User-flow tasks

The assembler scans task YAML's `acceptance_criteria` for the User-flow sentence prefix pattern: literal `As ` followed (within the same AC string, before the next sentence terminator `.` or `\n`) by literal `, navigate from`. When at least one AC matches, the assembler appends a `## Wiring contract (user-facing surface)` section containing the verbatim clause text from `skills/build/SKILL.md` Step 6a lines 1103-1124, with the `<path>` placeholder substituted by the parent wiring file path identified in task YAML's `files_in_scope` (the entry added by /build Step 6a.5 or 6a.6). When no AC matches, the section is OMITTED.

### BR-010: Token-budget warning

After full assembly, the assembler computes the assembled prompt's approximate token count via the stdlib heuristic `len(prompt) // 4`. When the count exceeds 1000, the assembler emits to stderr (one line, before exiting): `WARNING: assembled dispatch prompt ~<N> tokens exceeds 1000-token target. AC list may be substantial; verify content is task-specific and not duplicating system-overlay or role-manifest content.` Stdout is unaffected; exit code remains 0.

### BR-011: SKILL.md Step 6a update

`skills/build/SKILL.md` Step 6a lines 903-909 (the existing `Dispatch prompt construction: follow standards/process/subagent-dispatch.md...` paragraph) is replaced with a one-line invocation:

```
Assemble the dispatch prompt via `python3 ~/.claude/scripts/dispatch_prompt.py assemble --feature-path <feature_path> --task-id <task_id>`. The assembler mechanizes `standards/process/subagent-dispatch.md`; per-section content sourcing is documented there.
```

The existing F006 BR-005 spec.md+design.md briefing prose at SKILL.md lines 1091-1102 is updated to clarify that design.md is included via the assembler's requires_reading section (cite-only), not inlined.

### BR-012: Standards doc update

`standards/process/subagent-dispatch.md` line 96 (the existing pointer "Full dynamic prompt assembly (machine-driven via `scripts/dispatch_prompt.py`) is deferred to a future PRD (task #30).") is updated to "Full dynamic prompt assembly is mechanized via `scripts/dispatch_prompt.py` (F-2026-05-23). The script is the canonical implementation of the eight required sections above."

### BR-013: Forward-only boundary

The assembler is invoked by `/build` Step 6a from the F-2026-05-23 release tag onward. F-2026-05-23-and-earlier features that get re-built (resume, hotfix) continue to use the legacy prose path. The conductor's invocation prose at Step 6a includes a forward-only guard so the assembler is invoked only when present + when the feature's spec was written after the assembler's release tag. Implementation guidance: check `etc/feature/F-2026-05-23-dispatch-prompt-assembler/release` tag against the feature's spec git tag.

## Acceptance Criteria

1. **AC-001**: `scripts/dispatch_prompt.py assemble --feature-path .etc_sdlc/features/shipped/F023-distributed-id-allocation-discipline --task-id 003` produces an assembled prompt to stdout that, when diffed against `.etc_sdlc/incidents/2026-05-22-dispatch-examples/example-2-technical-writer-simple-adr.md` Section C (the captured per-dispatch prompt for the same task), matches modulo whitespace and the exception that the captured example includes the legacy "Dispatch hooks will enforce TDD..." line which the assembler MUST omit (anti-pattern #4 in standards doc).

2. **AC-002**: `scripts/dispatch_prompt.py assemble --feature-path .etc_sdlc/features/shipped/F023-distributed-id-allocation-discipline --task-id 001` produces an assembled prompt that includes all 8 sections from the standards doc, with feature intent extracted from F023's spec.md Summary first paragraph.

3. **AC-003**: When task YAML lacks an `intent:` field, the assembled prompt omits the task-intent section entirely (no empty heading, no placeholder). Verified via test fixture `tests/fixtures/dispatch-prompt-no-task-intent/`.

4. **AC-004**: When task YAML's `acceptance_criteria` contains an AC with the User-flow sentence prefix (`As {role}, navigate from`), the assembled prompt includes the wiring-contract section with the parent file path substituted from `files_in_scope`. Verified via test fixture with a User-flow AC.

5. **AC-005**: When task YAML's acceptance_criteria contain NO User-flow sentence, the assembled prompt OMITS the wiring-contract section. Verified via test fixture with backend-only ACs.

6. **AC-006**: Missing `--feature-path` argument exits 2 with stderr `usage: dispatch_prompt.py assemble --feature-path <path> --task-id <id>`. Missing `--task-id` argument exits 2 with the same usage line. Verified via parametrized argparse test.

7. **AC-007**: Non-existent feature-path exits 1 with stderr `error: feature-path <path> does not exist`. Verified via test passing a fabricated path.

8. **AC-008**: When `<feature-path>/tasks/<task-id>*.yaml` glob matches zero files, the assembler exits 1 with stderr `error: no task YAML matching id <task-id> under <feature-path>/tasks/`. When the glob matches multiple files, the assembler exits 1 with stderr `error: ambiguous task-id <task-id> matched <N> task YAMLs`.

9. **AC-009**: When the assembled prompt's approximate token count exceeds 1000, the assembler emits to stderr the verbatim warning line `WARNING: assembled dispatch prompt ~<N> tokens exceeds 1000-token target. AC list may be substantial; verify content is task-specific and not duplicating system-overlay or role-manifest content.` Stdout is unaffected; exit code remains 0. Verified via fixture with a task carrying 15+ ACs.

10. **AC-010**: `skills/build/SKILL.md` Step 6a no longer contains the hand-construction prose at lines 903-909. The replacement single-line invocation references `scripts/dispatch_prompt.py` by name.

11. **AC-011**: `standards/process/subagent-dispatch.md` line referencing task #30 is updated to reference the released F-2026-05-23 feature by name.

12. **AC-012**: `tests/test_dispatch_prompt_assembler.py` exists with at least 12 tests covering AC-001 through AC-011 plus the EC-001 through EC-006 edge cases below. Coverage of `scripts/dispatch_prompt.py` is ≥95%.

## Edge Cases

1. **EC-001**: spec.md exists but lacks a `## Summary` heading. The assembler MUST exit 1 with stderr `error: <feature-path>/spec.md missing required ## Summary section`.

2. **EC-002**: spec.md `## Summary` section is empty (heading followed immediately by another heading or EOF). The assembler MUST exit 1 with stderr `error: <feature-path>/spec.md Summary section is empty`.

3. **EC-003**: Task YAML is malformed (YAML parse error). The assembler MUST exit 1 with stderr `error: failed to parse <task-yaml-path>: <yaml-error>`.

4. **EC-004**: Task YAML lacks `acceptance_criteria` field. The assembler MUST exit 1 with stderr `error: <task-yaml-path> missing required field acceptance_criteria`.

5. **EC-005**: state.yaml is absent from feature-path. The assembler MUST exit 1 with stderr `error: <feature-path>/state.yaml does not exist; feature has not been allocated via /spec`.

6. **EC-006**: User-flow AC exists but no parent file path was added to `files_in_scope` (Step 6a.6 deferred). The assembler emits the wiring-contract section with `<path>` rendered literally as `(deferred — no parent file in scope; escalate if you discover the surface needs to be wired)` per SKILL.md line 1115's existing convention.

7. **EC-007**: requires_reading is absent or empty in the task YAML. The assembler emits the section heading followed by `(none)` rather than omitting the section. Mirrors SKILL.md's convention of always emitting the heading for predictability in snapshot tests.

8. **EC-008**: Token count is exactly 1000. The warning does NOT fire (strict greater-than per BR-010).

## Edge Cases — Deferral Audit Trail

(populated by /spec User-Flow gate when applicable; none for this infrastructure-only feature)
