# Validated & Updated: Agent Hardening Best Practices for Claude Code

**Date:** 2026-02-25
**Version:** 2.0
**Author:** Manus AI (commissioned by Jason Vertrees)

**Purpose:** This document provides a validated and updated set of best practices for hardening Claude Code agent definitions. It synthesizes findings from the latest official Anthropic documentation (as of February 2026), established community patterns from leading practitioners, and a strategic analysis of agent design principles. It is intended to replace the previous research document and serve as the canonical guide for building robust, secure, and effective agents.

---

## 1. Core Concepts: Agents, Skills, and Teams

Claude Code's architecture has evolved beyond a simple agent/skill dichotomy. A clear understanding of the three primary components—Subagents, Agent Teams, and Skills—is fundamental to effective hardening. The original document's distinction was directionally correct but is now superseded by this more precise, officially documented hierarchy.

| Component | Description | Use Case | State & Context |
|---|---|---|---|
| **Subagent** | A specialized, autonomous assistant for a specific task. It runs in its own context window with a custom prompt, tools, and permissions. | Delegating focused, isolated tasks like running tests, performing a security scan, or refactoring a specific module. Ideal for reducing context clutter in the main conversation. | Isolated context. Communicates results back to the parent agent but not with other subagents. |
| **Agent Team** | A coordinated group of multiple independent Claude Code sessions. A "lead" agent assigns tasks to "teammate" sessions, which can work in parallel and communicate with each other. | Complex, parallelizable work. Examples: multi-pronged research, developing a new feature with frontend/backend/database specialists, or debugging with competing hypotheses. | Each teammate has its own independent context window. Teammates share a task list and can communicate directly. |
| **Skill** | A reusable set of instructions for a specific procedure. It does not have its own persona or long-term memory. | Encapsulating a precise, repeatable process, like a deployment checklist, a code explanation template, or a specific linting procedure. | Injected directly into the context of the calling agent (main session, subagent, or teammate). |

**Key Takeaway:** Use **Subagents** for task isolation, **Agent Teams** for parallel collaboration, and **Skills** to provide reusable, procedural knowledge to any agent or team.

---

## 2. The Agent Definition File: Anatomy & Frontmatter

Agents are defined in Markdown files (`.md`) located in `~/.claude/agents/` (user-level), `.claude/agents/` (project-level), or passed via the `--agents` CLI flag. The file consists of two parts: YAML frontmatter for configuration and a Markdown body for the system prompt.

### Canonical Frontmatter Reference (2026)

The original document's frontmatter list was incomplete. The following table represents the comprehensive, validated set of fields available for subagent definitions as of February 2026 [1].

| Field | Required | Type | Description & Best Practices |
|---|---|---|---|
| `name` | **Yes** | `string` | The unique, `kebab-case` identifier for the agent. This is how it's invoked. |
| `description` | **Yes** | `string` | **The single most critical field for hardening.** The orchestrator LLM uses this to decide when to delegate a task. It must be specific, using gerunds (verbs ending in -ing) to describe actions. Include activation triggers, boundaries, and `<example>` blocks for few-shot routing [2][3]. |
| `model` | No | `string` | Model to use. Aliases: `opus`, `sonnet`, `haiku`. `inherit` (default) uses the parent's model. **Hardening Principle:** Use `sonnet` for mechanical, checklist-driven agents and `opus` for agents requiring complex reasoning or judgment. This optimizes both cost and performance [4]. |
| `tools` | No | `list[string]` | **Allowlist** of tools the agent can use (e.g., `Read`, `Grep`, `Bash`). If omitted, inherits all parent tools. **Hardening Principle:** Enforce least privilege. A review agent should *never* have `Write` or `Edit` [5]. |
| `disallowedTools` | No | `list[string]` | **Denylist** of tools to prevent the agent from using. This overrides `tools` and inherited tools. |
| `permissionMode` | No | `string` | Sets the agent's permission behavior. Values: `default` (ask), `acceptEdits`, `dontAsk`, `bypassPermissions` (use with extreme caution), `plan` (read-only exploration). **Hardening Principle:** Use `plan` or `dontAsk` for review agents. `bypassPermissions` should only be used in tightly controlled, sandboxed environments [5][6]. |
| `maxTurns` | No | `integer` | Maximum number of agentic turns before the subagent stops. A crucial guardrail against runaway execution and unexpected costs. |
| `skills` | No | `list[string]` | A list of skill names to preload into the subagent's context at startup. The full skill content is injected. |
| `memory` | No | `string` | Enables persistent memory. Scopes: `user`, `project`, `local`. The agent can read/write to a dedicated directory to learn across sessions. Essential for agents that need to build institutional knowledge [7]. |
| `hooks` | No | `dict` | Lifecycle hooks (e.g., `PreToolUse`, `PostToolUse`, `Stop`) scoped to this subagent. Powerful for validation, cleanup, and automation [8]. |
| `isolation` | No | `string` | Set to `worktree` to run the agent in a temporary, isolated `git worktree`. The worktree is automatically cleaned up if no changes are made. A powerful sandboxing mechanism for agents that might modify files [6]. |
| `background` | No | `boolean` | If `true`, the agent runs as a background task, allowing the main conversation to continue. |

