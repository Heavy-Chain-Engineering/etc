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
uv run pytest      # 121 tests, ~3 seconds
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

### The 14 Gates

```yaml
# Preconditions — before work begins
definition-of-ready:     UserPromptSubmit  → prompt  "Is this request clear enough?"
safety-guardrails:       PreToolUse (Bash) → command  Block rm -rf, force push, DROP TABLE
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
change-control:          ConfigChange       → command  Agent cannot loosen its own governance
compaction-recovery:     SessionStart       → command  Re-inject context after compaction
```

### The `/spec` → `/build` Pipeline

The full pipeline from idea to verified, working code:

```
/spec "Add user authentication"       → PRD with gray areas resolved
/build .etc_sdlc/features/auth/spec.md → validated, decomposed, built, verified
```

**`/spec`** — Socratic specification loop:
1. Asks clarifying questions (never starts writing immediately)
2. Researches the codebase and web for patterns, pitfalls, security
3. Surfaces gray areas — ambiguous decisions resolved before writing
4. Builds the PRD section by section, each approved by the user
5. Validates against Definition of Ready before finalizing

**`/build`** — The conductor. Orchestrates the full pipeline:
1. **Validate** — spec passes Definition of Ready
2. **Decompose** — break PRD into tasks with hierarchical IDs
3. **Score & Recurse** — any task scoring > 7 gets decomposed further (arbitrary depth)
4. **Plan Waves** — group by dependency, verify no file overlaps
5. **Execute** — dispatch wave by wave, verify after each wave
6. **Verify** — full CI + architectural review
7. **Report** — verification.md + summary

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

  definition-of-ready:
    event: UserPromptSubmit
    type: prompt
    model: sonnet
    role: |
      You are the VP of Engineering...
    prompt: |
      Review this request: $ARGUMENTS
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

compile-sdlc.py            DSL compiler → dist/
install.sh                 Deploys compiled artifacts to ~/.claude/

hooks/                     9 hook scripts
  check-test-exists.sh       TDD gate — test file must exist before source edit
  check-invariants.sh        Validates INVARIANTS.md contracts
  check-required-reading.sh  Agent must read required files before coding
  check-phase-gate.sh        Blocks edits inappropriate for current SDLC phase
  block-dangerous-commands.sh Safety — blocks rm -rf, force push, DROP TABLE, git add -A
  block-config-changes.sh    Agent cannot modify its own governance
  inject-standards.sh        Onboards every subagent with standards + antipatterns
  reinject-context.sh        Restores context after compaction
  mark-dirty.sh              Tracks which files changed (breadcrumb for CI)

skills/                    7 skills
  build/SKILL.md             /build — the conductor: full pipeline from spec to verified code
  spec/SKILL.md              /spec — Socratic loop to generate implementation-ready PRDs
  decompose/SKILL.md         /decompose — recursive hierarchical task breakdown
  implement/SKILL.md         /implement — scale-adaptive dispatch (QUICK/STANDARD/DEEP)
  tasks/SKILL.md             /tasks — native task tracker (list, next, board, tree, waves)
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

standards/                 18 engineering standards across 6 categories
  process/                   SDLC phases, TDD workflow, code review, definition of done
  code/                      Clean code, error handling, typing, Python conventions
  testing/                   Test naming, testing standards, LLM evaluation
  architecture/              Abstraction rules, ADR process, layer boundaries
  security/                  Data handling, OWASP checklist
  quality/                   Metrics, guardrail rules

tests/                     148 tests (pytest, ~4 seconds)
  test_block_dangerous.py    18 tests — dangerous command blocking
  test_tdd_gate.py           6 tests — TDD enforcement
  test_invariants.py         15 tests — invariant checking
  test_required_reading.py   5 tests — required reading verification
  test_config_changes.py     11 tests — config change protection
  test_inject_standards.py   7 tests — standards + antipatterns injection
  test_reinject_context.py   6 tests — compaction recovery + journal + checkpoint
  test_mark_dirty.py         7 tests — dirty marker tracking
  test_phase_gate.py         9 tests — SDLC phase enforcement
  test_compiler.py           12 tests — DSL compiler output
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
