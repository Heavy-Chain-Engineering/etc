# PRD: Closed-Loop Ticket Pipeline

## Summary

The Closed-Loop Ticket Pipeline is a skill (`/pull-tickets`) that bridges external task trackers (Linear, Jira, etc.) and the SDLC harness, enabling autonomous ticket-to-PR implementation with source-aware rejection routing.

When invoked (manually or via cron), the skill:
1. Pulls eligible tickets from the connected tracker via MCP
2. Analyzes the batch for cross-ticket dependencies and priority ordering
3. For each ticket, generates a **full PRD** (all 8 sections) by combining the SME's ticket content with codebase research, edge case analysis, and security considerations
4. Feeds the PRD through the complete SDLC pipeline (`/build`) — with all governance gates, TDD enforcement, invariant checks, and Definition of Ready evaluation intact
5. On **success**: creates a PR, updates the ticket to "In Review", and comments with a build summary and test instructions
6. On **failure at DoR**: rejects the ticket back to the originating source — commenting with specific, tactful questions and moving the ticket to "Needs Clarification"

The system treats the SDLC pipeline as non-negotiable. Every ticket, regardless of source, passes through the same gates a human-initiated `/build` would. The skill's unique contribution is the **intake translation** (ticket → PRD) and **bidirectional feedback** (rejection → source channel).

## Scope

### In Scope
- **`/pull-tickets` skill** — Claude Code skill (`.claude/skills/pull-tickets.md`) that orchestrates the full intake-to-build pipeline
- **Linear MCP integration** — Pull tickets via `list_issues`/`get_issue`, reject via `create_comment`/`update_issue`, close loop via status updates
- **Ticket-to-PRD translation** — Generate full 8-section PRD from ticket content + codebase research + web research
- **Batch dependency analysis** — Pull all eligible tickets, detect cross-ticket dependencies, plan execution order
- **Source-aware rejection routing** — When DoR fails, route specific questions back to the originating tracker (not inline to conversation)
- **Success loop closure** — On build completion: create PR, update ticket to "In Review", comment with build summary
- **Cron integration** — Configurable recurring invocation of `/pull-tickets` with concurrency limits
- **Tactful SME communication** — Question generation tuned for non-technical domain experts (no jargon, specific questions, actionable)

### Out of Scope
- **Auto-deployment** — Pipeline ends at PR creation. Merge and deploy remain human-gated.
- **GitHub Issues as a source** — Linear only for v1. Architecture supports future sources but we don't build the adapters.
- **Slack/email integration** — No notification channels beyond the tracker itself.
- **Jira adapter** — Architecture is transport-agnostic (MCP-based), but only Linear is implemented in v1.
- **Ticket creation** — The skill reads and responds to tickets. It does not create new tickets on behalf of SMEs.
- **Multi-repo builds** — One ticket maps to one codebase. Cross-repo work is out of scope.
- **SME authentication/permissions** — Any ticket in eligible status is fair game. No per-user filtering.

## Requirements

### BR-001: Ticket Eligibility Filter
The skill pulls tickets from the connected tracker that match configurable eligibility criteria. For Linear v1: tickets in the ENG team, in "Todo" status, assigned to the V2 Build project. Tickets in "Backlog", "Needs Clarification", "In Progress", "In Review", or "Done" are excluded.

### BR-002: Batch Dependency Analysis
When multiple eligible tickets are pulled, the skill analyzes them for cross-ticket dependencies before processing. Dependencies are detected by: (a) overlapping affected areas of the codebase (determined by codebase research per ticket), (b) explicit references between tickets, (c) logical ordering (e.g., "add notes model" must precede "add notes to vendor detail page"). Dependent tickets are sequenced; independent tickets may be processed concurrently up to the configured concurrency limit.

### BR-003: Ticket-to-PRD Translation
Each eligible ticket is translated into a full PRD matching the `/spec` output format (Summary, Scope, Requirements, Acceptance Criteria, Edge Cases, Technical Constraints, Security Considerations, Module Structure). The translation combines: (a) the SME's ticket title and description, (b) codebase research (existing patterns, adjacent code, affected files), (c) edge case and security analysis. The PRD is written to `.etc_sdlc/features/{ticket-id}/spec.md`.

