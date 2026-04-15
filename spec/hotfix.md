# PRD: /hotfix — Incident Response Lane

## Summary

`/hotfix` is the third lane in the etc harness, complementing `/spec` and `/build`. Where `/spec` produces well-formed PRDs through Socratic questioning and `/build` executes them through gated waves, `/hotfix` exists for the operating mode every engineering team needs but most harnesses neglect: **incident response**. When production is on fire, the operator does not need a Definition-of-Ready interview, a three-state classifier, or a wave-by-wave decomposition. They need to file what's broken, what the fix is, and what the rollback plan is in under 30 seconds, and then have an authorized subagent execute the fix while the harness's safety-critical gates (`safety-guardrails`, `tier-0-preflight`, `check-invariants`) still fire — even if a `/build` is mid-wave, in which case the build is checkpointed and `/hotfix` preempts.

The lane sacrifices upfront ceremony for speed, then reclaims accountability afterward through automatic `/postmortem` suggestion. Every `/hotfix` invocation produces a structured incident log at `.etc_sdlc/incidents/{YYYY-MM-DD}-{slug}/incident.md` recording the failure type, the fix, the rollback plan, the gates that were bypassed, the dedicated `hotfix-responder` subagent that ran, and the files it touched. The directory pattern leaves room for a sibling `postmortem.md` once the fire is out, and an optional `subagent.log` capturing the subagent's execution trace. The audit trail makes the lane trustworthy: every bypass is greppable, every incident is git-tracked, and every gate that was skipped is named in the record.

Three defenses prevent the lane from being abused as a TDD or context-gate backdoor. First, the `gates_bypassed` field in every `incident.md` is the retroactive audit anchor. Second, the `hotfix-responder` subagent's manifest includes a guardrail: it inspects the incident description and refuses to proceed if the description doesn't sound like a real production failure (LLM-judgment defense at the moment of action). Third, the "/postmortem-or-it-didn't-happen" social pressure: any incident left without a postmortem for more than 24 hours surfaces a banner at the next `/hotfix` invocation listing the open debts. Defense in depth, no hard rate limits, no rejection of legitimately bad weeks. The lane has a single-incident lock — only one `/hotfix` runs at a time, and rollback-of-rollback waits for the first incident to close — to keep the operating model predictable under stress.

## Scope

### In Scope

- A new skill `skills/hotfix/SKILL.md` invokable as `/hotfix {short description}` from any project under the etc harness.
- Three Pattern A pickers on invocation: failure type (Q1), fix kind (Q2), rollback strategy (Q3). Each picker has 4–5 enumerated categories plus the automatic `Other` escape hatch. When a selection requires specifics, an immediate Pattern B follow-up captures the detail.
- A new dedicated agent type `agents/hotfix-responder.md` (the subagent dispatched by `/hotfix`).
- Subagent-constrained gate bypass (NOT hook modification): `tdd-gate`, `enough-context`, `phase-gate` are bypassed at the `hotfix-responder` agent's authorization layer. `safety-guardrails`, `tier-0-preflight`, `check-invariants` continue to fire.
- Single-incident lock: only one `/hotfix` runs at a time.
- `/build` preemption: if a `/build` is mid-wave when `/hotfix` is invoked, the build's `state.yaml` is checkpointed, the wave halts, the hotfix runs to completion, and the operator runs `/build --resume` afterward.
- Incident log directory at `.etc_sdlc/incidents/{YYYY-MM-DD}-{slug}/incident.md` with YAML frontmatter and free-form prose body.
- Automatic `/postmortem` suggestion via `AskUserQuestion` after the `hotfix-responder` reports completion.
- "/postmortem-or-it-didn't-happen" warning banner at the next `/hotfix` invocation.
- Subagent manifest guardrail: the `hotfix-responder` inspects the incident description and refuses to proceed if it doesn't match an incident shape.
- New standards doc at `standards/process/incident-response.md`.
- DSL entry under `skills:` in `spec/etc_sdlc.yaml`.
- New test file `tests/test_hotfix.py` covering all BRs.
- `.gitignore` exception adding four lines after the existing `.etc_sdlc/` ignore so the `incidents/` subdirectory is tracked while `features/` and `tasks/` stay ignored. See the Module Structure section for the exact pattern — the obvious two-line form (`!.etc_sdlc/incidents/` + `!.etc_sdlc/incidents/**`) does NOT work because git refuses to re-include a file whose parent directory is excluded.

