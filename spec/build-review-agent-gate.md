# PRD: Build-Time Review Gate — Fire the Review Agents at /build Step 7

## Summary

`/build` Step 7 (VERIFY) dispatches **only** `spec-enforcer` for adversarial
acceptance-criteria verification. The `code-reviewer`, `security-reviewer`, and
`architect-reviewer` agents — made stack-correct by F-2026-06-01 (#59) — have
**no firing point** in the pipeline. The consequence: code quality, security,
and architecture are never reviewed at the verification gate. A build can be
spec-COMPLIANT and structurally green yet ship a controller-layering violation,
an unsafe ID generator, a multi-tenant scope leak, or a data-retention leak —
exactly the defect classes the review agents own, and exactly what escaped to a
human reviewer + CodeQL at PR time in the covr-2.0 field report that motivated
#59. Until those agents fire, #59's investment is inert.

This feature gives the review agents a firing point at Step 7. Per the resolved
policy (GA-001): **code-reviewer and security-reviewer fire on every build**
(the two lenses where a missed review = a shipped defect — never gated on
imperfect signal detection), **architect-reviewer fires proportionally** (only
when the change has architectural impact — the one place gating reviews nothing,
so it is relevance, not friction-cutting), and findings are **severity-gated**:
CRITICAL/HIGH block the release tag and route to remediation like a
NON-COMPLIANT spec-enforcer; MEDIUM/LOW are recorded in `verification.md` and do
not block. This reuses the existing Step 7 parallel-fan-out + `dispatch_prompt`
machinery and the Step 1c layer-review mandatory-CRITICAL severity pattern — no
new orchestration primitive.

Out of band: this feature does NOT add the deterministic spec-conformance gate
(tracker #65) and does NOT modify the review agents themselves (#59, shipped).

Source: tracker #60; harness-feedback covr-2.0; the F-2026-06-01 (#59) deferral
of AC-7 (which needed exactly this firing point).

## Scope

### In Scope
- A new `/build` Step 7 review sub-step that dispatches `code-reviewer` (always),
  `security-reviewer` (always), and `architect-reviewer` (on architectural-impact
  signal), in parallel, against the changed fileset, after spec-enforcer (item 3)
  and before the journey/coupling/runtime gates + release-tag write.
- Severity-gated blocking: CRITICAL/HIGH block the release tag and route to
  remediation; MEDIUM/LOW are advisory and recorded in `verification.md`.
- Proportional architect-reviewer firing keyed on the existing architectural
  signal (design.md present AND non-trivial layer impact, or detected new
  modules/boundaries); skipped for `infrastructure_only` / no-architecture changes.
- Aggregation of review verdicts with spec-enforcer's onto the same
  release-gating path; remediation routing + re-run on `/build --resume`.
- An explicit, logged operator override for a blocking finding (mirrors the
  `--skip-spec-coupling-check` discipline).
- Autonomous-mode (`--autonomous`) routing of CRITICAL/HIGH findings through the
  existing `/goal` remediation loop.

### Out of Scope
- The review agents themselves (F-2026-06-01 / #59 — shipped, stack-correct).
- The deterministic spec-conformance gate (#65 — separate feature).
- `verifier` as a Step-7 dispatch — its role is already covered mechanically by
  the per-wave `verify-green` gate (Step 6c).
- Changing spec-enforcer's AC-verification behavior (item 3 is unchanged; the
  review gate is additive).

## Requirements

### BR-001: Review-agent dispatch at Step 7
A new Step 7 review sub-step dispatches `code-reviewer` (always) and
`security-reviewer` (always), and `architect-reviewer` (conditionally per
BR-003), in a single parallel fan-out, against the build's changed fileset
(git diff vs the integration base + the wave tasks' `files_in_scope`), with the
spec and (if present) design as context. It runs after spec-enforcer (item 3)
and before the Step 7.4–7.6 gates and the release-tag write (item 5).

### BR-002: Severity-gated blocking
Each review agent returns findings carrying a severity in the closed set
{CRITICAL, HIGH, MEDIUM, LOW}. Any CRITICAL or HIGH finding (from any dispatched
review agent) blocks the terminal close: the release tag and release-notes are
NOT written, and the finding routes to remediation exactly like a NON-COMPLIANT
spec-enforcer. MEDIUM and LOW findings do NOT block; they are recorded in
`verification.md` under a Review Findings section and the build proceeds.

### BR-003: Proportional architect-reviewer firing
`architect-reviewer` fires only when the change has architectural impact,
detected via the existing signal: `design.md` present AND the layer-impact
analysis reports non-trivial touched layers (Step 1c), OR new modules/boundaries
detected in the changed fileset. It does NOT fire when
`state.yaml.spec_phase.infrastructure_only` is true, or when the layer-impact
analysis reports no touched layers. A skip is recorded with its reason in
`verification.md` (audited, not silent). code-reviewer and security-reviewer are
NEVER gated this way — they always fire.

### BR-004: Changed-fileset + context, reusing existing machinery
The review dispatch reuses the Step 7 parallel-fan-out shape, the
`dispatch_prompt.py` assembler, and the chunking pattern when the changed
fileset exceeds a review agent's tool budget. Each agent is given the changed
fileset to review (not the whole repo) plus the spec/design as intent context.

### BR-005: Aggregated verdict on the release-gating path
The review-gate verdict aggregates with spec-enforcer's: the terminal close
proceeds only when spec-enforcer is COMPLIANT AND no CRITICAL/HIGH review finding
is outstanding. Remediation routes findings to the responsible task owners; the
gate re-runs on `/build --resume`.

### BR-006: Forward-only + autonomous mode
The gate fires for builds from this feature's release tag onward; features whose
build predates it are unaffected (no retroactive blocking). Under `--autonomous`,
a CRITICAL/HIGH finding routes through the existing `/goal` evaluator remediation
loop (no operator pause); on max-turns it stops with the finding surfaced, never
a silent clean release.

### BR-007: Logged override discipline
A blocking CRITICAL/HIGH finding may be overridden only via an explicit operator
flag carrying a non-empty reason; the reason is appended to `verification.md` and
`release-notes.md` under a Review Gate subsection. An empty reason is rejected.
Routine override defeats the gate (the cry-wolf / dead-gate failure mode to
monitor), mirroring the `--skip-spec-coupling-check` discipline.

### BR-008: Credible, non-noisy gate (cost proportionality)
Review dispatches run concurrently (a single conductor turn), the
architect-reviewer gate avoids no-op dispatches, and the severity gate ensures
only CRITICAL/HIGH block — so the gate stays credible (does not cry wolf) while
adding bounded cost. Every dispatched review produces a relevant review (no
agent fires where it has nothing to review).

## Acceptance Criteria

1. On a build whose changed fileset includes code, Step 7 dispatches
   `code-reviewer` AND `security-reviewer` in parallel against the changed
   fileset; both run and both verdicts are recorded in `verification.md`.
2. `architect-reviewer` fires when the feature has `design.md` + non-trivial
   layer impact (or detected new modules/boundaries) and is skipped (with a
   recorded reason in `verification.md`) when `infrastructure_only` is true or
   no layers are touched. `code-reviewer`/`security-reviewer` are never skipped.
3. A CRITICAL or HIGH review finding blocks the terminal close: the release tag
   and release-notes are NOT written, the active→shipped move is NOT attempted,
   and the finding is routed to remediation (re-runnable via `/build --resume`),
   mirroring a NON-COMPLIANT spec-enforcer.
4. A MEDIUM or LOW review finding does NOT block; it is recorded under a Review
   Findings section of `verification.md` and the build proceeds to the release
   gates.
5. The review gate runs AFTER spec-enforcer (Step 7 item 3) and BEFORE the
   Step 7.4–7.6 gates and the release-tag write; the terminal close requires BOTH
   spec-enforcer COMPLIANT AND no outstanding CRITICAL/HIGH review finding.
6. The dispatched review agents self-resolve their active profile (post-#59), so
   on a non-Python project their findings reference the project's real toolchain
   (e.g. code-reviewer cites jest/eslint/tsc, not pytest/ruff/mypy).
7. A blocking CRITICAL/HIGH finding can be overridden only via an explicit flag
   with a non-empty reason, which is logged to `verification.md` + `release-notes.md`;
   without the flag the block holds; an empty reason is rejected.
8. Forward-only: a build predating this feature's release tag is unaffected.
   Under `--autonomous`, a CRITICAL/HIGH finding routes through the `/goal`
   remediation loop with no operator pause and never yields a silent clean release.

## Edge Cases

1. **Docs/spec-only change (no code in the diff).** code-reviewer still runs
   (reviews the changed docs); security-reviewer runs and typically finds nothing;
   architect-reviewer is skipped. No false block.
2. **A review agent fails to emit a verdict / errors out.** Treated as
   INSUFFICIENT_EVIDENCE → blocks (conservative, mirroring the chunker's
   missing-verdict → NON-COMPLIANT rule). The agent's stderr is surfaced.
3. **Diff exceeds a review agent's tool budget.** Reuse the Step 7 chunking /
   fan-out pattern to partition the changed fileset across dispatches.
4. **`design.md` present but layer-impact reports no touched layers** (e.g.
   `infrastructure_only`). architect-reviewer gates OUT — no architectural impact
   means nothing to review; recorded as a skip-with-reason.
5. **False-positive finding the operator disagrees with.** The BR-007 override
   flag (with logged reason) is the escape hatch; routine use is the cry-wolf
   failure mode `/metrics` should surface.
6. **This feature's own build is `infrastructure_only`.** architect-reviewer is
   skipped on its own build; code-reviewer + security-reviewer run against the
   harness code (the new Step 7 sub-step + helper).

## Research Notes
- Step 7 dispatch site + chunker fan-out to mirror: `skills/build/SKILL.md:1574–1667`.
- Severity-gated-blocking precedent: Step 1c layer-review mandatory-CRITICAL.
- Dispatch assembler: `scripts/dispatch_prompt.py`; `standards/process/subagent-dispatch.md`.
- Review agents (post-#59, stack-correct, self-resolving): `agents/{code-reviewer,security-reviewer,architect-reviewer}.md`.
- `verifier` excluded — covered by per-wave `verify-green` (Step 6c).
- No `INVARIANTS.md`, no `.etc_sdlc/antipatterns.md` present.
- Resolver/architecture decisions (verdict schema, severity protocol, exact dispatch wiring, override flag name) deferred to `/architect`.
