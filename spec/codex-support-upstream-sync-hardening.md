# PRD: Upstream-Safe Codex Support Integration

**Status:** spec
**Date:** 2026-05-23
**Delivery target:** PR into the shared ETC repository
**Parent baseline:** current `origin/main`, synced from
`Heavy-Chain-Engineering/etc-internal`
**Release bar:** Codex support survives routine parent syncs with low conflict
cost

## Problem

`feature/codex-support` adds a Codex compiler target, project-local installer
support, runtime checks, hook adapters, docs, tests, and dogfood evidence. The
implementation works functionally, but it was built on an older local `main`
while the parent repo continued to move.

The fork regularly syncs updates from the parent repo. If Codex support remains
only in this fork, the implementation must avoid long-lived edits in files the
parent changes frequently. The current shape has three conflict-prone areas:

- `install.sh`: parent `origin/main` rewrote this into a small Bash bootstrap
  that delegates to `etc_installer`; Codex support currently adds substantial
  Bash install logic to the old installer shape.
- `compile-sdlc.py`: Codex support adds a large target to the monolithic
  compiler, which is likely to conflict with future parent compiler updates.
- Shared hook scripts: Codex support updates the same hook scripts that parent
  features continue to edit.

The goal is not merely to resolve today's merge. The goal is to reshape Codex
support so future upstream syncs are boring.

## Solution

Rebase Codex support onto current `origin/main` and move integration points to
the parent repo's current extension surfaces.

The hardened implementation should:

- Preserve the parent `install.sh` bootstrap model.
- Add Codex install support inside `etc_installer`, not as a large Bash branch
  in `install.sh`.
- Keep `compile-sdlc.py` as the public compiler entry point, but isolate Codex
  target generation behind small Codex-specific helpers or modules where
  practical.
- Keep Codex runtime, docs, tests, and dogfood evidence in Codex-specific files
  whenever possible.
- Avoid committing generated `dist/` artifacts or unrelated dependency lock
  churn.
- Prove that Codex support can be rebased onto the current parent baseline
  without unresolved conflicts and with the full test suite passing.

## Scope

### In Scope

- Rebase or replay Codex support onto current `origin/main`.
- Port `--client codex` and `--scope project` install behavior into
  `etc_installer`.
- Preserve `install.sh` as a bootstrap that delegates to `etc_installer`.
- Update installer tests to cover Codex through the Python installer path.
- Keep project-local Codex install behavior:
  - `AGENTS.md` managed block when a project already has instructions.
  - `.codex/hooks.json`
  - `.codex/hooks/`
  - `.codex/agents/`
  - `.codex/scripts/`
  - `.codex/schemas/`
  - `.codex/expected/`
  - `.codex/source/`
  - `.agents/skills/` merge without deleting project-owned skills.
  - `gate-classification.json`
- Preserve Codex `doctor` and `ci-check` behavior.
- Keep synthetic and real-repo dogfood evidence current.
- Add merge/sync validation notes to Codex operator docs.
- Remove accidental `uv.lock` changes unless a deliberate dependency change is
  required and documented.

### Out of Scope

- Upstreaming Codex support to `Heavy-Chain-Engineering/etc-internal`.
- Changing the parent sync process itself.
- Supporting user/global Codex install.
- Rewriting all compiler behavior into a new package in this PR.
- Making plugin packaging the authoritative install path.
- Removing Claude or Antigravity install support.

## Requirements

### BR-001: Rebase Onto Current Parent Baseline

Codex support must be replayed onto current `origin/main`, not merged from the
old local `main` state.

The final branch must show `origin/main` as its merge base or must have a
documented reason if a newer parent sync is intentionally deferred.

### BR-002: Preserve `install.sh` Bootstrap Ownership

`install.sh` must remain a thin bootstrap that resolves `uv` and delegates to
`etc_installer`.

Codex-specific install behavior must not be implemented as a large Bash branch
inside `install.sh`.

### BR-003: Add Codex To `etc_installer`

`etc_installer` must understand Codex as a supported client in the same
operator-facing path as existing clients.

Required behavior:

