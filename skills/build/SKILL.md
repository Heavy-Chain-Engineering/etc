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
/build .etc_sdlc/features/auth/spec.md --autonomous          # F014: drive via /goal, skip operator prompts
/build .etc_sdlc/features/auth/spec.md --autonomous --max-turns 75
/build .etc_sdlc/features/auth/spec.md --autonomous --goal-condition "<override>"
```

## Autonomous Mode (F014)

When invoked with `--autonomous`, /build wraps Anthropic's `/goal` feature
to drive the pipeline unattended. Behavior changes:

1. **Step 2 (SETUP)** derives a goal condition from `state.yaml` and the
   spec's AC count, then invokes `/goal <condition>`. The Haiku evaluator
   then checks every turn whether Claude has surfaced evidence the
   condition holds.
2. **Step 3 (DECOMPOSE)** SKIPS the Pattern A "Task breakdown looks
   right?" `AskUserQuestion`. Auto-proceeds to scoring.
3. **Step 5 (PLAN WAVES)** SKIPS the Pattern A "Proceed with wave
   execution?" `AskUserQuestion`. Auto-proceeds with the equivalent of
   "Execute all waves".
4. **Step 7 (VERIFY)** NON-COMPLIANT routes through the existing
   remediation path without operator pause — /goal's
   evaluator-after-each-turn drives the loop until COMPLIANT or
   max-turns exhausts.
5. **Terminal-phase close** (after release tag write) clears the goal
   via `/goal --clear` (or the equivalent skill invocation) so a
   follow-up session does not inherit a stale autonomous loop.

**Goal condition (auto-derived):**

```
F<NNN> spec-enforcer returns COMPLIANT for feature <feature_id>;
all <N> ACs in <feature_path>/spec.md are SATISFIED;
git tag etc/feature/F<NNN>/release exists;
pytest reports 0 failures;
feature directory at .etc_sdlc/features/shipped/F<NNN>-<slug>/.
```

Operator override: `--goal-condition "<custom condition>"`.

**`--max-turns N`** bounds runaway loops. Default 50. Hard cap 200
regardless of operator override — beyond 200 turns the model has almost
certainly diverged and operator intervention beats further looping.

**`--autonomous --resume`** reuses the original goal condition from
`state.yaml.build.autonomous.goal_condition`. Does NOT re-derive.

**`disableAllHooks: true` in managed settings** disables /goal; in that
case `/build --autonomous` falls back to interactive mode with a warning
to stderr rather than hard-failing.

**`state.yaml.build.autonomous` schema** (written at Step 2 when this
mode is engaged):

```yaml
build:
  autonomous:
    mode: autonomous              # or 'interactive' (default)
    max_turns: 50
    goal_condition: "<derived or override string>"
    started_at: "<iso8601>"
```

The `mode` field gates the per-step Pattern A skip logic. `--resume`
reads this block to know whether to skip prompts on resume.

**`state.yaml.build.cross_feature_collisions` schema (F016 R2):**
populated by Step 5 when the cross-feature collision detector returns
exit 2. Each entry records one colliding file plus the in-flight
features that claim it:

```yaml
build:
  cross_feature_collisions:
    - file: src/shared.py
      other_features: [F101, F102]
    - file: tests/test_shared.py
      other_features: [F101]
```

When empty or absent, the build had no detected cross-feature
collisions at wave-plan time.

**`state.yaml.build.submission` and `state.yaml.build.merged` schemas
(F016 R7):** documented for use by future features. F016 only
documents the schema slot; auto-population is deferred.

```yaml
build:
  submission:
    submitted_at: "<iso8601>"
    submitted_by: "<operator>"
    target_branch: "internal/main"   # or equivalent submission target
    pr_url: "<URL or null for non-PR pushes>"
  merged:
    merged_at: "<iso8601>"
    merged_by: "<human>"             # explicitly human, not agent
    commit_sha: "<sha>"
```

The submission/merged distinction mirrors the Stripe Minions pattern:
the agent **submits** work (push to internal/main); a **human merges**
to the public target. Etc enforces this via the standing rule that
agents never push to `origin/main`. F016 documents the schema so
future features can wire up the audit trail.

## The Pipeline

```
VALIDATE → SETUP → DECOMPOSE → SCORE/RECURSE → PLAN WAVES → EXECUTE → VERIFY → REPORT
   1         2         3            4               5           6         7        8
```

Each step writes state to the feature directory. If the session dies, compacts,
or is interrupted, `/build --resume` picks up from the last completed step.

---

<!-- forward-only: /build --extend lifecycle enforced from F025 release tag onward -->

### Step A: EXTEND lifecycle (F025) — post-ship refinement lane

`/build --extend "<problem>"` is the refinement lane for **already-shipped**
features. When the `--extend` flag is present on the `/build` invocation, the
conductor switches into the EXTEND lifecycle below (Steps A1–A14) INSTEAD OF
running Step 1 (VALIDATE). When the flag is absent, `/build` behaves
identically to its pre-F025 shape — Step 1 runs as normal and Step A is
skipped entirely.

**CLI shape:**

```
/build --extend "<problem>" [--feature F<NNN>] [--triage light|medium|heavy]
```

- `<problem>` (required) — free-text operator description of the refinement
  (e.g., "the SettingsPage uses shadcn but the rest uses radix; swap it").
  Empty string → reject with "Problem statement required" and exit non-zero.
- `--feature F<NNN>` (optional) — target a specific shipped feature by ID.
  When omitted, the resolver picks the most-recently-shipped feature.
- `--triage light|medium|heavy` (optional) — operator override of the
  rule-based triage classifier. Invalid values → reject with "Unknown
  triage value '<v>'. Valid: light, medium, heavy." and exit non-zero.

**Lifecycle anchor:** `shipped/` is a state, not a one-way door. For Light
and Medium triage outcomes, the feature dir moves shipped→active for the
duration of the extension, then back to shipped on re-close (Step A13).
Each successful extend cuts a new versioned release tag
(`etc/feature/F<NNN>/release_<extend_id>`); the original
`etc/feature/F<NNN>/release` tag is never modified or deleted (append-only,
F021 BR-008 inherited).

**Composition with prior features:** F019 (audit-log surface, new
`event_type: "extend_dispatch"`), F021 (append-only tag discipline), F022
(`shutil.move` fallback for gitignored shipped↔active moves), F023 (POSIX-
atomic allocate-next + Ftmp-style 8-hex shape rhymes with the extension ID),
F024 (conditional system-overlay injection inherited by extend dispatches).

**Helper script:** `scripts/extend_resolver.py` exposes the CLI subcommands
this step invokes (`generate-id`, `resolve-target`, `classify`, `reopen`,
`record-extend`, `complete-extend`, `close`). The conductor invokes each via
Bash; this skill body does NOT inline the helper's implementation. See
`standards/process/build-extend.md` for the full operator-facing convention.

---

**Step A1: Parse `<problem>` + `--feature` + `--triage` flags.**

Validate the operator's invocation arguments BEFORE touching the filesystem
or generating any IDs. Empty `<problem>` strings, malformed feature IDs
(reject anything not matching `^F\d{3}$`), and invalid `--triage` values
exit non-zero with a clear message. No state changes.

**Step A2: Resolve the target shipped feature.**

```bash
target_dir=$(python3 ~/.claude/scripts/extend_resolver.py resolve-target \
    --etc-sdlc-root .etc_sdlc \
    [--feature F<NNN>])
