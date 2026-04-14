# Research Discipline — Consult Current Docs Before Reading Source

When a third-party framework, library, or tool isn't behaving the way
you expect, your first move is to consult **current documentation**.
Reading source, disassembling bundled artifacts, or reverse-engineering
framework internals is a last resort, not a first step.

## The Rule

Before spending more than ~5 minutes tracing framework internals:

1. **Query `context7`** for the library's current docs. Claude Code
   ships the `context7` MCP server — use it. It returns
   version-accurate documentation keyed to the library name and topic.
2. **Check the framework's official reference site** if context7 is
   ambiguous. Framework authors publish canonical how-tos for the
   common customizations, and they update them when APIs change.
3. **Grep the framework's repo** for the symbol you're trying to use,
   or for the feature name. Public repos usually have integration
   tests that demonstrate the "supported way" to do what you want.
4. **Only then** read built artifacts, disassembled bundles, or
   transpiled output. If you find yourself running `prettier` over
   `dist/**/*.js` to understand how a framework works, stop and
   re-query the docs — you are almost certainly fighting an API that
   has a first-class alternative two lines of docs away.

## Why This Rule Exists

Framework authors document the supported way to do the thing you're
trying to do. The "wrong way you're fighting" usually has a supported
alternative that is:

- **Cheaper to find** — one query instead of an hour of code archaeology.
- **More durable** — supported APIs survive version bumps; internal
  patterns get refactored out from under you.
- **Better tested** — the supported path has the framework team's test
  suite behind it.
- **Easier to hand off** — a future agent (or human) can re-derive your
  decision from a docs link. They cannot re-derive it from "I spent 40
  minutes staring at a minified Worker bundle."

Reading source is a legitimate tool when docs genuinely fail you. But
"I didn't check the docs first" and "the docs didn't answer my
question" are different states, and only one of them justifies
disassembly.

## The Ordering Heuristic

When a customization isn't behaving as expected, apply this order:

| Step | Tool | Time budget |
|------|------|-------------|
| 1 | `context7` MCP query | 30 seconds |
| 2 | Framework's official docs / reference site | 2 minutes |
| 3 | Framework's public repo — grep for the feature name | 5 minutes |
| 4 | Framework's integration test suite | 5 minutes |
| 5 | Read source / disassemble bundles | As long as it takes |

If you hit step 5 before step 1, you have inverted the cost gradient.
The rule is: **try the cheapest, most-likely-to-work source first**.
Current docs are almost always both.

## Origin

This rule was adopted on 2026-04-14 after a session spent ~40 minutes
disassembling a built Worker bundle to explain why setting
`Cache-Control` headers inside a `defineHandlerCallback` wasn't
surfacing on production responses. The correct API was
`createFileRoute({ ..., headers: () => ({...}) })`, documented at
`framework/react/guide/isr.md` and findable in a single `context7`
query. The 40 minutes of bundle archaeology was pure waste — the
docs had the answer on page one.

The postmortem caught this as a research-ordering mistake, not an
escaped bug. It doesn't fit the `/postmortem` → antipatterns schema
(no phase-introduced, no gate-that-should-have-caught-it) because
nothing shipped broken — the mistake was in the research process
itself. That's why this lives in `standards/process/` as a
discipline, not in `.etc_sdlc/antipatterns.md` as an escaped bug.

## How This Gets Enforced

This standard is injected into every subagent's onboarding packet via
`hooks/inject-standards.sh` under the "Research Discipline" section.
Every subagent spawned by the harness — whether via `/build`,
`/implement`, or a direct Task dispatch — sees this rule at spawn
time, before it does any work.

There is no mechanical hook that blocks bundle disassembly — the rule
is too context-dependent for a deterministic check. Enforcement is via
context injection: every subagent reads this rule at spawn, so when it
faces the "why isn't this framework behaving?" moment, the rule fires
from working context instead of having to be recalled from training.

## When to Break This Rule

There is exactly one case where reading source before docs is correct:
**you have reason to believe the docs are wrong or missing**. This
happens with:

- Libraries whose docs lag behind the code (common in fast-moving OSS)
- Undocumented but stable APIs that the maintainers encourage via
  examples but not prose
- Debugging a specific version's behavior that differs from what the
  docs describe (regression, unreleased change, etc.)

In these cases, read source — but *state the reason* in your response
before you do. "I'm going to source first because the context7 docs
for version X don't mention Y and the framework repo's last commit on
that file was 3 months ago" is a valid escape hatch. "I'll just check
the source real quick" is not.
