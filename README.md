# etc — Engineering Team, Codified

A harness for [Claude Code](https://claude.ai/code) that enforces software engineering best practices through deterministic hooks, LLM-based judgment gates, and a declarative SDLC specification. Instead of relying on the AI to choose to follow standards, the harness makes it mechanically impossible to skip them.

The idea: take 20 years of engineering leadership lessons — TDD, Definition of Ready, code review, architectural invariants, CI pipelines — and scaffold them as enforcement hooks around the AI coding assistant. The agent doesn't choose whether to write tests first. The hook blocks the edit if the test doesn't exist.

## Quick Start

```bash
git clone https://github.com/Heavy-Chain-Engineering/etc.git
cd etc

# 1. Compile the SDLC specification into deployable artifacts
python3 compile-sdlc.py spec/etc_sdlc.yaml

# 2. Install the harness into Claude Code
./install.sh    # Choose option 1 for Claude Code

# 3. Restart Claude Code — the harness is active
```

### Verify It Works

```bash
uv sync            # Install test dependencies
uv run pytest      # 276+ tests, ~7 seconds
```

Then in Claude Code, try editing a `src/` file without writing a test first. The TDD hook will block you.

## How It Works

### Three-Layer Enforcement

| Layer | Type | Speed | Purpose |
|-------|------|-------|---------|
| **Command hooks** | Deterministic bash scripts | <1s | Binary checks: test file exists? invariant violated? dangerous command? |
| **Prompt hooks** | Single LLM call (Sonnet) | ~5s | Judgment: "Is this request specific enough to implement?" |
| **Agent hooks** | Multi-turn LLM with tool access | ~60s | Verification: run tests, check coverage, validate architecture |

Command hooks fire on every Edit/Write (hundreds of times per session). Prompt hooks fire on task boundaries (a few times). Agent hooks fire on Stop (once per turn). The cost profile is intentional — cheap gates run often, expensive verification runs once.

### The 15 Gates

```yaml
# Preconditions — before work begins
safety-guardrails:       PreToolUse (Bash) → command  Block rm -rf, force push, DROP TABLE
tier-0-preflight:        PreToolUse (Edit) → command  DOMAIN.md and PROJECT.md must exist at repo root
tdd-gate:                PreToolUse (Edit) → command  Test file must exist before source
invariant-check:         PreToolUse (Edit) → command  INVARIANTS.md contracts must hold
enough-context:          PreToolUse (Edit) → command  Agent must read required files first
phase-gate:              PreToolUse (Edit) → command  Block edits inappropriate for current SDLC phase

# During work
dirty-marker:            PostToolUse (Edit) → command  Track which files changed

# Task lifecycle
task-readiness:          TaskCreated        → prompt  "Does this task have clear criteria?"
task-completion:         TaskCompleted      → agent   Verify deliverable matches acceptance criteria

# Subagent lifecycle
standards-injection:     SubagentStart      → command  Inject engineering standards into every subagent
adversarial-review:      SubagentStop       → agent   Fresh hostile reviewer — never grades its own work

# Session lifecycle
ci-pipeline:             Stop               → agent   Full CI: tests + types + lint + invariants
harness-feedback:        Stop               → prompt  Watch for cross-project lessons; emit copy-pasteable note
change-control:          ConfigChange       → command  Agent cannot loosen its own governance
compaction-recovery:     SessionStart       → command  Re-inject context after compaction
```

### The `/init-project` → `/spec` → `/build` Pipeline

The full pipeline from an empty repo to verified, working code:

```
/init-project                          → tiered scaffold + DOMAIN.md + role manifests
/spec "Add user authentication"        → PRD with gray areas resolved
/build .etc_sdlc/features/auth/spec.md → validated, decomposed, built, verified
```

**`/init-project`** — Bootstraps any repo (greenfield or brownfield) into a
state where the harness can operate. Four phases: technical scaffold (via
the `project-bootstrapper` agent), interactive `DOMAIN.md` / `PROJECT.md` /
`CLAUDE.md` creation, tiered docs skeleton (`docs/prds/`, `docs/plans/`,
`docs/sources/`, etc.), and starter role manifests under `roles/`. Phase 2
supports two modes: answer six Socratic questions yourself, or provide a
company website URL and the skill researches via WebFetch and drafts with
citations. Idempotent — re-runs on an initialized repo produce no changes.

**`/spec`** — Socratic specification loop:
1. Asks clarifying questions (never starts writing immediately)
2. Researches the codebase and web for patterns, pitfalls, security, and **auto-fills citable gaps** with decided_by: research entries in gray-areas.md
3. **Three-state classification** (v1.5): well-specified → write PRD; under-specified with research-fillable gaps → auto-fill with citations and proceed; under-specified with too many unfillable gaps → reject to `rejected.md` with specific questions the human must answer before resubmitting
4. Surfaces only unfillable gray areas to the user — no busywork resolving what the codebase already answers
5. Builds the PRD section by section, each approved by the user

**`/build`** — The conductor. Orchestrates the full pipeline:
1. **Validate** — DoR preflight on the spec artifact (rubber-stamps specs that came through `/spec`; rejects hand-written specs with specific gaps). This is the single quality gate at the pipeline entry — conversation is never gated at the thread boundary.
2. **Decompose** — break PRD into tasks via `tasks.py bulk-create` (atomic JSON batch, ~75% fewer tokens than hand-writing YAML)
3. **Score & Recurse** — any task scoring > 7 gets decomposed further (arbitrary depth)
4. **Plan Waves** — group by dependency, verify no file overlaps
5. **Execute** — dispatch wave by wave, verify after each wave
6. **Verify** — full CI + architectural review
7. **Report** — verification.md + summary

**`/hotfix`** — Incident response lane. When production is on fire and the
normal `/spec` → `/build` ceremony is too slow, `/hotfix` lets an operator file
an incident in under 30 seconds and dispatch a constrained `hotfix-responder`
subagent to execute the fix. The lane sacrifices upfront ceremony for speed
and reclaims accountability afterward through automatic `/postmortem`
suggestion. The subagent is authorized to bypass `tdd-gate`, `enough-context`,
and `phase-gate` at its own manifest layer (the hook scripts are untouched);
`safety-guardrails`, `tier-0-preflight`, and `check-invariants` continue to
fire. Every invocation produces a structured audit trail at
`.etc_sdlc/incidents/{YYYY-MM-DD}-{slug}/incident.md` recording the failure
type, the fix, the rollback plan, the gates that were bypassed, and the files
the subagent touched. Three anti-abuse defenses (gates-bypassed audit,
subagent description guardrail, postmortem-or-it-didn't-happen banner) keep
the lane trustworthy as a fire-response tool rather than a TDD escape hatch.
See `standards/process/incident-response.md` for the operator's discipline
guide.

**`/decompose`** — Recursive hierarchical breakdown. Tasks too complex
for a single agent session get broken into subtasks, which get broken into
sub-subtasks, until every leaf is implementable. Enables arbitrary scale.

**`/pull-tickets`** — Closed-loop ticket pipeline. Connects to Linear (or any
task tracker via MCP) and autonomously processes tickets through the full SDLC:

```
/pull-tickets                    # Pull from Linear, build, create PRs
/pull-tickets --triage-only      # Analyze and organize board without building
/pull-tickets --concurrency 3    # Process up to 3 tickets in parallel
```

For each ticket: generates a full PRD from ticket content + codebase research,
runs `/build` with all governance gates, and either creates a PR or rejects the
ticket back to the source with specific, tactful questions. SMEs get feedback in
their own tool — not in an engineering chat they don't follow.

**Triage mode** (`--triage-only`) analyzes the board without building: scores
ticket complexity (S/M/L/XL), maps cross-ticket dependencies, decomposes epics
into sub-issues, and comments analysis on each ticket.

**`/decompose`** — Recursive hierarchical breakdown. Tasks too complex
for a single agent session get broken into subtasks, which get broken into
sub-subtasks, until every leaf is implementable. Enables arbitrary scale.

**`/postmortem`** — When bugs escape, traces them to root cause and appends
prevention rules to `.etc_sdlc/antipatterns.md`. The system learns from mistakes.

## SDLC-as-Code

The entire harness is defined in a single YAML file:

```
spec/etc_sdlc.yaml          ← Source of truth (you edit this)
    │
    ▼
compile-sdlc.py              ← Compiler
    │
    ▼
dist/                        ← Compiled artifacts (gitignored)
    ├── settings-hooks.json
    ├── hooks/
    ├── agents/
    ├── skills/
    ├── standards/
    └── sdlc/
    │
    ▼
install.sh                   ← Deploys to ~/.claude/
```

To change the harness, edit `spec/etc_sdlc.yaml` and recompile. Don't edit the compiled artifacts directly.

### DSL Structure

```yaml
# spec/etc_sdlc.yaml
version: "1.0"

defaults:
  model: sonnet
  on_failure: block
  on_loop: escalate         # Fail loud, don't retry forever
  coverage_threshold: 98

gates:
  tdd-gate:
    event: PreToolUse
    matcher: "Edit|Write"
    type: command
    script: check-test-exists.sh

  task-readiness:
    event: TaskCreated
    type: prompt
    model: sonnet
    role: |
      You are a senior engineering manager reviewing a task
      file before it's assigned to an agent...
    prompt: |
      $ARGUMENTS
      ...

agents:
  backend-developer:
    source: agents/backend-developer.md

skills:
  implement:
    description: "Spec-based implementation workflow"
    flow: [validate_spec, decompose_tasks, dispatch_subagents, verify_and_report]

phases:
  build:
    team: [backend-developer, frontend-developer]
    watchdogs: [code-reviewer, verifier, security-reviewer]
    definition_of_done:
      - "All tasks completed and verified"
      - "Test coverage meets threshold"
```

## What's in the Box

```
spec/
  etc_sdlc.yaml            The SDLC specification (single source of truth)
  prd-hook-test-suite.md   Example PRD (used to build the test suite)
  prd-v1.1-harness-evolution.md  PRD for v1.1 features
  prd-v1.2-templates-journal-checkpoint.md  PRD for v1.2 features
  closed-loop-ticket-pipeline.md  PRD for /pull-tickets (Linear → build → PR)

compile-sdlc.py            DSL compiler → dist/
install.sh                 Deploys compiled artifacts to ~/.claude/

hooks/                     10 hook scripts
  check-test-exists.sh       TDD gate — test file must exist before source edit
  check-invariants.sh        Validates INVARIANTS.md contracts (case-sensitive match)
  check-required-reading.sh  Agent must read required files before coding
  check-phase-gate.sh        Blocks edits inappropriate for current SDLC phase
  check-tier-0.sh            Blocks code edits when DOMAIN.md or PROJECT.md is missing
  block-dangerous-commands.sh Safety — blocks rm -rf, force push, DROP TABLE, undisciplined staging
  block-config-changes.sh    Agent cannot modify its own governance
  inject-standards.sh        Onboards every subagent with standards + antipatterns
  reinject-context.sh        Restores context after compaction
  mark-dirty.sh              Tracks which files changed (breadcrumb for CI)

skills/                    10 skills
  init-project/SKILL.md      /init-project — tiered repo bootstrap (tooling, DOMAIN.md, docs, roles)
  build/SKILL.md             /build — the conductor: full pipeline from spec to verified code
  hotfix/SKILL.md            /hotfix — incident response lane: file, dispatch constrained subagent, suggest postmortem
  spec/SKILL.md              /spec — Socratic loop to generate implementation-ready PRDs
  decompose/SKILL.md         /decompose — recursive hierarchical task breakdown
  implement/SKILL.md         /implement — scale-adaptive dispatch (QUICK/STANDARD/DEEP)
  pull-tickets/SKILL.md      /pull-tickets — closed-loop ticket pipeline (Linear → PRD → build → PR)
  tasks/SKILL.md             /tasks — native task tracker (list, next, board, tree, waves, create, bulk-create)
  postmortem/SKILL.md        /postmortem — trace escaped bugs, build antipatterns knowledge
  checkpoint/SKILL.md        /checkpoint — save session state before compaction

templates/                 4 artifact templates
  adr.md.tmpl                Architecture Decision Record
  agent.md.tmpl              Agent definition with frontmatter
  task.yaml.tmpl             Task file for /implement
  invariant.md.tmpl          INVARIANTS.md entry

agents/                    23 agent definitions
  sem.md                     Orchestrator — owns SDLC phases, deploys teams
  backend-developer.md       TDD zealot — red/green/refactor
  code-reviewer.md           Quality watchdog
  security-reviewer.md       OWASP-trained security scanner
  ... and 19 more

standards/                 19 engineering standards across 6 categories
  process/                   SDLC phases, TDD workflow, code review, definition of done,
                             interactive-user-input (Pattern A picker + Pattern B marker)
  code/                      Clean code, error handling, typing, Python conventions
  testing/                   Test naming, testing standards, LLM evaluation
  architecture/              Abstraction rules, ADR process, layer boundaries
  security/                  Data handling, OWASP checklist
  quality/                   Metrics, guardrail rules

tests/                     276+ tests (pytest, ~7 seconds, sandbox-clean)
  test_block_dangerous.py    30 tests — dangerous command blocking (incl. git-add regex regression)
  test_tdd_gate.py           6 tests — TDD enforcement
  test_invariants.py         15 tests — invariant checking
  test_required_reading.py   5 tests — required reading verification
  test_config_changes.py     11 tests — config change protection
  test_inject_standards.py   7 tests — standards + antipatterns injection
  test_reinject_context.py   6 tests — compaction recovery + journal + checkpoint
  test_mark_dirty.py         7 tests — dirty marker tracking
  test_phase_gate.py         9 tests — SDLC phase enforcement
  test_compiler.py           17 tests — DSL compiler + hook shape-check contracts
  test_pull_tickets.py       13 tests — ticket pipeline skill validation
  test_init_project.py       48 tests — /init-project templates, phases, preflight, SKILL contracts
  test_tasks.py              50 tests — task tracker, waves scoping, feature filter, create/bulk-create
  test_spec_three_state.py    8 tests — /spec three-state classification contract + mutual-exclusion sweep
  conftest.py                Shared fixtures (run_hook, tmp_project, etc.)
```

## Requirements

- [Claude Code](https://claude.ai/code) v2.1.85+
- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (for running tests)
- `jq` (used by hook scripts — `brew install jq` on macOS)

## Philosophy

This project exists because of a simple observation: **AI coding assistants are smart enough to do good work, but they skip steps.** They skip tests, they skip reading the spec, they skip architectural review. Not because they can't — because nothing stops them.

In a real engineering team, you don't rely on individual discipline for quality. You build systems: CI pipelines that block red builds, code review that requires approval, sprint planning that rejects vague tickets. The discipline is in the process, not the person.

This harness applies the same principle to AI agents. The hooks fire deterministically — the agent doesn't choose whether to comply. Governance slows each individual action by 2-5 seconds, but prevents the hours or days of rework that come from skipping steps.

The three outcomes for every hook:
- **Pass** — proceed normally
- **Fail and retry** — block the action, give feedback, let the agent fix it
- **Fail and escalate** — kill the agent, surface the failure to the human (the andon cord)

We never swallow errors. We never lower the bar on the second attempt. We fail early and loud.

## License

[MIT](LICENSE)
