---
name: janitor
description: >
  Autonomous harness-cleanup orchestrator (Boy Scout rule + broken-windows).
  Surveys the repo, selects flawless-only cleanup, performs it in an ISOLATED git
  worktree cut from main, verifies the harness gates green, runs a mechanical
  pre-PR boundary check, and opens a pull request — never touching the operator's
  working tree or build. Two modes: interactive `/janitor` and hands-off
  `/janitor --autonomous` (ZERO prompts, for an operator-supplied scheduler).
  Janitor submits; a human merges. It never pushes origin/main, never self-merges,
  never bypasses git hooks (`--no-verify`), and never sets dangerouslyDisableSandbox.
---

# /janitor — Autonomous Harness Cleanup

`/janitor` is the *find-fix-and-ship* counterpart to F019's Chief Efficiency
Officer (which only observes and proposes). Each run surveys the repository,
selects a tiny batch of fixes it can perform flawlessly without supervision,
performs them in a throwaway git worktree on a fresh branch cut from `main`,
and opens a pull request. The defining invariant is **physical isolation**:
every edit lands in a worktree off `main`, so even a janitor bug structurally
cannot reach the operator's in-flight work (ADR-001).

Two safety rails make the trust earned, not hoped-for:

1. **Worktree isolation** — janitor writes only inside a throwaway worktree on a
   branch off `main`; the operator's primary tree is never read for mutation and
   never written (BR-002, AC-002/AC-003).
2. **Mechanical pre-PR boundary check** — `scripts/janitor_boundary_check.py`
   scans the diff and aborts the run before any PR if it touches a forbidden path
   or exceeds the file-count ceiling (BR-005, AC-004/AC-005). The scan is the
   rail; the prompt is advisory; on disagreement the scan wins.

Trust is per-category and graduated: every category starts in **preview** (draft
PR) and auto-promotes to **autonomous** (ready-for-review PR) after N=5
consecutive clean merges (ADR-003/ADR-005). Trust is read via
`scripts/janitor_trust.py`, the sole writer of `trust.yaml`.

## Usage

```
/janitor                          -- interactive survey-then-fix pass (may prompt)
/janitor --autonomous             -- hands-off; ZERO prompts; for a scheduler
/janitor --base <ref>             -- branch base (default: main)
/janitor trust                    -- print the per-category trust table
/janitor trust demote <category>  -- return a category to preview (streak → 0)
```

`--autonomous` runs the **identical pipeline** as `/janitor`; the sole
difference is that it issues **no operator prompts** — it chooses the safe
default or aborts (never blocks on input). No built-in scheduler ships in v1
(operator wires cron/launchd/CI themselves, e.g. `claude -p "/janitor --autonomous"`).

## Response Format (Verbosity)

Terse and structured. Use tables for the candidate/trust data, fenced code
blocks for the "Janitorial Services" report and any git/gh command, numbered
lists for ordered procedures. No preamble ("I'll...", "Here is..."), no
narrative summary, no emoji. Render file/PR-body contents as fenced blocks; do
not re-describe them in prose. In `--autonomous` mode, all output is a single
final report (no interim status the operator would not see).

## Subagent Dispatch

`/janitor` is an **orchestrator**. It performs the survey/select/isolate/
verify/boundary-check/deliver/record/teardown steps in its own context, but it
**MUST dispatch the actual fix work** to the constrained `janitor` fix-subagent
(`agents/janitor.md`) via the `Task` tool — one dispatch per selected fix, **one
category at a time**, scoped to the worktree.

The fix-subagent's toolset IS the security boundary: it has no authority to run
`gh`, `git push`, open/merge a PR, or reach the network (privilege separation —
design.md "Security Considerations"). The orchestrator is the only component
that crosses the trust boundary, and its single crossing is `gh` on the
operator's existing auth.

You MUST NOT perform the fix edits yourself in the orchestrator context, and you
MUST NOT grant the subagent delivery authority. Each `Task` dispatch passes the
subagent: the **worktree** path, exactly **one** `category`, the target
`files`, and the **boundary** standard path. The subagent returns a structured
result (`{category, worktree, files_touched, tool_invoked, success, reason}`)
that the orchestrator then verifies and boundary-checks before any delivery.

## Before Starting (Non-Negotiable)

Read these sources in order before any Step 1 action, using the named tool on
each exact path:

