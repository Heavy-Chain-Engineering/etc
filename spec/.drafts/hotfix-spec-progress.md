# /hotfix — /spec Progress Capture (2026-04-14)

Session paused mid-Phase-1 because the v1.5.1 harness-feedback hook had
a prompt bug that spammed every Stop event with evaluator prose. Fix
was committed (`822aa13` — the strict-silence rewrite) but could not
take effect mid-session because Claude Code caches hook configuration
at session start and ignores in-session edits. Resume /spec in a fresh
session; the fix will be active from turn one.

## Feature

`/hotfix` — the third lane for incident response, described in
`spec/hotfix-skill-brief.md`. Companion PRD to `/spec` and `/build`.

## Phase 1 Answers So Far

### Q1: Problem
Covered by the brief. Production incidents need a lane that trades
upfront ceremony for speed and reclaims accountability via a
post-incident `/postmortem` bridge.

### Q2: Users
Covered by the brief. The operator during an incident (human running
Claude Code with production on fire). Not other agents, not automated
systems.

### Q3: Success
Mostly covered by the brief. Sharpen measurable criteria in Phase 3:
- ≤30 seconds from incident recognition to `/hotfix` filed
- Every `/hotfix` invocation produces an incident log entry
- Every completed `/hotfix` auto-suggests `/postmortem`
- Zero DoR evaluation, zero three-state classifier run, zero
  `/build`-style decomposition

### Q4: Out of scope
Covered by the brief (no /spec routing, no /build routing, no DoR).
Extend in Phase 3 with: no alerting integration, no PagerDuty hooks,
no automatic rollback detection — hotfix is manual-trigger only.

### Q5: Constraints
To be elicited in Phase 3 from the gray areas below.

## Gray Areas Answered Mid-Session

### GA-HF-001 — Execution model

**Decided:** Option 2 — `/hotfix` records an intent and dispatches to
a specialized subagent pre-authorized to bypass specific gates. The
subagent carries the incident context; the SubagentStop adversarial
review hook still fires on the way out so the fix gets a hostile
review before the session ends.

**Rationale:** Option 1 (direct execution) is too trusting — no agent
review of the fix. Option 3 (advisory only) is too slow — user has to
context-switch back to executing. Option 2 threads the needle: fast
ceremony (3 questions), fast execution (subagent), and the existing
hostile-review sensor still fires.

**Decided by:** user

## Gray Areas Pending

### GA-HF-002 — Gate bypass policy (NOT YET ANSWERED)

Which existing gates does the `/hotfix` subagent bypass, and which
still fire? Proposed default:

| Gate | Proposed | Rationale |
|---|---|---|
| safety-guardrails (rm -rf, force push, DROP TABLE) | **still fires** | Dangerous commands during incidents are more dangerous, not less |
| tier-0-preflight (DOMAIN.md, PROJECT.md must exist) | **still fires** | If missing, the harness shouldn't have been active at all |
| tdd-gate (test before source) | **bypass** | TDD during an incident is the wrong priority; postmortem reclaims it |
| check-invariants (INVARIANTS.md contracts) | **still fires** | Invariants exist because they should never break, including in fixes |
| enough-context (requires_reading) | **bypass** | No task file means no requires_reading to enforce |
| phase-gate (SDLC phase permissions) | **bypass** | Hotfix is its own lane with no phase |

Open refinement: **should tdd-gate bypass be conditional on fix type**
— e.g., "bypass allowed only if the fix is a git revert, a config
flip, or a dependency rollback — NOT for new code additions, which
must still write the failing test first"? This prevents hotfix from
becoming a general TDD escape hatch during incidents.

### Remaining gaps to elicit in Phase 1/2 after restart

- **Incident log format and location** — fields, path, rotation.
  Candidates: `.etc_sdlc/incidents/{YYYY-MM-DD}-{slug}.md`.
- **Concurrency semantics** — can two hotfixes run simultaneously?
  What if `/build` is mid-pipeline? What about rollback-of-rollback?
- **How the three questions are asked** — AskUserQuestion Pattern A
  or visual-marker Pattern B. Lean toward Pattern B for speed.
- **Security considerations** around the gate bypasses — can the
  lane be abused to intentionally bypass TDD/context gates by
  invoking `/hotfix` on non-incident work?
- **Module structure** — skill file, DSL entry, new hooks (if any),
  test file locations.

## How to resume

After restarting Claude Code (so the strict-silence hook fix takes
effect), run:

    /spec spec/hotfix-skill-brief.md

The /spec skill will re-enter Phase 1. Point it at this progress file
in the first message so Phase 1 doesn't re-ask Q1-Q5:

> Resume from spec/.drafts/hotfix-spec-progress.md. Phase 1 Q1-Q4
> covered in the brief, Q5 pending, GA-HF-001 answered (execution
> model = option 2 subagent dispatch), GA-HF-002 pending (gate-bypass
> split). Continue from GA-HF-002.

## Why this session burned so many turns on hook debugging

The v1.5.1 harness-feedback hook was shipped this session and had a
prompt bug (verbose silent response) that fired for the first time
live in this very session. Three mid-session fix attempts failed
because Claude Code caches hook config at session start; the fix is
committed and will take effect on the next Claude Code restart.

This is itself a v1.5.2 candidate lesson worth a `📬` block *after*
the restart-and-verify step:

> **Trigger:** near-miss-gate / framework-surprise
>
> **What happened:** harness-feedback shipped with a silent-case
> instruction weak enough that the LLM evaluator returned prose
> reasoning alongside the JSON. Bug discovered on first live firing.
> Fix landed but could not be verified in-session because Claude
> Code caches hook config at session start.
>
> **Proposed rule:** add `scripts/test-hook-prompt.py` — a local
> fixture-based runner that invokes prompt hooks against synthetic
> session fixtures and asserts response shape. Closes the prompt
> test loop without requiring a Claude Code restart.
>
> **Origin trace:** ~7 turns of this 2026-04-14 session spent
> attempting to silence a hook mid-session. None of the attempts
> took effect because the settings cache is frozen. The local
> fixture runner would have verified the `822aa13` fix in one
> command instead of seven.
