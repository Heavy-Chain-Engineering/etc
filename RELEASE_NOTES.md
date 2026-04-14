# Release Notes

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
