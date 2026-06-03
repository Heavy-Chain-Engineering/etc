# ADR F-2026-06-02-build-review-agent-gate-003: Severity-gated blocking + whole-gate logged override

**Date:** 2026-06-02
**Status:** Accepted

**Context:**
LLM review agents are noisy. Blocking the release tag on *every* finding (any
severity) would train operators to reach for the override on routine LOW noise —
a routinely-skipped gate is a dead gate, and that erodes the discipline that is
etc's entire value (project-etc-product-thesis). But never blocking makes the
review advisory-only, which the pbj retro showed is how real defects ship. The
spec resolved the firing/blocking policy in GA-001; this ADR fixes the mechanism.

**Decision:**
**Severity-gated blocking, reusing the layer-review mandatory-CRITICAL model.**
A CRITICAL or HIGH finding (from any dispatched review agent) blocks the terminal
close — the release tag + release-notes are NOT written, the active→shipped move
is NOT attempted, and the finding routes to remediation exactly like a
NON-COMPLIANT spec-enforcer (re-runnable via `/build --resume`). MEDIUM/LOW
findings do NOT block; they are recorded in `verification.md` under a Review
Findings section and the build proceeds. The review verdict aggregates with
spec-enforcer's: terminal close requires spec-enforcer COMPLIANT AND no
outstanding CRITICAL/HIGH review finding.

**Override:** a whole-gate `--skip-review-gate="<reason>"` flag (non-empty reason
mandatory; empty rejected), logged verbatim to `verification.md` + `release-notes.md`
under a Review Gate subsection. This mirrors `--skip-spec-coupling-check` (F015)
and `--skip-journey-check` (F017) exactly. Per-finding override is deferred (YAGNI).

Under `--autonomous`, a CRITICAL/HIGH finding routes through the existing `/goal`
evaluator remediation loop (no operator pause); on max-turns it stops with the
finding surfaced — never a silent clean release.

**Consequences:**
- *Easier:* the gate stays credible (only CRITICAL/HIGH block, so it rarely
  cries wolf); consistent with the established Step 1c layer-review severity
  model and the two existing release-gate skip flags; remediation routing reuses
  the spec-enforcer NON-COMPLIANT path.
- *Harder:* a genuinely-severe issue an agent rates only MEDIUM would not block
  — mitigated by the severity vocabulary being shared/consistent and by the
  finding still being recorded for the operator. Routine `--skip-review-gate`
  use is the cry-wolf failure mode `/metrics` must surface (over-override is a
  signal the severity calibration or the agents are too noisy).
- The override's logged-reason audit trail is the discipline; the gate is
  enforcement, the skip is the explicit, accountable exception.
