# Hook Cost Reduction — PRD Brief (Deferred)

**Status:** Deferred. This is a brief, not a buildable spec. Promote to a
full PRD via `/spec` when ready to implement.

**Origin:** 2026-04-15, surfaced mid-`/hotfix` `/build` when the operator
noticed ~15–30s of wall-clock latency per Edit being spent in
PreToolUse hook machinery. Root cause analysis below.

## The Problem

Every Edit/Write tool call in the etc harness fires **6 command hooks** — 5
PreToolUse (blocking) and 1 PostToolUse (non-blocking):

| Hook | Event | Matcher | Timeout | What it does |
|---|---|---|---|---|
| `check-tier-0.sh` | PreToolUse | `Edit\|Write` | 5s | Repo has DOMAIN.md + PROJECT.md |
| `check-test-exists.sh` | PreToolUse | `Edit\|Write` | 5s | `src/*.py` has matching `tests/test_*.py` |
| `check-invariants.sh` | PreToolUse | `Edit\|Write` | 10s | INVARIANTS.md verify commands |
| `check-required-reading.sh` | PreToolUse | `Edit\|Write` | 10s | Agent read `requires_reading` from task |
| `check-phase-gate.sh` | PreToolUse | `Edit\|Write` | (default) | Edit is appropriate for current SDLC phase |
| `mark-dirty.sh` | PostToolUse | `Edit\|Write` | — | Touches `.tdd-dirty` breadcrumb |

A typical subagent doing ~10 edits → 60 bash-script launches. A wave of 8
parallel subagents → ~480 subprocess launches. On macOS, each bash
invocation has ~30–80ms of shell startup + `jq` stdin unmarshaling,
*before* the script does any work. That's ~24 seconds of pure hook
bootstrap per wave, not counting the scripts' actual execution.

The worst offenders:

- **`check-invariants.sh`** (10s timeout). If INVARIANTS.md verify commands
  run `pytest` or `mypy` on every Edit, the per-Edit cost is seconds,
  not milliseconds. 10× worse than bash startup.
- **`check-required-reading.sh`** (10s timeout). Parses transcript JSON
  on every Edit to determine which files the agent has read. Amortizing
  this to once-per-subagent would cut ~90% of its fires.

## Why the Obvious Fix Doesn't Work

The naive optimization is "move `check-required-reading` and
`check-phase-gate` from PreToolUse `Edit|Write` to SubagentStart." Both
hooks check subagent-scope state that can't change between Edits within
the same subagent session, so the move *sounds* like a pure win.

**It isn't, and here's why.** Both scripts read `.tool_input.file_path`
from stdin — that field only exists on PreToolUse Edit|Write events.
At SubagentStart, the script input has `cwd`, `agent_type`, and
`transcript_path` — no `tool_input`. If we move the registration without
rewriting the scripts:

- `check-phase-gate.sh` hits its early-exit: `if [[ -z "$FILE_PATH" ]]; then exit 0; fi` → **always passes, effectively disabled**.
- `check-required-reading.sh` has the same early-exit pattern → **always passes, effectively disabled**.

Moving the registrations without rewriting the scripts is disabling the
gates, not optimizing them. The scripts would need to be rewritten to
operate on subagent-level state (agent_type, task_id, current phase)
rather than per-Edit state (target file path, recent tool_input history).
That's a real refactor, not a one-line DSL edit.

## Option Space

Three real optimization paths, each with real tradeoffs:

### Option A: Rewrite check-required-reading + check-phase-gate for SubagentStart

- **What:** Replace both hook scripts with SubagentStart variants that
  operate on subagent-level context.
  - `check-required-reading.sh` at SubagentStart: check whether the
    subagent's active task file has a `requires_reading` list, and if so,
    inject the files' contents into the subagent's context at spawn.
    Converts "block on Edit if not read" to "auto-read at spawn" — the
    subagent can't fail the check because the harness does the reading
    for it.
  - `check-phase-gate.sh` at SubagentStart: check whether the
    subagent's `agent_type` is allowed in the current SDLC phase (e.g.,
    during Spec phase, only `spec-enforcer` and read-only agents can
    spawn). Whole-subagent granularity instead of per-Edit.
- **Win:** 2 of 5 PreToolUse hooks eliminated per Edit. Subagent context
  is richer at spawn.
- **Loss:** Phase-gate weakens from per-Edit to per-subagent. If a
  backend-developer is spawned during Spec phase, the whole subagent is
  rejected up front instead of specific Edits being blocked — probably
  fine in practice, but a semantic change worth calling out.
- **Work:** 2 script rewrites (~150 lines each), 2 new test files,
  DSL changes, regression verification that existing `check-phase-gate`
  test still passes or is replaced.

