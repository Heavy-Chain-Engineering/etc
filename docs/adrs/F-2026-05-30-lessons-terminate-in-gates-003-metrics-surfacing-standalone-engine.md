# ADR F-2026-05-30-lessons-terminate-in-gates-003: `/metrics`-not-`/janitor` surfacing + standalone reusable engine

**Date:** 2026-05-30
**Status:** Accepted

**Context:**
The feedback-loop closure report needs a home in the harness. Two candidate
surfaces exist: `/metrics` (the established read-only three-layer
process/outcome/cost reporter) and `/janitor` (the autonomous health auditor
that surveys, cleans in worktrees, and opens PRs). The audit logic also needs
to be unit-testable and directly operator-callable, independent of whichever
skill surfaces it.

**Decision:**
1. The engine is a **standalone** `scripts/lesson_gate_audit.py` in the
   helper-script tier (peer to `git_tags.py`, `value_hypothesis.py`,
   `layer_review.py`): frozen-dataclass core + `argparse` CLI emitting JSON on
   stdout, importable functions for tests.
2. The report surfaces in a new **`/metrics` "Feedback-loop closure" section**
   — NOT `/janitor`. `/metrics` invokes the engine CLI by absolute path and
   parses its JSON, exactly as it already does for `value_hypothesis.py load`
   and `telemetry.py aggregate`.
3. Reuse, don't fork (BR-008): the feature is one engine + the `/metrics`
   section + two entry-skill write-time prompts + the `etc_sdlc.yaml`
   compile-wire. No new daemon, no scheduler.

**Consequences:**
- *Easier:* fits `/metrics`' read-only model with zero new machinery; the
  engine stays testable in isolation and callable by the operator on demand;
  the report composes with the existing three layers.
- *Harder:* `/metrics` gains a 4th concern beyond process/outcome/cost —
  accepted, because reporting is precisely `/metrics`' lane and a memory-
  lesson report is read-only (the cross-derivation ban BR-010 is unaffected:
  the new section reads only the engine's output, never the other layers).
- `/janitor` was rejected as the home: it is an autonomous *fixer* (worktree
  cleanup + PRs), and auto-mutating operator memory is explicitly out of scope
  (BR-006, forward-only). A read-only report does not belong in a fixer.
