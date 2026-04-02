# PRD: etc Harness v1.1 — Learning Loop, Phase Gating, Adversarial Review, and /spec Command

## Summary

Evolve the etc harness with four capabilities inspired by Correctless and
field experience: (1) an antipatterns learning loop that makes the system
smarter over time, (2) phase-aware file gating that prevents edits
inappropriate for the current SDLC phase, (3) adversarial review that ensures
no agent grades its own work, and (4) a `/spec` command that generates
implementation-ready PRDs through Socratic questioning, research, and
iterative refinement.

## Motivation

The v1.0 harness enforces discipline during implementation (TDD, invariants,
required reading, CI). But it has three gaps:

1. **It doesn't learn from mistakes.** When a bug escapes the harness, there's
   no mechanism to prevent the same class of bug next time. Each session starts
   from zero.

2. **It doesn't enforce phase discipline.** During the Spec phase, nothing stops
   the agent from editing `src/` files. During Build, nothing stops it from
   rewriting the PRD. The SDLC phases exist in the tracker but aren't enforced
   by hooks.

3. **Agents can grade their own work.** The orchestrator that decomposes tasks
   also verifies them. The implementer's subagent output is reviewed by a
   prompt hook, but not by a fresh agent with adversarial intent.

4. **There's no structured path from idea to spec.** The `/implement` command
   requires a PRD, but there's no tooling to help create that PRD. Users either
   write it by hand or give vague instructions that fail the Definition of Ready
   gate.

## Scope

### In Scope

- **Feature 1:** Antipatterns learning loop
- **Feature 2:** Phase-aware file gating hook
- **Feature 3:** Adversarial review on subagent output
- **Feature 4:** `/spec` Socratic specification command

### Out of Scope

- Postgres persistence (future)
- Execution graph / DAG scheduling (future)
- Metrics / ROI tracking (future — lower priority)
- Full Correctless feature parity (their formal modeling, mutation testing,
  STRIDE analysis — these are valuable but too much for v1.1)

---

## Feature 1: Antipatterns Learning Loop

### Problem

When a bug escapes the harness — the tests passed, the hooks allowed it, but
the code was still wrong — there's no mechanism to prevent the same class of
bug in the future. The harness is stateless across sessions.

### Solution

A persistent antipatterns file (`.etc_sdlc/antipatterns.md`) that accumulates
lessons from escaped bugs. Every subagent reads this file at startup. Every
postmortem appends to it.

### Specification

#### Antipatterns File Format

```markdown
# Antipatterns — Lessons from Escaped Bugs

These patterns have caused bugs that escaped our harness. Every spec and
implementation must account for them.

## AP-001: Async exception swallowing in FastAPI middleware
- **Date discovered:** 2026-04-01
- **Root cause:** try/except in middleware caught all exceptions including
  validation errors, returning 500 instead of 422
- **Class of bug:** Error handling that's too broad
- **Prevention rule:** Never catch bare Exception in middleware. Catch specific
  exception types. Let validation errors propagate.
- **Spec impact:** Every error handling spec must enumerate which exceptions
  are caught and which propagate.

## AP-002: ...
```

#### Integration Points

1. **`inject-standards.sh`** (SubagentStart hook) — already injects standards
   and active task. Add: if `.etc_sdlc/antipatterns.md` exists, include it in
   the subagent's context under a "## Known Antipatterns" section.

2. **New `/postmortem` skill** — Triggered when a bug is found post-delivery.
   The skill:
   - Asks: "What was the bug? What should have caught it?"
   - Traces the bug to the phase where it was introduced
   - Identifies which gate should have caught it and why it didn't
   - Generates an AP-NNN entry with prevention rule
   - Appends to `.etc_sdlc/antipatterns.md`
   - Optionally: suggests a new invariant or hook to prevent recurrence

3. **`/spec` command integration** — When generating a new spec, the `/spec`
   command reads antipatterns and incorporates relevant prevention rules into
   the acceptance criteria.

#### Acceptance Criteria

