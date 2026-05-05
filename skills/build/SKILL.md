---
name: build
description: Full pipeline conductor — validate, decompose recursively, plan waves, dispatch each wave via Agent-tool subagent calls, verify. The single entry point for building any feature from spec to working code.
---

# /build — The Conductor

You are the pipeline conductor. You orchestrate the ENTIRE build lifecycle from
spec to verified, working code. You call other skills and scripts in a
deterministic sequence with checkpoints at every step.

Unlike `/implement` (which handles dispatch) or `/decompose` (which handles
breakdown), `/build` owns the full pipeline and ensures nothing is skipped.

## Response Format (Verbosity)

Terse and structured. Use tables for wave/task data, numbered lists for
ordered procedures, fenced code blocks for machine-readable artifacts
(state.yaml, wave plans, verification reports). Prose is limited to:
(a) step-entry announcements defined below, (b) rejection messages from
Step 1, (c) escalation messages to the user. No preamble ("I'll...",
"Here is..."). No narrative summary. No emoji. Max 300 words per
orchestrator-level response unless producing a step-transition report
(max 600 words) or the final Step 8 summary (max 800 words). When a
dispatched subagent returns, summarize the result in <= 5 lines; do not
echo the full subagent output.

## Subagent Dispatch (Non-Negotiable)

Your sole execution mode for task work is dispatch. You MUST NOT perform
task implementation in your own context. The rules below are absolute:

1. **For every task in the current wave, you MUST invoke the Agent tool
   once with `subagent_type` set to the task's `assigned_agent` field.**
   One Agent invocation per task, no exceptions.
2. **You MUST NOT implement the task in your own context.** If you catch
   yourself writing production code, writing tests, or editing files in
   `src/`, stop and dispatch to the correct agent instead.
3. **You proceed to the next wave only after every dispatched subagent
   has returned a result.** Read each result before updating task status.
4. **In parallel fan-out within a wave, issue all N Agent-tool calls
   in a single turn.** The wave-planner has already verified file-set
   isolation; do not serialize within a wave unless a subagent
   returned an escalation requiring the next Agent call to wait.
5. **Your allowed in-context actions are limited to:** (a) reading state
   via Read/Grep/Glob/Bash, (b) announcing step and wave transitions,
   (c) writing briefing prompts for subagents, (d) reading and
   summarizing subagent results, (e) updating `state.yaml` and task
   status via `tasks.py` Bash calls, (f) running verification commands
   (pytest, compile, invariant checks) at Step 7, (g) writing the
   `verification.md` artifact.

If a task has no `assigned_agent` or the agent name does not resolve,
STOP and ask the user which agent should own it. Do not default to
doing the task yourself.

## Before Starting (Non-Negotiable)

Read these files in order before any Step 1 action, using the Read tool
on each exact path:

1. `standards/process/interactive-user-input.md` — AskUserQuestion
   Pattern A (used in Steps 3 and 5)
2. `INVARIANTS.md` (at repo root, if present) — the verify commands
   referenced in Step 7

If `INVARIANTS.md` does not exist, record that Step 7 will skip the
invariant-check sub-step and proceed. If
`standards/process/interactive-user-input.md` does not exist, STOP and
report the missing file to the user — Steps 3 and 5 cannot proceed
without it.

## Usage

```
/build spec/prd-authentication.md
/build .etc_sdlc/features/auth/spec.md
/build --resume                           # Resume from last checkpoint
```

## The Pipeline

```
VALIDATE → SETUP → DECOMPOSE → SCORE/RECURSE → PLAN WAVES → EXECUTE → VERIFY → REPORT
   1         2         3            4               5           6         7        8
```

Each step writes state to the feature directory. If the session dies, compacts,
or is interrupted, `/build --resume` picks up from the last completed step.

---

### Step 1: VALIDATE — Definition of Ready gate

This is the single quality gate at the entry to the build pipeline. You are
the VP of Engineering reviewing a spec before committing agent-hours to
implementing it. Be firm but constructive — when you reject, tell the user
exactly what's missing so they can fix it.

**Step 1a: Check for a prior /spec classification.**

If `.etc_sdlc/features/{slug}/rejected.md` exists, the spec has already
been classified as too under-specified to build. STOP immediately. Do not
run any further steps. Report:

> This spec was rejected by /spec as under-specified. See
> `.etc_sdlc/features/{slug}/rejected.md` for the specific gaps.
> Resubmit via `/spec` after answering the questions listed there.

If `.etc_sdlc/features/{slug}/spec.md` exists AND a sibling `state.yaml`
shows the feature passed through /spec's three-state classifier with a
research-assisted or well-specified result, pass Step 1 immediately —
the DoR check already happened upstream. Write `step_completed: 1_validate`.

