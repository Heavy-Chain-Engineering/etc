# PRD: /janitor — Autonomous Harness Cleanup

## Summary

**/janitor** is an autonomous harness-cleanup skill that applies the Boy Scout
rule ("leave the campsite better than you found it") and broken-windows theory
to the etc codebase. It is the *find-fix-and-ship* counterpart to F019's Chief
Efficiency Officer (which only *observes and proposes*): janitor surveys the
repository, selects a small batch of fixes it can perform flawlessly without
supervision, performs them in a fully isolated git worktree, and opens a pull
request — never touching the operator's active working tree or build.

It runs in two ways. **Interactively** (`/janitor`), the operator triggers a
survey-then-fix pass. **Unattended** (`/janitor --autonomous`, wired to whatever
scheduler the operator chooses), it does the same work without prompts. Either
way the output is always a pull request, preserving etc's standing discipline:
the agent submits, a human merges.

The value is *autonomous background improvement the operator can trust like
Dependabot*: point a scheduler at it, and wake up to a tight, reviewable PR you
merge with confidence. Two safety mechanisms make that trust earned rather than
hoped-for: (1) **physical worktree isolation** — janitor operates on a fresh
branch off `main` in a throwaway worktree, so even a janitor bug cannot corrupt
in-flight work; and (2) **a mechanical pre-PR boundary check** — a diff scan
aborts the run before any PR is opened if it touches a forbidden path or exceeds
the file-count ceiling. Trust is per-category and graduated: every fix-category
starts in **preview** (draft PR) and auto-promotes to **autonomous**
(ready-for-review PR) only after N consecutive clean merges. v1 ships the
minimal safe category set; richer categories follow once the rail is proven.

This is infrastructure work (`infrastructure_only: true`): harness internals
that directly improve operator UX (less manual litter-picking; autonomous
background PRs) and indirectly compound into better customer UX over time. No
direct customer-journey trace.

## Scope

### In Scope
- A `/janitor` skill with interactive (`/janitor`) and non-interactive
  (`/janitor --autonomous`) modes.
- A read-only survey/discovery pass that assembles a candidate fix list and
  selects a bounded batch (target ~2 fixes) of flawless-only work.
- Isolated execution in a throwaway git worktree on a fresh branch cut from
  `main`.
- Three v1 fix categories: (a) lint/format auto-fix where a config exists;
  (b) dead-code removal proven unreached by the existing test suite;
  (c) whitespace / EOF-newline / import-order normalization.
- A mechanical pre-PR boundary check (`janitor_boundary_check.py`).
- Pull-request output: preview → draft PR; autonomous → ready-for-review PR;
  always targets `main`.
- Per-category graduated trust in `.etc_sdlc/janitor/trust.yaml`.
- An operator command surface for inspecting/overriding trust state.
- Net-positive verification: harness gates (tests/lint/types) green in the
  worktree before any PR.
- `standards/process/janitor-write-boundary.md` as the single source of truth
  for forbidden paths + file-count ceiling.

### Out of Scope
- A built-in scheduler (operator wires cron/launchd/CI themselves in v1).
- Cloud execution / Claude Code routines (declared orthogonal; janitor is
  custom).
- Deferred fix categories (doc reorganization, screenshot cleanup, single-file
  refactors) — v2.
- Any write outside the boundary (see BR-006).
- Merging (janitor submits; a human merges; never pushes `origin/main`; never
  self-merges).
- `dangerouslyDisableSandbox` — never, any mode.
- Chat-history mining as a hard requirement (best-effort where local signal
  exists; not a v1 dependency).

## Requirements

### BR-001: Dual invocation
`/janitor` runs interactively; `/janitor --autonomous` runs the identical
pipeline non-interactively (no prompts), suitable for an operator-supplied
scheduler. No built-in scheduler ships in v1.

### BR-002: Mandatory worktree isolation
All janitor edits MUST occur in a throwaway git worktree on a fresh branch cut
from `main` (e.g. `claude/janitor/<category>-<date>`). Janitor MUST NOT edit,
stage, or commit anything in the operator's primary working tree. The worktree
is removed after the PR is opened (or on abort). Hard safety invariant: a
janitor failure cannot corrupt in-flight work.

### BR-003: Survey-then-select
Each run begins with a read-only survey assembling a candidate fix list, then
selects a bounded batch (default target ~2 fixes) limited to categories janitor
can perform flawlessly. The survey reads broadly (repo, and local
roadmap/session signal where available); it writes nothing outside the
worktree.

### BR-004: v1 fix categories
v1 performs exactly three categories: (a) lint/format auto-fix where a config
already exists; (b) dead-code removal where the existing test suite proves the
code unreached; (c) whitespace / EOF-newline / import-order normalization. Any
candidate outside these is not actioned in v1.

