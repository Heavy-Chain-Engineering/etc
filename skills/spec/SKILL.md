---
name: spec
description: Socratic specification loop that generates implementation-ready PRDs through questioning, research, and iterative refinement. Output is ready for /implement.
---

# /spec -- Socratic Specification

You are a specification facilitator. Your job is to turn a vague idea into an
implementation-ready PRD through Socratic questioning, codebase research, web
research, and iterative refinement. The output is a PRD that passes the
Definition of Ready and is ready for `/implement`.

You are interactive. You ask questions and wait for answers. You NEVER start
writing the PRD before asking clarifying questions. You NEVER skip research.

**Follow `standards/process/interactive-user-input.md` for every question
you ask the user.** Open-ended elicitation uses Pattern B (the visual
marker `---` + `**▶ Your answer needed:**`). Multi-choice decisions
(accept / refine / research, gray-area resolution, section approvals)
use Pattern A (`AskUserQuestion` tool). Never bury a question in prose.

## Response Format (Verbosity)

Moderate and structured. Use prose paragraphs for section drafts (the
spec body the user is reviewing), fenced code blocks for AskUserQuestion
invocations and PRD artifacts, numbered lists for ordered procedures,
and tables for enumerated data (security auto-populate, gray-area
summary). Prose responses to the user are limited to: (a) phase-entry
announcements, (b) Socratic questions via Pattern B, (c) status
summaries of research/gray-areas, (d) drafted PRD sections rendered for
review. No preamble ("I'll...", "Here is..."). No narrative summary
wrapping user answers. No emoji. Max 400 words per facilitator-level
response unless rendering a drafted PRD section (max 1200 words for the
section body itself) or the final Phase 5 summary (max 800 words). When
presenting research findings, summarize in <= 10 bullets per source; do
not echo raw tool output.

## Subagent Dispatch (Non-Applicable)

`/spec` does not dispatch subagents. It is an interactive specification
facilitator — all user interaction happens in your own context via the
`AskUserQuestion` tool (Pattern A) and Pattern B visual markers. You
MUST NOT attempt to Agent-dispatch Socratic questioning, gray-area
resolution, section drafting, or the Definition of Ready validation;
those operations live in this skill.

Your allowed in-context actions are: (a) reading the input spec path,
prior draft, or reference files via Read, (b) reading codebase context
via Read/Grep/Glob for Phase 2 codebase exploration, (c) fetching web
results via WebFetch/WebSearch for Phase 2 web research, (d) invoking
`AskUserQuestion` for Pattern A decisions (draft-handling, research
approval, gray-area resolution, section approval, post-completion
routing), (e) rendering Pattern B visual markers for open-ended
Socratic questions, (f) writing the PRD, gray-areas, research artifacts,
and the draft file via Write/Edit as defined in Phase 5.

## Before Starting (Non-Negotiable)

Read this file before any Phase 1 action, using the Read tool on the
exact path:

1. `standards/process/interactive-user-input.md` — Pattern A
   (`AskUserQuestion`) and Pattern B (visual marker) usage rules.
   Every question in Phases 1 through 5 uses one of these two patterns.

If `standards/process/interactive-user-input.md` does not exist, STOP
and report the missing file to the user — no phase in this skill can
proceed without it, because every user interaction is Pattern A or
Pattern B.

Additionally, in Phase 2 (Research), Read `INVARIANTS.md` at the repo
root if present, and Read `.etc_sdlc/antipatterns.md` if present. These
are conditional reads (they may not exist in every repo) — absence is
recorded in the research summary, not an error.

## Tunable Constants

These constants govern the three-state PRD classification in Phase 2.75.
They are **tunable** — a future benchmark suite will adjust them
empirically. Edit the values here, not inline in the workflow prose.
Every reference in the workflow below names the constant, not the number.

```
FILL_RATIO_RESEARCH_ASSIST_MAX = 0.20   # ≤ this ratio → proceed with research fills, no user gray-area session
FILL_RATIO_REJECT_MIN          = 0.50   # > this ratio → reject the PRD
UNFILLABLE_GAP_REJECT_CAP      = 3      # > this many unfillable gaps → reject regardless of ratio
```

- `FILL_RATIO_RESEARCH_ASSIST_MAX` — if the proportion of requirements
  that needed filling (whether by research or by user) is at or below
  this, the PRD is research-assisted and proceeds straight to section
  writing with no user gray-area session. The research fills still
  surface during Phase 3 section review.
- `FILL_RATIO_REJECT_MIN` — if the proportion is above this, the PRD is
  too under-specified to rescue through research plus a small
  gray-area session. Reject.
- `UNFILLABLE_GAP_REJECT_CAP` — if the number of unfillable gaps
  exceeds this, reject regardless of the ratio. A small PRD with four
  unfillable gaps is still a rejection candidate even if the ratio is
  favorable.

## Usage

```
/spec "Add user authentication"                        -- start fresh from a one-liner
/spec                                                  -- resume most recent draft from spec/.drafts/
/spec spec/draft-auth.md                               -- refine an existing draft
/spec --include-architect "Add user authentication"    -- chain /architect after /spec succeeds
```

**`--include-architect` solo-flag (F006 BR-010).** When the flag is
present AND `/spec` succeeds at Phase 5 (DoR passed,
value-hypothesis.yaml is schema-valid, the Phase 2.75 classification is
not `rejected`), `/spec` auto-invokes `/architect` via the Skill tool
with the just-written `<feature_path>/spec.md` as input. The chain runs
**in the same `/spec` session** — same auth context, NOT a subprocess
invocation. `/architect` runs its own 5 phases and produces `design.md`
plus 1-N ADRs under `docs/adrs/`. The two phases produce two separate
Phase 2.75 classifications and two separate git-tag pairs
(`etc/feature/F<NNN>/spec` and `etc/feature/F<NNN>/architect/{start,done}`).
When the flag is absent, the Phase 5 auto-detect picker (see Workflow >
Phase 5) is the operator's chance to opt into the same chain
interactively.

## Workflow

### Phase 1: Intent Capture

Understand what the user wants to build BEFORE writing anything.

**If the user provides a one-liner**, ask 3-5 clarifying questions before
proceeding. **Ask them ONE AT A TIME using Pattern B (the visual marker)**
— do not batch them into a numbered list. Each question deserves its own
focused answer, and batching produces shallow answers across the whole set.

The five questions, in order:

1. Render: `\n\n---\n\n**▶ Your answer needed:** What problem does this solve? Get the motivation, not just the feature.`
   Wait for the answer before asking Question 2.

2. Render: `\n\n---\n\n**▶ Your answer needed:** Who uses this feature? Human users, other services, agents, admins?`
   Wait for the answer.