1. `.etc_sdlc/antipatterns.md` is created on first `/postmortem` invocation
2. `inject-standards.sh` includes antipatterns content when the file exists
3. `inject-standards.sh` does not fail when the file does not exist
4. `/postmortem` appends a well-structured AP-NNN entry with all required fields
5. Antipatterns are numbered sequentially (AP-001, AP-002, ...)
6. Each antipattern has: date, root cause, class of bug, prevention rule, spec impact
7. Test: `inject-standards.sh` output contains antipattern content when file exists

---

## Feature 2: Phase-Aware File Gating

### Problem

The SDLC phases (Spec, Design, Build, etc.) exist in `.sdlc/state.json` but
aren't enforced by hooks. During the Spec phase, nothing prevents the agent from
editing source code. During Build, nothing prevents rewriting the PRD.

### Solution

A new `PreToolUse` command hook that reads the current SDLC phase from
`.sdlc/state.json` and blocks file edits that are inappropriate for that phase.

### Specification

#### Phase-to-File Rules

| Phase | Allowed Edits | Blocked Edits |
|-------|--------------|---------------|
| bootstrap | `.meta/`, docs | src/, tests/ |
| spec | `spec/`, docs | src/, tests/ |
| design | `spec/`, docs, `INVARIANTS.md` | src/, tests/ |
| decompose | `.etc_sdlc/tasks/` | src/, tests/, spec/ |
| build | src/, tests/, `INVARIANTS.md` | spec/ (read-only during build) |
| verify | tests/ (fixes only) | spec/, src/ (no new features) |
| ship | docs/, README, config | src/, tests/, spec/ |
| evaluate | docs/ | src/, tests/, spec/ |

#### Hook Script: `check-phase-gate.sh`

- **Event:** PreToolUse
- **Matcher:** Edit|Write
- **Input:** `tool_input.file_path`, `cwd`
- **Logic:**
  1. Read `.sdlc/state.json` → extract `current_phase`
  2. If no state file exists, allow (harness not initialized)
  3. Match the file path against the phase rules
  4. If blocked: exit 2 with message "Phase '{phase}' does not allow edits to '{path}'. Transition to the appropriate phase first."
  5. If allowed: exit 0

#### DSL Addition

```yaml
gates:
  phase-gate:
    description: >
      Blocks file edits inappropriate for the current SDLC phase.
      During Spec, you can't edit source code. During Build, you
      can't rewrite the PRD. Phase discipline, mechanically enforced.
    event: PreToolUse
    matcher: "Edit|Write"
    type: command
    script: check-phase-gate.sh
    on_failure: block
```

#### Acceptance Criteria

1. During `spec` phase, editing `src/app.py` is blocked with clear message
2. During `build` phase, editing `spec/prd.md` is blocked with clear message
3. During `build` phase, editing `src/app.py` is allowed
4. When no `.sdlc/state.json` exists, all edits are allowed
5. The hook reads the phase from `.sdlc/state.json` `current_phase` field
6. Error messages name the current phase and the blocked file
7. Tests cover every phase with at least one allow and one block case

---

## Feature 3: Adversarial Review

### Problem

The current `SubagentStop` prompt hook reviews output constructively — "does this
meet standards?" But it doesn't review adversarially — "what could go wrong? what
did the agent miss? what assumptions are wrong?" Additionally, the same session
context that produced the work is the context that reviews it.

Correctless solves this with `context: fork` — a fresh agent at 0% context with
hostile instructions. We should adopt this principle.

### Solution

Replace the current `SubagentStop` prompt hook with an agent hook that spawns a
fresh verification agent with adversarial instructions. The verifier has tool
access (Read, Grep, Bash) to actually check the code, not just read the summary.

### Specification

#### Updated DSL Gate

