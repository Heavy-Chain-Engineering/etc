# Industrial Coding Harness — Design Document

**Date:** 2026-02-25
**Author:** Jason Vertrees (with Claude analysis)
**Status:** Design approved, pending implementation plan
**Purpose:** Design an industrial-grade, reusable engineering harness that establishes guardrails, roles, and practices for Claude Code-driven development. First deployment: Bald Eagle.

---

## Executive Summary

This document describes a **synthetic engineering organization** — a complete set of AI agents, engineering standards, enforcement mechanisms, and workflow conventions that replicate the discipline of a well-run human software team. The harness is designed to be:

- **Reusable** across projects (user-level components propagate improvements to all projects)
- **Improvable** over time (standards and agents are independently versioned and updatable)
- **Mechanically enforced** (hooks and CI gates, not just documentation)
- **Complete** (covers the full SDLC, not just the coding phase)

The harness is also the first practical instantiation of Jason's **Industrialized System Synthesis (ISS)** vision — a declarative, ontology-grounded approach to software development where specs act as genotype and agent swarms express them into running systems (phenotype).

---

## Connection to Industrialized System Synthesis

The harness maps directly to the ISS biological model:

| ISS Concept | Harness Equivalent |
|---|---|
| **Genotype** (declarative spec) | Standards directory + `.meta/` descriptions + hierarchical PRDs |
| **Gene expression machinery** (agents) | 15-agent roster organized by SDLC phase |
| **Homeostasis** (continuous convergence) | Hooks — continuously reconcile code against standards |
| **Natural selection** (fitness) | Tests + CI + Process Evaluator — kill phenotypes that don't pass |
| **Cells** (components) | The actual code/services produced |
| **Organism** (phenotype) | Running system |
| **Regulatory elements** (gene regulation) | Agent-specific standards + tool restrictions + permission modes |

**Critical distinction from ISS:** Agents are the *process* (gene expression machinery), not the *architecture* (cells/components). They spin up in response to a spec delta, do their work, and the system converges. They are not permanent residents.

---

## Architecture Overview

The harness has two layers and a bootstrap mechanism:

```
+-------------------------------------------------------+
|  USER-LEVEL PLATFORM  (~/.claude/)                     |
|  Your engineering philosophy, codified.                 |
|  Lives once. Applies everywhere. Improved over time.    |
|                                                         |
|  agents/          <- 14 specialized subagents           |
|  standards/       <- Reusable engineering standards     |
|  hooks/           <- Shared hook scripts                |
|  settings.json    <- Global hook wiring                 |
+--------------------+------------------------------------+
                     | references
+--------------------v------------------------------------+
|  PROJECT-LEVEL SCAFFOLDING  (.claude/, root files)      |
|  Per-repo. Checked into version control.                |
|                                                         |
|  .claude/settings.json  <- Project hooks + permissions  |
|  .claude/standards/     <- Domain & arch standards      |
|  CLAUDE.md              <- Concise pointer file         |
|  pyproject.toml         <- Tool config (98% coverage)   |
|  .github/workflows/     <- CI pipeline                  |
|  tests/conftest.py      <- Fixtures + markers           |
|  .meta/                 <- System-level description      |
+----------------------------------------------------------+
```

### Key Principles

1. **CLAUDE.md is a concise routing document.** It says "here's what this project is" and "read these standards directories before working." The actual rules live in the standards files. This keeps CLAUDE.md under the 200-line effective limit and makes standards independently maintainable.

2. **User-level agents are the reusable engineering team.** When you improve the TDD implementer, every project benefits on the next session. No need to copy changes into each repo.

3. **Hooks enforce outcomes, instructions enforce process.** CLAUDE.md and agent system prompts enforce the TDD sequence (write test first). Hooks enforce the result (tests must pass, coverage must meet threshold). CI is the final backstop.

4. **Standards are separate files, not embedded in CLAUDE.md.** Each standard is independently maintainable, versionable, and loadable by specific agents.

---

## The `.meta/` Convention — Ambient Context Through the Ambiguity Gradient

Every directory in the source tree contains a `.meta/` subdirectory with a `description.md` file that describes what that directory contains and everything below it. This creates an **ambiguity gradient** — a spectrum from strategic intent at the top to executable precision at the bottom.

### How It Works