1. `standards/process/janitor-write-boundary.md` via Read — the single source of
   truth for forbidden paths + the ≤3-file ceiling (AC-013). Both this skill and
   `janitor_boundary_check.py` source the list from here; never hardcode a copy.
2. `agents/janitor.md` via Read — the fix-subagent's I/O contract and the
   toolset security boundary you dispatch into.
3. `.etc_sdlc/janitor/trust.yaml` via Read, if it exists — the per-category trust
   cache. Missing or malformed → treat every category as `preview` (edge 11);
   never silently assume `autonomous`.
4. The interactive-input rules `standards/process/interactive-user-input.md` via
   Read — Pattern A/B apply **only** in interactive mode. In `--autonomous`
   mode there are ZERO prompts on any path.

If `.etc_sdlc/janitor/` does not exist, create it via Bash (`mkdir -p
.etc_sdlc/janitor`) before any state write. All janitor state lives under
`.etc_sdlc/janitor/` and nowhere else (BR-011, AC-011).

**Preconditions (abort with a clear message; no silent fallback):**
- `main` is missing, has no commits, or is unreadable → abort (edge 3). Never
  fall back to the current branch.
- A `.etc_sdlc/janitor/` run lock is held by another run → defer rather than race
  (edge 10).
- The boundary standard is absent or unparseable → abort, fail-closed.

## Workflow

The pipeline is a strict linear sequence with a fail-closed gate at each step.
Any gate failure aborts the remainder, tears down the worktree, opens nothing,
and credits no trust.

```
survey → select → isolate → dispatch → verify → boundary-check → deliver → record → teardown
```

### Step 0: Reconcile trust (run start)

Run `python3 scripts/janitor_trust.py reconcile` once at run start. This derives
each category's clean-streak from git/gh merge history and persists `trust.yaml`
(ADR-003). If `gh` is unavailable, reconciliation is a no-op and `trust.yaml` is
left untouched (never falsely promotes). This is the only place trust is written.

### Step 1: SURVEY (read-only)

Assemble a candidate fix list with a **read-only** repo scan (and local
roadmap/session signal where available). The survey writes **nothing** outside
the worktree (which does not exist yet) — it only reads. Classify each candidate
by category; candidates outside the v1 set are recorded in the report but **not
actioned** (AC-009).

**Published-asset classification (BR-001, before candidate finalization).** For
each `dead-code` deletion candidate, classify its path BEFORE the candidate is
finalized in the select step:

```bash
python3 scripts/janitor_assets.py classify <path>   # → published-asset | other
```

A `published-asset` path is **a published API surface**: it is served from a
deploy-to-URL root (the glob list lives ONLY in
`standards/process/janitor-write-boundary.md`; never hardcode a copy), and a
sibling repo may hotlink the URL it serves.
**Repo-local unreferenced-ness alone is never sufficient evidence for this file class**
— so a published-asset candidate is NOT finalized on the repo-local
test-unreached proof; it carries forward to the select-time org search below. A
candidate classified `other` (e.g. `src/helper.py`) is **not** a published
asset: it gets **no org search and no new prompt** — its flow is byte-equivalent
to today.

### Step 2: SELECT (flawless-only, capped)

Filter the candidate list to the **v1 categories ONLY** (BR-004, AC-009):

- **`lint-format`** — lint/format auto-fix **where a config already exists**.
  If no config exists, no-op for that category (never introduce a new config —
  an out-of-scope behavior change, edge 8).
- **`dead-code`** — removal of code the **existing test suite proves unreached**.
  No covering proof → not removed (edge 9, untested-files rule).
- **`whitespace-eof-imports`** — whitespace / EOF-newline / import-order
  normalization. Purely mechanical, no behavior change.

Cap the batch at the file-count ceiling: **batch max 3** files total. Drop any
candidate that is also an in-flight file (open-PR or recently-committed —
active-surface rule); report it as skipped (edge 6).

**Nothing to clean →** exit 0 with a "nothing to clean" report, **no PR, no
branch, no worktree created**, no leftover state (edge 1, AC-001).

**Published-asset guard at select (BR-002/BR-003/BR-004/BR-005, the gh trust
crossing).** For every candidate the survey classified `published-asset`, run
the org-wide consumer search HERE, in the orchestrator — this is the
orchestrator's single **gh trust crossing**; the fix-subagent is networkless and
never runs the search (see Subagent Dispatch / `agents/janitor.md`). The search
applies **identically in both lanes** — `/janitor` and `/janitor --autonomous`;
reviewer presence never substitutes for consumer evidence:

