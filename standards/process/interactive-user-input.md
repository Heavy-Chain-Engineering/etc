# Interactive User Input — Two Patterns, No Prose Questions

## Status: MANDATORY
## Applies to: All skills, all agents that prompt the user

## The rule

**Never embed a question in your prose output and hope the user sees it.**
A question buried between agent status text and reasoning paragraphs gets
skimmed past — users miss it, respond to the wrong thing, or think the
agent is still working. Every interactive prompt MUST use one of the two
patterns below.

## Pattern A: Multi-choice decisions → `AskUserQuestion` tool

Use when the set of valid answers is enumerable (2–4 discrete options).
Examples: approve / refine / reject, create now / defer, merge / keep /
replace, binary yes/no, picking from a finite set of libraries or
approaches.

The `AskUserQuestion` tool renders as a dedicated picker UI outside the
text stream. The user cannot miss it because it visually breaks out of
the conversation flow into a structured chooser.

**Call shape:**

```
AskUserQuestion(
  questions: [{
    question: "The full question, ending with a question mark?",
    header: "Short chip label (≤12 chars)",
    multiSelect: false,
    options: [
      {
        label: "First option (Recommended)",
        description: "What this option means and what happens if chosen."
      },
      {
        label: "Second option",
        description: "What this option means and what happens if chosen."
      }
    ]
  }]
)
```

**Rules:**

- Use 2–4 options per question (tool enforces this).
- If you have a recommendation, put it first and append "(Recommended)"
  to the label. Do NOT add a separate "pick the recommended one" prompt
  — the label says it.
- The `description` is where you explain trade-offs. Keep it one or two
  sentences. This is shown in the picker alongside each option.
- Do NOT add an "Other" option — the tool provides that automatically.
- Never pair `AskUserQuestion` with a prose question about the same
  decision. Pick one pattern and commit.
- A single call may ask up to 4 independent questions at once
  (`questions: [...]` takes 1–4 items). Use this for batch confirmations.

**When NOT to use AskUserQuestion:**

- When the answer is free-form text and cannot be enumerated (see Pattern B).
- When the question is rhetorical in your own reasoning. Questions the
  agent is thinking through do not need user input.

## Pattern B: Open-ended elicitation → visual marker convention

Use when the answer is free-form and cannot be enumerated in 2–4 options.
Examples: "What domain does this business operate in?", "Describe the
failure modes." Any question that starts with "what", "why", "how",
"describe" is a Pattern B candidate.

**Render format:**

```

---

**▶ Your answer needed:** <the actual question, one line if possible>

```

The horizontal rule, blank lines above and below, and the bold arrow
prefix create a clear visual break in the text stream. The user's eye
lands on the arrow and the bold "Your answer needed" label. The question
is impossible to miss.

**Rules:**

- Put the question on its own line after the marker.
- If the question needs context — two illustrative forms are a
  priming instruction like "push back on marketing fluff" or a set of
  example answers — put the context ABOVE the marker block, not after.
  The user should see the question and be able to answer immediately
  without scrolling back up.
- Ask ONE question at a time in Pattern B. Do not batch open-ended
  questions — each one needs its own focused turn.
- Wait for the user's answer before moving on. Never answer your own
  open-ended question.

## Anti-patterns

### Questions buried in prose

```
Tier 1 written. Phase 3 Step 2 — Tier 2 prompt:

Will this project have multiple bounded contexts, architectural decision
records, or cross-cutting invariants? ... <long paragraph explaining
the trade-offs> ... Create Tier 2 now, or defer?
```

The question abuts the agent's own status output with no visual break.
Users skim past it. This is the form that prompted this standard.

### Stacked questions in one marker

```

---

**▶ Your answer needed:** What's the domain? Also what's the revenue model?
And what are the core entities?
```

Three questions in one marker. The user will answer the first one and
forget the others, or answer all three in a paragraph that's hard to
parse. Ask them one at a time.

### Prose + tool double-gating

```
<prose paragraph asking the same question>

AskUserQuestion(...)
```

Redundant. The user now has to reconcile two presentations of the same
question. Use the tool alone — its own `question` and `options[].description`
fields carry all the context you need.

### Rhetorical questions that look like prompts

```
Now let's think about the trade-offs. Should we use Redis or Postgres
for the cache? Well, it depends on ...
```

That's the agent thinking out loud, not a question for the user. Don't
use the visual marker for rhetorical questions — it trains the user to
ignore the marker. Reserve the marker for ACTUAL user input needed.

## How to verify this standard is being followed

1. **Contract tests in `tests/test_init_project.py::TestSkillMdContract`
   can be extended** to check any skill for these patterns. The existing
   `test_should_use_ask_user_question_for_multi_choice_prompts` and
   `test_should_document_visual_marker_for_open_questions` are templates.
2. **During skill review**, grep the SKILL.md for literal quoted strings
   ending in `?`. Every match should either be inside a Pattern A tool
   call or immediately preceded by a Pattern B visual marker.
3. **During dogfood runs**, watch for the "question got lost in prose"
   UX failure. If you find yourself scrolling back up to find what the
   agent just asked, the skill violates this standard.

## Client compatibility note

`AskUserQuestion` is a Claude Code tool. Skills that target other
clients (Antigravity / Gemini, Cursor, etc.) may not have an equivalent
tool available. In that case, Pattern B (the visual marker) is the
fallback for multi-choice decisions as well. Render the options as an
enumerated list under the marker:

```

---

**▶ Your answer needed:** Create Tier 2 directories now, or defer?

1. Create now (Recommended) — create docs/adrs/, docs/contexts/, docs/invariants/
2. Defer until needed — skip for now, re-run /init-project --phase=skeleton later

```

Claude Code users get the picker UI. Other clients get an enumerated
list with the same information. Do not maintain two versions of the
prompt text — write the list form and let Claude Code users enjoy the
picker when the tool is available.

## When in doubt

- Is the answer space enumerable in 2–4 options? → Pattern A.
- Is the answer free-form text? → Pattern B.
- Is it a rhetorical question in your reasoning? → Neither; just prose.
- Still unsure? → Default to Pattern B. It's never wrong, just less
  distinctive than Pattern A for multi-choice.