### Out of Scope

- No external alerting integration (no PagerDuty, Slack, email, webhooks).
- No automatic rollback detection (no monitoring-driven rollback).
- No multi-operator coordination beyond the single-incident lock.
- No mutation of `/spec` or `/build`.
- No removal or weakening of any existing gate.
- No re-introduction of the v1.5.1 `harness-feedback` Stop hook.
- No cross-repo execution.
- No hard rate limits.
- No GUI or TUI.
- No batch hotfix mode.
- No `/hotfix` on non-production environments.

## Requirements

### BR-001: Single subagent dispatch per invocation

`/hotfix` dispatches exactly one `hotfix-responder` subagent per invocation. There is no decomposition, no wave planning, no parallel dispatch.

### BR-002: Subagent-constrained gate bypass

The `hotfix-responder` is authorized to bypass `tdd-gate`, `enough-context`, and `phase-gate`. The bypass lives in the subagent's authorization layer, not in the hook scripts. The existing hook code is untouched.

### BR-003: Safety-critical gates always fire

The `hotfix-responder` does NOT bypass `safety-guardrails`, `tier-0-preflight`, or `check-invariants`. These gates fire on every operation the subagent performs.

### BR-004: Single-incident lock

Before dispatching, `/hotfix` scans `.etc_sdlc/incidents/*/incident.md` for any file whose `status` is in `{filed, in_progress}`. If a match exists, the new invocation is rejected with a status announcement naming the open incident's path.

### BR-005: /build preemption

Before dispatching, `/hotfix` checks for an active `/build`. If found, the build's `state.yaml` is updated with `status: preempted_by_hotfix` and `preempted_at: <timestamp>`, the running wave halts at the next safe boundary, and `/hotfix` proceeds. After completion, `/hotfix` prints the `/build --resume` command.

### BR-006: Three Pattern A pickers on invocation

`/hotfix` asks three questions via `AskUserQuestion`, one per turn:

- **Q1 — failure_type**: `endpoint_error`, `service_down`, `data_corruption`, `config_wrong`, `deployment_failure`, plus `Other`.
- **Q2 — fix_kind**: `revert_commit`, `edit_files`, `flip_config`, `disable_feature_flag`, `dependency_rollback`, plus `Other`.
- **Q3 — rollback_kind**: `revert_to_sha`, `restore_backup`, `disable_flag`, `reapply_commit`, `manual_steps`, plus `Other`.

### BR-007: Pattern B follow-ups for specifics

Each picker selection that requires concrete data (a SHA, a file path, a flag name) triggers an immediate Pattern B follow-up that captures the detail into the corresponding `*_detail` field of the incident log.

### BR-008: Incident log schema

Every `/hotfix` invocation produces a directory at `.etc_sdlc/incidents/{YYYY-MM-DD}-{slug}/` containing an `incident.md` file with YAML frontmatter:

```yaml
---
incident_id: "2026-04-15-api-users-500"
filed_at: "2026-04-15T14:32:18Z"
filed_by: "<operator identity from environment>"
status: "filed"   # filed | in_progress | completed | escalated
failure_type: "endpoint_error"
target: "POST /api/users returns 500 after 14:30 deploy"
fix_kind: "revert_commit"
fix_detail: "7a4fb67"
rollback_kind: "reapply_commit"
rollback_detail: "re-apply 7a4fb67 if monitoring shows X"
gates_bypassed: ["tdd-gate", "enough-context", "phase-gate"]
subagent: "hotfix-responder"
files_touched: []          # filled by subagent at completion
completed_at: null         # filled by subagent at completion
postmortem: null           # filled by /postmortem when run
---
```

Required fields at filing time: everything except `files_touched`, `completed_at`, and `postmortem`.

### BR-009: Status state machine

`status` transitions: `filed → in_progress → completed | escalated`. No transition from `completed` back to `in_progress`.

### BR-010: Postmortem suggestion

Immediately after the `hotfix-responder` reports `status: completed`, `/hotfix` invokes `AskUserQuestion` with three options: (a) **Run /postmortem now (Recommended)**, (b) **Defer to later**, (c) **Skip with confirmation**.

### BR-011: Postmortem debt banner

At the start of every `/hotfix` invocation, the skill scans for incidents with `status: completed`, `filed_at > 24h ago`, no sibling `postmortem.md`, and `postmortem != "waived"`. Each match is listed in a banner before any other check. The banner does NOT block.