```bash
python3 scripts/janitor_assets.py consumer-search <filename> --repo-root .
# → JSON verdict {status, consumers[], evidence{}|null, reason|null}
#   status ∈ { cleared | blocked | fail-closed }   (closed vocabulary)
```

Branch on the verdict `status` (never the exit code), and record the outcome in
the run record (Step 8) for **every published-asset candidate, cleared or not**:

- **`cleared`** (org search succeeded, **zero** consumers) → the candidate is
  cleared for deletion; record the `evidence` dict verbatim — its `query`,
  `org_scope`, ISO-8601 `searched_at` timestamp, and `hit_count` (BR-006).
- **`blocked`** (one or more consumers) → **drop** the candidate; record the
  named `consumers[]` in the run record (the asset is consumed across a repo
  boundary). In interactive mode the operator MAY still confirm the deletion
  naming the known consumers (operator authority, edge 7) — recorded verbatim.
- **`fail-closed`** (search could not run — gh absent, unauthenticated,
  rate-limited, error; `reason` names the class) → **never clear by repo-local
  fallback** (BR-003 / GA-003). The two lanes diverge here, identically to the
  standard's dynamic-rule precedent:
  - **interactive** → route to an **operator-confirm** prompt (Pattern A) naming
    the asset and the fail-closed `reason`; the operator decides.
  - **`--autonomous`** → **drop** the candidate from the run and record the
    **fail-closed drop** (with `reason`) in `runs.jsonl`. No prompt, no clear.

Each published-asset candidate evaluates independently: cleared ones stay cleared
once their evidence is recorded; a mid-run rate-limit fails only the remaining
candidates closed (edge 6).

In **interactive** mode you MAY confirm the selected batch via Pattern A
(`AskUserQuestion`); the published-asset operator-confirm prompt above is the
ONLY new prompt this feature adds, and it fires **only** for published-asset
candidates. A candidate classified `other` reaches select with **no org search
and no new prompt** — the non-published-asset flow is byte-equivalent to today.
In **--autonomous** mode you MUST NOT prompt — proceed with the selected batch,
take the autonomous fail-closed **drop** for any unsearchable published asset,
or, if the batch is empty, take the nothing-to-clean exit.

### Step 3: ISOLATE (worktree off main — MANDATORY)

Create a throwaway git worktree on a fresh branch cut from `--base` (default
`main`), regardless of the operator's current branch (BR-002, ADR-001):

```bash
git worktree add <worktree-path> -b claude/janitor/<category>-<YYYY-MM-DD> main
```

- The branch name is in the `claude/janitor/*` namespace (distinct from
  `etc/feature/*` tags). The worktree path is unique per run.
- **Invariant (AC-002):** the operator's PRIMARY working tree is byte-identical
  before and after — verify `git status --porcelain` in the primary checkout is
  unchanged. Janitor never edits, stages, or commits in the primary tree.
- **Invariant (AC-003):** the branch's merge-base with `main` equals `main`'s
  HEAD at run start (`git merge-base claude/janitor/... main` == `git rev-parse
  main`) — proves "branched off main."
- If worktree creation fails (collision, disk, git error) → abort, no PR, clean
  up any partial worktree (edge 4).

All subsequent edits, the fix-subagent, and verification happen **inside this
worktree only**.

### Step 4: DISPATCH (one category at a time)

For each selected fix, dispatch the `janitor` fix-subagent (`agents/janitor.md`)
via the `Task` tool, passing the worktree path, **one** category, the target
files, and the boundary standard path (see Subagent Dispatch above). Never mix
categories in one dispatch. Collect each structured result.

If a subagent returns `success=false` (no config, unprovable dead code, refusal,
uncertainty), drop that fix from the batch and record it; never proceed on a
guess. If the batch becomes empty, tear down and take the nothing-to-clean exit.

### Step 5: VERIFY (gates green — net-positive)

Run the harness verification gates (tests, lint, type-check as applicable to the
touched files) **inside the worktree**. They MUST come back **green** before any
PR (BR-009, AC-006). A **red** or timed-out gate **aborts** the run with **no
PR** (fail-closed, edge 7). Never `--no-verify`, never `dangerouslyDisableSandbox`.

### Step 6: BOUNDARY-CHECK (mechanical veto — defense-in-depth)

