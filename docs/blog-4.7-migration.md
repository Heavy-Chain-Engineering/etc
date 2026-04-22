# Notes From a Claude 4.6 → 4.7 Migration: What Breaks, Why, and How We Fixed It

**TL;DR.** Upgrading the model under our engineering harness exposed
months of latent fragility. The fix required 192 edits across 68
files, a new catalog of prompt anti-patterns, and an audit discipline
that couldn't rely on the broken tool to repair itself. The deeper
lesson: a more literal model isn't worse. It's a forcing function
that makes your harness be honest about what it wants.

---

## The moment the ground shifted

The day Claude Opus 4.7 rolled out, our engineering harness — a
compile-and-install pipeline of 24 specialized agents, 10 skills,
14 hooks, and 38 standards documents that enforces software
engineering discipline across an AI-assisted team — started doing
things we'd never seen before.

Agents that had been dispatching subagents correctly for months
began trying to do the work in their own context. Skills that
orchestrated multi-wave builds suddenly produced flat, single-turn
outputs. An adversarial code reviewer whose job was "find what's
wrong" started returning "looks fine" on code that obviously wasn't.
The hotfix lane's gate-bypass language — load-bearing for incident
response — started triggering unexpected refusals.

We hadn't changed any code. We'd upgraded a model.

## What actually changed in 4.7

Anthropic's migration guide lists nine behavioral differences. One
dominates the others:

> **More literal instruction following.** Claude Opus 4.7 interprets
> prompts more literally and explicitly than Claude Opus 4.6,
> particularly at lower effort levels. It will not silently
> generalize an instruction from one item to another, and it will
> not infer requests you didn't make.

Eight other changes matter — calibrated verbosity, fewer subagents
spawned by default, stricter effort adherence, cybersecurity
safeguards — but literalism is the force that amplifies all of them.

Here's what that means in practice. Consider a prompt that says:

> "Follow best practices for error handling."

A 4.6-era Claude would read that, pull from training knowledge about
Python exception handling, apply a reasonable interpretation, and
produce code that looked like it had actually thought about errors.
The prompt was a gesture; the model filled in the gesture with
generous inference.

A 4.7-era Claude reads that exact same prompt and... does nothing
specific. "Best practices" has no referent. There's no file to read,
no rule to follow. The instruction is literally unactionable. The
model either ignores it or satisfies it minimally (a `try/except`
around the happy path, maybe).

The model didn't get worse. The prompt was always under-specified.
The earlier model was generously papering over the gap. The newer
model isn't.

## The scope of the problem

Our harness is a prompt surface. Every one of the 24 agents has a
system prompt that says things like "you are a TDD zealot" and
"write idiomatic Python." Every one of the 10 skills has a
workflow that says things like "dispatch the tasks" and "verify the
output." Every one of the 38 standards docs has rules like "apply
where appropriate" and "consider edge cases."

Each of those phrases was a tiny gesture that worked under 4.6 and
silently failed under 4.7. We had 68 such files to audit.

## The paradox of self-repair

Here's where the problem gets interesting: **how do you fix a
prompt-driven tool using prompts, when the model you're using to do
the fixing is the same model whose behavior the tool is calibrated
for?**

You can't use the broken tool to fix itself. If we ran our harness's
own `/spec` and `/build` skills on the migration PRD, those skills
would dispatch subagents loaded with the broken agent definitions
we were trying to repair. The skills themselves had the same
inference-dependent language. Running the harness on itself would
propagate the bug into the fix.

The workaround: dispatch subagents with `subagent_type:
"general-purpose"` instead of through the harness's named agent
types. That bypasses the broken agent definitions; the subagent
gets a fresh context, and we write its full prompt inline. We still
use the model to do the edits — but we route around the scaffolding
that was itself under repair.

This is a bootstrapping pattern worth remembering. When the
abstraction is broken, go one level below it. Use direct tool calls
(Read, Edit, Bash) in the main thread. Dispatch subagents only
with explicit, inline prompts. Never rely on the specific named
agent whose definition you're fixing. The main thread does the
planning; the subagents do disposable leaf work.

## The second-order trap

One more wrinkle. The main-thread model is also 4.7. If I (as the
orchestrator) write a fix plan using 4.7-era habits — "follow the
AP-001 pattern for the rest," "apply similar fixes where
appropriate" — then I've written a plan with the exact same bugs
the plan is meant to fix. A future session that picks up this plan
after compaction will read it literally, miss the implicit
generalizations, and execute wrong.

