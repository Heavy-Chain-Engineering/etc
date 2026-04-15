# Release Notes

## 2026-04-15 — etc v1.6: the hotfix lane

This release completes the three-lane architecture that v1.5 introduced
as a principle. v1.5 named conversation and spec-build as distinct
lanes with their own quality bars; v1.6 ships the third lane the
harness had been neglecting — incident response — as the `/hotfix`
skill and its dedicated `hotfix-responder` subagent. The conversation
/ spec-build / hotfix triad is now complete.

### New: `/hotfix` — incident response lane

`/hotfix` exists for the operating mode every engineering team needs
but most harnesses neglect: production is on fire, and the full
`/spec → /build` ceremony is too slow. The operator does not need a
Definition-of-Ready interview, a three-state classifier, or a
wave-by-wave decomposition. They need to file what's broken, what the
fix is, and what the rollback plan is in under 30 seconds — then have
an authorized subagent execute the fix while the harness's
safety-critical gates (`safety-guardrails`, `tier-0-preflight`,
`check-invariants`) still fire.

The workflow is three `AskUserQuestion` pickers (Pattern A) in
sequence: failure type (Q1), fix kind (Q2), rollback strategy (Q3).
Each picker has 5 enumerated categories plus an automatic `Other`
escape hatch. Selections that require specifics (a SHA, a file path,
a flag name) trigger an immediate Pattern B follow-up that captures
the detail into the corresponding `*_detail` field of the incident
log. After the three pickers, `/hotfix` dispatches exactly one
`hotfix-responder` subagent and, on its completion, automatically
invokes `AskUserQuestion` to offer `/postmortem` as the recommended
next step.

The gate bypass is subagent-constrained, not hook-modified. The
existing `check-test-exists.sh`, `check-required-reading.sh`, and
`check-phase-gate.sh` hook scripts are untouched. Authorization to
bypass `tdd-gate`, `enough-context`, and `phase-gate` lives in the
`hotfix-responder`'s manifest layer — additive, reversible, and
greppable. Any future gate added under `PreToolUse: Edit|Write` will
automatically fire on the `hotfix-responder` unless that gate is
explicitly added to the bypass list.

Every invocation produces a structured incident log at
`.etc_sdlc/incidents/{YYYY-MM-DD}-{slug}/incident.md` with YAML
frontmatter (machine-readable audit fields) and a free-form prose
body (human-readable context). The directory pattern leaves room for
a sibling `postmortem.md` once the fire is out. Three anti-abuse
defenses keep the lane from being used as a TDD backdoor: (1) the
`gates_bypassed` audit field is git-tracked and greppable for
retroactive audit; (2) the `hotfix-responder` manifest includes a
description guardrail that refuses to proceed if the incident
description doesn't name both a specific system and a specific
failure mode; (3) a postmortem-debt banner surfaces at the next
`/hotfix` invocation listing any incident completed more than 24
hours ago without a sibling `postmortem.md`. None alone is
sufficient; together they make abuse detectable and socially
expensive without hard rate limits that would break real incidents
during a bad week.

### Architectural decisions

- **GA-HF-001 — Execution model**: subagent dispatch (not direct
  execution or advisory-only), so the `SubagentStop` adversarial-review
  hook still fires on the way out and every hotfix gets a hostile
  review before the session ends.
- **GA-HF-002 — Gate bypass policy**: subagent-constrained, not
  hook-modified — the existing `check-test-exists.sh`,
  `check-required-reading.sh`, and `check-phase-gate.sh` are
  untouched; bypass lives in the `hotfix-responder` manifest's
  authorization layer.
- **GA-HF-003 — Incident log format**: per-incident directory at
  `.etc_sdlc/incidents/{YYYY-MM-DD}-{slug}/` with YAML frontmatter
  plus prose body — matches the existing `.etc_sdlc/features/{slug}/`
  pattern so `/postmortem` drops a sibling file with no migration.
- **GA-HF-004 — Concurrency semantics**: single-incident lock plus
  `/build` preempt — one `/hotfix` at a time, and a mid-wave `/build`
  is checkpointed (`status: preempted_by_hotfix`) and resumed via
  `/build --resume` after the fire is out.
- **GA-HF-005 — Question UX**: all three pickers are Pattern A
  (`AskUserQuestion`), not free-text, because structured categorical
  fields are greppable and indexable where raw prose is not.
- **GA-HF-006 — Anti-abuse defense level**: medium — three
  complementary layers (audit field, subagent description guardrail,
  postmortem-debt banner). No hard rate limits, because the lane has
  to work during a bad week.

### New files

- `skills/hotfix/SKILL.md` — the workflow skill (538 lines, 6
  workflow phases + 3 utility sections)
