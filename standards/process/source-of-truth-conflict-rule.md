# Source-of-Truth Conflict Rule

## Status: MANDATORY
## Applies to: /spec, /architect, /build

## The Problem

A build draws on up to three descriptions of the same behavior: the **code**
as written, the **canonical spec** (the `/spec`-produced PRD plus its
acceptance criteria), and a **prototype** (a design mock, reference
implementation, or impeccable-style `DESIGN.md` artifact). When two of them
disagree — the spec says `HH:mm`, the prototype renders `h:mm a`, the code
stores a float — the build has no standing tie-breaker and starts guessing.

In the covr.care `pbj` build, exactly this happened: a `{code, spec,
prototype}` conflict had **no tie-breaker rule until tag 6**. Five feature
tags were spent re-deciding which source won, per disagreement, from scratch.
The cost was not the conflict; it was that the rule was re-litigated every
time instead of being a standing default adopted at kickoff.

This standard makes the tie-breaker a permanent, MANDATORY rule so no build
ever has to invent it again.

## The Rule

When the in-play sources disagree about a behavior or contract:

1. **Majority wins.** Of `{code, canonical-spec, prototype}`, the value
   agreed on by the majority of the *in-play* sources is authoritative. With
   all three in play, two-of-three carries; with two in play, agreement is
   required and any disagreement escalates (see below).
2. **Dissent escalates to the operator.** Any source that disagrees with the
   adopted majority — or any tie where no majority exists — is **not silently
   overridden**. The disagreement is recorded and surfaced to the operator as
   a decision, never resolved unilaterally by the build.
3. **Mark the winning spec copy `[SPEC-WINS]`.** When the canonical spec is
   part of (or breaks) the majority and its value is adopted, the
   authoritative spec text is tagged with the inline marker `[SPEC-WINS]` so
   the resolution is grep-able and the spec is unambiguously the source of
   record for that behavior going forward.

The disagreement is always **recorded, not silently resolved by the build.**

## Always In Force

This rule is **standing and MANDATORY**. It is **never re-litigated per
feature** — adopting it is the default at kickoff, not a per-build decision.
No `/spec`, `/architect`, or `/build` run may opt out of, weaken, or
re-derive the tie-breaker.

What *is* per-feature is the **source set**: `/spec` captures which of
`{code, canonical-spec, prototype}` are in play for a given feature (recorded
as `conflict_sources` in `state.yaml`). A pure greenfield feature may have no
prototype; a refactor may have no separate prototype or fresh spec. The rule
above then applies to whatever subset is in play — the *rule* is fixed, only
the *operands* vary.

## Cross-References

- `standards/process/contract-completeness.md` — the contract classes whose
  disagreements this rule arbitrates; records `conflict_sources` and the
  WARN+recorded-override audit trail.
- `skills/spec/SKILL.md` — captures the in-play source set during `/spec`.
- `hooks/inject-standards.sh` — surfaces this rule to every subagent's
  onboarding context.

**Origin:** covr.care `pbj` build retrospective (2026-05-29) — a
`{code, spec, prototype}` conflict with no tie-breaker until tag 6, after five
tags of per-conflict guessing.
