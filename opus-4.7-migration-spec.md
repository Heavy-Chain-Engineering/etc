# Opus 4.7 Migration Spec for etc

**Status:** Execution plan, outside the etc framework
**Author:** Jason Vertrees + Claude Opus 4.7 (1M context)
**Created:** 2026-04-17
**Purpose:** Repair the etc harness's prompt surfaces so they operate
correctly under Claude Opus 4.7's literal instruction-following,
calibrated response length, reduced subagent spawning, and reduced
tool-use-by-default.

---

## 0. How to use this document

This is a **direct execution spec**, not an etc PRD. It does not use
`/spec`, `/build`, or etc's agent dispatch scaffolding (because those
are themselves broken by 4.7 literalism and are what we are repairing).

**Who executes this:** the operator (Jason) directing Claude Opus 4.7
in the main thread. The main thread does the planning, editing, and
dispatching. Subagents may be used for parallelizable audits, but only
with `subagent_type: "general-purpose"` and with prompts written fresh
from this spec — never by loading the broken etc agent definitions.

**How to resume:** every phase has an explicit "checkpoint state"
subsection. After each phase completes, the operator or the main thread
writes the checkpoint to `.etc_sdlc/4.7-migration-state.md`. On resume
(new session, after compaction, etc.), read that file first, then jump
to the next unfinished phase.

**How to know you are on the right track:** every phase has a
"verification" subsection with explicit commands that produce
observable output. Do not proceed to the next phase until the
verification passes.

---

## 1. Why this exists (the problem)

Claude Opus 4.7 differs from 4.6 in nine observable ways (per the
official migration guide at
https://platform.claude.com/docs/en/about-claude/models/migration-guide):

1. **More literal instruction following.** Will not silently generalize.
   Will not infer unstated requests.
2. **Response length calibrated to complexity.** No fixed verbosity
   default.
3. **More direct tone.** Less validation-forward. Fewer emoji.
4. **Built-in progress updates.** Scaffolding that forced interim
   updates is now redundant or contradictory.
5. **Fewer subagents spawned by default.** Prefers in-context reasoning.
6. **Stricter effort calibration.** At low/medium effort, does only
   what was asked.
7. **Fewer tool calls by default.** Reasons more, uses tools less.
8. **New tokenizer** uses up to 1.35x more tokens than 4.6.
9. **Real-time cybersecurity safeguards** may refuse legitimate work.

The etc harness was written in the 4.6 era. Its prompts rely on:

- The model generalizing "follow best practices" to specific actions
- The model inferring "be thorough" without explicit checklists
- Skills dispatching subagents based on implicit "wave execution" cues
- Agents reading relevant files without being told which
- Standards docs assumed to apply "where appropriate" without trigger
  conditions
- Progress reporting implicitly expected mid-execution

Under 4.7, these fail silently and literally. The operator observes
"spectacular breakage" — agents completing tasks partially, skipping
required reads, producing wrong-length output, refusing to spawn
subagents for waves, or treating the literal words of a prompt as the
complete scope when the 4.6-era author intended them as examples.

This spec is the repair plan.

---

## 2. The guiding principles

### 2.1 No implicit inference in prompts

Every prompt we write or repair must, if read with zero inference,
produce the correct behavior. If the prompt says "follow best
practices," the operator must either:

- Replace "follow best practices" with an explicit numbered list, OR
- Replace it with "read and apply the rules in standards/code/X.md
  sections Y and Z" (concrete reference), OR
- Delete the phrase (often the simplest fix).

### 2.2 Explicit verbosity guidance

Every agent definition and skill must state expected output length
and format. Options: "terse — max 3 sentences per response," "moderate
— prose paragraphs for rationale but tables for data," "exhaustive —
cover every case." If the agent is expected to produce artifacts (like
PRDs), it must state which.

### 2.3 Explicit subagent dispatch rules

Skills that orchestrate multi-task work must state: "You MUST
dispatch one subagent per task via the Agent tool. You MUST NOT
attempt to complete the tasks in your own context." If the skill
allows sequential in-context work, it must say so explicitly.

### 2.4 Explicit file-reading rules

Agent definitions that expect pre-reading must list exact files.
`requires_reading` in task YAMLs already does this correctly for
tasks. We need to mirror the pattern in agent definitions themselves
where they apply globally.

### 2.5 Scaffolding removal where 4.7 is native

Remove or soften phrases like:
- "After each step, report progress"
- "Summarize your work at the end of each phase"
- "Keep the user informed of your progress"

4.7 does this natively. Keeping the scaffolding either duplicates or
conflicts.

### 2.6 Self-review for 4.7 literalism

