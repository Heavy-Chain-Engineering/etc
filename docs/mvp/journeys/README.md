# MVP Journeys

This directory captures **customer journeys** — first-person accounts of
how a real person gets work done in your domain. Journeys are written
in journey-shape, not capability-shape:

- **Capability-shape** says: "The platform can do X, Y, Z."
- **Journey-shape** says: "Julie clicks a contract, picks a template, sends to Sales, customer redlines, e-signs, Julie counter-signs, stores in CRM."

The intersection of journeys IS the MVP. If three journeys all require
template management + e-sign + CRM storage, then those three things are
the MVP. Capability lists can grow forever without converging on
something a real user can complete end-to-end.

## How to capture a journey

Run `/journey` in Claude Code. You'll be asked 6 plain-English questions
(plus one optional emotion question):

1. Who is doing this work?
2. What kicks it off?
3. Walk me through what they do.
4. When does it work well?
5. When does it go wrong?
6. What tools do they touch?
7. (Optional) How do they feel at each step?

You can answer in narrative paragraphs, bullet points, or a paste from
Slack / interview notes. The skill refines your answer into a structured
journey artifact saved here.

## File layout

```
docs/mvp/journeys/
├── README.md                              ← this file
├── J-001-contract-execution.md            ← canonical example (anonymized)
├── J-002-<your-journey-slug>.md           ← your captured journeys
└── ...
```

Journey IDs (`J-NNN`) are allocated by `scripts/journey_id.py` and are
forward-only (never reused, never deleted). Each journey file has
frontmatter with `journey_id`, `actor`, `trigger`, `outcome`, `status`
(`draft` / `refined` / `locked`).

## How journeys connect to features

Every feature filed after F017 ships declares one of two things in its
`state.yaml.spec_phase`:

- `journey_refs: [J-007, J-012]` — the customer journeys this feature serves
- `infrastructure_only: true` + `infrastructure_reason: "<one-liner>"` — for
  platform / tooling / harness internals that don't trace to a customer

The `/build` Step 7.4 gate enforces this at release-tag time. Features
without journey lineage AND without the infrastructure sentinel cannot
ship. Override is available via `/build --skip-journey-check="<reason>"`
with the reason logged to the verification + release-notes audit trail.

## Why this matters

Capability-shape PRDs accumulate. Journey-shape PRDs converge. If your
PRD pile is growing but your product isn't reaching shippable, you may
have the same problem the team that filed this feedback had: ten months
of capability specs that never intersected on a single customer journey.

Capture a journey. Read it back to the SME. The gaps the SME points out
are the features you forgot to file.