```

The resolver returns the absolute path to the target shipped feature's
directory under `.etc_sdlc/features/shipped/F<NNN>-<slug>/`. When
`--feature` is omitted, it picks the most-recently-shipped (by
`completed_at` in `state.yaml`). Exit codes:

- **0** = target resolved; continue.
- **1** = no shipped features (EC-001) OR `--feature F<NNN>` not found
  anywhere under `features/{active,shipped,rejections}/` (EC-002) OR the
  named feature is in `active/` rather than `shipped/` (EC-003). Surface
  stderr verbatim to the operator and abort. No state changes.

**Step A3: Classify the problem against the target's context-pack.**

```bash
triage=$(python3 ~/.claude/scripts/extend_resolver.py classify \
    --problem "<problem>" \
    --target-dir "$target_dir")
```

Returns one of `light | medium | heavy` per the rule-based rubric (file-path
detection + architectural-keyword scan). When the operator passed
`--triage`, that value REPLACES the classifier's output as the effective
triage outcome — record both (classifier-emitted vs. operator-override) on
the audit-log row at Step A8.

**Step A4: Heavy-triage refusal path (AC-003, BR-003).**

If the effective triage is `heavy` AND the operator did NOT pass `--triage`
(i.e., the classifier itself returned heavy with no operator override), the
conductor MUST refuse the extend. Emit the following message to stderr —
the literal substring `scope creep, not a refinement` is required verbatim
(the AC-003 contract greps for it):

> This problem reads as scope creep, not a refinement. The harness will
> not silently expand a shipped feature with architectural-impact work.
> Run `/spec '<your problem>'` to file a fresh feature with proper
> Socratic refinement + architect handoff. If you believe this IS
> refinement (not scope creep), re-invoke with
> `/build --extend --triage medium '<problem>'` to override.

Exit non-zero. NO state changes — no directory move, no `state.yaml.extends`
append, no extension ID generation, no audit-log emission, no release tag.
The refusal is the entire outcome.

When the operator explicitly passes `--triage heavy` (acknowledged override),
Step A4 does NOT fire and the conductor proceeds to Step A5 — the operator
has taken the audit-trail responsibility for the override.

**Step A5: Generate the extension ID.**

```bash
extend_id=$(python3 ~/.claude/scripts/extend_resolver.py generate-id)
```

Returns an 8-char hex string (`^[0-9a-f]{8}$`), time-ordered (sortable
lexicographically by creation time), stdlib-only, collision-free across
machines. Mirrors F023's `Ftmp-<8-hex>` shape so the audit-trail format
rhymes.

**Step A6: Reopen the feature — move shipped → active (BR-004).**

```bash
active_dir=$(python3 ~/.claude/scripts/extend_resolver.py reopen \
    --target-dir "$target_dir" \
    --etc-sdlc-root .etc_sdlc)
```

Moves `.etc_sdlc/features/shipped/F<NNN>-<slug>/` to
`.etc_sdlc/features/active/F<NNN>-<slug>/` via F022's `shutil.move`
fallback (gitignored-safe; path-traversal-rejected). On `shutil.Error`
(destination already exists per EC-004 — concurrent extends from a second
machine), surface stderr and abort. The second operator retries after the
first extend completes.

**Step A7: Record the extend on `state.yaml` (BR-005).**

```bash
python3 ~/.claude/scripts/extend_resolver.py record-extend \
    --target-dir "$active_dir" \
    --extend-id "$extend_id" \
    --problem "<problem>" \
    --triage "$triage" \
    --dispatched-agents "<comma-list>"
```

Appends a new entry to `state.yaml.extends` (creating the field if absent —
BR-012 forward-only):

```yaml
extends:
  - extend_id: "<extend_id>"
    problem: "<verbatim problem string>"
    triage: light | medium | heavy
    started_at: <ISO-8601 UTC now>
    completed_at: null            # set at Step A10
    release_tag: null              # set at Step A10
    dispatched_agents: [<roles>]
```

Append-only. Pre-existing `extends:` entries from earlier extensions are
preserved byte-equivalent (EC-007). The original `build:` block,
`id_history`, `spec_phase`, `architect_phase`, and any other top-level keys
are NOT mutated.

**Step A8: Emit the audit-log row (BR-009).**

Append one row to `.etc_sdlc/efficiency/turn-events.jsonl` (F019 surface):

```json
{"ts": "<ISO-8601 UTC>",
 "event_type": "extend_dispatch",
 "feature_id": "F<NNN>",
 "extend_id": "<extend_id>",
 "triage": "<effective triage>",
 "problem_truncated_80": "<first 80 chars of problem>",
 "dispatched_agents": ["<role>", ...],
 "started_at": "<ISO-8601 UTC>"}