- CLI accepts `--client codex`.
- CLI accepts `--scope project` for Codex.
- CLI rejects Codex user/global scope with a clear error before writes.
- Dry-run reports project-local Codex write targets.
- Install writes only to the selected project target.
- Re-running install is idempotent.

### BR-004: Preserve Project-Owned Codex Surfaces

The Codex installer must not erase project-owned instructions or skills.

Required behavior:

- If `AGENTS.md` does not exist, install the generated Codex instructions.
- If `AGENTS.md` exists, append or refresh an `ETC_CODEX` managed block.
- Re-running install must update only the managed block.
- `.agents/skills` install must merge ETC skills without deleting
  project-owned skill directories.

### BR-005: Keep Compiler Changes Narrow

`compile-sdlc.py` may remain the command entry point, but Codex generation must
be structured to minimize future conflicts.

At minimum:

- Codex constants and helper functions are grouped.
- Existing Claude compile behavior is unchanged.
- `--client claude`, `--client codex`, and `--client all` are covered by tests.
- No hand-maintained Codex generated artifacts are committed.

If practical within this PR, Codex generation should move into a dedicated
module imported by `compile-sdlc.py`.

### BR-006: Keep Hook Changes Backward-Compatible

Shared hook scripts must continue to accept legacy Claude payloads while also
accepting Codex command-hook payloads through a normalized adapter.

Required behavior:

- Existing Claude hook tests still pass.
- Codex `apply_patch` payload tests pass.
- Multi-file, create, delete, and move-like patch cases are covered.
- Hook helper files are copied into both Claude and Codex install surfaces as
  needed.

### BR-007: Avoid Lockfile And Generated-Artifact Churn

The PR must not include unrelated `uv.lock` changes, compiled `dist/` output,
temporary dogfood clones, caches, or runtime-generated files.

Any lockfile change must name the dependency reason in the PR description.

### BR-008: Prove Current Merge Cleanliness

Before the PR is considered ready, the branch must be tested against current
`origin/main`.

Required evidence:

- A non-destructive merge/rebase check against `origin/main` shows no
  unresolved conflicts.
- The final branch has no conflict markers.
- The full test suite passes after the rebase.

### BR-009: Preserve Dogfood Findings

Dogfood evidence from Codex support must remain documented, including the
issues found during real-repo temp-clone installs:

- Existing `AGENTS.md` and project skills must be preserved.
- Installed `doctor` must not require target-repo PyYAML or other source
  compiler dependencies.

## Acceptance Criteria

1. `git merge-base HEAD origin/main` equals current `origin/main`, or the PR
   description explicitly names the accepted lag.
2. `install.sh --help` still shows the parent bootstrap help surface and does
   not contain the old large Bash Codex install branch.
3. `etc_installer` accepts `--client codex --scope project`.
4. `etc_installer` rejects `--client codex --scope user` before writing files.
5. Codex dry-run lists the project-local targets, including `.codex/expected`
   and `.codex/source`.
6. Codex install writes project-local Codex artifacts into a clean target.
7. Codex install preserves existing `AGENTS.md` content and adds exactly one
   managed `ETC_CODEX` block.
8. Re-running Codex install refreshes the managed block without duplicating it.
9. Codex install preserves a pre-existing project-owned skill such as
   `.agents/skills/project-skill/SKILL.md`.
10. `python3 compile-sdlc.py spec/etc_sdlc.yaml --client claude` preserves
    current Claude output behavior.
11. `python3 compile-sdlc.py spec/etc_sdlc.yaml --client codex` emits Codex
    output.
12. `python3 compile-sdlc.py spec/etc_sdlc.yaml --client all` emits both Claude
    and Codex output.
13. `etc-runtime doctor --client codex` passes in a freshly installed fixture.
14. `etc-runtime ci-check --client codex` passes in a valid installed fixture.
15. `etc-runtime ci-check --client codex` detects generated-output drift.
16. Codex hook payload tests cover `apply_patch` multi-file edits.
17. Existing Claude hook tests pass.
18. Existing `etc_installer` tests pass.
19. New Codex installer tests pass through `etc_installer`, not only through a
    copied Bash installer fixture.