### BR-012: Subagent description guardrail

The `hotfix-responder` agent inspects the incident description before taking any tool action. The description must reference both (a) a specific system/file/endpoint, AND (b) a specific failure mode. If either is missing, the subagent returns `{"continue": false, "stopReason": "Description does not match an incident shape: missing <system|failure-mode>..."}`.

### BR-013: Audit trail of bypassed gates

Every gate the `hotfix-responder` bypassed is recorded in the `gates_bypassed` field of `incident.md`.

### BR-014: Files touched audit

Every file the `hotfix-responder` modified is recorded in `files_touched` at completion.

### BR-015: No recursive /hotfix

The `hotfix-responder` cannot invoke `/hotfix` recursively. The skill checks `agent_type == "hotfix-responder"` in the caller context and rejects with `recursive /hotfix not allowed`.

## Acceptance Criteria

1. **Filing creates a populated incident directory.** Invoking `/hotfix "POST /api/users returns 500"` with no other open incident creates `.etc_sdlc/incidents/2026-04-15-post-api-users-returns-500/incident.md` with all required YAML frontmatter fields populated. [BR-006, BR-007, BR-008]

2. **Single-incident lock rejects concurrent invocation.** Invoking `/hotfix` while any incident has `status` in `{filed, in_progress}` is rejected with a status announcement naming the open incident's path. No new directory is created. [BR-004]

3. **TDD gate bypass succeeds for hotfix-responder.** A `hotfix-responder` can Edit `src/foo.py` with no `tests/test_foo.py`, where any other agent type would be blocked by `check-test-exists.sh`. Verified by integration test. [BR-002]

4. **Safety-guardrails still fires.** A `hotfix-responder` attempting `rm -rf /` is blocked exactly as any other agent. [BR-003]

5. **Invariant check still fires.** A `hotfix-responder` operating on a fixture with a failing `INVARIANTS.md` verify command is blocked at the Edit. [BR-003]

6. **/build preemption checkpoints state.** Invoking `/hotfix` while a `/build` is active updates `state.yaml` with `status: preempted_by_hotfix` and `preempted_at: <ISO timestamp>` before dispatch. After completion, `/hotfix` prints `/build --resume <slug>`. [BR-005]

7. **Picker selections populate structured fields.** After Q1=`endpoint_error`, Q2=`revert_commit`, Q3=`reapply_commit`, the resulting `incident.md` frontmatter contains those exact values. [BR-006, BR-007]

8. **Picker follow-ups capture detail.** A Q2 selection of `revert_commit` triggers a Pattern B follow-up "Which SHA should be reverted?" and writes the answer to `fix_detail`. [BR-007]

9. **Postmortem suggestion fires at completion.** After `hotfix-responder` reports `status: completed`, `/hotfix` invokes `AskUserQuestion` with the three postmortem options. [BR-010]

10. **Postmortem-debt banner surfaces stale incidents.** When the next `/hotfix` is invoked, the skill scans for `incident.md` files with `status: completed`, `filed_at > 24h ago`, no sibling `postmortem.md`, and `postmortem != "waived"`. Each match is listed in a Pattern B banner BEFORE any other check. The banner does NOT block. [BR-011]

11. **Description guardrail rejects vague descriptions.** Dispatching with "fix it" (no system reference) or "src/api/users.py is broken somehow" (no failure mode) returns `{"continue": false, "stopReason": "Description does not match an incident shape: missing <system|failure-mode>..."}`. The orchestrator surfaces the rejection and `incident.md` is updated to `status: escalated`. [BR-012]

12. **Description guardrail accepts concrete descriptions.** Dispatching with "POST /api/users returns 500 after 14:30 deploy" does NOT trigger the guardrail rejection. The subagent proceeds. [BR-012]

13. **gates_bypassed audit field is populated correctly.** After a run that bypasses `tdd-gate`, `enough-context`, and `phase-gate`, the completed `incident.md`'s `gates_bypassed` field contains all three. [BR-013]

14. **files_touched audit field matches actual edits.** After a run that modifies `src/api/users.py` and `config/feature-flags.yaml`, `files_touched` is exactly those two files. [BR-014]

15. **Recursive /hotfix is rejected.** A `hotfix-responder` invoking `/hotfix` (via Skill tool or any alternative path) is rejected with `recursive /hotfix not allowed`. [BR-015]

