# ADR-F024-002: Asymmetric safe-default policy — over-inject for cheap sections, under-inject for verbose role-specific sections

**Date:** 2026-05-22
**Status:** Accepted

**Context:** F024 introduces conditional emission of three sections in `hooks/inject-standards.sh`. Each conditional section requires a safe-default policy for the two cases where the gating predicate cannot be evaluated: (a) `agent_type` is absent, null, or the literal string `"unknown"`; (b) the task YAML is absent or malformed. The naive resolution is a uniform policy — always over-inject (emit the section) whenever the condition is indeterminate. That is safe in the narrowest sense: no section is ever silently dropped. But the cost of a wrong default is not uniform across sections.

`### Git Commit Discipline` is ~250 tokens. Its content governs shared-index behavior in parallel-fan-out. When injected into a non-developer role it is irrelevant but inert — the reader skips past it. When suppressed for an unrecognized role that turns out to be a developer variant, a real git-index race class goes uncovered. Wrong direction: under-injection is the more costly failure.

`### Stub-Marker Grep Contract for spec-enforcer` is ~250 tokens that speak in spec-enforcer's first person ("you MUST run grep…"). When injected into a non-enforcer role it is not merely irrelevant — it reads as an instruction addressed to that subagent, causing active operator confusion about whether the receiving agent is expected to run the grep. The contract is explicitly role-indexed by its heading. Over-injection in an unknown-role context produces false-obligation noise. Wrong direction: over-injection is the more costly failure.

`### User-Flow Completeness for User-Facing ACs` is ~200 tokens documenting a fundamental wiring rule. When task YAML is absent or malformed, the hook has no information about whether the task has user-facing ACs. The rule is cheap and fundamental; missing it for a task that turns out to have user-flow ACs leaves a user-facing correctness gap uncovered.

**Decision:** The safe-default policy is asymmetric, matched to the asymmetric cost of a wrong default per section:

| Section | Unknown role | Absent/malformed task YAML |
|---|---|---|
| `### Git Commit Discipline` | **Emit** (over-inject) | N/A — role-gated only |
| `### Stub-Marker Grep Contract` | **Suppress** (under-inject) | N/A — role-gated only |
| `### User-Flow Completeness` | N/A — task-gated only | **Emit** (over-inject) |

The rule: when a wrong default is cheap and covers a real defect class, over-inject. When a wrong default produces active confusion (the section speaks in a specific role's voice), under-inject.

EC-006 (`agent_type == "unknown"` literal string) is treated identically to absent — the same per-section policy applies.

**Consequences:** *Positive:* defaults are calibrated to actual injection cost rather than to a single worst-case axis; Git Commit Discipline over-injection on unknown covers any unrecognized developer variant; Stub-Marker Grep Contract is never injected outside a confirmed spec-enforcer context, preserving role clarity for all other subagents; operators who add new non-developer roles get sensible defaults without harness changes. *Negative:* two different rules where one would be simpler; the asymmetry must be documented explicitly (covered by `standards/process/conditional-onboarding.md` and this ADR) and referenced when future conditional sections are added; new roles must be evaluated against the asymmetric policy, not assumed to inherit either default.

**Alternatives considered:** Uniform safe-default — always emit every conditional section when the gating condition is indeterminate (rejected: treats injection cost as symmetric when it is not; Stub-Marker Grep Contract injected into every unrecognized-role dispatch produces false-obligation noise and erodes operator trust in the onboarding context; the uniform policy optimizes for simplicity at the cost of correctness for the class of dispatches where role is unknown but the receiving agent is clearly not a spec-enforcer).
