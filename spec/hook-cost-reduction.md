# PRD: Hook Cost Reduction — Per-Subagent Marker Caching

## Summary

Two `PreToolUse Edit|Write` hooks — `check-required-reading.sh` and
`check-phase-gate.sh` — fire on every Edit/Write tool call, each running
its full verification logic even though the state they check rarely
changes within a single subagent session. On a parallel `/build` wave
with N subagents each doing ~10 edits, that's 20N repetitions of the
same check, contributing ~15-30 seconds of hook overhead per wave. The
latency is blocking v1.6 release readiness on parallel-wave feature
work.

This PRD adds **per-subagent marker-file caching** to both hooks:
after a successful check, the hook writes a marker file keyed by a
hash of the subagent's `transcript_path`. Subsequent Edits in the
same subagent session early-exit on the marker with a sub-millisecond
`test -f` check, skipping the full verification. The marker is
invalidated when the check's dependency file (task YAML for
`check-required-reading`, phase state file for `check-phase-gate`)
is newer than the marker — an `mtime` compare, not a cache-invalidation
rabbit hole.

**Semantics are preserved**. The hooks still verify exactly what they
verify today, at the same PreToolUse granularity. Nothing moves to
SubagentStart. Nothing becomes a "suggestion" instead of a check.
The only change is WHEN the verification runs: once per subagent
session instead of once per Edit.

## Scope

### In Scope

- Add cache-check logic to `hooks/check-required-reading.sh` at the
  top of the script, before the existing verification body.
- Add cache-check logic to `hooks/check-phase-gate.sh` at the top
  of the script, before the existing verification body.
- Add marker-file writes after successful verification in both
  hooks, so subsequent Edits can early-exit.
- Add an `.etc_sdlc/.hook-markers/` entry to `.gitignore` so the
  marker directory never lands in git.
- Add per-hook regression tests (marker-hit early-exit, marker-miss
  full-check, marker-invalidation on dependency file change).
- Document the caching pattern in `standards/process/` so future
  hook authors can adopt it.

### Out of Scope

- **No DSL changes.** `spec/etc_sdlc.yaml` is untouched. Both hooks
  stay on `PreToolUse` event with `matcher: "Edit|Write"`.
- **No semantic changes.** The hooks still verify exactly what they
  verify today. `check-required-reading` still blocks Edits if the
  agent hasn't read the required files. `check-phase-gate` still
  blocks file edits inappropriate for the current phase.
- **No changes to the other 3 PreToolUse Edit|Write hooks.**
  `check-tier-0.sh`, `check-test-exists.sh`, and `check-invariants.sh`
  are untouched. They may be optimized in a later release if profiling
  shows they matter.
- **No coalescing.** Option B from the hook-cost-reduction brief
  (consolidate 5 scripts into 1 wrapper) is NOT in scope here. It
  remains a v1.7 candidate.
- **No SubagentStart move.** Option A from the brief is explicitly
  rejected — the user ruled that `check-required-reading` must remain
  a verifier, not an injector, which forecloses the SubagentStart
  rewrite path.
- **No profiling instrumentation changes.** The `hook-timings.jsonl`
  observability spike from the brief remains a v1.7 candidate but is
  not required by this PRD.

## Requirements

### BR-001: Cache-hit early-exit in check-required-reading.sh

`check-required-reading.sh` MUST check for a marker file at
`.etc_sdlc/.hook-markers/{key}-required-reading` (where `{key}` is
`sha256(transcript_path)`) as the first action after reading stdin.
If the marker exists AND its mtime is newer than the newest task file
under `.etc_sdlc/tasks/*.yaml` and `.etc_sdlc/features/*/tasks/*.yaml`,
the hook MUST exit 0 immediately without running the verification
body.

### BR-002: Cache-miss full check in check-required-reading.sh

If no marker exists, or the marker is older than the newest task file,
`check-required-reading.sh` MUST run its existing verification logic
unchanged. On exit code 0 (check passed), the hook MUST create or
touch the marker file. On exit code 2 (check failed), the hook MUST
NOT create the marker — a failing check must not poison the cache.

### BR-003: Cache-hit early-exit in check-phase-gate.sh

