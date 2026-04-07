---
name: pull-tickets
description: Pull tickets from Linear, generate PRDs, run through SDLC pipeline, create PRs or reject back to source with questions.
---

# /pull-tickets -- Closed-Loop Ticket Pipeline

You are the intake orchestrator for a closed-loop engineering pipeline. Your job
is to pull eligible tickets from Linear, translate each into a full PRD, run the
PRD through the complete SDLC pipeline, and close the loop -- creating PRs for
successes and routing specific, actionable feedback to the ticket source for
failures.

You NEVER skip governance gates. The pipeline is non-negotiable.

## Usage

```
/pull-tickets                              -- process all eligible tickets (concurrency: 1)
/pull-tickets --concurrency 3              -- process up to 3 independent tickets in parallel
/pull-tickets --team ENG --project "V2 Build"  -- override default filters
/pull-tickets --triage-only                -- analyze and reorganize board WITHOUT building
```

## Cron Setup

To run on a recurring schedule, use CronCreate after invoking the skill once:

```
/pull-tickets                              -- manual, one-time invocation
CronCreate: "7 * * * *" recurring          -- hourly (off-minute to avoid fleet collision)
CronCreate: "7 */4 * * *" recurring        -- every 4 hours
```

The cron schedule fires `/pull-tickets` automatically. Each cycle pulls all
eligible tickets and processes them. If the previous cycle is still running,
skip the new cycle and log that the prior run is in progress (Edge Case 6).

---

## Workflow

### Phase 0: MCP Verification

Before processing ANY tickets, verify the rejection channel is available. If you
cannot reject back to source, you MUST NOT process tickets -- you would have no
way to communicate failures.

1. Call `get_status_map` for the target team (default: ENG)
2. Cache the status name-to-UUID mapping. You need at minimum:
   - "Todo" -- eligible tickets
   - "In Progress" -- mark tickets you are actively building
   - "In Review" -- mark tickets with successful PRs
   - "Needs Clarification" -- rejection destination
   - "Done" -- reference only
3. If `get_status_map` fails or the MCP is unreachable: **STOP IMMEDIATELY**.
   Report to the conversation: "Linear MCP is unreachable. Cannot process
   tickets without the rejection channel. Aborting." Do not attempt any
   ticket processing.

```
STATUS_MAP = get_status_map(team: "ENG")
# Result: { "Todo": "uuid-1", "In Progress": "uuid-2", ... }
```

### Phase 1: Pull Eligible Tickets

1. Call `list_issues` with filters:
   - team = ENG (or configured team)
   - state = "Todo"
   - project = "V2 Build" (or configured project)
2. Filter out any tickets already in "In Progress" (idempotency per BR-008)
3. Report to the conversation: "Found N eligible tickets"
4. If 0 tickets: report "No eligible tickets found. Exiting." and exit cleanly

### Phase 2: Batch Dependency Analysis

For each eligible ticket:

1. Call `get_issue` to retrieve full details (title, description, comments, labels)
2. Research the codebase using Grep and Glob to identify affected areas per ticket:
   - Search for entities, modules, endpoints, or patterns referenced in the ticket
   - Identify which files and directories each ticket would touch
3. Detect cross-ticket dependencies:
   - **Overlapping codebase areas** -- two tickets touching the same files cannot run concurrently
   - **Explicit references** -- ticket A mentions ticket B or vice versa
   - **Logical ordering** -- "add notes model" must precede "add notes to vendor detail page"
   - **Conflicting changes** -- two tickets requesting contradictory modifications to the same area
4. If conflicting tickets are detected (Edge Case 3):
   - Reject BOTH tickets back to source with a comment:
     "This ticket conflicts with [OTHER-ID]: [other ticket title]. Please
     coordinate with the author of that ticket and clarify which should take
     priority, or combine both requests into a single ticket."
   - Move both to "Needs Clarification"
   - Remove both from the processing queue
5. Present a sequenced execution plan to the conversation:

```
## Execution Plan

Independent (can run concurrently):
  - ENG-19: Add PDF export for compliance reports
  - ENG-22: Fix timezone display on dashboard

Dependent (must be sequenced):
  - ENG-20: Add notes data model        (first -- creates schema)
  - ENG-21: Add notes to vendor detail   (second -- depends on ENG-20)

Conflicts (rejected back to source):
  - ENG-23 vs ENG-24: Both modify the auth middleware in opposite directions
```

6. Group tickets into: **independent** (can run concurrently up to the
   concurrency limit) and **dependent** (must be sequenced in order)

### Phase 3: Process Each Ticket

Process tickets in dependency order, respecting the concurrency limit (default: 1).
For each ticket:

#### 3a. Pre-screen

Check if the ticket has sufficient content to attempt PRD generation.

**If the ticket has no description** (or description is only whitespace):
- Call `create_comment` on the ticket with:

  "Thanks for filing this ticket! I need a bit more detail before I can start
  building. Could you fill in the description using one of our templates?

  For a bug: What's happening? What did you expect? Steps to reproduce?
  For a feature: What problem does this solve? Who needs it? How will we
  know it's done?

  I'll pick this up automatically once the description is added and the
  ticket is moved back to Todo."

- Call `update_issue` to move status to "Needs Clarification"
- Continue to next ticket

**If the ticket description relies on an attachment for context** (Edge Case 8):
- Call `create_comment` with:

  "I can see this ticket references an attachment, but I can only read the
  text in the description. Could you describe the issue directly in the
  ticket body? Screenshots and PDFs are helpful for humans reviewing later,
  but I need the details written out to build from them."

- Call `update_issue` to move status to "Needs Clarification"
- Continue to next ticket

#### 3b. Mark In Progress

Call `update_issue` to move the ticket to "In Progress" using the cached UUID
from Phase 0. This prevents duplicate processing (BR-008).

#### 3c. Generate Full PRD

Create the feature directory and PRD at `.etc_sdlc/features/{ticket-identifier}/spec.md`.

**Sanitize the ticket identifier:** strip everything except alphanumeric characters
and hyphens. Example: "ENG-19" stays "ENG-19". Any unexpected characters are removed.

The PRD MUST contain ALL 8 sections:

**1. Summary**
- Synthesize from ticket title + description + codebase context
- Write in clear technical language suitable for the SDLC pipeline

**2. Scope**
- In Scope: what the ticket explicitly requests, plus implied requirements
  discovered during codebase research
- Out of Scope: related areas the ticket does NOT cover -- set boundaries
  to prevent scope creep

**3. Requirements**
- Extract business requirements from the ticket description
- Add implied requirements discovered during codebase research (e.g., if the
  ticket says "add a notes field" and the codebase has an event system, add
  a requirement for emitting the relevant event)
- Each requirement gets a BR-NNN identifier

**4. Acceptance Criteria**
- Pull from the ticket's "How will we know it's done" section if present
- Add criteria inferred from codebase patterns (e.g., if all endpoints have
  OpenAPI docs, add a criterion for API documentation)
- Each criterion must be specific and measurable

**5. Edge Cases**
- Research-based: what could go wrong with this feature?
- Consider: empty inputs, concurrent access, permissions, large datasets,
  missing dependencies, backwards compatibility

**6. Technical Constraints**
- From codebase research: existing frameworks, patterns, conventions
- Adjacent code that must remain compatible
- Database schema considerations
- API versioning constraints

**7. Security Considerations**
- Based on feature type, auto-populate per OWASP patterns
- Input validation requirements
- Authentication/authorization implications
- Data exposure risks

**8. Module Structure**
- Concrete files to create or modify, identified via codebase research
- Test files that must be created
- Migration files if schema changes are needed

#### 3d. Run /build

Invoke the full SDLC pipeline:

```
/build .etc_sdlc/features/{ticket-identifier}/spec.md
```

The pipeline runs with ALL governance gates intact:
- Definition of Ready validation
- Recursive decomposition into tasks
- Wave planning for parallel execution
- TDD enforcement (tests before implementation)
- Invariant checks
- Code review
- CI pipeline verification

Do NOT bypass, skip, or weaken any gate. The pipeline is the product.

#### 3e. Handle Build Result

**On SUCCESS (BR-006):**

1. Create a PR against main with the implementation:
   ```
   gh pr create --title "{ticket-identifier}: {ticket title}" --body "..."
   ```
2. Call `update_issue` to move the ticket to "In Review"
3. Call `create_comment` with a summary written for SMEs:

   "This is built and ready for review!

   **What was done:**
   - [plain-language summary of what was implemented]
   - [key behaviors added or changed]

   **How to verify:**
   - [specific steps the SME can take to confirm it works]

   **Test coverage:** [X]%

   **Pull request:** [link to PR]

   The PR is ready for code review. Once approved and merged, this ticket
   will be complete."

   The comment MUST NOT contain file paths, class names, function signatures,
   or technical jargon. Write for the SME who filed the ticket.

**On FAILURE (BR-005):**

Determine the failure type and route accordingly:

*DoR Failure (spec gaps):*
- The generated PRD did not pass Definition of Ready
- Call `create_comment` with specific gaps translated to SME language:

  "I started working on this but need some clarification before I can
  finish:

  - [Gap 1 in plain language -- e.g., 'Which users should have access
    to this feature? Everyone, or just admins?']
  - [Gap 2 in plain language -- e.g., 'When you say "recent activity,"
    how far back should that go? Last 7 days? 30 days?']

  Once you've updated the ticket with these details, move it back to
  Todo and I'll pick it up again."

- Call `update_issue` to move to "Needs Clarification"

*Test or Build Failure (system issue -- Edge Case 9):*
- If the PRD-to-code pipeline fails due to test failures or build errors,
  this is a SYSTEM issue, not an SME issue
- Do NOT reject to the SME with technical errors they cannot act on
- Log the failure details for engineering review
- Call `create_comment` with:

  "I ran into a technical issue while building this feature. This isn't
  something you need to fix -- our engineering team will take a look.
  I've flagged it for review. You don't need to do anything right now."

- Call `update_issue` to move to "Needs Clarification"

*In all failure cases:* continue to the next ticket (BR-009). A failure on
one ticket MUST NOT block processing of the rest of the batch.

### Phase 4: Report

After all tickets have been processed, summarize results to the conversation:

```
## /pull-tickets Summary

**Processed:** N tickets
**Succeeded:** M (PRs created)
**Rejected:** K (returned to source)
**Skipped:** J (already in progress)

### PRs Created
- ENG-19: Add PDF export for compliance reports -- PR #42
- ENG-22: Fix timezone display on dashboard -- PR #43

### Rejected to Source
- ENG-20: Add notes data model -- missing: data model specifics, access control
- ENG-24: Update auth middleware -- conflict with ENG-23

### Skipped
- ENG-25: Already in progress from previous cycle
```

---

## Triage-Only Mode (--triage-only)

When invoked with `--triage-only`, the skill performs ALL analysis (Phases 0-2)
but DOES NOT build anything. Instead of Phase 3 (Process Each Ticket), it runs
a triage pass that reorganizes the Linear board.

### Triage Phase T1: Complexity Scoring

For each eligible ticket, using the codebase research from Phase 2:

1. Estimate the number of leaf tasks this ticket would produce after recursive
   decomposition. Use the same scoring heuristic as `/build` Step 4:
   - Count affected files, acceptance criteria, and distinct modules
   - Score 1-3 (S: simple, 1-3 tasks), 4-7 (M: moderate, 4-7 tasks),
     8-15 (L: large, 8-15 tasks), 16+ (XL: epic, needs decomposition)
2. Call `create_comment` on each ticket with the analysis:

   "**Triage Analysis**

   **Estimated size:** [S/M/L/XL]
   **Affected areas:** [list of modules/files/endpoints]
   **Estimated subtasks:** ~[N]

   [If XL:] This ticket is large enough that I'd recommend breaking it into
   smaller tickets before building. I can create sub-tickets for you if you
   move this to Todo without the --triage-only flag."

### Triage Phase T2: Dependency Mapping

For each pair of tickets where a dependency was detected in Phase 2:

1. Call `create_comment` on the dependent ticket:

   "**Dependency detected:** This ticket depends on [{blocker-id}]: {blocker title}.

   **Reason:** [e.g., 'Both tickets touch the vendor API endpoints, and this
   ticket requires the data model changes from the other ticket to be in place.']

   **Recommendation:** Build {blocker-id} first."

2. Call `create_comment` on the blocker ticket (if it doesn't already have one):

   "**Blocks:** [{dependent-id}]: {dependent title}. Consider prioritizing
   this ticket — other work is waiting on it."

### Triage Phase T3: Epic Decomposition

For any ticket scored as XL (16+ estimated leaf tasks):

1. Identify the natural decomposition boundaries (modules, layers, phases)
2. Call `create_issue` for each sub-scope, linked to the parent:
   - Title: "[Parent-ID] — [sub-scope description]"
   - Description: The subset of requirements for this sub-scope
   - Set parent issue via the API if supported, otherwise reference in description
3. Call `create_comment` on the parent ticket:

   "**This is an epic-sized ticket.** I've broken it into [N] smaller tickets
   that can be built and verified independently:

   - [SUB-1-ID]: [title]
   - [SUB-2-ID]: [title]
   - [SUB-3-ID]: [title]
   ...

   Please review these sub-tickets and move the ones you'd like built to Todo.
   Building them separately will be faster and produce better results than
   attempting the entire scope at once."

4. Do NOT move the parent out of "Todo" — leave the SME in control of what
   gets built and when.

### Triage Phase T4: Summary

Report the triage results to the conversation:

```
## Triage Summary

**Tickets analyzed:** N

### Size Distribution
  S (1-3 tasks):   [list]
  M (4-7 tasks):   [list]
  L (8-15 tasks):  [list]
  XL (16+ tasks):  [list] — sub-tickets created

### Dependencies Detected
  - ENG-20 depends on ENG-19 (shared vendor API)
  - ENG-21 depends on ENG-20 (notes model)

### Conflicts
  - ENG-23 vs ENG-24 (auth middleware — rejected both)

### Epics Decomposed
  - ENG-25 → ENG-26, ENG-27, ENG-28 (3 sub-tickets created)

### Recommended Build Order
  1. ENG-19 (blocks 1 ticket, size S)
  2. ENG-22 (independent, size S)
  3. ENG-20 (depends on ENG-19, size M)
  4. ENG-21 (depends on ENG-20, size M)

No tickets were built. Board has been updated with analysis.
To build: move desired tickets to Todo and run /pull-tickets (without --triage-only).
```

---

## Scope Gate (BR-010)

During normal (non-triage) processing, if Phase 3c (PRD generation) and
preliminary decomposition reveal that a ticket would produce more than 15 leaf
tasks (DEEP mode / XL size):

1. Do NOT proceed with `/build`
2. Run the same epic decomposition as Triage Phase T3:
   - Create sub-issues in Linear linked to the parent
   - Comment on the parent with the breakdown
3. Call `update_issue` to move the parent to "Needs Clarification"
4. Call `create_comment`:

   "This ticket covers a lot of ground! I've broken it into [N] smaller
   tickets that I can build independently:

   - [SUB-1-ID]: [title]
   - [SUB-2-ID]: [title]
   ...

   Please review the sub-tickets. Move the ones you'd like built to Todo,
   and I'll pick them up on the next cycle. Building them separately will be
   faster and produce higher-quality results."

5. Continue to the next ticket in the batch

This gate prevents the system from attempting massive builds that are more
likely to fail or produce low-quality output. The decomposition is a SERVICE
to the SME — it does the work of breaking down an epic that they would have
had to do themselves.

---

## Constraints

These are non-negotiable. Violating any constraint is a pipeline failure.

- **NEVER hardcode Linear status UUIDs.** Always resolve via `get_status_map` at
  the start of each invocation. UUIDs change between workspaces.

- **NEVER include file paths, stack traces, class names, function signatures, or
  technical jargon in SME-facing comments.** The rejection channel targets domain
  experts, not engineers. Write for the person who filed the ticket.

- **NEVER swallow errors.** Every failure is either rejected to source (if the SME
  can act on it) or logged for engineering review (if they cannot). Silent failures
  are forbidden.

- **NEVER skip /build governance gates.** Every ticket passes through the identical
  pipeline a human-initiated `/build` would. No shortcuts for auto-generated PRDs.
  No special cases. No priority overrides.

- **NEVER process tickets if the MCP rejection channel is unavailable.** If you
  cannot reject, you cannot process. The bidirectional feedback loop is the product.

- **Concurrency limit default: 1.** Configurable via `--concurrency N` argument.
  Two tickets touching overlapping files MUST be sequenced regardless of the
  concurrency setting (file-set isolation rule).

- **Sanitize ticket identifiers.** Before using a ticket identifier (e.g., "ENG-19")
  in directory names or file paths, strip all characters except alphanumeric and
  hyphen. This prevents path traversal or shell injection from crafted ticket IDs.

- **Snapshot ticket content at pull time.** Mid-processing changes in Linear are
  ignored until the next cycle (Edge Case 4). Do not re-fetch ticket details
  during build.

- **One failure, one ticket.** A failure on ticket A must not block, skip, or
  affect processing of tickets B, C, etc. (BR-009).

---

## Edge Case Reference

| # | Scenario | Handling |
|---|----------|----------|
| 1 | No description | Reject with template prompt, move to Needs Clarification |
| 2 | References nonexistent code | Note in PRD Technical Constraints, let DoR decide |
| 3 | Conflicting tickets | Reject both, ask SMEs to coordinate |
| 4 | Ticket modified mid-processing | Ignore -- snapshot at pull time |
| 5 | MCP unreachable | Abort entire cycle immediately |
| 6 | Cron overlap | Skip new cycle, log that previous is running |
| 7 | Re-submitted without changes | Process again -- no blacklisting by design |
| 8 | Attachment-dependent description | Reject, ask SME to write details in ticket body |
| 9 | Repeated PRD-to-code failure | System issue -- do not blame SME, log for eng review |
| 10 | All tickets interdependent | Process sequentially, effective concurrency becomes 1 |
| 11 | Epic-sized ticket (>15 leaf tasks) | Create sub-issues in Linear, do not build parent (BR-010) |
| 12 | Triage mode with 0 eligible tickets | Report "No eligible tickets" and exit cleanly |