```
src/bald_eagle/
|-- .meta/
|   +-- description.md              <- "A regulatory compliance platform that helps
|                                       manufacturers navigate DRNSG across jurisdictions."
|                                       Strategic. Broad. PM and architect level.
|
|-- prd.md                          <- Top-level system PRD
|
|-- ingestion/
|   |-- .meta/
|   |   +-- description.md          <- "The ingestion subsystem processes regulatory
|   |                                   documents into structured, searchable knowledge.
|   |                                   Handles PDF parsing, section-aware chunking,
|   |                                   metadata extraction, and embedding."
|   |                                   Subsystem level. Architect and lead dev.
|   |
|   |-- prd.md                      <- Ingestion subsystem PRD
|   |-- chunking/
|   |   |-- .meta/
|   |   |   +-- description.md      <- "Section-aware document chunking. Preserves
|   |   |                               article/annex boundaries. Hierarchical nodes:
|   |   |                               regulation -> chapter -> article -> paragraph.
|   |   |                               Uses LlamaIndex HierarchicalNodeParser.
|   |   |                               Chunk size: 1024 tokens, overlap: 128."
|   |   |                               Module level. Developer-precise.
|   |   +-- service.py
|   +-- parsing/
|       |-- .meta/
|       |   +-- description.md
|       +-- service.py
|
|-- retrieval/
|   |-- .meta/
|   |   +-- description.md
|   |-- prd.md
|   +-- ...
|
+-- compliance/
    |-- .meta/
    |   +-- description.md
    |-- prd.md
    +-- ...
```

### The Ambiguity Gradient

| Level | Ambiguity | Audience | Content |
|---|---|---|---|
| System root `.meta/` | High — strategic intent | PM, stakeholders, all agents | What the system does, who it serves, core value proposition |
| Subsystem `.meta/` | Medium — boundaries and contracts | Architect, lead dev | Subsystem responsibilities, interfaces, key dependencies |
| Module `.meta/` | Low — specific behavior and constraints | Developer agents | Tech choices, algorithms, configuration, data flow |
| File-level (docstrings) | None — executable specification | Code reviewer, verifier | Implementation-level annotations |

### Rollup Mechanism

Each `.meta/description.md` at a higher level summarizes the `.meta/` descriptions below it. Change a module-level description, and it propagates upward. This keeps every level in sync without requiring humans to manually maintain redundant documentation.

### Why `.meta/` Matters for Agents

An agent working at ANY level can orient itself:
- **"I'm working in `ingestion/chunking/`"** — reads `.meta/description.md` — knows exactly what this module does, its constraints, its tech choices
- **"I'm reviewing the whole system"** — reads top-level `.meta/description.md` — gets the strategic picture without drowning in detail
- **"I'm the architect planning a new subsystem"** — reads subsystem-level `.meta/` files — understands boundaries and contracts

This is the ISS "boundary object" concept made concrete: the same directory structure serves product managers, architects, developers, and agents — each reading at their appropriate zoom level.

### Spec Lives WITH the Code

The `.meta/` convention embeds the spec in the source tree, not in a separate documentation repo. The genotype travels with the phenotype. This means:
- The spec is always in sync with the code structure
- Git history tracks spec evolution alongside code evolution
- PRs that change code also update the relevant `.meta/` descriptions
- Agents always have access to local context without leaving the source tree

---

## Hierarchical PRD Structure

The system specification is a tree of PRDs, organized to mirror the system structure. Each level provides increasing specificity.

```
docs/
+-- system-spec-readme.md           <- Top-level manifest (already exists)
+-- prd.md                          <- System-level PRD (already exists)
+-- prd/
    |-- core-platform.md            <- Core infrastructure PRD
    |-- ingestion-pipeline.md       <- Ingestion subsystem PRD
    |-- retrieval-service.md        <- Retrieval subsystem PRD
    |-- compliance-planning.md      <- Compliance planning PRD
    |-- ui.md                       <- Frontend PRD
    +-- features/
        |-- document-upload.md      <- Feature-level PRD
        |-- hybrid-search.md
        |-- applicability-engine.md
        +-- golden-answer-eval.md
```

The PRD tree and the `.meta/` tree are complementary:
- **PRDs** describe the desired behavior (what to build)
- **`.meta/`** describes the current reality (what exists, how it works)
- **The delta** between PRD intent and `.meta/` reality generates work units for agents

This is exactly the ISS "declared state vs. existing state" diffing mechanism.

### Iterative Spec Creation

The specification process itself is iterative:
1. Human SME provides domain knowledge and business intent
2. PM and Architect agents help structure this into PRDs (Socratically — asking questions, being opinionated within guardrails)
3. PRDs decompose via TaskMaster into implementation tasks
4. Agent swarms implement tasks
5. `.meta/` descriptions update to reflect new reality
6. Process Evaluator measures outcomes
7. Feedback informs the next spec iteration

---

## The Complete Agent Roster