- `agents/hotfix-responder.md` — the dedicated subagent manifest with
  gate-bypass authorization, description guardrail, and audit-trail
  recording instructions
- `standards/process/incident-response.md` — the operator-facing
  discipline guide (the secrets warning, the public-exposure warning,
  recovery procedures)
- `tests/test_hotfix.py` — contract tests (26 tests across 12
  classes, string-asserting the source files encode the BRs)
- `.etc_sdlc/incidents/.gitkeep` — placeholder so the directory
  exists in fresh checkouts

### Modified files

- `spec/etc_sdlc.yaml` — new entries under `skills:` (`hotfix`) and
  `agents:` (`hotfix-responder`). No changes to `gates:`.
- `.gitignore` — exception for `.etc_sdlc/incidents/` so incident
  logs are git-tracked. The obvious dual-bang pattern
  (`!.etc_sdlc/incidents/` + `!.etc_sdlc/incidents/**`) does NOT work
  because git's "re-include parent" rule requires the parent
  directory to be un-ignored first. Working pattern: `.etc_sdlc/` +
  `!.etc_sdlc/` + `.etc_sdlc/*` + `!.etc_sdlc/incidents/` +
  `!.etc_sdlc/incidents/**`. The pattern is non-obvious — the
  `/hotfix` spec itself initially had the wrong form.
- `README.md` — skills count 9 → 10, test count 264 → 290, new
  `/hotfix` pipeline narrative paragraph.

### By the numbers

| | v1.5.1 | v1.6 | delta |
|---|---|---|---|
| Gates | 14 | 14 | 0 |
| Hooks | 10 | 10 | 0 |
| Skills | 9 | 10 | +1 |
| Agents | 19 | 20 | +1 |
| Standards docs | 31 | 32 | +1 |
| Tests passing | 264 | 290 | +26 |
| `tests/test_hotfix.py` | — | 26 | +26 |
| Workflow phases in /hotfix | — | 6 | +6 |
| Anti-abuse defenses | — | 3 | +3 |

### Upgrade notes

1. **Recompile**: `python3 compile-sdlc.py spec/etc_sdlc.yaml` —
   produces `dist/skills/hotfix/SKILL.md`,
   `dist/agents/hotfix-responder.md`, and
   `dist/standards/process/incident-response.md`. Skills go 9 → 10,
   agents 19 → 20, standards 31 → 32. Gates stay at 14; hooks stay
   at 10.
2. **Reinstall**: `./install.sh` — propagates the new skill and
   agent manifest into `~/.claude/`.
3. **Read the standards doc before first use**: operators should
   read `standards/process/incident-response.md` once before they
   ever invoke `/hotfix` in anger. The "DO NOT include secrets"
   warning is non-obvious — `incident.md` files are git-tracked, so
   any credential pasted into a description or prose body lands in
   commit history permanently.
4. **No opt-out flag**. The lane does not fire unless the operator
   explicitly types `/hotfix`. There is nothing to mute.

### Philosophy note

v1.5 introduced the principle that rigor should live at lane
boundaries, not at the thread boundary. v1.6 completes that principle
by adding the third lane the harness had been neglecting — incident
response. Conversation, spec-to-build, and hotfix are now the three
explicit lanes, and the operator declares the lane by the slash
command they type. The harness's job is to enforce the right kind
of rigor inside each lane, not to guess which lane the operator
intended from the shape of their prose.

The three-lane architecture is what makes it safe to trade upfront
ceremony for speed in the hotfix case. You can afford to sacrifice
`/spec`'s Definition-of-Ready interview only because `/postmortem`
reclaims the accountability afterward, and you can afford to bypass
`tdd-gate` only because the subagent's manifest-layer authorization
is visible in every `incident.md`'s `gates_bypassed` field. The
lane's trustworthiness depends on the other two lanes' rigor —
remove either one and `/hotfix` becomes a TDD backdoor instead of an
incident response tool.

---

## 2026-04-14 — etc v1.5.1: research discipline + harness feedback loop

A same-day patch release following v1.5, adding two related learning
mechanisms that address a gap v1.5 left open: **how do cross-project
lessons flow back into the harness in the first place?**

### New: research discipline rule

Adds `standards/process/research-discipline.md` and a matching section
in `hooks/inject-standards.sh` that briefs every subagent at spawn
time on the "consult current docs before disassembling bundles" rule.

The rule is specific enough to fire in the moment: if an agent finds
itself grepping `dist/**/*.js` or tracing transpiled output before
querying `context7`, it stops and re-queries docs. The standards doc
documents the ordering heuristic with time budgets (context7 30s →
official docs 2min → repo grep 5min → test suite 5min → source last
resort).

