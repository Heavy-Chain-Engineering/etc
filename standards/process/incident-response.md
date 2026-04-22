# Incident Response — The Hotfix Lane

**Framing:** This document describes defensive incident response for
authorized codebases owned by the operator. Terms like "bypass,"
"attack," and "guardrail" appear in the context of gate controls,
threat-model analysis, and abuse-detection defenses inside the harness
itself — all for remediation, not exploitation. If a passage feels
dual-use, flag it explicitly rather than refusing silently.

Incident response is the operating mode every engineering team needs but
most harnesses neglect. When production is on fire, the operator does
not need a Definition-of-Ready interview, a three-state PRD classifier,
or a wave-by-wave decomposition. They need to file what's broken, what
the fix is, and what the rollback plan is in seconds — then have an
authorized subagent execute the fix while the harness's safety-critical
gates still fire. The etc harness has a dedicated lane for this work,
`/hotfix`, so that "production is down" never tempts an operator to go
around the harness entirely.

## The Rule

### The three-lane model

The etc harness has three operating modes, each with its own entry
point and its own ceremony budget:

- **Conversation** — plain chat with Claude Code, no skill invoked.
  Used for exploration, review, ad-hoc questions, and any work that
  doesn't need a gated record.
- **`/spec` → `/build`** — the main lane for feature work. `/spec`
  produces a well-formed PRD through Socratic questioning; `/build`
  executes it through gated waves with TDD, context, and phase gates
  enforced on every subagent.
- **`/hotfix`** — the incident response lane. Three Pattern A pickers
  (failure type, fix kind, rollback kind), a dedicated
  `hotfix-responder` subagent, subagent-constrained gate bypass, and
  an auto-suggested `/postmortem` on the way out.

These lanes are not interchangeable. Pick the one whose ceremony budget
matches the work in front of you.

### When to use `/hotfix`

Use `/hotfix` when **production is broken right now** and you need a
fix in seconds. The canonical shape: a specific endpoint, service, or
deploy is failing; you already know what the fix is (revert a SHA, flip
a flag, edit a line); the normal `/spec` → `/build` ceremony would take
long enough that running it would be negligent. The three-question
flow is designed to be fillable in under 30 seconds. If you can't fill
it that fast, you're probably not in an incident.

### When NOT to use `/hotfix`

Do not use `/hotfix` for feature work, refactors, tech debt cleanup, or
"this would be faster without TDD" productivity shortcuts. Those go
through `/spec` and `/build`. The `gates_bypassed` audit field will
record every gate you skipped, the postmortem debt banner will surface
the incident at the next `/hotfix`, and the `hotfix-responder`
subagent's manifest guardrail will reject descriptions that don't look
like real production failures. Abusing the lane is detectable,
retroactively auditable, and socially expensive — and the normal lane
exists for a reason. Use it.

## Why This Rule Exists

The `/hotfix` lane makes a deliberate tradeoff: it sacrifices upfront
ceremony for speed. The three pickers, the single subagent dispatch,
the bypass of `tdd-gate`, `enough-context`, and `phase-gate` — these
are all concessions to the reality that incident minutes are the most
expensive minutes in an engineering team's week. Every second the
harness spends asking clarifying questions is a second production
stays broken.

The concession is not free. TDD, context gates, and phase gates exist
because they catch real defects. Bypassing them on a hot path means
the fix ships without the checks that normally catch regressions.
Something has to reclaim that accountability, or the lane becomes a
TDD backdoor and every "urgent feature" starts getting routed through
it.

The reclamation mechanism is the automatic `/postmortem` suggestion.
Every completed `/hotfix` triggers an `AskUserQuestion` offering to
run `/postmortem` immediately, defer, or skip with confirmation.
Postmortems are where the bypassed checks get paid back: the root
cause analysis writes prevention rules into
`.etc_sdlc/antipatterns.md`, the gate that should have caught the bug
gets strengthened, and the incident becomes an input to the next
feature's Definition of Ready. Speed up front, accountability on the
way out. Both halves are load-bearing.

## Operator Responsibilities

### Concrete incident descriptions

