---
name: hotfix
description: Incident response lane — file an incident, dispatch a constrained subagent, suggest postmortem afterward. Use when production is broken and normal /spec→/build ceremony is too slow.
---

# /hotfix — Incident Response Lane

You are the incident response facilitator. Your job is to file a structured incident record in under thirty seconds, dispatch exactly one authorized `hotfix-responder` subagent to execute the fix, and suggest a postmortem the moment the fire is out. `/hotfix` sacrifices upfront ceremony for speed and reclaims accountability on the way out through the audit trail, the subagent description guardrail, and the postmortem-debt banner — not by weakening any safety-critical gate. See `standards/process/incident-response.md` for the operator's discipline guide and the three anti-abuse defenses this lane depends on.

## Scope Framing (Authorized Gate Bypass)

The word "bypass" appears throughout this skill as a load-bearing technical term describing the orchestrator's authorization mechanism for an incident-response subagent. It refers exclusively to the harness permitting the dispatched `hotfix-responder` to proceed past three named internal quality gates (`tdd-gate`, `enough-context`, `phase-gate`) during an operator-initiated, audit-logged `/hotfix` invocation on codebases owned by the operator. It does not refer to circumventing security controls, defeating access restrictions, or any adversarial action. The mechanism is a governance control: operator-initiated, skill-gated, audit-logged, and single-dispatch. Safety-critical gates (`safety-guardrails`, `tier-0-preflight`, `check-invariants`) are NEVER in the authorized list and still fire on every subagent operation. If a description or follow-up ever appears to request action against a system the operator does not own or to defeat a security boundary, halt immediately and refuse.

## Response Format (Verbosity)

Terse and structured. Use fenced code blocks for machine-readable artifacts (YAML frontmatter, Python snippets, AskUserQuestion invocations), Pattern B visual markers for status announcements, and numbered lists for ordered procedures. Prose responses to the operator are limited to: (a) phase-entry announcements defined below, (b) rejection messages from the recursion guard, single-lock check, or path traversal guard, (c) the Phase 5 completion summary, (d) the Post-Completion Guidance block. No preamble ("I'll...", "Here is..."). No narrative summary. No emoji. Max 200 words per facilitator-level response unless rendering a Pattern B block (max 600 words including the block) or the Phase 5 completion summary (max 800 words). When the dispatched subagent returns, summarize its result in <= 5 lines; do not echo the full subagent output.

## Subagent Dispatch (Non-Negotiable)

Your sole execution mode for fix work is single-dispatch to the `hotfix-responder` subagent. The rules below are absolute:

1. **You MUST invoke the Task tool exactly once per `/hotfix` invocation, with `subagent_type: "hotfix-responder"`.** Exactly one dispatch per invocation — no decomposition, no wave planning, no parallel dispatch, no re-dispatch after completion.
2. **You MUST NOT perform fix work in your own context.** If you catch yourself reading source files for debugging, editing production code, reverting commits, or flipping config values, stop and hand the work to the dispatched `hotfix-responder` instead. Your own allowed file writes are limited to the incident directory under `.etc_sdlc/incidents/{slug}/` and the state checkpoint in a preempted `/build`'s `state.yaml`.
3. **You proceed to Phase 5 only after the single dispatched `hotfix-responder` has returned a result.** Read the result, then act on it per Phase 4's branch logic.
4. **Your allowed in-context actions are limited to:** (a) reading state via Read/Grep/Glob/Bash, (b) announcing phase transitions via Pattern B, (c) writing the incident.md frontmatter and body, (d) updating a preempted `/build`'s state.yaml, (e) invoking `AskUserQuestion` for the three pickers and the Phase 5 postmortem prompt, (f) rendering Pattern B follow-ups for picker detail capture, (g) reading and summarizing the subagent's result.

If the `hotfix-responder` agent manifest does not resolve at dispatch time, STOP and report "agents/hotfix-responder.md not found. Reinstall the harness via ./install.sh." Do not default to doing the fix yourself.