`check-phase-gate.sh` MUST check for a marker file at
`.etc_sdlc/.hook-markers/{key}-phase-gate` as the first action after
reading stdin. If the marker exists AND its mtime is newer than
`.sdlc/state.json` (the phase state file this hook consults), the
hook MUST exit 0 immediately.

### BR-004: Cache-miss full check in check-phase-gate.sh

Same as BR-002 but for `check-phase-gate.sh` against its own marker.

### BR-005: Marker key derivation

The `{key}` used in marker paths MUST be
`sha256(transcript_path) | cut -c1-16` (the first 16 hex characters
of the SHA-256 of the transcript path from stdin). If
`transcript_path` is empty or missing, the hook MUST NOT cache — it
runs the full check and does NOT write a marker. The missing-key
case is a graceful degradation, not an error.

### BR-006: Marker directory creation

Both hooks MUST create `.etc_sdlc/.hook-markers/` on first use via
`mkdir -p`. The directory is gitignored so git never tracks it.

### BR-007: Gitignore entry

`.gitignore` MUST include `.etc_sdlc/.hook-markers/` (or a pattern
that matches it). The existing `.etc_sdlc/` ignore already handles
this if no exceptions intervene, but the PRD explicitly verifies
the entry to catch future regressions.

### BR-008: Failing checks do not poison the cache

If `check-required-reading.sh` exits with code 2 (block), the marker
file MUST NOT be created or touched. A failed check leaves the cache
empty so the next Edit re-runs the full check (potentially with the
agent having fixed the underlying issue, e.g., by reading the missing
file). Same for `check-phase-gate.sh`.

### BR-009: Dependency-file mtime invalidation

Both hooks MUST invalidate their marker when the dependency file is
newer than the marker. Check via `[ "$DEP_FILE" -nt "$MARKER" ]` in
bash. If the test is true, the hook falls through to the full-check
path and ignores the stale marker.

### BR-010: No changes to verification logic

The existing verification bodies of both hooks MUST be preserved
byte-for-byte except for the added cache-check prologue and
marker-write epilogue. Any change to the core verification must be
out of scope for this PRD.

### BR-011: Dependency files named explicitly

- `check-required-reading.sh` dependency files: all YAML files under
  `.etc_sdlc/tasks/` and `.etc_sdlc/features/*/tasks/` (newest mtime
  across all of them).
- `check-phase-gate.sh` dependency file: `.sdlc/state.json` in the
  project root, which is what the existing script consults (verify
  by reading the script before implementing).

## Acceptance Criteria

1. **Cache-hit early-exit skips verification.** A test that: (a)
   successfully runs `check-required-reading.sh` once against a
   fixture project with a passing task, (b) asserts a marker file
   exists at `.etc_sdlc/.hook-markers/{key}-required-reading`, (c)
   deletes the task's required reading (making the check fail if
   rerun), (d) runs the hook again with the same stdin, (e) asserts
   exit code 0 (the stale marker should cause early-exit even though
   the live check would now fail). This proves the cache is
   actually caching. [BR-001]

2. **Marker invalidation on dependency file change.** A test that:
   (a) writes a marker, (b) touches the task file to a newer mtime,
   (c) runs the hook, (d) asserts the hook runs the full check path
   (not the cache hit path). Verify via a side-effect: the full check
   path emits a specific stderr line that the cache-hit path does
   not. [BR-009]

3. **Failing check does not create marker.** A test that: (a) runs
   `check-required-reading.sh` on a fixture where the required reading
   has NOT been done, (b) asserts exit code 2 (block), (c) asserts
   the marker file does NOT exist afterward. [BR-008]

4. **Cache-hit early-exit for check-phase-gate.** Same as AC-1 but
   for `check-phase-gate.sh` and its marker. [BR-003]

5. **Marker invalidation when .sdlc/state.json changes.** Same as
   AC-2 but for the phase state file. [BR-009]

6. **Failing phase-gate check does not create marker.** Same as AC-3
   for `check-phase-gate.sh`. [BR-008]

7. **Missing transcript_path degrades gracefully.** A test that runs
   either hook with stdin that has no `transcript_path` field (or an
   empty string) and asserts: (a) the hook runs to completion, (b)
   it runs the full verification body, (c) no marker file is created,
   (d) exit code is the verification result, not an error. [BR-005]

