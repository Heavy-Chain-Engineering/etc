# Release Notes — Architecture Baseline for Brownfield Projects

**June 12, 2026**

## Who this is for

Teams running etc on an existing codebase — especially one that grew organically,
spans more than one repository, or carries conventions that live in senior
engineers' heads rather than in writing. If you have ever watched an AI agent put
a file in a defensible-but-wrong place, this release is for you.

## The problem this solves

On a brownfield codebase, an AI agent learns "how we do things here" by reading
your code and docs. That fails in two directions at once. If your conventions are
unwritten, every wrong choice has *some* precedent somewhere in the repo, so the
agent picks one confidently. And if your docs are stale or aspirational, the agent
trusts them and builds against a world that no longer exists. A recent client
engagement showed both failure modes in one feature: real conventions nobody had
written down, and an onboarding doc that misdescribed the system boundary. The
team spent the better part of a week cleaning up code that was plausible in every
local decision and wrong in aggregate.

## What's new

### `/init-project` gains an architecture-baseline phase

On brownfield repos, initialization now runs a four-step loop:

1. **Discover.** Parallel agents inventory your existing architecture docs,
   measure how consistently your code follows its own patterns, rank candidate
   "golden exemplar" modules, and detect cross-repo seams (a frontend loaded by
   another repo, a database schema owned elsewhere).
2. **Verify.** Every load-bearing claim in a discovered document is checked
   against the actual code and classified: VERIFIED, STALE, ASPIRATIONAL, or
   CONTRADICTED — each with file-level evidence. **Documentation is treated as a
   set of claims, not facts.** Only verified claims flow into agent context
   silently; everything else comes to you. This applies to etc's own previously
   generated files too — the harness fact-checks itself on re-runs.
3. **Ratify.** You — a human — walk through the findings and bless the target:
   which modules are the examples to copy, which are marked do-not-copy, how each
   cross-repo seam is owned, and what the repo's architecture-confidence score is.
   Nothing is ever auto-blessed. Your decisions land in two places: a readable
   `ARCHITECTURE.md` at the repo root, and a machine-readable baseline that the
   build system enforces.
4. **Enforce.** Ratified rules are wired into your existing lint/boundary tooling
   where possible, or into a generated checker otherwise — and they run at every
   build gate from then on.

In the first field run, the verify step flagged 49 stale, aspirational, or
contradicted claims in a client's existing docs — including security mandates the
docs promised and the code no longer kept. Those findings surfaced *before* any
feature was built on top of them.

### Workspace mode: multi-repo systems are first-class

Run `/init-project` from a directory containing several repos and it initializes
each one, then builds a single **seam map**: which repo owns the URLs, the
login/session handoff, the shared database schema, the embed points. Each repo
also keeps a local copy of the seams that touch it, so nothing is lost when a
repo is cloned alone. "Worked on my machine, broke in the deployed environment"
very often lives in exactly these seams — now they are written down and checked.

### `/rule-sweep`: turn a review comment into a permanent rule

When a reviewer spots a repeatable miss ("DTOs never carry runtime logic"), one
command captures the rule with provenance, sweeps the whole repo for violations,
dispatches fixes, reports honestly on anything it could not safely fix, and adds
the rule to the conformance checker. The convention stops depending on reviewer
memory. This pattern was invented ad hoc by a client team under deadline
pressure; it worked so well we made it a first-class capability.

### Builds respect the baseline

`/build` now checks the baseline before starting work:

- **No baseline** (every pre-existing project): a gentle warning with a one-line
  offer to backfill. Nothing breaks; adoption is a ramp, not a flag day.
- **Baseline started but never ratified:** the build stops and asks you to finish
  — building against a half-verified picture of your architecture is exactly the
  failure this release exists to prevent.
- **Ratified:** the conformance checker runs at every build checkpoint.

`/spec` and `/architect` warn (without blocking) when the architectural ground
truth is unverified, so authors know what they are standing on.

## Fixes

- **Janitor trust graduation works now.** A crash in the trust-reconciliation
  step meant clean-merge streaks were never credited, so no cleanup category
  could ever graduate from preview to autonomous. Any GitHub CLI hiccup now
  degrades to a safe no-op instead of crashing, and streak crediting functions.
- **Hardening from review:** path-containment checks on rule-driven file scans,
  validation of profile names before script dispatch, stricter shell error
  handling in the new hooks, and an explicitly documented allowlist for
  build-invoked verification hooks.

## Numbers from this release

- 16 tasks across 5 build waves; ~2,660 tests passing at close, zero failures.
- 15 of 15 acceptance criteria verified, including a live acceptance run against
  a real two-repo client system (results recorded anonymized).
- Five architecture decision records accompany the feature for anyone who wants
  the reasoning behind the design.

## What to do after upgrading

1. Re-install: `python3 compile-sdlc.py spec/etc_sdlc.yaml && ./install.sh`.
2. On your next brownfield project: `/init-project` and budget ~30–60 minutes for
   the ratification session — it is the highest-leverage hour you will spend on
   the project.
3. Already-initialized projects: run `/init-project --phase=baseline` to backfill
   at your convenience. Nothing forces you; the build will simply remind you.
