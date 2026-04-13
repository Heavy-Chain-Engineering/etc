# Release Notes

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
