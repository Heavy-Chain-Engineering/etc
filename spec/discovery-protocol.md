# Discovery Protocol

**Status:** Design draft
**Date:** 2026-04-13
**Owner:** ETC harness

## Purpose

The discovery protocol is the mechanism by which an agent that starts with a narrow default context projection can request additional context mid-task when it discovers the default is insufficient. It is the **soft POLA** counterpart to the strict `forbids` model: agents aren't walled off from the repository, but every widening of their scope is a deliberate, logged, justifiable act.

Without this protocol, the closed-loop guarantee has a hole: an agent whose default projection doesn't contain the file it needs has only two options — **fabricate** or **escalate to a human**. Fabrication breaks the "incapable of wrong" goal. Escalation-to-human breaks the autonomy goal. Discovery gives the agent a third option: *ask the system for the missing piece*, with a justification that gets logged.

## Design principles

1. **Agents start narrow.** Default projection from the role manifest is the starting point, not a ceiling.
2. **Every widening is structured.** Free-form "I need more context" is not allowed. Requests conform to a typed schema and match a pattern declared in the role manifest's `allowed_requests`.
3. **Every request is logged.** The log is the substrate for manifest evolution — patterns in the log drive updates to `default_consumes`.
4. **Parents grant by default; policies grant deterministic cases.** The role manifest can declare `auto_grant: true` for low-risk request kinds (e.g., ADR lookups); everything else requires a parent-agent judgment call.
5. **Denied requests escalate.** A denied request doesn't silently fail — it becomes an escalation of kind `discovery_denied`, which propagates upward until someone can answer or a human is asked.

## Request schema

Emitted by a child agent when its default projection is insufficient. One request, one narrowly-scoped ask. No batching in the first version.

```yaml
discovery_request:
  # Who/what is asking (populated by the runtime, not the agent)
  task_id:           string       # matches the active .etc_sdlc task file
  role:              string       # e.g. "backend-dev"
  bounded_context:   string       # e.g. "compliance-execution"
  timestamp:         iso-8601

  # What is being requested (populated by the agent)
  kind:              string       # MUST match an entry in the role manifest's allowed_requests
  target:            string       # file path or glob matching the pattern for that kind
  justification:     string       # 1-2 sentences: why the default projection is insufficient
  blocking:          boolean      # true = task cannot proceed without this
```

**Validation rules:**
- `kind` must exist in the role manifest's `discovery.allowed_requests`.
- `target` must match the `pattern` declared for that kind (glob or exact path).
- `justification` must be non-empty. Empty or generic justifications ("I need more context") are rejected by the runtime, not the parent — this is a cheap filter for lazy requests.

## Response schema

Returned to the requesting agent. Exactly one of three decisions.

```yaml
discovery_response:
  request_id:        string       # matches the emitted request
  decision:          enum         # granted | denied | escalate_instead
  timestamp:         iso-8601
  decided_by:        string       # "policy:auto_grant" | "agent:sem" | "agent:architect" | "human"

  # On decision=granted
  granted_files:     [string]     # absolute or repo-relative paths now in the projection
  expires_with:     string       # "task" — granted files revert when the task ends

  # On decision=denied
  denied_reason:     string       # human-readable
  alternative:       string       # optional: "try asking for X instead" or "this task is mis-scoped"

  # On decision=escalate_instead
  escalation_kind:   enum         # scope | architectural | technical
  escalation_target: string       # "sem" | "architect" | "human"
  rationale:         string       # why this is actually a higher-level question
```

**`escalate_instead` is the interesting third option:** the reviewer (policy or parent agent) determines that this isn't a context gap — it's a scoping or architectural question that shouldn't be answered by widening the projection. The request is *rewritten* as an escalation, which travels upward through the normal escalation channels.

## Resolution flow