When writing any new prompt (including prompts in this spec itself,
and prompts given to subagents), after drafting, re-read it through
the lens of: "If I execute this literally with zero inference, will
the behavior match intent?" If no, revise.

---

## 3. The anti-pattern catalog

This is the complete list of prompt anti-patterns we are hunting. Each
entry has a search pattern (for grep), a diagnosis, and a replacement
strategy. The catalog is **exhaustive** — if a pattern is not on this
list, we do not fix it, because the catalog is the contract for what
"done" means.

### AP-001: Vague quality descriptors

- **Grep:** `best practices|follow established|industry standard|\bidiomatic\b|\bstrict typing\b|\bproper\b|\brobust\b|\bwell-designed\b`
- **Diagnosis:** implies a body of knowledge the model should infer.
  4.6 generalized; 4.7 executes literally (i.e., does nothing specific).
  Includes vague adjective descriptors ("idiomatic", "robust", "proper")
  that imply conformance to an unstated standard.
- **Fix:** replace with either (a) an inline numbered list of the
  specific practices, or (b) a concrete reference to a standards doc
  (e.g., "apply the rules in standards/code/python-conventions.md")
- **Delete condition:** if no specific practices are intended, delete
  the phrase entirely rather than leave it vague.
- **Revision history:** grep pattern expanded during Phase 1 execution
  (2026-04-17) after the narrower initial pattern missed "idiomatic"
  and "strict typing" in `agents/backend-developer.md` line 30.

### AP-002: "Be thorough" / "Be exhaustive"

- **Grep:** `be thorough|be exhaustive|comprehensive review|careful analysis`
- **Diagnosis:** implies a level of effort without specifying dimensions.
  4.7 under low/medium effort scopes to the literal ask.
- **Fix:** replace with explicit dimensions: "For each of the following,
  produce a finding: [list]." Example: instead of "thoroughly review
  the code," use "for each of {error handling, null inputs, off-by-one,
  concurrent access, authorization}, identify any violations."
- **Delete condition:** if the dimensions aren't known, the phrase
  isn't actionable; delete it.

### AP-003: "Consider edge cases" / "Handle edge cases"

- **Grep:** `edge case|corner case|consider.*cases|handle.*cases`
- **Diagnosis:** implies the model knows which edge cases matter.
  Under 4.7 literalism, the model considers the ones explicitly named
  and no others.
- **Fix:** for each context, enumerate the edge cases that matter.
  Use standards/process/ and the agent's scope to identify them.
  Example: for a backend API endpoint, the canonical set is
  {empty body, malformed JSON, auth absent, auth expired, quota
  exceeded, idempotency, concurrent duplicate request}. Spell them out.

### AP-004: "Where applicable" / "If appropriate" / "As needed"

- **Grep:** `where applicable|if appropriate|as needed|when appropriate|where appropriate`
- **Diagnosis:** implies the model knows when the trigger fires. 4.7
  defaults to "this does not apply here" under ambiguity.
- **Fix:** replace with concrete trigger. Example: "If the file path
  contains 'tests/', ignore ANN rules" not "ignore ANN rules where
  applicable."
- **Delete condition:** if no trigger can be specified, the guidance
  is unusable; delete.

### AP-005: Progress scaffolding

- **Grep:** `after each step|after each (phase|wave|task)|checkpoint (after|every)|report progress|keep.*informed`
- **Diagnosis:** 4.7 produces native progress updates in agentic
  traces. Our scaffolding is redundant.
- **Fix:** delete the scaffolding unless it specifies a structured
  output (e.g., "write state.yaml after each wave completes" — that's
  a concrete artifact, not a progress update).
- **Keep condition:** explicit checkpoint artifacts (state.yaml,
  ledger entry, commit) are kept. Only remove prose-level progress
  reporting.

### AP-006: Implicit subagent dispatch

- **Grep (in skills):** `execute.*waves?|dispatch.*tasks?|run.*tasks?|process.*tasks?`
- **Diagnosis:** the skill assumes the orchestrator will spawn
  subagents. 4.7 may try to complete everything in-context.
- **Fix:** add explicit dispatch rules:
  > "For each task in the current wave, you MUST invoke the Agent
  > tool once with subagent_type set to the task's assigned_agent.
  > You MUST NOT implement the task in your own context. You proceed
  > to the next wave only after every dispatched subagent has
  > returned a result."
- **Scope:** /build, /decompose, /implement, any skill that
  orchestrates multi-agent work.

### AP-007: Implicit tool use

- **Grep:** `as needed|if necessary|look up|check|verify|investigate`
  (in agent definitions and skills)
- **Diagnosis:** 4.7 uses tools less by default. Agents expected to
  read code before editing may skip the Read if the prompt only
  implies it.