15 agents covering the full SDLC. Each has a focused persona, constrained tools, standards they follow, and a phase where they activate.

### Strategy & Spec Layer

| Agent | Persona | Key Behavior | Tools |
|---|---|---|---|
| **Product Manager** | Pragmatic, outcome-focused. Thinks in user problems, not features. Kills scope creep. | Translates business intent into structured specs. Asks "why does the user need this?" Owns prioritization. Socratic with stakeholders, decisive on scope. | Read, Grep, Glob, Write (specs only) |
| **Product Owner** | Stakeholder advocate. Writes acceptance criteria. Guards the definition of done. | Validates that specs match business intent. Writes acceptance criteria as testable assertions. Approves or rejects deliverables against spec. | Read, Grep, Glob |

### Design Layer

| Agent | Persona | Key Behavior | Tools |
|---|---|---|---|
| **UX Designer** | User-obsessed. Thinks in flows, not screens. Accessibility-first. | Produces interaction designs, user flows, information architecture. Challenges assumptions about what users actually need vs. what was requested. | Read, Grep, Glob, Write (design docs) |
| **UI Designer** | Visual craftsman. Design system thinker. Pixel-precise but practical. | Translates UX flows into component-level visual designs. Maintains design system consistency. Produces implementable specs, not aspirational mockups. | Read, Grep, Glob, Write, Edit (frontend only) |

### Architecture Layer

| Agent | Persona | Key Behavior | Tools |
|---|---|---|---|
| **Architect** | Martin Fowler meets pragmatist. Understands abstractions AND business constraints. Anti-over-engineering. | Designs system boundaries, data flow, integration patterns. Produces ADRs. Reviews for layer violations, coupling, premature abstraction. "Pattern must appear twice before abstracting." | Read, Grep, Glob, Write (ADRs, .meta/) |
| **Domain Modeler** | Eric Evans disciple. Obsessed with ubiquitous language. | Validates domain model, bounded contexts, entity relationships. Catches terminology drift. Ensures code reflects domain language, not implementation language. | Read, Grep, Glob |

### Implementation Layer

| Agent | Persona | Key Behavior | Tools |
|---|---|---|---|
| **Backend Developer** | Clean coder. TDD zealot. Idiomatic Python. | Red/green TDD strictly enforced. Writes minimum code to pass tests. Follows standards directory. Knows the tech stack deeply (FastAPI, Pydantic, SQLAlchemy, LlamaIndex, PydanticAI). | Read, Edit, Write, Bash, Grep, Glob |
| **Frontend Developer** | Component thinker. Accessibility-aware. Performance-conscious. | Red/green TDD. Builds from design system components. Semantic HTML, proper ARIA, responsive-first. | Read, Edit, Write, Bash, Grep, Glob |
| **DevOps Engineer** | Infrastructure-as-code. Docker, CI/CD, monitoring. Automates everything. | Manages Docker Compose, CI pipeline, deployment configs. Reviews Dockerfiles, workflow files, environment configs. "If it's not automated, it doesn't exist." | Read, Edit, Write, Bash, Grep, Glob |

### Quality Layer

| Agent | Persona | Key Behavior | Tools |
|---|---|---|---|
| **Code Reviewer** | Reads standards directory before every review. Catches what tests can't. | Reviews against engineering standards. Checks clean code, idiomatic patterns, SOLID, no dead code, no silent errors, naming, clarity, architecture drift, security smells. Reports issues by severity: critical, warning, suggestion. | Read, Grep, Glob, Bash |
| **Verifier (QA)** | Hard gate. No opinions, only facts. Tests pass or they don't. | Runs full test suite + coverage + types + lint. Blocks completion if ANY threshold is missed. The mechanical gatekeeper. Cannot be bypassed. | Read, Bash, Grep, Glob |
| **Security Reviewer** | OWASP-trained. Paranoid by design. | Reviews for injection, XSS, secrets in source, auth bypass, input validation gaps, dependency vulnerabilities. Flags before code ships, not after. | Read, Grep, Glob, Bash |

### Evaluation Layer

| Agent | Persona | Key Behavior | Tools |
|---|---|---|---|
| **Process Evaluator** | Data-driven. Measures outcomes, not activity. Trend-obsessed. | Tracks: spec-to-implementation fidelity, test coverage trends, defect rates, velocity, regression frequency, code complexity over time. Produces periodic reports. Answers "are we getting better?" with data, not feelings. | Read, Bash, Grep, Glob |

### Bootstrap Layer