```
┌─────────────────────────────────────────────────────────────┐
│  1. Agent hits gap while executing task                     │
│     "I don't have PRD-02 but the task references it"        │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  2. Agent emits discovery_request                            │
│     kind=additional_prd, target=docs/prds/PRD-02-*.md,      │
│     justification="task mentions the relationship-           │
│     management context boundary"                           │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  3. Runtime validates request against role manifest         │
│     - kind in allowed_requests?                              │
│     - target matches pattern?                                │
│     - justification non-empty?                               │
│     If invalid → rejected, agent must reformulate           │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  4. Policy check (cheap, deterministic)                      │
│     If allowed_requests[kind].auto_grant == true:           │
│       decision=granted, decided_by=policy:auto_grant        │
│     Otherwise → punt to parent agent                         │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  5. Parent agent makes judgment call                         │
│     Parent sees: the request + the justification + their    │
│     own task context. Decides: granted / denied /           │
│     escalate_instead.                                       │
│     The parent's reasoning itself is logged.                │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  6. Response returned to requesting agent                    │
│     granted  → files added to projection, agent continues  │
│     denied   → if blocking=true, agent escalates upward    │
│     escalate → agent's task is rewritten as escalation     │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  7. Log entry written to .etc_sdlc/discovery.log            │
│     Full request + response, JSONL                          │
└─────────────────────────────────────────────────────────────┘
```

## Log format & location

**Location:** `.etc_sdlc/discovery.log` (per-project, JSONL, append-only)

**Rationale for per-project:** patterns in discovery requests are highly context-specific. A "backend-dev needs R13 workflow research" pattern is meaningful in VenLink and meaningless everywhere else. Global logs would dilute the signal.

**Entry format (one JSON object per line):**

```json
{
  "ts": "2026-04-13T14:22:03Z",
  "task_id": "PRD-04-level-1-evaluator",
  "role": "backend-dev",
  "bounded_context": "compliance-execution",
  "request": {
    "kind": "cross_context_research",
    "target": "docs/sources/research/R13-workflow-engine-architecture.md",
    "justification": "compliance execution triggers workflows and I need to understand how the workflow engine consumes event codes to match my events correctly",
    "blocking": true
  },
  "response": {
    "decision": "granted",
    "decided_by": "agent:sem",
    "granted_files": ["docs/sources/research/R13-workflow-engine-architecture.md"],
    "expires_with": "task"
  }
}
```

**Retention:** append-only, no rotation. The log is telemetry, not state — it can be truncated or archived without affecting correctness. Human-driven periodic review (weekly or per-phase) turns the log into manifest updates.

## How the log drives manifest evolution

The log is the single data source for answering "is the default projection for role X too narrow?" Three evolution paths:

1. **Frequent grants → add to default_consumes.**
   If `backend-dev` tasks on `compliance-execution` request `R13-workflow-engine-architecture.md` in 40% of tasks, and the request is almost always granted, it belongs in the default. Add it to `roles/backend-dev.yaml`, filtered by bounded context.

2. **Frequent denies → split the role or the context.**
   If a role keeps asking for things it doesn't get, either the role is doing too many kinds of work (split it — `backend-dev-payments` vs `backend-dev-core`), or the bounded context is too big and needs decomposition.

3. **Frequent escalate_instead → fix task authoring.**
   If requests are routinely being rewritten as escalations, the tasks the agent is being given are mis-scoped. The fix is upstream in task decomposition, not in the manifest.

**This is the feedback loop that makes "incapable of wrong" achievable over time.** Initial manifests will be underspecified. The log makes the under-specification visible and quantifies it. Manifest updates become data-driven, not taste-driven.

## Worked example

**Setup:** A `backend-dev` agent is assigned the task "Implement Level 1 individual requirement evaluator in the compliance execution cascade." Its default projection comes from the VenLink `backend-dev.yaml` manifest filtered by `bounded_context: compliance-execution`.

**Mid-task discovery:** The agent is writing the evaluator and realizes Level 1 results need to be published as domain events for downstream workflow triggering — but its projection doesn't include `R13-workflow-engine-architecture.md`, which documents the trigger-code contract.

**Request emitted:**
```json
{
  "kind": "cross_context_research",
  "target": "docs/sources/research/R13-workflow-engine-architecture.md",
  "justification": "Level 1 results must emit events consumed by the workflow engine; I need to know the trigger_event_code format contract",
  "blocking": true
}
```

**Runtime validates:** `kind` exists in the manifest's `allowed_requests`, pattern matches, justification is specific. Forwarded to the policy check.