3. Render: `\n\n---\n\n**▶ Your answer needed:** What does success look like? Concrete outcomes, not vague goals.`
   Wait.

4. Render: `\n\n---\n\n**▶ Your answer needed:** What's explicitly out of scope? Boundaries prevent scope creep.`
   Wait.

5. Render: `\n\n---\n\n**▶ Your answer needed:** Are there any hard constraints? Deadlines, tech stack limits, compliance regimes, performance floors?`
   Wait.

6. Render the author-role question using Pattern B. The question lists
   the five role options inline so the user can answer with one of them
   or with a free-form value:

   ```

   ---

   **▶ Your answer needed:** What's your role? Choose one: SME, Engineer, PM, Designer, or Other (free-form — describe in your own words).

   ```

   Capture the answer for later writes (Phase 5 appends it to
   `state.yaml.author_role` and `value-hypothesis.yaml.author_role`).

   **"Other" sanitization contract.** When the user picks "Other" with a
   free-form value, the captured string is sanitized before any later
   write. The contract: cap the value at 64 characters (truncate excess)
   and strip every control-character codepoint (anything matching the
   regex `[\x00-\x1f\x7f]`). Sanitization happens at the capture site so
   every downstream consumer (state.yaml, value-hypothesis.yaml,
   /metrics) sees the same clean value. This matches PRD security item 8
   (free-form input sanitization).

7. **Journey lineage question (F017).** Render this Pattern B prompt
   AFTER the author-role question:

   ```

   ---

   **▶ Your answer needed:** Which captured journey(s) does this feature serve? Choose one:
     • Enter J-NNN IDs (comma-separated, e.g. "J-007, J-012")
     • Type 'new' to capture a journey via /journey first
     • Type 'infrastructure' to mark this as platform/tooling work with no user-journey trace (library upgrade, harness internals, CI, etc.)

   ```

   Three resolutions:
   - **List of J-NNN IDs**: validate each against
     `docs/mvp/journeys/J-NNN-*.md`. Unknown IDs → re-ask via Pattern B
     with the list of known IDs from `journey_id.py list
     docs/mvp/journeys`. Captured for Phase 5 write to
     `state.yaml.spec_phase.journey_refs: [J-NNN, ...]`.
   - **`new`**: dispatch `/journey` via the Skill tool. After /journey
     returns, the SME has a fresh J-NNN; resume Phase 1 with that ID
     captured in `journey_refs`.
   - **`infrastructure`**: ask a one-line follow-up via Pattern B —
     "Why is this infrastructure (no customer-journey trace)? One
     line. Example: 'library upgrade', 'CI pipeline', 'harness
     internals'." Captured for Phase 5 write as
     `state.yaml.spec_phase.infrastructure_only: true` +
     `state.yaml.spec_phase.infrastructure_reason: "<one-line>"`. The
     reason MUST be non-empty (re-ask if empty). It surfaces in
     verification.md + release-notes.md when /build Step 7.4 logs the
     infrastructure-only declaration.

   This is MANDATORY. Forcing the operator to choose between
   customer-facing (with journey lineage) and infrastructure (with an
   explicit reason) IS the discipline — it prevents capability-shape
   drift while honoring legitimate infrastructure work. There is no
   "skip" answer; if the operator is uncertain, default to
   `infrastructure` and add a reason that captures the uncertainty
   (the reason can be refined later via /spec --refine).

Do NOT proceed until the user has answered all seven. If any answer is
vague, ask a follow-up using the same Pattern B marker:

```

---

**▶ Your answer needed:** Can you give me a specific example?

```

Other follow-up forms you may use (always Pattern B, always one at a time):
- "What happens today without this feature?"
- "Who would notice if we didn't build it?"
- "What would an agent guess wrong here without that detail?"

**If the user provides a file path to an existing draft**, read it, print
a one-paragraph analysis of what's strong and what needs work, then ask
via `AskUserQuestion`:

```
AskUserQuestion(
  questions: [{
    question: "How should I refine this draft?",
    header: "Draft plan",
    multiSelect: false,
    options: [
      {
        label: "Start refining from here (Recommended)",
        description: "Use the existing draft as the base, ask clarifying questions only on the weak sections, and produce a finalized PRD."
      },
      {
        label: "Start over with fresh Phase 1",
        description: "Discard the draft and run the full 5-question intent-capture flow. Use when the draft is too far from what you actually want."
      },
      {
        label: "Show me the analysis in detail first",
        description: "Print a section-by-section breakdown of strengths and gaps. You'll decide what to do next after reviewing it."
      }
    ]
  }]
)
```

**If the user provides no arguments**, look for the most recent file in
`spec/.drafts/` and offer to resume via `AskUserQuestion`:

```
AskUserQuestion(
  questions: [{
    question: "Found draft: spec/.drafts/{slug}.md. Pick up where we left off?",
    header: "Resume draft?",
    multiSelect: false,
    options: [
      {
        label: "Yes, resume (Recommended)",
        description: "Continue from the last accepted section of this draft."
      },
      {
        label: "No, start fresh",
        description: "Ignore the draft and begin a new /spec session from Phase 1."
      },
      {
        label: "Show me what's in the draft first",
        description: "Print the current state of the draft before deciding."
      }
    ]
  }]
)
```

### Phase 2: Research

Before writing any PRD content, gather information from three sources. Present
a research summary to the user before proceeding to spec writing.

**Phase 2 Step 0: Allocate the feature directory (F<NNN>) FIRST.**

Allocate the feature ID at the very start of Phase 2 — BEFORE any research
runs, BEFORE Phase 2.5 gray-area resolution, and BEFORE any other write under
`.etc_sdlc/features/`. Every subsequent file write in Phases 2, 2.5, and 5
lands inside the freshly-allocated `F<NNN>-<slug>/` directory.

Derive the slug from the user's intent (Phase 1 answers) using the same
kebab-case convention as `scripts/feature_id.py::slugify`. Then invoke the
allocator CLI:

```
python3 ~/.claude/scripts/feature_id.py allocate-next .etc_sdlc/features "<slug>"
```

The CLI prints a single space-separated line to stdout: `<feature_id> <feature_path>`
(e.g. `F042 .etc_sdlc/features/F042-add-user-auth`). A runtime conductor
parses the output as follows:

- The **first token** is `<feature_id>` (e.g. `F042`).
- The **second token** is `<feature_path>` (the freshly-created directory).

Capture both into skill-local state. Reference them throughout the rest of
the skill as `<feature_id>` and `<feature_path>`. Phase 2.5 writes
`<feature_path>/gray-areas.md`. Phase 5 writes `<feature_path>/spec.md`,
`<feature_path>/value-hypothesis.yaml`, `<feature_path>/state.yaml`, and
`<feature_path>/research/`.