```yaml
gates:
  adversarial-review:
    description: >
      Fresh agent reviews subagent output with adversarial intent.
      "What could go wrong? What did the agent miss? What edge cases
      are unhandled?" Never lets the implementer grade their own work.
    event: SubagentStop
    type: agent
    model: sonnet
    role: |
      You are a hostile code reviewer. Your job is NOT to confirm the
      work looks good — it's to find what's wrong. You have seen
      thousands of bugs escape well-intentioned reviews because the
      reviewer was too agreeable.

      You are a FRESH agent with no context from the implementation.
      You review the output cold, looking for:
      - Edge cases the implementer didn't consider
      - Error handling gaps (what happens when X fails?)
      - Assumptions that aren't validated
      - Security implications
      - Missing test cases for failure paths
      - Spec compliance gaps (does it ACTUALLY meet criteria?)

      You are constructive but relentless. You don't say "looks good"
      unless you genuinely cannot find issues.
    prompt: |
      A subagent just completed its work. Review it adversarially.

      $ARGUMENTS

      Read the actual files that were modified. Don't trust the summary.
      Check the tests — do they test failure paths or only happy paths?
      Check error handling — are exceptions caught too broadly?
      Check the acceptance criteria — is each one demonstrably met?

      If stop_hook_active is true and you still find critical issues:
        Return {"continue": false, "stopReason": "ADVERSARIAL REVIEW FAILED: [details]"}

      If you find issues the agent should fix:
        Return {"ok": false, "reason": "[specific issues with file:line references]"}

      If the work genuinely passes adversarial scrutiny:
        Return {"ok": true}
    timeout: 90
    max_retries: 1
    on_loop: escalate
```

#### Acceptance Criteria

1. SubagentStop fires an agent hook (not just a prompt hook)
2. The agent has Read, Grep, Glob, Bash tool access to inspect files
3. The role text includes "hostile" / "adversarial" framing
4. The agent checks actual files, not just the last_assistant_message summary
5. Happy-path-only test suites are flagged as insufficient
6. The gate replaces the existing constructive `subagent-review` gate
7. `on_loop: escalate` prevents infinite adversarial loops

---

## Feature 4: `/spec` Command — Socratic Specification

### Problem

The `/implement` command requires a PRD that passes Definition of Ready. But
writing a good PRD is hard — it requires understanding the domain, the codebase,
the constraints, and the edge cases. Users often start with a vague idea and
need help turning it into a buildable spec.

### Solution

A `/spec` skill that runs a Socratic loop: asking questions, researching the
codebase, searching the web for best practices, and iteratively building a PRD
until it's ready for `/implement`.

### Specification

#### Usage

```
/spec "Add user authentication with OAuth2 and JWT"
/spec                    # Resume an in-progress spec session
/spec spec/draft-auth.md # Refine an existing draft
```

#### Workflow

**Phase 1: Intent Capture**

The skill starts by understanding what the user wants to build:
- "What problem does this solve?"
- "Who uses this feature?"
- "What does success look like?"
- "What's explicitly out of scope?"

If the user provides a one-liner, the skill asks 3-5 clarifying questions
before proceeding. It does NOT start writing the PRD immediately.

**Phase 2: Research**

The skill dispatches research subagents in parallel:

1. **Codebase research** — Explore agent reads the existing codebase:
   - What patterns exist? (frameworks, conventions, architecture)
   - What code will this feature touch?
   - What tests exist for adjacent functionality?
   - Are there INVARIANTS.md contracts that apply?

2. **Web research** — WebSearch/WebFetch for:
   - Best practices for this type of feature
   - Common pitfalls and edge cases
   - Security considerations (CVEs, OWASP patterns)
   - Library/framework documentation for relevant tools

3. **Antipatterns check** — Read `.etc_sdlc/antipatterns.md` for relevant
   lessons from past bugs

The skill presents research findings to the user as a summary before
proceeding to spec writing.

**Phase 3: Iterative Spec Writing**

The skill writes a draft PRD and presents it section by section:

1. **Summary** — "Here's what I understand you want to build. Correct?"
2. **Scope** — "Here's what's in and out. Anything missing?"
3. **Requirements** — "Here are the business rules. Any I missed?"
4. **Acceptance Criteria** — "Here's how we'll know it's done. Specific enough?"
5. **Edge Cases** — "Here are the edge cases I found during research. Others?"
6. **Technical Constraints** — "Based on the codebase, here are the constraints."
7. **Security Considerations** — "Based on research, these need attention."

At each step, the user can:
- **Accept** — move to next section
- **Refine** — "No, also include X" or "Remove Y, it's out of scope"
- **Research more** — "I'm not sure about Z, can you research that?"

**Phase 4: Validation**

Before finalizing, the skill runs the PRD through the Definition of Ready
checklist (the same one the `/implement` command uses):
- [ ] Specific enough to implement without ambiguity
- [ ] Names concrete files, modules, endpoints
- [ ] Has measurable acceptance criteria
- [ ] Scope boundaries are clear
- [ ] Edge cases documented
- [ ] Security considerations addressed

If any gaps: the skill points them out and asks the user to resolve them.

**Phase 5: Output**

The skill writes the final PRD to `spec/{slug}.md` and confirms:

```
Spec written to: spec/prd-user-authentication.md

Definition of Ready: PASSED
- 12 acceptance criteria
- 8 edge cases documented
- 3 security considerations
- 4 files in scope

Ready to build:
  /implement spec/prd-user-authentication.md
```

#### PRD Output Format

The `/spec` command produces PRDs in the same format `/implement` expects:

```markdown
# PRD: [Feature Name]

## Summary
[1-3 paragraphs]

## Scope
### In Scope
- [specific items]
### Out of Scope
- [specific items]

## Requirements
### BR-001: [Business Rule]
[description]
### BR-002: ...

## Acceptance Criteria
1. [Specific, measurable criterion]
2. ...

## Edge Cases
1. [What happens when X]
2. ...

## Technical Constraints
- [Codebase patterns to follow]
- [Frameworks/libraries in use]
- [INVARIANTS.md rules that apply]

## Security Considerations
- [Based on web research + OWASP + feature type]

## Module Structure
[files to create/modify, based on codebase research]

## Research Notes
[Key findings from codebase and web research, for implementer context]
```

#### State Persistence

In-progress specs are saved to `spec/.drafts/{slug}.md` so the user can
resume with `/spec` in a new session. Completed specs are moved to `spec/`.

#### Acceptance Criteria

1. `/spec "one-liner"` asks at least 3 clarifying questions before writing
2. `/spec` with no args resumes the most recent draft from `spec/.drafts/`
3. Codebase research subagent reads relevant existing files and patterns
4. Web research subagent finds best practices and security considerations
5. Each PRD section is presented to the user for approval before moving on
6. The final PRD passes the Definition of Ready checklist
7. Output is written to `spec/{slug}.md` in the format `/implement` expects
8. The user can say "research more about X" at any point to trigger additional research
9. Antipatterns from `.etc_sdlc/antipatterns.md` are incorporated when relevant
10. Security considerations are auto-populated based on feature type
    (auth → CSRF/session, input → injection, storage → encryption)
11. The spec includes a Module Structure section with specific files to create/modify
12. `/spec spec/existing-draft.md` can refine an existing draft

---

## Implementation Order

1. **Phase gate hook** — smallest scope, most immediately useful, pure command hook
2. **Antipatterns learning loop** — update `inject-standards.sh` + create `/postmortem`
3. **Adversarial review** — update DSL gate, compile, install
4. **`/spec` command** — largest scope, requires skill definition + research integration

## Dependencies

- Features 1-3 have no external dependencies
- Feature 4 (`/spec`) benefits from Feature 1 (antipatterns) being in place first
- All features require `compile-sdlc.py` updates and `install.sh` redeployment

## Success Metrics

- Phase gate prevents at least 1 out-of-phase edit per session (measurable via audit trail)
- Antipatterns file grows over time (each postmortem adds an entry)
- Adversarial review catches issues the constructive review missed (tracked by retry count)
- `/spec` produces PRDs that pass Definition of Ready on first attempt (no rejection by `/implement`)
