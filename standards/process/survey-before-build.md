# Survey Before Build

## Status: MANDATORY
## Applies to: any agent that creates new source files

Before deciding to create a new file, you MUST establish that no
existing file in the codebase already does (or could do) the job.

## The rule

1. **List the directory where the file would land.** Read the listing.
   Don't skim. Don't rely on prior context — another agent may have
   added or moved files since.
2. **Search the codebase for siblings** that touch the same domain
   entity or solve a similar shape — by name, by data source, by import
   graph. Cast a wider net than the immediate directory; cross-cutting
   concerns often have a canonical home elsewhere.
3. **For every plausible candidate, choose one of:**
   - **Compose** it — use it directly from the new caller.
   - **Extend** it — widen its props, parameters, or scope so it fits
     both the existing and the new use case.
   - **Reject** it — and name the specific reason (different scope,
     different data contract, different lifecycle, different security
     boundary). Vague reasons are not acceptable.
4. **"I didn't see one" is not a valid rejection.** It means the survey
   was incomplete; do it again.
5. **Surveys are per-task.** Re-list the directory and re-grep at the
   start of each task. Prior context goes stale fast — once another
   agent has run, your mental model of the tree is out of date.

## What this prevents

The recurring failure mode is parallel implementation: a new feature
arrives, the agent reads only the spec, and produces files that solve
the same problem as files that already exist — usually with a
different naming convention so the duplication isn't obvious until a
human reviewer notices. The cost is paid forever after: every change
to the domain entity touches two implementations, drift between them
becomes a bug surface, and the codebase reads as if multiple teams
worked in isolation.

The cure is mechanical: list the tree, search for siblings, justify
the choice. Five minutes at the start of a task saves hours of cleanup
afterward.

## Enforcement

This step is surfaced two places today:

1. **DoD checkboxes** — `definition-of-done.md` Code section *and* the
   tracker's Build-phase items in `.sdlc/dod-templates.json`. Marking the
   box requires the agent to have done the survey and recorded
   candidates/rejections somewhere a reviewer can read them (design note,
   PR description, or feature directory).
2. **Code Reviewer audit** — the `code-reviewer` agent reads this
   standard in its required-reading list and flags PRs whose survey
   rationale is missing or vague ("I didn't see one" is not valid).

**What's not yet automated:** there is no script or hook that mechanically
greps for survey evidence at task-completion time. The `verifier` agent
runs the test / coverage / type / lint gates only — it has no detector
for missing surveys. A mechanical gate (probable shape: `Survey:` block
in a known artifact location, validated by a small script invoked from
the verifier) is a planned follow-up; until it lands, enforcement is
honor-system at the agent level and audit-by-reviewer at the PR level.

When you reject a candidate, record both the candidate and the reason
in your design note or PR description. A reviewer should be able to
read the rejection list and agree with each call without asking you
what you considered.

## Related

- `standards/process/user-flow-completeness.md` (F001) — closes the
  inverse failure mode: a new surface ships but no navigation reaches
  it. Survey-before-build catches new code that duplicates existing code;
  user-flow-completeness catches new code that no user can reach.
- `scripts/tasks.py` wave-planner (F008) — closes the wave-level analog:
  two tasks in the same `/build` wave claim overlapping files. The wave
  planner rejects the plan before dispatch. Survey-before-build is the
  task-level scale-down: one agent, deciding whether to add a sibling
  file at all.