### BR-004: Full Pipeline Enforcement
Every generated PRD enters the SDLC pipeline through `/build`. All existing governance gates apply without exception: Definition of Ready validation, TDD enforcement, invariant checks, required reading, code review, CI pipeline. No ticket bypasses any gate regardless of source, priority, or label.

### BR-005: Source-Aware Rejection Routing
When a ticket fails at any pipeline gate (DoR, build failure, test failure), the skill routes feedback to the originating source. For Linear: (a) adds a comment to the ticket with specific, actionable questions or failure details, (b) moves the ticket status to "Needs Clarification." The comment is written for SMEs — no jargon, no stack traces, no file paths unless necessary. Each rejection includes what's missing and what the SME should do next.

### BR-006: Success Loop Closure
When `/build` succeeds for a ticket: (a) create a PR against the main branch with the implementation, (b) update the Linear ticket status to "In Review", (c) add a comment to the ticket summarizing what was built, files changed, test coverage, and how to verify. The comment links to the PR.

### BR-007: Cron-Triggered Invocation
The skill can be invoked on a configurable cron schedule. Each cron cycle calls `/pull-tickets` which pulls all eligible tickets and processes them per BR-002 through BR-006. The cron schedule, concurrency limit, and team/project filter are configurable at invocation time.

### BR-008: Idempotent Ticket Processing
The skill must not re-process a ticket that is already in progress. Before starting work on a ticket, the skill moves it to "In Progress" in Linear. If a ticket is already "In Progress", it is skipped. This prevents duplicate processing from overlapping cron cycles or manual invocations.

### BR-009: Graceful Failure Isolation
A failure on one ticket must not block processing of other tickets in the batch. If ticket A fails at any stage, log the failure, reject ticket A back to source per BR-005, and continue processing tickets B, C, etc.

### BR-010: Scope Gate
If the ticket-to-PRD translation produces a PRD that, after recursive decomposition, yields more than 15 leaf tasks (DEEP mode), the skill does NOT proceed with the build. Instead, it: (a) creates sub-issues in Linear for each major work area identified during decomposition, (b) links sub-issues to the parent ticket, (c) adds a comment to the parent: "This is a large scope — I've broken it into N smaller tickets that can be built independently. Please review and prioritize the sub-tickets, then move the ones you want built to Todo." (d) moves the parent to "Needs Clarification". This prevents the system from attempting oversized builds and teaches SMEs to file right-sized tickets.

### BR-011: Triage Mode
When invoked with `--triage-only`, the skill performs batch analysis WITHOUT building. It: (a) pulls all eligible tickets, (b) researches the codebase per ticket to identify affected areas and estimate complexity, (c) detects cross-ticket dependencies, conflicts, and logical ordering, (d) reorganizes the Linear board: creates sub-issues for epics, sets priorities based on dependency depth (blockers get higher priority), adds "blocked by" relationships between dependent tickets via comments, adds size labels (S/M/L/XL based on estimated leaf task count), (e) comments on each ticket with the analysis summary. Triage mode is non-destructive — it adds information to tickets but does not move them out of "Todo" or start builds.

### BR-012: Dependency Linking in Linear
When batch analysis detects that ticket A depends on ticket B, the skill comments on ticket A: "This ticket depends on [B-identifier]: [B title]. I recommend building [B] first." If both tickets are eligible, triage mode also suggests priority ordering. The skill does NOT change ticket status for dependencies (only for conflicts per BR-002) — it informs, the SME decides.

## Acceptance Criteria