| Agent | Persona | Key Behavior | Tools |
|---|---|---|---|
| **Brownfield Bootstrapper** | Archaeologist meets cartographer. Reads existing code and derives the genotype from the phenotype. | For existing codebases (brownfield): spins up agent teams that parallelize by directory subtree, read bottom-up through the source tree, create `.meta/description.md` at every directory level, then roll up summaries from leaf to root. Creates the ambiguity gradient from an existing system. Also identifies missing tests, undocumented modules, architectural patterns, and tech debt. The output is a complete `.meta/` tree that represents "what the system actually is" — ISS Phase 0 (Observe). | Read, Write, Grep, Glob, Bash, Task (spawns agent teams) |

**How the Brownfield Bootstrapper works:**
1. Spawns agent teams organized by top-level directory (one team per subsystem)
2. Each team reads bottom-up: files → module `.meta/` → subsystem `.meta/`
3. At each level, the agent creates `.meta/description.md` with: purpose, key components, dependencies, patterns used, tech choices
4. After all teams complete, the bootstrapper synthesizes the root-level `.meta/description.md`
5. Optionally: generates a gap analysis (missing tests, undocumented APIs, architectural concerns)

This works for greenfield too — after the first implementation pass, the bootstrapper creates the `.meta/` tree for the newly written code.

### Support Layer

| Agent | Persona | Key Behavior | Tools |
|---|---|---|---|
| **Technical Writer** | Clear, concise, audience-aware. Docs-as-code. | API documentation, architecture docs, `.meta/` descriptions, user-facing content. Keeps docs in sync with code. "If it's not documented, it doesn't exist." | Read, Edit, Write, Grep, Glob |

### Agent Activation by SDLC Phase

```
Bootstrap:       Brownfield Bootstrapper (derives .meta/ from existing code)
Spec Phase:      PM -> Product Owner -> Domain Modeler
Design Phase:    Architect -> UX Designer -> UI Designer
Build Phase:     Backend Dev -> Frontend Dev -> DevOps
                      | (continuous loop)
                 Code Reviewer -> Verifier -> Security Reviewer
Ship Phase:      Technical Writer -> DevOps -> Verifier (final gate)
Evaluate:        Process Evaluator (continuous)
Reconcile:       Brownfield Bootstrapper (updates .meta/ after changes)
```

### Agent Design Principles

1. **Socratic but opinionated.** Top-level agents (PM, Architect, UX Designer) ask clarifying questions when ambiguity exists, but also make decisions within their guardrails. They don't just execute — they think.

2. **Constrained tools.** Each agent only has access to the tools it needs. Read-only agents cannot write. Spec agents cannot edit source code. This prevents role confusion and unauthorized changes.

3. **Standards-driven.** Every agent's system prompt references the specific standards files relevant to its role. The Backend Developer loads `tdd-workflow.md` + `python-conventions.md` + `testing-standards.md`. The Code Reviewer loads everything.

4. **Phase-activated, not permanent.** Agents spin up when their phase is active and stand down when done. They are expression machinery, not permanent residents.

5. **Persistent memory (where appropriate).** Agents like the Code Reviewer and Architect benefit from `memory: project` — they learn codebase patterns over time and apply them consistently.

---

## Standards Directory Structure

The standards are the **genotype** — the declarative rules that constrain how every agent works. Organized by concern, split between reusable (user-level) and project-specific.

### User-Level Standards (`~/.claude/standards/`)

These are YOUR engineering philosophy. They apply to every project.

```
~/.claude/standards/
|-- process/
|   |-- tdd-workflow.md                 <- Red/green TDD cycle definition
|   |-- sdlc-phases.md                 <- Phase definitions, agent activation rules
|   |-- code-review-process.md         <- What reviewers check, severity levels
|   +-- definition-of-done.md          <- What "done" means for any task
|-- code/
|   |-- python-conventions.md          <- Idiomatic Python, naming, structure
|   |-- clean-code.md                  <- Function length, file length, complexity limits
|   |-- typing-standards.md            <- mypy strict, no Any, Pydantic models
|   +-- error-handling.md              <- No silent swallowing, explicit error types
|-- testing/
|   |-- testing-standards.md           <- 98% coverage, marker tiers, no test logic
|   |-- llm-evaluation.md             <- Golden answers, retrieval vs generation eval
|   +-- test-naming.md                <- "should X when Y" convention
|-- architecture/
|   |-- layer-boundaries.md            <- Dependency direction, no layer violations
|   |-- abstraction-rules.md           <- "Twice before abstracting", YAGNI
|   +-- adr-process.md                <- When and how to write ADRs
|-- security/
|   |-- owasp-checklist.md             <- Top 10, input validation, secrets management
|   +-- data-handling.md              <- What can leave internal tier, sanitization rules
+-- quality/
    +-- metrics.md                     <- What the evaluator measures, thresholds
```