**Step 1b: Inline DoR check (for hand-written specs).**

If the spec did NOT come through /spec (for instance, the user ran
`/build spec/some-file.md` on a hand-written PRD), evaluate the DoR
checklist yourself against the spec file contents:

- [ ] **Specific enough to implement without ambiguity.** No phrases like
      "something like", "probably", "TBD", or "figure out later".
- [ ] **Names concrete files, modules, endpoints, or components.** At
      least one explicit file path or module name per major section.
- [ ] **Has measurable acceptance criteria.** Every requirement is
      phrased so a reviewer can say "this is met" or "this is not met"
      without judgment calls.
- [ ] **Does not require unstated domain knowledge.** A fresh agent
      reading only this spec and the repo could implement it.
- [ ] **Scope boundaries are clear.** Explicit "in scope" and "out of
      scope" lists, or equivalent language.

**If the spec passes:** Write `step_completed: 1_validate` and proceed
to Step 2.

**If the spec fails:** STOP immediately. Do not proceed to Step 2. Write
a rejection message of the form:

> Spec is not ready to build. Specific gaps:
> (1) [gap with file/section reference]
> (2) [gap with file/section reference]
> ...
>
> Run `/spec {path}` to refine it, then re-run `/build`.

Name every gap with a specific section or line reference from the spec
file. Vague feedback ("add more detail") is not acceptable — the user
must be able to act on each gap without asking you what you meant.

**Scope of this gate.** This check runs ONLY on the spec artifact at
`/build` invocation. It does not run on conversational prompts,
ideation, or hotfixes — those are different lanes with different quality
bars. If the user is in a conversation and asks you to build something
casually, suggest they run `/spec` first to formalize the request before
invoking `/build`.

### Step 2: SETUP

Determine the feature slug from the spec title (lowercase, hyphens).

Create or verify the feature directory:
```
.etc_sdlc/features/{slug}/
  spec.md              ← copy PRD here if not already present
  tasks/               ← empty, will be populated in Step 3
  state.yaml           ← pipeline state tracking
```

**MERGE state.yaml; never overwrite.** /spec writes load-bearing
metadata into state.yaml during Phases 2.75 and 5: `classification`,
`phase_2_75_metrics`, `author_role`. /build's Step 2 owns its own keys
under a top-level `build:` block, but every other key MUST be preserved
verbatim. Read existing state.yaml first; if absent, start with an
empty dict; then add or update the `build:` block; then write back.

The canonical merge is the following inline Python invocation. Run it
from the project root with `<state_yaml_path>`, `<slug>`, `<spec_path>`,
and `<iso8601>` substituted in by the runtime conductor:

```
python3 -c "
import yaml
from pathlib import Path
p = Path('<state_yaml_path>')
state = yaml.safe_load(p.read_text()) if p.exists() else {}
state['build'] = {
    'feature': '<slug>',
    'spec_path': '<spec_path>',
    'current_step': 2,
    'started_at': '<iso8601>',
    'mode': None,
    'waves_completed': 0,
    'total_waves': None,
}
p.write_text(yaml.safe_dump(state, sort_keys=False))
"
```

Every later state-update step in /build mutates only `state['build'][...]`
(e.g. `state['build']['current_step'] = 3`); the top-level `classification`,
`phase_2_75_metrics`, and `author_role` keys written by /spec stay
untouched throughout the pipeline.

**On success:** Mutate `state['build']['current_step'] = 2` and write the
merged state back.

### Step 3: DECOMPOSE (Initial Breakdown)

Read the spec. Break it into tasks following `/decompose` conventions:

1. Identify natural boundaries (modules, layers, components, interfaces)
2. Write task YAML files via a single atomic batch:
   `python3 ~/.claude/scripts/tasks.py bulk-create --feature {slug}` with a JSON array
   on stdin. NEVER hand-write task YAML with the Write tool — the CLI
   enforces schema, rolls back on any error, and saves ~75% of tokens.
   See `/decompose` for the full JSON shape and field reference.
3. Use hierarchical IDs: `001`, `002`, `003`, ...
4. Each task gets: requires_reading, files_in_scope, acceptance_criteria, dependencies
5. Every acceptance criterion from the spec maps to exactly one task
6. Every file in Module Structure maps to exactly one task

Run: `python3 ~/.claude/scripts/tasks.py list --tree` to confirm the breakdown.
Print the tree so the user can see it, then ask for confirmation using
`AskUserQuestion` (see standards/process/interactive-user-input.md,
Pattern A):