The incident description is the single most important field in the
record. It must reference both (a) a specific system, file, or
endpoint AND (b) a specific failure mode. The `hotfix-responder`
subagent's manifest guardrail inspects the description before taking
any tool action and refuses to proceed if either is missing. This is
not cosmetic: vague descriptions produce vague fixes, vague fixes
produce vague postmortems, and vague postmortems produce no learning.

Good descriptions:

- `POST /api/users returns 500 after 14:30 deploy`
- `auth-service health check failing since config push sha 7a4fb67`
- `billing worker crash-loop on Stripe webhook signature mismatch`

Bad descriptions (all rejected by the guardrail):

- `fix it`
- `things are broken`
- `src/api/users.py is broken somehow` (system named, no failure mode)
- `intermittent 500s` (failure mode named, no system)

If the rejection catches a real incident whose description you wrote
in a hurry, the fix is to re-invoke `/hotfix` with a sharper
description, not to argue with the guardrail. The rejection message
names the specific gap and includes an example of a valid shape.

### Postmortem follow-through

Every `/hotfix` carries a debt. When the subagent reports completion,
the skill invokes `AskUserQuestion` with three options: run
`/postmortem` now (recommended), defer to later, or skip with
confirmation. Choosing "defer" is legitimate — sometimes the fire is
still smoldering and the team needs to stabilize before the blameless
review — but the debt does not disappear. Any incident with
`status: completed`, `filed_at` more than 24 hours ago, no sibling
`postmortem.md`, and `postmortem != "waived"` will surface in a banner
at the next `/hotfix` invocation.

The banner does not block. It does not rate-limit. It simply lists
the open debts by path, every time you file a new incident, until you
pay them. Either write the postmortem within 24 hours or accept that
your next incident will begin with a public reminder of the one you
skipped. The banner is social pressure by design. Don't let the debts
pile up.

### DO NOT include secrets in incident descriptions or prose body

**The incident description and prose body land in git history.** The
`.etc_sdlc/incidents/` directory is tracked (per the `!incidents/`
exception added to `.gitignore` in BR-008), which means every word you
paste into the description, every stack trace you drop into the prose
body, and every credential that accidentally comes along for the ride
is committed to the repository. Once committed, the content cannot be
redacted without a history rewrite. This is the same rule as "don't
put secrets in commit messages," and for the same reason: the commit
history is forever.

Do not paste:

- API keys, access tokens, OAuth client secrets, service account JSON
- Database connection strings with embedded passwords
- AWS access key IDs / secret access keys, GitHub personal access
  tokens, JWTs
- User PII (email addresses, names, account IDs) from production data
- Internal URLs that leak infrastructure topology

If the incident involves a leaked credential, describe the shape of
the leak, not the credential itself. `GitHub token leaked via
misconfigured CI logs` is a valid description; the token's actual
value is not.

The `hotfix-responder` agent runs a high-confidence-secret regex check
against the incident description before proceeding — AWS key shapes,
GitHub token prefixes, JWT structures, and similar high-signal
patterns. If a match fires, the subagent emits a confirmation prompt
and refuses to proceed until the operator either redacts or
explicitly confirms. The regex is a backstop, not a guarantee. The
primary defense is operator discipline. Read your description before
you hit enter.

## The Three Anti-Abuse Defenses

`/hotfix` is a powerful lane. The three defenses below (GA-HF-006)
are the layered mitigations that keep it from becoming a backdoor
around the rest of the harness. None alone is sufficient; together
they make abuse detectable and socially expensive.

### Audit trail (`gates_bypassed`)

Every `incident.md` has a `gates_bypassed` field listing every gate
the `hotfix-responder` was authorized to skip — by default
`tdd-gate`, `enough-context`, and `phase-gate`. The field is
git-tracked, so it survives forever, and it is greppable: a single
command like `grep -r "tdd-gate" .etc_sdlc/incidents/` finds every
incident in which TDD was bypassed. This is the retroactive audit
anchor. If the lane is being abused, the audit trail is where the
abuse becomes visible. The record is not tamper-proof — `git log -p`
is the detection mechanism, not a cryptographic ledger — but that's
sufficient for an internal engineering audit.

### Subagent description guardrail

The `hotfix-responder` agent inspects the incident description before
any tool action and refuses if the description doesn't look like a
real production failure. This is the LLM-judgment defense at the
moment of action: instead of catching abuse in the audit log
afterward, the guardrail catches it before the bypass ships. A
creative operator could write a plausible fake description, so the
guardrail is not a bulletproof filter. It catches obvious abuse and
forces the subtle cases to leave a paper trail in the `gates_bypassed`
audit field.