Origin: a 2026-04-14 session spent ~40 minutes disassembling a built
Worker bundle to trace cache-header plumbing when the canonical API
was one `context7` query away.

Three regression tests (`tests/test_inject_standards.py`) guard the
three qualities that make the rule fire in practice: the section
exists in onboarding, it names `context7` concretely, and it calls
out the `dist/`/bundles failure mode by name. Abstract rules drift
past agents in the heat of debugging — specific failure-mode names
don't.

### New: harness feedback loop (the Stop-hook scout)

Adds a `harness-feedback` gate to the Stop event. It runs a Sonnet
prompt hook at the end of every turn, in every project, under every
installation of etc. Its job is one question: *"Did anything happen
in this turn where a harness rule could have prevented wasted time, a
mistake, or a workaround?"*

**Silent by default.** The 95% case is "nothing happened" and the
hook returns `{"continue": true}` with no output. When it does fire,
it emits a distinctive `📬 Harness feedback` block sized for
copy-paste into a new conversation with the etc repo.

**The six triggers** the hook looks for, any one of which is
sufficient to emit:

1. **Research inversion** — read source before docs, grepped dist
   bundles, disassembled transpiled output before `context7`.
2. **Repeated mistake** — same class of bug fixed twice in one turn.
3. **Manual workaround** — invented a sed/copy-paste hack where a
   CLI flag, skill step, or hook would have been cleaner.
4. **Time-wasted pattern** — >10 minutes on something with a one-shot
   documented answer elsewhere.
5. **Framework/tool surprise** — "obvious in hindsight" behavior that
   a one-line onboarding addition would have preempted.
6. **Near-miss gate** — an existing gate almost caught something but
   missed because of a narrow rule gap.

**Output format is load-bearing.** The block's emoji, rule lines, and
field names are structural, not decorative — they're the parser
anchors a future etc-repo agent uses to recognise and implement the
proposed rule without re-deriving context:

```
📬 Harness feedback — paste this into etc:
─────────────────────────────────────────────
**Observed in:** {project}
**Date:** YYYY-MM-DD
**Trigger:** {one of the six}

**What happened**
**Why the harness could have prevented it**
**Proposed rule**
**Origin trace**
─────────────────────────────────────────────
```

**Context-aware routing.** If the Stop hook detects it's running
*inside* the etc repo itself (cwd matches `etc-system-engineering`),
the marker line becomes "implement this now?" instead of "paste this
into etc" — so the harness can eat its own dog food without copy-
paste overhead.

**Signal-to-noise is the whole game.** The prompt refuses to emit
unless the proposed rule names a specific file, hook, or standards
doc. Vague "be more careful" suggestions are rejected at the rubric
level. Seven contract tests in `tests/test_compiler.py` assert this:
the six triggers are enumerated by name, silence is the default, the
📬 marker is present, context-aware routing is wired in, and the
advisory timeout is ≤60s so a hung hook cannot block a session.

**Why it's advisory, not enforcing.** This hook runs alongside the
existing `ci-pipeline` agent hook on the same Stop event. The CI hook
gates code quality and can block the stop if tests fail. The feedback
hook is advisory: `on_failure: allow`, `timeout: 30`, silent by
default. Missing a lesson is a smaller cost than blocking a session.

### The two loops together

The harness now has two learning loops, catching different things:

| Loop | Trigger | Catches | Lives in |
|---|---|---|---|
| `/postmortem` | Human-invoked after a bug escapes | Per-project escaped bugs with known root cause | `.etc_sdlc/antipatterns.md` (per project, gitignored) |
| `harness-feedback` | Automatic, every Stop | Cross-project process lessons, time-wasted patterns, near-misses | `📬` block → paste back to etc → standards/hooks/skills |

`/postmortem` is reactive and project-local. `harness-feedback` is
proactive and cross-project. Together they close the gap between "a
bug shipped broken in this project" and "a process mistake wasted
time in every project, including ones where no bug ever shipped."

`standards/process/harness-feedback-loop.md` documents both loops,
the six triggers, the parsing contract for the 📬 block, and the
close-the-loop workflow (copy block → paste into etc → agent
implements → `./install.sh` deploys globally).

### By the numbers

| | v1.5 | v1.5.1 | delta |
|---|---|---|---|
| Gates | 14 | 15 | +1 (harness-feedback) |
| Standards docs | 28 | 30 | +2 (research-discipline, harness-feedback-loop) |
| Tests passing | 257 | 267 | +10 |
| `test_inject_standards.py` | 7 | 10 | +3 |
| `test_compiler.py::TestHarnessFeedbackHook` | 0 | 7 | +7 |
| Onboarding sections in `inject-standards.sh` | 4 | 5 | +1 |
| Stop-event hooks | 1 | 2 | +1 |

