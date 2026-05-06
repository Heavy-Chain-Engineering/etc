# PRD: Wave-Planner Implicit-Dependency Rejection (F008)

## Summary

F008 adds a pre-pack implicit-dependency scan to `scripts/tasks.py::compute_waves`. Before the wave-packer computes waves, the new scan walks each task's `context` and `acceptance_criteria` fields for three case-insensitive phrasings: `stub until task <NNN>`, `placeholder for task <NNN>`, `until task <NNN> lands`. Each match promotes a hard `dependencies:` edge in-memory (`current_task → captured_task_id`) so the wave-packer never schedules sibling tasks where one stubs for the other. If a captured task ID does not exist in the feature's task list, the script exits with code 1 and a stderr message naming the offending task and the missing reference. Promoted edges are surfaced as one-note-per-edge lines in `tasks.py waves` output so operators see what was modified.

F008 is the plan-time half of the stub-detection three-layer defense. F007 (spec-enforcer stub-marker grep, just shipped) is the verify-time half. Together they mirror F001-F003's three-layer orphan-surface defense: independent gates on independent artifacts that do not trust each other.

The motivating incident was venlink-platform F005-discussion-threads (2026-05-05): wave-planner shipped tasks 012 (`DiscussionThread`) and 013 (`MessageComposer`) to the same wave in parallel because the explicit `dependencies:` field had no edge between them — but task 012's prompt said "stub until task 013 lands" (an implicit edge structurally invisible to the planner). Task 012 finished first, shipped `<div data-testid="composer-stub" />`, and the stub got committed by orchestrator-finalize. F008's pre-pack scan would have caught this at plan time by promoting the implicit edge before wave-packing.

## Scope

### In Scope

