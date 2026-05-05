# PRD: /build Per-Phase Completion-Report Writing

## Summary

Every feature shipped via `/build` this session (F001, F002, F003, F004) produced a stub `release-notes.md` saying "_No build phases found._" The cause is a structural gap between `/build` and `scripts/release_notes.py`: `release_notes.py` is a pure roll-up reader that walks `<feature_dir>/build/phase-<N>/completion-report.md` files and aggregates them into a single markdown roll-up (per its docstring, lines 1-30, and per `tests/test_release_notes.py:38-82` which exercises the exact format). But `/build` Step 6d writes only the `etc/feature/F<NNN>/build/phase-<N>/done` git tag — not the per-phase report file. Result: `release_notes.py` walks `build/phase-*` and finds zero report files, returning the stub. Every feature's audit-trail artifact is empty.

This refactor closes the gap with a small mechanical fix. **Add a new `scripts/completion_report.py` Python helper** that takes a feature directory, a phase number, and metadata (PRD title, feature ID, per-task AC list, deferred items, known limitations) and writes a properly-formatted `completion-report.md` to `<feature_dir>/build/phase-<N>/completion-report.md`. The format matches `release_notes.py`'s reader contract verbatim — `## PRD` + `## Acceptance Criteria` (with `- [x]` / `- [ ]` markdown checkboxes) + `## Deferred Items` + `## Known Limitations`. **Extend `skills/build/SKILL.md` Step 6d** to invoke `completion_report.py write` after the phase-done tag write, before advancing to the next wave. The trigger semantics match the existing phase-done tag exactly — only on successful wave exit (Step 6c tests pass, no task escalated); failed phases produce no report. The skill body sources its content from the wave's task YAMLs (each task contributes its `acceptance_criteria` list, all marked passed because the wave already passed Step 6c verification before reaching 6d).

This PRD is intentionally narrow. **`scripts/release_notes.py` is unchanged** — it already has the correct reader contract; we just need a writer that meets it. **F001-F004 keep their existing stub `release-notes.md`** — forward-only per harness convention; backfilling already-shipped audit trails is a separate concern requiring its own PRD. **No standards-doc edits, no agent edits, no skill edits beyond `/build` Step 6d** — F001/F002/F003 (orphan-surface defense) and F004 (Windows compat) are independent and untouched. After F005 ships, the next feature that builds via `/build` will produce a proper `release-notes.md` containing PRD title+ID, per-phase AC pass/fail summaries, deferred items, and known limitations sourced from the wave's task YAMLs — the audit trail the artifact was always supposed to be.

## Scope