So the plan itself has to be audited as you write it. Every step
needs to be explicit enough that a 4.7 reader executing with zero
inference produces the correct behavior. This is exhausting, but
it's also the whole point. If you can't write the plan to the
literalism standard, you can't expect your tool to meet it either.

## The audit framework

Once we accepted the scope, we needed a way to find the problem
prompts mechanically. Hand-review of 68 files was too slow and too
error-prone. What we built was a **catalog of prompt anti-patterns**
(internally: "AP-001" through "AP-013"), each with a grep pattern,
a diagnosis, and a concrete fix recipe.

Some examples:

| Anti-pattern | Grep pattern | Fix |
|---|---|---|
| AP-001: Vague quality descriptors | `best practices\|idiomatic\|proper\|robust` | Name the rule or point to a specific standards doc |
| AP-003: Edge-case gesturing | `edge case\|corner case` | Enumerate the cases that matter |
| AP-004: Unanchored triggers | `where applicable\|as needed` | Specify the explicit trigger condition |
| AP-006: Implicit subagent dispatch | `execute.*waves?\|dispatch.*tasks?` | Add explicit MUST/MUST NOT rules per the Agent tool |
| AP-008: Missing verbosity directive | (absence check) | Add a "Response Format" block with word caps |
| AP-011: Implicit Definition of Done | `when done\|once complete` | Numbered checklist of observable artifacts |
| AP-013: Reference without read-enforcement | structural check | Ensure every standards ref is in a forced-read list |

AP-013 was the most interesting. It emerged mid-audit, not from the
migration guide. The pattern: an agent prompt would reference a
standards doc ("conformant to `standards/code/python-conventions.md`")
but the agent had no mechanism — no explicit Read, no injection
hook, no required-reading list — that forced the file into context.
Under 4.6, the model would often read it anyway out of inference.
Under 4.7, it wouldn't. The reference became a promise the harness
didn't keep.

AP-013 is now a first-class structural invariant. Every agent
either has a "Before Starting: Read these files" section, or
relies on a mechanical injection hook, or uses task-level
`requires_reading` enforcement. No hope-based references.

## Execution

Five phases over a day. The sequencing was not arbitrary; it was
chosen to surface problems early and minimize blast radius.

**Phase 0: Baseline.** Count everything that might break. 409
tests. 17 gates. AP-NNN matches across the harness: 154 total.
Commit the current state as a rollback target.

**Phase 1: Prototype on one file.** Pick the highest-volume agent
(`backend-developer.md`). Write the pre-edit brief, apply the
edits, verify mechanically and behaviorally. Stop. Let a human
review before scaling. The idea: if the pattern is wrong, we find
out after 8 edits, not 200.

Phase 1 surfaced two sub-experiments worth repeating. The first
tested whether the updated prompt actually drove forced-file-reads
under 4.7 (it did — 3 of 7 files for a knowledge task; all 7 for
a code-writing task, exactly as the "before writing any code"
conditional dictated). The second tested whether the terse
verbosity directive held under real load (it did, across both
experiments). These empirical checks mattered because they
confirmed the mental model: 4.7 isn't broken; it's precise.
Precision is what we want.

**Phase 2: Scale to 22 more agents.** Five batches of ~5 agents
each, parallel within a batch (files are disjoint), sequential
between batches (to review diffs). Each subagent received the AP
catalog, the fix catalog, and a completed reference agent as a
pattern to mirror. Per-batch verification: AP grep zero, tests
green, compile counts unchanged.

**Phase 3: Skills.** Strictly sequential because skills reference
each other. Each skill is an orchestrator — the stakes are higher.
Phase 3 is where the **dispatch taxonomy** crystallized. Every skill
now declares itself either:

- **"Subagent Dispatch (Non-Negotiable)"** if it orchestrates (MUST
  dispatch via Agent tool, MUST NOT execute in own context,
  explicit rules for fan-out and sequencing)
- **"Subagent Dispatch (Non-Applicable)"** if it's an engine or CLI
  wrapper (explicit statement that this skill does NOT dispatch,
  plus enumeration of allowed in-context actions)

Both forms prevent the same 4.7 failure mode: a skill silently
drifting into or out of the orchestrator role because the prompt
didn't explicitly say which one it was.