16. **Status state machine enforces forward-only transitions.** Updating `incident.md` with `status: in_progress` when current `status` is `completed` is rejected. [BR-009]

17. **Compile produces all expected artifacts.** After `python3 compile-sdlc.py spec/etc_sdlc.yaml`: `dist/skills/hotfix/SKILL.md`, `dist/agents/hotfix-responder.md`, `dist/standards/process/incident-response.md` exist. Skills 9 → 10, agents 19 → 20, standards 31 → 32, gates unchanged at 14, hooks unchanged at 10.

18. **`.gitignore` tracks incident logs.** `git check-ignore .etc_sdlc/incidents/2026-04-15-test/incident.md` returns non-zero (NOT ignored). `git check-ignore .etc_sdlc/features/test-feature/spec.md` still returns zero (still ignored).

19. **`tests/test_hotfix.py` lands with at least +12 tests.** Total count goes from 264 to at least 276.

## Edge Cases

1. **Two operators file `/hotfix` simultaneously from different terminals.** Atomic `mkdir`; the loser sees the standard lock-rejection naming the winner's path. No silent overwrite.

2. **Operator answers a picker with `Other` but the free text doesn't categorize.** The picker captures `Other` text directly into the structured field. The description guardrail still runs and may reject if the result is too vague.

3. **The `hotfix-responder` crashes mid-fix.** `incident.md` left in `status: in_progress`. Next `/hotfix` detects the stale incident and offers interactive recovery via `AskUserQuestion`: (a) **Mark escalated and proceed**, (b) **Wait — the original is still working**, (c) **Cancel new /hotfix**.

4. **`/build` is mid-Edit when `/hotfix` arrives.** The wave halt waits for the in-flight subagent's current tool call to complete. The skill MUST NOT kill a subagent mid-Edit.

5. **The slug derivation produces an empty string.** Fall back to `incident-{HHMMSS}`.

6. **Two incidents on the same day produce the same slug.** Append `-1`, `-2` if the target directory already exists.

7. **The guardrail rejects but the operator REALLY meant a real incident.** The rejection `stopReason` includes the specific gap and an example of what a valid description looks like.

8. **The operator doesn't know the SHA when Q2 = `revert_commit`.** The Pattern B follow-up accepts free-text — they can write "find it from `git log`" and the subagent resolves.

9. **`/build --resume` after a `/hotfix` preempt finds files in conflict.** `/hotfix` records touched files in the preempted build's `state.yaml` under `files_modified_during_preempt`. `/build --resume` warns the operator. Resume does not auto-abort.

10. **The `hotfix-responder` agent definition is missing at runtime.** The skill fails fast at startup with: "agents/hotfix-responder.md not found. Reinstall the harness via ./install.sh."

11. **Operator sets `postmortem: waived` and the next debt banner should not list the incident.** The banner check honors `waived`.

12. **A `/postmortem` is written but the operator forgot to update the `postmortem` field.** The banner uses sibling `postmortem.md` file existence as the primary signal.

13. **Recursive `/hotfix` via an alternative invocation path.** The check is robust: it inspects the caller context for `agent_type == "hotfix-responder"` regardless of how `/hotfix` was reached.

14. **`gates_bypassed` field claims gates that never would have fired.** Cosmetic; the field is "gates the subagent was authorized to bypass" not "gates that were actually skipped."

15. **The 24h debt banner is timezone-sensitive.** Accepted; the banner is social pressure, not a hard gate.

16. **The operator uses `/postmortem` directly without going through `/hotfix` first.** No interaction with the `/hotfix` debt banner.

17. **Build preemption is requested but no build is active.** The skill simply skips the preempt step.

18. **`/hotfix` is invoked with no description argument.** The skill rejects with "Usage: /hotfix <short description of incident>". No interactive description capture.

## Technical Constraints

### Codebase patterns to follow

- **Skill file format**: matches `skills/spec/SKILL.md` (frontmatter, Usage, Workflow, Constraints, Post-Completion Guidance).
- **Agent manifest format**: matches `agents/backend-developer.md` and other 19 agents. Modeled after `agents/spec-enforcer.md` for gate-aware dispatch.
- **DSL entry**: a new entry under `skills:` in `spec/etc_sdlc.yaml`, no changes to `gates:`.
- **Test file pattern**: class-per-concern matching `tests/test_inject_standards.py`. Reuses `conftest.py` fixtures (`tmp_project`, `run_hook`).
- **Hook scripts NOT modified**: `hooks/check-test-exists.sh`, `hooks/check-required-reading.sh`, `hooks/check-phase-gate.sh` are untouched.

