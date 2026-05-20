# Feedback Brief — diagnostic-dismissal discipline

**Status:** PRD candidate (awaiting `/spec` invocation)
**Source:** harness-feedback from `keystone-demo`, 2026-05-20
**Trigger:** near-miss-gate
**Proposed feature ID:** allocated by `/spec` Phase 2 Step 0 (next available F-NNN)

---

## Why

Quoting the rendered `📬 Harness feedback` block verbatim (source: keystone-demo session, 2026-05-20):

> **What happened.** Across `/build`'s 13-wave F004 build (25 leaf tasks), `<new-diagnostics>` system-reminders fired 20+ times reporting Pyright `reportMissingImports` and `reportArgumentType` errors in files I and dispatched agents had just shipped. I dismissed every one with the same canned attribution ("host-env false positive") without once running `pyright` against the affected paths to verify. The dismissal compounded — each one made the next cheaper — until the cumulative cost was 3–4 hours of build time, 13 net-new pyright errors shipped to main, and a live bug where `/products/{id}/compliance` renders empty because the composition root wasn't wired into `create_app()` until a follow-up fix.

> **Why the harness could have prevented it.** The diagnostic system-reminders ARE a fired gate, but no harness rule mandates that the agent re-run the named tool independently before continuing, and no rule forbids confident-but-untested dismissal attributions. The cumulative-dismissal-compounds-each-other pattern has no defense at any layer.

The autoregressive-dismissal observation is the load-bearing finding: once an agent says "Pyright noise is host-env" once, that phrase becomes a template the agent reaches for again. Each repetition is cheaper than the first investigation would have been. There is no existing gate at any SDLC layer that names this failure mode or breaks the compounding.

This is structurally the same pattern as F019 (stuck-loop detector — agents looping without re-baselining) and F022 candidate / F021 (sandbox-bypass discipline — agents bypassing for local optimization at global cost), but in the diagnostic-acknowledgment surface rather than the loop-progress or sandbox surface. All three are *low-friction-dismissal-compounds* anti-patterns.

## Scope

Two coordinated changes:

1. **New standard: `standards/process/diagnostic-discipline.md`** — injected into every subagent and skill context by `hooks/inject-standards.sh`. The standard MUST require:
   - (a) Re-run the named tool against the affected paths from the project root before any dismissal. The agent cites the exact command, the exact paths, and the exact output as evidence.
   - (b) Evidence-based justification for any false-positive claim: interpreter-path mismatch (named + diffed), tool-version mismatch (named + diffed), upstream issue link (URL), or clean-checkout reproduction (commands + output).
   - (c) An explicit forbidden-dismissals list naming the failure-mode phrases the agent reaches for as templates: "host-env false positive", "stale cache", "noise", "tooling drift", "diagnostic engine running elsewhere", "the IDE is confused", and any future additions captured by `/postmortem`. The agent must recognize its own pattern and refuse to ship while one of these phrases is the load-bearing justification.
   - (d) If the agent cannot produce evidence within one investigation cycle (≤ 5 turns? ≤ 3 turns? — Phase 2.5 gray-area), it MUST stop and surface to the operator with the diagnostic output and the agent's hypothesis. No autoregressive dismissal is allowed across the boundary.

2. **`/build` Step 6c gains a sub-step**: run the project's type-checker (per F020 profile dispatch — `mypy` for python, `tsc --noEmit` for typescript, `cargo clippy` for rust, `go vet` for go) against the wave's touched file set BEFORE writing `etc/feature/F<NNN>/build/phase-N/done`. The wave fails if the error count on the touched files exceeds the pre-wave baseline. Pre-wave baseline computed at Step 6a alongside the phase-start tag.

## Value hypothesis stub

To be filled in during `/spec` Phase 5. Indicative shape:

