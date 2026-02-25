# Agent Hardening Research

**Date:** 2026-02-25
**Purpose:** Research findings to drive hardening of 22 Claude Code agent definitions
**Scope:** Agent definition best practices, community patterns, senior engineering heuristics, TDD enforcement, gap analysis of current agents

**Note on sources:** WebSearch and WebFetch were unavailable during this research session. Findings in sections 1-4 are synthesized from training data (Anthropic documentation through early 2025, engineering blogs, community repos). Section 5 (gap analysis) is based on direct reading of all 22 agent files and 17 standards files in the repo. URLs are provided where known but could not be verified live.

---

## 1. Claude Code Agent Best Practices

### Official Documentation Findings

Claude Code agents are defined as Markdown files with YAML frontmatter. The canonical location is a project's `.claude/agents/` directory or a user-level `~/.claude/agents/` directory. Key documentation sources:

- https://docs.anthropic.com/en/docs/claude-code/agents
- https://docs.anthropic.com/en/docs/claude-code/skills
- https://docs.anthropic.com/en/docs/claude-code/memory

**Required Frontmatter Fields:**

| Field | Required | Notes |
|-------|----------|-------|
| `name` | Yes | kebab-case identifier, used to invoke the agent |
| `description` | Yes | Shown to the orchestrating model for agent selection. THIS IS THE MOST IMPORTANT FIELD for routing. |
| `tools` | Yes | Comma-separated list of tools the agent can use. Constrains capability. |
| `model` | No | `opus`, `sonnet`, `haiku`, or `inherit`. Defaults to the invoking model. |

**Skills vs. Agents:**

Skills and agents differ in scope and invocation pattern:

| Dimension | Agent | Skill |
|-----------|-------|-------|
| **Scope** | Full persona with workflow, judgment, process | Narrow capability with specific procedure |
| **Invocation** | Via Task tool or direct user invocation | Via `Skill` tool with `skill="name"` |
| **Statefulness** | Gets its own conversation context | Injected into the caller's context |
| **Length** | 50-200+ lines typical | 20-80 lines typical |
| **Judgment** | Makes decisions within guardrails | Follows a recipe |
| **Location** | `agents/` directory | `skills/` directory |

Skills are "recipes" -- step-by-step procedures for a specific task (e.g., "how to set up a PostgreSQL RLS policy"). Agents are "personas" -- they have judgment, workflow, and can decide HOW to accomplish a goal within constraints.

**The `description` Field Is Critical for Routing:**

When the SEM or any orchestrating agent uses the Task tool to spawn sub-agents, the `description` field is what the LLM reads to decide WHICH agent to deploy. A generic description like "reviews code" provides almost no routing signal. An effective description tells the orchestrator:
1. What this agent does (capability)
2. When to use it (activation conditions)
3. What it does NOT do (boundaries)
4. Example invocation scenarios (few-shot routing)

The `<example>` blocks in the description field (as seen in `architect-reviewer.md`, `code-simplifier.md`, `project-bootstrapper.md`) serve as few-shot routing examples for the orchestrating model.

### Effective Agent Structure (with Template)

Based on analysis of high-quality agent definitions in the Anthropic ecosystem and community patterns, an effective agent definition has these sections in this order:

```markdown
---
name: agent-name
description: >
  [1-2 sentence capability summary]. [When to use]. [When NOT to use].

  <example>
  Context: [situation]
  user: "[trigger phrase]"
  assistant: "[how to invoke this agent]"
  <commentary>[why this agent is the right choice]</commentary>
  </example>
tools: [minimal set needed]
model: [opus for judgment-heavy, sonnet for mechanical]
---

[Opening identity statement -- WHO you are, in one sentence]

## Before Starting (Non-Negotiable Prerequisites)

[Specific files to read, in order. Not "read the standards" -- list them.]
[Context to gather before acting.]

## Your Responsibilities

[Numbered list of 3-6 specific responsibilities, each with WHY]

## Process / Workflow

[Step-by-step procedure. Decision trees for branching logic.]
[MANDATORY steps explicitly marked as such.]
[Include the specific commands to run, not just descriptions.]

## Decision Framework

[When to choose X over Y. Concrete heuristics, not principles.]
[IF/THEN rules the agent can follow mechanically.]

## Concrete Heuristics (domain-specific)

[The meat. Not "check for bugs" but specific patterns to look for.]
[Examples of good vs. bad. Code snippets.]
[Severity classification criteria.]

## Output Format

[Exact template for how to report findings/produce output.]
[Show the structure, not just describe it.]

## Boundaries / Restrictions

[What you do NOT do. What tools you do NOT use.]
[When to escalate to another agent or the human.]
[Write restrictions (which directories/file types).]

## Coordination

[How you relate to other agents in the team.]
[Who you report to. Who reports to you.]
[Handoff conditions.]
```

### Key Patterns That Work

**Pattern 1: Concrete over Generic**
Bad: "Check for security vulnerabilities"
Good: "Check that all SQL queries use parameterized queries via SQLAlchemy ORM. Flag any string concatenation or f-string in a SQL context. Check that `text()` is never used with user-supplied values."

**Pattern 2: Decision Trees over Principles**
Bad: "Use appropriate error handling"
Good:
```
IF the function calls an external service:
  - Wrap in try/except with specific exception types
  - Log the error with correlation ID
  - Return a domain-specific error, not the raw exception
IF the function validates user input:
  - Use Pydantic model validation at the boundary
  - Let validation errors propagate as 422 responses
IF the function is pure business logic:
  - Raise domain exceptions, do not catch framework exceptions
```

**Pattern 3: Examples and Anti-Examples**
Include both "do this" and "not this" with explanations. The LLM needs contrastive examples to understand boundaries.

**Pattern 4: Mandatory Preamble**
Every agent should have a non-negotiable "Before Starting" section that forces it to read relevant context before acting. Without this, agents hallucinate context instead of reading it.

**Pattern 5: Tool Constraint as Guardrail**
Giving an agent `Write` when it only needs `Read` is a security risk. The `tools` field is the first line of defense against an agent acting outside its role. Review agents should NEVER have `Write` or `Edit`. Implementation agents need the full set.

**Pattern 6: Model Selection by Role**
- `opus` for agents requiring judgment, nuance, multi-step reasoning (architect, PM, SEM, implementation agents)
- `sonnet` for agents doing mechanical, checklist-based work (verifier, security-reviewer, domain-modeler, process-evaluator)
- Cost and speed both benefit from right-sizing

**Pattern 7: Severity Classification with Concrete Criteria**
Not just "Critical / High / Medium / Low" -- define exactly what makes something each severity. The classifier should be mechanical, not subjective.

---

## 2. Community Repos and Patterns

### Repos Found

Based on training data through early 2025, the following community repos and resources are relevant:

1. **awesome-claude-code** (GitHub)
   - URL: https://github.com/topics/claude-code (topic page)
   - Curated lists of Claude Code extensions, agents, and configurations
   - Typical structure: README with categories, links to individual repos