### Project-Level Standards (`<project>/.claude/standards/`)

These are project-specific. Checked into version control.

```
<project>/.claude/standards/
|-- domain-constraints.md              <- DRNSG taxonomy, legal hierarchy rules
|-- tech-stack.md                      <- FastAPI, Pydantic, LlamaIndex conventions
|-- architecture.md                    <- Three-tier model, Bridge Tier rules
+-- agent-operating-rules.md           <- No fabrication, halt on ambiguity, etc.
```

### How CLAUDE.md References Standards

CLAUDE.md becomes a concise pointer:

```markdown
## Standards

Before writing or reviewing code, read:
- All files in ~/.claude/standards/ (engineering standards)
- All files in .claude/standards/ (project standards)

These are mandatory constraints, not suggestions. Violations will be caught
by the Code Reviewer and Verifier agents and must be resolved before completion.
```

Each agent's system prompt also references the specific standards relevant to its role, using the `skills` frontmatter field to preload them.

---

## Hooks and Enforcement — The Homeostasis Layer

Hooks provide continuous reconciliation between the code's actual state and the declared standards. Three enforcement points:

### Hook 1: PreToolUse on Edit|Write — "Test File Must Exist"

**Trigger:** Before any Edit or Write to a production source file.
**Action:** Check that a corresponding test file exists. If not, deny with "write a failing test first."
**Performance:** File existence check — instant, no test execution.
**Location:** User-level (`~/.claude/hooks/check-test-exists.sh`) or project-level.

```bash
#!/bin/bash
# .claude/hooks/check-test-exists.sh
INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')
CWD=$(echo "$INPUT" | jq -r '.cwd // "."')

# Only gate production code
if [[ "$FILE_PATH" == */src/* ]]; then
  # Extract module name from path
  MODULE=$(basename "$FILE_PATH" .py)
  if ! find "${CWD}/tests" -name "*${MODULE}*" -o -name "test_*${MODULE}*" 2>/dev/null | grep -q .; then
    echo "No test file found for ${FILE_PATH}. Write a failing test first (Red/Green TDD)." >&2
    exit 2
  fi
fi
exit 0
```

### Hook 2: PostToolUse on Edit|Write — "Mark Dirty"

**Trigger:** After any Edit or Write to a production source file.
**Action:** Touch a `.tdd-dirty` marker file. Zero-cost breadcrumb.
**Purpose:** Tells the Stop hook that production code changed and needs validation.

```bash
#!/bin/bash
# .claude/hooks/mark-dirty.sh
INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')
CWD=$(echo "$INPUT" | jq -r '.cwd // "."')

if [[ "$FILE_PATH" == */src/* ]]; then
  touch "${CWD}/.tdd-dirty"
fi
exit 0
```

### Hook 3: Stop — "Hard Gate"

**Trigger:** When an agent is about to finish responding.
**Action:** If `.tdd-dirty` exists, run full test suite + coverage + types + lint. Block completion if anything fails.
**Effect:** The agent sees the error and must fix it before it can finish.

```bash
#!/bin/bash
# .claude/hooks/verify-green.sh
INPUT=$(cat)
CWD=$(echo "$INPUT" | jq -r '.cwd // "."')

if [ -f "${CWD}/.tdd-dirty" ]; then
  cd "$CWD"

  # Run tests with coverage
  OUTPUT=$(python -m pytest --cov --cov-fail-under=98 -x --tb=short -q 2>&1)
  EXIT_CODE=$?

  if [ $EXIT_CODE -ne 0 ]; then
    echo "VERIFICATION FAILED: Tests failed or coverage below 98%." >&2
    echo "$OUTPUT" | tail -30 >&2
    exit 2
  fi

  # Clean dirty marker on success
  rm -f "${CWD}/.tdd-dirty"
fi
exit 0
```

### Hook 4: TaskCompleted — "Team Gate"

**Trigger:** When an agent team task is marked complete.
**Action:** Run full verification suite. Prevent task completion if any check fails.
**Location:** Project-level `.claude/settings.json`.

### Hook Configuration

