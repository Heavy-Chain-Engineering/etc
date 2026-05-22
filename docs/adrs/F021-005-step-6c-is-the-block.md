# ADR-F021-005: Step 6c is the structural block; PreToolUse warns

**Date:** 2026-05-20
**Status:** Accepted

**Context:** The agent-discipline track needs to surface missing-evidence events. Three placement options: (a) PreToolUse hook blocks (exit 2) on missing evidence; (b) PreToolUse hook warns (exit 0) and Step 6c is the structural block; (c) Stop hook only (no per-Edit visibility). Blocking at PreToolUse creates false-positive friction during legitimate investigations (the agent is mid-tool-rerun when the next Edit happens).

**Decision:** PreToolUse warns (stderr Pattern B) and exits 0 — always; Stop-hook residual scan also warns. The structural block lives at `/build` Step 6c via `verify-green.sh`. The 5-turn `DIAGNOSTIC_INVESTIGATION_TURNS` is the agent's patience budget — sufficient cycles to investigate without immediate block.

**Consequences:** *Positive:* agent has space to investigate legitimate false positives; operator sees drift early (per-Edit visibility) without false-positive blocks; Step 6c per-wave verify-green is the actual gate (which the agent can't route around via clever transcript manipulation). *Negative:* audit log contains `diagnostic_dismissal_missing_evidence` rows that don't correspond to build failures (the warning didn't block); distinguishing "evidence was eventually produced" from "evidence never came" requires rolling-window analysis at metrics time.

**Alternatives considered:** PreToolUse blocking (rejected — false-positive friction; would surface as agent-frustration and operator-bypass attempts). Stop-only (rejected — no per-Edit visibility; operator only learns at session end). Hybrid blocking with whitelist (rejected as YAGNI — Step 6c is sufficient).