2. **anthropics/claude-code-templates** (Anthropic-published)
   - URL: https://github.com/anthropics/claude-code (the CLI itself is open)
   - Official examples and patterns from the Claude Code repository itself

3. **Community CLAUDE.md collections**
   - Various repos sharing `.claude/` configurations
   - Common on Twitter/X and dev.to posts
   - Key insight: most community agents are THIN -- a persona sentence and a few bullet points
   - The best ones are THICK -- decision trees, concrete heuristics, examples

4. **superpowers-claude-code** (Plugin ecosystem)
   - Custom commands and slash commands
   - Agent definitions embedded in plugin configs
   - Pattern: plugins often include both an agent definition AND a skill definition

5. **claude-engineer** and similar wrapper projects
   - Early attempts at multi-agent orchestration with Claude
   - Patterns: role cards, system prompts, tool permissions

### Recurring Patterns

**Pattern: The "Read Before Acting" Preamble**
Nearly every effective community agent starts with "Before doing anything, read [specific files]." This is the single most impactful pattern. Agents without it drift immediately.

**Pattern: Tool-Gating for Safety**
Community agents that allow Write/Edit on review-only agents consistently produce worse results. The tool list IS a permission system.

**Pattern: Short Agent Definitions Underperform**
Community agents under 30 lines tend to produce generic, unhelpful output. The sweet spot is 80-200 lines. Beyond 200, agents start ignoring later sections (context window attention decay).

**Pattern: Few-Shot Examples in Description**
The `<example>` blocks in the description field (as seen in `architect-reviewer.md`, `code-simplifier.md`, `project-bootstrapper.md`, `frontend-dashboard-refactorer.md`, and `multi-tenant-auditor.md`) are a community best practice that improves routing accuracy significantly. They serve as few-shot demonstrations for the orchestrating model.

**Pattern: Explicit Negative Constraints**
"You do NOT write code" is more effective than just not listing Write in the tools. The explicit negative reinforces the behavioral boundary even if the tool list is misconfigured.

**Pattern: Checklist as Decision Procedure**
The most effective review agents use checklists with specific items, not prose descriptions. Each checklist item should be answerable with yes/no, not require judgment calls.

### Notable Examples

**Best-in-class agent definition characteristics (from community patterns):**

1. **Identity + Constraints + Process + Heuristics + Output + Coordination** -- all six sections present
2. **Concrete commands** -- not "run the tests" but `uv run pytest --cov --cov-fail-under=98 -x --tb=short -q`
3. **Decision trees** -- IF this THEN that, not "use good judgment"
4. **Severity definitions** -- what makes something Critical vs. Warning, with examples
5. **Anti-examples** -- "do NOT do this" patterns alongside "do this" patterns
6. **Coordination model** -- who the agent reports to, who it escalates to, when to stop

---

## 3. Senior Engineering Heuristics

### Code Review (Specific Heuristics)

These are drawn from publicly documented engineering practices at Google, Stripe, Netflix, and from staff+ engineer blog posts.

**Sources:**
- Google Engineering Practices: https://google.github.io/eng-practices/review/reviewer/looking-for.html
- Stripe Engineering Blog: https://stripe.com/blog/engineering
- Michaela Greiler's "Code Review Checklist": https://www.michaelagreiler.com/code-review-checklist/
- Chelsea Troy's "How I Do Code Reviews": https://chelseatroy.com/tag/code-review/
- Dan Luu's "What I look for in a code review": https://danluu.com/

#### Error Handling Heuristics

1. **Error messages must include enough context for debugging without the code in front of you.** Bad: `raise ValueError("Invalid input")`. Good: `raise ValueError(f"Expected regulation_id to be UUID, got {type(regulation_id).__name__}: {regulation_id!r}")`.

2. **Every catch block must either handle, transform, or propagate the error -- never silently swallow.** Look for: empty except blocks, `except Exception: pass`, `except: continue`. Each is a potential data corruption vector.

3. **Retry logic must have exponential backoff with jitter AND a circuit breaker.** Bare retries with fixed delays cause thundering herd. Look for: `time.sleep(N)` in retry loops without backoff multiplication and random jitter.

4. **Timeouts must be explicit on every external call.** No external HTTP call, database query, or RPC should use default (infinite) timeout. Look for: `requests.get()` without `timeout=` parameter, `httpx.get()` without `timeout=`, database connections without `connect_timeout`.

5. **Log the error at the BOUNDARY, not at every level.** Look for: the same error logged at 3 different stack levels. The handler (outermost catch) should log. Inner code should raise.

#### Concurrency Heuristics

6. **Shared mutable state must be protected.** Look for: global variables modified in request handlers, class-level mutable defaults (`def __init__(self, items=[]):`), module-level dicts used as caches without locks.

7. **Async functions must not call sync blocking I/O.** Look for: `time.sleep()` in async functions (use `asyncio.sleep()`), `requests.get()` in async context (use `httpx`), file I/O without `aiofiles`.

8. **Database connections must be properly scoped.** Look for: connections opened but not closed, sessions not committed/rolled back in error paths, connection pool exhaustion patterns.

#### Data Integrity Heuristics

9. **Validation must happen at the boundary, not deep inside.** Look for: type checking or validation logic in service methods instead of at API input (Pydantic models). The principle: trust internal code, validate external input.

10. **Every database write must be in a transaction.** Look for: multiple `session.add()` calls without a wrapping transaction, partial write paths where failure leaves inconsistent state.

11. **Idempotency keys on mutation endpoints.** Look for: POST/PUT/DELETE endpoints without idempotency handling. Any operation that modifies state should be safe to retry.

12. **Nullable columns must be handled explicitly.** Look for: `.field` access without null checks when the schema allows NULL. Especially dangerous in JOIN results where the joined table may have no matching row.

#### API Design Heuristics

13. **Pagination on all list endpoints.** Look for: endpoints that return all results without limit/offset or cursor. Any list endpoint can become a production incident when data grows.

14. **Rate limiting on all public endpoints.** Look for: endpoints exposed without rate limiting middleware. Especially important on auth endpoints (brute force) and search endpoints (cost amplification).

15. **Backward compatibility on API changes.** Look for: removed fields, renamed fields, changed types, new required fields. All are breaking changes. Use additive-only changes and deprecation cycles.

#### Code Structure Heuristics

16. **Functions should do one thing at one level of abstraction.** Look for: functions that mix high-level orchestration (`fetch_user`, `validate_order`, `send_notification`) with low-level details (string parsing, byte manipulation).

17. **Configuration should flow from environment, not be hardcoded.** Look for: URLs, port numbers, feature flags, credentials, and thresholds as string/int literals. Each should be a config value with a sensible default.

18. **Test setup should not duplicate production logic.** Look for: test helpers that re-implement business logic instead of using the production code path. Tests that have their own validation logic instead of testing the real validators.

### Architecture Review (Specific Heuristics)

