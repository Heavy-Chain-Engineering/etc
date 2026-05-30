# ADR F-2026-05-30-lessons-terminate-in-gates-001: Explicit `terminates_in` field + union lesson-class classifier

**Date:** 2026-05-30
**Status:** Accepted

**Context:**
etc's feedback loop leaks: lessons flow incident → retro → memory, but not
memory → enforced gate. The pbj retro named this the deepest cause (the F001
runtime gate was written as a lesson and never built; the incident recurred
3+ times into a paying client). To make the leak measurable, the audit must
(a) know which gate a lesson terminates in, and (b) reliably identify which
memories are lessons.

Two forces:
1. *How does the audit know a lesson has a gate?* A heuristic lesson↔gate
   matcher repeats the #54 subject-matter-detection fragility (false
   "covered"/"unguarded"). The pbj trilogy (Gap B conflict-sources, Gap A
   liveness, Gap C prototype declaration) converged on **explicit declaration
   over heuristic inference**.
2. *How does the audit identify a lesson-class memory?* The spec's BR-001
   keyed on `metadata.type ∈ {feedback, lessons}`. A live corpus probe
   (2026-05-30, 44 files) falsified that as sufficient: 23 files use a flat
   top-level `type:` (older shape), no `lessons` type value exists in the
   wild, and 2 files named `lessons-*` are typed `project`. BR-001 as written
   would silently exempt half the corpus and the 2 mis-typed files. The
   value-hypothesis's own `current_cost` counts "23 feedback-/lessons- files"
   BY FILENAME.

**Decision:**
1. Each lesson-class memory carries an explicit `terminates_in:` frontmatter
   field: a gate-ref path (`standards/…`, `hooks/…`, `scripts/…`, or a
   `skills/…/SKILL.md` step-ref), or `none-yet: #<tracker>`, or `note-only`;
   a YAML list when it terminates in multiple gates. The audit reads the
   declaration — it never infers a gate by matching subject matter.
2. The classifier identifies a lesson-class memory by the **union**: filename
   starts `feedback-`/`lessons-` **OR** `type` (read from nested
   `metadata.type` OR flat top-level `type`) is `feedback`/`lessons`. This
   **revises spec BR-001** (type-only) to match the real corpus and the
   operator's filename-based count.

**Consequences:**
- *Easier:* honest, mechanical classification with no false "covered"; all 23
  operator-counted files are audited, including the mis-typed `lessons-*`
  ones; robust to both frontmatter shapes.
- *Harder:* the operator must declare `terminates_in` per lesson — mitigated
  by the `/harness-feedback` + `/postmortem` write-time prompts (BR-004) so
  new lessons are born with the field.
- The union can flag a hypothetical `feedback-`-named file that is genuinely a
  `reference` note; the `note-only` value is the escape hatch (declares it
  intentionally not gate-able).
- Revises BR-001; the spec's literal text is superseded by this ADR. Recorded
  as GA-001 (`decided_by: user`).