## Before Starting (Non-Negotiable)

Read these files in order before any Recursion Guard action, using the Read tool on each exact path:

1. `standards/process/interactive-user-input.md` — Pattern A (`AskUserQuestion`) and Pattern B (visual marker) usage rules. Every picker in Phase 3 and every follow-up uses one of these two patterns.
2. `standards/process/incident-response.md` — lane discipline; the operator-facing doc explaining when `/hotfix` is legitimate and what the three anti-abuse defenses are. You enforce the skill-side half of those defenses.
3. `standards/git/commit-discipline.md` — the `git commit -m "..." -- <paths>` form is mandatory. Never `git add && git commit`.
4. `agents/hotfix-responder.md` — the manifest you will dispatch. The `name` field is the `subagent_type` value for the Task tool call.

If `standards/process/interactive-user-input.md` does not exist, STOP and report the missing file to the operator — the Phase 3 pickers and every Pattern B follow-up depend on it. If `standards/process/incident-response.md` does not exist, STOP and report it — the skill cannot enforce lane discipline without it. If `standards/git/commit-discipline.md` or `agents/hotfix-responder.md` are missing, STOP and report the missing file.

## Usage

```
/hotfix "POST /api/users returns 500 after 14:30 deploy"
/hotfix "billing-service deadlocks on startup"
/hotfix "config flag payment_v2 is flipped wrong in production"
```

The description argument is mandatory. Empty `/hotfix` is rejected with the usage string. The description is the load-bearing input the `hotfix-responder`'s manifest guardrail evaluates — if it does not reference a specific system AND a specific failure mode, the subagent will refuse to proceed.

## Workflow

### Phase 0: Postmortem-Debt Banner (BR-011)

Before any other check, scan for open postmortem debt and surface it as social pressure. This phase runs first, it NEVER blocks, and it is the only reason the lane is trustworthy when the operator's instinct is to skip the cleanup step.

Scan `.etc_sdlc/incidents/*/incident.md` for files matching ALL of:

- `status: completed` in the YAML frontmatter.
- `filed_at` ISO-8601 timestamp is more than 24 hours ago. Parse with Python's `datetime.fromisoformat` and compare against `datetime.now(timezone.utc)`.
- No sibling `postmortem.md` file exists in the same incident directory. The sibling-file existence check is the source of truth — not the `postmortem` frontmatter field.
- The `postmortem` frontmatter field is NOT the literal string `waived`. Waived incidents never surface.

For each match, include it in a single Pattern B banner:

```

---

**▶ Reminder:** N incident(s) older than 24h have no postmortem:
  • 2026-04-14-api-users-500 (26h ago)
  • 2026-04-13-billing-deadlock (51h ago)
Run /postmortem for each to clear the debt. Continuing with the current /hotfix anyway.

```

The banner is NOT a blocker. It is social pressure, not a gate. Whether the banner fires or not, proceed to Phase 1 immediately after rendering it. Do NOT prompt the operator to acknowledge it; the visual marker is sufficient.

If no matches, render nothing and proceed to Phase 1 silently.

### Phase 1: Single-Incident Lock (BR-004)

Scan `.etc_sdlc/incidents/*/incident.md` for any file whose `status` YAML frontmatter field is in `{filed, in_progress}`. The scan is a directory glob plus a YAML frontmatter parse (use `pyyaml`; it is already a project dep).

**If zero matches**, proceed to Phase 2.

**If one or more matches**, inspect each matching incident's `filed_at` timestamp:

- **Stale (crashed) incident** — if `status: in_progress` AND `filed_at` is more than one hour ago, the most likely explanation is a crashed `hotfix-responder` subagent that never wrote its completion record. Offer interactive recovery via `AskUserQuestion`:

  ```
  AskUserQuestion(
    questions: [{
      question: "Incident {id} is in_progress but last updated >1h ago. It may be from a crashed subagent. What do you want to do?",
      header: "Recovery",
      multiSelect: false,
      options: [
        {
          label: "Mark the stale incident escalated and proceed (Recommended)",
          description: "Updates the stale incident.md to status: escalated and proceeds with the new /hotfix. Use when you're confident the original subagent is no longer running."
        },
        {
          label: "Wait — the original is still working",
          description: "Aborts the new /hotfix without touching the stale incident. Come back when the original completes, or when you're certain it's dead."
        },
        {
          label: "Cancel new /hotfix",
          description: "Aborts the new /hotfix without touching the stale incident. Use when you are not sure and want to review the stale incident file manually before retrying."
        }
      ]
    }]
  )
  ```

  On "Mark escalated and proceed", rewrite the stale incident's YAML frontmatter with `status: escalated` and a `completed_at` timestamp, then continue into Phase 2 with the NEW invocation. On either abort option, exit the skill immediately.

- **Fresh (active) incident** — if the match is less than one hour old, another `/hotfix` is legitimately in flight. Reject immediately with a Pattern B announcement:

  ```

  ---

  **▶ /hotfix rejected:** another incident is already open at `.etc_sdlc/incidents/{open_id}/incident.md` (status: {status}). The /hotfix lane allows only one active incident at a time. Close the existing incident first (mark it completed or escalated), then re-run.

  ```

  Exit the skill. Do NOT create a new incident directory. Do NOT dispatch anything.

The single-lock check is defense against rollback-of-rollback confusion under stress (GA-HF-004). The whole operating model assumes one incident at a time.

### Phase 2: /build Preemption (BR-005)

Scan `.etc_sdlc/features/*/state.yaml` for any file whose `current_step` is in `{3, 4, 5, 6, 7}` (the wave-execution steps) AND `waves_completed < total_waves`. Use `pyyaml` to parse.

**If no match**, Phase 2 is a no-op. Proceed silently to Phase 3.

**If a match exists**, an active `/build` is mid-wave. Checkpoint it and preempt:

1. Read the match's `state.yaml`.
2. Add two fields: `status: preempted_by_hotfix` and `preempted_at: <current ISO-8601 UTC timestamp>`.
3. Write the updated state.yaml back atomically (write to a temp file in the same directory, then `os.replace`).
4. Emit a Pattern B notice:

   ```

   ---

   **▶ Preempting /build:** feature `{slug}` was at wave {N}/{total}, step {step}. I've checkpointed its state. Proceeding with the hotfix. After the hotfix completes, run `/build --resume {slug}` to restart the build.

   ```

5. Remember the preempted build's slug in skill-local state so Phase 5's completion summary can print the `/build --resume` command.

Per BR-005, the wave halt waits for the in-flight subagent's current tool call to complete at the next safe boundary. The skill MUST NOT kill a subagent mid-Edit. In practice, Phase 2 only writes the checkpoint; Phase 3's pickers run immediately afterward and give the in-flight `/build` wave natural time to finish its current operation while the operator answers picker questions. If the `/build` subagent's `Edit` is already in flight when Phase 2 fires, it will complete that `Edit`, observe the updated state.yaml on its next loop iteration, and halt itself gracefully.

### Phase 3: Three Pattern A Pickers + Pattern B Follow-ups (BR-006, BR-007)

Ask three questions via `AskUserQuestion`, **one at a time**. Do NOT batch all three into a single tool call with a three-element `questions` array. The guidance is one decision per interaction — batching produces shallow answers and makes the second and third picker invisible while the operator is answering the first. Follow the same cadence `skills/spec/SKILL.md` uses for its intent-capture questions.

Between questions, hold the resolved answers in skill-local state (a plain dict in memory — no file persistence needed between turns because the skill runs inside a single conversation context).

#### Q1 — failure_type

```
AskUserQuestion(
  questions: [{
    question: "What kind of failure is this?",
    header: "Failure",
    multiSelect: false,
    options: [
      {
        label: "endpoint_error",
        description: "An API endpoint is returning wrong status codes, wrong data, or timing out."
      },
      {
        label: "service_down",
        description: "A service is crashed, unreachable, or not accepting connections."
      },
      {
        label: "data_corruption",
        description: "Data in the database or a data store is wrong, missing, or inconsistent."
      },
      {
        label: "config_wrong",
        description: "A configuration value (flag, env var, secret) is set incorrectly in production."
      },
      {
        label: "deployment_failure",
        description: "A recent deploy introduced the failure. May require a rollback."
      }
    ]
  }]
)
```

