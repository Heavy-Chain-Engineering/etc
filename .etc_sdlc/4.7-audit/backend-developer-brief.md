# Pre-edit brief: agents/backend-developer.md

Target file analyzed for 4.7 literalism gaps per migration spec section 6.2.

## Method

For each section of the file, I materialize:
- What the section says (literal 4.7 reading)
- What the section intended (4.6-era context)
- The gap, if any
- Which AP-NNN pattern applies
- The proposed fix

Sections not listed here were examined and found clean.

## Findings

### Frontmatter description — AP-001

**Literal:** "Writes idiomatic Python with strict typing" is a vague
quality descriptor. 4.7 has no anchor for what "idiomatic" or "strict"
means in this project.

**Intended:** Apply the conventions in `standards/code/python-conventions.md`
and the typing rules in `standards/code/typing-standards.md`. The agent
already reads these files in its "Before Starting" section, so the
knowledge is available — it just isn't connected to this descriptor.

**Gap:** Under 4.7 literalism, the descriptor becomes decorative. The
agent behaves based on the "Before Starting" reads, not the descriptor.
This is OK behaviorally but the descriptor is dead weight and reads
badly.

**AP:** AP-001 (vague directive).

**Fix:** Replace "idiomatic Python with strict typing" with a concrete
pointer: "Python per `standards/code/python-conventions.md` and
`standards/code/typing-standards.md`."

### Your Responsibilities #2 — AP-001

**Literal:** "Write idiomatic, fully typed Python."

**Intended:** Same as above — apply the two standards docs.

**Gap:** Same as above. The next two sentences provide concrete rules
(type annotations, no `Any`), so the "idiomatic, fully typed" opener
is redundant rather than harmful. But it's still an AP-001 hit.

**AP:** AP-001.

**Fix:** Replace "idiomatic, fully typed" with "fully typed and
conformant to `standards/code/python-conventions.md`." The existing
concrete rules remain.

### Before Starting — implicit fallback location

**Literal:** "If any file does not exist, note the gap but continue
with available context."

**Intended:** Record the missing file somewhere visible so a reviewer
can see the agent operated with incomplete context.

**Gap:** "Note the gap" doesn't specify where. Under 4.7 literalism,
the agent may write the note in a random place (completion report?
inline comment? nowhere?) or may skip it silently because the
instruction is ambiguous.

**AP:** Borderline AP-004 (no explicit trigger for where/how).

**Fix:** "If any file does not exist, list it in the 'Files Not
Available' section of your completion report and continue with
available context."

### Python Antipatterns #4 — AP-004

**Literal:** "Overly broad type annotations. `dict[str, Any]` when a
TypedDict or Pydantic model would be appropriate."

**Intended:** Use a TypedDict or Pydantic model when the set of keys
is known at design time; use `dict[str, Any]` only for truly open-
ended maps (e.g., arbitrary JSON from an external API).

**Gap:** "Would be appropriate" is the exact AP-004 phrasing. Under
4.7 literalism, "appropriate" is an unanchored inference. The agent
may leave `dict[str, Any]` in place because it can't decide when it
isn't appropriate.

**AP:** AP-004.

**Fix:** "Overly broad type annotations. `dict[str, Any]` when the set
of keys is known at design time (use TypedDict or Pydantic model
instead). `list[Any]` when the element type is known (use `list[T]`)."

### Output Format — AP-008 missing verbosity directive

**Literal:** The section describes what to produce (code, tests,
commits) and what to include in the completion report (files, test
counts, gaps). It does NOT specify format, length, or tone of the
report itself.

**Intended:** Terse, bulleted/tabular completion reports — no
narrative prose summaries, no preamble, no emoji, no "I completed
the task" validation openers.

**Gap:** Under 4.7's complexity-calibrated verbosity, a simple task
produces a short report and a complex task produces a long one. The
variance is larger than operators want — we want terseness regardless
of task complexity.

**AP:** AP-008.

**Fix:** Add to the end of the Output Format section:

> **Response format:** Terse. Bulleted or tabular. No preamble
> ("I'll...", "Here is..."). No narrative summary. No emoji. Report
> the facts (files changed, tests, gaps); do not explain or
> contextualize unless asked.

### Examples in description — safe, no change

The two `<example>` blocks in the frontmatter description are
illustrative of use cases, not scope-defining. They are concrete and
grounded. AP-010 (example-as-scope) does not apply because the blocks
are clearly bounded `<example>` XML elements, which 4.7 can parse as
structural.

### Tech Stack section — safe, no change

This is a reference inventory of frameworks. It contains no
instructional language. An agent reading this list doesn't infer WHEN
to use each framework from this section; the Decision Framework table
below does that explicitly. Leave as-is.

### Decision Framework table — exemplar, no change

This is the model we want elsewhere. Situation → Decision → Rationale
tables are ideal 4.7 input. Do not touch.

### Boundaries / Error Recovery / Coordination — clean

All three sections use specific, observable language. No AP matches.

## Summary of planned changes

| Section | AP | Edit type |
|---|---|---|
| Frontmatter description | AP-001 | Text replacement |
| Responsibilities #2 | AP-001 | Text replacement |
| Before Starting fallback | AP-004-ish | Text replacement |
| Python Antipatterns #4 | AP-004 | Text replacement |
| Output Format | AP-008 | Addition (new paragraph) |

Total edits: 5. No section deletions. No structural restructuring.

## Verification plan

After edits:

1. Run the AP grep sweep against `agents/backend-developer.md` alone.
   Expected: zero matches for AP-001, AP-004, and AP-008 patterns
   (AP-008 is absence-based; verify the new "Response format" paragraph
   exists).
2. Full repo AP sweep should show AP-001 count drops by at least 2
   (the two instances in this file) and AP-004 by 1.
3. Full test suite must still pass (409 tests). Agent definition edits
   cannot break tests, but run anyway as a regression check.

## Dispatched-subagent behavioral test (Phase 1 step 6.4 test B)

Plan: dispatch a `backend-developer` subagent against a small,
previously-built task to observe behavior. Options:

- A previously-completed task in `.etc_sdlc/features/hook-cost-reduction/`
  has concrete ACs and a known-passing outcome. Use one of those.
- Alternatively: a synthetic task that exercises the TDD cycle and the
  standards reads.

The test is behavioral, not mechanical. Observations:
- Did the subagent read the 7 standards files from "Before Starting"?
- Did it follow RED → GREEN → REFACTOR?
- Did its completion report match the new verbosity directive (terse,
  no preamble)?
- Did it produce working code and passing tests?

If all four observations check out, the prototype is validated.

## Known risks

1. **I may be under-specifying the verbosity directive.** "Terse" is
   itself somewhat vague. 4.7 may interpret it with a different
   threshold than intended. Mitigation: include concrete examples of
   preamble-to-avoid and acceptable-output shape in the fix.

2. **Pointing to standards docs may be redundant.** The agent already
   reads them in "Before Starting." Pointing to them again in the
   description/responsibilities could read as duplicative. Accept this
   — the duplication is deliberate. Redundancy is safer than vagueness
   under 4.7 literalism.

3. **Operator may disagree that the Decision Framework table is
   perfect as-is.** It's opinion. If the operator wants to change
   anything there, flag and re-examine. Per spec section 13.4
   (escape hatches), operator judgment overrides my assessment.