**User-level (`~/.claude/settings.json`):**

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [
          {
            "type": "command",
            "command": "~/.claude/hooks/check-test-exists.sh",
            "timeout": 5,
            "statusMessage": "Checking TDD compliance..."
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [
          {
            "type": "command",
            "command": "~/.claude/hooks/mark-dirty.sh",
            "timeout": 2
          }
        ]
      }
    ]
  }
}
```

**Project-level (`.claude/settings.json`):**

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": ".claude/hooks/verify-green.sh",
            "timeout": 120,
            "statusMessage": "Verifying tests pass and coverage >= 98%..."
          }
        ]
      }
    ],
    "TaskCompleted": [
      {
        "hooks": [
          {
            "type": "command",
            "command": ".claude/hooks/verify-green.sh",
            "timeout": 120,
            "statusMessage": "Validating task completion..."
          }
        ]
      }
    ]
  }
}
```

### Enforcement Layer Summary

```
Layer 1: CLAUDE.md + Agent System Prompts
         -> Enforce PROCESS (TDD sequence, standards reading)
         -> Instruction-driven, behavioral

Layer 2: PreToolUse Hooks
         -> Enforce PRECONDITIONS (test file exists before code edit)
         -> Mechanical gate, instant

Layer 3: Stop / TaskCompleted Hooks
         -> Enforce OUTCOMES (tests pass, coverage met)
         -> Mechanical gate, runs full suite

Layer 4: CI Pipeline
         -> Enforce MERGE CRITERIA (backstop for anything that bypasses hooks)
         -> Final gate, blocks PR merge
```

---

## CI Pipeline Enhancements

The existing CI pipeline is solid. Additions needed:

### Coverage Threshold Update

Change from 80% to 98% in both `pyproject.toml` and CI.

### LLM Evaluation Tier

Add a new CI job that runs `pytest -m llm_eval` on PRs:

```yaml
llm-eval:
  name: LLM Evaluation Tests
  if: github.event_name == 'pull_request'
  needs: [typecheck, lint]
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    - name: Install uv
      uses: astral-sh/setup-uv@v5
      with:
        enable-cache: true
    - name: Set up Python
      uses: actions/setup-python@v5
      with:
        python-version: ${{ env.PYTHON_VERSION }}
    - name: Install dependencies
      run: uv sync --frozen --dev
    - name: Run LLM evaluation tests
      env:
        OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
        ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
      run: uv run pytest tests/llm_eval/ -m llm_eval --tb=short -v
```

### New Pytest Markers

```toml
markers = [
    "unit: Unit tests (isolated, no external dependencies)",
    "integration: Integration tests (require database or external services)",
    "e2e: End-to-end tests (full workflow)",
    "llm_eval: LLM evaluation tests (require API keys, validate reasoning quality)",
    "golden_answer: Golden answer assertions from SME-validated compliance plan",
    "slow: Tests that take significant time to run",
]
```

---

## Workflow Model

The human's role is SME + spec author. Agents handle expression.

```
Human (SME) --> System Spec --> Hierarchical PRDs --> Agent Swarms --> Running System
                     ^                                        |
                     +-- Process Evaluator (fitness feedback) -+
```

### Detailed Workflow

1. **Human provides domain knowledge and business intent.** Brings SME expertise, makes strategic decisions, reviews and approves specs.

2. **Strategy agents structure the spec.** PM and Product Owner help translate intent into structured PRDs. They are Socratic (ask questions) but opinionated (make decisions within guardrails). Domain Modeler validates terminology.

3. **Design agents produce architecture and UX.** Architect creates system boundaries and ADRs. UX/UI designers produce interaction and visual designs.

4. **PRDs decompose into tasks.** TaskMaster parses PRDs into implementation tasks with dependencies, complexity analysis, and subtask expansion.

5. **Implementation agents execute.** Agent teams or subagents claim tasks. Backend/Frontend Developers write code using red/green TDD. DevOps manages infrastructure.

6. **Quality agents gate.** Code Reviewer validates against standards. Verifier runs the hard gate. Security Reviewer checks for vulnerabilities. All must pass before task completion.

7. **Technical Writer updates documentation.** `.meta/` descriptions update to reflect new reality. API docs, architecture docs stay in sync.

8. **Process Evaluator measures.** Tracks trends across iterations. Reports whether the process is producing better outcomes.

9. **Feedback informs next iteration.** Evaluator findings feed back into spec refinement. The cycle repeats.

### The Existing Process (What Works Today)

The user's current process — SpecKit + TaskMaster + Claude Code — already works well:
- **SpecKit** (`docs/speckit/`) — Constitution (governance) + Specify (behavior spec)
- **TaskMaster** — Task decomposition, dependency management, progress tracking
- **Claude Code** — AI-assisted implementation

The harness EXTENDS this, not replaces it. It adds:
- Agent specialization (instead of one general-purpose Claude Code session doing everything)
- Mechanical enforcement (hooks and CI gates)
- Standards-as-files (instead of standards buried in CLAUDE.md)
- The `.meta/` convention (ambient context at every directory level)
- Evaluation (closed feedback loop)