1. When `/pull-tickets` is invoked, it pulls all tickets from the ENG team in "Todo" status in the V2 Build project and reports the count to the conversation
2. When 3+ eligible tickets exist, the skill identifies cross-ticket dependencies (overlapping codebase areas) and presents a sequenced execution plan before proceeding
3. When a ticket titled "Add ability to export compliance reports to PDF" with a well-structured description is processed, the skill generates a full 8-section PRD at `.etc_sdlc/features/ENG-{N}/spec.md` that names concrete files, endpoints, and acceptance criteria
4. When a ticket titled "Reports" with no description is processed, the skill rejects it: a comment appears on the Linear ticket with specific questions ("What type of reports?", "Who is the audience?", "What data should the report contain?"), and the ticket status moves to "Needs Clarification"
5. When a generated PRD passes DoR and `/build` succeeds, a PR is created, the Linear ticket moves to "In Review", and a comment summarizes what was built with a link to the PR
6. When `/build` fails due to test failure on a ticket, the Linear ticket receives a comment explaining the failure in SME-friendly language and moves to "Needs Clarification"
7. When a ticket is already "In Progress", `/pull-tickets` skips it without error
8. When ticket A fails during processing, tickets B and C continue processing unaffected
9. When `/pull-tickets` is invoked via cron with concurrency limit 2, at most 2 tickets are being built simultaneously at any point
10. When a rejection comment is posted to Linear, it contains no jargon, no stack traces, no raw file paths — only questions and next steps an SME can act on
11. When a ticket titled "Build the entire reporting module" decomposes into 20+ leaf tasks, the skill creates sub-issues in Linear linked to the parent, comments with the breakdown, and moves the parent to "Needs Clarification" without attempting the build
12. When `/pull-tickets --triage-only` is invoked with 5 eligible tickets, each ticket receives a comment with complexity estimate and dependency analysis, size labels (S/M/L/XL) are suggested, and dependency relationships are documented — but no tickets are built or moved out of "Todo"
13. When triage detects that ENG-20 depends on ENG-19, a comment is added to ENG-20 noting the dependency and recommending ENG-19 be built first

## Edge Cases

