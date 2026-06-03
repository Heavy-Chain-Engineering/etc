# ADR F-2026-06-02-build-review-agent-gate-002: review_gate.py helper owns the mechanics; the build skill orchestrates

**Date:** 2026-06-02
**Status:** Accepted

**Context:**
The review gate needs to: derive the changed fileset, decide whether
architect-reviewer fires (architectural-impact signal), parse the per-agent
structured-findings blocks (ADR-001), aggregate to a block/proceed decision, and
emit the `verification.md` Review Findings fragment. This mechanical work could
live inline in the build skill body or in a helper script.

**Decision:**
A new `scripts/review_gate.py` helper owns all the mechanical work; the build
skill ORCHESTRATES (issues the parallel Agent dispatches with the ADR-001
emission contract in each prompt, then reads `review_gate.py`'s verdict). This is
the 6th sibling in the established etc gate-helper family
(`spec_enforcer_chunker.py`, `layer_review.py`, `journey_lineage_check.py`,
`spec_coupling_check.py`, `runtime_totalization_check.py`).

CLI surface:
- `review_gate.py plan --feature-dir <dir>` → JSON: which review agents fire
  (code-reviewer + security-reviewer always; architect-reviewer iff
  `layer_review.py detect` returns non-empty AND not `infrastructure_only`), plus
  the changed fileset (union of wave-task `files_in_scope`, git-diff cross-check —
  ADR GA-003).
- `review_gate.py aggregate --findings <files...>` → exit 0 (proceed) / exit 2
  (block: ≥1 CRITICAL/HIGH or an unparseable/INSUFFICIENT_EVIDENCE block) / exit 1
  (usage/IO); emits the max-severity verdict + the `verification.md` fragment.

**Consequences:**
- *Easier:* deterministic, unit-testable mechanics (the firing decision, the
  parse, the aggregation) isolated from the LLM dispatch; consistent with every
  other etc gate; the skill body stays an orchestrator, not a parser.
- *Harder:* one more helper to maintain + keep dist-mirrored (it rides the broad
  `scripts/` copy, like its siblings — verified, not the narrowed-glob failure
  mode). The architect-reviewer firing decision reuses `layer_review.py detect`
  rather than re-implementing layer detection — single source of truth.
- The skill ↔ helper split matches "skill orchestrates, helper does mechanical
  work" and keeps the blocking logic deterministic (a noisy LLM can't accidentally
  flip the gate; only a parsed CRITICAL/HIGH does).