```
AskUserQuestion(
  questions: [{
    question: "Task breakdown looks right?",
    header: "Breakdown",
    multiSelect: false,
    options: [
      {
        label: "Yes, proceed to scoring (Recommended)",
        description: "The breakdown covers every acceptance criterion and every file from the Module Structure. Move to Step 4."
      },
      {
        label: "Re-decompose",
        description: "Something is missing, overlapping, or miscategorised. Revise the tasks and re-run this step."
      }
    ]
  }]
)
```

**On success:** Update `state.yaml`: `current_step: 3`

### Step 4: SCORE AND RECURSE

This is the critical loop that enables arbitrary scale.

```
REPEAT:
  1. Run: python3 ~/.claude/scripts/tasks.py score
  2. Run: python3 ~/.claude/scripts/tasks.py ready-to-decompose
  3. IF any tasks score > 7:
       For each flagged task:
         a. Read the task's acceptance criteria and files_in_scope
         b. Break into subtasks (hierarchical IDs: 002 → 002.001, 002.002, ...)
         c. Set parent status to "decomposed"
         d. Each subtask gets a subset of the parent's criteria and files
         e. NO criteria orphaned, NO files orphaned, NO scope overlap
       CONTINUE loop
  4. ELSE:
       All leaf tasks score ≤ 7. Exit loop.
```

After the loop:

Determine mode from final task tree:
- ≤ 3 leaf tasks → QUICK
- 4-15 leaf tasks → STANDARD
- > 15 leaf tasks → DEEP

Update `state.yaml`: `current_step: 4`, `mode: {QUICK|STANDARD|DEEP}`

Report to user:
```
Decomposition complete.
  Total tasks: {N} ({M} leaf, {K} parent)
  Max depth: {D} levels
  Mode: {mode}
  All leaf tasks score ≤ 7. Ready for wave planning.
```

### Step 5: PLAN WAVES

Run: `python3 ~/.claude/scripts/tasks.py waves`

Verify:
- No file overlaps within any wave (if found, serialize the conflicting tasks)
- Dependencies respected (no task in wave N depends on a task in wave N+1)

Update `state.yaml`: `current_step: 5`, `total_waves: {N}`

Print the wave plan so the user can see it:

```
Wave plan:
  Wave 0: {N} tasks (parallel)
  Wave 1: {M} tasks (parallel, after wave 0)
  Wave 2: {K} tasks (parallel, after wave 1)
  ...
  Total waves: {W}
```

Then ask for confirmation via `AskUserQuestion`:

```
AskUserQuestion(
  questions: [{
    question: "Proceed with wave execution?",
    header: "Execute?",
    multiSelect: false,
    options: [
      {
        label: "Execute all waves (Recommended)",
        description: "Run every wave in order. I'll stop on any failing test or escalated task."
      },
      {
        label: "Dry run — first wave only",
        description: "Run Wave 0 only, then stop and report. Use this for debugging or unfamiliar features."
      },
      {
        label: "Cancel — review the plan first",
        description: "Don't execute yet. I'll pause so you can review tasks/ and state.yaml before proceeding."
      }
    ]
  }]
)
```

Wait for the user's selection before executing.

### Step 6: EXECUTE (Wave by Wave)

For each wave, in order:

**6a. Dispatch wave N (Agent-tool rules from the Subagent Dispatch
section above apply absolutely):**

Before dispatching any subagent for wave N, write the phase-start tag
for the feature so process metrics observe wave entry:

- Treat the current wave as phase-N for tag-naming purposes. (If the
  build does not yet maintain an explicit phase->wave mapping, each
  wave is its own phase. This assumption is documented here so the
  metrics layer can rely on it.)