1. **Ticket with no description** — Reject immediately with a comment asking the SME to use the Bug Report or Feature Request template. Don't attempt PRD generation from title alone.
2. **Ticket references code/features that don't exist in the codebase** — PRD generation includes codebase research. If the referenced area doesn't exist, note it in the PRD's Technical Constraints and let DoR decide if it's implementable or needs clarification.
3. **Two tickets request conflicting changes** — Batch dependency analysis flags the conflict. Both tickets are rejected back to source with a comment: "This ticket conflicts with [other ticket]. Please coordinate with [other ticket author] and clarify which should take priority."
4. **Ticket is modified in Linear while being processed** — The skill snapshots ticket content at pull time. Mid-processing changes are ignored until the next cron cycle.
5. **Linear MCP is unreachable** — Fail the entire cycle loudly. Do not process any tickets if the rejection channel is unavailable (we'd have no way to reject back).
6. **Cron fires while previous cycle is still running** — Skip the new cycle. Log that the previous cycle is still in progress.
7. **SME re-submits a "Needs Clarification" ticket back to "Todo" without changes** — The skill will pull it again, generate a new PRD, and likely reject again with the same questions. This is by design — no blacklisting.
8. **Ticket has attachments (screenshots, PDFs)** — v1 processes text content only. Note in rejection if the ticket description relies on an attachment for context: "Your ticket references an attachment, but I can only read the text description. Please describe the issue in the ticket body."
9. **Generated PRD fails DoR repeatedly after ticket-to-PRD translation** — This is a system failure, not an SME failure. Don't reject to the SME. Log the failure for engineering review and skip the ticket.
10. **All tickets in a batch are interdependent** — Process sequentially in dependency order, concurrency limit effectively becomes 1 for this batch.

## Technical Constraints

- **Skill format:** `.claude/skills/pull-tickets.md` — follows existing skill conventions (SKILL.md with prompt orchestration)
- **MCP dependency:** Requires `linear-server` MCP to be connected. Skill must verify MCP availability before proceeding.
- **Existing pipeline integration:** PRDs feed into `/build` exactly as if a human ran `/spec` then `/build`. No special-casing in the pipeline for auto-generated PRDs.
- **Task file format:** Uses existing `.etc_sdlc/tasks/*.yaml` structure with all required fields (task_id, title, assigned_agent, status, requires_reading, files_in_scope, acceptance_criteria, dependencies)
- **Feature directory:** Each ticket gets `.etc_sdlc/features/{ticket-identifier}/` (e.g., `.etc_sdlc/features/ENG-19/`)
- **Cron mechanism:** Claude Code's `CronCreate` tool — session-scoped, 7-day auto-expiry. The skill documents how to set up the cron.
- **File-set isolation:** Cross-ticket concurrency must respect the same file-set isolation rule as within-ticket parallelism — two tickets touching overlapping files cannot build simultaneously
- **Status mapping:** Skill calls `get_status_map` at startup to resolve status names to UUIDs. Does not hardcode UUIDs.
- **Compiler integration:** The skill source lives in `skills/pull-tickets.md` and is compiled to `dist/skills/pull-tickets/SKILL.md` by `compile-sdlc.py`. Requires compiler update.

## Security Considerations

- **MCP credential handling:** Linear API key is in `.claude.json` env config — never logged, never included in PRDs or comments. The skill uses MCP tools which handle auth transparently.
- **Comment content sanitization:** Rejection comments must not leak internal file paths, stack traces, environment variables, or infrastructure details to SMEs. The comment generation prompt explicitly prohibits this.
- **Ticket content as untrusted input:** SME ticket descriptions are untrusted input. They are used as context for PRD generation but never executed as code, interpolated into shell commands, or used in file paths without sanitization. The ticket identifier (e.g., "ENG-19") is sanitized to alphanumeric + hyphen before use in directory names.
- **PR content:** Auto-generated PRs contain code that has passed all harness gates (TDD, invariants, code review, CI). The PR itself is human-reviewed before merge — this is the final security boundary.
- **Rate limiting:** Concurrency limit prevents the skill from overwhelming the Linear API or the build infrastructure. Default concurrency of 1 for v1.

## Module Structure

| File | Action | Description |
|------|--------|-------------|
| `skills/pull-tickets.md` | **Create** | Skill source — orchestration prompt for the full intake-to-build pipeline |
| `compile-sdlc.py` | **Modify** | Add compilation support for `pull-tickets` skill (copy to `dist/skills/pull-tickets/SKILL.md`) |
| `spec/etc_sdlc.yaml` | **Modify** | Add `pull-tickets` to the skills section with description and configuration schema |
| `install.sh` | **Modify** | Include `pull-tickets` skill in installation to `~/.claude/skills/` |
| `tests/test_pull_tickets.py` | **Create** | Tests for ticket eligibility filtering, dependency detection, PRD generation prompts, rejection comment formatting, status transitions |

## Research Notes

### Existing Harness Architecture
- 13 governance gates compiled from `spec/etc_sdlc.yaml` via `compile-sdlc.py` to `dist/`
- `/implement` is a 4-step pipeline: validate spec → decompose → dispatch subagents → verify
- `/build` is an 8-step conductor wrapping `/implement` with scoring, wave planning, recursive decomposition
- Definition of Ready evaluated at UserPromptSubmit (project-level) and TaskCreated (task-level)
- Existing intake system (`platform/src/etc_platform/intake.py`) tracks source material types/classifications but has no origin channel concept

### Linear MCP Tools Available
- `list_issues` — filter by team, project, state, priority, assignee
- `get_issue` — full details including description, comments, sub-issues
- `create_comment` — add comment to issue (Markdown)
- `update_issue` — change state, priority, assignee, description
- `get_status_map` — resolve status names to UUIDs per team

### Linear Workflow States (ENG team)
- Backlog → Todo → In Progress → In Review → Done
- Needs Clarification (custom, unstarted type — for rejection routing)
- Canceled, Duplicate

### Gray Areas Resolved
See `.etc_sdlc/features/closed-loop-ticket-pipeline/gray-areas.md` for 5 resolved architectural decisions with rationale.
