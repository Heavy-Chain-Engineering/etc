# Release Notes — Janitor Published-Asset Guard

**June 12, 2026**

## Who this is for

Anyone running etc's `/janitor` autonomous cleanup on a repo whose files are
deployed to public URLs — landing pages, doc sites, anything with a `public/`,
`static/`, or `www/` directory. And, indirectly, every sibling project that
links to those URLs.

## The incident behind it

A cleanup pass deleted a logo file from a landing-page repo because nothing in
that repo referenced it. Reasonable evidence — for ordinary code. But the file
was served at a public URL, and another project's email templates hotlinked it.
Every subscriber email shipped a broken image for three days, until a
near-cancel-grade complaint surfaced it.

The lesson is structural, not situational: a file served at a public URL is a
**published API surface**. "Unreferenced in this repo" can never prove a
deployed URL is dead, because its consumers live in other repos by definition.

## What's new

**The janitor now treats `public/`, `static/`, and `www/` as published API
surface.** Before deleting anything under those paths, it must do one of:

- **Search the whole organization** for consumers of the file. Zero hits — with
  the search itself succeeding — clears the deletion, and the query, scope, and
  timestamp are recorded in the run's audit trail. Any hit blocks the deletion
  and names the consumer.
- **Ask you**, naming what it knows, if the search can't run.

Three properties worth knowing:

- **Fail closed, always.** If the search tool is missing, unauthenticated, or
  rate-limited, the candidate is *not* cleared — it's dropped (autonomous runs)
  or routed to you (interactive runs). The janitor never falls back to
  repo-local evidence for this file class, and a malformed search result is
  treated as a failure, never as "probably fine."
- **Honest audit trail.** Every published-asset candidate gets a recorded
  verdict — cleared-by-search, cleared-without-needing-search, blocked (with the
  consumer named), or dropped fail-closed. You can always reconstruct why a
  file lived or died.
- **Everything else is untouched.** Ordinary dead-code cleanup (a helper in
  `src/` nobody calls) flows exactly as before — no new searches, no new
  prompts, no slowdown.

The rule applies identically in both janitor lanes: a draft PR awaiting human
review gets the same evidence requirement as an autonomous run, because the
original incident *was* human-reviewed and shipped anyway. Review is not a
substitute for consumer evidence.

## Hardening that rode along

The review gates on this build caught and fixed several things before ship:

- A file *named* like a command-line flag (`--limit`) can no longer corrupt the
  consumer search into a false all-clear.
- Malicious or malformed search responses (bad org names, path-traversal
  tricks) route to fail-closed instead of being trusted.
- The behavior "no search ever runs for ordinary files" is now pinned by a test
  that explodes if anyone wires a search into that path by accident.

## Also in this release

- **Janitor trust graduation fixed** (shipped alongside): a crash in trust
  reconciliation meant clean-merge streaks were never credited, so no cleanup
  category could ever graduate from preview to autonomous. GitHub CLI hiccups
  now degrade safely and streaks credit properly.

## Numbers

- 3 tasks, 2 waves; ~2,780 tests passing at close, zero failures.
- 7 of 7 acceptance criteria verified by adversarial review, including a
  behavioral test that the consumer search can never fire for ordinary files.
- Incident-to-shipped turnaround: same day the report arrived.

## What to do after upgrading

1. Re-install: `python3 compile-sdlc.py spec/etc_sdlc.yaml && ./install.sh`.
2. Nothing else. The guard activates on the next `/janitor` run in any repo
   with deployed-asset directories; repos without them see zero change.
3. If your deploy roots live elsewhere (say, nested `apps/*/public/`), the
   path list is extendable in `standards/process/janitor-write-boundary.md` —
   one line per glob.