### The Power of the `<example>` Block

The original document correctly identified this pattern. Our research confirms it is a community-driven best practice that significantly improves routing accuracy. By providing concrete examples of when and how an agent should be invoked, you are giving the orchestrator model a set of few-shot demonstrations to guide its decision-making.

**Mandatory Practice:** Every agent definition **must** include at least two `<example>` blocks in its `description` field.

```yaml
description: >
  Performs a comprehensive security review of code changes, focusing on OWASP Top 10 vulnerabilities.
  Use when new endpoints are added, authentication logic changes, or new dependencies are introduced.

  <example>
  Context: A developer has added a new API endpoint that processes user-uploaded files.
  user: "I'm ready for a review of my new file upload endpoint."
  assistant: "Understood. I'll invoke the `security-reviewer` agent to check for path traversal, file type validation, and resource exhaustion vulnerabilities."
  <commentary>The trigger is a new endpoint handling potentially malicious user input, which is a primary security concern.</commentary>
  </example>
```

---

## 3. The Hardened Agent Template (v2.0)

Based on the validated findings, the following template should be used for all new and updated agent definitions. It incorporates the complete frontmatter, structured sections for clarity, and explicit sections for modern features like error recovery and coordination.

```markdown
---
name: your-agent-name
description: >
  [One-sentence capability statement, starting with a gerund.] [Specific activation triggers.]
  [Clear boundaries on what this agent does NOT do.]

  <example>
  Context: [A realistic situation where this agent is needed.]
  user: "[A typical user request that should trigger this agent.]"
  assistant: "[The ideal response from the lead agent, invoking this subagent.]"
  <commentary>[Explanation of why this agent was the correct choice.]</commentary>
  </example>

  <example>
  Context: [Another distinct situation.]
  user: "[Another trigger phrase.]"
  assistant: "[Another invocation example.]"
  <commentary>[Another justification.]</commentary>
  </example>

model: [opus | sonnet | haiku | inherit] # Choose based on cognitive load
tools: [Read, Grep, Glob] # Principle of Least Privilege
disallowedTools: [Write, Edit] # Explicitly deny dangerous tools for review agents
permissionMode: plan # Default to read-only planning for safety
isolation: worktree # Isolate file changes from the main project branch
maxTurns: 25 # Prevent runaway execution
memory: project # Enable shared, persistent learning for the team
hooks:
  PreToolUse:
    - matcher: "Bash"
      hooks:
        - type: command
          command: "./.claude/scripts/validate-bash.sh"
---

# [ROLE & PHILOSOPHY]

[A single, powerful sentence defining the agent's persona and core principle. e.g., "You are a hyper-vigilant Security Reviewer who trusts nothing and verifies everything."]

## 1. Before Starting (Non-Negotiable Prerequisites)

**MUST** read the following files in order to establish full context. Do not proceed without this information.

1.  `~/.claude/standards/global-coding-standard.md`
2.  `.claude/standards/project-specific-patterns.md`
3.  The full `git diff` of the current changes.

## 2. Core Responsibilities

A numbered list of 3-5 primary duties. Each should be a single, clear sentence explaining the "what" and the "why."

1.  **Identify Security Flaws:** To prevent vulnerabilities from reaching production.
2.  **Provide Actionable Fixes:** To empower developers to remediate issues quickly.
3.  **Classify Finding Severity:** To prioritize the most critical risks.

## 3. Workflow / Process

A step-by-step, numbered procedure that the agent must follow. Use explicit commands and decision trees.

1.  **Map Attack Surface:** Use `Grep` to find all new or modified API endpoints.
2.  **Analyze Input Vectors:** For each endpoint, trace all user-supplied input.
3.  **Run Static Analysis:** Execute the `security-scan.sh` script on changed files.
4.  **Synthesize Findings:** Collate results into the specified output format.

## 4. Concrete Heuristics & Decision Frameworks

This is the agent's brain. Provide specific, deterministic rules, not vague principles.

### SQL Injection Detection

-   **Grep Pattern:** `grep -rE "(f-string|\.format).*SELECT.*FROM"`
-   **Rule:** If user input is part of a raw SQL query string, flag as **CRITICAL**.
-   **Good:** `session.execute(select(User).where(User.id == :user_id), {"user_id": user_id})`
-   **Bad:** `session.execute(f"SELECT * FROM users WHERE id = {user_id}")`

## 5. Output Format

Provide the exact Markdown template the agent must use for its final report. This ensures consistency and machine-readability.

```markdown
### Security Review Report