Generate the worktree branch diff against `main` and pipe it to the mechanical
check, which sources its forbidden-path list + ceiling from the boundary
standard (AC-013):

```bash
git -C <worktree-path> diff main...HEAD | \
  python3 scripts/janitor_boundary_check.py --diff - \
    --boundary standards/process/janitor-write-boundary.md
```

- Exit 0 / `{"verdict":"clean"}` → proceed.
- Exit 2 / `{"verdict":"violation","rule":...}` → **abort**, **open no PR**,
  report the violated rule by name (AC-004/AC-005). A diff > 3 files fires
  `file-count-ceiling` (AC-005).
- Exit 1 (malformed/absent standard) → abort, fail-closed.

The scan is authoritative over the prompt: if the prompt and the scan disagree,
the scan wins and the run aborts (edge 5).

### Step 7: DELIVER (PR — draft vs ready, with local-branch fallback)

Read each selected category's trust level via
`python3 scripts/janitor_trust.py level <category>`, then open the PR targeting
`main` (BR-007, AC-007/AC-014):

- **All categories `preview`** → open a **DRAFT** PR (`gh pr create --draft`).
- **All categories `autonomous`** → open a **ready-for-review** PR.
- **Mixed batch** (any `preview` present) → **DRAFT** PR.

PR shape (design.md "API Contracts"):
- title: `janitor: <category> cleanup (<n> files)`
- base `main`, head `claude/janitor/<category>-<date>`
- body: the categorized **Janitorial Services** summary — categories, file list,
  boundary-check result (`clean`), gates (`green`), one-line per-fix rationale
  (AC-014).

**Degraded path (ADR-004):** if `gh` is absent, unauthenticated, or PR creation
fails, **degrade** rather than discard the verified fix: commit the fix to the
**local branch** (`claude/janitor/<category>-<date>`, off `main`), tear down the
worktree (the branch ref survives), and present the **Janitorial Services**
report directly to the operator — branch name plus the categorized summary — so
they can push/PR manually. A local-branch-only outcome earns **no** automatic
trust credit (ADR-003 reconciliation credits it later if the operator merges it).

```
Janitorial Services — <YYYY-MM-DD>
Branch: claude/janitor/<category>-<date>   (local branch — gh unavailable)
Categories: <category>(<n> files)
Boundary check: clean    Gates: green
Fixes:
  - <file>: <one-line rationale>
```

**Merge discipline (BR-010, AC-010):** janitor **never pushes to `origin/main`**,
**never merges its own PR** (no `gh pr merge`), **never bypasses git hooks**
(`--no-verify`), and **never sets `dangerouslyDisableSandbox`** — in any mode.
Janitor submits; a human merges. Trust graduation changes draft→ready only,
never merge authority.

### Step 8: RECORD (run ledger)

Append one line to `.etc_sdlc/janitor/runs.jsonl` (AC-011) describing the run:
`{run_id, mode, branch, categories[], files[], outcome, pr_url, boundary_check,
gates}` where `outcome ∈ {pr_opened, local_branch, nothing_to_clean,
aborted_boundary, aborted_gates, aborted_worktree, aborted_timeout}`. Trust is
NOT written here — clean-streaks are reconciled lazily at the next run's Step 0
(ADR-003). This skill is a read-only consumer of `trust.yaml`.

**Published-asset audit trail (BR-006).** The run line additionally carries a
`published_assets[]` array with one entry per published-asset candidate the
survey classified — **cleared or not** — so the consumer-search outcome from
Step 2 is auditable. Each entry records the path, the verdict `status`
(`cleared` | `blocked` | `fail-closed`), and the select-time outcome:

- `cleared` → the `evidence` dict verbatim (`query`, `org_scope`, `searched_at`,
  `hit_count`).
- `blocked` → the named `consumers[]` (and the operator-confirm record, if the
  operator authorized the deletion despite a named consumer — edge 7).
- `fail-closed` → the `reason` (gh-boundary class) plus the lane resolution: the
  **operator-confirm** record (interactive) or the **fail-closed drop**
  (autonomous). Recording the fail-closed drop in `runs.jsonl` is mandatory in
  the autonomous lane — a dropped published-asset candidate is never silent.

### Step 9: TEARDOWN (always)

Remove the worktree on completion **or** abort — idempotent, best-effort:

```bash
git worktree remove <worktree-path> --force
git worktree prune
```