**Policy check:** `cross_context_research` has `auto_grant: false`. Punted to parent (the `sem` agent that dispatched this task).

**Parent (sem) decides:** The justification is legitimate — the evaluator does need to produce correctly-formatted events. Grant.

**Response:**
```json
{
  "decision": "granted",
  "decided_by": "agent:sem",
  "granted_files": ["docs/sources/research/R13-workflow-engine-architecture.md"],
  "expires_with": "task"
}
```

**Agent continues.** The granted file is added to the projection for the remainder of this task. When the task ends, the grant expires — the next task starts from the default projection again.

**Log entry written.** A week later, when reviewing the discovery log, we see 8 out of 10 `compliance-execution` tasks requested `R13`. Update `roles/backend-dev.yaml` to include it in the default for this context.

## Open questions

1. **Granularity of grant expiration.** Does a grant last for the whole task, or just the current agent invocation? Default: whole task. Alternative: per-tool-call, forcing the agent to re-justify for each use — probably too chatty.

2. **Can a child agent emit discovery requests, or only the leaf agent?** Probably any agent at any level. A `sem` agent might discover it needs an ADR it didn't consume by default. Manifests for each role declare their own `allowed_requests`.

3. **What about read-only context vs. modification scope?** The discovery protocol widens *read* projection. It does NOT expand write access — an agent cannot request permission to edit a file outside its task's `files_in_scope`. That's a scope change and bubbles up as an escalation of kind `scope`, not a discovery request.

4. **How is the parent agent consulted mechanically?** Two options: (a) the discovery request is surfaced in the parent agent's own context (expensive — parent is stateful during child execution), or (b) a sub-agent-style callback where the parent is re-invoked with just the request. (b) is cleaner but requires the parent's decision-making logic to be deterministic-enough to serialize.

5. **Should grants be transitive?** If agent A grants agent B access to file X, and agent B spawns agent C, does C inherit access to X? Default: no — each agent gets its own default projection. Transitive grants would be confusing to audit. Agent C, if it needs X, emits its own request.

6. **Log write path in a concurrent agent world.** The log is append-only JSONL — concurrent writes need either file locking or per-agent log files that merge later. First version: single log, `flock` on append. Revisit if contention shows up.

## Required changes to ETC

To implement this protocol:

1. **Runtime library:** `etc.discovery.emit_request(kind, target, justification, blocking) -> response`
   - Validates against active role manifest
   - Consults policy (auto_grant checks)
   - Routes to parent agent if needed
   - Writes log entry
   - Returns the response or raises on invalid requests

2. **Role manifest loader:** already partially built; needs to expose `discovery.allowed_requests` to the runtime.

3. **Log location convention:** `.etc_sdlc/discovery.log`, created by `/init-project` alongside other SDLC state.

4. **Analysis skill:** `/analyze-discovery-log` — summarizes patterns from the log and proposes manifest updates. Low priority; can be a human-driven SQL-against-JSONL task initially.

5. **Escalation protocol:** the `escalate_instead` response path depends on the escalation protocol existing — currently designed but not yet implemented. Discovery and escalation are sibling primitives, and both are needed for the closed-loop guarantee.

## What this replaces

- **Strict `forbids` lists in role manifests.** Already removed from `backend-dev.yaml`; other role manifests should follow when they are written.
- **Free-form "I need more context" escalations.** Those become typed discovery requests or escalations, not ambient conversation.
- **Silent fabrication when the default projection is underspecified.** The agent's only way to act beyond the default is now a logged request — so fabrication either shows up as a denied request in the log (visible), or as a violation of the "cite your sources" rule (caught by a different hook).

## Status and next steps

This document is a **design draft**. Before implementation, validate:
- [ ] Does the worked example cover the common case? Get a second read.
- [ ] Is the three-decision response schema (`granted | denied | escalate_instead`) sufficient, or do we need `partial`?
- [ ] Where does the policy engine live — embedded in the runtime or a separate `discovery-policy.yaml` file?

After validation:
- Prototype the runtime library with a mock parent-agent callback
- Wire it into one VenLink task as an end-to-end test
- Write `/analyze-discovery-log` as a follow-up skill