### Upgrade notes

1. **Recompile**: `python3 compile-sdlc.py spec/etc_sdlc.yaml`
2. **Reinstall**: `./install.sh` — this propagates the new Stop hook
   to `~/.claude/settings.json` so every project under the harness
   starts getting feedback evaluation at end-of-turn.
3. **No opt-out flag** in this release — the hook is silent by
   default and advisory when it fires, so there's nothing to mute.
   If you find it noisy in practice, raise the rubric bar in the
   prompt rather than disabling the hook.

### Philosophy note

v1.5 landed the principle "rigor lives at lane boundaries, not at the
thread boundary." v1.5.1 adds the complementary principle: **the
harness watches itself for lessons it should have taught**. Every
session is a chance for the harness to learn, and the cost of watching
is one Sonnet call per turn. If one lesson a week flows through this
loop into a real rule change, the cost is repaid a hundredfold by the
compounding effect of every future session under the improved rule.

An engineering harness that does not learn from its consumers is a
fossil. This release makes "noticing" automatic and "writing it down"
frictionless — the only two friction points that matter for a
learning loop to close.

---

## 2026-04-14 — etc v1.5: lanes, not gates

The theme of this release is **architectural honesty about how humans
actually interact with an engineering harness**. The top-level thread is
not a single lane — it's a dispatcher across several, each with its own
quality bar. Pretending otherwise produces hooks that block conversation
about how to unblock themselves.

Three landed features, one deferred brief, and one load-bearing
refactor that moves the Definition of Ready gate out of the
conversational layer entirely.

### New: `tasks.py create` and `bulk-create`

Task YAML files are now authored via a schema-validating CLI instead of
hand-written through the Write tool during decomposition.

- **`python3 scripts/tasks.py create --feature {slug} ...`** — single
  task via repeated `--file`, `--ac`, `--dep`, `--read` flags. The
  debugging path.
- **`python3 scripts/tasks.py bulk-create --feature {slug} < tasks.json`**
  — the normal path. Accepts a JSON array via stdin, `--json`, or
  `--json-file`. Validates every task, refuses to write if any target
  already exists (unless `--allow-existing`), and rolls back the entire
  batch on any error. No half-decomposed state ever lands on disk.

**Measured impact.** A 10-task decomposition used to burn ~12,000 tokens
on YAML syntax (indentation, quoting, field ordering). The CLI version
uses ~3,000. That's ~75% of decomposition-phase cost recovered, and it
eliminates a whole class of transcription errors: YAML indentation
drift, field name typos, dependency reference typos, and missing
required fields only discovered three steps later when `tasks.py score`
fails.

**Byte-identical output.** The CLI's YAML emitter is hand-rolled to
match the existing `_create_task` test helper exactly — not `yaml.safe_dump`
— because safe_dump is not deterministic across pyyaml versions on
string quoting and would have broken every existing task file comparison
in the test suite. See `tests/test_tasks.py` for the byte-equality
regression test.

**Agent skill updates.** `/decompose`, `/build`, `/implement`, and `/tasks`
all now direct agents to the new CLI and explicitly forbid hand-writing
task YAML with the Write tool. This is the change that actually realizes
the token savings — the CLI on its own is useless if agents don't know
to use it.

### New: `/spec` three-state PRD classification

`/spec` now classifies every incoming PRD into one of three states
before writing anything:

1. **Well-specified** — every requirement has a concrete answer. Proceed
   directly to section-by-section writing.
2. **Under-specified with research-fillable gaps** — some requirements
   are missing, but codebase grep, existing docs (DOMAIN.md, ADRs,
   INVARIANTS.md, adjacent PRDs), or web research can resolve them. The
   skill auto-fills these during Phase 2, records each resolution with
   its citation in `gray-areas.md` (new `decided_by: research` field),
   and proceeds.
3. **Under-specified with unfillable gaps** — requirements depend on
   business intent, product scope, roadmap decisions, or stakeholder
   policy that cannot be inferred from citable evidence. The skill
   either surfaces only the unfillable gaps for user resolution, or
   rejects the PRD entirely to `rejected.md` with specific questions the
   human must answer before resubmitting.

**The rejection threshold** (tunable via constants at the top of the
skill):

- ≤ 20% of requirements need filling → research-assisted, proceed with
  citations.
- 20%–50% → gray-area session with user, surface only unfillable gaps.
- \> 50% OR > 3 unfillable gaps → reject to `rejected.md`, no `spec.md`
  is written.