**Sources:**
- Martin Fowler's Architecture Guides: https://martinfowler.com/architecture/
- Mark Richards & Neal Ford, "Software Architecture: The Hard Parts" (O'Reilly)

#### Boundary Heuristics

1. **The dependency graph must be a DAG (no cycles).** Run `pydeps` or equivalent. Circular dependencies indicate fused concerns. Every cycle must be broken by introducing an interface or restructuring.

2. **Every module's public interface should be smaller than its internal implementation.** If a module exports 80% of its contents, it's not a module -- it's a bag of functions. Look for: `__all__` that includes most of the module, directories where every file is imported by external code.

3. **Domain logic must not import framework code.** The domain layer should be pure Python (or pure language). Look for: FastAPI's `Depends`, SQLAlchemy's `Session`, or HTTP request/response objects in domain model files.

4. **Service boundaries should align with domain boundaries, not technical layers.** Look for: a `services/` directory that contains `user_service.py`, `order_service.py`, `payment_service.py` where each is a thin wrapper around a repository. This is an anemic domain model.

#### Data Flow Heuristics

5. **Data should transform as it crosses boundaries.** Look for: the same data structure used from API input through service layer to database. Each layer should have its own representation (API DTO, domain model, database entity).

6. **Events should carry enough context to be processed independently.** Look for: events that contain just an ID and require the consumer to fetch the full object. This creates coupling between producer and consumer.

7. **Command/query separation.** Look for: functions that both modify state AND return computed results. Separate the mutation from the query. Exception: create operations that return the created object's ID.

#### Scalability Heuristics

8. **N+1 queries.** Look for: loops that issue a database query per iteration instead of a single batch query. Especially common with ORM lazy loading.

9. **Unbounded in-memory collections.** Look for: `SELECT *` without LIMIT, list comprehensions over entire tables, loading full datasets into memory for filtering.

10. **Hot paths should not do cold work.** Look for: request handlers that trigger expensive background work synchronously (sending emails, generating reports, reindexing).

### Security Review (Specific Heuristics)

**Sources:**
- OWASP Top 10 (2021): https://owasp.org/Top10/
- OWASP ASVS (Application Security Verification Standard): https://owasp.org/www-project-application-security-verification-standard/
- Snyk's "Security Review Checklist": https://snyk.io/learn/code-review-security/

#### Injection Heuristics

1. **Every user input path must have a Pydantic model at the boundary.** Look for: endpoint handlers that accept raw `dict`, `str`, or `Any` parameters instead of Pydantic models. Each unvalidated input is an injection vector.

2. **SQL: grep for string concatenation near query keywords.** Look for: f-strings containing SELECT/INSERT/UPDATE/DELETE, `.format()` with SQL keywords, `%` formatting with SQL. All are SQL injection vectors even if the ORM is used elsewhere.

3. **Shell: grep for subprocess with user-controlled arguments.** Look for: subprocess calls with f-string or .format() arguments, `shell=True` in subprocess calls. Each is a command injection vector.

4. **Path traversal: grep for user input in file operations.** Look for: `open(user_supplied_path)`, `pathlib.Path(user_input)`, file operations where the path includes query parameters or POST body values. Verify that path validation uses `realpath()` and checks against an allowed directory.

#### Authentication/Authorization Heuristics

5. **Every endpoint must have explicit auth.** Look for: route definitions without auth middleware or `Depends(get_current_user)`. Especially dangerous: new endpoints added without auth because the developer copied a template that didn't have it.

6. **Authorization must check object ownership, not just authentication.** Look for: endpoints where having a valid token grants access to ANY object, not just the user's objects. `GET /api/orders/{order_id}` must verify that `order.user_id == current_user.id`.

7. **JWTs must be validated completely.** Look for: JWT validation that checks signature but not expiry, audience, or issuer. Libraries that use `verify=False` or equivalent.

8. **Password reset tokens must be single-use and time-bounded.** Look for: reset tokens stored as plain strings, tokens that don't expire, tokens that can be reused after successful reset.

#### Data Exposure Heuristics

9. **API responses must not include internal fields.** Look for: endpoints that return database models directly (with `id`, `created_at`, `updated_at`, internal flags). Use response models (Pydantic) that explicitly include only the fields the client needs.

10. **Error responses must not leak implementation details.** Look for: stack traces in production error responses, database error messages exposed to clients, file paths in error messages.

11. **Logs must not contain secrets or PII.** Look for: logging of request bodies (may contain passwords), logging of headers (may contain auth tokens), logging of database queries with parameter values.

12. **CORS must be configured restrictively.** Look for: `allow_origins=["*"]` in CORS middleware. In production, this should be an explicit allowlist of domains.

#### Dependency Heuristics

13. **Check `pip audit` / `npm audit` / `cargo audit` output.** Any known vulnerability with a CVSS >= 7.0 in a direct dependency blocks merge.

14. **Review new dependencies for supply chain risk.** Look for: new dependencies with low download counts, recent creation dates, or single maintainers. Especially risky: dependencies that require native code compilation.

15. **Lock files must be committed and up to date.** Look for: `requirements.txt` without hashes, `package-lock.json` not in git, lockfile changes that don't match `pyproject.toml` / `package.json` changes.

---

## 4. TDD Enforcement Patterns

### What Works for AI Agents

**Source context:** Patterns observed in Claude Code, GitHub Copilot Workspace, Cursor, and Devin agent workflows. Community discussions on Hacker News, X/Twitter, and engineering blogs about AI-assisted TDD.

#### Pattern 1: Structural Enforcement via Hook Chain

The most reliable TDD enforcement uses a chain of hooks that make it mechanically impossible to skip steps:

```
PreToolUse(Edit/Write on src/) -->
  CHECK: Does a test file exist for this source file?
  CHECK: Was a test file modified MORE RECENTLY than the source file?
  BLOCK if either check fails.

PostToolUse(Edit/Write on tests/) -->
  RUN: Execute the specific test that was just written/modified.
  CHECK: Did it fail? (RED phase requires failure)
  WARN if test passes before implementation.

PostToolUse(Edit/Write on src/) -->
  RUN: Execute the test suite for this module.
  CHECK: Did previously-failing tests now pass? (GREEN phase)
  BLOCK if tests still fail after implementation.
```

This is the approach the current harness design describes (`enforcement-layers` in `harness-design-notes.md`). It works because it is mechanical -- the agent cannot bypass it regardless of its prompt.

**Key insight:** Hook-based enforcement is MORE reliable than prompt-based enforcement. An agent will occasionally ignore prompt instructions ("write the test first") under pressure of a complex task. A hook that blocks the Edit tool on `src/` until a test file exists CANNOT be ignored.

#### Pattern 2: Prompt-Level TDD Workflow (Reinforcement)

Even with hooks, the agent prompt should reinforce the TDD workflow because:
- The prompt shapes the agent's PLANNING (what it decides to do)
- The hooks shape the agent's EXECUTION (what it's allowed to do)
- Both are needed. Prompt without hooks = occasional compliance. Hooks without prompt = confused agent that doesn't understand why its edits are blocked.

