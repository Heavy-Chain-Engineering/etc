# ADR-F021-001: Structural-evidence enforcement, not phrase-grep

**Date:** 2026-05-20
**Status:** Accepted

**Context:** The harness must prevent agents from dismissing quality-tool diagnostics without verification. Two enforcement models are available: (a) regex-grep for forbidden dismissal phrases ("host-env false positive", "stale cache", etc.); (b) structural-evidence contract requiring a parseable YAML block with four required fields on every dismissal. The keystone-demo F004 incident showed dismissal phrases become autoregressive templates — the first paraphrase defeats the grep approach.

**Decision:** Enforce structurally. The standard requires every dismissal of a `<new-diagnostics>` reminder (or equivalent quality-tool signal) to emit a YAML block containing `tool_rerun_command`, `tool_rerun_output`, `attribution`, and `evidence_type` (controlled enum). The validator (`scripts/diagnostic_evidence.py::validate_block`) verifies shape; the forbidden-phrases list ships as illustrative documentation only (per BR-002), explicitly NOT used for enforcement matching.

**Consequences:** *Positive:* paraphrase-resistant by construction — a new dismissal template fails the same shape check the seed phrase would; no ongoing maintenance burden chasing new dismissal vocabulary. *Negative:* per-dismissal cognitive load is higher (four fields vs one sentence); standard-authoring burden falls on the design team to keep the schema capturing all legitimate dismissal cases.

**Alternatives considered:** Reflection-based detection (small-fast-model evaluating "did the agent dismiss without evidence?") deferred to a future PRD if structural-only proves insufficient. Phrase-grep alone explicitly rejected as documentation theater.