The allocator is POSIX-atomic (BR-003 / AC-002): concurrent /spec
invocations get distinct IDs. On a non-zero exit code, surface the stderr
to the user via Pattern B and STOP — Phase 2 cannot proceed without an
allocated feature directory.

**Dispatch these research tasks in parallel:**

1. **Codebase Exploration** -- Read the existing codebase to understand context:
   - What frameworks and patterns are in use?
   - What code will this feature touch or extend?
   - What tests exist for adjacent functionality?
   - Does `INVARIANTS.md` exist? If so, what contracts apply to this feature?
   - What naming conventions, module structure, and architectural patterns are established?

2. **Web Research** -- Search for established patterns, documented
   pitfalls, and applicable standards for this feature type:
   - Documented patterns for this feature type (OWASP for auth, RFC
     references for protocol work, framework-official guides for the
     libraries in use)
   - Security considerations: OWASP Top 10 entries that apply, known
     CVEs for the specific libraries this feature will use
   - Documented failure modes and boundary-condition bugs from the
     framework's issue tracker, library changelogs, or vendor advisories
   - Relevant library or framework documentation for the exact version
     pinned in the repo

3. **Antipatterns Check** -- Read `.etc_sdlc/antipatterns.md` if it exists:
   - Are any past antipatterns relevant to this feature?
   - Incorporate prevention rules from relevant AP entries into the spec

4. **Research-Fill of Identified Gaps (the fillable test)** — after the
   three research tasks above complete, walk the list of requirements
   identified so far and, for each requirement that is missing an
   answer, apply the **fillable test**:

   > Can I ground my answer in citable evidence, or do I need to ask?

   A gap is **research-fillable** if at least one of the following
   yields a citable answer:

   - A codebase grep finds a canonical pattern.
   - An existing doc cites the answer (`DOMAIN.md`, an ADR,
     `INVARIANTS.md`, an adjacent PRD, a tier-1 standard).
   - Web research finds a universally-accepted best practice with no
     competing alternatives in this codebase's context.
   - An adjacent test file shows the expected shape.

   A gap is **unfillable** if any of the following hold:

   - Multiple plausible answers exist and the codebase does not pick
     between them.
   - The answer depends on business intent or product scope.
   - The answer depends on roadmap ordering.
   - The answer is a policy decision.

   For each research-fillable gap, record a gray-area entry with
   `decided_by: research` plus a `citation` (file path or URL) and a
   one-line resolution rationale. These entries are written to
   `<feature_path>/gray-areas.md` during Phase 2.5 using the extended
   schema (the F<NNN>-<slug> directory was allocated in Phase 2 Step 0
   above). For each unfillable gap, record a gray-area entry with
   `decided_by: user` and leave it for Phase 2.5 to surface to the user
   (or for Phase 2.75 to fold into a rejection).

   The user sees every research fill during Phase 3 section review and
   may override any of them through the normal section-refinement flow.

**Present the research summary to the user** (as prose — this is status
output, not a question), followed by an `AskUserQuestion` prompt for the
next action:

```
Research Summary:

Codebase:
- [key findings about patterns, adjacent code, invariants]

Best Practices:
- [key findings from web research]

Antipatterns:
- [relevant AP entries, or "No antipatterns file found"]
```

Then ask:

```
AskUserQuestion(
  questions: [{
    question: "Research looks sufficient?",
    header: "Research",
    multiSelect: false,
    options: [
      {
        label: "Yes, proceed to spec writing (Recommended)",
        description: "Research covers the codebase, the documented patterns from web sources, and the antipatterns file. Move to Phase 2.5 gray-area resolution."
      },
      {
        label: "Research more",
        description: "Name a specific topic to dig deeper on. I'll research and re-present the summary before proceeding."
      },
      {
        label: "Skip research for this one",
        description: "Small or self-contained features may not need additional research. I'll note the skip and proceed — but /implement may push back later if context is thin."
      }
    ]
  }]
)
```

If the user picks "Research more", ask via Pattern B for the specific
topic, do the research, and re-invoke the `AskUserQuestion` above.

### Phase 2.5: Gray Area Resolution

Before writing the spec, systematically identify **decisions that could go either
way** — architectural choices, technology selections, design trade-offs where the
research found multiple valid options.

Print a numbered summary of the gray areas you found as status output:

```
I found N gray areas that need your input before I write the spec:

1. **[Decision topic]** — research found: [trade-off summary]
2. **[Decision topic]** — research found: [trade-off summary]
3. ...
```

Then resolve them ONE AT A TIME using `AskUserQuestion` (Pattern A —
multi-choice is a perfect fit for gray areas because each has 2-4
enumerable options from the research). Do NOT batch all gray areas into
a single question — resolving them sequentially lets the user build
confidence and lets earlier decisions constrain later ones.

For each gray area:

```
AskUserQuestion(
  questions: [{
    question: "<decision topic>: <one-sentence framing>?",
    header: "<≤12-char chip label>",
    multiSelect: false,
    options: [
      {
        label: "<Option A> (Recommended if you have a research-backed default)",
        description: "<one-sentence trade-off for this option, from research>"
      },
      {
        label: "<Option B>",
        description: "<one-sentence trade-off>"
      },
      {
        label: "<Option C — if it exists>",
        description: "<one-sentence trade-off>"
      }
    ]
  }]
)
```