### BR-005: Mechanical pre-PR boundary check
Before any PR is opened, `janitor_boundary_check.py` scans the worktree branch
diff against the forbidden-path list (BR-006) and the file-count ceiling. On
any violation it aborts the run, opens no PR, and reports which rule fired. The
check is independent of the prompt (defense-in-depth) and runs identically in
both modes.

### BR-006: Write boundary
Janitor's write set excludes, at minimum: intent files (`spec/`,
`.etc_sdlc/features/**/spec.md` & `design.md`, `docs/adrs/`, `INVARIANTS.md`,
`DOMAIN.md`, `PRODUCT.md`, `RELEASES.md`); active surfaces (files in an open PR,
active feature dirs, files committed in the last 24 h); behavior-changing
logic; schemas, migrations, lockfiles, dependency lists; secrets, CI workflows,
`hooks/`, `spec/etc_sdlc.yaml`, the installer, the compiler; untested files;
public-facing copy; and any change spanning > 3 files or 2+ bounded contexts.
The authoritative list lives in `standards/process/janitor-write-boundary.md`
(BR-013).

### BR-007: Pull-request output and merge discipline
Output is always a PR targeting `main`. Preview-mode categories open a **draft**
PR; autonomous-mode categories open a **ready-for-review** PR. Janitor never
pushes to `origin/main` and never merges its own PR.

### BR-008: Per-category graduated trust
Trust is tracked per fix-category in `.etc_sdlc/janitor/trust.yaml`. Every
category starts in `preview`. A category auto-promotes to `autonomous` after N
consecutive janitor PRs in that category merge with zero operator edits (N
tunable, default decided in /architect). A janitor PR that is closed-unmerged
or merged-with-edits resets that category's clean-streak counter.

### BR-009: Net-positive verification
Before opening a PR, the harness verification gates (tests, lint, type-check as
applicable to touched files) MUST pass green in the worktree. A red gate aborts
the run with no PR.

### BR-010: Safety prohibitions
Janitor MUST NOT invoke `dangerouslyDisableSandbox`, MUST NOT push to
`origin/main`, MUST NOT bypass git hooks (`--no-verify`), and MUST NOT mark its
own PR merged — in any mode.

### BR-011: State storage
All janitor runtime state (`trust.yaml`, run ledger, already-proposed/fixed
records) lives under `.etc_sdlc/janitor/` (gitignored, operator-local).

### BR-012: Operator trust-command surface
The operator can inspect and override trust state — at minimum view current
per-category trust levels and clean-streak counts, and manually demote a
category back to `preview`.

### BR-013: Write-boundary standard
`standards/process/janitor-write-boundary.md` is the single source of truth for
forbidden paths + the file-count ceiling, referenced by both the janitor prompt
and `janitor_boundary_check.py`.

## Acceptance Criteria

All criteria are backend-only (infrastructure feature, no customer-journey
surface); no User-flow sentences required.

1. **AC-001** — Both `/janitor` and `/janitor --autonomous` run the full
   survey → fix → boundary-check → PR pipeline; the sole difference is that
   autonomous mode issues no operator prompts. Each invocation terminates in
   either an opened PR or a clean "nothing to clean" exit (code 0).
2. **AC-002** — After any janitor run, the operator's primary working tree is
   unchanged: `git status --porcelain` in the primary checkout is byte-identical
   before and after. All edits are confined to a worktree outside the primary
   tree.
3. **AC-003** — The janitor branch's merge-base with `main` equals `main`'s HEAD
   at run start (proves "branched off main").
4. **AC-004** — A run that would touch a forbidden path causes
   `janitor_boundary_check.py` to exit non-zero, open no PR, and report the
   violated rule by name.
5. **AC-005** — A run whose worktree diff exceeds the file-count ceiling
   (> 3 files) aborts with no PR.
6. **AC-006** — A run whose worktree verification gates come back red aborts
   with no PR (BR-009).
7. **AC-007** — A category in `preview` trust opens a draft PR; a category in
   `autonomous` trust opens a ready-for-review PR.
8. **AC-008** — A category's `trust.yaml` entry auto-promotes
   `preview → autonomous` after N consecutive clean merges; a closed-unmerged or
   merged-with-edits PR resets that category's clean-streak counter to 0.
9. **AC-009** — v1 actions only the three categories. A candidate outside them
   appears in the run report but is not actioned.
10. **AC-010** — Janitor never pushes to `origin/main`, never runs
    `--no-verify`, and never sets `dangerouslyDisableSandbox` — verifiable by
    static scan of the skill + scripts and enforced by the boundary check.
11. **AC-011** — Every janitor state write lands under `.etc_sdlc/janitor/`; no
    janitor state is written elsewhere.