- **Fix:** specify the tool explicitly: "Use the Read tool to load
  each file in the task's requires_reading list before using Edit
  on any file in files_in_scope. A read is not considered complete
  unless the Read tool was invoked with the exact file path."
- **Cross-ref:** this is why `hooks/check-required-reading.sh` was
  invented. It forces the reads. Keep the hook — it's the mechanical
  enforcement of this anti-pattern.

### AP-008: Implicit verbosity

- **Grep (in agent definitions, skills):** look for absence, not
  presence. Any agent/skill that does not include a verbosity
  directive is suspect.
- **Diagnosis:** 4.7 calibrates to task complexity. An agent that
  produced 400-line writeups under 4.6 may produce 40 under 4.7
  on a simple task — or the inverse on a complex task.
- **Fix:** add explicit verbosity guidance to every agent. Options:
  - "Terse: max 3 sentences per response, tables over prose, no
    preamble."
  - "Moderate: prose for rationale, tables for data, bullet lists
    for enumerations, max 500 words unless the task explicitly
    requests a longer artifact."
  - "Exhaustive: produce complete analysis covering every dimension
    listed below. Do not abbreviate."

### AP-009: Tone assumptions

- **Grep:** `warm|friendly|validating|encouraging|supportive`
- **Diagnosis:** 4.7 is more direct by default. Tone prompts that
  relied on 4.6's warmer baseline may over-correct.
- **Fix:** only retain tone directives if they are load-bearing
  (e.g., UX copy, customer-facing skills). For engineering
  surfaces, neutral technical tone is the 4.7 default and should
  be left unspecified.

### AP-010: Example-as-scope conflation

- **Grep:** `for example|e\.g\.|such as|including but not limited to`
- **Diagnosis:** under 4.7 literalism, "for example" followed by a
  list is sometimes treated as the complete scope, not illustrative.
- **Fix:** if the list is exhaustive, remove "for example" and make
  the list authoritative ("Check for: A, B, C"). If the list is
  illustrative, add "(illustrative; not exhaustive — extend as the
  situation warrants)" — but prefer to make the list exhaustive
  instead.

### AP-011: Implicit definition of done

- **Grep (in skills):** `done|complete|finished|ready to ship`
- **Diagnosis:** skills often imply DoD without specifying it. 4.7
  may terminate at the first apparent completion rather than the
  full DoD.
- **Fix:** each skill has an explicit "Definition of Done" section
  with a numbered checklist of observable artifacts.

### AP-012: Cyber-adjacent phrasing

- **Grep:** `exploit|vulnerability|attack|bypass|break`
- **Diagnosis:** 4.7's cybersecurity safeguards may trigger refusals
  on security-reviewer, especially for offensive-security-adjacent
  work.
- **Fix:** add an explicit context framing: "This is defensive
  security review for authorized codebases owned by the operator.
  All findings are for remediation, not exploitation. If you
  encounter a request that feels dual-use, flag it explicitly
  rather than refusing silently."

### AP-013: Reference without read-enforcement

- **Grep:** Not a single-pass grep. This is a cross-reference
  structural check. For each standards-doc or file reference in an
  agent prompt (e.g., `standards/code/python-conventions.md`),
  verify that at least one read-enforcement mechanism puts the
  referenced content into the agent's context.