`spec.md` and `rejected.md` are **mutually exclusive** in any feature
directory — a contract test sweeps every existing feature dir to enforce
this invariant, so a future refactor can't accidentally produce both.

**`gray-areas.md` schema is backward compatible.** Existing entries
without `decided_by` are still valid. New entries gain three additive
fields: `decided_by` (research | user | rejected), `citation` (source
file or URL), and `resolution rationale` (why this answer, when research
was the decider).

### Refactor: DoR moved from `UserPromptSubmit` to `/build` Step 1

**This is the architectural change the v1.5 title refers to.**

The v1.4 harness had a Sonnet-powered Definition of Ready gate on every
`UserPromptSubmit` event. In theory it was a coarse filter that would
fail open on slash commands, short prompts, and continuation keywords.
In practice it kept mis-classifying conversational follow-ups — any
imperative message of more than 15 words referencing prior
conversation was at risk of being rejected as a "vague work request."
The failure mode was catastrophic: the hook blocked conversation about
how to fix the hook.

The root cause: the hook only sees the user's current prompt, not the
conversation history. It was trying to guess the lane from free text and
kept adding early-exit rules to patch each new failure. Adding more
rules is a losing strategy — natural language has infinite ways to say
"continuation of our conversation."

**The fix is to invert the default.** Rigor now lives at lane
boundaries, not at the thread boundary:

| Lane | Entry | Gate |
|---|---|---|
| Conversation / ideation / meta | Any free text | **None** |
| Spec authoring | `/spec` | Three-state classifier (internal) |
| Build execution | `/build {spec}` | DoR preflight on the spec artifact |
| Hotfix (deferred to v1.6) | `/hotfix` | Lightweight — file, change, rollback |

The top-level thread is now a free-form conversation. You can ideate,
discuss the framework, follow up on agent work, and reply casually
without any gate interpreting you as a spec submission. Rigor kicks in
only when you explicitly cross a lane boundary with a slash command.

Concretely this release:

- **Removes** the `definition-of-ready` gate from `spec/etc_sdlc.yaml`
  entirely. Recompilation produces 14 gates, not 15. The
  `UserPromptSubmit` event is no longer in the compiled
  `dist/settings-hooks.json` at all.