---

## Testing Strategy

### Four Test Tiers

| Tier | Marker | Runs When | What It Tests | Speed |
|---|---|---|---|---|
| **Tier 1: Deterministic** | `unit` | Every commit (hook + CI) | Pydantic schemas, chunking math, score normalization, applicability rules | Seconds |
| **Tier 2: Retrieval Quality** | `integration` | Every push (CI) | Top-k chunk relevance, jurisdiction filtering, hybrid search quality | Minutes |
| **Tier 3: LLM Output** | `llm_eval` | Every PR (CI) | Golden-answer comparison, applicability correctness, hallucination detection | Minutes (costs tokens) |
| **Tier 4: Regression** | `golden_answer` | Every PR (CI) | Cross-run comparison, pass/fail delta detection, trend tracking | Minutes |

### Coverage Requirements

- **98% line and branch coverage minimum**, enforced by:
  - `pyproject.toml`: `fail_under = 98`
  - Stop hook: `pytest --cov-fail-under=98`
  - CI: `uv run pytest --cov-fail-under=98`
- **No `# pragma: no cover`** without a linked justification comment
- **Coverage may not decrease** between PRs

### Red/Green TDD Workflow (Mandatory)

Per Simon Willison's agentic engineering pattern:

1. **RED**: Write a failing test that defines expected behavior. Run it. Confirm it fails.
2. **GREEN**: Write the minimum implementation to make the test pass. Run it. Confirm it passes.
3. **REFACTOR**: Clean up without changing behavior. Run tests. Confirm still green.

**Critical:** Confirming the test fails (step 1) is non-negotiable. Skipping this risks creating tests that already pass — tests that validate nothing.

Every good model understands "red/green TDD" as shorthand for this full workflow. Agent system prompts include this explicitly.

### LLM Evaluation Tests

LLM evaluations are first-class pytest tests, not a separate evaluation runner:

```python
@pytest.mark.llm_eval
@pytest.mark.golden_answer
@pytest.mark.parametrize("drnsg,expected", GOLDEN_ANSWERS["novagenesis"])
def test_should_determine_correct_applicability_when_given_novagenesis(
    compliance_pipeline, novagenesis_product_def, drnsg, expected
):
    result = compliance_pipeline.determine_applicability(
        product=novagenesis_product_def, drnsg=drnsg
    )
    assert result.status == expected.status
    assert result.basis_type == expected.basis_type
    if expected.residual_obligations:
        assert result.residual_obligations == expected.residual_obligations
```

### Retrieval vs. Generation Separation

When a test fails, we need to know WHY:
- **Retrieval problem:** The right chunks weren't surfaced
- **Generation problem:** Right chunks found, LLM misinterpreted
- **Ingestion problem:** Information wasn't in the corpus at all

The evaluation framework separates these failure modes with dedicated test fixtures that isolate each component.

---

## What CLAUDE.md Becomes

After the harness is installed, CLAUDE.md is concise:

```markdown
# CLAUDE.md

## Project
[2-3 sentence project description]

## Standards
Before writing or reviewing code, read:
- All files in ~/.claude/standards/ (engineering standards)
- All files in .claude/standards/ (project standards)
These are mandatory constraints, not suggestions.

## Context
- Read .meta/description.md in your working directory for local context
- Read parent .meta/ files for broader system context
- Read docs/prd.md and relevant sub-PRDs for requirements

## Tech Stack
[Brief list — Python 3.14, FastAPI, Pydantic, etc.]

## Domain
See DOMAIN.md and docs/domain-taxonomy.md for domain model.
See .claude/standards/domain-constraints.md for invariants.
```

Everything else lives in the standards files, `.meta/` descriptions, and agent system prompts.

---

## Implementation Phases

### Phase 1: User-Level Platform (build first)
- Create `~/.claude/agents/` with all 14 agent definitions
- Create `~/.claude/standards/` with engineering standards files
- Create `~/.claude/hooks/` with enforcement scripts
- Update `~/.claude/settings.json` with hook wiring
- Test with a toy project before deploying to Bald Eagle

### Phase 2: Project Template
- Create GitHub template repo with project-level scaffolding
- `.claude/settings.json`, `.claude/standards/`, CI pipeline, pyproject.toml, CLAUDE.md skeleton, tests/conftest.py, Makefile, .meta/ convention
- Optionally integrate with existing project-bootstrapper skill