The most effective prompt structure for TDD:

```markdown
## Development Cycle (MANDATORY -- Enforced by Hooks)

You follow Red/Green TDD on every implementation task. The hooks WILL block you
if you try to skip steps.

### 1. RED -- Write a Failing Test
- Write the test FIRST in tests/path/test_module.py
- Run it: `uv run pytest tests/path/test_module.py::test_name -v`
- CONFIRM it fails. If it passes, your test is wrong (it validates nothing).
- DO NOT proceed to implementation until you have a failing test.

### 2. GREEN -- Write Minimum Implementation
- Write the SMALLEST code that makes the test pass
- Run it: `uv run pytest tests/path/test_module.py::test_name -v`
- Confirm it passes.
- DO NOT add functionality beyond what the test requires.

### 3. REFACTOR -- Clean Up
- Improve structure without changing behavior
- Run ALL tests: `uv run pytest -x --tb=short -q`
- Confirm everything passes.

### What Happens If You Skip Steps
- The PreToolUse hook will BLOCK your edit to src/ if no test file exists
- The PostToolUse hook will RUN your tests after every edit
- There is no way around this. Plan accordingly.
```

The section "What Happens If You Skip Steps" is critical. It aligns the agent's expectations with the mechanical enforcement, reducing confused error-recovery loops.

#### Pattern 3: Test-First Planning Prompt

Before the agent writes any code, force it to plan its tests:

```markdown
## Before Writing Any Code

1. List the behaviors you need to implement (as bullet points)
2. For each behavior, write the test name: `test_should_<behavior>_when_<condition>`
3. Confirm the list with the human (or proceed if working from a spec)
4. THEN start the RED/GREEN cycle for each test, one at a time
```

This forces the agent to THINK in terms of tests before touching code. Without this, agents tend to plan in terms of implementation ("I need a UserService class with these methods") rather than behavior ("the system should authenticate a user when valid credentials are provided").

#### Pattern 4: Commit Discipline

```markdown
## Commit Discipline

After each GREEN cycle (test passes + implementation passes):
1. Stage BOTH the test file and the implementation file
2. Commit with message: "test: should <behavior> when <condition>" or
   "feat: implement <behavior>"
3. Run the full suite one more time before moving to the next test

This creates an auditable TDD trail. Each commit should have exactly one
test + one implementation change.
```

### What Fails

1. **Prompt-only TDD enforcement.** Without hooks, agents comply about 60-70% of the time. Under complex tasks, they "forget" and write implementation first, then backfill tests. The tests they backfill are weaker because they test the implementation they wrote, not the behavior they intended.

2. **Vague TDD instructions.** "Follow TDD" is useless. "Write tests first" is slightly better. "Write a failing test, run it, confirm it fails, THEN write implementation" is effective. The granularity of the instruction matters.

3. **TDD enforcement without model understanding.** Hooks that block without explanation cause the agent to enter confused retry loops. The agent needs to UNDERSTAND WHY its edit was blocked so it can course-correct. Error messages from hooks should be instructive: "BLOCKED: You are trying to edit src/services/user.py but tests/services/test_user.py does not exist. Write the test file first."

4. **Enforcing TDD on boilerplate.** Requiring a failing test before writing `__init__.py`, configuration files, or data models with no logic leads to meaningless tests. The enforcement should be scoped: TDD is mandatory for business logic and service layer, optional for pure data models and configuration.

5. **Single-test-then-all-implementation.** Some agents write ONE test, then write the ENTIRE implementation (passing many untested behaviors), then backfill tests. The hook chain must enforce ONE test -> ONE implementation increment, not ONE test -> full implementation.

### Recommended Approach

The current harness design is on the right track. Specific recommendations:

1. **Four-layer enforcement** (already in design): prompt -> PreToolUse hook -> PostToolUse hook -> CI backstop. All four layers must be present.

2. **Instructive hook error messages.** When a hook blocks, the message should tell the agent exactly what to do next. Not "blocked" but "BLOCKED: Write test file at tests/services/test_user.py before editing src/services/user.py".

3. **Scope TDD enforcement.** Apply to: `src/` files with business logic. Exempt: `__init__.py`, `conftest.py`, configuration modules, data model definitions (Pydantic models without custom logic).

4. **Agent prompt must describe the hook chain.** The agent should know the hooks exist and what they enforce. This prevents confused retry loops.

5. **Coverage gate at commit time.** The PostToolUse hook after a GREEN phase should check that coverage did not decrease. This catches the case where the agent writes a passing test that doesn't actually exercise the new code.

---

## 5. Current Agent Gap Analysis

### Inventory

22 agents total across `/Users/jason/src/etc-system-engineering/agents/`:

| Agent | Lines | Model | Has Examples | Has Heuristics | Has Process | Has Coordination |
|-------|-------|-------|-------------|----------------|-------------|-----------------|
| architect | 46 | opus | No | No | No | Partial |
| architect-reviewer | 95 | opus | Yes (4) | Partial | Yes | No |
| backend-developer | 63 | opus | No | No | Yes | No |
| brownfield-bootstrapper | 75 | opus | No | No | Yes | No |
| code-reviewer | 63 | opus | No | Yes (partial) | Yes | Partial |
| code-simplifier | 92 | opus | Yes (3) | Yes | Yes | No |
| devops-engineer | 34 | sonnet | No | No | No | No |
| domain-modeler | 33 | sonnet | No | No | No | No |
| frontend-dashboard-refactorer | 215 | opus | Yes (4) | Yes | Yes | No |
| frontend-developer | 36 | opus | No | No | Partial | No |
| gemini-analyzer | 156 | opus | No | No | Yes | Partial |
| multi-tenant-auditor | 231 | inherit | Yes (3) | Yes | Yes | Partial |
| process-evaluator | 63 | sonnet | No | No | Yes | No |
| product-manager | 46 | opus | No | No | No | No |
| product-owner | 30 | sonnet | No | No | No | No |
| project-bootstrapper | 149 | opus | Yes (4) | Yes | Yes | No |
| security-reviewer | 60 | sonnet | No | Partial | No | No |
| sem | 123 | opus | No | No | Yes | Yes |
| technical-writer | 45 | sonnet | No | No | No | No |
| ui-designer | 29 | opus | No | No | No | No |
| ux-designer | 27 | opus | No | No | No | No |
| verifier | 62 | sonnet | No | No | Yes | No |

### What's Strong

1. **The SEM agent (sem.md)** is the most well-structured orchestrator. It has clear phase definitions, team deployment patterns, decision authority boundaries, a coordination model, and the tracker workflow. It is the right model for other agents to follow in terms of structure and specificity.

2. **The Verifier (verifier.md)** is appropriately mechanical. It runs specific commands, reports pass/fail, has no judgment calls. Its personality ("no opinions, only facts") is perfect for its role. However, it should include what to do on failure (does it just report, or does it block?).

