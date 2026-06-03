# ADR F-2026-06-02-build-review-agent-gate-001: Review-finding emission contract (prose structured-findings block)

**Date:** 2026-06-02
**Status:** Accepted

**Context:**
The Step 7 review gate severity-gates blocking (CRITICAL/HIGH block; MEDIUM/LOW
advisory), so it needs each LLM review agent (code-reviewer / security-reviewer /
architect-reviewer) to emit findings with a *machine-readable severity*. These
are Agent-tool dispatches that return prose, not Workflow agents with a
StructuredOutput schema. spec-enforcer already emits a prose COMPLIANT /
NON-COMPLIANT verdict that the Step 7 conductor reads.

**Decision:**
Extend the existing prose-verdict-emission pattern with a severity-tagged block.
The dispatch prompt instructs each review agent to end its output with:

```
## Review Findings
- [CRITICAL|HIGH|MEDIUM|LOW] <file:line> — <one-line finding>
- ...
GATE: BLOCK | PASS
```

(or a single `GATE: CLEAN` line when there are no findings). The severity
vocabulary is the **layer-review severity scale** (CRITICAL/HIGH/MEDIUM/LOW) —
reused, not invented. `review_gate.py` (ADR-002) parses the block and computes
the max severity; `GATE: BLOCK` is derived deterministically when any
CRITICAL/HIGH finding is present. The emission contract lives in the **dispatch
prompt** (assembled by the build skill), NOT in the agent manifests — so
F-2026-06-01's (#59) agents stay byte-unchanged.

**Consequences:**
- *Easier:* mirrors the spec-enforcer mechanism the conductor already handles;
  no new dispatch primitive; agents unchanged (the contract is per-dispatch);
  severity vocabulary is consistent with the layer-review gate.
- *Harder:* prose parsing is less robust than a hard schema — `review_gate.py`
  must tolerate formatting drift (missing block, malformed severity tag). An
  agent that fails to emit a parseable block is treated as INSUFFICIENT_EVIDENCE
  → conservative block (spec Edge Case 2), not silently passed.
- A future migration to a structured-output dispatch mechanism, if Claude Code
  exposes one for Agent-tool calls, can replace the prose contract behind the
  same `review_gate.py` parse seam.
