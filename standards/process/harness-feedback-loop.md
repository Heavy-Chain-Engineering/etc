# The Harness Feedback Loop

The etc harness has two learning loops, and they catch different things.

## Loop 1 — `/postmortem` (per-project escaped bugs)

When a bug *ships* and is caught in the wild, `/postmortem` traces it to
a root cause, identifies which gate should have caught it, and appends a
prevention rule to `.etc_sdlc/antipatterns.md` in the project where it
happened. That file is injected into every future subagent's onboarding
context by `hooks/inject-standards.sh`, so the lesson fires from working
context the next time.

This loop is reactive and project-local. It catches what *shipped
broken*.

## Loop 2 — `harness-feedback` Stop hook (cross-project process lessons)

But not every lesson is an escaped bug. Sometimes a session surfaces a
pattern that wasted 40 minutes, or a workaround around a missing harness
feature, or a framework surprise that should have been in the onboarding
packet — and none of it shipped broken. These lessons fall through
`/postmortem`'s schema (no phase-introduced, no gate-that-should-have-
caught-it) because the process itself was the failure, not the code.

The `harness-feedback` hook catches these. It's a prompt-type Stop hook
that runs an LLM evaluator at the end of every turn, in every project,
under every etc-harness installation. Its job is one question:

> **Did anything happen in this turn where a harness rule could have
> prevented wasted time, a mistake, or a workaround?**

If yes, it emits a distinctive `📬 Harness feedback` block sized for
copy-paste into a new conversation with the etc repo. If no — which is
the 95% case — it returns `{"continue": true}` silently.

## The Six Triggers

The hook fires only when one of these specific failure modes is present.
Vague "be more careful" suggestions are refused at the rubric level:

1. **Research inversion** — agent read source before docs, grepped
   `dist/**/*.js`, disassembled bundles, or traced framework internals
   without first querying `context7`. The `research-discipline` rule is
   either not firing or not specific enough.
2. **Repeated mistake** — same class of bug fixed twice in one turn,
   same error message hit twice with the same root cause, or same code
   rewritten two ways. Two is the threshold; one recovery loop is fine.
3. **Manual workaround** — agent invented a sed one-liner, inline
   copy-paste, or manual file generation where a CLI flag, skill step,
   or hook would have been cleaner. The workaround is the signal.
4. **Time-wasted pattern** — agent spent >10 minutes on something with
   a one-shot documented answer. Inefficiency is the trigger, not
   failure — successful work that took 10x too long still counts.
5. **Framework/tool surprise** — behavior that was "obvious in
   hindsight" but the onboarding packet didn't warn about. If a one-
   line standards addition would have obviated the whole detour, it's
   a lesson.
6. **Near-miss gate** — an existing gate almost caught something but
   missed because of a narrow rule gap. The near-miss is the signal.

## The Output Format (load-bearing)

When the hook fires, it emits a block with a specific shape:

```
📬 Harness feedback — paste this into etc:
─────────────────────────────────────────────
**Observed in:** {project name}
**Date:** YYYY-MM-DD
**Trigger:** {one of the six trigger names}

**What happened**
[2-3 sentences, concrete and specific]

**Why the harness could have prevented it**
[1-2 sentences naming the layer that's missing]

**Proposed rule**
[concrete rule naming the file/hook/standards doc]

**Origin trace**
[one paragraph of context so the etc-repo agent can re-derive
the lesson without the full session transcript]
─────────────────────────────────────────────
```

The emoji, the rule lines, and the field names are all structural.
When a future agent working in the etc repo receives a pasted block, it
can parse these fields deterministically and implement the proposed
rule without re-deriving context.

## Context-Aware Routing

If the Stop hook detects it's running *inside* the etc repo itself
(cwd matches `etc-system-engineering` or similar markers), it changes
the marker line from "paste this into etc:" to "implement this now?"
— the block is otherwise identical. This lets the harness eat its own
dog food: when you're editing etc and a lesson surfaces, the hook
offers to close the loop immediately instead of asking you to copy
and paste.

## Signal-to-Noise Is the Whole Game

This hook runs on every Stop event across every project. If it emits
noise, the user will mute it and the feedback loop breaks. The rubric
refuses to emit unless:

- A specific trigger fired (not a vague reflection)
- A specific file/hook/standards doc is named in the proposed rule
- The change is actionable by a future agent without re-deriving
  context

Silence is the default. A quiet hook that fires once a week with a
load-bearing lesson is infinitely more valuable than a chatty hook
that fires every turn with generic advice.

## Closing the Loop

When a `📬 Harness feedback` block fires in a non-etc project:

1. **Copy the block** from the session output.
2. **Open a new conversation with the etc repo** (or the existing one
   if you have it open).
3. **Paste the block** as the next user message.
4. The etc-repo agent recognises the marker, parses the fields, and
   either implements the proposed rule directly or asks clarifying
   questions if the rule is ambiguous.
5. After the rule lands, the next `./install.sh` deploys it globally
   and the next session in any project benefits.

When the block fires *inside* the etc repo, the agent offers to
implement the rule in the same conversation — no copy-paste needed.

## Why This Loop Matters

The most valuable harness lessons come from watching real work fail
in unexpected ways. They cannot be anticipated upfront, and they rarely
show up in the project where they'd be most useful (you learn the
lesson in a consumer project; the fix belongs in the harness that
serves all consumer projects).

Without this loop, lessons leak. The user notices them, forgets to
write them down, and they re-occur a week later in a different project.
The hook's only job is to make "noticing" automatic and "writing it
down" frictionless.

This loop closes the gap between `/postmortem` (per-project escaped
bugs) and the harness's default onboarding packet (cross-project
process wisdom). Every lesson that flows through this loop becomes a
candidate for:

- A new line in `hooks/inject-standards.sh`
- A new standards doc under `standards/process/`
- A new check in an existing hook
- A new skill step in `/spec`, `/build`, `/implement`, or `/decompose`
- A new agent manifest rule

The feedback loop is non-blocking. If the hook fails, times out, or
returns garbage, the session proceeds normally — the CI-pipeline hook
on the same Stop event is the one that gates code quality. This hook
is advisory, not enforcing. That's why its `on_failure` is `allow`:
missing a lesson is a smaller cost than blocking the session.
