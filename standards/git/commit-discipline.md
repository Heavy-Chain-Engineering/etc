# Git Commit Discipline — Parallel-Agent Safety

When multiple agents may be writing commits in the same repository at
the same time (e.g. a `/build` wave that dispatches three frontend
agents in parallel), the shared git index is a race condition waiting
to fire. The canonical "add then commit" pattern that humans use is
**wrong** in parallel-agent contexts, because `git commit` commits the
entire index — not just what you just staged. Another agent's staged
files silently become part of your commit.

## The Rule

In any parallel-agent context, **always use `git commit <paths>`, never
`git add <path> && git commit`**. Passing explicit paths to
`git commit` uses the working-tree-to-commit path that bypasses the
shared index for those files, so you commit exactly what you name and
nothing else.

```bash
# WRONG — commits whatever is in the index, including other agents' work
git add 'frontend/src/routes/_auth/clients/index.tsx'
git commit -m "feat: add client detail route"

# RIGHT — commits exactly the named paths, ignores other staged files
git commit -m "feat: add client detail route" -- \
  'frontend/src/routes/_auth/clients/index.tsx' \
  'frontend/src/routes/_auth/clients/index.test.tsx'
```

Additional rules that follow from the same principle:

1. **Never run `git add .`, `git add -u`, or any glob pattern** in a
   parallel-agent context. The index is shared; globs see everyone's
   work and sweep it into your commit.
2. **Deletes:** use `git rm --cached <path>` then `git commit <path>`.
   Plain `git rm <path>` also modifies the shared index.
3. **If you absolutely must stage** (e.g. to preview a diff with
   `git diff --cached`), reset the index afterward with
   `git reset HEAD` before committing — but prefer the direct
   `git commit <paths>` form so you never touch the index at all.
4. **High-collision-risk work** — multi-agent refactors where each
   agent touches more than three files — should run each agent in a
   git worktree via `isolation: "worktree"` on the `Agent` call. Each
   worktree has its own index, which eliminates the race entirely.

## Why This Rule Exists

The git index is process-shared state within a single working tree.
Two agents in the same repo share one index, and `git commit` (with no
path argument) commits whatever is sitting in that index at the moment
the command runs. The convention most humans follow — `git add <path>`
then `git commit` — assumes a single-writer world. In a multi-writer
world it's a straight-up race condition:

- Agent A stages `file_a.tsx`.
- Agent B stages `file_b.tsx` (index now contains both).
- Agent A runs `git commit -m "..."` and gets a commit containing
  both files, including `file_b.tsx` which is outside its
  `files_in_scope`.
- Agent B runs `git commit -m "..."` and gets an empty commit — or,
  worse, picks up whatever agent C has since staged.

Recovery is possible via `git reset --soft HEAD~1` + re-stage, but it
burns 5-10 minutes per agent, and on a less-defensive agent it can
produce wrong commits that land and break the build. The cheaper fix
is to never touch the index in the first place.

`git commit <paths>` has been supported by git since forever. It reads
the working tree, compares against HEAD, and commits the named paths in
one operation — no index involvement for those files. Agents reading
human-oriented git advice inherit the `add`-then-`commit` bug because
the advice was written for a single-writer context. The rule above
corrects for that.

## The Ordering Heuristic

When an agent in a parallel-dispatch context needs to commit files,
apply this order:

| Step | Action | When |
|------|--------|------|
| 1 | `git commit -m "..." -- <paths>` | Default — always prefer this |
| 2 | `isolation: "worktree"` on the `Agent` call | High-collision work (3+ files per agent, multiple agents) |
| 3 | `git add <paths>` + `git commit <paths>` + `git reset HEAD` | Only if you must preview the diff first |
| 4 | `git add <path> && git commit` | **Never** in a parallel context |

If you hit step 4, you have the bug. Back out and use step 1.

## Origin

This rule was adopted on **2026-04-15** after a `/build` run in the
`venlink-platform` repository. During execution of the
`vendor-perspective-client-detail` feature, three of five parallel
frontend agents (tasks 002, 003, 004) independently hit the same
git-index-race problem on a shared worktree:

- **Task 002** (`clients/index.tsx`) had its files captured by task
  003's commit, ran out of time mid-recovery, and had to be finalized
  by the orchestrator.
- **Task 003** (`clients/$id.tsx`) saw task 002's files get swept into
  its first commit; amended to exclude.
- **Task 004** (vendors redirect) saw task 005's already-staged
  deletions accidentally included in its first commit; amended to
  restore them.

Total recovery time was ~10 minutes across the three agents. The cost
was bounded only because the agents were able to self-diagnose via
`git diff --cached`. On a smaller model, or a less-defensive agent,
this same pattern could have produced wrong commits that landed and
broke the build, or fully-stuck agents that burned their time budget
without recovery.

The harness-feedback Stop hook captured the finding, flagged it as a
repeated-mistake pattern (same race hit by three independent agents in
one wave), and routed it back to this repo for codification as a
cross-project standard.

## How This Gets Enforced

This standard lives in two places by design:

1. **Canonical reference** — this document at
   `standards/git/commit-discipline.md`. It's the place a human or a
   deep-reading agent goes to understand the full rule, the rationale,
   and the examples.
2. **Inline onboarding injection** — a condensed five-bullet version
   in `hooks/inject-standards.sh` under the "Git Commit Discipline
   (parallel-agent safety)" section. Every subagent spawned by the
   harness — whether via `/build`, `/implement`, or a direct `Task`
   dispatch — sees this condensed rule at spawn time, before it does
   any work.

The dual placement matters. The standards doc is the canonical
reference for humans and for agents that read deeply; the inline
injection is what fires from working context the moment a parallel-
dispatched agent reaches for `git add && git commit`. Neither layer
alone is enough — the doc can be missed if an agent doesn't think to
read it, and the inline version lacks the examples and the origin
story that make the rule durable.

There is no mechanical hook that blocks `git add <path> && git commit`
in a parallel context, because "am I in a parallel context?" is not
something a git pre-commit hook can reliably answer from inside a
subagent shell. Enforcement is via context injection and the origin
story — the rule fires from working context because every agent sees
it at spawn, alongside the war story that explains why it matters.

## When to Break This Rule

There is exactly one case where `git add <path> && git commit` is
acceptable: **you are operating in a single-agent context with no
concurrent writers to the same repo**. A background agent running
solo, a foreground human session, or any dispatch where no other
process is touching the same working tree — those contexts are
race-free and the human convention is fine.

If you are ever unsure whether you are in a parallel context, the
answer is to use `git commit -m "..." -- <paths>` anyway. The path
form is safe in all contexts; the `add`-then-`commit` form is safe
in only one of them. Prefer the one that can't go wrong.