```

Write failures degrade silently per F019 best-effort surface (EC-009). The
extend itself proceeds regardless.

**Step A9: Dispatch the refinement work.**

Branch on the effective triage outcome:

- **Light triage** — Skip `/spec` and `/architect` entirely. The target's
  existing `spec.md`, `design.md`, `gray-areas-*.md`, ADRs, and
  `value-hypothesis.yaml` are the context-pack; the operator's `<problem>`
  text is the delta. Decompose the problem into ≤3 tasks (1 wave),
  parallel-isolatable by file-set. Dispatch via the Agent tool one
  invocation per task, following the Subagent Dispatch (Non-Negotiable)
  rules from the top of this skill body. Each dispatch prompt is
  constructed per `standards/process/subagent-dispatch.md` — the
  per-invocation delta cites the target feature's existing artifacts as
  required reading; the original `spec.md` and `design.md` are the
  intent substrate. Run Step 6c's per-wave verify-green gate; route any
  NON-COMPLIANT result through the existing remediation path. Do NOT
  re-invoke Step 1 — the spec has already been DoR-passed once.

- **Medium triage** — Run a micro-`/spec` (2-3 Socratic questions, not the
  full 6 from `skills/spec/SKILL.md`) targeting ONLY the deltas the
  `<problem>` introduces. The micro-spec output amends — does NOT replace
  — the target's existing `spec.md` (append a `## Extension <extend_id>`
  sub-section with the new ACs, if any). Re-decompose into 1-2 waves;
  dispatch per Step 6's wave-by-wave loop above. Run Step 6c's verify-green
  per wave. Same remediation routing as Light.

- **Heavy triage with operator override** — Same dispatch shape as Medium
  (micro-spec → decompose → waves), but record `triage: heavy` on the
  `state.yaml.extends` entry so the audit trail shows the override was
  conscious. `/metrics` (future) MAY surface override-heavy extends for
  operator review.

The dispatched subagents inherit F024's conditional system-overlay
injection — extend dispatches get the same onboarding as fresh dispatches,
no special-case wiring.

**Step A10: Complete the extend on `state.yaml`.**

After every dispatched task returns and the wave(s) pass Step 6c
verify-green AND a spec-enforcer COMPLIANT result (Step 7 item 3 still
applies to extend dispatches — the original `spec.md` + the optional
extension sub-section together are the verification target), close the
extension:

```bash
python3 ~/.claude/scripts/extend_resolver.py complete-extend \
    --target-dir "$active_dir" \
    --extend-id "$extend_id" \
    --release-tag "etc/feature/F<NNN>/release/$extend_id"
```