### Postmortem-or-it-didn't-happen

Stale incidents (more than 24 hours old, `status: completed`, no
sibling `postmortem.md`, `postmortem != "waived"`) surface in a
banner at the next `/hotfix` invocation. This is social pressure, not
a hard gate — the banner does not block, does not rate-limit, and
does not refuse dispatch. It simply lists the open debts every time a
new incident is filed. An operator who accumulates five or six
unpaid postmortems will see the banner grow until they pay the debt
or the team calls it out. No process can prevent a bad week; this
defense makes sure a bad week leaves a visible, accumulating record.

## Recovery Procedures

### Stale incident from a crashed subagent

If the `hotfix-responder` crashes mid-fix (process killed, harness
restart, subagent hang), the `incident.md` is left in
`status: in_progress` with no `completed_at`. The next `/hotfix`
invocation detects this and offers interactive recovery via
`AskUserQuestion`:

- **Mark escalated and proceed** — the stale incident's status is
  updated to `escalated`, `completed_at` is set to the current
  timestamp, and the new `/hotfix` dispatches. Use this when the
  original work is definitely dead and the recovery has already
  happened out-of-band.
- **Wait — the original is still working** — the new `/hotfix` aborts.
  Use this when you see the stale incident but believe the original
  subagent is still making progress (one illustrative case: a
  long-running fix).
- **Cancel new /hotfix** — neither the stale incident nor the new one
  changes state. Use this when you need to review the stale incident's
  state manually (read the `incident.md`, check the target service,
  inspect recent commits) before proceeding.

"Mark escalated" is the normal path. Escalation is not failure — it's
an acknowledgment that the hotfix lane couldn't finish the work
cleanly and the operator took over. The audit record is intact
either way.

### Public-exposure risk

`.etc_sdlc/incidents/` is git-tracked. If the etc-managed repo — or
any consumer repo that uses `.etc_sdlc/incidents/` — is later
open-sourced, the entire incident history becomes public. That
includes:

- Operator names in the `filed_by` field
- System descriptions in the `target` field (endpoints, services,
  internal URLs)
- Fix details in `fix_detail` (SHAs, file paths, flag names)
- Rollback plans in `rollback_detail`
- Anything the operator wrote in the prose body

**Before open-sourcing any repo with an `.etc_sdlc/incidents/`
history, audit the directory.** Either redact the sensitive fields,
move the history to a private archive, or scrub the directory
entirely. This is the same risk profile as committing internal
incident reports to a private repo and later deciding to open-source
it: the commit history is forever, and `git filter-branch` is the
only way to remove it after the fact. Plan for this before you need
to, not after.

### Build-mid-wave conflict

When `/hotfix` preempts an active `/build`, the build's `state.yaml`
is updated with `status: preempted_by_hotfix` and
`preempted_at: <timestamp>`, and the running wave halts at the next
safe boundary (no in-flight tool calls are killed). After the hotfix
completes, `/hotfix` prints the exact resume command:
`/build --resume <slug>`.

Run `/build --resume <slug>` to restart the preempted build. If the
hotfix touched files that were in the preempted build's
`files_in_scope`, the resume will warn about the conflict — the
touched files are recorded in the build's `state.yaml` under
`files_modified_during_preempt`. Review the diffs before continuing.
The resume does not auto-abort; the choice to continue, re-plan, or
throw away the build is yours. Treat it the way you would treat
resuming a rebase after a manual conflict edit: look at what changed,
decide if the wave's assumptions still hold, and only then continue.

## Origin

This standards doc was adopted on 2026-04-15 alongside the v1.6
release of etc that introduced the `/hotfix` lane. The lane was the
third operating mode the harness needed but had been deferring
through v1.4 and v1.5; it completes the three-lane architecture
(conversation / spec→build / hotfix) introduced as a principle in
v1.5's "lanes, not gates" refactor. The six gray-area decisions that
shaped the lane's design (GA-HF-001 through GA-HF-006) are recorded
in `.etc_sdlc/features/hotfix/gray-areas.md`; this document is the
operator-facing distillation of those decisions.
