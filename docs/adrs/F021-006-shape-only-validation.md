# ADR-F021-006: Shape-only validation, not semantic re-execution

**Date:** 2026-05-20
**Status:** Accepted

**Context:** The validator `scripts/diagnostic_evidence.py::validate_block` could verify the agent's evidence block at two levels: (a) shape-only — parse YAML, check four required fields, check evidence_type enum membership; (b) semantically — additionally re-execute the agent's claimed `tool_rerun_command` and compare output to the agent's claimed `tool_rerun_output`. Option (b) catches fabrication; option (a) is fast and pure.

**Decision:** Shape-only validation. `validate_block` is a pure function (no I/O, no subprocess, no toolchain dependency) returning a `ValidationResult` dataclass. The structural contract makes fabrication noticeably more expensive than dismissal (the agent must compose four well-formed fields rather than dismiss in one sentence) but does not prevent it absolutely; that's deliberate.

**Consequences:** *Positive:* validator is testable in isolation (unit tests against fixture YAML); fast (<50ms typical); deterministic; no tool-environment dependency (the hook's `python3` doesn't have to match the project's). *Negative:* an adversarial agent could fabricate `tool_rerun_output` content; the audit log records a `diagnostic_dismissal_with_evidence` event for a structurally-valid-but-semantically-false block. EC-010 documents this limitation.

**Trust boundary:** the agent emits the block; the validator verifies shape; Step 6c (per-wave verify-green) verifies reality. The two layers together make fabrication unprofitable — the agent can pass the validator with a fabricated block, but the next Step 6c run catches the real error and fails the wave.

**Alternatives considered:** Semantic re-execution (rejected — reproduces the work Step 6c already does; introduces tool-environment dependencies; costs hook latency; doesn't meaningfully improve security given Step 6c is the real check). Hybrid (shape-only on PreToolUse, semantic on Stop) rejected as YAGNI.