Sets `state.yaml.extends[N].completed_at = <now>` and
`state.yaml.extends[N].release_tag = etc/feature/F<NNN>/release_<extend_id>`.
On extend-failure (subagent escalates, verify-green non-zero, spec-enforcer
NON-COMPLIANT not remediated), `completed_at` STAYS null and the feature
stays in `active/` per BR-010 (operator remediates manually + re-runs
`/build --resume`; matches F022's three-branch failure shape).

**Step A11: Write the versioned release tag (BR-007).**

```bash
python3 ~/.claude/scripts/git_tags.py write-tag \
    "etc/feature/F<NNN>/release/$extend_id"
```

The original `etc/feature/F<NNN>/release` tag is NEVER modified or deleted
(append-only per F021 BR-008). Both tags exist after a successful extend
and both name distinct commits — the original at the post-Step-7c.1 close
HEAD, the extension at the post-Step-A10 close HEAD.

**Step A12: Append to `release-notes.md` (BR-008).**

Invoke the F025-aware `scripts/release_notes.py` to add an append-only
`## Extensions` section (or `### Extension <extend_id>` sub-section if the
section already exists):

```bash
python3 ~/.claude/scripts/release_notes.py build "$active_dir" \
    > "$active_dir/release-notes.md"
```

Pre-existing content is preserved byte-equivalent (AC-008 contract). The
new sub-section includes: extend ID, triage, date, problem (verbatim),
dispatched agents, AC pass/fail outcome, release tag.

**Step A13: Close the extension — move active → shipped.**

```bash
python3 ~/.claude/scripts/extend_resolver.py close \
    --target-dir "$active_dir" \
    --etc-sdlc-root .etc_sdlc
```

Moves the feature dir back from `active/` to `shipped/` via the same
three-branch failure shape used at Step 7c.1 (`git mv` preferred,
`shutil.move` fallback for gitignored repos). The feature is now
re-frozen at its terminal audit-frozen state — until the next `--extend`
reopens it. Endpoint discipline (BR-010): a reopened extension MUST
eventually reach Step A13; in-flight extends are surfaced by `/metrics`.

**Step A14: Report the extend outcome.**

Render a Step 8-shape summary scoped to the extension:

```
## Extend Complete

**Feature:** F<NNN> — <slug>
**Extension:** <extend_id>
**Triage:** <light | medium | heavy>
**Problem:** <verbatim>

### Pipeline
  ✓ Step A1–A4: parsed, resolved, classified, refusal-checked
  ✓ Step A5–A8: ID generated, reopened, recorded, audit-logged
  ✓ Step A9:    dispatched <K> task(s) in <W> wave(s)
  ✓ Step A10:   completed-at recorded
  ✓ Step A11:   release tag etc/feature/F<NNN>/release_<extend_id> written
  ✓ Step A12:   release-notes.md ## Extensions section appended
  ✓ Step A13:   feature re-closed to shipped/

### Artifacts
  .etc_sdlc/features/shipped/F<NNN>-<slug>/release-notes.md  — Extensions section
  refs/tags/etc/feature/F<NNN>/release_<extend_id>            — extension tag
  .etc_sdlc/efficiency/turn-events.jsonl                      — extend_dispatch row
```

Update `state.yaml.extends[N]` to reflect the final fields (already done at
Step A10). The conductor does NOT re-render Step 1–8 summary content — Step
A14 is the extension's terminal report and the original Step 8 summary for
the parent feature remains unchanged.

**EXTEND lifecycle exits here. The conductor does NOT fall through to Step 1.**

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

**Step 1c: Engineering-implication detection (design.md soft-coupling check).**

This sub-step is additive on top of Steps 1a–1b and runs AFTER Step 1b
has resolved (whether via the /spec rubber-stamp path or the inline DoR
check). It implements the soft default declared by F006 GA-008: `/spec`
and `/architect` are coupled by recommendation, not by hard requirement,
so `/build` warns when engineering work appears unaccompanied by a
design but does NOT block.

**Detection.** Scan `spec.md` for engineering-signal tokens (the same
list documented in F006 BR-002 for /spec's Phase 5 auto-detect):

- **File paths** matching the regex `[a-z][a-z0-9_/.-]+\.(py|ts|tsx|md|sh|yaml|yml)`
  (case-sensitive on the extension).
- **Identifier patterns** — camelCase or snake_case identifiers paired
  with `import`, `use`, `extend`, or equivalent verbs in the same
  sentence.
- **HTTP method tokens** (`GET`, `POST`, `PUT`, `PATCH`, `DELETE`)
  appearing alongside `/api/` substrings or route patterns.
- **DB schema language** — the literal tokens `table`, `column`,
  `index`, or `migration` appearing in a structural context (not in
  prose like "table of contents").
- **User-flow sentences** matching F001's canonical prefix pair (`As `
  followed later in the same sentence by `, navigate from`).

**Presence check.** Look for `design.md` in the same feature directory
that contains the spec.md being built (i.e.,
`.etc_sdlc/features/{slug}/design.md`).

**Decision matrix:**

- **Engineering signals present AND `design.md` absent.** Default
  outcome: emit the soft warning below to stderr and PROCEED to Step 2.
  Step 1c is non-blocking under the soft default.

  Emit this EXACT warning text to stderr (the test contract greps for
  the verbatim string — do not paraphrase, reflow, or otherwise mutate
  it):

  ```
  WARNING: spec.md implies engineering work but design.md is absent. Consider running /architect first. Proceeding with build using spec.md alone.
  ```

- **Engineering signals present AND `design.md` absent AND
  `state.yaml.spec_phase.architect_recommendation == "yes-and-mark-design-mandatory"`.**
  The operator opted into stricter coupling at /spec's Phase 5
  auto-detect (per F006 BR-002). Step 1c HARD-fails: STOP, do not
  proceed to Step 2, and report:

  > Spec was marked design-mandatory at /spec time but design.md is absent.
  > Run /architect on this feature, then re-invoke /build.

- **Engineering signals present AND `design.md` present.** No warning;
  proceed to Step 2. Step 6 dispatch will include design.md content
  alongside spec.md (see Step 6).
- **No engineering signals detected.** No warning; proceed to Step 2.
  /build does not require design.md for non-engineering features.

**Forward-only posture.** Step 1c fires for every spec, including
F001-F009 legacy specs that predate the /architect skill. On those
specs, the warning is cosmetic — the operator is informed but build
proceeds as before (per F006 edge case 9). The hard-fail variant
above triggers only when /spec wrote the explicit
`yes-and-mark-design-mandatory` recommendation into state.yaml; legacy
state.yaml files without a `spec_phase` block fall through to the soft
warning path.

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
    'stacked': None,  # bool, set at Step 5 once total_waves is known:
                      # True when total_waves > 1 (stack layers emitted
                      # per wave); False when total_waves == 1 (single-wave
                      # bypass per F010 BR-005). Legacy state.yaml files
                      # without this field are treated as stacked=false
                      # (F010 BR-008 forward-only). Merge-preserved across
                      # every later state-write — the field name 'stacked'
                      # is part of the build dict shape.
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

**Autonomous-mode setup (F014):** When `/build` was invoked with
`--autonomous`, also write `state['build']['autonomous']` per the
schema documented in the Autonomous Mode section above (`mode`,
`max_turns`, `goal_condition`, `started_at`). Then dispatch `/goal
<condition>` via the Skill tool to register the completion condition
with Claude Code's evaluator. The goal condition is derived
deterministically from `state.yaml` and spec.md AC count, or taken
verbatim from `--goal-condition` if the operator overrode the default.

If `disableAllHooks: true` is detected in the operator's managed
settings, `/goal` is unavailable; emit a single stderr warning
(`WARNING: --autonomous requested but /goal is disabled by managed
policy; falling back to interactive mode.`), set
`state['build']['autonomous']['mode'] = 'interactive'`, and proceed as
if `--autonomous` had not been passed.

`--max-turns` defaults to 50; operator overrides are capped at 200
regardless of the value passed. Beyond 200 turns the model has almost
certainly diverged and operator intervention is more productive than
further looping.

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
Print the tree so the user can see it.

**Autonomous-mode skip (F014):** When `state.yaml.build.autonomous.mode == "autonomous"`,
SKIP the AskUserQuestion below entirely. Auto-proceed to Step 4 as if the operator
had selected "Yes, proceed to scoring". The /goal evaluator will judge whether the
breakdown was correct by checking AC satisfaction at Step 7. Log a single line:
`Step 3 confirmation auto-accepted (autonomous mode).`

Then ask for confirmation using `AskUserQuestion` (see
standards/process/interactive-user-input.md, Pattern A):

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

**Cross-feature collision check (F016 R2):** Run the collision detector
after the wave plan is printed and BEFORE the operator confirmation. The
detector compares the current feature's `files_in_scope` against every
other in-flight feature's:

```bash
python3 ~/.claude/scripts/cross_feature_collision_check.py \
    .etc_sdlc/features/F<NNN>-<slug>
```

Exit codes: 0 = no collisions, 2 = collisions detected, 1 = usage/IO error.

- **Exit 0:** proceed to the wave-execution confirmation below.
- **Exit 2:** present the structured collision report (script writes it to
  stdout) and surface a new Pattern A `AskUserQuestion` with three
  options: **Cancel** (stop /build; coordinate with the other features),
  **Proceed with risk acknowledged** (operator owns the eventual merge
  resolution), **Serialize via dependency** (add a task dependency so
  this feature builds AFTER the colliding feature completes).
- **Exit 1:** treat as hard fault; surface stderr to operator.

**Under `--autonomous` mode (F014):** collision check still runs. On
exit 2: log the collisions to stderr, write
`state.yaml.build.cross_feature_collisions: [...]` with the collision
report, and auto-select "Proceed with risk acknowledged". The autonomous-
mode philosophy is "fail forward + audit-trail," not "halt for human."

**Autonomous-mode skip (F014) for wave execution confirmation:** When
`state.yaml.build.autonomous.mode == "autonomous"`, SKIP the
AskUserQuestion below entirely. Auto-proceed with the equivalent of
"Execute all waves" (the Recommended option). Log a single line:
`Step 5 confirmation auto-accepted (autonomous mode).`

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

**Dispatch prompt construction:** follow `standards/process/subagent-dispatch.md`.
The dispatch prompt is the per-invocation delta — Feature intent (lifted from
spec.md Summary), Task intent (from task YAML if present), required reading
(paths + ≤8-word commentary), files in scope, ACs verbatim, cross-task
awareness, report-back format. Do NOT restate TDD, hooks-enforce, no-emoji,
or architectural constraints already in design.md — those live in the system
overlay and role manifest. Target: ≤1,000 tokens per dispatch.

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
- **spec.md + design.md briefing context (F006 BR-005).** The
  briefing prompt's spec-content section embeds the contents of
  `.etc_sdlc/features/{slug}/spec.md` so the dispatched subagent has
  the intent in front of it. When
  `.etc_sdlc/features/{slug}/design.md` ALSO exists in the same
  feature directory (i.e., the feature went through /architect per
  F006), the orchestrator MUST additionally embed design.md's
  contents alongside spec.md in the briefing prompt — clearly
  delimited so the subagent can tell which artifact is which (intent
  vs. architecture). Both artifacts are read-at-dispatch-time so the
  subagent sees the latest committed versions. When design.md is
  absent, the prompt embeds spec.md alone (the legacy F001-F009 shape
  and the soft-default path from Step 1c). The rest of the per-task
  briefing structure — task YAML path, requires_reading,
  files_in_scope, acceptance criteria, and the hooks reminder — is
  unchanged by this rule.
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

**Quality gate (per-wave, profile-dispatched) — F021 BR-003 + BR-004.**
After per-wave tests pass and before the `phase-N/done` tag is written,
invoke the F020 profile-aware dispatcher against the wave's working tree:

```bash
printf '{"cwd":"%s"}' "$CWD" | bash hooks/verify-green.sh
```

Inherits F020 exit semantics (per ADR-F021-004 — read-only inheritance,
no modifications to verify-green.sh): exit 0 = pass (or no-profile
warn-and-skip per ADR-F020-003); non-zero = quality-tool failure.
**Zero-tolerance contract per F021 BR-004:** any non-zero exit fails the
wave. The conductor MUST NOT write the `phase-N/done` tag. Surface
verify-green's stdout and stderr verbatim to the operator in the wave's
`verification.md` (Step 7), and STOP. There is NO threshold-based,
delta-based, or count-based exception; "the wave produced fewer errors
than the previous wave" is not a passing condition. Zero is zero. No
exception flag is offered or accepted — by design, per ADR-F021-003.
Pre-existing errors in the project are the operator's responsibility to
resolve before the first `/build` invocation (BR-005); once etc is
installed, no quality-tool error is ever permitted to ship through a
wave boundary.

See `standards/process/diagnostic-discipline.md` for the full rule and
ADR-F021-003 + ADR-F021-005 for the design rationale.

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

**6d.7: Emit stack layer (F010).**

After 6d's phase-N/done tag AND 6d.5's completion-report both succeed,
emit the wave's diff as a distinct GitHub PR stack layer via `gh-stack`.
Tag FIRST (6d) so the append-only tag captures the wave's close even if
6d.7 fails; 6d.7 runs AFTER, never before.

**Single-wave bypass (BR-005, AC7).** If `total_waves == 1`, SKIP 6d.7
entirely. Set `state['build']['stacked'] = false` (merge-preserve pattern
from Step 2) and fall through to 6e. Multi-wave builds (`total_waves > 1`)
set `state['build']['stacked'] = true` and proceed.

**Layer branch naming (BR-003, AC4).** Branches: `<feature-slug>-L<N>`,
slug from `state.yaml.build.feature`, `<N>` is 1-indexed wave number.
Example: F010 wave 0 → `stacked-prs-from-build-L1`. Verbatim regex:

```
^[a-z][a-z0-9-]+-L[0-9]+$
```

Sanitization: characters outside `[a-z0-9-]` are replaced with `-` and
the slug is lowercased at branch-creation time. On-disk slug unchanged.

**Squash-commit (GA-002).** Collect the wave's modified files and
squash-commit on the new branch `<feature-slug>-L<N>`. Base: previous
layer branch when `N > 1`, or `main` when `N == 1`. One squash-commit
per wave matches F005's one-report-per-wave + F008's wave-as-isolation.

**gh-stack invocation (BR-002, AC3).** Argv-list `subprocess.run` —
never shell string — mirrors F008's `git mv` precedent:

```python
import subprocess
result = subprocess.run(
    ["gh", "stack", "push", "--base", "<previous_layer_branch>"],
    capture_output=True, text=True,
    cwd="<feature_repo_worktree>",
)
```

`<previous_layer_branch>` = `<feature-slug>-L<N-1>` (or `main` when `N==1`).
No auto-push (BR-010); operator runs `gh stack submit` after terminal close.

**Soft LOC warning (BR-004, AC5).** Compute `net_loc = additions + deletions`
from `git diff --shortstat` (use `abs(net_loc)` so deletion-only waves
warn too — edge case 2). When `net_loc > 500`, emit this VERBATIM line
to stderr (the test contract greps for prefix `WARNING: layer L`):

```
WARNING: layer L<N> contains <K> LOC (target: 500). Consider splitting the wave for review tractability. Proceeding with stack emission.
```

Non-blocking. The 500 threshold is a module-level constant
`LAYER_LOC_SOFT_TARGET = 500` in the implementing script — future tuning
is a one-line edit; never inline `500` at the check site.

**Failure semantics (edge cases 3, 5).** If `git commit` non-zero OR
`gh stack push` non-zero, STOP. Do NOT proceed to 6e. Write
`state['build']['stacked_failure'] = <wave_num>` for `--resume`. The
phase-N/done tag from 6d remains. Surface stderr verbatim. /build does
NOT degrade to monolithic-PR mode silently.

**Empty wave (edge case 1).** Zero file changes → skip layer emission;
log `note: wave <N> produced no file changes; skipping layer emission`.
Layer `N-1` remains the head; subsequent layers base off `N-1`.

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

4.4. **Step 7.4: Journey lineage gate (F017).**

   This sub-step runs AFTER `verification.md` is written (item 4) and
   BEFORE the F015 spec→ADR coupling gate (item 4.5). It enforces that
   every feature filed after F017 ships traces to either a captured
   customer journey OR an explicit infrastructure-only declaration.

   Invocation:

   ```bash
   python3 ~/.claude/scripts/journey_lineage_check.py \
       .etc_sdlc/features/F<NNN>-<slug>
   ```

   Exit codes:
   - **0** = lineage OK (journey_refs resolve to journey files OR
     infrastructure_only sentinel is set with a non-empty reason OR
     feature predates F017 release tag). Proceed to Step 4.5.
   - **2** = lineage missing. STOP. Do NOT proceed to Step 4.5, the
     release tag, or release-notes.md. Do NOT move the feature to
     `shipped/`. The script emits a JOURNEY LINEAGE MISSING stdout
     report with remediation options.
   - **1** = usage / IO error. Surface stderr to user.

   **Two paths to pass the gate (per F017 spec):**

   - **Customer-facing path:** `state.yaml.spec_phase.journey_refs:
     [J-NNN, ...]` lists one or more journey IDs, each resolving to
     `docs/mvp/journeys/J-NNN-*.md`. /spec Phase 1's seventh question
     (journey lineage) is how this gets populated.
   - **Infrastructure path:** `state.yaml.spec_phase.infrastructure_only:
     true` + `state.yaml.spec_phase.infrastructure_reason: "<one-line>"`
     is set. The reason must be non-empty (gate exits 2 if empty even
     with the sentinel set).

   **Backward compatibility (F017 BR):** features filed BEFORE the F017
   release tag (`etc/feature/F017/release`) pass automatically. The
   script reads `state.yaml.spec_phase.completed_at` and compares against
   the tag's commit date via `git log -1 --format=%cI <tag>`. Legacy
   F001-F016 features stay green; only post-F017 features are gated.

   **Operator override:** `--skip-journey-check="<reason>"` (the reason
   MUST be non-empty). The reason is appended to `verification.md` and
   `release-notes.md` under a "Journey Lineage Gate" subsection so the
   audit trail is preserved. Empty reason → exit 1. Same discipline
   pattern as F015's `--skip-spec-coupling-check`.

   **Autonomous mode (F014) interaction:** under `--autonomous`, the
   gate still runs. Exit-2 routes through the existing Step 7
   remediation path under the /goal evaluator loop — the evaluator
   reads the structured report and dispatches /journey capture (or
   state.yaml infrastructure_only declaration) as the remediation
   work, then the gate re-runs on the next `/build --resume` iteration.

   **Authored journey capture (operator-facing):** if the gate fails
   on a customer-facing feature with no captured journey, the operator
   invokes `/journey` to capture one, then updates state.yaml's
   `journey_refs` to reference the new J-NNN, then resumes /build.

4.5. **Step 7.5: Spec→ADR coupling gate (F015).**

   This sub-step runs AFTER `verification.md` is written (item 4) and
   BEFORE the release tag is written (item 5). It is a blocking gate:
   if any scope-change marker in `spec.md` (or `design.md` if present)
   is anchored to an AC/BR/ADR reference AND not covered by either a
   decision memo at `.etc_sdlc/features/{slug}/decisions/*.md` OR an
   ADR appendix at `docs/adrs/*.md` (with a "Scope clarification",
   "scope-narrowed", or "appendix" phrase), the gate fires.

   Invocation:

   ```bash
   python3 ~/.claude/scripts/spec_coupling_check.py \
       .etc_sdlc/features/F<NNN>-<slug>
   ```

   Exit codes:
   - **0** = all findings covered (or no findings). Proceed to item 5.
   - **2** = uncovered findings. STOP. Do NOT write the release tag.
     Do NOT write `release-notes.md`. Do NOT move the feature to
     `shipped/`. The script emits a structured stdout report with
     each uncovered finding's `file:line` reference + AC/BR/ADR
     tokens + remediation hints. Route the findings to the relevant
     task owners (or to the operator) for decision-memo authoring,
     then re-run `/build --resume`.
   - **1** = usage/IO error. Treat as a hard fault; surface stderr to
     the user.

   **Marker detection is AC-number-anchored** (F015 BR-003): a marker
   word counts as a finding only when it appears in the same
   paragraph/bullet as an `AC-\d+`, `BR-\d+`, or `ADR-\d+` reference,
   OR a backtick-quoted spec phrase. Bare narrative use is excluded.
   Markers inside fenced code blocks and inside literal "Out of Scope"
   / "Not in Scope" section headers are also excluded. When the
   `etc/feature/F<NNN>/spec/done` git tag exists, the detector diffs
   current spec.md against the tag and flags only markers added since;
   pre-existing markers from the original spec are excluded.

   **Operator override:** `--skip-spec-coupling-check="<reason>"` (the
   reason MUST be non-empty). The reason is appended to
   `verification.md` and `release-notes.md` under a "Spec Coupling Gate"
   subsection so the audit trail is preserved. `--skip-spec-coupling-check`
   with no value or empty string → exit 1 with an error. This flag is
   intended for legacy specs predating F015 or for genuinely-defensible
   skip cases; routine use defeats the gate's discipline (see F007+F008
   trust-chain lesson in `memory/feedback-stub-detection-gates.md`).

   **Autonomous mode (F014) interaction:** when `--autonomous` is set,
   this gate still runs. An exit-2 result routes through the existing
   Step 7 remediation path under the /goal evaluator loop — the
   evaluator reads the structured report and dispatches decision-memo
   authoring as the remediation work, then the gate re-runs on the
   next /build --resume iteration. The skip flag remains an explicit
   operator override even in autonomous mode.