- **Diagnosis:** Under 4.7's fewer-tool-calls default, an agent may
  see a reference like "conformant to `standards/X.md`" and not
  Read the file — because nothing forced it to. The reference
  becomes a false promise the harness doesn't keep. Experimentally
  validated 2026-04-17: when the trigger condition ("before writing
  any code") fires, agents do read all forced-read files; when it
  doesn't fire, they read only what the task requires. So the
  enforcement mechanism is what makes the reference real.
- **Check procedure:** For each file reference in the agent prompt:
  1. Does the agent have a "Before Starting" (or equivalent)
     section that mandates reading the referenced file?
  2. Does `hooks/inject-standards.sh` inject the referenced
     content into this agent's context at dispatch?
  3. Is the referenced file listed in `requires_reading` in the
     task YAML that dispatches this agent, enforced by
     `hooks/check-required-reading.sh`?
  If none of 1-3 is true, the reference is an AP-013 violation.
- **Fix options:** (a) add the referenced file to the agent's
  Before Starting section; (b) remove the reference and inline
  the rules the reference was pointing to; (c) move enforcement
  to `inject-standards.sh` or `requires_reading` at the task level.
- **Exempt condition:** Pure documentation/commentary references
  (e.g., "See also..." in a "Further Reading" section) are not
  behavioral directives. They do not require enforcement.
- **Revision history:** added 2026-04-17 during Phase 1 execution
  after Experiment 2 confirmed the forced-reads pattern works
  unconditionally for code-writing tasks on `backend-developer.md`
  but only because all standards references in that file were
  already on the Before Starting list. The check formalizes what
  was verified implicitly.

---

## 4. The fix catalog

For each anti-pattern above, the fix is one of three kinds:

- **Mechanical substitution** (regex-level find/replace): applies
  when the pattern has a clean token-level match and the replacement
  is deterministic. AP-001 with a known standards reference,
  AP-004 with a known trigger.
- **Guided rewrite** (human judgment, prompt-level edit): applies
  when the pattern needs interpretation. AP-002, AP-003, AP-007.
- **Deletion** (remove the phrase entirely): applies when the
  phrase adds no value. AP-005 scaffolding, vague AP-001 without a
  target.

A file edit passes review only if the result contains zero instances
of any AP-NNN grep pattern (except inside explicit "anti-pattern
catalog" references like this spec).

---

## 5. Phase 0: Snapshot & baseline

Goal: capture "before" state so we can prove "after" worked.

### 5.1 Commit the working tree first

Before any migration edits, commit the current state of the working
tree to main (it already is, per the earlier session — confirm with
`git status` returns clean).

### 5.2 Run the test suite and record the count

```
python -m pytest -q 2>&1 | tail -3
```

Record the passing test count. Current baseline: 409 (pre-v1.8).
Post-v1.8 build-in-progress is expected to be ~439. Whichever is the
current HEAD count is the baseline.

### 5.3 Compile and record counts

```
python3 compile-sdlc.py spec/etc_sdlc.yaml 2>&1 | tail -10
```

Record: gates, hooks, agents, skills, standards counts. These must
match after migration (we are not adding or removing, only editing
existing definitions).

### 5.4 Inventory the prompt surfaces

```
find agents -name '*.md' -not -path '*/.meta/*' | wc -l
find skills -name 'SKILL.md' | wc -l
grep -l 'type: agent\|type: prompt' spec/etc_sdlc.yaml | wc -l
find standards -name '*.md' -not -path '*/.meta/*' | wc -l
```

Record the counts. This is the universe we are auditing.

### 5.5 Run the anti-pattern grep sweep

Sweep every AP pattern in the catalog (section 3) and record counts.
Patterns ordered by AP number. AP-008 is absence-based (no grep);
audit manually in Phase 2.

```
mkdir -p .etc_sdlc/4.7-audit
{
  echo "=== AP-001: vague quality descriptors ==="
  grep -rInE 'best practices|follow established|industry standard|\bidiomatic\b|\bstrict typing\b|\bproper\b|\brobust\b|\bwell-designed\b' agents/ skills/ standards/ spec/etc_sdlc.yaml | wc -l

  echo "=== AP-002: be thorough / comprehensive ==="
  grep -rInE 'be thorough|be exhaustive|comprehensive review|careful analysis' agents/ skills/ standards/ spec/etc_sdlc.yaml | wc -l

  echo "=== AP-003: edge/corner cases ==="
  grep -rInE 'edge case|corner case|consider.*cases|handle.*cases' agents/ skills/ standards/ spec/etc_sdlc.yaml | wc -l

  echo "=== AP-004: where applicable / as needed ==="
  grep -rInE 'where applicable|if appropriate|as needed|when appropriate|where appropriate' agents/ skills/ standards/ spec/etc_sdlc.yaml | wc -l

  echo "=== AP-005: progress scaffolding ==="
  grep -rInE 'after each step|after each phase|after each wave|after each task|checkpoint after|checkpoint every|report progress|keep.*informed' agents/ skills/ standards/ spec/etc_sdlc.yaml | wc -l

  echo "=== AP-006: implicit subagent dispatch (skills only) ==="
  grep -rInE 'execute.*waves?|dispatch.*tasks?|run.*tasks?|process.*tasks?' skills/ spec/etc_sdlc.yaml | wc -l

  echo "=== AP-007: implicit tool use (narrow patterns to reduce noise) ==="
  grep -rInE '\bif necessary\b|\blook up\b|\binvestigate\b|\bas needed\b' agents/ skills/ standards/ spec/etc_sdlc.yaml | wc -l

  echo "=== AP-008: implicit verbosity — manual audit in Phase 2, no grep ==="
  echo "N/A"

  echo "=== AP-009: tone assumptions ==="
  grep -rInE 'warm|friendly|validating|encouraging|supportive' agents/ skills/ standards/ spec/etc_sdlc.yaml | wc -l

  echo "=== AP-010: example-as-scope ==="
  grep -rInE 'for example|\be\.g\.|such as|including but not limited to' agents/ skills/ standards/ spec/etc_sdlc.yaml | wc -l

  echo "=== AP-011: implicit DoD (skills only; narrow patterns) ==="
  grep -rInE '\bwhen done\b|\bonce (done|complete|finished)\b|\bready to ship\b' skills/ spec/etc_sdlc.yaml | wc -l

  echo "=== AP-012: cyber-adjacent phrasing (in security-reviewer) ==="
  grep -rInE '\bexploit\b|\bvulnerabilit|\battack\b|\bbypass\b' agents/ skills/ | wc -l
} > .etc_sdlc/4.7-audit/before.txt
```

The `before.txt` file is the baseline for how much work there is.
Keep it; we rerun the same sweep at the end to prove coverage.

**Note on narrow patterns:** AP-007 and AP-011 use word-boundary anchors
(\b) because their bare forms (`check`, `done`) produce massive false-
positive counts across the codebase (`git check-ignore`, `done messages`,
etc.). The narrow patterns catch the prompt-anti-pattern uses while
filtering most incidental matches. Manual verification in Phase 2 will
catch any narrow-pattern misses.

### 5.6 Checkpoint state

Write `.etc_sdlc/4.7-migration-state.md`:

```markdown
# 4.7 Migration State

Phase 0: complete
- Baseline commit: <SHA>
- Baseline test count: <N>
- Baseline compile counts: gates=<>, hooks=<>, agents=<>, skills=<>, standards=<>
- Audit counts in .etc_sdlc/4.7-audit/before.txt

Phase 1: not started
```

### 5.7 Verification

- `git status` shows clean tree
- `.etc_sdlc/4.7-audit/before.txt` exists and is non-empty
- `.etc_sdlc/4.7-migration-state.md` exists
- Test count recorded

---

## 6. Phase 1: Prototype on one agent

Goal: prove the fix pattern works on a single agent before rolling
out to the other twenty.

### 6.1 Target selection

Target: `agents/backend-developer.md`.

Rationale: it is the most frequently dispatched agent in etc. If the
fix pattern works here, it will scale to the others. If it fails
here, we need to rethink before committing to a full rollout.

### 6.2 Pre-edit analysis (deep-think)

Before editing, write a brief in `.etc_sdlc/4.7-audit/backend-developer-brief.md`:

Read the current `agents/backend-developer.md`. For each section,
enumerate:

1. What the section SAYS, literally, in 4.7 reading.
2. What the section INTENDED (based on context and the 4.6 era).
3. The gap, if any.
4. Which AP-NNN patterns apply.
5. The proposed fix (inline or reference).

This file is not shared; it is scratch memory for the main thread
to catch its own 4.7-literalism mistakes before committing them to
the agent definition. **This is the self-review protocol in practice
for this one agent.** Do not skip it.

### 6.3 Apply fixes

Edit `agents/backend-developer.md` with the fixes from the brief.
Do it one section at a time. After each Edit, reread the full file
and check: does any AP-NNN pattern still match? If yes, fix it.

Do not batch all edits into one write. Do them one section at a
time. The diff legibility matters for the operator's review.

### 6.4 Test the prototype

There are three tests:

**Test A (mechanical):** `grep -rnE '...' agents/backend-developer.md`
for each AP-NNN pattern returns zero matches (or only matches with
explicit "not-an-anti-pattern" escape like a reference to this spec).

**Test B (behavioral):** dispatch a backend-developer subagent
against a known existing task in `.etc_sdlc/features/` that was
built successfully in a prior wave. Compare its behavior to the
historical output of that same task (git log, commit diffs). Did
it read the required files? Did it produce the expected artifact?
Did verbosity match? Capture the transcript.

**Test C (regression):** run the full test suite. Counts must match
baseline exactly. No test should have been broken by the agent
definition edit.

### 6.5 Operator review

Stop here. Do not proceed to Phase 2 without the operator's explicit
approval. Present the diff, the three test results, and the
before/after of the `.etc_sdlc/4.7-audit/backend-developer-brief.md`
analysis.

### 6.6 Checkpoint state

Update `.etc_sdlc/4.7-migration-state.md`:

```markdown
Phase 1: complete
- Target: agents/backend-developer.md
- Diff: <hash of commit or path to diff>
- Test A: pass
- Test B: <pass | partial | fail> + transcript path
- Test C: pass (N/N tests)
- Operator approval: <yes|no> (date)

Phase 2: not started
```

### 6.7 Verification

- Zero AP-NNN grep matches in `agents/backend-developer.md`
- Test suite green
- Operator has approved the prototype

---

## 7. Phase 2: Apply to remaining 20 agents

Goal: roll out the prototype pattern to all other agents.

### 7.1 Target list

All `.md` files in `agents/` except `backend-developer.md` (done in
Phase 1) and `.meta/` files. Expected count: 20.

### 7.2 Parallelization plan

These files are file-disjoint — each agent is its own file. We can
dispatch multiple subagent audits in parallel.

**BUT** — each subagent must be given an explicit prompt that does
NOT rely on the broken etc agent definitions. Use `subagent_type:
"general-purpose"` only. Never dispatch through the etc agent
definitions we are repairing.

The prompt each subagent receives must be written from scratch by
the main thread, and must include:

1. The full anti-pattern catalog (section 3 of this spec)
2. The full fix catalog (section 4)
3. The target file path (single agent to audit)
4. The completed Phase 1 agent as a reference example of "what good
   looks like"
5. Explicit verbosity directive: "Produce a diff for the target
   file. Return the diff text, the AP-NNN pattern counts before/
   after, the number of edits made, and the AP-013 reference-
   enforcement check result. Terse output; no prose commentary."
6. Explicit completion rule: "You have one file to audit. When the
   file contains zero matches for AP-001..AP-012 AND the AP-013
   structural check passes (every standards reference has an
   enforcement path), you are done. Do not audit other files."
7. AP-013 structural check instructions: "After fixing AP-001..AP-012,
   list every `standards/...` or `.md` file reference in the target
   file. For each, identify the enforcement path: (a) a Before
   Starting section in the same agent that mandates reading the
   file, OR (b) `inject-standards.sh` injection (only for files in
   `standards/`), OR (c) `requires_reading` in task YAML. If a
   reference has no enforcement path, either add the file to the
   Before Starting section or remove the reference. Document the
   check in the completion report."

### 7.3 Dispatch pattern

Dispatch agents in batches of 5 (to respect rate limits and keep
review tractable). Wait for all 5 to complete. Review the diffs.
Commit or request revisions. Then dispatch the next 5.

Do NOT dispatch 20 agents in one shot. The review becomes a bottleneck.

### 7.4 Per-batch verification

After each batch lands, run:
- `grep -rnE '...' agents/` — should show the AP-NNN counts
  decreasing as we go
- `python -m pytest -q` — test suite still green
- Compile — counts unchanged

If any batch fails, roll back just that batch's commits and redispatch
with a refined prompt.

### 7.5 Checkpoint state

Update `.etc_sdlc/4.7-migration-state.md` after each batch:

```markdown
Phase 2: in progress
- Batch 1 (5 agents): complete — commit <SHA>
- Batch 2 (5 agents): complete — commit <SHA>
- ...
```

### 7.6 Verification

- All 21 agents show zero AP-NNN grep matches
- Test suite green
- Compile counts unchanged
- Commit history shows the batches

---

## 8. Phase 3: Audit skills

Goal: repair skill definitions (`skills/*/SKILL.md`).

### 8.1 Why skills are trickier

Skills orchestrate. They contain the implicit-subagent-dispatch
language (AP-006) that is most load-bearing. A wrong fix here
breaks orchestration globally, not just one task.

### 8.2 Execution mode

Skills must be audited sequentially, not in parallel, because
several skills share conventions and reference each other (e.g.,
`/build` references `/decompose`). Batching them risks a refactor
in one skill that contradicts another.

### 8.3 Target order (priority)

1. `skills/build/SKILL.md` — highest-blast-radius orchestrator
2. `skills/decompose/SKILL.md` — called by /build
3. `skills/implement/SKILL.md` — parallel orchestrator
4. `skills/spec/SKILL.md` — mostly explicit already; should be
   lighter work
5. `skills/hotfix/SKILL.md` — already explicit (Pattern A/B);
   should be light
6. Remaining skills in any order

### 8.4 Per-skill protocol

For each skill, follow the Phase 1 protocol (pre-edit brief,
section-by-section edits, AP grep check). The difference is that
skills have an additional check:

**Dispatch-rule audit:** search the skill for any implicit
"execute" or "run" or "process" language. Add the explicit
subagent dispatch rule (AP-006 fix) where multi-task orchestration
is implied.

**DoD audit:** every skill must have an explicit "Definition of
Done" section with a numbered checklist (AP-011 fix). Add if missing.

### 8.5 Verification

After each skill, run the full test suite and compile. The test
suite should catch any compile-level breakage. Behavioral correctness
of skills is hard to test without running them end-to-end, so the
operator must spot-check one real usage per modified skill.

### 8.6 Checkpoint state

Update per skill.

---

## 9. Phase 4: Audit hooks and standards

Goal: repair remaining prompt surfaces.

### 9.1 Hooks

Targets: any hook in `spec/etc_sdlc.yaml` with `type: agent` or
`type: prompt`.

Known list:
- `task-readiness` (TaskCreated, prompt)
- `task-completion` (TaskCompleted, agent)
- `adversarial-review` (SubagentStop, agent)

For each, open the `prompt:` block in `spec/etc_sdlc.yaml`, run
the AP catalog against it, fix inline. Recompile after.

Command hooks (`type: command`) are bash scripts, not prompts.
Skip them.

### 9.2 Standards docs

Standards docs are read by agents via `inject-standards.sh`. Their
quality directly affects agent behavior under 4.7.

Targets: all files in `standards/` that are directive (tell the
agent what to do). Audit for:
- AP-001 vague "follow best practices" language
- AP-004 "where applicable" triggers
- AP-008 implicit verbosity (standards docs should not mandate
  length, but they may mandate content)
- AP-010 example-as-scope conflation (common in standards —
  lists of example rules are sometimes interpreted as exhaustive)

Standards are read-only for agents; editing them is lower-risk
than editing agents or skills. Do this phase LAST because the
lift is largest and the per-edit risk is lowest.

### 9.3 Verification

Full AP grep sweep across the entire harness. Compare to
`.etc_sdlc/4.7-audit/before.txt`. Write `after.txt`. The diff is
the migration's concrete output.

---

## 10. Phase 5: Regression test and ship

### 10.1 Full test suite

```
python -m pytest -q 2>&1 | tail -5
```

Must pass. Count must match baseline or be greater (v1.8 tests
should have landed in the interim, adding to the count).

### 10.2 Compile

```
python3 compile-sdlc.py spec/etc_sdlc.yaml 2>&1 | tail -12
```

Counts must match baseline exactly.

### 10.3 End-to-end smoke test

Dispatch one subagent against a simple known task. Observe:
- Did it read required files (via hook telemetry)?
- Did it produce expected verbosity?
- Did it complete without manual intervention?

This is qualitative — it confirms that the prompt repairs
produced behavioral improvement, not just mechanical grep-zero.

### 10.4 Write the migration changelog

Create `docs/4.7-migration-changelog.md`:

- Files changed (count, list)
- AP-NNN counts before/after (from before.txt and after.txt)
- Test count before/after
- Compile counts before/after
- Known remaining issues (if any)
- Next steps (if any)

### 10.5 Commit and tag

Commit message: `fix(harness): audit all prompts for 4.7 literal
instruction-following`

Tag: `v1.7.2-4.7-migration` (not a major version — this is a
defect repair against 4.7, not a feature release).

### 10.6 Ledger entry

If the v1.8 ledger feature has landed, add an entry:

```markdown
## 2026-04-17 — Opus 4.6 → 4.7 migration audit
**Category:** discovery
**Source:** this migration run
**Lesson:** The harness had accumulated implicit-inference prompts
that relied on 4.6's generalization. 4.7's literal following
surfaces these as silent failures. The fix pattern is: enumerate,
don't imply. Apply it during prompt authoring, not retroactively.
```

### 10.7 Checkpoint state

Final update to `.etc_sdlc/4.7-migration-state.md`:

```markdown
Phase 5: complete
- Migration changelog: docs/4.7-migration-changelog.md
- Test count: N → N' (unchanged or grew)
- Compile counts: unchanged
- Commit: <SHA>
- Tag: v1.7.2-4.7-migration
```

---

## 11. The self-review protocol (deep-think discipline)

This section is the countermeasure to my own 4.7 literalism while
executing this spec. The main-thread agent (me, or a future Claude
session) MUST apply it at the trigger points below.

### 11.1 Trigger points

- **Before starting each phase:** read section 3 (anti-pattern
  catalog) and section 4 (fix catalog). Do not start a phase
  from memory of the catalog.
- **Before editing any file:** write a 3-5 line pre-edit brief
  stating what will change and why. If this is hard to write,
  the edit is not ready.
- **Before dispatching any subagent:** read the full subagent
  prompt draft and ask "if executed with zero inference, will
  the behavior match intent?" If no, revise.
- **After each Edit tool call:** re-read the file and check for
  AP-NNN matches. If any remain, fix before proceeding.
- **Before checkpointing a phase as complete:** run the phase's
  verification subsection. Every item must pass.

### 11.2 Failure modes to watch for

The main-thread agent may fall into these 4.7-literalism traps
while executing. Each trap has a concrete counter.

**Trap 1: Treating the anti-pattern catalog as exhaustive for all
possible bad patterns.**

Counter: the catalog is exhaustive for AP-001 through AP-012.
If a new pattern is discovered during execution, add it as
AP-NNN in this file FIRST, then fix all instances. Do not silently
"also fix similar patterns" — that reintroduces the implicit
inference we are trying to eliminate.

**Trap 2: Copying the fix for one agent to another without
re-deriving it.**

Counter: each agent's fixes are independently reasoned. A fix that
works for backend-developer may be wrong for researcher. Do the
pre-edit brief (section 6.2 protocol) for each target.

**Trap 3: Parallelizing audits that have hidden dependencies.**

Counter: before dispatching parallel audits, grep for cross-agent
references. If agent A's definition references agent B, they are
coupled — audit sequentially, not in parallel.

**Trap 4: Checkpointing a phase without running verification.**

Counter: the verification subsection of each phase is non-negotiable.
The checkpoint file includes verification pass/fail per item. If
any item fails, the phase is not complete, even if the edits are
done.

**Trap 5: Reading this spec from the middle without reading the
preamble.**

Counter: on resume, always read sections 0, 1, 2, 3, 4, and the
relevant phase section. The execution requires the anti-pattern
catalog and the guiding principles as active context. Reading only
the phase section risks executing with stale or absent context.

### 11.3 When in doubt, deep-think

If a step feels under-specified, stop. Write what you think the
step means, list alternative interpretations, pick the one most
consistent with section 2 (guiding principles), and document the
choice in `.etc_sdlc/4.7-migration-state.md`. Then proceed.

Under-specified is worse than over-specified for a 4.7 executor.
Bias toward explicitness at every branch.

---

## 12. Out of scope

The following are deliberately excluded from this migration. Do not
drift into them.

- **Adding new features to etc.** This is a repair pass, not a
  feature pass. If the audit surfaces a feature-worthy idea, log
  it to the roadmap (once v1.8 lands) and keep moving.
- **Changing the SDLC phase model, three-lane architecture, or
  agent roster.** The repair is within the existing structure.
- **Performance optimization of `inject-standards.sh` or other
  hook surfaces.** The 35% tokenizer inflation is a real concern,
  but it is orthogonal to the literalism repair. Separate PRD.
- **Consumer-project migration.** VenLink, Novasterilis, Covr
  will need their own 4.7 audits. This spec covers only etc itself.
  Consumer-project migrations can reuse the anti-pattern catalog.
- **Rewriting the etc harness "from scratch for 4.7."** No. The
  existing harness is repairable. Rewrites defer shipping and
  accumulate the same class of drift on the new codebase.
- **`standards/process/` docs that are non-directive** (overviews,
  background). Only audit directive standards (ones that tell
  agents what to do).

---

## 13. Escape hatches

### 13.1 If a phase's verification fails

Do not proceed to the next phase. Document the failure in
`.etc_sdlc/4.7-migration-state.md` under the failing phase.
Fix, then retry verification.

### 13.2 If the prototype (Phase 1) fails

Do not scale to Phase 2. Present the failure to the operator.
The fix pattern may need refinement.

### 13.3 If the test suite breaks during migration

`git revert` the specific commit that broke it. Do not continue
through a broken test suite.

### 13.4 If an agent definition becomes unreadably verbose after
fix application

Re-evaluate the fix: maybe the original anti-pattern was cover for
a concept that was genuinely fuzzy. Either enumerate the concept in
a standards doc and reference it, or accept some fuzziness and
document why in an inline comment.

### 13.5 If execution is interrupted

Read `.etc_sdlc/4.7-migration-state.md` first. Then re-read sections
0-4 of this spec. Then resume at the next unfinished phase.

---

## 14. Definition of Done for this migration

This migration is complete when ALL of the following hold:

1. Every file in `agents/`, `skills/*/SKILL.md`, the agent/prompt
   blocks of `spec/etc_sdlc.yaml`, and directive files in `standards/`
   shows zero AP-NNN grep matches from the catalog in section 3.
2. The full test suite passes with a count equal to or greater than
   the Phase 0 baseline.
3. The compile counts match the Phase 0 baseline exactly.
4. `.etc_sdlc/4.7-audit/before.txt` and `after.txt` exist, and the
   after counts are all zero for each AP-NNN.
5. `docs/4.7-migration-changelog.md` exists with before/after
   measurements, a concrete list of files changed, and any known
   remaining issues.
6. A commit on main tagged `v1.7.2-4.7-migration` lands.
7. An end-to-end smoke test (dispatch one subagent on a real task)
   has been observed to work correctly.
8. `.etc_sdlc/4.7-migration-state.md` shows Phase 5 complete.

Nothing less counts as done. Nothing more is needed.