**Phase 4: Hooks and standards.** The three agent/prompt-type hooks
in our SDLC spec (task-readiness, task-completion,
adversarial-review) each got rewritten. The biggest change:
adversarial-review's prompt shifted from open-ended ("what could go
wrong?") to an explicit eight-dimension checklist (error-handling
paths, null inputs, off-by-one, concurrent access, security
boundaries, failure-path test coverage, AC compliance, spec
compliance), each requiring either a concrete finding or the
literal string "no finding." Vague open questions were a 4.6
luxury.

31 standards docs audited across four parallel batches. **17 of the
31 (55%) were already 4.7-clean at baseline.** Standards docs are
authored deliberately over longer horizons; they don't accumulate
the gesture-drift that dispatch-flow documents do.

## What we found along the way

The audit was framed as "repair 4.7 literalism." In practice it was
also an archaeology expedition. Seven pre-existing latent bugs
surfaced because 4.7's literal reading broke what 4.6's generosity
had been hiding:

1. **`code-reviewer.md` referenced three standards files that
   didn't exist.** `quality-standards.md`, `naming-conventions.md`,
   `test-standards.md` — all in the forced-reads list, all missing
   from disk. Under 4.6, the agent would silently proceed. Under
   4.7, it would have failed or inferred something odd.

2. **`multi-tenant-auditor.md` had no "Before Starting" section at
   all.** It listed "Required Skills" as a tail section — advisory,
   not mandatory. No read-enforcement mechanism. Every execution
   depended on the model choosing to read.

3. **`frontend-dashboard-refactorer.md`: same.**

4. **`ci-gate.sh` hardcoded `src/ tests/` paths.** On our own repo
   (which uses `hooks/ scripts/ platform/src/`), the gate was
   false-failing on every session stop with a `No such file or
   directory` error. We'd been ignoring the noise.

5. **`scripts/tasks.py` path references** in skills pointed to
   `scripts/tasks.py` relative to project root, but the installer
   placed the script at `~/.claude/scripts/tasks.py`. Consumer
   projects hit a missing-file error on first use.

6. **`install.sh` hardcoded the six standards subdirectories it
   knew about** (process, code, testing, architecture, security,
   quality). When `standards/git/commit-discipline.md` was added in
   v1.6, the installer silently dropped it. Any skill that forced a
   read on it would fail on fresh installs.

7. **The KG POC PRD recommended Kuzu**, which had been archived
   weeks earlier.

Five of these seven had the same shape: **hardcoded inventory
diverges from truth the moment it's written.** ci-gate hardcoded
dirs. install.sh hardcoded categories. Skills hardcoded paths.
Every time someone added something, the list got stale. The
structural fix is always the same — discover dynamically from the
filesystem, never hardcode.

That's a pattern we now recognize across the harness. It'll
inform future code too.

## The numbers

| Metric | Value |
|---|---|
| Edits applied | 192 across 68 files |
| Tests before → after | 409 → 409 (one test-quality improvement) |
| Compile gates | 17 → 17 |
| Compile hooks | 14 → 14 |
| Compile agents | 21 → 21 |
| Compile skills | 10 → 10 |
| Compile standards | 38 → 38 |
| Total AP-NNN matches | 154 → ~12 (all in non-directive inventory files or defensive-framed security content) |
| Latent bugs fixed in-flight | 8 |
| Sessions | multi-day; branch `4.7-migration` |
| Commits on branch | 26 |

Zero regressions. Counts unchanged. The harness looks identical from
the outside; only the prompts are different. That's exactly what a
clean behavioral migration should look like.

## The deeper lesson

The usual instinct when a tool breaks is to fight the change —
"why did they make it worse?" The better instinct here is to
notice what the change reveals.

Under 4.6, our harness's enforcement pyramid looked like this:

```
ruff rules          ← mechanical, deterministic, free
custom AST hooks    ← mechanical, per-edit
required-reading    ← mechanical, pre-edit
agent judgment      ← inference-dependent, silent, generous
```

The bottom layer — agent judgment — was doing enormous load-bearing
work that nobody had quantified. Every gesture-phrase in every
prompt relied on 4.6 generously interpreting. We'd built a
discipline-enforcement tool whose bottom 30% of enforcement was a
vibe.

Under 4.7, the bottom layer produces less. That's not regression.
That's **pricing getting honest**. The mechanical tiers above
(ruff, hooks, forced reads) were always the real enforcement. The
generous inference was a subsidy the model was silently providing
that we mistook for our own discipline.

So the migration wasn't a repair in the narrow sense. It was a
**pressure test that forced the harness to be explicit about what
it wanted**. Every phrase that survived is now doing actual work.
Every phrase that was deleted was admitting that a gesture isn't
enforcement.