20. `git diff --check` passes.
21. Full test suite passes.
22. `uv.lock` is unchanged unless the PR documents a required dependency
    change.
23. No generated `dist/` artifacts are committed.
24. Codex operator docs describe the parent-sync/rebase expectation.
25. The PR description includes current merge-cleanliness evidence against
    `origin/main`.

## PR Definition of Done

The PR is done when all of the following are true:

1. Codex support is rebased onto current `origin/main`.
2. `install.sh` remains the parent bootstrap and does not own Codex install
   logic directly.
3. Codex install behavior lives in `etc_installer` with tests.
4. The Codex compiler target still works from `compile-sdlc.py`.
5. Existing Claude and Antigravity installer behavior still works.
6. Existing Claude hook behavior still works.
7. Codex hook payload normalization still works.
8. Existing project `AGENTS.md` and `.agents/skills` content are preserved by
   Codex install.
9. User/global Codex install fails clearly and writes nothing.
10. Docs explain the supported project-local install mode and parent-sync
    implications.
11. The PR contains no unrelated lockfile, generated artifact, cache, or
    dogfood clone changes.
12. `git diff --check` passes.
13. Shell syntax checks pass for touched shell scripts.
14. Python syntax checks pass for touched Python files.
15. Focused Codex tests pass.
16. Existing installer tests pass.
17. Full test suite passes.
18. A non-destructive merge/rebase check against `origin/main` has no
    unresolved conflicts.

## Release Definition of Done

The release is done when all PR DoD items are true and:

1. The branch is merge-ready into the shared ETC repository.
2. The fork can sync current parent `origin/main` with Codex support present
   without manual conflict resolution.
3. Two real-repo temp-clone dogfood installs pass after the rebase.
4. Synthetic installed Codex dogfood still passes.
5. Dogfood evidence includes install, blocked gate, successful edit gate,
   `doctor`, and `ci-check`.
6. No accepted known gap increases future parent-sync conflict risk.
7. A maintainer can repeat the sync validation from documented commands.

## Test Plan

Run after rebasing onto current `origin/main`:

```bash
git diff --check
python3 -m py_compile compile-sdlc.py scripts/etc_runtime.py hooks/helpers/hook_payload.py hooks/helpers/required_reading.py
bash -n install.sh hooks/*.sh scripts/etc-runtime
```

Run focused tests:

```bash
python3 -m pytest \
  tests/test_etc_installer_cli.py \
  tests/test_etc_installer_install_steps.py \
  tests/test_etc_installer_paths.py \
  tests/test_codex_installer.py \
  tests/test_codex_compiler.py \
  tests/test_codex_ci_check.py \
  tests/test_codex_dogfood.py \
  tests/test_codex_hook_payloads.py \
  tests/test_codex_hooks.py \
  tests/test_runtime_compat.py \
  -q
```

Run the full suite:

```bash
python3 -m pytest -q
```

Run a non-destructive merge check against current parent baseline:

```bash
git fetch origin
git merge-tree "$(git merge-base HEAD origin/main)" origin/main HEAD
```

The output must contain no `<<<<<<<`, `=======`, or `>>>>>>>` conflict markers.

## Implementation Notes

- The current parent `origin/main` contains `etc_installer/` and a bootstrap
  `install.sh`. Treat that as the installer architecture of record.
- The old Bash Codex install implementation is useful as behavior reference,
  not as the final integration location.
- The existing Codex dogfood found two real issues; keep those regression tests
  even if the installer is moved into Python.
- Keep README edits minimal. Prefer `docs/guides/codex-harness.md` for operator
  detail to reduce recurring conflicts.
- If Codex compiler extraction into a module is too large for this PR, keep it
  grouped in `compile-sdlc.py` and record a follow-up.

## Open Questions

1. Should Codex support remain fork-local long term, or should it be proposed
   upstream once project-local install is stable?
2. Should the parent sync workflow get a dedicated CI job that runs the
   non-destructive merge check before every fork sync PR?
3. Should Codex generation be extracted from `compile-sdlc.py` in this PR, or
   deferred until after installer rebasing is complete?
