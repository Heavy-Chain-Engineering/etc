# ADR-F-2026-05-26-003: /architect reasons (interactive walk); /build enforces (completeness gate); advisory-default

**Date:** 2026-05-26
**Status:** Accepted

**Context:** The Layer Impact Analysis must run somewhere and be enforced somewhere. `/architect` is the natural home for the reasoning — it is where design decisions are made — but `skills/architect/SKILL.md` lines 45-52 hard-constrain it to be an interactive Socratic facilitator that MUST NOT dispatch subagents. `/build` is where enforcement gates already live (Step 1c design-coupling, Step 7 spec-enforcer). The question: how to split the responsibility, and how hard to gate.

Two sub-decisions. (1) **Placement:** does the analysis happen at /architect (reason) with enforcement at /build (gate), or somewhere unified? (2) **Teeth:** does an incomplete Layer Impact Analysis hard-block the build, or warn?

The prod-bug evidence cuts both ways on teeth. The miss happened because nothing forced the consideration → argues for hard teeth. But hard-blocking every design on a brand-new framework's completeness check risks false-positive friction that trains operators to override or skip — the F007+F008 trust-chain lesson, where gates that cry wolf get disabled.

**Decision:** Split along the existing skill-capability boundary, advisory-by-default with per-feature mandatory escalation.

- **/architect reasons.** A Layer Impact Analysis phase (after Phase 2 research) invokes `layer_review.py detect` to find touched layers, then walks each layer's rubric interactively (Pattern A/B), the architect producing answer-or-reasoned-N/A per item (ADR-002), and writes the Layer Impact Analysis table into design.md. No Agent dispatch — respects the /architect non-dispatch constraint. The architect also records `architect_phase.layer_review_mandatory: <bool>` in state.yaml.
- **/build enforces.** Step 1c is extended: when design.md is present, run `layer_review.py check`. On an unfilled rubric item for a touched layer: WARN to stderr + record in verification.md, then PROCEED (advisory default). When `layer_review_mandatory` is true, an unfilled item with `severity_if_missed: CRITICAL` HARD-fails the build until filled or explicitly overridden.

This mirrors F006's `design_mandatory` soft-coupling exactly (warn-not-block default; opt-in hard gate), and reuses the established /build gate placement (Step 1c).

**Consequences:** *Positive:* respects the /architect non-dispatch invariant — no change to /architect's interactive nature; reuses /build's existing gate machinery (Step 1c) and the F006 soft-coupling pattern operators already understand; advisory default avoids the cry-wolf failure that disables gates; mandatory escalation gives teeth where a team wants them, scoped CRITICAL-only to avoid friction on hygiene items; the architect makes the decisions where decisions belong (design time), the build verifies completeness where verification belongs (gate time). *Negative:* the analysis and its enforcement live in two skills, so a change to the table format must update both /architect (writer) and /build (checker) — mitigation: both go through `layer_review.py`, which owns the format contract, so neither skill reimplements it; advisory default means a careless team CAN ship an incomplete analysis (the warning is recorded but not blocking) — mitigation: the matrix walk at /architect time is the primary forcing function; the /build gate is the backstop, and mandatory mode is available; two-phase split means a feature that skips /architect entirely has no Layer Impact Analysis to check (EC-002) — /build degrades to the existing F006 soft-warning.

**Alternatives considered:**

*Hard-block by default* (rejected). Any incomplete analysis fails the build. *Positive:* maximum teeth; the prod bug could never recur. *Negative:* a brand-new framework with false positives that hard-blocks trains operators to disable or `--skip` it (F007+F008 trust-chain lesson); the friction lands on every persistence design from day one, before the rubric has been tuned; etc's house style for new gates is soft-default + opt-in hard (F006). Teeth can be escalated per feature; starting hard and loosening is harder than starting soft and tightening.

*Make /architect dispatch a reviewer agent* (rejected). Carve a dispatch exception into /architect for this one reviewer. *Positive:* enforcement co-located with reasoning. *Negative:* breaks the /architect non-dispatch invariant (SKILL.md:45-52) — a load-bearing constraint that keeps /architect a predictable interactive facilitator; opens the door to /architect dispatching arbitrarily, which the constraint exists to prevent; /build already has the gate machinery, so the dispatch exception buys nothing.

*Unified standalone command* (rejected). A `/layer-review` command run independently. *Positive:* single home. *Negative:* a separate command is one more thing to remember to run — exactly the "rely on the human to invoke review" failure that shipped the prod bug; embedding the reasoning in /architect (which every engineering feature already runs) makes it unmissable.

**Related ADRs:**
- F-2026-05-26-001 (declarative registry), F-2026-05-26-002 (matrix-walk) — the reasoning this ADR places + enforces.
- F006 (design_mandatory soft-coupling) — the escalation pattern this mirrors.
- F015 (spec_coupling_check at /build Step 7.5) — sibling /build gate precedent.