### Frameworks and libraries

- Python 3.11+. Stdlib only, plus `pyyaml` (already a project dep) for `incident.md` frontmatter.
- pytest + pytest-mock for `tests/test_hotfix.py`.
- Claude Code's `Skill`, `AskUserQuestion`, and `Task` tools as runtime primitives.

### Standards and INVARIANTS rules

- **TDD discipline**: `tests/test_hotfix.py` is required as the contract test asserting compiled SKILL.md and agent manifest shape.
- **Layer boundaries**: `/hotfix` operates on `.etc_sdlc/incidents/` paths relative to cwd, no consumer-project imports.
- **Domain fidelity**: use "incident", "hotfix", "operator", "fix", "rollback", "bypass", "postmortem", "preempt" consistently.
- **Standards injection**: incident response discipline is NOT injected globally; it lives in the standards doc and the agent manifest.
- **Git commit discipline (commit `ff2b268`)**: any subagent uses `git commit -m "..." -- <paths>` form. The `hotfix-responder` runs serially so the parallel-index race isn't a hot risk, but the rule applies for consistency.
- **No re-introduction of prompt hooks on Stop**: `tests/test_compiler.py::TestHarnessFeedbackHookRemoved` enforces this. `/hotfix`'s postmortem suggestion lives in the skill body, not as a Stop hook.
- **Three-state PRD classifier does NOT apply to `/hotfix`** invocations; it applies only to this PRD itself.

### Compile / install / test invariants

- `compile-sdlc.py` succeeds. Skills 9 → 10, agents 19 → 20, standards 31 → 32, gates unchanged at 14, hooks unchanged at 10.
- `./install.sh` succeeds. `dist/skills/hotfix/SKILL.md` and `dist/agents/hotfix-responder.md` deploy.
- Test count 264 → at least 276.

## Security Considerations

### Privilege escalation via gate bypass

The defining tradeoff of the feature. The three GA-HF-006 defenses (audit trail, subagent description guardrail, postmortem-debt banner) are the layered mitigations. None alone is sufficient; together they make abuse detectable and socially expensive.

### Path traversal via slug derivation

Slug derivation MUST sanitize: lowercase, replace `[^a-z0-9-]` with `-`, collapse runs, strip leading/trailing `-`, truncate to 50 characters. After construction, MUST verify `os.path.realpath(target_dir).startswith(os.path.realpath(incidents_root))` before creating.

### Symlink attacks on incident directories

Use `os.O_NOFOLLOW` when writing `incident.md`. Check parent directory is not a symlink before writing.

### Command injection via picker `Other` text

Any shell interpolation MUST use `subprocess.run([...], shell=False)` with argv-list passing. Never `shell=True` with f-string concatenation.

### Sensitive data in incident descriptions and prose body

Operators in a hurry may paste secrets/credentials/tokens/PII. Because `incident.md` files are git-tracked, this content lands in commit history. The standards doc MUST include a "DO NOT include secrets" warning. The `hotfix-responder` agent emits a confirmation prompt if the description matches a high-confidence secret pattern (AWS keys, GitHub tokens, JWT, etc.).

### Audit trail tampering

`incident.md` is git-tracked; tampering is detectable via `git log -p`. The audit isn't a tamper-proof ledger, but detection is sufficient.

### Race conditions on the single-incident lock

Atomic `os.mkdir`; if `FileExistsError`, the other operator won. Covered in Edge Case 1 but bears repeating: lock races are the canonical lock-bypass vulnerability.

### Subagent description guardrail bypass

LLM-judgment defense. A creative operator could write a plausible fake description. The guardrail catches obvious abuse, not determined abuse. The other two defenses are the catch-after-the-fact backstops.

### Accidental public exposure of incident history

Open-sourcing a repo with `.etc_sdlc/incidents/` content exposes operator names, system descriptions, and fix details. The standards doc MUST warn project owners to audit `.etc_sdlc/incidents/` before open-sourcing.

### Recursive `/hotfix` as denial-of-service

BR-015's recursion guard is the primary defense. The single-incident lock (BR-004) is the secondary defense.

## Module Structure

### Files created

