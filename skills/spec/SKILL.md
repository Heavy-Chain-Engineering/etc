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
/spec "Add user authentication"     -- start fresh from a one-liner
/spec                               -- resume most recent draft from spec/.drafts/
/spec spec/draft-auth.md            -- refine an existing draft
```

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

Do NOT proceed until the user has answered all five. If any answer is
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

**Dispatch these research tasks in parallel:**

1. **Codebase Exploration** -- Read the existing codebase to understand context:
   - What frameworks and patterns are in use?
   - What code will this feature touch or extend?
   - What tests exist for adjacent functionality?
   - Does `INVARIANTS.md` exist? If so, what contracts apply to this feature?
   - What naming conventions, module structure, and architectural patterns are established?

2. **Web Research** -- Search for best practices and common pitfalls:
   - Best practices for this type of feature
   - Security considerations (OWASP patterns, known CVEs for relevant libraries)
   - Common pitfalls and edge cases others have encountered
   - Relevant library or framework documentation

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
   `.etc_sdlc/features/{slug}/gray-areas.md` during Phase 2.5 using the
   extended schema. For each unfillable gap, record a gray-area entry
   with `decided_by: user` and leave it for Phase 2.5 to surface to the
   user (or for Phase 2.75 to fold into a rejection).

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
        description: "Research covers the codebase, best practices, and antipatterns. Move to Phase 2.5 gray-area resolution."
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

Save resolutions to `.etc_sdlc/features/{slug}/gray-areas.md` using the
**extended schema** (the previous schema is the first four lines; the
bottom two lines are required for `decided_by: research` entries and
optional for `decided_by: user` entries):

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
`Decided by` values written as free-form text (e.g. `Decided by: user,
2026-03-01`). Only newly-written entries are guaranteed to use the
controlled enum.

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
2. Write `.etc_sdlc/features/{slug}/rejected.md` with this layout:

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
4. Surface the rejection to the user using Pattern B (the visual
   marker), because the message is a status/error announcement, not a
   question. Name the rejected file path and the next action:

   ```

   ---

   **▶ Action required:** PRD rejected. Answer the questions in
   `.etc_sdlc/features/{slug}/rejected.md` and re-run `/spec {slug}`.

   ```

5. Exit the skill. Do not proceed to Phase 3, Phase 4, or Phase 5. The
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
6. **Technical Constraints**
7. **Security Considerations**
8. **Module Structure**

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
is buildable:

- [ ] Specific enough to implement without ambiguity
- [ ] Names concrete files, modules, endpoints
- [ ] Has measurable acceptance criteria
- [ ] Scope boundaries are clear
- [ ] Edge cases documented
- [ ] Security considerations addressed

**If all items pass:** Tell the user the spec is ready and proceed to output.

**If any items fail:** Point out the specific gaps and ask the user to resolve
them before finalizing:

```
Definition of Ready check found gaps:

- [ ] Names concrete files, modules, endpoints
  Gap: The Module Structure section says "relevant API files" but doesn't
  name specific files. Which files will be created or modified?

- [ ] Security considerations addressed
  Gap: This feature handles user input but has no mention of input
  validation or injection prevention. Should we add that?

Let's resolve these before finalizing.
```

Iterate until all items pass.

### Phase 5: Output

Once the Definition of Ready passes:

1. **Create feature directory:** `.etc_sdlc/features/{slug}/`
2. **Write the final PRD** to `.etc_sdlc/features/{slug}/spec.md`
3. **Copy to spec/{slug}.md** for backward compatibility and browsability
4. **Save research** to `.etc_sdlc/features/{slug}/research/`
5. **Gray areas** are already saved from Phase 2.5
6. **Remove the draft** from `spec/.drafts/{slug}.md` (if it exists)
7. **Report the summary:**

```
Feature directory: .etc_sdlc/features/{slug}/
  spec.md         — the PRD
  gray-areas.md   — N resolved decisions
  research/       — codebase + web findings

Also written to: spec/{slug}.md

Definition of Ready: PASSED
- [N] acceptance criteria
- [N] edge cases documented
- [N] security considerations
- [N] gray areas resolved
- [N] files in scope

Ready to build:
  /build .etc_sdlc/features/{slug}/spec.md
```

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
        description: "Validate, decompose recursively, execute wave-by-wave, verify. Recommended for most features because it exercises the whole pipeline."
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