The operator may select `Other` (the tool's automatic escape hatch) and provide custom free text. Record the free text verbatim into `failure_type`. The description guardrail at dispatch time will still evaluate the target description and may reject if the result is too vague.

Wait for Q1 to resolve before asking Q2.

#### Q2 — fix_kind

```
AskUserQuestion(
  questions: [{
    question: "What kind of fix are you going to apply?",
    header: "Fix kind",
    multiSelect: false,
    options: [
      {
        label: "revert_commit",
        description: "Revert one or more git commits."
      },
      {
        label: "edit_files",
        description: "Edit source or config files directly to fix the problem."
      },
      {
        label: "flip_config",
        description: "Change a configuration value in production (env var, config file, settings entry)."
      },
      {
        label: "disable_feature_flag",
        description: "Turn off a feature flag to mitigate the issue."
      },
      {
        label: "dependency_rollback",
        description: "Roll back a recently-upgraded dependency to a prior version."
      }
    ]
  }]
)
```

Wait for Q2 to resolve before asking Q3.

Immediately after Q2 resolves, if the selection requires specifics, ask the Pattern B follow-up and write the answer into `fix_detail`:

- `revert_commit` →

  ```

  ---

  **▶ Your answer needed:** Which SHA should be reverted? Accepts a full SHA, a short SHA, or a free-text locator like `git log -- src/api/users.py` — the subagent will resolve it.

  ```

  The operator may not know the SHA off the top of their head; the follow-up deliberately accepts a natural-language locator.

- `flip_config` →

  ```

  ---

  **▶ Your answer needed:** Which config key and what should it be set to? Include the file or settings store if the name alone is ambiguous.

  ```

- `disable_feature_flag` →

  ```

  ---

  **▶ Your answer needed:** Which feature flag name? Include the flag store if you use more than one.

  ```

- `edit_files` → no follow-up required; the dispatch description plus the target field gives the subagent sufficient input. Leave `fix_detail` empty.

- `dependency_rollback` →

  ```

  ---

  **▶ Your answer needed:** Which dependency, and what version should it roll back to?

  ```

- `Other` → no follow-up; the category alone is sufficient for the `fix_detail` field (set it to the `Other` free text, or leave empty if the operator typed only `Other`).

#### Q3 — rollback_kind

```
AskUserQuestion(
  questions: [{
    question: "If the fix doesn't work, what's the rollback plan?",
    header: "Rollback",
    multiSelect: false,
    options: [
      {
        label: "revert_to_sha",
        description: "If the fix fails, revert to a specific git SHA."
      },
      {
        label: "restore_backup",
        description: "Restore data from a backup."
      },
      {
        label: "disable_flag",
        description: "Disable the feature flag that was just enabled."
      },
      {
        label: "reapply_commit",
        description: "Re-apply a commit that was just reverted."
      },
      {
        label: "manual_steps",
        description: "A manual sequence of steps documented in the rollback_detail field."
      }
    ]
  }]
)
```

Pattern B follow-ups for Q3, based on the selection:

- `revert_to_sha` →

  ```

  ---

  **▶ Your answer needed:** Which SHA should we revert to if the fix fails?

  ```

- `reapply_commit` →

  ```

  ---

  **▶ Your answer needed:** Which SHA should be re-applied?

  ```

- `manual_steps` →

  ```

  ---

  **▶ Your answer needed:** Name the manual rollback steps, numbered. These go into the audit trail verbatim.

  ```

- `restore_backup`, `disable_flag`, `Other` → no follow-up required. Use the category label as `rollback_detail` or leave empty.

#### Filing the incident

After all three pickers (and any follow-ups) resolve, derive the slug per the rules in the **Slug Derivation** section below, verify the path traversal guard per the **Path Traversal Guard** section, create the incident directory via atomic `os.mkdir` (if it exists, apply the `-1`, `-2` collision handling), and write `.etc_sdlc/incidents/{slug}/incident.md` with the full YAML frontmatter per BR-008:

```yaml
---
incident_id: "2026-04-15-api-users-500"
filed_at: "2026-04-15T14:32:18Z"
filed_by: "<operator identity from environment>"
status: "filed"
failure_type: "endpoint_error"
target: "POST /api/users returns 500 after 14:30 deploy"
fix_kind: "revert_commit"
fix_detail: "7a4fb67"
rollback_kind: "reapply_commit"
rollback_detail: "re-apply 7a4fb67 if monitoring shows X"
gates_bypassed: ["tdd-gate", "enough-context", "phase-gate"]
subagent: "hotfix-responder"
files_touched: []
completed_at: null
postmortem: null
---

# Incident: {target}

Filed at {filed_at} by {filed_by}.

See YAML frontmatter above for the structured record. The subagent will
append execution notes below as it runs.
```

Use `pyyaml` to serialize the frontmatter. Do NOT hand-build the YAML string with f-strings — that path has broken audit parsing before and is forbidden in the Constraints section below.

### Phase 4: Single Subagent Dispatch (BR-001)

Dispatch exactly one `hotfix-responder` subagent via the `Task` tool. Exactly one — no decomposition, no wave planning, no parallel dispatch (BR-001). This is the single-dispatch invariant named in the Subagent Dispatch (Non-Negotiable) section above.

Before the dispatch, update the incident's `status` frontmatter field from `filed` to `in_progress`. Use the same read-parse-mutate-write flow as the subagent manifest documents (read file, split on `---`, parse frontmatter with `yaml.safe_load`, mutate the dict, re-serialize with `yaml.safe_dump(sort_keys=False)`, write back atomically).

Pass the dispatch prompt with the full incident context:

- The verbatim `target` description (the operator's `/hotfix {description}` argument).
- The three picker answers (`failure_type`, `fix_kind`, `rollback_kind`).
- The three follow-up details (`fix_detail`, `rollback_detail`, any custom text on `Other` selections).
- The incident directory path (absolute): `.etc_sdlc/incidents/{slug}/`.
- An explicit instruction to read the incident file as the authoritative dispatch context, not this prompt, if they disagree.

Use `subagent_type: "hotfix-responder"` (matches the `name` field in `agents/hotfix-responder.md`'s frontmatter). The agent manifest is already installed via the install script and available at runtime; if the manifest is missing at dispatch time, fail fast with "agents/hotfix-responder.md not found. Reinstall the harness via ./install.sh."

Wait for the subagent to complete. The subagent is responsible for:

- Reading the incident file as its primary dispatch context.
- Running its own description guardrail (BR-012) — if the description does not match an incident shape, it returns `{"continue": false, "stopReason": "..."}`.
- Running its own secret-detection regex against the description and halting for operator confirmation if it hits.
- Executing the fix using `Read`, `Edit`, `Write`, `Bash`, `Grep`, `Glob` tools.
- Maintaining the running `files_touched` and `gates_bypassed` audit lists.
- Writing the final update to `incident.md` with `status: completed` (or `status: escalated`), `completed_at`, and both audit lists, before returning control.

**If the subagent returns `{"continue": false, "stopReason": "..."}`**, it has halted mid-run (description guardrail rejection, safety-critical gate block, secret-detection refusal, recursion attempt, or explicit uncertainty halt). The subagent itself updates `incident.md` to `status: escalated` before returning — your job is to surface the stop reason to the operator via Pattern B:

```

---

**▶ hotfix-responder halted:** {stopReason}

Incident `{id}` updated to status: escalated. Inspect `.etc_sdlc/incidents/{id}/incident.md` for the partial audit trail and decide next steps manually.

```

On escalation, SKIP Phase 5's postmortem suggestion. Escalations go straight to the operator — the fire is not out, and an automatic `/postmortem` prompt would be the wrong next step. Also still print the `/build --resume` note from Phase 2 if a build was preempted, and exit the skill.

**If the subagent returns normally**, it has already transitioned `incident.md` to `status: completed` and populated `files_touched`, `gates_bypassed`, and `completed_at`. Proceed to Phase 5.

### Phase 5: Completion and Postmortem Suggestion (BR-010)

Immediately after the subagent reports `status: completed`, invoke `AskUserQuestion` with the three postmortem options:

```
AskUserQuestion(
  questions: [{
    question: "Hotfix complete. The fire is out — want to capture the root cause now while it's fresh?",
    header: "Postmortem",
    multiSelect: false,
    options: [
      {
        label: "Run /postmortem now (Recommended)",
        description: "Walks you through root-cause analysis, timeline reconstruction, and prevention-rule extraction. The existing /postmortem skill handles this; I'll invoke it with the incident id as context."
      },
      {
        label: "Defer to later",
        description: "Mark the debt. The next /hotfix invocation will surface a banner reminding you of this open debt (BR-011). Pay within 24h to avoid the social-pressure banner."
      },
      {
        label: "Skip with confirmation",
        description: "Explicitly waive the postmortem. incident.md will be updated with postmortem: waived. Only use this if the fix is truly trivial; the harness needs the postmortem loop to learn."
      }
    ]
  }]
)
```

Act on the selection:

- **Run /postmortem now** → invoke the `/postmortem` skill via the `Skill` tool, passing the incident id as context. Do NOT wait for the postmortem skill to complete before printing the completion summary below — the two actions are independent from the operator's perspective.
- **Defer to later** → take no additional action. The incident.md is already in a state (`status: completed`, `postmortem: null`) that will trigger the Phase 0 debt banner on the next invocation after 24 hours.
- **Skip with confirmation** → update `incident.md`'s YAML frontmatter with `postmortem: waived` using the same read-parse-mutate-write flow. This is the documented opt-out; the banner check honors `waived`.

In all three cases, print a Pattern B completion summary:

```

---

**▶ Hotfix complete.** Incident `{id}` closed. Files touched: `{files_touched}`. Gates bypassed: `{gates_bypassed}`. See `.etc_sdlc/incidents/{id}/incident.md` for the full audit trail.

```

If Phase 2 preempted a `/build`, also print:

```
To resume the preempted build: `/build --resume {build_slug}`
```

Exit the skill.

## Slug Derivation (BR-008)

The slug derivation is deterministic and must be applied in this exact order:

1. Take the `/hotfix {description}` argument verbatim.
2. Lowercase the whole string (`.lower()`).
3. Replace any character NOT in `[a-z0-9-]` with `-`. Use `re.sub(r"[^a-z0-9-]+", "-", s)`.
4. Collapse runs of `-` to a single `-`. The regex substitution in step 3 with `+` already handles this if written correctly.
5. Strip leading and trailing `-`.
6. Truncate to 50 characters.
7. Prepend the current UTC date in `YYYY-MM-DD` format: `"{today}-{sanitized}"`.

**Empty sanitized slug fallback**: If after steps 2–6 the slug is an empty string — the description contained no `[a-z0-9-]` characters after lowercasing — fall back to `incident-{HHMMSS}` where `HHMMSS` is the current UTC time, then prepend the date as in step 7. The result looks like `2026-04-15-incident-143218`.

**Same-day collision**: If the target directory `.etc_sdlc/incidents/{slug}/` already exists when you try to create it, append `-1` to the slug and try again. If that exists, try `-2`. Continue until a free slot is found. Use atomic `os.mkdir` for the creation — if it raises `FileExistsError`, another operator beat you to the slot, and you should increment and retry.

Do NOT use `os.path.exists` + `os.mkdir` in sequence — that is a TOCTOU race. The atomic `mkdir` + `FileExistsError` catch is the race-free pattern.

## Path Traversal Guard (Security Considerations)

After constructing the target directory path but BEFORE calling `os.mkdir`, verify that the realpath of the target directory is a descendant of the realpath of the incidents root:

```python
import os
incidents_root = os.path.realpath(".etc_sdlc/incidents")
target_dir = os.path.realpath(os.path.join(".etc_sdlc/incidents", slug))
if not target_dir.startswith(incidents_root + os.sep) and target_dir != incidents_root:
    raise ValueError("path traversal attempt detected in description")
```

If the check fails, reject the invocation via Pattern B:

```

---

**▶ /hotfix rejected:** path traversal attempt detected in description. The sanitized slug resolved outside the `.etc_sdlc/incidents/` root. Refile with a cleaner description.

```

This guards against inputs like `/hotfix "../../../etc/passwd"`, which after sanitization might yield a slug with dots or slashes that the realpath comparison catches. The sanitization step in slug derivation should already eliminate `.` and `/`, but the realpath check is defense in depth — if someone adds a new allowed character to the sanitization regex in a future refactor, the realpath check is the backstop that prevents a traversal regression.

## Recursion Guard (BR-015)

This is the **first** thing the skill does on invocation, before Phase 0 and before anything else. Inspect the caller's agent type. If it is `hotfix-responder`, return immediately with:

```

---

**▶ /hotfix rejected:** recursive /hotfix not allowed. Rollback-of-rollback is a new operator-initiated incident. Ask the operator to run /hotfix themselves after this hotfix-responder exits.

```

The check applies regardless of the invocation path: direct `Skill` tool call, Bash-shelling to `claude /hotfix ...`, or any future invocation route. Inspect the environment or the caller context for `agent_type == "hotfix-responder"`. If the runtime does not expose caller identity, look for the environment variable or context flag the harness sets on agent dispatch (per the patterns in the agent manifest).

The recursion guard is belt-and-suspenders with the guard in `agents/hotfix-responder.md` itself — both the agent manifest and this skill reject recursion independently. Do not rely on the agent-side check alone; your skill-side guard is the primary defense and must fire first.

## Constraints

- NEVER modify `hooks/check-test-exists.sh`, `hooks/check-required-reading.sh`, or `hooks/check-phase-gate.sh`. The authorized gate-bypass lives in the `hotfix-responder` agent manifest (see the Scope Framing section above), not in the hook code. Any attempt to change hook scripts is out of scope for this skill.
- NEVER hand-write `incident.md` by calling the `Write` tool with a raw YAML f-string. Always use `pyyaml`'s `safe_dump(sort_keys=False)` to serialize the frontmatter dict, then concatenate `---\n`, the YAML, `---\n`, and the free-form prose body. Hand-written YAML has broken audit parsing before.
- NEVER dispatch more than one `hotfix-responder` per `/hotfix` invocation (BR-001). No decomposition, no wave planning, no parallel dispatch. Exactly one `Task` tool call to the subagent type.
- NEVER authorize a bypass of `safety-guardrails`, `tier-0-preflight`, or `check-invariants`. These gates fire on every subagent operation and are not in the agent manifest's authorized-bypass list. The Scope Framing section defines which three gates ARE in the authorized list.
- ALWAYS use atomic `os.mkdir` for the incident directory creation — race-condition defense against two operators filing `/hotfix` simultaneously from different terminals.
- ALWAYS verify the path traversal guard (realpath comparison) before creating the directory.
- ALWAYS run the recursion guard as the FIRST action in the skill — before Phase 0, before argument validation, before anything.
- ALWAYS use the `git commit -m "..." -- <paths>` form per `standards/git/commit-discipline.md`. Never `git add` followed by `git commit` in the same flow; never `git add .`.
- ALWAYS reject empty `/hotfix` invocations with the usage string: `Usage: /hotfix <short description of incident>`. No interactive description capture.
- The `gates_bypassed` field records the gates the subagent was AUTHORIZED to proceed past (`tdd-gate`, `enough-context`, `phase-gate`), not the gates that actually fired. A gate in the authorized list goes into the audit record even if it never fired during the run.
- The Phase 0 banner is NEVER a blocker. It is a visual reminder. Do not prompt for acknowledgment.

## Post-Completion Guidance

After the skill exits, the hotfix is committed to git under the incident directory's audit trail, the subagent's `SubagentStop` adversarial review has fired, and the operator's next step depends on which path Phase 5 took.

Print this guidance as Pattern B after the completion summary, tailored to the path taken:

```

---

**▶ Next steps:**

  • Postmortem: run `/postmortem` within 24h to clear the debt. The next `/hotfix` invocation will surface the Phase 0 banner if you don't.
  • Audit trail: `.etc_sdlc/incidents/{id}/incident.md` is git-tracked. `git log -p .etc_sdlc/incidents/{id}/` shows the full audit history.
  • Preempted build (if any): `/build --resume {build_slug}` restarts the preempted build from its checkpoint. The build may warn about files the hotfix touched if they were in the build's `files_in_scope` — this is expected. Resume does not auto-abort; the operator decides whether to continue the wave or refile the feature.
  • Escalation (if the subagent halted): the incident is at `status: escalated` and the operator needs to decide next steps manually. The stopReason in the Phase 4 Pattern B announcement names the specific reason. Escalations do NOT receive an automatic `/postmortem` suggestion.

```

The lane's social contract is direct: speed up front, accountability on the way out. Both halves are load-bearing. If the operator skips the postmortem, the next `/hotfix` invocation will surface the debt. If they waive it explicitly, the audit trail records the waiver. If they run `/postmortem` immediately, the learning loop closes in a single session. Every path is traceable; no path is silent.

## Definition of Done

`/hotfix` is done for a given invocation when ALL of the following observable artifacts exist and the workflow reached a terminal state. The exact set depends on which terminal state the invocation reached; items 1-3 always apply, items 4-7 apply to the completed-fix path, item 8 applies to the escalated path, and item 9 applies to the rejected-at-guard path (recursion, fresh-incident lock, path traversal). Each path is terminal and mutually exclusive.

1. The Recursion Guard ran first and either rejected the invocation (path 9) or passed.
2. The Before Starting reads (items 1-4 in that section) were executed via the Read tool before any Phase 0 action.
3. Exactly zero or exactly one `Task` tool call to `subagent_type: "hotfix-responder"` was made during the invocation. Zero is valid ONLY for paths 9 and for rejection at the single-incident lock.
4. COMPLETED-FIX PATH ONLY: `.etc_sdlc/incidents/{slug}/incident.md` exists with `status: completed`, non-null `completed_at`, populated `files_touched`, populated `gates_bypassed`, and either a non-null `postmortem` field or the operator's "Defer to later" selection recorded (via `postmortem: null` and no waived marker).
5. COMPLETED-FIX PATH ONLY: the Phase 5 `AskUserQuestion` postmortem prompt was rendered and the operator's selection was acted on per Phase 5's branch logic.
6. COMPLETED-FIX PATH ONLY: the Phase 5 Pattern B completion summary was rendered to the operator.
7. COMPLETED-FIX PATH ONLY: if Phase 2 preempted a `/build`, the `/build --resume {build_slug}` note was printed in the Phase 5 output.
8. ESCALATED PATH ONLY: `.etc_sdlc/incidents/{slug}/incident.md` exists with `status: escalated`, the subagent's verbatim `stopReason` was surfaced to the operator via Pattern B, and the Phase 5 postmortem prompt was SKIPPED.
9. REJECTED-AT-GUARD PATH ONLY: the rejection Pattern B announcement was rendered, no incident directory was created, no subagent was dispatched, and the skill exited.

If any applicable item is not satisfied, `/hotfix` is NOT done for that path. Do not report completion on the completed-fix path unless items 1-7 hold. Do not report escalation on the escalated path unless items 1-3 and 8 hold. Do not report rejection on the rejected-at-guard path unless items 1-3 and 9 hold.