- Invoke the git_tags.py write-tag CLI with the name
  `etc/feature/F<NNN>/build/phase-<N>/start` at the current HEAD:
  ```
  python3 ~/.claude/scripts/git_tags.py write-tag "etc/feature/F<NNN>/build/phase-<N>/start"
  ```
  Substitute `F<NNN>` with the feature ID from `state.yaml`'s
  top-level metadata (set by /spec) and `<N>` with the wave number.
  The CLI degrades gracefully on non-git directories or repos without
  a HEAD commit (exit code 1 with a stderr warning); treat exit codes
  0 (created) and 1 (degrade) as both acceptable advisory outcomes
  and continue. Only exit code 2 (hard error) is a real fault.

  The CLI form is required because the helpers are installed under
  `~/.claude/scripts/`, not the user's project — `from scripts.git_tags
  import …` only resolves inside this checkout, so it MUST NOT be used.

**6a.5: Detect user-facing tasks and auto-add parent wiring files
(per `standards/process/user-flow-completeness.md` — Dispatch-time
Wiring Contract section).**

Before dispatching each task in this wave, scan the task's
`acceptance_criteria` field (only — not `requires_reading`, not the
task description) for the canonical User-flow sentence prefix: the
literal substring `As ` followed (later in the same sentence, before
the next sentence terminator) by the literal substring `, navigate
from`. A task is user-facing for the purposes of this step iff at
least one of its ACs contains that prefix pair.

- **Detected tasks** trigger the auto-add heuristic below.
- **Non-detected tasks** dispatch through the existing flow at 6a
  unchanged — no heuristic, no clause injection, no operator prompt.
  The wiring check fires forward-only on User-flow-sentenced ACs (per
  F001 BR-007); legacy specs and backend-only ACs pass through.

For each detected user-facing task, run the four-tier auto-add
heuristic in the preference order defined by the Dispatch-time Wiring
Contract section of `standards/process/user-flow-completeness.md`:

1. **Tier 1 — Sidebar-nav config files** (e.g., `**/layout/sidebar-nav.*`,
   `**/nav/sidebar.*`).
2. **Tier 2 — Parent-route files** matching the new component's route
   prefix (e.g., new file at `routes/_auth/admin/orgs/new/...` →
   parent at `routes/_auth/admin/orgs/index.*`).
3. **Tier 3 — Barrel exports** (`index.ts`, `index.tsx`, `mod.rs`)
   that already export sibling components in the same directory.
4. **Tier 4 — Settings-rail / tab-array config files** matching
   `**/tabs/*` or `**/settings/*` config patterns.

Stop at the first tier that returns one or more candidates; do not
continue to lower tiers once a tier has matched. The full pattern
definitions, signal lists, and matching rules live in the standards
doc — do NOT duplicate them here. Use `Glob` and `Grep` against the
deliverable directory tree (the user's project, not the etc repo) to
materialize candidates, and verify each candidate exists on disk
before treating it as a match.

Resolution outcomes:

- **Exactly one strong candidate.** Auto-add the candidate path to
  the task's `files_in_scope`. If the task YAML is the source of
  truth, persist via `python3 ~/.claude/scripts/tasks.py` (matching
  the existing CLI conventions used elsewhere in Step 6); if the
  dispatcher is operating on in-memory task state, mutate the
  in-memory list. Idempotency: if the candidate is already present
  in `files_in_scope`, skip the add (no-op) and proceed. Note the
  addition in a status message before dispatching, e.g., `Auto-added
  'frontend/src/components/layout/sidebar-nav.tsx' to task
  003.files_in_scope as parent wiring file (Tier 1, sidebar-nav)`.
  Then proceed to the per-task dispatch below.
- **Zero candidates.** Fall through to the operator-prompt fallback
  (sub-step 6a.6, owned by sibling task 002.002). Do not dispatch
  the task until the operator-prompt outcome is recorded.
- **Multiple plausible candidates with comparable confidence**
  (more than one match in the same heuristic tier with no clear
  winner). Fall through to the operator-prompt fallback (sub-step
  6a.6).

The standards doc is the single source of truth for the heuristic
preference order, the signal list, and the operator-prompt structure.
This skill body cites it by path; consult the Dispatch-time Wiring
Contract section of `standards/process/user-flow-completeness.md`
for the full rule.

**6a.6: Operator-prompt fallback for ambiguous heuristic results
(per `standards/process/user-flow-completeness.md` — Dispatch-time
Wiring Contract section, Operator-Prompt Fallback subsection).**

If sub-step 6a.5 returned zero candidates OR multiple candidates with
no clear winner (more than one match in the same heuristic tier with
comparable confidence), the dispatcher MUST resolve the ambiguity by
prompting the operator via Pattern A (`AskUserQuestion`) per
`standards/process/interactive-user-input.md`. Do NOT bury this
question in prose; do NOT guess past the ambiguity; do NOT dispatch
the task until the operator's selection is recorded.

Forward-only reminder: this fallback fires ONLY for tasks whose AC
contained the canonical User-flow sentence prefix detected in 6a.5.
ACs without User-flow sentences pass through dispatch unchanged — no
heuristic, no operator prompt, no clause appended (per BR-007 + AC18).

Invoke `AskUserQuestion` with the question text naming the task ID
and the User-flow sentence's `{parent route}` value, and with one
option per heuristic candidate plus an explicit "intentionally
orphaned" deferral option. The "None of the above — let me name a
custom parent file" path uses `AskUserQuestion`'s automatic Other
escape hatch (do NOT add an explicit "Other" option — the tool
provides it). Example shape:

```
AskUserQuestion(
  questions: [{
    question: "Task 003 creates a user-facing surface; its User-flow sentence references parent route '/admin/orgs'. Which file wires the new surface into the parent navigation graph?",
    header: "Parent wire",
    multiSelect: false,
    options: [
      {
        label: "frontend/src/components/layout/sidebar-nav.tsx (Recommended)",
        description: "Tier-1 sidebar-nav config candidate from the heuristic. Adds this path to files_in_scope and dispatches normally."
      },
      {
        label: "frontend/src/routes/_auth/admin/orgs/index.tsx",
        description: "Tier-2 parent-route candidate. Adds this path to files_in_scope and dispatches normally."
      },
      {
        label: "Skip — this surface is intentionally orphaned",
        description: "Records `surface_status: deferred` on the task YAML and dispatches without a parent file. Use when the surface is not yet user-reachable by design."
      }
    ]
  }]
)
```

Post-prompt action:

- **Operator selected a candidate file** (one of the heuristic options
  OR a custom path entered via `AskUserQuestion`'s automatic Other
  escape hatch). Record the selection in the task's `files_in_scope`
  via `python3 ~/.claude/scripts/tasks.py` (or in-memory mutation if
  the dispatcher is operating on in-memory task state), then proceed
  to the per-task dispatch loop below. Operator-supplied custom paths
  are sanitized per the rule defined in the standards doc — do NOT
  duplicate the sanitization regex inline; consult the Dispatch-time
  Wiring Contract section of
  `standards/process/user-flow-completeness.md` for the full
  operator-supplied path sanitization contract.
- **Operator selected "Skip — intentionally orphaned"**. Record
  `surface_status: deferred` as a top-level line on the task YAML
  (via `tasks.py` or in-memory mutation), then proceed to the
  per-task dispatch loop. The dispatched agent still receives the
  wiring-contract clause in its prompt (see below) so it understands
  that wiring is part of the deliverable; the deferral is an audited
  exception, not a silent skip.

After the operator-prompt outcome is recorded, dispatch proceeds at
the existing per-task loop below. The standards doc owns the full
contract for the prompt structure, the candidate-set construction,
the operator-supplied-path sanitization rule, and the deferral
recording format — see the Operator-Prompt Fallback subsection of
`standards/process/user-flow-completeness.md`.

For each task in the current wave:
- Update task status via `python3 ~/.claude/scripts/tasks.py set-status
  --id {task_id} --status in_progress`
- Invoke the Agent tool ONCE with `subagent_type` set to the task's
  `assigned_agent` field. The prompt MUST include: the task YAML path,
  the list of `requires_reading` file paths, the list of
  `files_in_scope` paths, the acceptance criteria, and the instruction
  "Dispatch hooks will enforce TDD, invariants, required reading, and
  phase gate — do not circumvent them."
- For User-flow-sentenced tasks (those detected at sub-step 6a.5), the
  prompt MUST also include the wiring-contract clause from
  `standards/process/user-flow-completeness.md` (Dispatch-time Wiring
  Contract section, "The Wiring Contract" subsection), appended
  verbatim as a blockquote so the dispatched agent reads it as part
  of its onboarding context. The clause body is:

  > Your task creates a user-facing surface (route/modal/tab/sidebar entry/wizard step) per the User-flow sentence in your AC. The surface is NOT done until it is wired into the parent navigation graph in the SAME commit as the new surface. Your `files_in_scope` includes the parent wiring file at `<path>` for this purpose. Before reporting success, run `grep -rn "<your-route-or-component-name>" <project>/frontend/src` (or the equivalent for your stack) and confirm at least one parent surface references it via `<Link>`, `<Tab>`, sidebar-config entry, or equivalent. If the parent file does not contain a working reference after your edits, do not report success. See `standards/process/user-flow-completeness.md` (Dispatch-time Wiring Contract section) for the full rule.

  Substitute `<path>` with the parent wiring file path resolved at
  6a.5 (auto-add) or 6a.6 (operator selection). For tasks marked
  `surface_status: deferred` at 6a.6, the clause is still appended
  (the agent must understand wiring is part of the deliverable even
  when no parent file is in scope) and `<path>` is rendered as
  `(deferred — no parent file in scope; escalate if you discover the
  surface needs to be wired)`. ACs without User-flow sentences pass
  through dispatch unchanged: no clause appended, no operator prompt
  fired, prompt content matches the pre-edit shape byte-equivalently.
- You MUST NOT read, edit, or write any file listed in the task's
  `files_in_scope` in your own context. That work belongs to the
  dispatched subagent.

Dispatch all tasks in the wave in a single turn (parallel fan-out).
The wave-planner from Step 5 has already verified file-set isolation;
do not serialize within a wave.

**6b. Wait for wave completion:**
- Every dispatched subagent must return a result before you proceed.
- For each returned result, set task status to `completed` (if the
  subagent reported success) or `escalated` (if the subagent reported
  a blocker) via `tasks.py set-status`.

**6c. Verify wave:**
- Run tests: `python3 -m pytest --tb=short -q`
- If tests fail: STOP. Report the failure. Do NOT proceed to next wave.
  **Do not write the phase-N/done tag.** The phase-N/start tag from
  step 6a remains in place — it is append-only and records that the
  wave was attempted. Earlier successful phase tags also remain.
- If any task status is `escalated`: STOP. Report the escalation to
  the user. **Do not write the phase-N/done tag.** The phase-N/start
  tag remains. Earlier successful phase tags are kept (no rollback).

**6d. Checkpoint and phase-done tag:**

Only after step 6c confirms tests pass and no task is escalated — i.e.
on a successful wave exit — write the phase-done tag and update state:

- Invoke the git_tags.py write-tag CLI with the name
  `etc/feature/F<NNN>/build/phase-<N>/done` at HEAD:
  ```
  python3 ~/.claude/scripts/git_tags.py write-tag "etc/feature/F<NNN>/build/phase-<N>/done"
  ```
  Use the same `F<NNN>` and `<N>` values as 6a. Same exit-code
  semantics as 6a (0 created, 1 degrade, 2 hard fault).

**6d.5: Write per-phase completion report.**

After the phase-done tag is written and before the waves_completed
state update, write a per-phase completion-report.md so
`scripts/release_notes.py` can roll it up at terminal close (Step 7.5b).
The completion-report.md lands at
`<feature_path>/build/phase-<N>/completion-report.md` and is the
canonical audit-trail artifact for this wave's outcome.

**Trigger condition:** matches the phase-done tag — only on successful
wave exit (Step 6c tests passed, no task escalated). Failed phases
produce no report; the absence of phase-N/done plus the absence of
completion-report.md is the existing failure signal.

**Source the report's content from the wave's task YAMLs:**

- `prd-title`: read the first `# PRD: <title>` heading from
  `<feature_path>/spec.md`. Fall back to the feature directory slug
  if no `# PRD:` heading is present.
- `prd-id`: read `feature_id` from `<feature_path>/state.yaml`. Fall
  back to the feature directory name (e.g., `F005-build-completion-
  reports`) if the field is absent.
- `ac-passed`: collect every `acceptance_criteria` entry from each
  task YAML in `<feature_path>/tasks/` whose `status` is `completed`
  and whose phase membership corresponds to wave N. Because the
  phase-done tag is gated on successful wave exit, every AC in the
  wave's task list is treated as passed at write time. Concatenate
  into a temp file (one AC per line); pass via `--ac-passed-file`.
- `ac-failed`: empty (the wave passed Step 6c verification before
  reaching 6d.5; no failed ACs land in this report). Pass an empty
  temp file via `--ac-failed-file`.
- `deferred`: collect any `surface_status: deferred` markers from
  the wave's task YAMLs (introduced by F003 — see
  `standards/process/user-flow-completeness.md`'s Operator-Prompt
  Fallback subsection). Concatenate into a temp file; pass via
  `--deferred-file`. If none found, write an empty file (the helper
  emits `- (none)` automatically).
- `limitations`: default to an empty file. The helper emits
  `- (none)`. The operator can hand-amend the resulting
  completion-report.md after write if known limitations should be
  recorded; the amendment lands in release-notes.md at Step 7.5b.

**Invoke the helper:**

```
python3 ~/.claude/scripts/completion_report.py write \
    --feature-dir "<feature_path>" \
    --phase <N> \
    --prd-title "<prd-title>" \
    --prd-id "<prd-id>" \
    --ac-passed-file "<temp-file-of-ac-list>" \
    --ac-failed-file "<empty-temp-file>" \
    --deferred-file "<temp-file-of-deferred-list>" \
    --limitations-file "<empty-temp-file>"
```

The CLI form is required because the helper lives at
`~/.claude/scripts/`, not the user's project — `from
scripts.completion_report import write` would only resolve inside
this etc checkout, so it MUST NOT be used.

Exit codes follow the F004 + git_tags + value_hypothesis convention
(0 created, 1 hard fault). On exit code 1, the conductor surfaces
stderr to the operator and STOPS — completion-report.md must exist
before advancing to 6d's waves_completed update.

- Update `state['build']['waves_completed'] = N` in state.yaml using
  the same merge-preserving read/mutate/write pattern from Step 2;
  the top-level /spec metadata stays untouched.
- This enables resume from the last completed wave if session dies.

**Discipline (BR-008, edge case 4):** Tags written by `git_tags.write_tag()`
are append-only. The harness never deletes, retags, or force-updates a
tag it has written. On any failure inside step 6c, the phase-N/done tag
is NOT written for the failing wave; phase-N/start tags and any
phase-M/start|done tags from earlier successful waves remain (preserved).
Resume continues from the last successfully completed wave.

**6e. Proceed to next wave or finish.**

**On escalation or test failure:**
```
⚠ Wave {N} failed.
  Failing tests: {list}
  Escalated tasks: {list}

The pipeline is paused. Options:
  1. Fix the issues and run: /build --resume
  2. Investigate with: python3 ~/.claude/scripts/tasks.py board
```

### Step 7: VERIFY (Final)

After all waves complete — i.e. the terminal phase has been closed
successfully at Step 6:

1. Run full CI: tests + coverage + types (if applicable) + lint (if applicable)
2. Run invariant checks: `INVARIANTS.md` verify commands
3. **Dispatch spec-enforcer** for adversarial AC verification:
   ```
   Agent({
     subagent_type: "spec-enforcer",
     prompt: "Verify the deliverables for feature '{slug}' against the PRD at {spec_path}. Check every acceptance criterion. For any AC containing a User-flow sentence (canonical prefix 'As {role}, navigate from'), additionally require reachability evidence per `standards/process/user-flow-completeness.md` (Reachability Evidence section). Acceptable evidence forms in preference order: E2E test that walks the navigation path, static nav-graph reference grep proof, or manual reachability proof. A unit test that imports the target component directly is necessary but NOT sufficient for a user-facing AC. Report COMPLIANT or NON-COMPLIANT with evidence."
   })
   ```
   If the spec-enforcer returns NON-COMPLIANT, the build is NOT done.
   Route the violations back to the responsible task owners for remediation
   before proceeding to Step 8. **Do not write the release tag or
   release-notes.md** while remediation is outstanding — release artifacts
   are gated on a successful terminal-phase close.
4. Write `.etc_sdlc/features/{slug}/verification.md`:

```markdown
# Verification Report — {feature name}

**Date:** {timestamp}
**Spec:** {spec path}
**Mode:** {QUICK|STANDARD|DEEP}

## Task Summary
- Total: {N} tasks ({M} leaf, {K} parent)
- Completed: {C}
- Escalated: {E}

## Acceptance Criteria
- [ ] {criterion 1} — VERIFIED by task {id}
- [ ] {criterion 2} — VERIFIED by task {id}
...

## Quality Checks
- [ ] Tests: {pass/fail} ({count} tests)
- [ ] Coverage: {N}% (threshold: 98%)
- [ ] Type checking: {pass/fail/skipped}
- [ ] Lint: {pass/fail/skipped}
- [ ] Invariants: {pass/fail/no invariants}

## Files Modified
{list of all files created or modified across all tasks}
```

5. **Write the release tag and release-notes.md (terminal phase close).**

   This step runs ONLY after items 1–4 above have all succeeded — full
   CI passing, invariants verified, spec-enforcer COMPLIANT, and
   verification.md written. These two writes are the marker of a
   successful terminal-phase close (BR-009, AC-009, AC-011).

   a. Write the release tag via the git_tags.py write-tag CLI:
      ```
      python3 ~/.claude/scripts/git_tags.py write-tag "etc/feature/F<NNN>/release"
      ```
      Substitute `F<NNN>` with the feature ID from `state.yaml`. Exit
      codes follow the same convention as Step 6 (0 created, 1 degrade
      on non-git/no-HEAD, 2 hard fault).

   b. Build and write `release-notes.md` via the release_notes.py build
      CLI. The CLI prints the rendered markdown to stdout; redirect to
      the feature directory:
      ```
      python3 ~/.claude/scripts/release_notes.py build .etc_sdlc/features/F<NNN>-<slug> > .etc_sdlc/features/F<NNN>-<slug>/release-notes.md
      ```
      Substitute `F<NNN>-<slug>` with the actual feature directory name.
      The result lands at
      `.etc_sdlc/features/F<NNN>-<slug>/release-notes.md` and rolls up
      PRD title and ID, phases closed, per-phase AC pass/fail summary
      citing each completion-report path, deferred items, and known
      limitations.

      The CLI form is required for the same reason as the git_tags.py
      invocations: helpers live at `~/.claude/scripts/`, not the user's
      project, so import-style invocation (`from scripts.release_notes
      import build`) MUST NOT be used.

   **Discipline (edge case 4).** On mid-build failure — an escalated
   wave or a failing test at Step 6c, or a NON-COMPLIANT spec-enforcer
   result at Step 7 item 3 — neither the release tag nor
   release-notes.md is written. Skip both. Phase start/done tags
   written by earlier successful waves remain in place; they are
   append-only and are not rolled back. Re-run `/build --resume` after
   remediation; Steps 7.5a and 7.5b run only on the successful
   terminal-phase close.

### Step 8: REPORT

Present final summary to user:

```
## Build Complete ✓

**Feature:** {name}
**Spec:** {path}
**Mode:** {QUICK|STANDARD|DEEP}

### Pipeline
  ✓ Step 1: Validated spec (DoR passed)
  ✓ Step 2: Feature directory created
  ✓ Step 3: Decomposed into {N} initial tasks
  ✓ Step 4: Recursive decomposition ({M} leaf tasks, max depth {D})
  ✓ Step 5: Planned {W} execution waves
  ✓ Step 6: Executed all waves
  ✓ Step 7: Verified ({T} tests pass, {C}% coverage)
  ✓ Step 8: Report

### What Was Built
{summary per task}

### Artifacts
  .etc_sdlc/features/{slug}/
    spec.md            — the PRD
    tasks/             — {N} task files
    verification.md    — quality report
    state.yaml         — pipeline state
    release-notes.md   — roll-up of phases closed, AC pass/fail, deferred items

  Git tags written under refs/tags/etc/feature/F<NNN>/:
    build/phase-<N>/start, build/phase-<N>/done — one pair per wave
    release tag: etc/feature/F<NNN>/release      — terminal phase close

### Deferred Items
{anything escalated or out of scope}
```

Update `state.yaml`: `current_step: 8`, `completed_at: {timestamp}`

---

## Resume Protocol

When invoked with `--resume`:

1. Find the most recent feature directory with an incomplete `state.yaml`
2. Read `current_step` and `waves_completed`
3. Report: "Resuming {feature} from Step {N}, Wave {M}"
4. Continue from the next uncompleted step

If no incomplete features found: "No build in progress. Start with: /build spec/prd.md"

## Constraints

- You NEVER skip steps. The pipeline is sequential and checkpointed.
- You NEVER proceed past a failed wave. Stop and report.
- You NEVER issue an Agent-tool call for a task whose complexity score
  is > 7. Decompose it via Step 4 first.
- You ALWAYS wait for user confirmation before entering Step 6.
- You ALWAYS write `state.yaml` at each step completion for resume
  capability.
- You ALWAYS write `verification.md` before reporting success in
  Step 8.
- If context utilization exceeds 60%, suggest `/checkpoint` then
  `/compact`.

## Post-Completion Guidance

After a successful build, prompt the user:

```
Build complete. All {N} tests pass, {C}% coverage.

This feature is ready to commit. Next steps:
  • Review the changes: git diff
  • Commit when satisfied
  • If you find issues later: /postmortem to trace and prevent recurrence
  • Ready to build something else? /spec "your next idea"
```

After a failed build (escalation or test failure):

```
Build paused at Wave {N}. {reason}

Options:
  • Fix the issue, then: /build --resume
  • Review the task board: /tasks board
  • Check what's blocking: /tasks deps {task_id}
  • If you need to rethink: /spec to revisit the specification
```

After a wave completes mid-pipeline:

```
Wave {N} of {total} complete. {M} tasks done, {K} remaining.
Tests passing. Proceeding to Wave {N+1}...
```

## Definition of Done

The `/build` pipeline is done for a given feature when ALL of the
following observable artifacts exist and pass:

1. `.etc_sdlc/features/{slug}/state.yaml` exists with
   `current_step: 8` and a non-null `completed_at` timestamp.
2. `.etc_sdlc/features/{slug}/spec.md` exists (copied from the input
   spec path, if different).
3. `.etc_sdlc/features/{slug}/tasks/` contains one YAML file per leaf
   task, each with `status: completed` (no `in_progress` or
   `escalated` remaining).
4. `python3 ~/.claude/scripts/tasks.py list --tree` shows every leaf
   task with status `completed` and a complexity score <= 7.
5. `python3 -m pytest --tb=short -q` passes with zero failures.
6. If `INVARIANTS.md` exists at the repo root, every invariant-verify
   command it lists has been run and returned exit code 0.
7. An adversarial `spec-enforcer` subagent has been dispatched via
   the Agent tool against the spec and returned `COMPLIANT`. A
   `NON-COMPLIANT` result means the feature is NOT done; remediation
   tasks must be dispatched and the check re-run.
8. `.etc_sdlc/features/{slug}/verification.md` exists with every
   checklist item under "Acceptance Criteria" and "Quality Checks"
   marked passing (or explicitly marked `skipped` with a stated
   reason).
9. The Step 8 summary has been rendered to the user.

If any of the nine items is not satisfied, the build is NOT done,
regardless of how many steps reported success individually. Do not
report "Build Complete" unless every item holds.
