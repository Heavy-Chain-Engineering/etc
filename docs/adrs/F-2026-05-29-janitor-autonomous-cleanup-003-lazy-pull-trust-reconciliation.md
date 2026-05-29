# ADR-003: Trust streaks are derived from git/gh history, reconciled lazily at run start

**Date:** 2026-05-29
**Status:** Accepted
**Context:** A fix-category graduates preview→autonomous after N consecutive
janitor PRs merge with zero operator edits (BR-008). The clean-streak therefore
depends on MERGE OUTCOMES, which happen after janitor's run ends — janitor
cannot know at PR-open time whether the PR will merge clean, merge with edits,
or be closed. We need a way to learn merge outcomes without a daemon, webhook,
or watching process (the spec is skill-only, no scheduler — GA-001).
**Decision:** Clean-streaks are DERIVED, not authoritatively stored. At the
START of each run, `janitor_trust.py reconcile` queries
`gh pr list --author <janitor> --state merged|closed --limit N`, joins against
the `runs.jsonl` ledger by branch name, classifies each prior janitor PR as
clean-merged (zero commits after janitor's initial commit) / merged-with-edits /
closed-unmerged, recomputes each category's consecutive-clean streak
(newest-first, reset on first non-clean), and persists the result to
`trust.yaml`. Git+gh is the system of record; `trust.yaml` is a rebuildable
cache. If `gh` is unavailable, reconciliation is a no-op and `trust.yaml` is left
untouched (never falsely promotes).
**Consequences:**
- *Easier:* no daemon/webhook; `trust.yaml` can always be rebuilt from history;
  survives a deleted/corrupt cache (defaults to preview); single-writer
  (`janitor_trust.py`) keeps mutation centralized.
- *Harder:* trust is eventually-consistent — a category promotes on the *next*
  run after its Nth clean merge, not the instant it merges; chronic `gh` outage
  freezes promotion in `preview`.
- *Accepted:* eventual consistency is fine for a nightly tool, and freezing in
  the safe (preview) direction is the correct failure mode.