- Edit `scripts/tasks.py` to add a pre-pack implicit-dependency scan at the top of `compute_waves(tasks: list[dict])` (before line 160's `leaf_tasks = get_leaf_tasks(tasks)` call). The scan returns the augmented task list AND a list of promoted-edge tuples.
- Edit `cmd_waves` (line 420) to receive the promoted-edge tuples and print one note per edge in the existing `tasks.py waves` output, immediately before the first wave block.
- Define **three implicit-dependency phrasings** as case-insensitive Python regex with capture group for the task ID:
  - `stub\s+until\s+task\s+([0-9]+)`
  - `placeholder\s+for\s+task\s+([0-9]+)`
  - `until\s+task\s+([0-9]+)\s+lands`
- **Fields scanned per task** (per GA-002 + GA-005): `task["context"]` (free-form prose) AND each string in `task["acceptance_criteria"]` (list).
- **Promotion semantics:** Each match promotes a hard `dependencies:` edge in-memory only — the on-disk task YAML is NOT modified. The augmented edge set is what the wave-packer uses for scheduling.
- **Idempotency:** if the captured task ID already exists in the task's `dependencies` list, no double-add and no error.
- **Fail-fast:** if the captured task ID does not exist in the feature's task list, exit with code 1 and stderr message naming the offending source task ID, the matched phrasing, and the missing reference.
- **CLI internal-only** (per GA-006): no new `tasks.py scan-implicit-deps` subcommand. The scan runs automatically every time `compute_waves` is called.
- Tests: `tests/test_wave_planner_implicit_deps.py` mirroring F005's tmp_path-with-subprocess-cwd pattern. Synthetic task YAMLs in tmpdir; drive `compute_waves` directly (pure function).

### Out of Scope

- Spec-enforcer stub-marker grep (that's F007, shipped).
- Pre-decompose detection (warning at `/decompose` time if a task description contains stub phrasings without an explicit dep). Future PRD candidate.
- Phrasings beyond the three documented (per-project config could be added later if needed; out of scope for v1).
- Modifying the on-disk task YAML to materialize the edge (the in-memory promotion is sufficient for wave-packing).
- Retroactive scan of shipped F001-F007 task YAMLs (forward-only convention per BR-007 of F001).
- A new CLI subcommand for the scan (per GA-006 — internal-only).
- Phrasings in fields other than `context` and `acceptance_criteria` (e.g., `title`, `requires_reading` paths). The scan is scoped to the two free-text fields.

## Requirements

### BR-001: Pre-pack scan location and signature

The implicit-dependency scan is implemented as a new helper function in `scripts/tasks.py` (e.g., `_scan_implicit_deps(tasks: list[dict]) -> tuple[list[dict], list[tuple[str, str, str, str]]]`) and invoked from the very top of `compute_waves(tasks)`, before `leaf_tasks = get_leaf_tasks(tasks)`. The helper returns the augmented task list (with promoted dep edges merged into each task's `dependencies`) and a list of promoted-edge tuples `(source_task_id, target_task_id, matched_phrase, source_field)` for downstream printing.

### BR-002: Three implicit-dependency phrasings

Three case-insensitive Python regex patterns, each with one capture group for the target task ID:

- `stub\s+until\s+task\s+([0-9]+)`
- `placeholder\s+for\s+task\s+([0-9]+)`
- `until\s+task\s+([0-9]+)\s+lands`

All compile with `re.IGNORECASE`. The captured group becomes the target task ID. Multiple matches in one field promote multiple edges.

### BR-003: Fields scanned per task

The scan walks two fields of each task dict:

1. `task.get("context", "")` — the free-form prose context block.
2. Each string in `task.get("acceptance_criteria", [])` — every AC bullet, scanned independently.

Other fields (`title`, `requires_reading` paths, `files_in_scope` paths) are NOT scanned.

### BR-004: In-memory edge promotion

For each match, the captured task ID is appended to the source task's `dependencies` list IN-MEMORY only. The on-disk task YAML file is NOT modified. The wave-packer (existing logic in `compute_waves`) operates on the augmented task list as if the edge had been authored explicitly. The augmented dependencies are visible to subsequent calls within the same Python process; persisting changes to disk is OUT of scope.

### BR-005: Idempotency

If the captured task ID already appears in the source task's `dependencies` list, the helper does NOT double-add it. The promoted-edge tuple list also de-duplicates: the same `(source, target, phrase, field)` tuple appears at most once even if matched twice in different fields.

### BR-006: Fail-fast on unknown task ID

If a captured task ID does NOT exist as a `task_id` in the loaded task list (the feature's task set), the helper raises `SystemExit(1)` (or equivalent — the scripts use `sys.exit(1)` per existing convention) with a stderr message of the form: `error: task <source_id> in feature <feature> references task <captured_id> via phrase "<matched>" but no such task exists in this feature.` Exit code is 1 (matches the existing fail-fast convention used by `feature_id.py`, `git_tags.py`, `value_hypothesis.py`). The scan halts immediately on the first unknown reference; subsequent matches are not processed.

### BR-007: Promoted-edge printing in cmd_waves

The `cmd_waves` function (line 420) accepts the promoted-edge tuple list (returned by the new `compute_waves` signature) and prints one note per promoted edge in the wave-output stream. Format:

```
  note: promoted task <source> → task <target> (matched: "<phrase>" in <source>.<field>)
```

where `<field>` is `context` or `acceptance_criteria[<index>]`. Notes appear once at the top of the output, before the first wave block, so operators see the augmented edge set before reading the wave layout.

### BR-008: Test contract

A new test file `tests/test_wave_planner_implicit_deps.py` mirrors F005's tmp_path-with-subprocess-cwd pattern for grep-based contract tests. Tests cover: (a) all three phrasings fire (case-insensitive), (b) edge promotion appears in the augmented task list, (c) fail-fast on unknown task ID with correct exit code and stderr substring, (d) idempotency when explicit edge already present, (e) both `context` and `acceptance_criteria` fields are scanned, (f) `cmd_waves` output contains the note format from BR-007.

### BR-009: Forward-only

F008 applies to NEW invocations of `compute_waves` after `install.sh` deploys the updated `scripts/tasks.py` to `~/.claude/scripts/`. Already-completed feature builds (F001-F007) are NOT retroactively scanned. Matches BR-007 of F001 (forward-only convention).

## Acceptance Criteria

1. **Helper function added** — `scripts/tasks.py` contains a new private helper `_scan_implicit_deps(tasks)` (or equivalent name) that returns a 2-tuple `(augmented_tasks, promoted_edges)` where `augmented_tasks` is the input list with promoted edges merged into each task's `dependencies`, and `promoted_edges` is a list of tuples `(source_task_id, target_task_id, matched_phrase, source_field)`.
2. **`compute_waves` invokes the scan first** — the first non-trivial line of `compute_waves` is the call to the implicit-dep scanner. The scanned tasks are passed to the existing wave-packing logic.
3. **Three regex patterns present** — `scripts/tasks.py` contains the three documented regex patterns (case-insensitive): `stub\s+until\s+task\s+([0-9]+)`, `placeholder\s+for\s+task\s+([0-9]+)`, `until\s+task\s+([0-9]+)\s+lands`. All three are used in the scan.
4. **`task.context` is scanned** — the helper extracts `task.get("context", "")` and runs each of the three regex patterns against it.
5. **Each AC string is scanned** — the helper iterates `task.get("acceptance_criteria", [])` and runs each of the three regex patterns against every AC string. The matched-field record distinguishes `context` vs `acceptance_criteria[<index>]`.
6. **In-memory promotion only** — when a match fires, the helper appends the captured task ID to the source task's `dependencies` list in the in-memory dict. NO writes to disk. Specifically: no task YAML file modifications, no `tasks.py set-status` invocations, no side effects on the filesystem.
7. **Idempotency** — if the captured task ID already exists in the source task's `dependencies` list, the helper does NOT double-add it. The promoted-edge tuple list de-duplicates exact-match tuples.
8. **Fail-fast on unknown task ID** — if any captured task ID does not match a `task_id` in the loaded task list, the helper calls `sys.exit(1)` with a stderr message containing the literal substring `references task` AND the source task ID AND the captured (missing) task ID AND the matched phrase verbatim. The scan halts on the first unknown reference.
9. **Promoted-edge notes in cmd_waves output** — `cmd_waves` prints one note per promoted edge before the first wave block. Format string: `  note: promoted task <source> → task <target> (matched: "<phrase>" in <source>.<field>)`. The notes are de-duplicated to match BR-005.
10. **Test file exists with required contract tests** — `tests/test_wave_planner_implicit_deps.py` exists with at least 6 test functions: one per phrasing (3 tests), one for edge promotion correctness, one for fail-fast on unknown task ID, one for idempotency, plus AC-coverage tests for both-fields-scanned and cmd_waves note format.
11. **All test functions use pytest tmpdir** — no test in `tests/test_wave_planner_implicit_deps.py` writes to or reads from real `.etc_sdlc/features/*/tasks/` directories. Tests construct synthetic task dicts in-memory or write synthetic YAMLs to `tmp_path`.
12. **Regression baseline** — full pytest suite passes (≥ 703 baseline tests + the new F008 tests, no regressions) when running `python3 -m pytest --tb=short -q` from the project root.
13. **Preservation + changeset scope** — no F001-F007 release-notes.md, verification.md, task YAML, or other shipped artifacts are modified by this build. The changeset is exactly: `scripts/tasks.py`, `tests/test_wave_planner_implicit_deps.py`, plus the F008 PRD copy at `spec/wave-planner-implicit-deps.md`.

## Edge Cases

1. **Task with empty `context` and empty `acceptance_criteria`** — both fields are empty strings or empty lists. Behavior: scan finds no matches; no edges promoted; task passes through unchanged.
2. **Task with `context: null` (YAML null value)** — `task.get("context", "")` returns `""` instead of `None` via the default; safe regex no-op. Same for `acceptance_criteria` if absent.
3. **Phrase appears in code-block fence within `context`** — e.g., `context` contains `` `stub until task 005` `` inside a Markdown code fence as documentation rather than as a real implicit dep. Behavior: still matches and promotes. False positive accepted; rationale is the same as F007's regex grep — code-block awareness adds parser complexity without reliably distinguishing intent. Operator can rephrase the doc.
4. **Captured task ID format is non-canonical** — phrasing names `task 5` (not `005`), but feature has only `005`-zero-padded task IDs. Behavior: regex captures `5`; the scan compares `5` against the task-list `task_id` set (which contains `005`). No match → fail-fast on unknown task ID per BR-006. Operator must use the canonical zero-padded form in the phrasing. The fail-fast message helps the operator self-correct.
5. **Self-referential phrasing** — task `005`'s context says "stub until task 005 lands" (cyclic). Behavior: scan promotes `005 → 005` self-loop. The wave-packer's existing cycle detection (line 195's "Circular dependency or unresolvable" branch) catches it and dumps to the last wave. The fail-fast does NOT fire because the captured task ID DOES exist. The cycle-handling is the existing wave-packer's job; F008 only adds the edge.
6. **Phrasing matches multiple times in same field** — `context` has `"stub until task 003. stub until task 004."`. Behavior: both edges promoted (003 and 004). The promoted-edge tuple list contains both entries (different captured IDs, so they're distinct tuples).
7. **Phrasing matches in BOTH `context` AND an AC** — same captured task ID appears in `context` and in `acceptance_criteria[0]`. Behavior: per BR-005 idempotency, the edge is added once to `dependencies`; the promoted-edge tuple list contains TWO distinct entries (different `source_field` values: `context` and `acceptance_criteria[0]`). The cmd_waves output prints two notes — one per source field. This is intentional: the operator sees both occurrences in the audit trail.
8. **Decomposed parent's context contains an implicit dep** — parent task is decomposed (status=`decomposed`, not pending) but its `context` matches a phrasing. Behavior: parent task is excluded from leaf-task processing per existing `compute_waves` logic at line 169-172. The scan should ALSO skip decomposed/completed tasks (apply the same status filter). The promoted edges only apply to leaf tasks that will actually run.
9. **Cross-feature phrasing** — task `005` in feature `F008` has context "stub until task 003" and the captured `003` exists in feature `F007` but NOT in `F008`. Behavior: when `compute_waves` is called with `feature=F008` filter, only F008's task list is loaded — `003` is unknown to that scope, so fail-fast fires. Cross-feature implicit deps are NOT supported; the fail-fast message guides operator to either add the dep explicitly across features or move the task.
10. **Captured task ID is itself decomposed** — phrasing matches `task 003`, but `003` is a parent task with status `decomposed`. Behavior: the edge is promoted; the wave-packer's existing logic treats decomposed tasks as already-satisfied (line 164-168 puts `decomposed` task IDs in `satisfied_ids`). So the source task's wave is NOT delayed. This is correct: if `003` is decomposed, its subtasks are tracked separately.
11. **Pre-existing dependencies and promoted dependencies overlap in a wave-conflict pattern** — task `005` has explicit `dependencies: [003]` AND a phrasing "stub until task 004 lands". Behavior: scan promotes `005 → 004`. Wave-packer sees `005`'s dependencies as `[003, 004]`. Both must be satisfied before `005` can run. No conflict; existing logic handles it.

## Technical Constraints

- **Forward-only convention.** Per BR-007 of F001 + reaffirmed across F002-F007. F008 applies to NEW `compute_waves` invocations after install.sh deploys the updated `scripts/tasks.py` to `~/.claude/scripts/`. No retroactive scan of F001-F007 task YAMLs.
- **Sonnet/Opus-1M child-dispatch workaround.** Every Agent-tool call during /build MUST pass `model: opus` override. Documented across F002-F007 (5 PRDs).
- **Pure Python stdlib.** `scripts/tasks.py` uses only stdlib imports (`re`, `sys`, `os`, `yaml`, `pathlib`). F008 does NOT add new dependencies. The `re` module's `IGNORECASE` flag is sufficient for case-insensitive matching.
- **In-memory only — no on-disk YAML mutation.** Per BR-004, the helper modifies the task dict's `dependencies` list in-place but does NOT persist changes. Subsequent calls to `tasks.py list` or `tasks.py status` see the on-disk state, not the in-memory augmentation.
- **`compute_waves` signature change is internal.** `compute_waves(tasks)` previously returned `dict[int, list[dict]]` (wave map). The new signature returns `tuple[dict[int, list[dict]], list[tuple[str, str, str, str]]]` (waves AND promoted-edge tuples). The only caller is `cmd_waves`; the change is local. /build's invocation of `cmd_waves` (via subprocess) sees the formatted output, not the raw return value.
- **Test fixture isolation.** Tests construct synthetic task dicts in memory or write synthetic YAMLs to pytest's `tmp_path`. NO test reads or writes real `.etc_sdlc/features/*/tasks/` task files. This protects the F001-F007 task corpus from accidental mutation during test runs.
- **PEP 686 future-proofing.** All file-open sites in F008's deliverables (test file, any helper scripts) pass `encoding="utf-8"` explicitly. Mirrors F004's compile-sdlc.py edit at 9 text-mode open sites.
- **Pyright workaround inventory.** F008 likely needs only the autouse-fixture pattern's `_ = _compile_sdlc` reference IF the test file uses the autouse compile fixture. Since F008 doesn't depend on a compiled artifact (the change is in `scripts/tasks.py`, not in `agents/` or `skills/`), the test file may NOT need the compile fixture.
- **No INVARIANTS.md, no `.etc_sdlc/antipatterns.md`.** Both absent in this repo.

## Security Considerations

1. **Regex DoS guard not required.** The three regex patterns are simple (no nested quantifiers, no backreferences); they don't have catastrophic backtracking risk. The scanned strings (`context` and `acceptance_criteria` items) are operator-authored task YAMLs — fully trusted input. F008 does not need an external regex-DoS sanitizer.
2. **No filesystem operations triggered by scan content.** The helper reads task fields and updates an in-memory list. It does NOT open files, execute commands, or follow paths derived from the scanned text. Path-traversal attacks via crafted phrasings are not applicable.
3. **stderr message sanitization.** The fail-fast message (BR-006) embeds user-authored substrings: source task ID, captured task ID, matched phrase. To prevent terminal-control-sequence injection (e.g., a hostile task with ANSI escape codes in its `context`), the matched-phrase string is stripped of control characters (regex `[\x00-\x1f\x7f]`) and capped at 256 chars before being printed to stderr. Mirrors F003's operator-supplied path sanitization and F007's matched-line sanitization.
4. **`cmd_waves` note printing also sanitizes the matched phrase** — same control-character strip + 256-char cap as the stderr message. Notes are printed to stdout for the operator; same threat model applies.
5. **No YAML injection.** The helper does NOT serialize the augmented dependencies back to disk. If it ever did (out of scope for v1), it would need to use `yaml.safe_dump` with `default_style='|'` or similar to prevent injection via crafted task IDs.
6. **Cross-feature isolation enforced by `feature` filter.** `compute_waves` is invoked from `cmd_waves(root, feature=feature)`, which calls `load_all_tasks(root, feature=feature)`. F008's scan operates only on the loaded task subset — cross-feature implicit deps fail-fast (per Edge Case 9). This prevents one feature's task from inadvertently scheduling itself against another feature's task ID.
7. **Captured task ID format constrained to `[0-9]+`.** The regex capture groups only match digit sequences. SQL/shell/path-injection via captured IDs is not applicable — non-digit characters cannot be captured.
8. **Test isolation.** Tests use pytest tmpdir per BR-008 and Constraint #6. They do NOT touch real `.etc_sdlc/features/*/tasks/` task YAMLs. Accidental mutation of the F001-F007 corpus during test runs is impossible by construction.

## Module Structure

### Created

- `tests/test_wave_planner_implicit_deps.py` — new contract-test module (~250-300 lines). Mirrors F005's `tests/test_completion_report.py` pattern: pytest tmp_path fixtures + synthetic task dicts in-memory + `subprocess.run` for end-to-end CLI tests where applicable. Tests cover all three phrasings, edge promotion, fail-fast, idempotency, both-fields-scanned, and `cmd_waves` note format.

### Modified

- `scripts/tasks.py` — three changes:
  1. New private helper `_scan_implicit_deps(tasks: list[dict]) -> tuple[list[dict], list[tuple[str, str, str, str]]]` defined near `compute_waves` (insertion point: just before line 150). Helper holds the three regex patterns as module-level constants for testability.
  2. `compute_waves` (line 150) updated to call `_scan_implicit_deps` first, take its augmented task list and promoted-edge tuple list, return both as a 2-tuple.
  3. `cmd_waves` (line 420) updated to unpack the new 2-tuple return value, print the promoted-edge notes before the wave block iteration, and handle the empty-promoted-list case gracefully (no extra blank line).

### Created at /spec time (already exist)

- `.etc_sdlc/features/F008-wave-planner-implicit-deps/spec.md` — this PRD.
- `.etc_sdlc/features/F008-wave-planner-implicit-deps/value-hypothesis.yaml` — outcome contract.
- `.etc_sdlc/features/F008-wave-planner-implicit-deps/state.yaml` — Phase 2.75 classification + author_role.
- `.etc_sdlc/features/F008-wave-planner-implicit-deps/gray-areas.md` — 7 entries (4 research + 3 user).
- `.etc_sdlc/features/F008-wave-planner-implicit-deps/research/codebase.md` — Phase 2 codebase findings.
- `spec/wave-planner-implicit-deps.md` — byte-identical copy of the spec.md above, for browsability.

### NOT in scope (do not touch)

- `agents/*.md` — F008 is a pure scripts/tasks.py change.
- `skills/*.md` — /spec, /build, /implement, /decompose all unchanged.
- `dist/**` — F008 doesn't trigger compile-sdlc.py edits.
- `hooks/*.sh` — F008 has no hook injection.
- `standards/process/*.md` — F008's contract is too small to warrant a standards doc.
- `.etc_sdlc/features/F001-F007*` — forward-only.
- Any test file other than the new `tests/test_wave_planner_implicit_deps.py`.

## Research Notes

**Codebase findings (Phase 2):**
- `scripts/tasks.py::compute_waves` at line 150 — pure function, takes `list[dict]`, returns wave map. Iterates over leaf tasks, packs by satisfied dependencies. F008's pre-pack scan slots at the very top.
- `cmd_waves` at line 420 — wraps `compute_waves` for CLI. Loads tasks via `load_all_tasks(root, feature=feature)`. F008 modifies this to print promoted-edge notes alongside wave blocks.
- Task YAML schema: `task_id`, `title`, `assigned_agent`, `status`, `requires_reading`, `files_in_scope`, `acceptance_criteria`, `dependencies`, `context`, `parent_task` (optional). NO `prompt` or `description` fields — the F008 draft used loose terminology; tightened to `context` + `acceptance_criteria`.
- Test pattern from F005 (`tests/test_completion_report.py`) — pytest tmp_path + subprocess.run with `cwd=str(tmp_path)`. F008 mirrors this for end-to-end CLI tests AND adds in-memory dict tests for the pure-function `_scan_implicit_deps` helper.
- Forward-only convention reaffirmed.

**Best Practices (precedent):**
- Build-system implicit-dep detection (Bazel, Pants, Buck) operates on code AST, not planning artifacts — no direct precedent.
- Lint-style "TODO: depends on X" code-comment detection is the closest cousin but operates on source code.
- F008's pattern is novel-but-simple: regex-scan free-text fields, promote captured task IDs to hard edges. No external pattern overrides the local design.

**Antipatterns:** No `.etc_sdlc/antipatterns.md` file exists; absence noted.
