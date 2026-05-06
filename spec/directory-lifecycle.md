# PRD: Two-State Features Lifecycle (F009)

## Summary

F009 restructures `.etc_sdlc/features/` from a flat `F<NNN>-<slug>/` layout to a two-state lifecycle: `features/active/F<NNN>-<slug>/` for in-flight work and `features/shipped/F<NNN>-<slug>/` for done audit-frozen work. A separate top-level `.etc_sdlc/rejections/F<NNN>-<slug>/` location holds operator-actionable rejection trails from /spec's three-state classifier. There is **no** `archived/` subdir — killed/abandoned ideas are deleted from the working tree (git history preserves them) and rationale is captured in ADRs at `docs/adrs/`. The user explicitly rejected `archived/` because anything inside `features/` is implicit AI dispatch context, and keeping killed specs adjacent to active work risks the AI pattern-matching dead designs as precedent.

The change touches four code sites: (1) `scripts/feature_id.py` gains a new `resolve_feature_path` helper and an updated `_scan_max_feature_id` that rglobs across `.etc_sdlc/` for any `F<NNN>-*` directory; (2) /spec's rejection-write flow at `skills/spec/SKILL.md:522` adds a `git mv` step that moves the entire feature dir from `features/active/` to `rejections/` after writing `rejected.md`; (3) /build's terminal-phase close at `skills/build/SKILL.md:714-737` adds a `git mv` step that moves the dir from `features/active/` to `features/shipped/` after the release tag and release-notes.md are written; (4) `skills/metrics/SKILL.md` and four cosmetic doc-strings in /spec and /build are updated to use the resolver / mention the new layout.

**Forward-only migration.** F001-F008 + the F006 placeholder remain at their existing flat path `.etc_sdlc/features/F<NNN>-<slug>/`. Only new features after F009 ships use the new layout. The resolver checks all four locations (legacy flat, active, shipped, rejections) to keep existing callers working. **`git mv` is mandatory** for state transitions — `mv + git add` would lose rename history through `git log`'s similarity heuristic.

## Scope

### In Scope

- Edit `scripts/feature_id.py`:
  - `_scan_max_feature_id` updated from `features_dir.iterdir()` to rglob across `.etc_sdlc/` root for any `F<NNN>-*` directory matching `_FEATURE_DIR_PATTERN`. Function signature accepts `etc_sdlc_root: Path` (or accepts both with backward-compat).
  - `allocate_next` updated to land new features at `features/active/F<NNN>-<slug>/` instead of the legacy flat `features/F<NNN>-<slug>/`.
  - New public function `resolve_feature_path(feature_id: str, etc_sdlc_root: Path) -> Path | None` that checks four locations in priority order (legacy flat → active → shipped → rejections) and returns the first hit (or None).
- Edit `skills/spec/SKILL.md` at the rejection-write flow (line 522 region):
  - After writing `rejected.md` to `<feature_path>`, invoke `git mv <feature_path> .etc_sdlc/rejections/F<NNN>-<slug>/`.
  - On `git mv` failure, exit non-zero with stderr message naming source, target, and git's error.
- Edit `skills/build/SKILL.md` at Step 7.5 (line 714-737 region):
  - After Step 7.5b (release-notes.md write), invoke `git mv .etc_sdlc/features/active/F<NNN>-<slug> .etc_sdlc/features/shipped/F<NNN>-<slug>`.
  - On `git mv` failure, abort /build with clear error (release artifacts already written; operator must remediate).
- Edit `skills/metrics/SKILL.md` lines 104+137 to use `resolve_feature_path` instead of hard-coded `features/F<NNN>-<slug>/value-hypothesis.yaml`.
- Edit 4 cosmetic doc-strings in `skills/spec/SKILL.md` (Phase 5 final-summary at ~line 952, post-completion summary at ~line 970) and `skills/build/SKILL.md` (artifacts-list at ~line 786, release-notes path at ~line 733).
- Compile `dist/skills/spec/SKILL.md`, `dist/skills/build/SKILL.md`, and `dist/skills/metrics/SKILL.md` byte-identical via `compile-sdlc.py`.
- Add `tests/test_directory_lifecycle.py` mirroring F005/F008 pattern: pytest tmp_path + synthetic `.etc_sdlc/` tree + subprocess.run with `cwd=str(tmp_path)`.

### Out of Scope