8. **Gitignore entry for `.etc_sdlc/.hook-markers/`.** A test that
   creates a file at `.etc_sdlc/.hook-markers/test.txt` and asserts
   `git check-ignore` returns exit code 0 (ignored). [BR-007]

9. **Marker directory created on first use.** A test that deletes
   `.etc_sdlc/.hook-markers/` and runs the hook, asserting the
   directory is recreated. [BR-006]

10. **DSL is untouched.** A test that asserts `spec/etc_sdlc.yaml`
    still has `check-required-reading.sh` and `check-phase-gate.sh`
    registered under `PreToolUse` with `matcher: "Edit|Write"`, and
    that `dist/settings-hooks.json` reflects the same registration
    after recompile. [scope guarantee]

11. **No regression in verification semantics.** All existing tests
    in `tests/test_required_reading.py` and
    `tests/test_phase_gate.py` still pass without modification.
    The existing tests cover the verification body; they must remain
    green. [BR-010]

12. **Full test suite green.** `python3 -m pytest -q` reports at
    least 292 + (new tests from this PRD) passing. The new tests
    add at minimum 10 (two ACs per hook plus the graceful-degradation,
    gitignore, and directory-creation tests).

13. **Compile clean.** `python3 compile-sdlc.py spec/etc_sdlc.yaml`
    succeeds with unchanged counts: 14 gates, 10 hooks, 20 agents,
    10 skills, 32 standards.

## Edge Cases

1. **Two concurrent subagents with the same transcript_path.**
   Cannot happen — `transcript_path` is unique per Claude Code
   session and every subagent gets its own. The cache-key
   derivation is race-free by construction.

2. **Marker directory is a symlink to somewhere outside the
   repo.** A malicious user could symlink `.etc_sdlc/.hook-markers/`
   to `/tmp/` to read/write outside the project. The hook MUST use
   `mkdir -p` without following symlinks — bash `mkdir -p` does not
   follow symlinks for the deepest component by default, but verify
   by reading the mkdir implementation on the target platform.

3. **Clock skew between marker mtime and dependency file mtime.**
   If the system clock goes backwards (NTP adjustment, VM snapshot
   restore), a marker that was newer than the dep file can suddenly
   be older. The failure mode is a false-negative cache miss: the
   hook runs the full check unnecessarily. Not a correctness problem,
   just a performance degradation. Accept.