- **`skills/hotfix/SKILL.md`** — the skill source. Modeled after `skills/spec/SKILL.md`.
- **`agents/hotfix-responder.md`** — the dedicated subagent manifest. Modeled after `agents/backend-developer.md`.
- **`standards/process/incident-response.md`** — lane discipline. Modeled after `standards/process/research-discipline.md`.
- **`tests/test_hotfix.py`** — 11 test classes covering all BRs. At least 12 tests.
- **`.etc_sdlc/incidents/.gitkeep`** — placeholder so the directory exists in fresh checkouts.

### Files modified

- **`spec/etc_sdlc.yaml`**: new `hotfix:` entry under `skills:`, new `hotfix-responder:` entry under `agents:`. No changes to `gates:`.
- **`.gitignore`**: add a four-line exception after the existing `.etc_sdlc/` ignore so the `incidents/` subdirectory is tracked while `features/` and `tasks/` stay ignored. **The two-line form `!.etc_sdlc/incidents/` + `!.etc_sdlc/incidents/**` does NOT work** — git will not re-include a file whose parent directory is excluded, so the `!.etc_sdlc/incidents/` negation is never reached. The working pattern is:
  ```
  .etc_sdlc/
  !.etc_sdlc/
  .etc_sdlc/*
  !.etc_sdlc/incidents/
  !.etc_sdlc/incidents/**
  ```
  First line: ignore the whole tree (unchanged, pre-existing). Second line: un-ignore the directory itself so git can descend into it. Third line: re-ignore the immediate contents entry-by-entry. Fourth and fifth lines: un-ignore `incidents/` and its contents specifically. This was discovered during the first build — see `.etc_sdlc/features/hotfix/verification.md` for the full finding.
- **`README.md`**: skills count 9 → 10; add `/hotfix` to pipeline narrative; gate count narrative still 14.
- **`RELEASE_NOTES.md`**: prepend v1.6 section "etc v1.6 — incident response lane".

### Files explicitly NOT modified

- `hooks/check-test-exists.sh`, `hooks/check-required-reading.sh`, `hooks/check-phase-gate.sh` — bypass lives in agent manifest.
- `hooks/inject-standards.sh` — incident response discipline is agent-specific, not global.
- `tests/test_compiler.py::TestHarnessFeedbackHookRemoved` — unchanged.
- `tests/test_inject_standards.py` — no new test classes.

### Compiled artifacts

- `dist/skills/hotfix/SKILL.md`
- `dist/agents/hotfix-responder.md`
- `dist/standards/process/incident-response.md`

### Post-compile count delta

| | Before | After | Delta |
|---|---|---|---|
| Gates | 14 | 14 | 0 |
| Hooks | 10 | 10 | 0 |
| Skills | 9 | 10 | +1 |
| Agents | 19 | 20 | +1 |
| Standards docs | 31 | 32 | +1 |

## Research Notes

### Codebase findings (Phase 2)

- **`hooks/check-test-exists.sh`** gates only `src/*.py` files; no fix-type or git-status awareness. The conditional-tdd-gate refinement is cheaper as a subagent constraint than as a hook change. This shaped GA-HF-002.
- **`skills/postmortem/SKILL.md`** already uses Pattern A/B discipline and writes to `.etc_sdlc/antipatterns.md`. The `/hotfix` → `/postmortem` handoff is a single `AskUserQuestion` at the end of the hotfix flow; no modification to `/postmortem` is required.
- **`.etc_sdlc/`** has `features/` and `tasks/` but no `incidents/`. No precedent — but the per-feature pattern suggests the parallel `.etc_sdlc/incidents/{YYYY-MM-DD}-{slug}/`.
- **`skills/build/SKILL.md`** dispatches subagents via `assigned_agent` type at line 260 — existing pattern for `/hotfix` to follow.
- **No `.etc_sdlc/antipatterns.md`** in the etc repo. No prior escaped-bug lessons to incorporate.

### Web research

Skipped — `/hotfix` is an internal harness feature with no external libraries to survey.

### Key research finding

The conditional-tdd-gate refinement ("bypass allowed only for git reverts, config flips, or dependency rollbacks — NOT for new code") is **cheaper as a subagent constraint than as a hook change**. Instead of teaching `check-test-exists.sh` to detect fix type from git status (complex, fragile), the `/hotfix` subagent itself is constrained: "you may only edit files that already have a matching test — new-source-file creations during a hotfix must be blocked at your own discretion." The existing hook stays unmodified, the bypass becomes additive at the subagent level, and `SubagentStop` adversarial review catches violations.