- Migration of F001-F008 + F006 placeholder to the new layout (forward-only convention per BR-007 of F001).
- A `--reserve` flag on `feature_id.py` (the F006 placeholder convention). Defer to F010+ if operator-tooling becomes painful.
- An `archived/` subdir (explicitly rejected per the user's positive-affirmation concern).
- Resubmission flow that LINKS the new F<NNN> to the old rejected F<NNN> (git history is enough).
- ADR-writing automation for killed features.
- Auto-generated README.md inside `.etc_sdlc/rejections/`.
- Updates to any agent body — F009 is purely lifecycle infrastructure.
- Updates to `hooks/inject-standards.sh` — F009 has no hook injection.
- Resolver adoption in other scripts (`release_notes.py`, `completion_report.py`, `git_tags.py`, `value_hypothesis.py`, `tasks.py`) — defer to F010+.

## Requirements

### BR-001: Allocator three-location scan

`scripts/feature_id.py::_scan_max_feature_id` is updated to rglob across `.etc_sdlc/` root for any directory whose name matches `_FEATURE_DIR_PATTERN` (`^F(\d{3})(?:-.*)?$`). The scan finds matching dirs at any depth: legacy flat `features/F<NNN>-<slug>/`, new `features/active/F<NNN>-<slug>/`, `features/shipped/F<NNN>-<slug>/`, and `rejections/F<NNN>-<slug>/`. The function returns the highest captured integer ID across all found locations (0 if none).

### BR-002: Allocator new-feature placement

`scripts/feature_id.py::allocate_next` lands new features at `<features_dir>/active/F<NNN>-<slug>/`. The `active/` subdirectory is created with `mkdir(parents=True, exist_ok=True)` if absent. The atomic `os.mkdir` allocation pattern is preserved for race-free F<NNN> uniqueness.

### BR-003: Path-resolution helper

A new public function `resolve_feature_path(feature_id: str, etc_sdlc_root: Path) -> Path | None` in `scripts/feature_id.py` checks four locations in priority order:

1. `<etc_sdlc_root>/features/F<NNN>-<slug>/` (legacy flat — F001-F008 + F006)
2. `<etc_sdlc_root>/features/active/F<NNN>-<slug>/`
3. `<etc_sdlc_root>/features/shipped/F<NNN>-<slug>/`
4. `<etc_sdlc_root>/rejections/F<NNN>-<slug>/`

Returns the first hit as a `Path` (resolved). Returns `None` if no hit. Slug-suffix matching uses glob (`F<NNN>-*`) — caller passes only the `F<NNN>` ID.

### BR-004: /spec rejection-move

`skills/spec/SKILL.md` rejection-write flow (line 522 region) is updated. After writing `rejected.md` to the allocated feature directory, /spec invokes `git mv <feature_path> .etc_sdlc/rejections/F<NNN>-<slug>/` (creating `.etc_sdlc/rejections/` parent if absent). On `git mv` failure, /spec exits non-zero with stderr message naming source, target, and git's error.

### BR-005: /build terminal-close active→shipped move

`skills/build/SKILL.md` Step 7.5 (line 714-737 region) is extended with a new sub-step (Step 7.5c, after release-notes.md write at 7.5b): invoke `git mv .etc_sdlc/features/active/F<NNN>-<slug> .etc_sdlc/features/shipped/F<NNN>-<slug>` (creating `features/shipped/` parent if absent). On `git mv` failure, /build aborts with stderr message and exit code 1.

### BR-006: Backward-compat resolver use

`skills/metrics/SKILL.md` lines 104 and 137 are updated to call `resolve_feature_path` instead of hard-coding `features/F<NNN>-<slug>/`.

### BR-007: Cosmetic doc-string updates

Four cosmetic doc-strings in skill bodies are updated to mention the new layout:

- `skills/spec/SKILL.md` Phase 5 final-summary (line ~952)
- `skills/spec/SKILL.md` post-completion guidance (line ~970)
- `skills/build/SKILL.md` artifacts-list (line ~786)
- `skills/build/SKILL.md` release-notes.md path (line ~733)

### BR-008: Byte-identical compile

After all edits, `python3 compile-sdlc.py spec/etc_sdlc.yaml` runs and `diff -q skills/spec/SKILL.md dist/skills/spec/SKILL.md` AND `diff -q skills/build/SKILL.md dist/skills/build/SKILL.md` AND `diff -q skills/metrics/SKILL.md dist/skills/metrics/SKILL.md` all exit 0.

### BR-009: Test contract

A new test file `tests/test_directory_lifecycle.py` mirrors F005/F008 pattern. Tests cover: (a) allocator rglob across all four locations finds the highest F<NNN>, (b) `resolve_feature_path` returns the right path for each location and `None` when missing, (c) allocator creates new dirs under `features/active/`, (d) /spec rejection-mv (subprocess test), (e) /build active→shipped mv (subprocess test), (f) backward-compat: legacy flat F001-F008 paths remain readable via the resolver, (g) `git mv` failure semantics (target exists → abort, exit non-zero, stderr).

### BR-010: Forward-only

F009 applies to NEW feature allocations after install.sh deploys the updated `feature_id.py` to `~/.claude/scripts/`. F001-F008 + the F006 placeholder remain at legacy flat paths and are NOT migrated. Matches BR-007 of F001 (forward-only convention).

## Acceptance Criteria

1. **Allocator rglob** — `scripts/feature_id.py::_scan_max_feature_id` uses `Path(...).rglob(...)` rooted at `.etc_sdlc/` directory. The function inspects each match's name against `_FEATURE_DIR_PATTERN` and returns the highest captured integer.
2. **Allocator placement under active/** — `scripts/feature_id.py::allocate_next` creates new feature directories at `<features_dir>/active/F<NNN>-<slug>/`. The `active/` parent is created with `parents=True, exist_ok=True` semantics. Legacy flat path NOT used for new allocations.
3. **Resolver four-location lookup** — `scripts/feature_id.py::resolve_feature_path(feature_id, etc_sdlc_root)` is a public function that checks legacy flat → active → shipped → rejections in priority order and returns the first matching `Path` or `None`. Slug-suffix matching uses glob `F<NNN>-*`.
4. **/spec rejection-mv** — `skills/spec/SKILL.md` rejection-write flow contains a `git mv` invocation that moves the feature dir from `<feature_path>` to `.etc_sdlc/rejections/F<NNN>-<slug>/` after `rejected.md` is written. The mv is invoked via subprocess; failure aborts /spec with stderr and non-zero exit.
5. **/build active→shipped mv** — `skills/build/SKILL.md` contains a Step 7.5c sub-step inserted after Step 7.5b. The sub-step invokes `git mv .etc_sdlc/features/active/F<NNN>-<slug> .etc_sdlc/features/shipped/F<NNN>-<slug>`. On failure, /build aborts with stderr and exit code 1; release tag and release-notes.md remain.
6. **metrics resolver adoption** — `skills/metrics/SKILL.md` lines previously hard-coding `features/F<NNN>-<slug>/value-hypothesis.yaml` now reference `resolve_feature_path`. The compiled dist version reflects the change.
7. **Cosmetic doc-string updates** — the four doc-strings named in BR-007 are updated in their source files. The compiled dist versions reflect the changes.
8. **Byte-identical compile** — after `python3 compile-sdlc.py spec/etc_sdlc.yaml`, `diff -q` for spec/build/metrics SKILL.md vs their dist counterparts all exit 0.
9. **Test file with required coverage** — `tests/test_directory_lifecycle.py` exists with at least 7 test functions covering the BR-009 list.
10. **All test functions use pytest tmp_path** — no test reads/writes real `.etc_sdlc/features/` or `.etc_sdlc/rejections/`. Tests construct synthetic trees in `tmp_path` and use `subprocess.run` with `cwd=str(tmp_path)` for end-to-end checks.
11. **Forward-only invariant** — F001-F008 + the F006 placeholder remain at their existing legacy flat paths after F009 ships. Test file includes a fixture that creates a synthetic legacy flat path and asserts the resolver finds it.
12. **Regression baseline** — full pytest suite passes (≥ 715 baseline tests + new F009 tests, no regressions) when running `python3 -m pytest --tb=short -q`.
13. **Preservation + changeset scope** — no F001-F008 release-notes.md, verification.md, task YAML, or other shipped artifacts modified. The changeset is exactly: `scripts/feature_id.py`, `skills/spec/SKILL.md`, `skills/build/SKILL.md`, `skills/metrics/SKILL.md`, the corresponding `dist/skills/*/SKILL.md` compiled outputs, `tests/test_directory_lifecycle.py`, plus the F009 PRD copy at `spec/directory-lifecycle.md`.

## Edge Cases

1. **Empty `.etc_sdlc/` (greenfield repo)** — allocator rglob finds zero matches; `_scan_max_feature_id` returns 0; `allocate_next` produces F001 under `features/active/F001-<slug>/`.
2. **`.etc_sdlc/` exists but `features/` doesn't** — allocator creates `features/active/` parent via `mkdir(parents=True, exist_ok=True)`. No error.
3. **`features/active/` and `features/shipped/` both have F<NNN>-<slug>/ for same N** — should be impossible by construction. If it occurs, resolver returns FIRST hit in priority order.
4. **F001-F008 directories at legacy flat path AFTER F009 ships** — resolver's priority-1 location finds them. New features go to `features/active/` per BR-002.
5. **F006 placeholder collision** — `.etc_sdlc/features/F006-design-phase-split/` exists at the legacy flat path with only a `RESERVED.md` file. Allocator's rglob finds it (treats it as a real F006 allocation) and allocates F010 next.
6. **`git mv` target already exists during /build close** — operator manually created `features/shipped/F<NNN>-<slug>/`. `git mv` refuses; /build aborts with exit 1 + stderr. Release tag and release-notes.md remain.
7. **`git mv` target already exists during /spec rejection-mv** — operator already has `rejections/F<NNN>-<slug>/`. Same semantics: /spec aborts with stderr.
8. **Operator edits feature dir AFTER `active/` → `shipped/` mv** — git tracks the rename canonically; future `git log --follow` works through the rename.
9. **Resolver called with malformed feature_id** — non-matching input returns `None`. Caller's responsibility to validate.
10. **Cross-feature rglob false positive** — operator manually created a non-feature dir matching the regex. Allocator treats it as taken. Operator should rename non-feature dirs that match.
11. **Compile-sdlc.py fails after edits** — byte-identical-compile invariant breaks. Operator inspects the diff and fixes the source file.
12. **Resolver lookup during F009's own build** — F009's allocator is the OLD version (since F009 is still being built). The legacy flat path matches; resolver returns it. After F009 ships, F010+ uses the new layout.
13. **Concurrent /spec invocations** — allocator's `os.mkdir` atomicity guarantees distinct F<NNN> values. Both new dirs land in `features/active/`. No conflict.

## Technical Constraints

- **Forward-only convention.** Per BR-007 of F001 + reaffirmed across F002-F008. F009 applies to NEW feature allocations after install.sh deploys the updated `feature_id.py`. F001-F008 + F006 placeholder remain at legacy flat path.
- **`git mv` mandate.** State transitions MUST use `git mv` not `mv + git add`. Rationale: `git mv` makes the rename canonical in the index.
- **Sonnet/Opus-1M child-dispatch workaround.** Every Agent-tool call during /build MUST pass `model: opus` override. Documented across F002-F008.
- **Pure Python stdlib.** `scripts/feature_id.py` uses only stdlib. F009 adds NO new dependencies. The `git mv` invocation uses `subprocess.run(["git", "mv", src, dst])`.
- **Atomic allocator preserved.** `allocate_next` continues to use `os.mkdir` for race-free F<NNN> uniqueness.
- **Test fixture isolation.** Tests construct synthetic `.etc_sdlc/` trees in `tmp_path`. Subprocess tests use `cwd=str(tmp_path)`.
- **Byte-identical compile invariant.** `compile-sdlc.py` produces byte-identical `dist/skills/{spec,build,metrics}/SKILL.md`.
- **PEP 686 future-proofing.** All file-open sites pass `encoding="utf-8"` explicitly.
- **Pyright workaround inventory.** Likely needs `_ = _compile_sdlc` autouse-fixture reference if test uses the compile fixture. F005's `# pyright: ignore[reportMissingImports]` may apply for sys.path-manipulated imports.
- **No INVARIANTS.md, no `.etc_sdlc/antipatterns.md`.** Both absent.

## Security Considerations

1. **Path-traversal guard on resolver input.** `resolve_feature_path` validates that `feature_id` matches `_FEATURE_DIR_PATTERN`. Inputs containing `../`, absolute paths, or other path-traversal markers return `None`.
2. **Resolver does NOT Read file contents.** Returns a `Path` object only.
3. **`git mv` invocation uses argv list, not shell string.** `subprocess.run(["git", "mv", src, dst])` — eliminates shell-injection risk from operator-controlled feature slugs.
4. **`git mv` failure surface preserves git's stderr verbatim.** No silent swallow.
5. **`features/active/` creation uses safe parents.** `mkdir(parents=True, exist_ok=True)`. Race-safe (atomic).
6. **Resolver lookup is read-only.** No filesystem mutations.
7. **rglob scope bounded by `.etc_sdlc/` root.** Cannot escape the project tree.
8. **No new write paths introduced.** All writes scoped to `.etc_sdlc/features/{active,shipped}/` and `.etc_sdlc/rejections/`.
9. **Test fixture isolation prevents pollution.** Per BR-009 + AC10, tmp_path only.

## Module Structure

### Created

- `tests/test_directory_lifecycle.py` — new contract-test module (~300-350 lines). Mirrors F005/F008 pattern: pytest tmp_path fixtures + synthetic `.etc_sdlc/` trees + subprocess.run with `cwd=str(tmp_path)`. Tests cover all 7 BR-009 items.

### Modified

- `scripts/feature_id.py` — three changes:
  1. `_scan_max_feature_id` updated to rglob across `.etc_sdlc/` root.
  2. `allocate_next` updated to land new features at `<features_dir>/active/F<NNN>-<slug>/`.
  3. New public function `resolve_feature_path(feature_id: str, etc_sdlc_root: Path) -> Path | None`.
- `skills/spec/SKILL.md` — two changes: rejection-mv at line 522 region; cosmetic doc-string updates at ~952 and ~970.
- `skills/build/SKILL.md` — two changes: Step 7.5c at line 714-737 region; cosmetic doc-string updates at ~786 and ~733.
- `skills/metrics/SKILL.md` — one change at lines 104+137: replace hard-coded path with resolver-aware language.
- `dist/skills/spec/SKILL.md`, `dist/skills/build/SKILL.md`, `dist/skills/metrics/SKILL.md` — compiled outputs via `compile-sdlc.py` (byte-identical).

### Created at /spec time (already exist)

- `.etc_sdlc/features/F009-directory-lifecycle/spec.md` — this PRD.
- `.etc_sdlc/features/F009-directory-lifecycle/value-hypothesis.yaml` — outcome contract.
- `.etc_sdlc/features/F009-directory-lifecycle/state.yaml` — Phase 2.75 classification + author_role.
- `.etc_sdlc/features/F009-directory-lifecycle/gray-areas.md` — 8 entries (5 research + 3 user).
- `.etc_sdlc/features/F009-directory-lifecycle/research/codebase.md` — Phase 2 codebase findings.
- `spec/directory-lifecycle.md` — byte-identical copy of the spec.md above, for browsability.

### NOT in scope (do not touch)

- `agents/*.md` — F009 is purely lifecycle infrastructure.
- `hooks/*.sh` — no hook injection.
- `standards/process/*.md` — F009's contract too small to warrant a standards doc.
- Other scripts (`release_notes.py`, `completion_report.py`, `git_tags.py`, `value_hypothesis.py`, `tasks.py`) — defer resolver adoption to F010+.
- `.etc_sdlc/features/F001-F008` directories and contents — forward-only.
- The F006 placeholder — stays at legacy flat path.
- Any test file other than the new `tests/test_directory_lifecycle.py`.
- `install.sh` — no changes needed.

## Research Notes

**Codebase findings (Phase 2):**
- `scripts/feature_id.py::_FEATURE_DIR_PATTERN` at line 30 captures `^F(\d{3})(?:-.*)?$`. `_scan_max_feature_id` at line 120 uses single-directory `iterdir()` — F009 changes to rglob.
- `skills/spec/SKILL.md:522` writes `<feature_path>/rejected.md`. F009 adds `git mv` to `rejections/`.
- `skills/build/SKILL.md:714-737` is the Step 7.5 region. F009 inserts Step 7.5c after release-notes.md write.
- `skills/metrics/SKILL.md:104,137` hard-code `features/F<NNN>-<slug>/value-hypothesis.yaml`. F009 updates to use resolver.
- `compile-sdlc.py` produces byte-identical dist/ outputs from skills/ source. No per-target transforms.

**Best Practices (precedent):**
- `git mv` for canonical directory renames (preserves rename history).
- Two-state lifecycle (active + shipped) is industry-standard.
- F009's tests mirror F005/F008 pattern (pytest tmp_path + subprocess.run with cwd).

**Antipatterns:** No `.etc_sdlc/antipatterns.md` file exists; absence noted.