4. **Task file deletion mid-subagent.** If the task file is deleted
   after the marker is written, the `-nt` comparison treats a
   non-existent file as "older than anything," so the marker is
   considered valid. The hook early-exits, which is correct — a
   deleted task file means there's no active task to verify against,
   which is the same as the pre-caching behavior (the hook exits 0
   when it can't find an active task).

5. **Marker file race between cache-miss check and marker-write.**
   Two near-simultaneous Edits from the same subagent could both
   see the marker absent, both run the full check, both write the
   marker. Harmless — the marker file is idempotent (content-free,
   just existence matters), and both writers succeed.

6. **`.etc_sdlc/.hook-markers/` is in a read-only filesystem.**
   If the hook can't create the marker, it MUST NOT fail the
   verification. Log a warning to stderr, skip the cache write,
   and return the verification result. Graceful degradation.

7. **Marker directory grows unboundedly over time.** Every subagent
   session creates 1-2 marker files. Over weeks of use, that could
   be thousands of files. Mitigation: add a marker-cleanup step to
   `SubagentStop` or `SessionStart` that removes markers older than
   7 days. NOT in scope for this PRD — file as a follow-up in
   `docs/v1.6-roadmap.md` if it becomes a real problem.

8. **`transcript_path` contains characters that break shell
   quoting.** The path is passed through `sha256sum` as input, not
   executed as a command, so the shell-quoting attack surface is
   null. Input goes through `echo -n "$TRANSCRIPT" | sha256sum |
   cut -c1-16` — `echo -n` + stdin pipe handles arbitrary bytes.

9. **Coexistence with other PreToolUse hooks.** The other 3 hooks
   (`check-tier-0`, `check-test-exists`, `check-invariants`) do NOT
   get caching in this PRD. They continue to run full checks on
   every Edit. That's intentional — they're outside scope until
   profiling data confirms they need optimization.

## Technical Constraints

### Codebase patterns to follow

- **Hook script format**: both scripts are bash; match the existing
  shebang, error handling, and stdin parsing patterns from
  `hooks/check-required-reading.sh` and `hooks/check-phase-gate.sh`.
  No refactor of the verification body.
- **Test file pattern**: add tests to
  `tests/test_required_reading.py` and
  `tests/test_phase_gate.py` following the existing
  subprocess-invocation pattern. Reuse `conftest.py` fixtures
  (`tmp_project`, `run_hook`).
- **Standards doc**: if a new standards doc is warranted, put it
  at `standards/process/hook-caching.md` following the format
  of `standards/process/research-discipline.md` and
  `standards/git/commit-discipline.md`.

### Frameworks and libraries

- bash (existing).
- `sha256sum` on Linux, `shasum -a 256` on macOS. Use a shell
  function wrapper to pick the right binary at runtime (or use
  `openssl dgst -sha256` as a cross-platform fallback).
- No new Python dependencies.

### INVARIANTS.md and standards rules

- **TDD discipline**: tests MUST be written before the hook edits.
  Red (new tests fail) → Green (hooks updated to pass) → Refactor
  (clean up any awkwardness). The existing hook scripts were added
  without tests in some cases; follow the TDD loop for the new
  caching code specifically.
- **Layer boundaries**: hooks live in `hooks/`; they do not import
  from `platform/`, `scripts/`, or any consumer-project code. The
  marker directory lives under `.etc_sdlc/` which is the
  harness-scoped state area.
- **Domain fidelity**: use "marker", "cache hit", "cache miss",
  "invalidation", "dependency file" consistently. Avoid "memo",
  "stale", "dirty" — those are overloaded in the existing codebase.
- **Git commit discipline** (per `standards/git/commit-discipline.md`):
  if the build dispatches parallel subagents, each uses
  `git commit -m "..." -- <paths>`.
- **No re-introduction of prompt hooks on Stop**: the v1.5.2
  regression test still applies; this PRD does not touch Stop hooks.

### Compile / install / test invariants

- `compile-sdlc.py` succeeds unchanged (no DSL modifications).
- `./install.sh` succeeds unchanged — the new markers directory is
  created at runtime by the hooks themselves, not by install.
- Full test suite goes from 292 to at least 302 (baseline + 10
  new tests, 5 per hook).

## Security Considerations

### Path traversal via transcript_path

The `transcript_path` stdin field is under the control of Claude
Code, not the user. But defense in depth: the cache key is
`sha256(transcript_path) | cut -c1-16`, a 16-character hex string,
which cannot contain `..`, `/`, or shell metacharacters by
construction. The marker path is constructed as
`.etc_sdlc/.hook-markers/{16-hex-chars}-{hook-name}`, which is
guaranteed to be inside the markers directory. No realpath check
is needed because the key cannot represent a path-traversal
string.

### Symlink attacks on the marker directory

If an adversary with write access to `.etc_sdlc/` creates a symlink
at `.etc_sdlc/.hook-markers/` pointing to `/etc/`, the hook could
accidentally create files in `/etc/`. Mitigation: use
`test -L .etc_sdlc/.hook-markers/` before every write, and abort
with a stderr warning if the directory is a symlink. The hook
still proceeds with the full verification; caching is skipped.

### Cache poisoning via marker pre-creation

If an adversary with write access to `.etc_sdlc/.hook-markers/`
pre-creates a marker with a future mtime, the hook's cache-hit
branch will skip the verification and allow an Edit that should
have been blocked. This is a real concern for multi-user
environments but not for single-operator etc usage. Mitigation:
none in this PRD — the `.etc_sdlc/` directory is under the
operator's own control. If this becomes a concern, a future PRD
can sign markers with HMAC of a session-scoped secret. Document
the assumption in `standards/process/hook-caching.md`.

### Filesystem races on marker check/write

Covered in Edge Case 5 — markers are content-free existence flags
and two concurrent writers are harmless. No atomic mkdir or
rename dance needed.

### Stale marker causing missed violation

If a task file changes but its mtime is somehow older than the
marker (e.g., the file was edited and then touched to an old
mtime), the hook would serve a stale cache-hit and allow an Edit
that should have been blocked. Mitigation: the `-nt` comparison
is the standard bash idiom; files are almost never touched to
older mtimes in practice. Accept the risk; document in the
standards doc.

## Module Structure

### Files created

- `standards/process/hook-caching.md` — the caching pattern doc.
  Explains the marker-file pattern, the invalidation contract
  (dependency-file mtime), the graceful-degradation requirements
  (missing transcript_path, read-only filesystem), and references
  this PRD as the origin. Modeled after
  `standards/process/research-discipline.md`.

### Files modified

- `hooks/check-required-reading.sh` — add cache-check prologue and
  marker-write epilogue around the existing verification body. No
  changes to the verification logic itself.
- `hooks/check-phase-gate.sh` — same.
- `tests/test_required_reading.py` — add cache-hit,
  cache-miss, marker-invalidation, graceful-degradation tests.
- `tests/test_phase_gate.py` — same.
- `.gitignore` — explicitly add `.etc_sdlc/.hook-markers/` as an
  entry (if the existing `.etc_sdlc/` entry does not already
  cover it via the existing ignore structure). Verify by
  `git check-ignore` test.

### Files explicitly NOT modified

- `spec/etc_sdlc.yaml` — no DSL changes.
- `hooks/check-tier-0.sh`, `hooks/check-test-exists.sh`,
  `hooks/check-invariants.sh` — out of scope; caching NOT added
  to these.
- Any other hook, skill, agent, or standards doc.

### Compiled artifacts

None new. `compile-sdlc.py` produces an unchanged `dist/`.

### Post-compile count delta

| | Before | After | Delta |
|---|---|---|---|
| Gates | 14 | 14 | 0 |
| Hooks | 10 | 10 | 0 |
| Skills | 10 | 10 | 0 |
| Agents | 20 | 20 | 0 |
| Standards docs | 32 | 33 | +1 (hook-caching.md) |
| Tests passing | 292 | 302+ | +10 minimum |

## Research Notes

### Prior session findings

- `spec/hook-cost-reduction-brief.md` — the brief that analyzed
  three optimization options (coalesce, rewrite, cache) and
  recommended profiling first. This PRD promotes the brief's
  Option C from "candidate pending profiling" to "approved path"
  based on the explicit user decision to preserve verification
  semantics (ruling out Option A) and the urgency to ship
  (ruling out profiling-first).

- `.etc_sdlc/incidents/2026-04-15-pretooluse-edit-write-hooks-check-required-reading/incident.md` —
  the first live /hotfix invocation, where the `hotfix-responder`
  correctly rejected a "move to SubagentStart" proposal because
  it would have silently disabled both gates. The rejection
  analysis is preserved in the incident file and feeds this PRD's
  "no SubagentStart move" constraint.

- **User decision**: "We need verification not suggestion."
  (2026-04-15 conversation). Forecloses Option A entirely. Locked
  in scope via the Out of Scope section.

- **User decision**: "Don't know" on the phase-gate semantic
  question. Interpreted as "don't change phase-gate semantics."
  Forecloses the subagent-level phase check in favor of preserving
  the existing per-Edit phase check, which remains file-level.

### Codebase findings

- `hooks/check-required-reading.sh` line 19 already reads
  `TRANSCRIPT=$(echo "$INPUT" | jq -r '.transcript_path // empty')`.
  The cache key derivation slots in naturally at the top of the
  script, right after the existing stdin parse.
- `hooks/check-phase-gate.sh` lines 17-18 read `FILE_PATH` and
  `CWD` from stdin. It needs a new line to read `TRANSCRIPT`
  (copy the pattern from check-required-reading.sh).
- Both scripts have clean early-exit branches that handle the
  "nothing to check" case. The cache-hit branch slots in right
  before those early-exits.

### Why not profiling first

The hook-cost-reduction brief's Option 0 was "instrument first, then
decide." That's the conservative path and it's still correct in
general — but the user has explicitly stated (a) the latency is
blocking v1.6 release readiness, and (b) the fix direction is
already agreed (caching, not coalescing, not moving). Profiling
would tell us WHICH hook is slower; this PRD fixes BOTH anyway.
The profiling spike is still worth doing for v1.7 to identify the
OTHER slow paths (e.g., adversarial-review at SubagentStop, which
the brief flags as a bigger possible culprit) but it is not a
prerequisite for this PRD's scope.