## What comes next

Migration once isn't enough. If nothing prevents the drift, prompts
written six months from now will reintroduce the same gestures. Two
pieces of durable infrastructure are coming next:

- **Compile-time AP-013 checks** — `compile-sdlc.py` will verify
  that every standards reference in every agent has an enforcement
  path (Before Starting, inject-standards, or task-level
  requires_reading). No more hope-based references.
- **Automated regression test** — `tests/test_agent_prompts_ap_free.py`
  will grep every agent and skill for every AP-NNN pattern on every
  test run. If someone writes "follow best practices" in a new
  agent, CI fails before it lands.

Neither existed pre-migration. Both are in the post-migration
backlog. Until they ship, the migration is a one-time cleanup; with
them, it becomes a permanent standard.

## Recommendations if you hit this

1. **Read the migration guide first.** Not the summary —
   the actual 4.6→4.7 section. Nine behavioral changes, each with
   specific remediation. Don't infer from the summary.
2. **Build an anti-pattern catalog for your own surface.** The 13
   APs we catalogued were specific to our harness. Yours may need
   different ones. But the grep-pattern-plus-fix structure scales.
3. **Audit your own plan as you write it.** 4.7 is literal about
   your prompts. If you write the migration plan with 4.6 habits,
   a future session won't execute it correctly.
4. **Don't use the broken tool to fix itself.** If the thing you're
   repairing is a prompt surface, route your fix around that
   surface. Direct Read/Edit/Bash in the main thread. Fresh-context
   subagents with inline prompts. Never dispatch through the
   definitions you're repairing.
5. **Surface the bugs that 4.6 was hiding.** The migration is
   also an audit. Every "huh, why did we never notice that?"
   finding was there all along.
6. **Move enforcement from inference to mechanics.** Everywhere
   you can. ruff rules, AST hooks, forced reads, mechanical
   invariants. The model's cooperation should be optional, not
   load-bearing.
7. **Invest in regression prevention.** The migration is only a
   fix if nothing can reintroduce the problem. Tests that grep for
   anti-patterns, compile-time checks, CI gates — pick your
   mechanism, but pick one.

---

## Concrete receipts (for the changelog-minded reader)

### New structural invariants

- **AP-013** — Reference without read-enforcement. Every file
  reference in every agent must be enforced by Before Starting,
  injection, or requires_reading.
- **Subagent Dispatch Taxonomy** — Every skill declares itself
  Non-Negotiable (orchestrator) or Non-Applicable (engine).
  Prevents silent role drift.
- **Verbosity Directive** — Every agent and skill has an explicit
  "Response Format" section with word caps, shape rules, no
  preamble/emoji/narrative.

### Files touched

- 23 agents (all of `agents/` except meta-inventory)
- 10 skills (every skill in `skills/`)
- 3 agent/prompt-type hook blocks in `spec/etc_sdlc.yaml`
- 14 of 31 directive standards docs (17 were already clean)
- install.sh, ci-gate.sh, pyproject.toml, and platform/ lint cleanups

### Latent bugs fixed

- A1: `code-reviewer.md` referenced non-existent standards files
- A2/A3: Two agents missing forced-read sections entirely
- A4: AP grep pattern was too narrow on first cut
- A5: `ci-gate.sh` hardcoded paths false-failing on this repo
- A6: `scripts/tasks.py` wrong path in consumer installs
- A7: Kuzu (referenced in KG POC) was archived
- A8: `install.sh` hardcoded standards subdirs, dropped `git/`

### Open follow-up (post-migration backlog)

- **B4 (P1)**: Compile-time AP-013 check
- **B5 (P1)**: Automated regression test for AP matches
- **B6 (P2)**: Positive marker for verbosity directive (greppable)
- **B7 (P2)**: `/implement` vs `/build` contract divergence
  (operator decision)

### Version

Shipping as **v1.8** — the scope (new invariants, taxonomy,
regression exposure) is too broad for a patch.

---

**Why this story is worth telling.** Most model-upgrade postmortems
are either defensive ("the model changed, we're adjusting") or
performative ("here's how we shipped in a day"). The more useful
frame is different: **a model upgrade is a stress test on your
assumptions about the model.** Every gesture-phrase in every
prompt is a silent bet on the model's generosity. When the model
gets more honest, your bets either pay out or they don't. The
ones that don't were always going to fail — you just didn't know
when.

4.7 told us when. The fix made the harness what it should have
been all along: explicit.