### In Scope
- New `scripts/completion_report.py` Python helper invoked from /build Step 6d via the same CLI-form convention used for git_tags.py, release_notes.py, feature_id.py, value_hypothesis.py.
- The helper accepts a feature directory + phase number + metadata (PRD title, feature ID, AC pass/fail lists, deferred items, known limitations) and writes `<feature_dir>/build/phase-<N>/completion-report.md` in release_notes.py's expected format.
- Edits to `skills/build/SKILL.md` Step 6d to invoke completion_report.py after the phase-done tag write, before advancing to the next wave.
- Step 6d sources per-phase content from the wave's task YAMLs (in `<feature_dir>/tasks/`): each task's `acceptance_criteria` list contributes to the AC pass/fail section; PRD title/ID come from `<feature_dir>/state.yaml`'s `feature_id` and `<feature_dir>/spec.md`'s first heading; deferred items come from any `surface_status: deferred` markers introduced by F003; known limitations default to "(none)" with operator-amendable downstream.
- New `tests/test_completion_report.py` contract tests with grep-based assertions and a dynamic round-trip test (write a report via the helper; read it via `release_notes.py`'s exposed parser; assert the round-trip is byte-equivalent).
- Compile pipeline integration via `python3 compile-sdlc.py spec/etc_sdlc.yaml` — no compiler edits.
- Forward-only: F001-F004 keep their existing stub release-notes.md.

### Out of Scope
- Backfill of F001-F004's release-notes.md.
- Modifications to `scripts/release_notes.py` (reader contract is unchanged; writer meets it).
- Changes to `/build` Steps 1-5, 6a-6c, 6e, 7, 8.
- F001/F002/F003 standards-doc / agent / skill files.
- F004 install.sh + compile-sdlc.py.
- Operator-amendable known-limitations editing UI (operator can hand-edit the file post-write if needed; no skill workflow added).
- A retroactive scanner over `.etc_sdlc/features/*/build/phase-*/` to add reports to legacy phases.

## Requirements

### BR-001: completion_report.py Helper Script
A new Python helper script MUST be created at `scripts/completion_report.py`. It MUST expose a `write` CLI subcommand (matching the convention of `git_tags.py write-tag`, `release_notes.py build`, `value_hypothesis.py validate`):

```
python3 ~/.claude/scripts/completion_report.py write \
    --feature-dir <feature_path> \
    --phase <N> \
    --prd-title <title> \
    --prd-id <feature_id> \
    --ac-passed-file <path-to-yaml-or-json-list> \
    --ac-failed-file <path-to-yaml-or-json-list> \
    --deferred-file <path-to-yaml-or-json-list> \
    --limitations-file <path-to-yaml-or-json-list>
```

The script MUST:
- Accept the feature directory, phase number, and metadata via CLI flags (not positional args, for future extensibility).
- Read AC pass/fail lists, deferred items, and limitations from operator-supplied files (since they may be long; passing as flag values is brittle).
- Create `<feature_dir>/build/phase-<N>/` if it doesn't exist.
- Write `<feature_dir>/build/phase-<N>/completion-report.md` in release_notes.py's expected format.
- Exit 0 on success, 1 on error (with stderr message).

### BR-002: Report Format Matches release_notes.py Reader Contract
The completion-report.md format MUST be:

```markdown
# Phase <N> — <prd-title>

## PRD
- Title: <prd-title>
- ID: <feature_id>

## Acceptance Criteria
- [x] <passed AC text>
- [ ] <failed AC text>

## Deferred Items
- <bullet>

## Known Limitations
- <bullet>
```

If a section has no items, it MUST contain the literal string `- (none)` rather than being empty. release_notes.py's reader handles both, but explicit "(none)" is more readable in the audit trail.

### BR-003: /build Step 6d Invokes the Helper
`skills/build/SKILL.md` Step 6d MUST be extended with a new procedural step that runs AFTER the phase-done git tag write and BEFORE the state.yaml waves_completed update:

> **6d.5: Write per-phase completion report.**
>
> Source the report's content from the wave's task YAMLs:
> - PRD title: read the first `# PRD: <title>` heading from `<feature_dir>/spec.md`
> - PRD ID: read `feature_id` from `<feature_dir>/state.yaml`
> - AC passed list: collect every `acceptance_criteria` entry from every task YAML in `<feature_dir>/tasks/` whose `parent_task` (or top-level task ID) corresponds to wave N. Because the phase-done tag is written only on successful wave exit, every AC in the wave's task list is treated as passed.
> - AC failed list: empty (the wave passed Step 6c verification; no failed ACs reach 6d.5).
> - Deferred items: collect any `surface_status: deferred` markers from the wave's task YAMLs (F003 introduced this concept). If none, the section gets `- (none)`.
> - Known limitations: default to `- (none)`. Operator can hand-amend post-write.
>
> Then invoke:
> ```
> python3 ~/.claude/scripts/completion_report.py write \
>     --feature-dir <feature_path> \
>     --phase <N> \
>     --prd-title "<title>" \
>     --prd-id <feature_id> \
>     --ac-passed-file <tmpfile-of-ac-list> \
>     --deferred-file <tmpfile-of-deferred-list> \
>     --limitations-file <tmpfile-of-limitations-list>
> ```

### BR-004: Trigger Condition
The completion-report.md write MUST fire only on successful phase close (matching the existing phase-N/done tag write semantics at Step 6d). Failed phases (test failure at Step 6c, escalated tasks) produce no report. The phase-N/start tag remains as audit trail; the absence of phase-N/done + completion-report.md is the existing failure signal.

### BR-005: Forward-Only Scope
The PRD MUST NOT modify F001-F004's already-shipped release-notes.md. No retroactive scanner across `.etc_sdlc/features/*/build/phase-*/`. New PRDs that build after F005 lands get proper completion reports; legacy features keep their stubs.

### BR-006: release_notes.py Unchanged
`scripts/release_notes.py` MUST NOT be modified. Its existing reader contract (lines 1-30 docstring + the parsing logic at lines 122-218) is the spec the writer follows. After F005 lands, release_notes.py's existing test_release_notes.py tests continue to pass with no changes.

### BR-007: Contract Test Coverage
A new test file `tests/test_completion_report.py` MUST exist and pass, containing at minimum:
- `test_completion_report_writes_expected_format` — invokes `completion_report.py write` with sample inputs and asserts the resulting file content matches the format from BR-002 verbatim.
- `test_completion_report_creates_phase_directory` — verifies `<feature_dir>/build/phase-<N>/` is created if absent.
- `test_completion_report_handles_empty_sections` — verifies empty AC/deferred/limitations lists produce the `- (none)` literal.
- `test_completion_report_round_trip_with_release_notes` — writes a report via the helper, then invokes `release_notes.build()` (the function from `scripts/release_notes.py`) on the parent feature directory, and asserts the resulting roll-up contains the PRD title, ID, AC checkboxes, and bullets that the helper just wrote. This is the load-bearing integration test — proves the writer/reader contract aligns.
- `test_build_skill_documents_step_6d_5` — greps `dist/skills/build/SKILL.md` Step 6d region for the new sub-step (literal `6d.5` + `completion_report.py write` invocation form).

### BR-008: Compile Pipeline Integration
`python3 compile-sdlc.py spec/etc_sdlc.yaml` MUST complete without error after the skill edit. The compiled `dist/skills/build/SKILL.md` MUST contain the new sub-step 6d.5 verbatim. No compiler edits.

### BR-009: Pattern A / Pattern B Compliance
F005 adds NO user-facing prompts. The helper script is non-interactive (CLI flags only). /build Step 6d's new sub-step is dispatcher-internal procedural logic, not operator-facing. No Pattern A/B work required.

## Acceptance Criteria

1. `scripts/completion_report.py` exists and exposes a `write` CLI subcommand with the exact flag signature from BR-001.
2. `completion_report.py write` creates `<feature_dir>/build/phase-<N>/completion-report.md` in the format from BR-002 verbatim, including the `# Phase N — <title>` top heading, the four `## PRD` / `## Acceptance Criteria` / `## Deferred Items` / `## Known Limitations` sections, and the `- [x]` / `- [ ]` markdown checkbox formatting.
3. Empty AC/deferred/limitations lists produce a literal `- (none)` line in the corresponding section (not empty content).
4. `completion_report.py write` exits 0 on success, 1 on error.
5. `dist/skills/build/SKILL.md` Step 6d contains a new sub-step `6d.5: Write per-phase completion report` (or equivalent header) that invokes `completion_report.py write` after the phase-done tag write and before the waves_completed update.
6. The new sub-step documents the source of each metadata field (PRD title from spec.md heading; PRD ID from state.yaml; ACs from task YAMLs; deferred from `surface_status: deferred` markers; limitations default to `(none)`).
7. The trigger condition matches the existing phase-done tag — completion-report.md is written only on successful wave exit (Step 6c tests pass, no task escalated).
8. `tests/test_completion_report.py` exists with at least the five tests from BR-007 and all pass via `pytest tests/test_completion_report.py -q`.
9. `test_completion_report_round_trip_with_release_notes` proves the writer/reader contract holds: a report written by the helper is correctly parsed by `release_notes.build()`, and the resulting roll-up contains the expected PRD title, ID, AC checkboxes, and bullets.
10. `python3 compile-sdlc.py spec/etc_sdlc.yaml` completes without error. `dist/skills/build/SKILL.md` is byte-identical to source.
11. `scripts/release_notes.py` is unmodified by F005. Verified by inspecting the changed-file set.
12. `tests/test_release_notes.py` is unmodified by F005. Verified by inspecting the changed-file set.
13. F001-F004's existing `release-notes.md` files are not altered. The PRD adds no retroactive scanner over `.etc_sdlc/features/*/build/phase-*/`. Verified by absence of glob/rglob patterns over feature dirs in the changeset.
14. Existing tests in the repository continue to pass after the changes. `pytest tests/ -q` reports no new failures (regression baseline; should be 692 + 5 = 697 after F005).
15. F001/F002/F003 standards-doc / agent / skill files NOT modified by F005. F004 install.sh / compile-sdlc.py NOT modified by F005. Only `scripts/completion_report.py`, `skills/build/SKILL.md`, and `tests/test_completion_report.py` are touched.
16. The next /build run after F005 lands produces a non-stub `release-notes.md` containing actual phase rollups (verified during F005's own /build cycle — F005's release-notes.md will be the first non-stub).

## Edge Cases

1. **Wave's task YAMLs reference `surface_status: deferred` (F003 introduced).** The new sub-step collects these into Deferred Items. Format: `- AC-N surface_status: deferred — User-flow sentence not authored at spec time.` per F003 BR-004.
2. **No deferred items in the wave.** Deferred Items section gets `- (none)`.
3. **No known limitations.** Known Limitations section gets `- (none)`. Operator can hand-amend the report file post-write if needed.
4. **`<feature_dir>/spec.md` first heading is not `# PRD: <title>` format.** Fall back to using the feature directory slug as the title. Most specs follow the convention; the fallback handles edge cases.
5. **`<feature_dir>/state.yaml` lacks `feature_id` field.** Use the feature directory name (e.g., `F005-build-completion-reports`) as the ID. Most state.yaml files have feature_id; the fallback prevents catastrophic failure.
6. **`<feature_dir>/tasks/` has no YAMLs for the current wave.** Empty AC list → AC section gets `- (none)`. Phase report still writes; release_notes.py handles the empty case gracefully.
7. **`<feature_dir>/build/phase-<N>/` already exists from a prior aborted run.** The helper overwrites the completion-report.md in place. Idempotent; re-running /build doesn't double-add.
8. **Wave is a re-decomposed parent (e.g., 002 → 002.001 + 002.002).** ACs come from the LEAF tasks in the wave, not the parent task (parents are marked `decomposed`). Step 6d.5's content sourcing must filter task YAMLs by `status: completed` (excluding `decomposed`).
9. **Compile pipeline fails after edits.** P0 blocker per F001/F002/F003/F004 precedent. The contract test in BR-007's `test_build_skill_documents_step_6d_5` catches it via the autouse compile fixture.
10. **release_notes.py's reader contract changes in a future PRD.** F005's writer would break. Mitigation: the round-trip test (BR-007's `test_completion_report_round_trip_with_release_notes`) is the canary — it fires whenever the contract drifts.
11. **Operator hand-amends the report file between Step 6d.5 write and Step 7.5b release-notes.md generation.** The operator's edit lands in release-notes.md (release_notes.py reads the file as it exists at Step 7.5b). Acceptable: known-limitations is operator-amendable by design.
12. **`completion_report.py` is invoked outside /build (e.g., manually).** The helper has no /build-specific dependencies; it just writes the file. Manual invocation is supported as a side benefit.
13. **F004 partner on Windows runs /build after F005 ships.** The helper script is pure Python with explicit `encoding="utf-8"` (matching F004's convention). Works under cp1252 default thanks to F004's pattern.

## Technical Constraints

- **File touchpoints (small, surgical):** the refactor creates `scripts/completion_report.py` and `tests/test_completion_report.py`, and modifies `skills/build/SKILL.md` Step 6d. No other files touched.
- **Helper script is Python.** Matches `scripts/` convention. Uses `argparse` for CLI parsing, follows the F002+F003+F004 pattern of small focused helpers.
- **Explicit `encoding="utf-8"` on every file open** in the helper script (per F004's PEP 686 future-proofing).
- **Skill body is prose.** /build Step 6d gains a new procedural sub-step described in agent-instruction prose, not Python code.
- **Compile pipeline:** `compile-sdlc.py` already recursively copies `skills/<name>/` and `scripts/`. No compiler edit.
- **release_notes.py reader contract is the writer spec.** The new helper produces output that release_notes.py's existing parser consumes. The round-trip test (BR-007) is the integration test that proves alignment.
- **Backward compatibility:**
  - F001-F004 stub release-notes.md files unchanged on disk.
  - /build Steps 1-5, 6a-6c, 6e, 7, 8 unchanged.
  - Existing tests/test_release_notes.py unchanged.
  - The eight-step /build pipeline structure preserved.
- **Forward-only application:** legacy features keep their stubs; new builds get proper reports.
- **Test precedent:** contract tests follow F001/F002/F003/F004 pattern (autouse session-scoped compile fixture, explicit `_ = _compile_sdlc` Pyright workaround, grep-based assertions over compiled `dist/`).
- **F001/F002/F003/F004 independence:** F005 is unrelated to orphan-surface defense + Windows compat. Standards doc unchanged. Agent files unchanged. Other skills unchanged.
- **Sonnet/Opus-1M child-dispatch bug:** F005's /build pipeline will use `model: opus` override on every Agent-tool call.
- **Missing infrastructure:** INVARIANTS.md and `.etc_sdlc/antipatterns.md` absent.

## Security Considerations

- **The helper writes to a path under `<feature_dir>/build/phase-<N>/`.** Path is operator-controlled (passed via `--feature-dir` flag). Path-traversal mitigation: validate that the resolved feature-dir is under `.etc_sdlc/features/` before writing. Refuse paths that escape the prefix.
- **Operator-supplied AC/deferred/limitations files are read verbatim.** The helper reads bullet text from the input files and writes it into the markdown report. Sanitize each bullet: strip control characters (regex `[\x00-\x1f\x7f]`) and cap each line at a reasonable length (1024 chars) before writing. Prevents log-injection or markdown-injection attacks against downstream readers.
- **`<feature_dir>/spec.md` and `<feature_dir>/state.yaml` are read-only inputs.** No write-back. The helper extracts PRD title and feature ID; it does not modify either source.
- **No secret material.** The helper reads/writes feature-internal artifacts only.
- **No network calls.** Pure local filesystem operation.
- **No subprocess.** Pure Python; no shell escapes.
- **The contract test is read-only in production paths.** Tests use pytest tmpdir fixtures for write operations; no writes to the repo's `.etc_sdlc/features/*/build/phase-*/` directories from test runs.
- **Forward-only is security-adjacent.** Legacy stubs are not corrupted by F005; pre-F005 `release-notes.md` files retain their original content.

## Module Structure

Files to create or modify:

- **Created:** `scripts/completion_report.py` — Python helper with `write` CLI subcommand. ~150-200 lines: argparse, file readers for AC/deferred/limitations input files, markdown emitter for release_notes.py-compatible format, path-traversal validation, control-char sanitization.
- **Modified:** `skills/build/SKILL.md` — Step 6d gains a new sub-step `6d.5: Write per-phase completion report` after the phase-done tag write (line ~575) and before the waves_completed update. ~30-40 lines of agent-instruction prose describing the metadata sourcing + helper invocation.
- **Created:** `tests/test_completion_report.py` — 5 tests from BR-007. Same autouse session-scoped compile fixture pattern as F001/F002/F003/F004 + explicit `_ = _compile_sdlc` Pyright workaround. Round-trip test imports `release_notes` from scripts/ and exercises the writer-reader pair end-to-end.
- **Created:** `.etc_sdlc/features/F005-build-completion-reports/spec.md` — this PRD.
- **Created:** `.etc_sdlc/features/F005-build-completion-reports/value-hypothesis.yaml` — outcome contract.
- **Created:** `.etc_sdlc/features/F005-build-completion-reports/state.yaml` — Phase 2.75 classification (research-assisted) + author_role: SME/PM.
- **Created:** `.etc_sdlc/features/F005-build-completion-reports/gray-areas.md` — 4 entries (4 research, 0 user).
- **Created:** `.etc_sdlc/features/F005-build-completion-reports/research/codebase.md` — Phase 2 findings.
- **Created (byte-identical copy):** `spec/build-completion-reports.md` — for browsability.
- **Regenerated by `compile-sdlc.py`:** `dist/skills/build/SKILL.md`, `dist/scripts/completion_report.py` (the latter only if scripts/ is mirrored to dist/; verified by F004 research that it is via install.sh's scripts/ install step).

Files explicitly NOT touched:

- `scripts/release_notes.py` — reader contract unchanged (BR-006).
- `tests/test_release_notes.py` — existing tests continue to pass.
- F001/F002/F003/F004 source files (standards doc, agent, install.sh, compile-sdlc.py, contract tests).
- /build Steps 1-5, 6a-6c, 6e, 7, 8.
- F001-F004 already-shipped release-notes.md files (forward-only per BR-005).
- Other agents, skills, standards docs, hooks.
- `compile-sdlc.py` — recursive copy already handles new files.
- `spec/etc_sdlc.yaml` — the skill is hand-authored Markdown.

## Research Notes

**Codebase findings (Phase 2):**

- `scripts/release_notes.py:1-30` documents the reader contract: walks `<feature_dir>/build/phase-<N>/completion-report.md` files, parses sections (PRD, Acceptance Criteria, Deferred Items, Known Limitations), and rolls up into a single markdown doc. The function is pure and never writes to disk.
- `scripts/release_notes.py:33-58` defines section constants (SECTION_AC, SECTION_DEFERRED, SECTION_LIMITATIONS, SECTION_PRD) and AC checkbox patterns (AC_PASS_PATTERN matches `- [x]`, AC_FAIL_PATTERN matches `- [ ]`).
- `tests/test_release_notes.py:38-82` `_create_completion_report` helper shows the exact format the reader expects:
  ```markdown
  # Phase N — <title>
  ## PRD
  - Title: <prd title>
  - ID: <feature_id>
  ## Acceptance Criteria
  - [x] passed AC text
  - [ ] failed AC text
  ## Deferred Items
  - bullet
  ## Known Limitations
  - bullet
  ```
- `skills/build/SKILL.md:561-585` Step 6d "Checkpoint and phase-done tag" is the natural insertion point for the new sub-step. The phase-done tag write happens here; the completion-report.md write joins it co-located, with the same trigger semantics (success-only).
- `scripts/` directory holds 8 Python helpers (feature_id.py, git_tags.py, release_notes.py, tasks.py, value_hypothesis.py, telemetry.py, meta-reconcile.py, check-vocabulary.py). The new `completion_report.py` matches the convention.
- INVARIANTS.md absent; `.etc_sdlc/antipatterns.md` absent.

**Best practices (light pass):**
- The pure-function reader pattern (release_notes.py.build()) plus a side-effecting writer (completion_report.py.write()) is the canonical "reader contract is the writer spec" pattern. The round-trip test (BR-007) is the integration glue.
- `argparse` with file-based input flags (rather than in-line list arguments) is the standard pattern for CLI helpers that take potentially-long lists. Matches release_notes.py and value_hypothesis.py.

**Antipatterns:** No `.etc_sdlc/antipatterns.md`. Nothing to incorporate.

**Process standards consulted:**
- `standards/process/interactive-user-input.md` — F005 adds no user-facing prompts.
- `standards/process/research-discipline.md` — applied during Phase 2 codebase exploration.