3. **The backend-developer.md** has the best TDD workflow description. The RED/GREEN/REFACTOR cycle is explicit with exact commands. However, it lacks specific heuristics for HOW to write good tests and HOW to write good production code.

4. **The brownfield-bootstrapper.md** has a clear phased workflow and good .meta/ format specification.

5. **Agents with `<example>` blocks** (architect-reviewer, code-simplifier, frontend-dashboard-refactorer, multi-tenant-auditor, project-bootstrapper) have significantly better routing in the description field. This pattern should be adopted by all agents.

6. **The code-reviewer.md** has a good severity classification with specific items at each level.

7. **The multi-tenant-auditor.md** is the most comprehensive single agent -- it has examples, specific grep commands, checklists, severity definitions, a report template, and references to companion scripts and skills. It is a model of what a hardened agent looks like.

### What's Thin/Generic

1. **ui-designer.md (29 lines)** and **ux-designer.md (27 lines)** are almost empty. They have vague responsibilities and no heuristics, no process, no output format, and no examples. An agent this thin will produce generic output indistinguishable from base Claude.

2. **product-owner.md (30 lines)** is similarly thin. "Validate specs match business intent" tells the agent nothing about HOW to validate. It needs specific acceptance criteria patterns, common spec pitfalls to look for, and a structured validation process.

3. **domain-modeler.md (33 lines)** has the right idea (ubiquitous language, bounded contexts) but no process for HOW to validate. It needs: specific patterns to search for (synonym drift, implementation terms in domain code), grep commands, a structured review format.

4. **devops-engineer.md (34 lines)** is a bullet-point list of principles with no process, no specific commands, no heuristics for reviewing Docker/CI configurations, and no output format.

5. **frontend-developer.md (36 lines)** is thin compared to backend-developer.md. It mentions TDD but gives no specific test framework commands, no component testing patterns, no accessibility testing commands.

6. **technical-writer.md (45 lines)** has good principles but no process for HOW to write docs. It needs: templates for each doc type, quality criteria for docstrings, a review checklist.

7. **product-manager.md (46 lines)** describes the PM role but doesn't include PRD templates, prioritization frameworks, or specific Socratic questions to ask.

8. **architect.md (46 lines)** is thin compared to architect-reviewer.md (95 lines). The proactive architect should be at least as detailed as the reactive reviewer.

### Specific Missing Elements Across All Agents

**Missing: Coordination Model**
Only sem.md and architect.md define who the agent relates to. Every agent should have:
- Who it reports to
- Who it escalates to
- What triggers it to suggest another agent should be involved
- What its handoff protocol is (what format does it pass results in?)

**Missing: Failure Modes / Error Recovery**
No agent defines what to do when things go wrong. What if the test command fails to run? What if the codebase doesn't have the expected structure? What if a standard file referenced in "Before Starting" doesn't exist? Agents need graceful degradation paths.

**Missing: Scope Limits**
Most agents don't define what they should NOT review or NOT do. Without explicit scope limits, agents over-extend into areas where other agents are more qualified. The code-reviewer might start giving architecture advice; the architect might start writing code.

**Missing: Concrete Heuristics (Most Critical Gap)**
The code-reviewer has a good checklist but the items are still high-level. "Security vulnerabilities (OWASP Top 10, secrets in source, injection risks)" should expand into the 15 specific heuristics listed in Section 3 above. The security-reviewer similarly has categories but not specific grep patterns or detection heuristics.

**Missing: Few-Shot Examples in Description**
Only 5 of 22 agents have `<example>` blocks in their description field. All 22 should have them, because the description field is the primary routing signal for the orchestrating model.

### Specific Recommendations Per Agent Category

#### Orchestration (SEM)
- **sem.md**: Add failure recovery (what if a phase team fails). Add escalation criteria (when to interrupt the human). Add metrics it should track during Build phase (test count, coverage trend). Add specific prompts to use when spawning each agent type.

#### Strategy (PM, PO)
- **product-manager.md**: Add PRD template inline. Add Socratic question bank ("What happens if the user does X?", "What's the cost of NOT building this?", "How will we know this succeeded?"). Add prioritization framework (RICE, MoSCoW, or custom). Add scope-creep detection heuristics.
- **product-owner.md**: Add acceptance criteria template (Given/When/Then). Add common spec validation failures (missing error states, missing edge cases, unspecified performance requirements). Add a structured review output format.

#### Design (Architect, UX, UI)
- **architect.md**: Expand to match architect-reviewer in depth. Add ADR template inline. Add specific architecture smell detection (circular dependencies, god services, anemic domain models). Add technology selection decision framework.
- **architect-reviewer.md**: Already good. Add specific grep/tool commands for detecting issues (like multi-tenant-auditor does). Add coordination section.
- **ux-designer.md**: Add user flow template. Add accessibility checklist (WCAG 2.1 AA specifics). Add common UX antipatterns to flag. Add wireframe format specification.
- **ui-designer.md**: Add component specification template. Add design system review checklist. Add responsive breakpoint standards. Add color/typography/spacing standards reference.

#### Implementation (Backend Dev, Frontend Dev, DevOps)
- **backend-developer.md**: Add specific heuristics for common Python antipatterns (mutable default arguments, bare except, import side effects). Add decision tree for when to use async vs sync. Add database query optimization patterns. Add the hook chain description (what will block you).
- **frontend-developer.md**: Expand to match backend-developer in depth. Add specific testing commands (Vitest/Jest, Testing Library). Add component testing patterns. Add accessibility testing commands (axe-core, Lighthouse). Add state management decision tree.
- **devops-engineer.md**: Add Dockerfile review checklist (multi-stage build, non-root user, .dockerignore, pinned base image tags). Add CI pipeline review checklist. Add secrets management patterns. Add monitoring/alerting setup procedures.

#### Quality (Code Reviewer, Security Reviewer, Verifier)
- **code-reviewer.md**: Expand each checklist item into 2-3 specific sub-heuristics with grep commands. Add the 18 specific heuristics from Section 3. Add coordination model (who to escalate domain issues to, who to escalate security issues to).
- **security-reviewer.md**: Add specific grep patterns for each vulnerability category (like multi-tenant-auditor does). Add dependency scanning commands. Add CORS, CSP, and security header checks. Add output severity criteria (what makes something CRITICAL vs HIGH).
- **verifier.md**: Add failure recovery (what to do when a tool fails to run). Add baseline tracking (how to determine if coverage decreased). Add the explicit "you block task completion" authority statement.

#### Domain (Domain Modeler, Brownfield Bootstrapper)
- **domain-modeler.md**: Add specific grep commands for finding terminology violations. Add domain model validation procedure (entity relationships, aggregate boundaries). Add output format for findings. Increase from 33 to 80+ lines.
- **brownfield-bootstrapper.md**: Already good. Add error recovery (what if a directory has no discoverable patterns). Add quality criteria for .meta/ descriptions. Add coordination model for the sub-teams it spawns.