- **Adds** a formal DoR preflight to `skills/build/SKILL.md` Step 1. The
  preflight first checks for `.etc_sdlc/features/{slug}/rejected.md`
  (from `/spec`'s three-state classifier) and stops immediately if
  found. If the spec passed through `/spec` cleanly, it rubber-stamps.
  If the spec was hand-written and placed outside `/spec`'s flow, it
  runs the DoR checklist inline and rejects with specific gaps the user
  can act on.
- **Replaces** two obsolete compiler tests that asserted the existence
  of the UserPromptSubmit gate with a single regression test
  (`test_should_not_register_userpromptsubmit_gate`) that enforces the
  architectural decision: if anyone re-adds a conversation-level gate,
  this test fails loudly so the decision must be re-justified.

**Prompt hooks that remain untouched.** `TaskCreated`, `TaskCompleted`,
`SubagentStop`, `Stop`, and `ConfigChange` are all still prompt or agent
hooks, because they gate *artifacts* (task files, completed work,
configuration changes) — not conversation. Same DoR machinery, applied
where it actually fits.

### Deferred: `/hotfix` lane brief

Filed as `spec/hotfix-skill-brief.md`. This is a brief, not a buildable
spec — promote via `/spec` when ready to implement.

The motivation: production incidents need a third lane that trades
upfront ceremony for speed. Three questions max (what's broken, what's
the fix, what's the rollback plan), then execute immediately. No DoR,
no decomposition, no wave planning. After the fire is out, auto-prompt
`/postmortem` to reclaim accountability. The hotfix lane sacrifices
ceremony upfront and makes up for it afterward — the spec-build lane is
the inverse tradeoff.

### Bug fixes surfaced by the refactor

- **`_validate_task_dict` type signature** (`scripts/tasks.py`) — the
  parameter was typed as `dict`, which made the runtime `isinstance`
  check unreachable from Pyright's perspective. Fixed to `object` so
  the defensive check for non-dict JSON input is typed meaningfully.
- **Stale `json` import diagnostics** — transient during the build; not
  a real bug, but noted as a reminder that harness diagnostics are
  snapshots from the session, not fresh scans.

### By the numbers

| | v1.4 | v1.5 | delta |
|---|---|---|---|
| Gates | 15 | 14 | -1 (DoR moved to /build Step 1) |
| Skills | 9 | 9 | 0 |
| Tests passing | 228 | 257 | +29 |
| `test_tasks.py` | 28 | 50 | +22 (create + bulk-create) |
| `test_spec_three_state.py` | 0 | 8 | +8 (new contract) |
| `test_compiler.py` | — | — | -1 test, +1 replacement |
| Hook events | 10 | 9 | -1 (UserPromptSubmit removed) |

### Upgrade notes

1. **Recompile.** `python3 compile-sdlc.py spec/etc_sdlc.yaml`
2. **Reinstall** if you want the DSL change reflected in your global
   settings: `./install.sh`.
3. **Remove the old hook from `~/.claude/settings.json`** if you
   installed v1.4 previously. The `UserPromptSubmit` hook entry will
   not be regenerated, but an existing installation may still have it.
   Delete the `hooks.UserPromptSubmit` array to match the new shape.
4. **Agents will start using the CLI automatically.** The updated
   `/decompose`, `/build`, `/implement`, and `/tasks` skills reference
   `tasks.py bulk-create` as the canonical path; reinstalling the
   harness propagates these changes.

### Philosophy note

This release is the first one where we deliberately *removed* a gate
rather than adding one. Every v1.x release through v1.4 added
enforcement. v1.5 acknowledges that enforcement at the wrong place is
worse than no enforcement — it blocks legitimate work while doing
nothing to catch actual problems.

The right mental model: **an engineering harness is a set of lanes
with explicit entry points, not a single checkpoint at the door**.
Conversation is a lane. Ideation is a lane. Spec authoring is a lane.
Build execution is a lane. Hotfix is a lane. Each lane has its own
quality bar, and the user declares the lane by how they address the
system. The harness's job is to enforce rigor *within* a lane, not to
guess which lane the user intended from the shape of their prose.

---

## 2026-04-13 — etc v1.4: /init-project and the rigor pass

Small but meaningful release. One new skill, a UX pattern rolled out to
five existing skills, and ten bug fixes that surfaced when the harness
was dogfooded against itself.

### New: `/init-project`

Single-command bootstrap for any repository, greenfield or brownfield.
Four phases:

- **Phase 1** — delegates to the existing `project-bootstrapper` agent
  for technical scaffolding (tooling, pre-commit, CI, `.meta/` tree).
  Unchanged behavior, invoked via the Task tool.
- **Phase 2** — interactive `DOMAIN.md` / `PROJECT.md` / `CLAUDE.md`
  creation. Two modes: answer six Socratic questions yourself, or
  provide a source URL and the skill uses WebFetch to research and
  drafts each section with citations. You confirm or correct before
  anything is written.
- **Phase 3** — tiered documentation skeleton. Tier 1 directories
  (`docs/prds/`, `docs/plans/`, `docs/sources/`, `docs/standards/`,
  `docs/guides/`) unconditionally. Tier 2 (`docs/adrs/`,
  `docs/contexts/`, `docs/invariants/`) prompted. Tier 3 opt-in for
  regulated domains.
- **Phase 4** — starter role manifests under `roles/` for the five
  standard roles (sem, architect, backend-dev, frontend-dev,
  code-reviewer), using the soft-POLA pattern with `default_consumes`
  plus `discovery.allowed_requests` and no `forbids` block.

The skill is idempotent. Re-runs on an initialized repo produce no
changes.

After `/init-project` completes, the new `tier-0-preflight` hook stops
blocking Edit|Write operations on that repo. Before it runs, the hook
blocks them — which is how the harness enforces that no repo is
modified without explicit domain grounding.

### UX: structured prompts across five skills

Claude Code ships an `AskUserQuestion` tool that renders a dedicated
picker UI outside the text stream. Questions buried in agent prose get
skimmed past; the picker makes them impossible to miss. Propagated to:

- `/init-project` — mode selection, Tier 2 prompt, CLAUDE.md merge
  decisions, teach-me-mode confirmations
- `/build` — task-breakdown and wave-execution confirmations (new:
  dry-run option for Wave 0 only)
- `/decompose` — post-breakdown "start the build?" prompt
- `/postmortem` — prevention-improvement approvals (new invariant /
  new test / hook change, with approve / defer / skip per item)
- `/spec` — section-by-section approvals, gray-area resolution,
  post-completion next-step selection

Free-form elicitation questions (the six `/spec` Phase 1 questions, the
six `/init-project` Phase 2 questions) use a visual marker convention
instead: horizontal rule, blank lines, and a bold `▶ Your answer
needed:` prefix. The rule is documented at
`standards/process/interactive-user-input.md` and enforced by contract
tests in `tests/test_init_project.py::TestSkillMdContract`.

### Bug fixes (the rigor pass)

All ten found by dogfooding `/init-project` end-to-end against a scratch
Python FastAPI repo. None of them were catastrophic in isolation; most
would have bitten another user eventually.

- **`compile-sdlc.py`** — `compile_skills()` only copied `SKILL.md` per
  skill, silently dropping `templates/` subdirectories. Fixed with
  `shutil.copytree(..., dirs_exist_ok=True)`.
- **`install.sh`** — same class of bug at install time. Non-recursive
  shell glob copy swallowed by `|| true` so the failure was silent.
  Fixed to use `rsync -a --delete` (with `cp -R` fallback). Skills with
  template subdirectories now install correctly.
- **`pyproject.toml`** — pytest's collection walker stat'd `.env`
  during rootdir discovery and failed on the sandbox denyRead list,
  forcing every pytest run to need a sandbox-bypass flag. Added
  `--ignore-glob=.env*` and expanded `norecursedirs`. Tests now run
  sandbox-clean.
- **`scripts/tasks.py waves`** — mixed tasks from multiple features
  into one wave plan, and treated already-completed tasks as if they
  were still pending (so their dependents were stuck). Added
  `--feature` scoping and pre-population of `satisfied_ids` with
  completed tasks.
- **`hooks/block-dangerous-commands.sh`** — the `git add` guard
  matched any path starting with a period (`.gitignore`,
  `.etc_sdlc/...`, `.github/...`). Fixed to require whitespace or
  end-of-line after the period so only the standalone period (meaning
  stage-everything) is blocked.
- **`hooks/check-invariants.sh`** — on case-insensitive filesystems
  (macOS APFS, Windows NTFS), the shell `-f` test on `INVARIANTS.md`
  matched a lowercase `invariants.md`. That caused the hook to parse
  standards docs as invariant registries and execute their example
  verify commands as shell commands on every edit. Fixed with a
  case-sensitive basename check via `ls | grep -qE`.
- **`spec/etc_sdlc.yaml`** — five AI-powered hooks used `model:
  sonnet` as shorthand that Claude Code's hook evaluator does not
  resolve. Replaced with the full `claude-sonnet-4-5` model ID.
- **`definition-of-ready` hook** — rejected slash commands, short
  conversational replies, and continuation keywords as "vague work
  requests," blocking every interactive skill flow. Added a
  length-based early exit (≤15 words), explicit exemptions for slash
  commands and continuation patterns, and an explicit fail-open
  directive: when in doubt, allow. The hook is now a coarse filter,
  not a strict gate.
- **`task-readiness` and `task-completion` hooks** — misfired on
  Claude Code's built-in `TaskCreate` tool, which creates lightweight
  in-context todos without the formal task fields the hooks were
  written to evaluate. Added shape-check early exits that allow
  inputs lacking `task_id` / `files_in_scope` / `acceptance_criteria`.
- **`/init-project` skill template copy** — agents were transcribing
  role manifests via `Read` + `Write` instead of copying them
  byte-identically, risking typos in the soft-POLA pattern and
  burning tokens on 60-line YAML files. SKILL.md now has explicit
  Template Copy Conventions: `Read` + substitute + `Write` for
  placeholder templates, `Bash cp` for verbatim templates.

### Meta: ETC eats its own dog food

`DOMAIN.md` and `PROJECT.md` now live at the ETC repo root. Before this
release, the `tier-0-preflight` hook blocked edits to any repo missing
its Tier 0 files — including the ETC repo itself, which meant the
harness could not be modified from inside the harness. The ETC repo's
own `DOMAIN.md` follows the 9-section blog-article format and describes
the harness as an "agentic software engineering discipline enforcement"
system.

### By the numbers

|                  | v1.3 | v1.4 |
|------------------|------|------|
| Enforcement gates | 14   | 15 (+ `tier-0-preflight`) |
| Hook scripts     | 9    | 10 (+ `check-tier-0.sh`) |
| Skills           | 8    | 9 (+ `/init-project`) |
| Standards        | 18   | 19 (+ `interactive-user-input.md`) |
| Tests            | 161  | 228 |

### How to upgrade

```bash
cd ~/src/etc-system-engineering
git pull
python3 compile-sdlc.py spec/etc_sdlc.yaml
./install.sh     # Choose option 1 for Claude Code
# Restart Claude Code
```

Running `/init-project` against a fresh repo will exercise the full new
flow. Existing `/spec` and `/build` invocations will automatically use
the picker-UI prompts after the reinstall.

### Notes for team review

- The release is 12 commits, each with a single concern, suitable for
  chunked review in git history.
- The new `standards/process/interactive-user-input.md` should become
  the default reference for any future skill author who needs to
  prompt the user.
- The `tier-0-preflight` hook is the first hook the harness enforces
  against itself — expect every new repo to need a `DOMAIN.md` and a
  `PROJECT.md` before it can be worked on with the harness active.

---

## 2026-04-06 — etc v1.3: The Full Pipeline

**etc** (Engineering Team, Codified) is a harness for Claude Code that enforces
software engineering best practices through deterministic hooks, LLM-based
judgment gates, and a declarative SDLC specification. Instead of relying on the
AI to follow standards, the harness makes it mechanically impossible to skip them.

**Repo:** https://github.com/Heavy-Chain-Engineering/etc

### What It Does

You type `/spec "what you want to build"` — the harness runs a Socratic loop,
researches your codebase and the web, surfaces ambiguous decisions (gray areas),
and generates an implementation-ready PRD.

Then you type `/build` — the harness validates the spec, recursively decomposes
it into right-sized tasks (arbitrary depth), plans execution waves, dispatches
subagents wave-by-wave, verifies after each wave, and reports results. Every
step is checkpointed and resumable.

Every file edit is gated by deterministic hooks: TDD enforcement (test must exist
before source), architectural invariants, required reading checks, phase-aware
file gating, dangerous command blocking. The agent can't skip steps because the
hooks fire whether it wants them to or not.

### By the Numbers

- **14** enforcement gates across 10 Claude Code hook events
- **9** hook scripts (deterministic bash, <1s each)
- **7** skills: `/spec`, `/build`, `/decompose`, `/implement`, `/tasks`, `/postmortem`, `/checkpoint`
- **4** artifact templates (ADR, agent, task, invariant)
- **148** tests, all passing in ~4 seconds
- **1** declarative YAML spec (`etc_sdlc.yaml`) that compiles to everything

### The Pipeline

```
/spec "add user authentication"
  → Socratic questions → codebase research → web research
  → gray area resolution → PRD section-by-section → Definition of Ready check
  → "This PRD is solid. Shall I /build it?"

/build .etc_sdlc/features/auth/spec.md
  → validate → decompose → score (any task > 7? decompose further)
  → plan waves → execute wave 0 → verify → execute wave 1 → verify → ...
  → final CI → verification report
  → "Build complete. 47 tests pass, 98% coverage. Ready to commit."
```

### Key Capabilities

**SDLC-as-Code.** The entire harness is defined in a single YAML file
(`spec/etc_sdlc.yaml`). A compiler reads it and emits Claude Code hooks,
agent definitions, skill files, standards, and templates. Change the YAML,
recompile, reinstall. One source of truth.

**Hierarchical decomposition.** Tasks too complex for a single agent session
get recursively broken into subtasks (001 → 001.001 → 001.001.001). The system
keeps decomposing until every leaf scores ≤ 7 on the complexity scale. This is
how you build arbitrarily large systems with AI agents.

**Wave-based execution.** Tasks are grouped into parallel execution waves by
dependency analysis. Within a wave, tasks run in parallel (file-set isolated).
Between waves, verification runs to catch regressions early. A failure stops
the pipeline — fail early and loud.

**Adversarial review.** A fresh agent with no implementation context reviews
every subagent's output with hostile intent — looking for what's wrong, not
confirming what's right. Never let an agent grade its own work.

**Antipatterns learning loop.** When bugs escape, `/postmortem` traces them to
root cause and appends prevention rules to `.etc_sdlc/antipatterns.md`. Every
future spec and subagent reads this file. The system gets smarter over time.

**Three-layer enforcement:**
- Command hooks (deterministic, <1s) — TDD, invariants, dangerous commands
- Prompt hooks (Sonnet, ~5s) — Definition of Ready, task readiness
- Agent hooks (Sonnet + tools, ~60s) — CI pipeline, adversarial review

### Quick Start

```bash
git clone https://github.com/Heavy-Chain-Engineering/etc.git
cd etc
python3 compile-sdlc.py spec/etc_sdlc.yaml
./install.sh   # Choose Claude Code
# Restart Claude Code
/spec "your feature idea"
```

### Inspired By

Built on ideas from [Correctless](https://github.com/joshft/correctless) (adversarial
review, antipatterns loop), [Armature](https://github.com/dsmedeiros/armature-public)
(templates, governance journal, checkpoint protocol), [GSD](https://github.com/itsjwill/gsd-pro)
(wave execution, context engineering), and [Spec Kitty](https://github.com/Priivacy-ai/spec-kitty)
(per-feature artifact directories).

### Philosophy

AI coding assistants are smart enough to do good work, but they skip steps.
In a real engineering team, you don't rely on individual discipline — you build
systems. This harness applies the same principle: CI pipelines that block red
builds, code review that requires approval, sprint planning that rejects vague
tickets. The discipline is in the process, not the person.

We never swallow errors. We never lower the bar on the second attempt. We fail
early and loud.

MIT License.