The branch ref **survives** (it is the PR head, or the recoverable local branch
on the degraded path). Release the `.etc_sdlc/janitor/` run lock. A crashed run
that strands a worktree dir is cleaned up by the next run's idempotent teardown.

## Ceilings (NFR — fail-closed on exhaustion)

- **30-min wall-clock** per run.
- **~50 subagent turns** per run (the fix-subagent's `maxTurns: 50`).
- **batch max 3** files (the boundary ceiling; same integer as the file-count
  rule).
- **N=5** consecutive clean merges to auto-promote a category (ADR-005).

On exhaustion (runaway / stuck loop), **abort with no PR** (edge 13, ties to
F019). The worktree is torn down (Step 9) and no trust is credited.

## Trust Command Surface (AC-012)

The operator inspects and overrides trust without touching files directly:

```
/janitor trust                    -- python3 scripts/janitor_trust.py table
/janitor trust demote <category>  -- python3 scripts/janitor_trust.py demote <category>
```

`/janitor trust` prints each category's trust level + clean-streak count.
`/janitor trust demote <category>` returns a named category to `preview`
(clean_streak → 0) in `trust.yaml`; effective on the next run (an already-open
autonomous PR is unaffected — edge 14). Validate `<category>` against the known
v1 set before delegating.

## Constraints

- **v1 categories ONLY:** `lint-format`, `dead-code`, `whitespace-eof-imports`.
  Any candidate outside these appears in the report but is **not actioned**
  (BR-004, AC-009). The SDLC autochain (`/goal → /spec → /architect → /build
  --autonomous`) is a documented **v2** north star (ADR-002), NOT built in v1.
- **Argv-list subprocess only** for all git/gh calls — never `shell=True`, never
  an interpolated shell string with a branch/category name (command-injection
  defense).
- **Fail-closed everywhere:** every ambiguous or error state aborts with no PR,
  or degrades to the local-branch no-op artifact — never proceeds on doubt.
- **Single source of truth:** the forbidden-path list + ceiling live ONLY in
  `standards/process/janitor-write-boundary.md`. Neither this skill nor the
  boundary check embeds a second copy (AC-013).
- **Hands-off absolute in `--autonomous`:** no `AskUserQuestion`, no Pattern B,
  no blocking prompt anywhere on that path. Choose the safe default or abort.

## Definition of Done

A `/janitor` run is done for a given invocation when ALL hold:

1. The run terminated in exactly one of: an opened PR (draft or ready), a
   degraded local branch, a clean "nothing to clean" exit (code 0), or a
   fail-closed abort with no PR (AC-001).
2. The operator's PRIMARY working tree is byte-identical before and after:
   `git status --porcelain` in the primary checkout is unchanged (AC-002). Any
   worktree created was removed (Step 9).
3. If a PR was opened, its branch's merge-base with `main` equals `main`'s HEAD
   at run start (AC-003), the verification gates were green and the boundary
   check returned `clean` BEFORE the PR existed (AC-006), the draft/ready state
   matches the categories' trust levels (AC-007), and the PR body names the
   categories + the clean boundary-check result (AC-014).
4. No edit, stage, or commit occurred in the operator's primary tree; the run
   did not push `origin/main`, did not run `gh pr merge`, did not pass
   `--no-verify`, and did not set `dangerouslyDisableSandbox` (AC-010).
5. Every janitor state write landed under `.etc_sdlc/janitor/` (AC-011); the run
   was appended to `runs.jsonl`; trust was written ONLY by `janitor_trust.py`.

If any item fails, the run is NOT done regardless of which steps reported success.

## See also

- Spec: `.etc_sdlc/features/active/F-2026-05-29-janitor-autonomous-cleanup/spec.md`
- Design: `.../design.md` (the 9-step pipeline, API contracts, security)
- ADRs: `docs/adrs/F-2026-05-29-janitor-autonomous-cleanup-00{1..5}-*.md`
- `agents/janitor.md` — the constrained fix-subagent
- `scripts/janitor_boundary_check.py` — the mechanical pre-PR veto
- `scripts/janitor_trust.py` — the sole `trust.yaml` writer
- `scripts/janitor_assets.py` — published-asset `classify` + `consumer-search`
- `standards/process/janitor-write-boundary.md` — forbidden paths + ceiling (SoT)
- `skills/efficiency/SKILL.md` — F019 observe-and-propose cousin
