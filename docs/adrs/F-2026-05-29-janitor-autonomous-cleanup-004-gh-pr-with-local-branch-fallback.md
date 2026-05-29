# ADR-004: gh PR is primary; degrade to a local branch + direct report when gh is unavailable

**Date:** 2026-05-29
**Status:** Accepted
**Context:** Janitor's delivery artifact is always a pull request (BR-007, the
agent-submits-human-merges discipline). But `gh` may be missing, unauthenticated,
or offline — especially in the unattended path. The original spec edge case 12
said "PR-open fails → abort, discard." The CTO refined this: a completed,
verified fix should not be thrown away just because `gh` is unavailable.
**Decision:** Primary delivery is `gh pr create` (draft if the batch's
categories are all `preview`, ready-for-review if all `autonomous`, draft on a
mixed batch). If `gh` is absent or PR creation fails, janitor DEGRADES: it leaves
the already-committed branch (`claude/janitor/<category>-<date>`, cut from `main`)
in place, tears down the worktree (the branch ref survives), and presents the
"Janitorial Services" report directly to the operator — branch name plus the
categorized summary of what's on it — so the operator can review and push/PR
manually. A local-branch-only outcome earns NO automatic trust credit; if the
operator later pushes it into a merged PR, ADR-003's lazy reconciliation credits
it then.
**Consequences:**
- *Easier:* janitor delivers value with no `gh`/network; verified work is never
  lost; isolation (off `main`) holds identically in both paths.
- *Harder:* two delivery paths to build and test; trust accounting must
  distinguish "PR merged clean" from "local branch never merged."
- *Cannot defer:* without the fallback, any `gh` hiccup discards a completed,
  gate-green, boundary-clean fix (edge case 12).