If the user picks "Other" (AskUserQuestion's automatic escape hatch) to
provide a custom answer, record it verbatim and continue.

Wait for ALL gray areas to be resolved before proceeding.

Save resolutions to `<feature_path>/gray-areas-spec.md` (NEW features
post-F006) using the **extended schema** (the previous schema is the
first four lines; the bottom two lines are required for
`decided_by: research` entries and optional for `decided_by: user`
entries). `<feature_path>` is the F<NNN>-<slug> directory allocated in
Phase 2 Step 0 — `gray-areas-spec.md` lands directly under it, never
under a slug-only path. Forward-only: F001-F009 retain the legacy
`gray-areas.md` filename and are not migrated. Per F006 BR-009 the
new naming applies only to features authored AFTER F006 ships:

```markdown
# Gray Areas — Resolved Decisions

## GA-001: [Topic]
- **Options:** [A] vs [B]
- **Decision:** [chosen option]
- **Rationale:** [why]
- **Decided by:** research | user | rejected
- **Citation:** [file path, URL, or adjacent PRD]   # required when Decided by = research
- **Resolution rationale:** [one-line evidence summary]   # required when Decided by = research
```

The `Decided by` field is a controlled enum taking one of `research`,
`user`, or `rejected`. Research fills (recorded during Phase 2) use
`research` and MUST include the `Citation` and `Resolution rationale`
fields. User-resolved gaps (recorded during Phase 2.5) use `user`.
Gaps that triggered rejection (recorded during Phase 2.75) use
`rejected` and are copied into `rejected.md` alongside the gray-area
file.

**Backward compatibility:** Readers MUST tolerate legacy entries that
omit `Citation` and `Resolution rationale`, and MUST tolerate legacy
`Decided by` values written as free-form text — illustrative legacy
form: `Decided by: user, 2026-03-01` (illustrative; not exhaustive).
Only newly-written entries are guaranteed to use the controlled enum.

These resolutions will be:
- Incorporated into the PRD's Technical Constraints section
- Injected into subagent context during implementation
- Referenced by acceptance criteria

If no gray areas are found, state explicitly: "No gray areas identified —
research findings are unambiguous." and proceed.

### Phase 2.75: Threshold Check and Classification

Before entering Phase 3, classify the PRD into one of three states:

1. **Well-specified** — every requirement has a concrete answer. No user
   intervention is needed beyond the existing section approvals.
2. **Research-fillable (research-assisted)** — some requirements were
   missing, but codebase evidence or web research resolved them during
   Phase 2. Proceed to Phase 3; the fills surface during section review.
3. **Rejected** — too many requirements are missing, or too many gaps
   are unfillable, to proceed without human refinement of the input.

Count the following from the Phase 2 research-fill pass and the
Phase 2.5 gray-area resolution:

- `total_requirements` — the number of requirements identified during
  Phase 1 and Phase 2.
- `filled_by_research` — gaps closed with `decided_by: research`.
- `unfillable_gaps` — gaps marked `decided_by: user` that are still
  pending (i.e., surfaced to the user but not yet resolved).

Let `fill_ratio = (filled_by_research + unfillable_gaps) / total_requirements`.

Apply the classification rules:

- If `total_requirements == 0`: **reject** with reason "no requirements
  identified; the input is not a PRD candidate." (avoids divide-by-zero
  and catches nonsense inputs).
- Else if `unfillable_gaps == 0` and `fill_ratio <= FILL_RATIO_RESEARCH_ASSIST_MAX`:
  **well-specified / research-assisted**. Skip the user gray-area session
  and proceed directly to Phase 3.
- Else if `fill_ratio <= FILL_RATIO_REJECT_MIN` and `unfillable_gaps <= UNFILLABLE_GAP_REJECT_CAP`:
  **research-assisted with user gray areas**. Run the existing Phase 2.5
  user-facing gray-area flow, but **only on the unfillable gaps**. The
  research fills are already recorded and are not re-asked.
- Else (`fill_ratio > FILL_RATIO_REJECT_MIN` OR `unfillable_gaps > UNFILLABLE_GAP_REJECT_CAP`):
  **rejected**. Transition to the Rejection Flow below instead of
  Phase 3. Do NOT write `spec.md`.

Note: the numeric literals `0.20`, `0.50`, and `3` never appear inline
in the workflow prose above — only the constant names do. Tuning the
thresholds is a one-line diff at the top of this skill file.

### Rejection Flow

Triggered only when Phase 2.75 classifies the PRD as rejected.

1. Do NOT write `spec.md`. Under no circumstances does the rejection
   path produce a spec file.
2. Write `<feature_path>/rejected.md` (the F<NNN>-<slug> directory
   allocated in Phase 2 Step 0) with this layout:

   ```markdown
   # PRD Rejected: {feature slug}

   **Reason:** {which threshold was exceeded, by the numbers}
   - total_requirements: {N}
   - filled_by_research: {M}
   - unfillable_gaps:    {K}
   - fill_ratio:         {fill_ratio:.2f}
   - Threshold exceeded: {FILL_RATIO_REJECT_MIN | UNFILLABLE_GAP_REJECT_CAP | zero-requirements}

   ## Unanswered questions (answer these before resubmitting)
   1. {specific question derived from unfillable gap #1}
   2. {specific question derived from unfillable gap #2}
   ...

   ## Research fills already performed (preserved so you don't redo work)
   - {gap} → {resolution} — source: {citation}
   - ...

   ## Next action
   Refine the input to answer the questions above, then re-run:

       /spec {slug}
   ```

3. Mirror any `decided_by: research` fills into the rejection report so
   the human does not have to redo research when resubmitting the
   refined PRD.
4. **Move the rejected feature directory to `.etc_sdlc/rejections/`.**
   After `rejected.md` is fully written (including the research-fill
   mirror in step 3), relocate the entire feature directory — including
   `rejected.md`, `gray-areas.md`, any partial `value-hypothesis.yaml`,
   and the `research/` subtree — to the rejections location. Use
   `git mv` so the rename is canonical in the index (a plain `mv`
   followed by `git add` loses the rename through git's similarity
   heuristic). Invoke via `subprocess.run` with an argv list, never a
   shell string, so operator-controlled feature slugs cannot inject
   shell metacharacters:

   ```python
   from pathlib import Path
   import subprocess, sys

   rejections_root = Path(".etc_sdlc/rejections")
   rejections_root.mkdir(parents=True, exist_ok=True)

   target = rejections_root / f"F{nnn:03d}-{slug}"
   result = subprocess.run(
       ["git", "mv", str(feature_path), str(target)],
       capture_output=True,
       text=True,
   )
   if result.returncode != 0:
       sys.stderr.write(
           f"git mv failed: {feature_path} -> {target}\n"
           f"git stderr: {result.stderr}"
       )
       sys.exit(1)
   ```

   The `mkdir(parents=True, exist_ok=True)` call is race-safe and
   creates the `.etc_sdlc/rejections/` parent the first time the
   rejection flow ever fires. On `git mv` failure (target already
   exists, git refuses for any reason), exit non-zero with a stderr
   message that names the source path, the target path, and git's
   stderr verbatim — no silent swallow. After this step the feature
   directory lives at `.etc_sdlc/rejections/F<NNN>-<slug>/` and is no
   longer under `.etc_sdlc/features/active/`.

5. Surface the rejection to the user using Pattern B (the visual
   marker), because the message is a status/error announcement, not a
   question. Name the rejected file path and the next action:

   ```

   ---

   **▶ Action required:** PRD rejected. Answer the questions in
   `.etc_sdlc/features/{slug}/rejected.md` and re-run `/spec {slug}`.

   ```

6. Exit the skill. Do not proceed to Phase 3, Phase 4, or Phase 5. The
   feature directory will contain `rejected.md` but NOT `spec.md`; the
   two files are mutually exclusive.

### Phase 3: Iterative Spec Writing

Write the PRD section by section. For EACH section:

1. **Print the drafted section as status output** (prose, not a question).
   Include the full section body so the user can read exactly what will
   land in the PRD.
2. **Prompt for approval via `AskUserQuestion`** using the standard
   section-approval template below. Pattern A fits because the user's
   response is always one of three enumerable actions (accept / refine
   / research more).

