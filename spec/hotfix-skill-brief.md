# /hotfix — Incident Response Lane (Deferred PRD)

**Status:** Deferred. This is a brief, not a buildable spec. Promote to a
full PRD via `/spec` when ready to implement.

## The Problem

The harness currently has two lanes for work:

1. **Conversational / ideation** — free chat, no gates, the top-level thread.
2. **Spec → build** — rigorous, gated by `/spec`'s three-state classifier
   and `/build`'s DoR preflight.

What's missing: a third lane for **incident response**. When production is
on fire, the user does not need a Socratic spec interview. They need:

- A terse statement of what's broken ("the `/api/users` endpoint returns 500
  after the 2026-04-14 deploy")
- A fix hypothesis or a git revision to revert
- A rollback plan if the fix makes things worse
- Fast execution
- A postmortem log captured *after* the fire is out

Running this through `/spec` wastes precious minutes. Running it through
unstructured conversation loses accountability — no ticket, no history, no
postmortem trigger.

## Proposed Shape

A new skill `/hotfix` with this surface:

```
/hotfix {short description of the incident}
```

Lightweight ceremony — three questions max:

1. **What file or system is broken?** (file path, endpoint, service name)
2. **What's the fix?** (revert SHA, code change, config flip)
3. **Rollback plan if the fix fails?** (revert to SHA, restore from backup,
   disable feature flag)

Then: execute immediately. No task decomposition, no wave planning, no
DoR gate. Run tests afterward if there's time.

## Post-Incident Hook

After `/hotfix` completes, automatically prompt:

> Fire is out. Run `/postmortem` now to capture root cause, timeline, and
> prevention rules while it's fresh?

This is the accountability bridge: the hotfix lane sacrifices upfront
ceremony, but the postmortem lane reclaims it afterward. No incident goes
undocumented, but no incident is slowed by documentation either.

## Success Criteria (to be refined in the real PRD)

- A user can file a hotfix in ≤30 seconds from noticing prod is down.
- The skill never runs a DoR gate, a spec classifier, or a decomposition step.
- Every `/hotfix` invocation is logged in a dedicated incident log that
  `/postmortem` reads from.
- `/postmortem` is auto-suggested after `/hotfix` completes.

## Why This Is Deferred

The current priority is stabilizing the spec → build lane (which we just did
with tasks-cli and the three-state classifier). The hotfix lane is a
separate architectural concern — it touches incident logging, postmortem
integration, and the top-level thread's lane-routing logic — and deserves
its own PRD + build cycle rather than being bolted onto the spec lane.

## Related

- `skills/postmortem/SKILL.md` — existing skill, will be the landing point
  after `/hotfix` completes.
- `skills/spec/SKILL.md` — the rigorous lane; hotfix must NOT route through
  this.
- `skills/build/SKILL.md` — Step 1 now hosts the DoR preflight; hotfix must
  NOT go through this either. Hotfix is its own lane with its own entry
  point and its own (much lighter) gate.