### Phase 3: Deploy to Bald Eagle
- Apply project template to bald-eagle repo
- Create `.claude/standards/` with Bald Eagle domain constraints
- Create `.meta/` descriptions for existing source tree
- Update pyproject.toml (98% coverage, new markers)
- Enhance CI pipeline (LLM eval tier)
- Begin using agent roster for implementation tasks

### Phase 4: Evaluate and Improve
- Process Evaluator tracks outcomes across first sprint
- Identify which agents are most/least effective
- Refine standards based on actual friction points
- Improve hooks based on false positive/negative rates
- Update agent personas based on observed behavior

---

## Future Vision: Declarative Reconciliation

The harness architecture is designed so that declarative reconciliation becomes possible as the system matures. This is the ISS endgame — not built this week, but the direction we're building toward.

### The Mechanism

The `.meta/` descriptions represent **derived state** (what the system IS). The PRDs represent **declared state** (what the system SHOULD BE). When these diverge, the delta produces work units:

```
Declared State (PRDs)          Derived State (.meta/)
"Ingestion uses                "Ingestion uses
 HierarchicalNodeParser,        SentenceSplitter,
 1024 tokens"                   128 tokens"
         |                              |
         +------ DELTA -----------------+
                   |
                   v
         Work Unit: "Refactor chunking
          from SentenceSplitter(128) to
          HierarchicalNodeParser(1024)"
                   |
                   v
         Agent team claims and implements
                   |
                   v
         .meta/ updates to match PRD
         (system converges)
```

### What This Enables (Future)

At its most powerful, changing the spec changes the system:

- **Tech stack swap:** Update a subsystem PRD from "Python/FastAPI" to "Java/Spring Boot" — agents rewrite the subsystem, including data models, tests, and deployment config. Database layer (SQL) stays the same; application layer is re-expressed.
- **Architecture migration:** Update the spec from "monolith" to "microservices for auth and billing" — agents extract the bounded contexts into separate services with API contracts.
- **Framework upgrade:** Update from "LlamaIndex 0.12" to "LlamaIndex 1.0" — agents identify breaking changes, update imports, adjust API calls, re-run tests.
- **Feature removal:** Remove a feature from the PRD — agents identify all code, tests, and docs related to that feature and cleanly excise them.

### Why the Harness Makes This Possible

The `.meta/` convention, hierarchical PRDs, and agent roster are the prerequisite infrastructure:
- `.meta/` provides the derived state in a structured, parseable format
- PRDs provide the declared state at matching granularity
- The agent roster provides the expression machinery to close deltas
- The verification layer (tests + hooks + CI) ensures convergence is correct

Without the harness, declarative reconciliation is impossible — there's no structured representation of either state, and no constrained machinery to close the gap.

---

## Open Design Questions

1. **Should the `.meta/` rollup be manual or agent-assisted?** A "spec reconciler" agent could periodically re-summarize upward when lower levels change. Or humans curate the higher levels.

2. **How do agent teams coordinate on larger features?** Does the Architect create the task breakdown, or does the PM? Or TaskMaster from the PRD?

3. **Should the Process Evaluator have its own persistent memory?** Trend data across sessions would enable "are we getting better over time?" analysis.

4. **How granular should the `.meta/` descriptions be?** Every directory? Only directories with 3+ files? Only directories that represent a logical module?

5. **Should standards files use a structured format** (YAML frontmatter + markdown body) or pure markdown? Structured format would allow agents to parse metadata (applies_to_role, severity, etc.).

6. **How do we handle standards conflicts?** If a project-level standard contradicts a user-level standard, which wins? (Proposed: project-level overrides user-level, like CSS specificity.)

---

## Glossary

| Term | Definition |
|---|---|
| **Harness** | The complete set of agents, standards, hooks, and conventions that constitute the synthetic engineering team |
| **User-level** | Configuration stored in `~/.claude/` that applies to all projects |
| **Project-level** | Configuration stored in `<project>/.claude/` that applies to one project |
| **Standards** | Engineering rules stored as separate files, referenced by CLAUDE.md and agent prompts |
| **`.meta/`** | Convention for embedding contextual descriptions at every directory level |
| **Ambiguity gradient** | The spectrum from strategic (high-level, broad) to precise (low-level, specific) across the directory tree |
| **Agent roster** | The 14 specialized agents that constitute the synthetic engineering team |
| **Expression machinery** | Agents viewed as ISS gene expression — they spin up, reconcile state, and stand down |
| **Fitness function** | Tests + CI + Process Evaluator — the mechanism that determines if the system is improving |
| **Genotype** | The declarative spec (standards + PRDs + `.meta/` descriptions) |
| **Phenotype** | The running system produced by agent expression of the genotype |