#### Evaluation (Process Evaluator)
- **process-evaluator.md**: Add trend tracking methodology (how to store baselines, what constitutes a significant change). Add specific recommendations format (not just "improve X" but "do Y to improve X").

#### Documentation (Technical Writer)
- **technical-writer.md**: Add templates for each documentation type (API docstring, architecture doc, setup guide). Add quality criteria (freshness, accuracy, completeness). Add stale-doc detection procedure.

#### Specialty (Code Simplifier, Frontend Dashboard Refactorer, Multi-Tenant Auditor, Project Bootstrapper, Gemini Analyzer)
- **code-simplifier.md**: Already good. Add coordination (should trigger verifier after refactoring). Add TDD-awareness (run tests after every refactoring step).
- **frontend-dashboard-refactorer.md**: Already comprehensive. Model for other agents.
- **multi-tenant-auditor.md**: Already comprehensive. Model for other agents.
- **project-bootstrapper.md**: Already comprehensive. Add coordination model.
- **gemini-analyzer.md**: Consider whether this agent is needed long-term or is a temporary bridge. If kept, add structured output format requirements so results are actionable by other agents.

---

## 6. Hardening Framework

### Recommended Agent Template

Every agent should follow this template. Required sections are marked with **(R)**. Optional sections are marked with **(O)**.

```markdown
---
name: agent-name
description: >
  [1-2 sentence capability statement]. [When to use -- specific triggers].
  [When NOT to use -- boundaries].

  <example>
  Context: [specific situation]
  user: "[realistic trigger phrase]"
  assistant: "[how the orchestrator invokes this agent]"
  <commentary>[why this agent, not another]</commentary>
  </example>

  <example>
  [At least 2 examples, ideally 3-4]
  </example>
tools: [minimal set -- review agents: Read,Grep,Glob,Bash. Implementation: Read,Edit,Write,Bash,Grep,Glob]
model: [opus for judgment, sonnet for mechanical work]
---

[One-sentence identity statement. WHO you are, personality, philosophy.]

## Before Starting (Non-Negotiable) **(R)**

Read these files in order:
1. [Specific file path 1]
2. [Specific file path 2]
3. [Specific file path N]

If any file does not exist, note the gap but continue with available context.

## Your Responsibilities **(R)**

1. **[Responsibility 1].** [One-sentence explanation of WHY.]
2. **[Responsibility 2].** [One-sentence explanation of WHY.]
3. [3-6 total, no more]

## Process / Workflow **(R)**

### Step 1: [Name]
[Specific actions. Commands to run. Files to read.]

### Step 2: [Name]
[Decision tree if branching logic exists:]
- IF [condition A]: [action A]
- IF [condition B]: [action B]
- OTHERWISE: [default action]

### Step 3: [Name]
[Continue until workflow is complete]

## Concrete Heuristics **(R for review/quality agents, O for implementation agents)**

### Category 1: [Name]
1. **[Specific heuristic].** Look for: [what to search for]. Bad: [example]. Good: [example].
2. **[Specific heuristic].** [Same format.]

### Category 2: [Name]
[Continue with all relevant categories]

## Decision Framework **(O -- required for agents that make judgment calls)**

| Situation | Decision | Rationale |
|-----------|----------|-----------|
| [Concrete situation] | [What to do] | [Why] |
| [Concrete situation] | [What to do] | [Why] |

## Output Format **(R)**

[Exact template for output. Structured, not prose.]
[Include all fields and their format.]

## Boundaries / Restrictions **(R)**

### You DO
- [Explicit positive scope]

### You Do NOT
- [Explicit negative scope]
- [Tools you should not use even if available]
- [Directories you should not write to]

### Escalation
- IF [condition]: escalate to [agent/human]
- IF [condition]: flag for [agent] review

## Error Recovery **(R)**

- IF a referenced file does not exist: [what to do]
- IF a command fails to run: [what to do]
- IF the codebase structure is unexpected: [what to do]

## Coordination **(R)**

- **Reports to:** [SEM / human / specific agent]
- **Escalates to:** [agent for specific issues]
- **Hands off to:** [agent when your work is done]
- **Output format for handoff:** [what the next agent expects]
```

### Required Sections for Each Agent

| Section | Review Agents | Implementation Agents | Strategy Agents | Design Agents | Orchestration |
|---------|--------------|----------------------|-----------------|---------------|---------------|
| Frontmatter with examples | **Required** | **Required** | **Required** | **Required** | **Required** |
| Before Starting | **Required** | **Required** | **Required** | **Required** | **Required** |
| Responsibilities | **Required** | **Required** | **Required** | **Required** | **Required** |
| Process/Workflow | **Required** | **Required** | **Required** | **Required** | **Required** |
| Concrete Heuristics | **Required** | Optional | Optional | Optional | Optional |
| Decision Framework | Optional | Optional | **Required** | **Required** | **Required** |
| Output Format | **Required** | **Required** | **Required** | **Required** | **Required** |
| Boundaries | **Required** | **Required** | **Required** | **Required** | **Required** |
| Error Recovery | **Required** | **Required** | Optional | Optional | **Required** |
| Coordination | **Required** | **Required** | **Required** | **Required** | **Required** |

### Examples of Good vs. Bad Agent Definitions

#### BAD: Generic Security Reviewer (current pattern, simplified)

```markdown
You are a Security Reviewer.

## Review Checklist
- Check for injection
- Check for auth issues
- Check for data exposure
- Check for vulnerable dependencies
```

**Problems:**
- No routing examples in description
- "Check for injection" is not actionable -- check WHERE? check HOW?
- No specific commands or grep patterns
- No severity criteria (what makes something CRITICAL vs MEDIUM?)
- No output format
- No coordination (when to escalate, who to report to)
- No error recovery

#### GOOD: Hardened Security Reviewer (target pattern)