12. **AC-012** — An operator trust command prints per-category trust level +
    clean-streak count, and a demote command returns a named category to
    `preview` in `trust.yaml`.
13. **AC-013** — `standards/process/janitor-write-boundary.md` exists and is the
    single file from which both the janitor prompt and
    `janitor_boundary_check.py` source the forbidden-path list (no duplicated
    hardcoded list).
14. **AC-014** — The opened PR body names the fix category/categories and
    records the (clean) boundary-check result.

## Edge Cases

1. Nothing to clean → exit 0, "nothing to clean" report, no PR, no leftover
   branch/worktree.
2. Dirty primary working tree → irrelevant by construction (branch cut from
   `main` into a separate worktree); AC-002 holds.
3. `main` dirty / no commits / absent → abort with a clear message; no silent
   fallback to the current branch.
4. Worktree creation fails (collision, disk, git error) → abort, no PR, no
   partial state; partial worktree cleaned up.
5. Boundary check and prompt disagree → the scan wins; run aborts, no PR.
6. A category's only candidate is also an in-flight file → skipped
   (active-surface rule), reported as skipped.
7. Verification gates flaky/slow → red or timed-out gate aborts with no PR
   (fail-closed).
8. Lint/format config absent for category (a) → no-op for the run; janitor does
   not introduce a new config (out-of-scope behavior change).
9. Dead-code candidate has no covering test → not removed (untested-file rule +
   category-(b) "test-proven unreached" requirement).
10. Concurrent janitor runs → uniquely-named worktree/branch per run; a
    `.etc_sdlc/janitor/` lock makes the second run defer rather than race.
11. Trust file missing or malformed → treat every category as `preview` (safe
    default); never silently assume `autonomous`.
12. PR open fails (network, auth, gh CLI missing) → abort, error surfaced,
    worktree cleaned up, trust state untouched (no clean-streak credit).
13. Runaway / stuck-loop → bounded by a per-run turn/time ceiling; on exhaustion
    abort with no PR (ties to F019; budget set in /architect).
14. Operator demotes a category mid-streak → effective next run; an already-open
    autonomous PR is unaffected.

## Technical Constraints
*(Intent-level; /architect owns the detailed design.)*
- Closest existing pattern: F019 Chief Efficiency Officer (`skills/efficiency/`)
  — proposal-queue + accept/dismiss UX is a reuse template for preview mode.
- Worktree isolation builds on F016 (mergiraf + worktree-conflict-prevention).
- `janitor_boundary_check.py` reuses the spec-enforcer diff/scan pattern and the
  `check-*.sh` path-scoping precedent.
- Runs under all existing harness gates (TDD-gate, INVARIANTS, code-quality,
  sandbox discipline) — no carve-outs.
- Reusable scripts: `git_tags.py`, `feature_id.py`, `telemetry.py` (cost),
  `sdlc_timing.py` (baseline).

## Security Considerations
*(Auto-populated for a file-handling + autonomous-execution feature; refine in
/architect.)*
- Path-traversal: the boundary check must canonicalize paths before matching the
  forbidden list (no `..` escape).
- Command injection: all git/gh invocations use argv lists, never shell strings
  with interpolated branch/category names.
- Sandbox: never `dangerouslyDisableSandbox` (BR-010).
- Least privilege: janitor never pushes `origin/main`, never self-merges.
- Fail-closed: every ambiguous or error state aborts with no PR rather than
  proceeding.

## Module Structure
*(Intent-level; /architect finalizes.)*
- `skills/janitor/SKILL.md` — the skill (interactive + `--autonomous`).
- `scripts/janitor_boundary_check.py` — mechanical pre-PR diff scan.
- `standards/process/janitor-write-boundary.md` — forbidden-path + ceiling SoT.
- `.etc_sdlc/janitor/trust.yaml` + run ledger — operator-local state (created at
  runtime; gitignored).
- `agents/janitor.md` — agent manifest if /architect decides janitor dispatches
  a subagent for the fix work.

## Research Notes
- **F019 cousin:** observe-and-propose (CEO) vs find-fix-and-PR (janitor); the
  evidence-cited discipline and accept/dismiss UX transfer.
- **Dependabot/Renovate prior art:** merge-confidence scoring → per-category
  trust graduation; scoped/grouped PRs → ≤3-file per-category PRs; auto-merge as
  a configurable threshold → preview/autonomous dial (not a global switch).
- **Internal antipattern memory:** 25–27% agentic-PR merge-conflict rate
  motivates worktree isolation + active-surface avoidance; F019 stuck-loop
  motivates the per-run ceiling; sandbox-bypass discipline → BR-010.
- No `INVARIANTS.md` / `.etc_sdlc/antipatterns.md` in this repo (recorded).