**Verdict:** [PASS | FAIL]

| Severity | Finding | File:Line | Recommendation |
|---|---|---|---|
| CRITICAL | SQL Injection | `api/v1/users.py:42` | Use parameterized queries. |
```

## 6. Boundaries & Escalation

Define what the agent does and does not do, and how it interacts with others.

-   **DO NOT** write or edit code. Your role is to review and report.
-   **DO NOT** comment on code style; escalate to the `code-reviewer` agent.
-   **ESCALATE** any `CRITICAL` findings to the human user for immediate attention.

## 7. Error Recovery

Define how the agent should behave when its own process fails.

-   **If a standards file is not found:** Proceed with built-in OWASP knowledge and report the missing file.
-   **If a `Bash` command fails:** Report the command, its output, and the error, then stop and ask for human guidance.

## 8. Coordination & Team Play

Define the agent's role within a larger team.

-   **Reports to:** The `sem` (Senior Engineering Manager) agent or the human user.
-   **Handoff:** When the review is complete, hand off the report to the `verifier` agent to confirm tests still pass.
-   **Interaction with Agent Teams:** If part of a `security-audit` team, share findings in the shared task list and review the work of the `dependency-auditor` teammate.

---

## 4. Summary of Validated Changes & Recommendations

This research has validated several core concepts from the original document while revealing significant updates to the Claude Code platform. The following summarizes the key changes and provides a clear path forward for hardening the existing agent suite.

1.  **Adopt New Terminology:** Replace all internal references to "agents" with the more specific **Subagents** and **Agent Teams**. This aligns with official documentation and clarifies capabilities.

2.  **Mandate the Hardened Template:** All 22 agents must be refactored to follow the `Hardened Agent Template (v2.0)` provided above. This is the single most important action to improve robustness and reliability.

3.  **Enrich Frontmatter:** All agent definitions must be updated to use the complete, modern frontmatter schema. Specifically, fields like `permissionMode`, `isolation`, `maxTurns`, and `memory` must be added to enforce security and efficiency.

4.  **Prioritize `description` Field Hardening:** Every agent's `description` must be rewritten to be a high-signal, action-oriented statement with at least two `<example>` blocks for few-shot routing.

5.  **Implement Least Privilege:** The `tools` and `disallowedTools` fields must be reviewed for every agent to ensure they have the absolute minimum set of capabilities required for their role.

6.  **Introduce Agent Teams:** For complex workflows currently handled by a single, monolithic agent, consider refactoring them into smaller, more focused agents coordinated by an **Agent Team**. This is particularly relevant for the `project-bootstrapper` and `frontend-dashboard-refactorer`.

By implementing these changes, the agent suite will be more secure, more reliable, more efficient, and better aligned with the current capabilities of the Claude Code platform.

---

## References

[1] Anthropic. (2026). *Create custom subagents - Claude Code Docs*. Retrieved from https://docs.anthropic.com/en/docs/claude-code/sub-agents

[2] Greene, T. (2025). *Best practices for Claude Code subagents*. PubNub. Retrieved from https://www.pubnub.com/blog/best-practices-for-claude-code-sub-agents/

[3] Moradi, K. (2025). *Claude Code Skills: The Engineering Handbook for Production-Grade Agentic Systems*. Medium. Retrieved from https://medium.com/@moradikor296/claude-code-skills-the-engineering-handbook-for-production-grade-agentic-systems-4997c883e19c

[4] Anthropic. (2026). *Claude Code settings - Model configuration*. Retrieved from https://docs.anthropic.com/en/docs/claude-code/settings#model-configuration

[5] Trail of Bits. (2026). *claude-code-config*. GitHub. Retrieved from https://github.com/trailofbits/claude-code-config

[6] Crosley, B. (2026). *Claude Code CLI: The Definitive Technical Reference*. Retrieved from https://blakecrosley.com/en/guides/claude-code

[7] Anthropic. (2026). *Manage Claude's memory - Claude Code Docs*. Retrieved from https://docs.anthropic.com/en/docs/claude-code/memory

[8] Anthropic. (2026). *Automate with hooks - Claude Code Docs*. Retrieved from https://docs.anthropic.com/en/docs/claude-code/hooks

[9] Anthropic. (2026). *Orchestrate teams of Claude Code sessions - Claude Code Docs*. Retrieved from https://docs.anthropic.com/en/docs/claude-code/agent-teams

