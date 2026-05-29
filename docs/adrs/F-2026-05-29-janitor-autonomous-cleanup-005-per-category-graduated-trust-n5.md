# ADR-005: Per-category graduated trust, auto-promote at N=5 clean merges

**Date:** 2026-05-29
**Status:** Accepted
**Context:** Janitor must become more hands-off over time without the operator
manually blessing each category. We need a rule for when a fix-category stops
opening DRAFT PRs (operator reviews each) and starts opening ready-for-review
PRs (autonomous). The options were: operator-manual promotion, auto-promote after
N clean merges, or preview-only-forever in v1. The CTO chose auto-promotion
(Dependabot merge-confidence analog).
**Decision:** Trust is tracked PER CATEGORY in `trust.yaml`, not globally. Every
category starts in `preview`. A category auto-promotes to `autonomous` when its
derived clean-streak (ADR-003) reaches **N = 5** consecutive clean merges. A
merged-with-edits or closed-unmerged janitor PR resets that category's streak to
0 (and, if it was autonomous, the next reconciliation can only keep it autonomous
while the streak stays ≥ N — a reset drops it back to preview). N is a tunable
constant, not a permanent contract; 5 is a conservative start (~2-3 weeks of
nightly clean runs before any category goes hands-off). The operator can always
`/janitor trust demote <category>`.
**Consequences:**
- *Easier:* hands-off coverage grows automatically as categories prove
  themselves; no manual-promotion toil; per-category granularity means a risky
  category never rides a safe category's trust.
- *Harder:* a category could graduate on 5 easy diffs and then meet a hard case
  autonomously — mitigated because the boundary check (BR-005) and the
  verification gate (BR-009) STILL run in autonomous mode, and the operator can
  demote at any time.
- *Tunable:* N lives in one constant; raising/lowering it is a one-line change as
  empirical merge-clean data accumulates.