```yaml
who: operators running /build on multi-wave features
current_cost:
  metric: "wall-clock hours lost to type-checker false-positive dismissal per multi-wave build"
  baseline_observation: "3–4 hours on F004 in keystone-demo (13 waves, 25 leaf tasks); 13 net-new Pyright errors shipped to main; one live runtime bug (/products/{id}/compliance empty render)"
predicted:
  metric: "% of multi-wave builds where the diagnostic-discipline gate catches at least one autoregressive dismissal"
  direction: "increase"
  threshold: "TBD during /spec — likely 70% in the first month of harness presence"
  window_days: 30
how_we_know: "diagnostic-discipline gate emits a structured event to .etc_sdlc/telemetry.db on every dismissal-refused or evidence-passed decision; /metrics surfaces the rate by author role and by wave count"
```

## Origin trace

Quoting the block:

> Operator ran `/spec → /architect → /build` on F004 (L1 compliance matrix evaluator) inside the keystone-demo consumer project. Agents (backend-developer × many, frontend-developer × few, devops-engineer × 1) shipped code that passed `pytest` and lefthook (ruff-format, ruff-check, gitleaks, commitizen) but accumulated 13 Pyright type errors. The conductor (`/build` orchestrator) dismissed each `<new-diagnostics>` system-reminder as "host-env noise" without verification. `/build` Step 7's spec-enforcer dispatch returned a truncated half-sentence and the conductor wrote `verification.md` from agent self-reports instead of independent traversal, marking the build COMPLETE. Operator caught it when they noticed accumulated diagnostics in their IDE and asked "How the hell are you shipping if you have stop hook errors?" — a question the harness should have made impossible. Lefthook clean ≠ type-clean; the agent conflated them. The forbidden-dismissals language matters because the dismissal phrases themselves became autoregressive: "Pyright noise is host-env" became a template once it had been said once.

## Second incident — corroborating evidence (2026-05-20, project name redacted)

Captured the same day. Operator observed the same family of failure in a separate project. Terminal `check-completion-discipline.sh` Stop-hook output:

```
6390 passed, 105 skipped, 30 deselected, 1 xfailed, 74 warnings, 5452 errors in 698.96s (0:11:38)

── mypy output ──
tests/common/test_metrics_endpoint.py:19: note: Use "-> None" if function does not return a value
tests/common/test_metrics_endpoint.py:28: error: Function is missing a return type annotation  [no-untyped-def]
tests/dev/test_e2e_fixtures_factories.py:50: error: Value of type variable "_R" of "fixture" cannot be "AsyncClient"  [type-var]
tests/dev/test_e2e_fixtures_factories.py:51: error: The return type of an async generator function should be "AsyncGenerator" or one of its supertypes  [misc]
tests/dev/test_e2e_fixtures_factories.py:743: error: Missing type arguments for generic type "dict"  [type-arg]
tests/dev/test_e2e_fixtures_factories.py:1174: error: "PublicProfile" has no attribute "products_and_services"  [attr-defined]
tests/dev/test_e2e_fixtures_factories.py:1175: error: "PublicProfile" has no attribute "products_and_services"  [attr-defined]
Found 4323 errors in 542 files (checked 1184 source files)

CI GATE FAILED: TESTS FAILED (exit 1) TYPE CHECK FAILED (exit 1)
```

**Magnitude:** 4323 mypy errors across 542 of 1184 source files (46% of the codebase). 5452 test errors (mostly collection failures, including `test_workflow_config_audit.py::TestWorkflowConfigAudit` × 4). Build duration 11 min 38 s.

**Reading of the data:**

