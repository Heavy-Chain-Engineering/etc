# ADR-F021-004: Compose on F019/F020 plumbing (no new audit-log surface, no new dispatcher)

**Date:** 2026-05-20
**Status:** Accepted

**Context:** F021 needs a per-language quality-tool gate and an audit-log surface. The harness already has both: F020's `hooks/verify-green.sh` is the profile-aware quality dispatcher; F019's `.etc_sdlc/efficiency/turn-events.jsonl` is the agent-behavior audit log. Two options: (a) compose on the existing surfaces; (b) introduce parallel plumbing (a new dispatcher + a new `diagnostic-events.jsonl`).

**Decision:** Compose. Step 6c invokes `hooks/verify-green.sh` directly (no wrapper, no new dispatcher); audit-log rows extend the F019 JSONL surface with two new `event_type` values (`diagnostic_dismissal_with_evidence`, `diagnostic_dismissal_missing_evidence`). F021 adds one new Python module (`scripts/diagnostic_evidence.py` ~150 LOC), three new/modified hooks (~110 LOC total bash), one new standards doc.

**Consequences:** *Positive:* small implementation surface; future operators don't learn new etc primitives; `/metrics` extension reads one audit-log file, not two; F021 inherits F019's existing readers' tolerance for new event types (forward-compatible by JSONL convention). *Negative:* F021 inherits F019's audit-log rotation gap (no rotation policy yet) and F020's per-profile slowness profile (tsc on large monorepos). Both deferred to their respective feature owners.

**Alternatives considered:** Dedicated `.etc_sdlc/efficiency/diagnostic-events.jsonl` surface rejected per GA-007 (same data family belongs in the same file). Parallel quality dispatcher rejected — would re-introduce the silo problem F019 was built to consolidate. Wrapper around `verify-green.sh` rejected as YAGNI.
