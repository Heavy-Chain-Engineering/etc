# ADR-001: Janitor edits in a throwaway git worktree branched off main

**Date:** 2026-05-29
**Status:** Accepted
**Context:** /janitor runs autonomously (including unattended) and opens PRs of
cleanup fixes. The operator's hard requirement: a janitor run must have ZERO
chance of corrupting in-flight work — "if I'm mid-80k-line build, janitor must
not be able to touch it." Logical file-avoidance (janitor *chooses* not to edit
in-flight files) is insufficient because a janitor bug could still write to the
primary working tree. We need a structural guarantee, not a behavioral promise.
**Decision:** Every janitor run materializes a throwaway git worktree
(`git worktree add`) on a fresh branch cut from `main` (`claude/janitor/<category>-<date>`),
regardless of the operator's current branch. All edits, the fix-subagent, and
verification happen inside that worktree only. The worktree is removed on
completion or abort; the branch ref survives. The operator's primary working
tree is never read for mutation and never written. Branch base is always `main`
(not the current branch) so the PR is a clean, independent diff.
**Consequences:**
- *Easier:* isolation is a git property, not a code-correctness property — even
  a janitor bug cannot reach the primary tree; PRs are tight diffs off a known
  base; concurrent operator work is irrelevant by construction.
- *Harder:* each run pays worktree create/teardown (~hundreds of ms + disk); a
  crashed run can strand a worktree dir — mitigated by idempotent teardown and a
  `.etc_sdlc/janitor/` concurrency lock (edge cases 4, 10).
- *Non-negotiable:* this is the load-bearing safety invariant (BR-002, AC-002).
  Builds on F016's worktree-conflict-prevention discipline.