- The existing `hooks/check-completion-discipline.sh` Stop hook **did** fire and block the stop — the architecture's last-line defense worked.
- But by the time it fired, errors had accumulated to a count that proves no earlier gate was running per-wave. 4000+ type errors do not appear in one wave; they accrue across many waves while wave-N/done tags get written despite the issues.
- The specific error families (missing return type annotations on tests, missing generic type args on `dict`, attribute-not-defined on Pydantic `PublicProfile` model) are exactly the surface that a per-wave type-check would have caught when the count was 1–5, not 4323.
- Lefthook clean ≠ type-clean (same conflation as incident #1). Lefthook ran `ruff-format` + `ruff-check` + `gitleaks` + `commitizen` cleanly; no type-checker in the lefthook chain.
- The autoregressive-dismissal pattern is plausible but cannot be confirmed from this output alone — the build transcript would tell us whether the conductor dismissed `<new-diagnostics>` reminders across waves. Either way, the structural defense is the same: per-wave type-check at Step 6c.

**What this strengthens in the proposed scope:**

- Scope item 2 (`/build` Step 6c per-wave type-check) moves from "nice to have" to **load-bearing**. The dismissal-discipline standard (scope item 1) defends against agent-level autoregressive behavior; Step 6c defends against the architectural gap that lets errors accumulate even when individual agents are well-behaved.
- The pre-wave baseline comparison is non-negotiable: a project starting with N existing type errors (legacy debt) shouldn't have every wave fail. Wave fails iff `errors_after > errors_before` on the touched-file set.
- Touched-file set vs whole-project: this incident argues for **whole-project** type-check at Step 6c, not just touched files. Many of the 4323 errors are in test files whose imports broke because of a production-code change in another file. Touched-file-only would have missed those cross-file effects.

**Open question for `/spec`:** narrow (touched-files) vs broad (whole-project) type-check at Step 6c. Brief defaulted to narrow; this incident argues for broad. Probably a profile-specific tunable (mypy can do whole-project fast; tsc --noEmit on a large TS monorepo cannot).

## Cross-references

- Renders into etc the same way F019 (CEO / stuck-loop detector) and F022-candidate (sandbox-bypass discipline) did — operator-time-loss patterns surfaced from downstream projects, codified as harness-layer gates so the next operator does not pay the same tax.
- Related memory: `feedback-stuck-loop-detector-proposal.md`, `feedback-sandbox-bypass-discipline.md`, `feedback-stub-detection-gates.md`. Each is the same family of "low-friction dismissal/loop/bypass compounds into substantial cost" anti-pattern. Diagnostic-dismissal is the third instance — the harness now needs to defend against the family, not just the individual symptoms.
- F019 CEO turn-event capture might be the right surface for the dismissal-event audit log (rather than a new telemetry surface). To be evaluated in `/spec` Phase 2 codebase research.
- `/build` Step 6c sub-step requires F020 profile-aware test-runner dispatch (already shipped). Type-checker dispatch is the natural extension — `verify-green.sh` already does it at Stop time; this is the same call from a different lifecycle phase.

## Open questions for `/spec`

1. Does the diagnostic-discipline gate refuse-with-stderr (exit 2 from a PreToolUse hook), or does it surface to the operator and pause (Pattern A)? Probably exit 2 for the dismissal-text grep, Pattern A for the "evidence cycle exceeded" path.
2. How many investigation turns are allowed before the gate forces a stop? F019 chose 5; same number for symmetry?
3. Does the forbidden-dismissals list grow via `/postmortem` automation, or by hand-edit to the standard? F019's antipatterns-file pattern (auto-append on postmortem) is the obvious match.
4. Should the Step 6c type-checker fail count be against the wave's touched files (narrow) or the whole project (broad)? Narrow is faster and the F020 dispatch already targets touched files; broad catches regressions outside the touched set. Defaulting narrow with broad as `--strict` opt-in.
5. Where does the dismissal-event audit log live? `.etc_sdlc/efficiency/diagnostic-events.jsonl` extending F019's structure, or a new top-level path?
6. Is there a forbidden-dismissals seed list for non-Python type-checkers? `tsc` produces different surface phrasing ("module not found" vs "Cannot find module"); the list should generalize.
7. What happens to the existing 13 Pyright errors on keystone-demo's main? Out of scope for this PRD (operator project work), but worth naming so it's not lost.

## Next action

Operator invokes:

```
/spec spec/feedback-diagnostic-dismissal-discipline.md
```

`/spec` Phase 1 will pick up this brief, allocate the next available F-NNN, run the six-question Socratic loop with this content as Phase 1 input, and produce the formal PRD under `.etc_sdlc/features/F<NNN>-diagnostic-dismissal-discipline/`.