### Option B: Coalesce the 5 PreToolUse scripts into one

- **What:** Write `hooks/check-edit-preflight.sh` that runs all 5
  existing scripts in sequence in one subprocess. DSL replaces the 5
  separate registrations with 1.
- **Win:** 5 bash startup costs → 1. Saves ~200–400ms per Edit on macOS.
  Zero semantic change — same exit codes, same checks, same order.
- **Loss:** Harder to read and test. Individual hook failure now
  surfaces as "the preflight script failed at step 3" instead of a named
  hook. Status messages are trickier to pipe through.
- **Work:** 1 wrapper script (~60 lines), 1 new test that asserts the
  wrapper invokes each sub-script correctly, DSL change, verify all
  existing `test_check_*` regression tests still pass against the
  wrapper.

### Option C: Cache per-subagent hook results via marker files

- **What:** Add `.etc_sdlc/.hook-markers/{subagent_id}/{hook_name}.ok`
  marker files. Each hook, at the start, checks if its marker exists
  and exits 0 if so. On first successful run, the hook creates its
  marker. SubagentStart or SessionStart clears the markers for new
  subagents.
- **Win:** First Edit per subagent pays full cost; subsequent Edits pay
  only a `test -f` check (sub-millisecond). For long-running subagents
  (10+ edits), nearly 10× speedup on the amortized cost.
- **Loss:** Cache invalidation is hard. If `requires_reading` changes
  mid-subagent (e.g., a new file is added to the task), the cached
  "passed" marker becomes stale. Phase changes mid-session have the
  same problem. Need a `cache_invalidation_triggers` contract per hook.
- **Work:** Add marker-check logic to all 5 hooks, add marker-clear to
  SubagentStart, add a `hook-markers/` entry to `.gitignore`, update
  all 5 hook test files to cover the marker-hit and marker-miss paths.
  Biggest engineering surface of the three options.

## Recommendation

**Option B first (coalescing) for speed, Option A second (SubagentStart
rewrite) for structural cleanness, Option C last (caching) for the
complexity budget.** B is the fastest to ship and has zero semantic
risk; A is a proper architectural improvement but needs the two
rewrites; C is the biggest win but also the biggest cache-invalidation
footgun.

## Open Questions

1. **Profile first, optimize second.** Is `check-invariants.sh` actually
   running `pytest` on every Edit, or is it reading a cached manifest?
   If it's fast in practice, the whole optimization is less urgent.
   Adding a `.etc_sdlc/hook-timings.jsonl` append from every hook
   invocation (event, script, duration, agent_type, cwd) would make
   the problem observable before we try to fix it. Worth doing as a
   zeroth step.

2. **Can we run PreToolUse hooks in parallel?** Claude Code already
   dispatches same-event handlers in parallel; our 5 hooks are under
   the same matcher but in separate hook entries. If they're serialized
   today, just splitting them into N parallel dispatches cuts latency
   without any other change.

3. **What's the actual cost of each hook?** 60 × 50ms = 3s per subagent,
   not 30s. If the real pain is elsewhere (adversarial-review at
   SubagentStop is 30–60s per subagent), the per-Edit path is the wrong
   optimization target entirely.

## Proposed First Step

A research spike (not a PRD) to add hook-timing observability. ~30
minutes of work: modify each hook script to append a JSONL line to
`.etc_sdlc/hook-timings.jsonl` with `event`, `script`, `duration_ms`,
`agent_type`, `cwd`, and `result`. Run a normal build and inspect the
resulting file. This turns the cost question from guesswork into data.
After that, the right optimization picks itself.

## Why This Is a Brief and Not a Spec

The quick-fix interpretation ("move 2 hooks to SubagentStart") turned
out to be a rewrite, not a move. The real work needs:

- Profiling data (open question #3) before we know which path is worth
  the engineering investment.
- Semantic tradeoff acknowledgment (Options A and C both have
  correctness risks).
- A clear success metric (the spec should target e.g., "reduce
  per-Edit hook overhead below 100ms" or "reduce wave wall-clock by
  30%") grounded in the profiling data.

None of those exist yet. File as a brief, revisit with /spec when the
profiling step lands.

## Related

- Earlier session finding: `adversarial-review` at SubagentStop is
  30–60s per subagent and may be a bigger cost driver than per-Edit
  hooks. Both deserve investigation in the same profiling spike.
- `standards/git/commit-discipline.md` (commit `ff2b268`) is an example
  of a discipline that shipped correctly once the failure mode was
  observable. Hook cost is less observable today than that failure
  mode was; observability is the prerequisite.
