# ADR-F021-002: Dual-track defense (agent-discipline + structural-gate)

**Date:** 2026-05-20
**Status:** Accepted

**Context:** F021 must defend against *low-friction-dismissal-compounds* at two distinct failure surfaces: (1) agents drifting into autoregressive dismissals during multi-wave work; (2) errors accumulating across waves even when individual agents are well-behaved (the redacted-project incident: 4323 mypy errors caught only at terminal Stop). One track alone is insufficient.

**Decision:** Ship both tracks in one PRD. Track 1 (agent-discipline): SubagentStart standard injection + PreToolUse evidence-block validation + Stop-time residual scan. Track 2 (structural-gate): `/build` Step 6c invokes the existing F020 `hooks/verify-green.sh` per-wave with zero-tolerance contract. Both tracks emit audit-log rows to the same F019 surface (`.etc_sdlc/efficiency/turn-events.jsonl`).

**Consequences:** *Positive:* either track independently catches the anti-pattern; agent cannot route around by suppressing one surface; mirrors the F001/F002/F003 defense-in-depth pattern the harness already embraces (three-gates-must-fail-simultaneously). *Negative:* two implementation surfaces to maintain (M-002 validator + Step 6c invocation); future `/metrics` aggregation reads across both.

**Alternatives considered:** Track 1 alone (rejected — incident #2 proved structural defense is load-bearing; would not catch projects where lefthook ran clean). Track 2 alone (rejected — would catch wave failures but not surface agent-level drift during a wave). Sequential ship (track 1 first, track 2 follow-up) rejected as the zero-tolerance contract per BR-004 requires both for completeness.