Write sections in this order:

1. **Summary**
2. **Scope (In/Out)**
3. **Requirements (BR-NNN)**
4. **Acceptance Criteria**
5. **Edge Cases**

`/spec` authors intent only. Architectural sections — Technical
Constraints, Security Considerations, Module Structure, Architecture
overview, Data model, API contracts, Trade-offs — belong to `/architect`
(see F006). When the accumulated ACs imply engineering work, Phase 5
surfaces a Pattern A picker recommending `/architect` (see "Phase 5
auto-detect of engineering implications" below).

#### Section #4 (Acceptance Criteria) — Additional Steps

For Section #4 only, insert the following steps **between** printing the
initial AC draft (step 1 above) and invoking the section-approval
`AskUserQuestion` (step 2 above). These steps do not apply to any other
section.

**Step 4a: Auto-detect user-facing ACs.**

After producing the initial AC draft, scan each AC for user-facing
signals per `standards/process/user-flow-completeness.md`. Classify
every AC as `user-facing` or `backend-only` using the signal lists and
conflict-default rule documented in that standard (do NOT duplicate the
signal lists inline here — the standard is the single source of truth).

**Step 4b: Idempotency check.**

Before prompting per AC, check whether the AC already begins with the
canonical prefix `As {role}, navigate from` (or otherwise contains a
complete User-flow sentence matching that form). If it does, the AC is
already compliant — skip the per-AC elicitation prompt for that AC and
record it as `surface_status: compliant`. This ensures re-running `/spec`
on a fully-compliant spec adds nothing and prompts for nothing on this
dimension.

**Step 4c: Per-AC User-flow sentence elicitation.**

For each AC classified `user-facing` AND not already compliant (per
Step 4b), present the AC alongside a *prefilled draft* User-flow sentence
inferred from surrounding PRD prose. Use these inference sources to
construct the draft:

- `{role}` — the AC's grammatical subject or the PRD's stated user persona
- `{parent route}` — Module Structure entries or adjacent ACs that name a route
- `{affordance label}` — UI nouns mentioned in the AC text
- `{happy path}` — the AC's success criterion
- `{outcome}` — the AC's measurable claim

Print the AC and the draft sentence as status output (this is the
context the user reads before answering), then immediately invoke
`AskUserQuestion` (Pattern A):

```
AskUserQuestion(
  questions: [{
    question: "AC-N: accept, refine, or mark not-user-facing?",
    header: "AC-N surface",
    multiSelect: false,
    options: [
      {
        label: "Accept the draft User-flow sentence (Recommended)",
        description: "The prefilled sentence is appended verbatim to AC-N in the final spec."
      },
      {
        label: "Refine — I have changes",
        description: "I'll ask what to change via a Pattern B follow-up, revise the draft, and re-present this picker."
      },
      {
        label: "Mark this AC not-user-facing",
        description: "Record surface_status: backend_only for AC-N. No User-flow sentence is required."
      }
    ]
  }]
)
```

**If the user picks "Refine — I have changes"**, dispatch a Pattern B
free-form follow-up using the visual marker:

```

---

**▶ Your answer needed:** What would you change about the User-flow sentence for AC-N? Name specific edits to {role}, {parent route}, {affordance label}, {happy path}, or {outcome}.

```

Incorporate the response, update the draft sentence, then re-invoke the
`AskUserQuestion` above with the revised draft. Repeat until the user
accepts or marks not-user-facing.

**If the user picks "Accept the draft User-flow sentence (Recommended)"**,
append the sentence verbatim to its parent AC in the spec body.

**If the user picks "Mark this AC not-user-facing"**, record
`surface_status: backend_only` inline on that AC — no User-flow sentence
is added.

**Step 4d: Free-form input sanitization.**

Per the Security Considerations for this feature (F001), Pattern B
refinement input flows verbatim into `spec.md`. Apply the same
sanitization contract used elsewhere in this skill: strip every
control-character codepoint (regex `[\x00-\x1f\x7f]`) and cap the
User-flow sentence at 512 characters (truncate excess). Sanitization
happens at the capture site, before the sentence is appended to the AC.

**After completing Steps 4a–4d for all user-facing ACs**, proceed to the
standard section-approval `AskUserQuestion` (step 2 of the outer loop)
to get final approval on the entire Acceptance Criteria section.

For each section, after printing the draft, invoke this template
(substituting the section name into `header`, `question`, and the
option descriptions):

```
AskUserQuestion(
  questions: [{
    question: "{Section name} — does this capture what you want?",
    header: "{Section name}",
    multiSelect: false,
    options: [
      {
        label: "Accept and proceed (Recommended)",
        description: "The {section name} looks right. Save this section and move to the next."
      },
      {
        label: "Refine — I have changes",
        description: "I'll ask for specific changes via Pattern B and revise this section before moving on."
      },
      {
        label: "Research more first",
        description: "This section needs more investigation. I'll do the research and re-draft before asking again."
      }
    ]
  }]
)
```

If the user picks "Refine", ask for the specifics via Pattern B:

```

---

**▶ Your answer needed:** What would you change about the {section name}? Name specific additions, removals, or rewordings.

```

Then revise and re-invoke the approval template. Repeat until accepted.

If the user picks "Research more", ask via Pattern B what to research,
do the research, and re-draft + re-ask for approval.

Save in-progress work to `spec/.drafts/{slug}.md` after each accepted
section, so the user can resume in a new session.

### Phase 4: Validation

After all sections are written and approved, run the Definition of Ready
checklist. This is the same checklist `/implement` uses to decide whether a PRD
is buildable. Architectural items (concrete module structure, technical
constraints, security considerations) are NOT in /spec's DoR — they
belong to /architect's DoR (see F006 BR-001). /spec's DoR validates
intent only:

- [ ] Specific enough to implement without ambiguity
- [ ] Names concrete files where given (intent-level, not architectural module structure)
- [ ] Has measurable acceptance criteria. Every user-facing AC also includes a User-flow sentence per `standards/process/user-flow-completeness.md`.
- [ ] Scope boundaries are clear
- [ ] Edge cases documented

#### User-Flow Gate (BR-004, AC7)

After evaluating the six DoR items above, run the user-flow gate.

**Enumerate offending ACs.** Collect every AC that Phase 3 Section #4
flagged as user-facing (i.e., not recorded as `surface_status: backend_only`
and not recorded as `surface_status: compliant`) and that does not yet
contain an accepted User-flow sentence. These are the offending ACs.

**If no offending ACs exist**, the gate passes silently — proceed to the
"If all items pass" / "If any items fail" iteration logic below.

**If one or more offending ACs exist**, first emit a prose status block
(NOT a question) enumerating each by number. For example:

```
User-flow gate — missing User-flow sentences:
  AC-3: "User sees the confirmation modal after submit" — no User-flow sentence authored
  AC-7: "Clicking Save navigates to the dashboard" — no User-flow sentence authored
```

Then immediately invoke Pattern A:

```
AskUserQuestion(
  questions: [{
    question: "User-facing ACs are missing User-flow sentences. Continue without them?",
    header: "User-flow gate",
    multiSelect: false,
    options: [
      {
        label: "No, fix the missing sentences first (Recommended)",
        description: "Return to Phase 3 Section #4 and complete the per-AC elicitation for each offending AC. The DoR check re-runs after edits."
      },
      {
        label: "Yes, ship without — these surfaces are intentionally deferred",
        description: "Append a `surface_status: deferred` line per offending AC to the Edge Cases section. The deferral is recorded in spec.md so future readers can audit. Proceed to Phase 5."
      }
    ]
  }]
)
```

**Gate is a WARN, not a hard-block.** Backend-only surfaces and
intentionally-unreleased features are legitimate reasons to proceed without
User-flow sentences. The YES selection is recorded for audit, not silently
swallowed.

**Deferral path (BR-004, AC8).** When the author selects "Yes, ship without
— these surfaces are intentionally deferred", the skill MUST append one line
per offending AC to the spec's Edge Cases section before proceeding to
Phase 5. The line format is:

```
- AC-<N> surface_status: deferred — User-flow sentence not authored at spec time.
```

For example, if AC-3 and AC-7 were offending, append to Edge Cases:

```
- AC-3 surface_status: deferred — User-flow sentence not authored at spec time.
- AC-7 surface_status: deferred — User-flow sentence not authored at spec time.
```

These lines are the audit trail. Future readers can locate them in the
Edge Cases section and add User-flow sentences when the surface is actually
wired up.

**Forward-only behavior (BR-007).** Legacy specs — those whose `spec.md`
predates this rule — are NOT auto-modified. When `/spec` resumes on a
legacy feature directory, Phase 3 detection runs on whatever ACs exist in
the current draft. If detection flags ACs as user-facing, the author retains
the per-AC dismissal options (Step 4c) AND the Phase 4 deferral gate as
their escape hatch. No existing `spec.md` content is modified without
explicit author action via one of those two paths. The phase gate never
inserts, edits, or deletes content in a legacy spec silently.

**If all items pass:** Tell the user the spec is ready and proceed to output.

**If any items fail:** Point out the specific gaps and ask the user to resolve
them before finalizing:

```
Definition of Ready check found gaps:

- [ ] Names concrete files where given
  Gap: AC-3 says "the auth endpoint" but never names the route or
  handler file. Which file or route does AC-3 actually mean?

- [ ] Edge cases documented
  Gap: The Edge Cases section is empty. Name at least one failure mode
  per user-facing AC.

Let's resolve these before finalizing.
```

Iterate until all items pass.

### Phase 5: Output

Once the Definition of Ready passes, execute these steps in order. The
discipline is **value-hypothesis-first**: `spec.md` is NOT written until
`value-hypothesis.yaml` exists with every required field populated. This
is AC-005 of the metrics-and-release-notes PRD and is non-negotiable —
shipping a spec without a hypothesis defeats the outcome-metric layer.

The feature directory was already allocated in Phase 2 Step 0 via
`python3 ~/.claude/scripts/feature_id.py allocate-next` — `<feature_id>`
and `<feature_path>` are in skill-local state. Phase 5 does NOT
re-allocate; it only writes inside the existing `<feature_path>`.

#### Phase 5 auto-detect of engineering implications (F006 BR-002)

BEFORE Step 1 (the value-hypothesis dict build), scan the accumulated
ACs for engineering-signal tokens. Surface a Pattern A picker
recommending `/architect` when any signal fires.

**Engineering-signal token list (the documented signals; matching is
ALL-of-set, not any-of-set — any single hit is sufficient):**

- **File paths** — match the regex `[a-z][a-z0-9_/.-]+\.(py|ts|tsx|md|sh|yaml|yml)`.
- **Identifier + import/use/extend verbs** — a camelCase or snake_case
  identifier paired with `import`, `from`, `use`, `uses`, `extend`,
  `extends`, `subclass`, `implements`, or `inherits`.
- **HTTP method tokens** — `GET`, `POST`, `PUT`, `DELETE`, `PATCH`
  paired with `/api/` or any URL-route pattern.
- **DB schema language** — `table`, `column`, `index`, `migration`,
  `schema`, `alter`.
- **User-flow sentence** — any AC that carries the canonical prefix
  `As {role}, navigate from` per F001 BR-002. The presence of a
  user-flow sentence implies a user-facing surface and therefore
  engineering work.

If at least one signal fires across the AC set, surface this
`AskUserQuestion` (Pattern A) before Step 1:

```
AskUserQuestion(
  questions: [{
    question: "Engineering implications detected — run /architect now?",
    header: "Run /architect?",
    multiSelect: false,
    options: [
      {
        label: "Yes — chain /architect now (Recommended)",
        description: "After /spec finishes (Steps 1-9 below), auto-invoke /architect via the Skill tool with the just-written spec.md. Same session, same auth context."
      },
      {
        label: "Yes, but later",
        description: "Record the recommendation in state.yaml. /architect can be run manually later; /build will warn but proceed if design.md is absent."
      },
      {
        label: "This is non-engineering",
        description: "Skip /architect entirely. /build will still warn at Step 1c when it sees engineering-signal tokens but proceed regardless."
      },
      {
        label: "Yes, and mark design mandatory",
        description: "Chain /architect AND record that /build must HARD-fail without design.md. Stricter coupling for this feature only."
      }
    ]
  }]
)
```

If NO signals fire, skip the picker entirely and proceed to Step 1. The
`spec_phase.architect_recommendation` field is recorded as
`not_applicable` in that case.

**Recording the answer.** The selection is captured into skill-local
state and written into `state.yaml` at Step 7 below under
`spec_phase.architect_recommendation`. Allowed values:

- `chain_now` — the chain runs at the end of Phase 5 (Step 10 below).
- `chain_later` — operator runs `/architect` manually.
- `non_engineering` — the chain is suppressed; /build warns but
  proceeds.
- `chain_now_design_mandatory` — chain runs AND
  `spec_phase.design_mandatory = true` is recorded; /build will
  HARD-fail when design.md is absent.
- `not_applicable` — no engineering signals fired.

The picker is INFORMATIONAL with a load-bearing side effect — it
chooses whether `/architect` is auto-invoked at the end of Phase 5.
The downstream behavior matches the `--include-architect` flag (see
the Usage section).

1. **Build the value-hypothesis dict** with every required field
   populated. The required fields (BR-005 / AC-004) are:

   - `schema_version` — integer, currently `1`
   - `feature_id` — the `<feature_id>` from Phase 2 Step 0
   - `spec_author_role` — the role captured in Phase 1 (SME, Engineer,
     PM, Designer, or sanitized Other free-form). For NEW features
     (post-F006) write `spec_author_role`, NOT the legacy `author_role`.
     The schema validator at `scripts/value_hypothesis.py` accepts both
     shapes (per F006 BR-007); F001-F009 keep the legacy `author_role`
     unchanged.
   - `who` — target user / cohort the feature serves
   - `current_cost` — the baseline pain in human terms (what is hard or
     impossible today)
   - `predicted` — mapping with `metric`, `direction`
     (`increase` | `decrease`), and `threshold` (numeric)
   - `how_we_know` — the measurement plan (how we will tell whether the
     prediction held)
   - `status` — initial value `"pending"`
   - `validation` — initial value
     `{measured_at: null, measured_value: null, evidence: null}`

   Try to infer `who`, `current_cost`, `predicted`, and `how_we_know`
   from the PRD prose (Summary, Scope, Acceptance Criteria) where they
   appear unambiguously. For every required field that cannot be
   inferred, prompt the user via Pattern B, ONE FIELD AT A TIME:

   ```

   ---

   **▶ Your answer needed:** value-hypothesis `who` — who is the target user / cohort this feature is for?

   ```

   Repeat for `current_cost`, `predicted` (ask for metric, direction,
   and threshold separately), and `how_we_know` as needed. The file is
   never written with placeholders — every field is populated before
   the dict is dumped.

2. **Write `value-hypothesis.yaml`** to
   `<feature_path>/value-hypothesis.yaml`. Serialize the dict to YAML
   and write the file. Then validate it via the CLI:

   ```
   python3 ~/.claude/scripts/value_hypothesis.py validate <feature_path>/value-hypothesis.yaml
   ```

   Exit code 0 means schema-valid. On non-zero exit, the stderr names
   the missing or malformed field — fix the field via the same Pattern B
   prompt loop and retry the write + validate cycle. **Do not proceed to
   step 3 until this file exists and the validate CLI exits 0.**

3. **Write the final PRD** to `<feature_path>/spec.md`. spec.md MUST
   NOT be written until value-hypothesis.yaml is complete and schema-
   valid (AC-005). If the hypothesis prompt loop in steps 1-2 was
   abandoned for any reason, stop here — do not write spec.md.

4. **Copy to `spec/{slug}.md`** for backward compatibility and
   browsability (byte-identical copy of the PRD).

5. **Save research** to `<feature_path>/research/` (at least one of
   `codebase.md`, `web.md`, or `antipatterns.md`).

6. **Gray areas** are already saved from Phase 2.5 directly under
   `<feature_path>/gray-areas-spec.md` (NEW features post-F006). Phase 2
   Step 0 ran before Phase 2.5, so no path migration is needed.
   Forward-only: F001-F009 keep the legacy `gray-areas.md` filename
   (no rename), per F006 BR-009.

7. **Write the `spec_phase` block to `state.yaml`** using the
   merge-preserve pattern (F006 BR-008). Read the existing state.yaml
   into a dict, then mutate ONLY the `spec_phase` block; preserve every
   other top-level key (`build`, `architect_phase` if a prior
   `/architect` run exists, etc.) verbatim. Write the merged dict back.

   The `spec_phase` block schema:

   ```yaml
   spec_phase:
     classification: <well-specified | research-assisted | rejected>
     phase_2_75_metrics:
       fill_ratio: <float>
       unfillable_gap_count: <int>
       gaps_filled_by_research: <int>
       gaps_filled_by_user: <int>
     architect_recommendation: <chain_now | chain_later | non_engineering | chain_now_design_mandatory | not_applicable>
     design_mandatory: <true | false>     # true ONLY when architect_recommendation == chain_now_design_mandatory
     spec_author_role: <captured value>   # SME | Engineer | PM | Designer | sanitized free-form
     completed_at: <ISO-8601 UTC timestamp>
   ```

   Forward-only: F001-F009 retain top-level `classification` and
   top-level `author_role` fields and continue to work unchanged. The
   `state.yaml` consumer (`/build` Step 1a) reads `spec_phase.*` first
   and falls back to top-level fields for legacy features.

8. **Write the spec git tag.** Invoke the git_tags.py CLI to lay down
   the canonical spec-finalization tag at the current HEAD commit
   (BR-007 / AC-007). Substitute `<feature_id>` from Phase 2 Step 0:

   ```
   python3 ~/.claude/scripts/git_tags.py write-tag "etc/feature/<feature_id>/spec"
   ```

   The CLI degrades gracefully on non-git directories or repos with no
   HEAD — it exits 1 with a stderr warning rather than failing the
   whole spec. Treat exit codes 0 (created) and 1 (degrade) as both
   acceptable; only an exit code of 2 (hard error) is fatal.

9. **Remove the draft** from `spec/.drafts/{slug}.md` (if it exists).

10. **Report the summary:**

```
Feature directory: .etc_sdlc/features/active/F<NNN>-<slug>/
  spec.md                  — the PRD
  value-hypothesis.yaml    — outcome contract (BR-005, spec_author_role)
  state.yaml               — spec_phase block (classification + recommendation)
  gray-areas-spec.md       — N resolved decisions (NEW features post-F006)
  research/                — codebase + web findings

(New features land under features/active/. On /build terminal close
the directory is `git mv`'d to features/shipped/; rejected specs are
`git mv`'d to .etc_sdlc/rejections/.)

Also written to: spec/{slug}.md
Tag written:     etc/feature/F<NNN>/spec

Definition of Ready: PASSED
- [N] acceptance criteria
- [N] entries in the Edge Cases section
- [N] gray areas resolved
- [N] files in scope

Ready to build:
  /build .etc_sdlc/features/active/F<NNN>-<slug>/spec.md
```

11. **Auto-invoke `/architect` when the chain is requested
    (F006 BR-010).** The chain runs when EITHER of these conditions
    holds:

    - The `--include-architect` solo-flag was passed at invocation
      (see the Usage section).
    - The Phase 5 auto-detect picker recorded
      `spec_phase.architect_recommendation` as `chain_now` or
      `chain_now_design_mandatory`.

    When the chain is requested AND Phase 5 succeeded (DoR passed,
    value-hypothesis.yaml validated, classification != `rejected`),
    invoke `/architect` via the Skill tool with the just-written
    `<feature_path>/spec.md` as input. The chain runs IN THE SAME
    `/spec` SESSION — same auth context, NOT a subprocess invocation.
    `/architect` runs its own 5 phases and writes `design.md`,
    `gray-areas-architect.md`, ADRs under `docs/adrs/`, its own
    `architect_phase` block in `state.yaml`, and the
    `architect_author_role` field in the existing
    `value-hypothesis.yaml`.

    Two separate Phase 2.75 classifications result (one for /spec, one
    for /architect). Two separate git tag pairs are laid down.

    When the chain is NOT requested (`chain_later`, `non_engineering`,
    or `not_applicable`), Phase 5 ends after Step 10 — the operator
    runs `/architect` manually if and when they choose.

## PRD Output Format

The final PRD MUST use this format. This is what `/implement` expects:

```markdown
# PRD: [Feature Name]

## Summary
[1-3 paragraphs describing the feature, its motivation, and its value]

## Scope
### In Scope
- [specific items]
### Out of Scope
- [specific items]

## Requirements
### BR-001: [Business Rule Name]
[description of the rule]
### BR-002: [Business Rule Name]
[description]

## Acceptance Criteria
1. [Specific, measurable criterion]
2. [Another criterion]

## Edge Cases
1. [What happens when X]
2. [What happens when Y]

## Technical Constraints
- [Codebase patterns to follow]
- [Frameworks/libraries in use]
- [INVARIANTS.md rules that apply]

## Security Considerations
- [Based on web research and feature type]

## Module Structure
- [files to create or modify, with brief description of each]

## Research Notes
[Key findings from codebase and web research, preserved for implementer context]
```

## Security Consideration Auto-Population

Based on the feature type, auto-populate relevant security considerations as a
starting point. The user can add, remove, or modify these:

| Feature involves... | Auto-populate these considerations |
|--------------------|------------------------------------|
| Authentication | CSRF protection, session management, credential storage, brute-force prevention |
| User input (forms, APIs) | Input validation, injection prevention (SQL, XSS, command), request size limits |
| Data storage | Encryption at rest, access control, backup/recovery, PII handling |
| File handling | Path traversal, upload size limits, content-type validation, malware scanning |
| External APIs | Rate limiting, timeout handling, credential rotation, response validation |
| Authorization | Privilege escalation, IDOR, role hierarchy, default-deny policy |
| Email/notifications | Template injection, rate limiting, unsubscribe compliance |

## Constraints

- NEVER start writing the PRD before asking clarifying questions
- NEVER skip the research phase -- always research the codebase and web
- ALWAYS present each section for user approval before moving to the next
- ALWAYS validate against Definition of Ready before finalizing
- ALWAYS save in-progress drafts to `spec/.drafts/{slug}.md`
- ALWAYS write the final output to `spec/{slug}.md`
- Security considerations are auto-populated based on feature type, then refined by the user
- The PRD format MUST match what `/implement` expects (see PRD Output Format above)
- If the user says "research more about X" at any point, honor the request before continuing
- AP entries from `.etc_sdlc/antipatterns.md` are incorporated when relevant -- never ignored

## Post-Completion Guidance

After the PRD is finalized and written, print the status summary as
prose, then prompt the user via `AskUserQuestion`:

```
This PRD is solid and meets all Definition of Ready criteria.

  Feature directory: .etc_sdlc/features/{slug}/
  Acceptance criteria: N
  Gray areas resolved: M
  Files in scope: K
```

Then ask:

```
AskUserQuestion(
  questions: [{
    question: "PRD complete. What's next?",
    header: "Next step",
    multiSelect: false,
    options: [
      {
        label: "Kick off /build now (Recommended)",
        description: "Hand off to /build, which owns the full pipeline: validation, recursive decomposition, wave planning, per-wave Agent-tool dispatch to one subagent per leaf, and final verification. Recommended for most features because it exercises the whole pipeline."
      },
      {
        label: "Review decomposition first with /decompose",
        description: "Break the spec into tasks but pause before execution so you can inspect the wave plan. Pick this when the feature is unfamiliar or high-risk."
      },
      {
        label: "Stop here — I'll run /build later",
        description: "Leave the spec in .etc_sdlc/features/{slug}/spec.md and return to it when you're ready. Spec is safe on disk; /build --resume can pick it up."
      }
    ]
  }]
)
```

Always present `/build` as the recommended default. Wait for the user's
selection before executing anything.

## Definition of Done

`/spec` is done for a given invocation when ALL of the following
observable artifacts exist and pass. The exact set depends on the
Phase 2.75 classification, so the checklist branches: items 1-3 always
apply, items 4-8 apply to the well-specified and research-assisted
paths, and item 9 applies to the rejected path (in which case items 4-8
are explicitly N/A, not skipped).

1. `.etc_sdlc/features/{slug}/` exists as the feature directory.
2. `.etc_sdlc/features/{slug}/state.yaml` exists and records the
   Phase 2.75 classification in its `classification` field, using
   exactly one of the controlled enum values `well-specified`,
   `research-assisted`, or `rejected`. The schema is load-bearing for
   `/build` Step 1a; do not rename fields or values.
3. `.etc_sdlc/features/{slug}/gray-areas.md` exists. If no gray areas
   were found, the file contains the literal sentinel line "No gray
   areas identified — research findings are unambiguous." If gray
   areas exist, every entry uses the extended schema (`Decided by`
   enum = `research` | `user` | `rejected`, with `Citation` and
   `Resolution rationale` required for `research` entries).
4. `.etc_sdlc/features/{slug}/spec.md` exists and has passed the
   Definition of Ready checklist from Phase 4. Every DoR item is
   checked. Exists ONLY on the well-specified and research-assisted
   paths.
5. `spec/{slug}.md` exists as a byte-identical copy of
   `.etc_sdlc/features/{slug}/spec.md`, for browsability.
6. `.etc_sdlc/features/{slug}/research/` exists and contains at least
   one of `codebase.md`, `web.md`, or `antipatterns.md` capturing the
   Phase 2 findings. An empty directory is NOT sufficient.
7. `spec/.drafts/{slug}.md` has been removed (if it existed during the
   session). In-progress drafts are not artifacts of a completed spec.
8. The Phase 5 output summary and the Post-Completion Guidance
   `AskUserQuestion` have been rendered to the user. Apply to all
   non-rejected paths.
9. REJECTED PATH ONLY: `.etc_sdlc/features/{slug}/rejected.md` exists
   with the layout defined in the Rejection Flow (`Reason`, threshold
   figures, unanswered questions, preserved research fills, next
   action). `spec.md` MUST NOT exist alongside `rejected.md` — the two
   files are mutually exclusive and that exclusivity is how `/build`
   Step 1a distinguishes a rejected feature from a build-ready one.

If any applicable item is not satisfied, `/spec` is NOT done,
regardless of how many phases reported internal success. Do not report
"PRD complete" on the non-rejected paths unless every item 1-8 holds,
and do not report "PRD rejected" on the rejected path unless items 1-3
and item 9 hold.