5. **Write the release tag and release-notes.md (terminal phase close).**

   This step runs ONLY after items 1–4 above have all succeeded — full
   CI passing, invariants verified, spec-enforcer COMPLIANT, and
   verification.md written. These two writes are the marker of a
   successful terminal-phase close (BR-009, AC-009, AC-011).

   Sub-steps run in this order: **c.0 → a → b → c.1**.

<!-- forward-only: temp-ID allocation enforced from F023 release tag onward -->

   c. **Step 7c.0: Resolve final F-ID (F023 BR-006).** This MUST run
      first — before the release-tag write (sub-step a) and before the
      active→shipped move (Step 7c.1) — because both subsequent steps
      require the final `F<NNN>` path. The conductor invokes:

      ```bash
      final_id=$(python3 ~/.claude/scripts/feature_id.py resolve-final-id "Ftmp-<hex>-<slug>")
      ```

      Substitute `Ftmp-<hex>-<slug>` with the actual temp directory name
      from `state.yaml`.

      On exit 0, the dir is now at
      `.etc_sdlc/features/active/<final_id>-<slug>/` and any ADRs under
      `docs/adrs/Ftmp-<hex>-NNN-*.md` have been renamed to
      `<final_id>-NNN-*.md` via `git mv` (since `docs/adrs/` IS tracked).
      The `state.yaml.id_history` field is updated with the final-ID
      entry. The subsequent active→shipped move (Step 7c.1) operates on
      the final `<final_id>-<slug>` path — NOT the temp form.

      On non-zero exit, surface stderr verbatim and abort with exit 1 —
      operator remediates manually before re-running `/build --resume`.
      Matches F022's three-branch failure-semantics shape.

      **Legacy features (F001–F023).** If the feature directory is
      already in `F<NNN>` form (no `Ftmp-` prefix), `resolve-final-id`
      detects this and exits 0 with a stderr note: "feature already has
      final ID; no rename needed" (EC-003). The conductor proceeds
      without error; capture the returned `F<NNN>` into `final_id` for
      the release-tag write at sub-step a. Forward-only per F023 BR-010:
      F001–F023 keep their sequential names; only F024 and later features
      produce `Ftmp-<hex>-<slug>` directories.

   a. Write the release tag via the git_tags.py write-tag CLI:
      ```
      python3 ~/.claude/scripts/git_tags.py write-tag "etc/feature/<final_id>/release"
      ```
      Substitute `<final_id>` with the **final** `F<NNN>` returned by
      Step 7c.0 above — NOT the `Ftmp-<hex>` temp form. Exit codes
      follow the same convention as Step 6 (0 created, 1 degrade on
      non-git/no-HEAD, 2 hard fault).

   b. Build and write `release-notes.md` via the release_notes.py build
      CLI. The CLI prints the rendered markdown to stdout; redirect to
      the feature directory:
      ```
      python3 ~/.claude/scripts/release_notes.py build .etc_sdlc/features/active/<final_id>-<slug> > .etc_sdlc/features/active/<final_id>-<slug>/release-notes.md
      ```
      Substitute `<final_id>-<slug>` with the final feature directory
      name (after Step 7c.0's resolve-final-id rename). This step runs
      BEFORE the active→shipped move at Step 7c.1, so the path under
      `features/active/` is the correct source.
      The result lands at
      `.etc_sdlc/features/active/<final_id>-<slug>/release-notes.md` and
      rolls up PRD title and ID, phases closed, per-phase AC pass/fail
      summary citing each completion-report path, deferred items, and
      known limitations.

      The CLI form is required for the same reason as the git_tags.py
      invocations: helpers live at `~/.claude/scripts/`, not the user's
      project, so import-style invocation (`from scripts.release_notes
      import build`) MUST NOT be used.

   **Step 7c.1: Move the feature directory from `active/` to `shipped/`** (F009
      BR-005). After the release tag and release-notes.md are written
      and persisted under `features/active/<final_id>-<slug>/`, the feature
      transitions to its terminal audit-frozen state by relocating the
      entire directory tree under `features/shipped/`.

      First, ensure the `features/shipped/` parent exists. The
      conductor MUST create it idempotently before invoking the rename:
      ```python
      from pathlib import Path
      Path(".etc_sdlc/features/shipped").mkdir(parents=True, exist_ok=True)
      ```

      Then perform the rename. `git mv` is preferred when possible (it
      makes the rename canonical in the index so `git log --follow`
      traces the directory history through the transition); `shutil.move`
      is the sanctioned fallback when `.etc_sdlc/` is gitignored and the
      source dir has no tracked files. The argv-style invocation is
      mandatory — never a shell string — so operator-controlled feature
      slugs cannot inject shell metacharacters:
      ```python
      import shutil
      import subprocess
      import sys

      src = ".etc_sdlc/features/active/<final_id>-<slug>"
      dst = ".etc_sdlc/features/shipped/<final_id>-<slug>"

      result = subprocess.run(
          ["git", "mv", src, dst],
          capture_output=True, text=True,
      )

      if result.returncode == 0:
          pass  # branch (a): canonical git-tracked rename
      elif "source directory is empty" in result.stderr:
          # branch (b): .etc_sdlc/ is gitignored in this repo (the
          # default in client projects and in etc itself outside the
          # incidents/ + 4.7-audit/ whitelist), so the source dir has
          # no tracked files and git mv refuses. Fall back to
          # shutil.move so the audit-trail directory transition still
          # happens, and log to stderr so the rename's filesystem-only
          # nature is honest in the operator's terminal.
          shutil.move(src, dst)
          print(
              f"[build] {src} -> {dst} (filesystem-only; "
              ".etc_sdlc/ is gitignored)",
              file=sys.stderr,
          )
      else:
          # branches (c) and (d): destination exists, source missing,
          # or any other git mv failure. Surface git's stderr verbatim
          # and abort — edge case 6 preserved.
          print(result.stderr, file=sys.stderr, end="")
          sys.exit(1)
      ```

      Substitute `<final_id>-<slug>` with the final feature directory
      name (after Step 7c.0's resolve-final-id rename). The conductor
      MAY invoke `scripts/active_to_shipped_mv.py` (which implements
      this exact three-branch shape, including the F022-shipped
      `shutil.move` fallback) in place of inlining the recipe.

      **Failure semantics (edge case 6 — three-branch shape).** `git mv`
      can fail in three ways and the conductor handles each
      distinctly:

      - **(a) source dir has no tracked files** — git's stderr contains
        `source directory is empty`. This is the most common failure in
        practice (fired on F021's build on 2026-05-20 and F022's build
        on 2026-05-21) because `.etc_sdlc/` is gitignored in client
        projects and in etc itself outside the whitelist. The conductor
        falls back to `shutil.move`, logs a `filesystem-only` line to
        stderr, and continues. The rename is real on disk but is NOT
        canonical in the git index for this feature.
      - **(b) destination already exists** — git refuses to clobber.
        /build aborts with exit code 1 and surfaces git's stderr
        verbatim to the operator. The release tag from sub-step a and
        the release-notes.md from sub-step b have ALREADY been written
        and are NOT rolled back; both are append-only / on-disk
        artifacts of the successful terminal-phase close.
      - **(c) any other failure** (source path missing entirely,
        permission error, etc.) — same as (b): abort with exit code 1,
        surface git's stderr verbatim, no rollback of the prior
        sub-step a and b artifacts.

      **Discipline.** On branches (b) and (c), the operator must
      remediate manually (rm the conflicting target under
      `features/shipped/`, or fix the source path in `state.yaml`) and
      then re-run `/build --resume`. The conductor does not retry
      automatically — silent recovery from a pre-existing target would
      mask operator state the harness cannot validate. On branch (a),
      no operator action is required; the audit-trail line is the
      only observable signal that the rename was filesystem-only.

   **Discipline (edge case 4).** On mid-build failure — an escalated
   wave or a failing test at Step 6c, or a NON-COMPLIANT spec-enforcer
   result at Step 7 item 3 — neither the release tag nor
   release-notes.md is written, and the active→shipped move is NOT
   attempted. Step 7c.0 (resolve-final-id) is also NOT invoked. Skip
   all four sub-steps (7c.0, a, b, 7c.1). Phase start/done tags written
   by earlier successful waves remain in place; they are append-only and
   are not rolled back. Re-run `/build --resume` after remediation;
   sub-steps 7c.0, a, b, and 7c.1 run only on the successful
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
  .etc_sdlc/features/shipped/<final_id>-<slug>/  — terminal audit-frozen location
                                                   (renamed from Ftmp-<hex>-<slug>
                                                   at Step 7c.0, then moved from
                                                   features/active/ at Step 7c.1
                                                   via git mv / shutil.move)
    spec.md            — the PRD
    tasks/             — {N} task files
    verification.md    — quality report
    state.yaml         — pipeline state (includes id_history mapping temp→final)
    release-notes.md   — roll-up of phases closed, AC pass/fail, deferred items

  Git tags written under refs/tags/etc/:
    feature/Ftmp-<hex>/build/phase-<N>/start   — written during wave runs
    feature/Ftmp-<hex>/build/phase-<N>/done    — written during wave runs
    feature/<final_id>/release                 — terminal phase close (Step 7a)

### Deferred Items
{anything escalated or out of scope}
```

Update `state.yaml`: `current_step: 8`, `completed_at: {timestamp}`

---

## Resume Protocol

When invoked with `--resume`:

1. Find the most recent feature directory with an incomplete `state.yaml`
2. Read `current_step`, `waves_completed`, and `stacked`
3. Report: "Resuming {feature} from Step {N}, Wave {M}"
4. Continue from the next uncompleted step

**Stacking-aware resume (F010 BR-006, AC9).** When
`state.yaml.build.stacked == true`, resume picks up at the next layer
boundary: `wave_num = waves_completed + 1`. Step 6d.7 re-fires for the
new layer and bases its branch on the most recent completed layer's
branch (`<feature-slug>-L<waves_completed>`). Layer branches from
previously completed waves remain in place — they are append-only and
are not rolled back by resume. When `state.yaml.build.stacked == false`
(single-wave bypass per BR-005) or the field is absent (legacy
pre-F010 state.yaml per BR-008), resume uses the existing single-PR
semantics unchanged.

**Resume failure modes (F010 edge cases 8, 10).** If
`state.yaml.build.total_waves` changes between the original /build and
/build --resume (re-decomposition produced a different wave plan),
resume ABORTS with `error: wave plan changed during resume (expected
<old> waves, got <new>); cancel and re-run /build from scratch, or
revert spec changes`. If `state.yaml.build.stacked == true` but
`gh-stack` is missing on resume (operator uninstalled it mid-build),
FAIL FAST at the first Step 6d.7 invocation with the install
instruction (same message as edge case 4). /build does NOT degrade to
monolithic mode mid-build.

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