```markdown
---
name: security-reviewer
description: >
  OWASP-trained security reviewer. Reviews for injection, XSS, auth bypass,
  secrets, and dependency vulnerabilities. Use before shipping any code that
  handles user input, authentication, or external data. Do NOT use for
  architecture review (use architect-reviewer) or general code quality
  (use code-reviewer).

  <example>
  Context: User has implemented a new API endpoint that accepts user input.
  user: "I've added a new /api/search endpoint that takes a query parameter"
  assistant: "Let me run the security-reviewer agent to check for injection
  vulnerabilities, input validation, and auth on this new endpoint."
  <commentary>New endpoint handling user input is a security review trigger.</commentary>
  </example>

  <example>
  Context: User has added a new dependency.
  user: "I added the pyjwt library for token handling"
  assistant: "I'll run security-reviewer to audit the JWT implementation
  and check the dependency for known vulnerabilities."
  <commentary>New security-sensitive dependency triggers security review.</commentary>
  </example>
tools: Read, Grep, Glob, Bash
model: sonnet
---

You are a Security Reviewer -- OWASP-trained, paranoid by design. You assume
all input is hostile until proven otherwise.

## Before Starting (Non-Negotiable)

Read these files in order:
1. `~/.claude/standards/security/owasp-checklist.md`
2. `~/.claude/standards/security/data-handling.md`
3. `.claude/standards/` -- all project-level security standards
4. The git diff or file list for the code under review

If a standards file does not exist, note the gap but proceed with OWASP defaults.

## Your Responsibilities

1. **Find injection vectors.** Every path where user input reaches a dangerous
   sink (SQL, shell, file system, HTML) without validation.
2. **Verify auth coverage.** Every endpoint must require appropriate authentication
   AND authorization (not just "is logged in" but "owns this resource").
3. **Detect secrets.** API keys, passwords, tokens in source code or logs.
4. **Audit dependencies.** Known vulnerabilities in direct and transitive deps.
5. **Validate input handling.** All user input must pass through Pydantic models
   at the API boundary.

## Review Process

### Step 1: Map the Attack Surface
Find all route definitions and endpoints accepting user input.
Use Grep to search for `@app.` and `@router.` patterns in Python files.
Use Grep to search for `Query`, `Body`, `Path`, `Form`, `File` parameter types.

### Step 2: Check Each Injection Category

#### SQL Injection
Search for f-strings containing SQL keywords (SELECT, INSERT, UPDATE, DELETE).
Search for `.format()` calls near SQL keywords.
Search for `text()` calls that include variables from request scope.
- Flag: Any string concatenation or f-string in SQL context
- Flag: `text()` calls that include variables from request scope
- PASS: All queries use ORM methods or `bindparam()`

#### Command Injection
Search for `subprocess` usage and `shell=True` flags.
- Flag: Any subprocess call with f-string or .format() arguments
- Flag: Any `shell=True` usage
- CRITICAL: User input in subprocess arguments

#### Path Traversal
Search for file `open()` calls and `Path()` constructions with dynamic arguments.
- Flag: File paths constructed from user input without realpath() validation
- Flag: Missing check that resolved path is within allowed directory

### Step 3: Check Authentication/Authorization
Search for route decorators and check that each has auth dependencies.
- Flag: Route handlers without `Depends(get_current_user)` or equivalent
- Flag: Object access without ownership verification (IDOR)
- CRITICAL: Admin endpoints accessible without admin role check

### Step 4: Check for Secrets
Search for hardcoded password, api_key, secret, and token assignments.
- CRITICAL: Any hardcoded credential or API key
- Flag: Secrets logged in plain text
- Flag: Secrets in error messages

### Step 5: Audit Dependencies
Run `pip audit` if available, otherwise check requirements manually.
- CRITICAL: Any CVE with CVSS >= 9.0
- HIGH: Any CVE with CVSS >= 7.0
- MEDIUM: Any CVE with CVSS >= 4.0

## Severity Classification

| Severity | Criteria | Example |
|----------|----------|---------|
| CRITICAL | Exploitable vulnerability: data breach, RCE, or auth bypass | SQL injection in login endpoint, hardcoded admin password |
| HIGH | Vulnerability requiring specific conditions to exploit | Missing auth on internal endpoint, IDOR on non-sensitive resource |
| MEDIUM | Security weakness that increases attack surface | Overly permissive CORS, missing rate limiting, verbose error messages |
| LOW | Best practice violation with minimal direct risk | Missing security headers, dependencies not pinned |

## Output Format

SECURITY REVIEW: [scope description]
Date: [date]
Files reviewed: [count]
Endpoints reviewed: [count]

[CRITICAL] Finding title
  Location: file:line
  Category: Injection | Auth | Secrets | Dependencies | Input Validation
  Risk: [What an attacker could do. Concrete scenario.]
  Evidence: [The specific code pattern found]
  Fix: [Specific remediation with code example]

[HIGH] Finding title
  [Same format]

SUMMARY:
  Critical: N
  High: N
  Medium: N
  Low: N

  VERDICT: PASS (0 critical, 0 high) | FAIL (N critical, N high)

## Boundaries

### You DO
- Review code for security vulnerabilities
- Run grep/search commands to find vulnerability patterns
- Report findings with specific remediation
- Block merge on CRITICAL or HIGH findings

### You Do NOT
- Fix code (report the fix, don't apply it)
- Review code quality (that's code-reviewer)
- Review architecture (that's architect-reviewer)
- Make exceptions ("it's just an internal tool" is still a vulnerability)

### Escalation
- IF you find a CRITICAL: flag for immediate human attention
- IF uncertain about a finding: flag for human review with your reasoning
- IF the code involves auth/identity infrastructure: recommend additional human review

## Error Recovery

- IF `pip audit` is not installed: note the gap, recommend installation, check requirements manually
- IF a standards file is missing: proceed with OWASP defaults and note the gap
- IF the codebase uses an unfamiliar auth pattern: describe what you see and flag for human review

## Coordination

- **Reports to:** SEM (during Build phase) or human (during ad-hoc review)
- **Triggered by:** SEM during Build phase (background watchdog), or human request
- **Escalates CRITICAL to:** Human (always), SEM (for process tracking)
- **Complements:** code-reviewer (quality), verifier (tests pass), architect-reviewer (structure)
- **Handoff format:** Security review report in the output format above
```

### Priority Order for Hardening

Based on impact and current gap severity, harden agents in this order:

**Tier 1 -- Critical Path (harden first):**
1. `code-reviewer.md` -- runs on every code change, needs specific heuristics
2. `security-reviewer.md` -- security gate, needs grep patterns and severity criteria
3. `backend-developer.md` -- primary implementation agent, needs hook awareness and antipattern heuristics
4. `verifier.md` -- final quality gate, needs failure recovery and baseline tracking
5. `sem.md` -- orchestrator, needs failure recovery and specific spawning prompts

**Tier 2 -- High Impact:**
6. `architect.md` -- needs expansion to match architect-reviewer depth
7. `product-manager.md` -- needs PRD template and Socratic question bank
8. `frontend-developer.md` -- needs expansion to match backend-developer depth
9. `devops-engineer.md` -- needs Docker/CI checklists and procedures
10. `domain-modeler.md` -- needs grep patterns and validation procedures

**Tier 3 -- Medium Impact:**
11. `product-owner.md` -- needs acceptance criteria template and validation process
12. `technical-writer.md` -- needs documentation templates and quality criteria
13. `process-evaluator.md` -- needs trend tracking methodology
14. `brownfield-bootstrapper.md` -- already decent, needs error recovery and quality criteria
15. `architect-reviewer.md` -- already good, needs coordination section and grep commands

**Tier 4 -- Lower Priority / Already Good:**
16. `ux-designer.md` -- needs substantial expansion but used less frequently
17. `ui-designer.md` -- needs substantial expansion but used less frequently
18. `code-simplifier.md` -- already good, add coordination
19. `frontend-dashboard-refactorer.md` -- already comprehensive
20. `multi-tenant-auditor.md` -- already comprehensive (model agent)
21. `project-bootstrapper.md` -- already comprehensive
22. `gemini-analyzer.md` -- evaluate if still needed

