# Lessons Terminate in Gates

## Status: MANDATORY
## Applies to: the harness's own lesson-capture loop

## The Problem

etc's feedback loop leaks. Lessons flow incident → retro → memory, but not
memory → enforced gate. A lesson written down is *recorded*, not *built*: it
sits in operator memory as prose, and unless a human turns it into a gate — a
standard, a hook, a skill-step — the same failure recurs.

In the covr.care `pbj` build, exactly this happened. The F001 runtime gate was
written down as a lesson at F001 and **never built**. The leak was invisible —
no memory file declared whether it had terminated in a gate — so the loop went
unmeasured and the incident recurred 3+ times into a paying client (one feature
became seven tags). A written-down lesson that is never built is the deepest
cause in the pbj retro.

This standard makes the feedback loop visible and contractual so a lesson can
never again be silently never built.

## The Rule

Every **lesson-class** memory declares where it terminates. Lesson-class =
filename starts `feedback-`/`lessons-` **OR** `type ∈ {feedback, lessons}`
(either frontmatter shape) — the union classifier (ADR-001). Non-lesson memory
(`user` / `project` / `reference`) is exempt.

1. **Declare `terminates_in`.** Every lesson-class memory carries a
   `terminates_in:` frontmatter field. Its value is one of three forms:
   - a **gate-ref path** — a path under `standards/`, `hooks/`, `scripts/`, or
     a `skills/…/SKILL.md` step-ref (the gate that now enforces the lesson);
   - **`"none-yet: #<tracker>"`** — declared-open, with an actionable tracker
     reference (a `#<tracker>` token is REQUIRED; without it the loop is not
     actionable and is treated as `missing`). When NO gate exists yet, emit
     the **quoted sentinel** `terminates_in: "none yet"` (or
     `"none-yet: #<tracker>"` once a tracker is filed) — **never** a blank or
     unquoted value;
   - **`note-only`** — a deliberate non-gating note (closed by declaration, not
     flagged).

   When a lesson terminates in multiple gates, `terminates_in` is a **YAML
   list**; **all** entries must resolve to an existing path or the lesson is
   dangling.

   **Quote the none-yet sentinel (write-time, #58).** A `none-yet` value
   carries a `:` and a `#` and so MUST be written as a **quoted YAML scalar**
   (`terminates_in: "none-yet: #54"`). Written bare, `none-yet: #54` is a YAML
   error (`mapping values are not allowed here`) that makes the whole
   frontmatter fail to parse — the audit then reports the lesson as `missing`
   "frontmatter unparseable", masking every other field. A blank value
   (`terminates_in:`) parses to `null` and is equally useless. Always emit a
   quoted scalar so the value round-trips. The audit accepts either spacing
   (`none yet` / `none-yet`) and classifies a tracker-less sentinel as
   `missing` (open loop, no landing place) and a tracker-bearing one as
   `none-yet` (open but tracked).

2. **The audit reads the declaration, never invents it.**
   `scripts/lesson_gate_audit.py` scans the memory directory and classifies
   each lesson-class memory into one of **five states**:
   - **gated** — `terminates_in` names an existing gate (loop closed).
   - **none-yet** — declared-open with a tracker (loop open, but tracked).
   - **note-only** — a declared note (loop closed by declaration).
   - **missing** — no `terminates_in` field (open loop; the unmeasured leak).
   - **dangling** — names a gate path that does **not** exist (gate-rot or a
     never-built claim — caught distinctly from `missing`).

   Open loops = `missing` + `dangling` + `none-yet`.

3. **Born with the field.** `/harness-feedback` and `/postmortem` prompt for
   `terminates_in` at lesson capture, so new lessons are declared at birth.
   `/metrics` surfaces the "Feedback-loop closure" section (% terminated-in-gate
   + the open-loop list) so the leak is visible on every report.

The declaration is **explicit, never heuristic** (ADR-001): the audit validates
the declared path's existence; it does **not** guess a lesson↔gate match from
prose. Explicit declaration over heuristic inference is the trilogy principle.

## Always In Force

This rule is **standing and MANDATORY**. It is **never re-litigated per
lesson** — declaring `terminates_in` is the default for every lesson-class
memory, not a per-capture decision.

The audit is **advisory, never a CI hard-block** (ADR-002): memory is
operator-machine-local and gitignored, so the CI runner cannot see it. The
audit is a report/nudge; any non-zero exit is informational only. Closure
depends on operator attention — which is exactly why `/metrics` surfaces it
every report.

Backfill is **forward-only** (BR-006): existing lessons are **never
auto-mutated**. They surface as `missing` for operator backfill (many fill
immediately — runtime→Gap A, contract→Gap B, prototype→Gap C, #54/#55→their
fixes). The operator decides the gate; the harness never fabricates one.

## Cross-References

- `docs/adrs/F-2026-05-30-lessons-terminate-in-gates-001-explicit-terminates-in-union-classifier.md`
  — explicit `terminates_in` field + the union lesson-class classifier
  (filename-prefix OR dual-shape `type`, because the corpus carries two
  frontmatter shapes and 2 mis-typed `lessons-*` files).
- `docs/adrs/F-2026-05-30-lessons-terminate-in-gates-002-advisory-machine-local.md`
  — advisory-only, machine-local; never a CI hard-block.
- `docs/adrs/F-2026-05-30-lessons-terminate-in-gates-003-metrics-surfacing-standalone-engine.md`
  — `/metrics`-not-`/janitor` surfacing + a standalone reusable engine.
- `scripts/lesson_gate_audit.py` — the audit engine. This standard states the
  RULE; the script carries the classification mechanism.
- `standards/process/prototype-as-intent.md` — the sibling standing standard
  (Gap C of the pbj retro); this rule closes the loop on the harness's own
  learning.

**Lineage:** the closed-loop precedents that prove etc *can* close loops —
stub-grep F007, spec-coupling F015, the dist-parity guard — were lessons that
got a gate. The runtime and contract lessons simply never got the field. This
standard makes the field mandatory so no lesson is left ungated by accident.

**Origin:** covr.care `pbj` build retrospective (2026-05-29) — the F001 runtime
gate was written down as a lesson and never built, so the incident recurred 3+
times into a paying client. A written-down lesson that is never built is the
deepest cause; this standard makes the loop visible and contractual.