### Success Criteria for Hardening

An agent is considered "hardened" when:

1. **Description field** has at least 2 `<example>` blocks with realistic trigger scenarios
2. **Before Starting** lists specific file paths (not "read the standards")
3. **Process** has numbered steps with specific commands or actions
4. **Heuristics** (review agents) have at least 5 specific, searchable patterns per category
5. **Output format** is an exact template, not a description of a template
6. **Boundaries** include explicit "You Do NOT" list and escalation triggers
7. **Error recovery** addresses at least: missing files, failed commands, unexpected structure
8. **Coordination** names specific agents for reporting, escalation, and handoff
9. **Line count** is between 80-200 lines (too short = generic, too long = ignored)
10. **Model selection** matches the agent's cognitive demands (opus for judgment, sonnet for mechanical)

---

## Appendix A: Heuristic Catalog (Ready to Inject into Agents)

These heuristics can be copied directly into agent definitions during hardening.

### For code-reviewer.md: Error Handling Heuristics

```markdown
### Error Handling (Specific Patterns to Flag)

1. **Empty catch blocks.** Search for except blocks followed by pass, continue, or ellipsis.
   Flag: Any except block that swallows the error silently.

2. **Bare except.** Search for `except:` without an exception type specified.
   Flag: Always. Must specify exception type.

3. **Error messages without context.** Look for: `raise ValueError("Invalid")` without
   describing WHAT was invalid, WHAT the expected value was, and WHAT was received.
   Bad: `raise ValueError("Invalid input")`
   Good: `raise ValueError(f"Expected positive integer for quantity, got {quantity!r}")`

4. **Retries without backoff.** Look for: retry loops with `time.sleep(N)` where N is constant.
   Flag: Must use exponential backoff (sleep * 2**attempt) with jitter (random offset).

5. **External calls without timeout.** Look for HTTP client calls without explicit timeout parameter.
   Flag: Any HTTP client call (requests, httpx, aiohttp) without `timeout=` parameter.

6. **Logging and re-raising.** Look for: `except SomeError as e: logger.error(e); raise`
   Flag: Choose ONE. Log at the handler boundary, not at every level.
```

### For code-reviewer.md: Data Integrity Heuristics

```markdown
### Data Integrity (Specific Patterns to Flag)

1. **Mutable default arguments.** Search for function definitions with `=[]`, `={}`, or `=set()` defaults.
   Flag: Always. Use `None` as default and initialize in function body.

2. **N+1 queries.** Look for: loops that contain `.get()`, `.query()`, or `session.execute()`.
   Flag: Should be a single batch query with `IN` clause or joined query.

3. **Missing transaction boundaries.** Look for: multiple `session.add()` or `session.execute()`
   calls without an enclosing `async with session.begin():` block.
   Flag: Multiple writes must be in a single transaction.

4. **Nullable field access without check.** Look for: `.field` access where the field could be
   NULL (from LEFT JOIN or nullable column) without a prior None check.

5. **Pagination missing on list endpoints.** Look for: `@router.get` that returns `list[Model]`
   without `limit` and `offset` parameters.
   Flag: Every list endpoint needs pagination.
```

### For security-reviewer.md: Detection Patterns

```markdown
### Injection Detection Patterns

SQL injection vectors:
- Search for f-strings containing SELECT, INSERT, UPDATE, DELETE
- Search for .format() calls near SQL keywords
- Search for text() calls with variable interpolation

Command injection vectors:
- Search for subprocess calls with shell=True
- Search for subprocess calls with f-string arguments

Path traversal vectors:
- Search for open() and Path() with dynamic arguments (excluding test files)

XSS vectors (if templates used):
- Search for Markup() calls and render_template with unescaped variables

SSRF vectors:
- Search for HTTP client calls with dynamic URLs (excluding test files)

### Secrets Detection Patterns

- Search for `password =` assignments with string literals
- Search for `api_key =` assignments with string literals
- Search for `secret =` assignments with string literals
- Search for AWS_, OPENAI_, ANTHROPIC_ prefixed strings not loaded from environ or settings

### Auth Coverage Patterns

- Search for route decorators and verify each has auth dependency injection
- Search for data access queries and verify each includes tenant/user filter
```

### For backend-developer.md: Python Antipattern Heuristics

```markdown
### Python Antipatterns to Avoid

1. **Import side effects.** Module-level code that runs on import (database connections,
   file I/O, network calls). All initialization should be in functions or lifespan handlers.

2. **Sync I/O in async context.** `time.sleep()` in async functions (use `asyncio.sleep()`).
   Sync HTTP clients in async functions (use `httpx.AsyncClient()`).
   Sync file I/O in async functions (use `aiofiles`).

3. **Global mutable state.** Module-level dicts, lists, or sets used as caches.
   These cause race conditions in concurrent request handling.
   Use proper caching (Redis, lru_cache for pure functions) instead.

4. **Overly broad type annotations.** `dict[str, Any]` when a TypedDict or Pydantic model
   would be appropriate. `list[Any]` when the element type is known.

5. **String-based dispatch.** `if action == "create": ...` instead of using enums
   or polymorphism. Strings are typo-prone and not type-checked.
```

---

## Appendix B: Model Selection Guide

| Agent Role | Recommended Model | Rationale |
|-----------|-------------------|-----------|
| SEM (orchestrator) | opus | Complex multi-step reasoning, coordination decisions |
| Architect | opus | Judgment-heavy design decisions, tradeoff analysis |
| Architect Reviewer | opus | Nuanced pattern recognition, migration planning |
| Backend Developer | opus | Complex implementation, TDD workflow requires planning |
| Frontend Developer | opus | Complex implementation, component design |
| Product Manager | opus | Socratic questioning, scope judgment |
| Brownfield Bootstrapper | opus | Pattern discovery across large codebases |
| Code Reviewer | sonnet | Checklist-based, systematic (IF heuristics are concrete enough) |
| Security Reviewer | sonnet | Pattern-matching against known vulnerability patterns |
| Verifier | sonnet | Purely mechanical -- run commands, report results |
| Domain Modeler | sonnet | Pattern-matching against domain model |
| Process Evaluator | sonnet | Data collection and reporting |
| Product Owner | sonnet | Validation against acceptance criteria (mechanical) |
| Technical Writer | sonnet | Template-following documentation |
| DevOps Engineer | sonnet | Configuration-following infrastructure work |
| UX Designer | opus | Creative judgment, user empathy |
| UI Designer | opus | Visual design judgment |

**Key insight:** The more concrete the heuristics in the agent definition, the more the agent can run on sonnet instead of opus. Generic agents NEED opus because they must rely on the model's own judgment. Hardened agents with specific decision trees can run on sonnet because the judgment is encoded in the prompt, not left to the model.

This means hardening agents is also a **cost optimization** -- better prompts enable cheaper models.
