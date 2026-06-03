# Build-Time Review Gate — Fire the Review Agents at /build Step 7

## Status: MANDATORY
## Applies to: /build

## The Problem

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

This standard defines the **single source of truth** for the missing firing
point: the Step 7 review gate. It pins the firing policy, the finding-emission
contract, the severity-gated blocking model, and the override discipline. The
build skill, `review_gate.py`, and any future caller cite this file by path and
implement what it pins; **they do not inline or restate the policy** (the #53
lessons-terminate-in-gates discipline — the lesson terminates in this gate, not
in a memory note or an inlined skill paragraph).

## Lineage

Decisions binding this standard (the three review-gate ADRs):

- `docs/adrs/F-2026-06-02-build-review-agent-gate-001-review-finding-emission-contract.md`
  — the prose structured-findings emission contract each review agent honors.
- `docs/adrs/F-2026-06-02-build-review-agent-gate-002-review-gate-helper-script.md`
  — `review_gate.py` owns the mechanics; the skill orchestrates.
- `docs/adrs/F-2026-06-02-build-review-agent-gate-003-severity-gated-blocking-and-override.md`
  — severity-gated blocking + whole-gate logged override.

The review gate is the **6th sibling** in the established etc gate-helper family
(`spec_enforcer_chunker.py`, `layer_review.py`, `journey_lineage_check.py`,
`spec_coupling_check.py`, `runtime_totalization_check.py`). It reuses the Step 7
parallel-fan-out + `dispatch_prompt.py` machinery and the Step 1c layer-review
mandatory-CRITICAL severity model — no new orchestration primitive.

## The Firing Policy (GA-001)

The gate dispatches the review agents in a single parallel fan-out at Step 7,
**after** spec-enforcer's AC verification (item 3) and **before** the
journey/coupling/runtime gates (7.4–7.6) and the release-tag write (item 5).
Which agents fire is **not uniform** — the policy is calibrated so that the
lenses where a miss equals a shipped defect always fire, while the one
correctness-neutral lens fires only where it has something to review.

| Review agent | Fires | Rationale |
|---|---|---|
| `code-reviewer` | **ALWAYS** | Universal, cheap; a missed code review ships a quality defect. Never signal-gated. |
| `security-reviewer` | **ALWAYS** | Never signal-gated: a false-negative in any "should we review?" signal would ship the exact defect class #59 targeted (multi-tenant scope leak, data-retention leak). When in doubt, more rigor — the dispatch cost is dwarfed by breach/rework cost. |
| `architect-reviewer` | **Proportional** | Fires only on architectural impact (see below). Running architecture review on a change with zero architectural impact reviews nothing — pure cry-wolf and waste with no correctness gain. This is the ONE correctness-neutral place to gate. |

**architect-reviewer firing signal.** `architect-reviewer` fires when, and only
when, the change has architectural impact, detected via the existing
deterministic signal: `layer_review.py detect` reports a non-empty set of
touched layers AND the change is **not** `infrastructure_only`
(`state.yaml.spec_phase.infrastructure_only` is not true). It does NOT fire when
`layer_review.py detect` reports no touched layers, or when the feature is
`infrastructure_only`. Because the signal is the same single source of truth the
`/architect` phase already uses, gating here is **relevance, not
friction-cutting**, and introduces no miss.

**Audited skip, never silent.** When `architect-reviewer` is gated out, the skip
is recorded with its reason in `verification.md`. A skip is an auditable event,
not an absence. `code-reviewer` and `security-reviewer` are NEVER gated this
way — they always fire and are always recorded.

## Severity-Gated Blocking (ADR-003)

Each finding carries a severity in the **closed set** `{CRITICAL, HIGH, MEDIUM,
LOW}` — the **layer-review severity scale**, reused, not invented. Blocking is
gated on severity, reusing the Step 1c layer-review mandatory-CRITICAL model:

| Max severity (any dispatched agent) | Outcome |
|---|---|
| **CRITICAL** or **HIGH** | **Blocks the terminal close.** The release tag and release-notes are NOT written, the active→shipped move is NOT attempted, and the finding routes to remediation **exactly like a NON-COMPLIANT spec-enforcer** (re-runnable via `/build --resume`). |
| **MEDIUM** or **LOW** | **Advisory.** Does NOT block. Recorded under the Review Findings section of `verification.md`; the build proceeds to the release gates. |
| No findings | `GATE: CLEAN`. Proceeds. |

**Aggregated verdict.** The review-gate verdict aggregates with spec-enforcer's
onto the same release-gating path. The terminal close proceeds **only** when
spec-enforcer is COMPLIANT **AND** no CRITICAL/HIGH review finding is
outstanding.

**Why severity-gated, not block-on-any.** LLM review agents are noisy. Blocking
on every LOW finding would train the operator to reach for the override on
routine noise — a routinely-skipped gate is a dead gate, and that erodes the
discipline that is etc's entire value. Blocking on CRITICAL/HIGH only keeps the
gate **credible**: it rarely cries wolf, so a block is taken seriously. The
trade-off — a genuinely-severe issue an agent rates only MEDIUM would not
block — is mitigated by the shared, consistent severity vocabulary and by the
finding still being recorded for the operator.

## The Emission Contract (ADR-001)

Each dispatched review agent ends its output with a `## Review Findings` block.
This is the contract `review_gate.py` parses; it lives in the **dispatch
prompt** (assembled by the build skill), NOT in the agent manifests — so
F-2026-06-01's (#59) agents stay byte-unchanged.

**The block:**

```
## Review Findings
- [CRITICAL|HIGH|MEDIUM|LOW] <file:line> — <one-line finding>
- ...
GATE: BLOCK | PASS
```

When there are no findings, the agent emits a single `GATE: CLEAN` line in place
of the finding list.

**Contract rules:**

- Each finding line is `- [<SEVERITY>] <file:line> — <one-line finding>`, where
  `<SEVERITY>` is a member of the closed set `{CRITICAL, HIGH, MEDIUM, LOW}`.
- The block ends with exactly one `GATE:` line valued `BLOCK`, `PASS`, or
  `CLEAN`. `GATE: BLOCK` is the agent's signal; `review_gate.py` derives the
  authoritative block decision deterministically from the parsed severities (any
  CRITICAL/HIGH ⇒ block), so a noisy LLM cannot accidentally flip the gate —
  only a parsed CRITICAL/HIGH does.
- `GATE: CLEAN` is emitted only with an empty finding list.
- The severity vocabulary is reused verbatim from the layer-review scale; agents
  do not invent severities.

**INSUFFICIENT_EVIDENCE → conservative block.** An agent that fails to emit a
parseable `## Review Findings` block — a missing block, a malformed severity
tag, a missing or unparseable `GATE:` line, or an agent that errors out before
emitting — is treated as **INSUFFICIENT_EVIDENCE**, which **blocks**. The gate
never silently passes an agent whose verdict it could not read; an unparseable
verdict is a block, mirroring the chunker's missing-verdict → NON-COMPLIANT
rule. The agent's stderr is surfaced.

## The Override (ADR-003)

A blocking CRITICAL/HIGH finding may be overridden only via an explicit operator
flag carrying a non-empty reason:

```
/build --skip-review-gate "<reason>"
```

**Override rules:**

- The reason is **mandatory and non-empty**. An empty reason is **rejected**
  (`review_gate.py aggregate --skip-review-gate ""` → exit 1) — the flag does not
  silently no-op.
- The reason is logged **verbatim** to **both** `verification.md` and
  `release-notes.md` under a Review Gate subsection. The logged-reason audit
  trail is the discipline; the gate is enforcement, the skip is the explicit,
  accountable exception.
- The override is **whole-gate**, mirroring `--skip-spec-coupling-check` (F015)
  and `--skip-journey-check` (F017) exactly. Per-finding override is deferred
  (YAGNI — added only if a real need surfaces).
- The `--skip-review-gate` reason is sanitized at the capture site before it is
  logged.

**Cry-wolf monitoring.** Routine `--skip-review-gate` use is the cry-wolf /
dead-gate failure mode `/metrics` must surface — over-override is a signal that
the severity calibration or the agents themselves are too noisy, not that the
gate should be relaxed.

## Changed-Fileset Scope (GA-003)

The review agents are given the build's **changed fileset** to review (not the
whole repo) plus the spec and (if present) design as intent context. The changed
fileset is the **union of the wave tasks' `files_in_scope`** (the canonical,
plan-time-declared, collision-checked change set), with `git diff --name-only`
vs the integration base as a cross-check/fallback that catches anything edited
outside declared scope. When the changed fileset exceeds a review agent's tool
budget, the dispatch reuses the Step 7 chunking / fan-out pattern to partition it
across dispatches.

## Forward-Only

The gate fires for builds from **this feature's release tag onward**. Features
whose build predates it are **unaffected** — there is no retroactive blocking and
no backfill of review findings against already-shipped features.

**Autonomous mode.** Under `/build --autonomous`, a CRITICAL/HIGH finding routes
through the existing `/goal` evaluator remediation loop (no operator pause;
re-run until the blocking finding is resolved or max-turns). On max-turns it
**stops with the finding surfaced** — never a silent clean release. MEDIUM/LOW
findings are recorded and do not interrupt the autonomous run.

## Edge Cases

- **Docs/spec-only change (no code in the diff).** `code-reviewer` still runs
  (reviews the changed docs); `security-reviewer` runs and typically finds
  nothing; `architect-reviewer` is skipped (no touched layers). No false block.
- **A review agent fails to emit a verdict / errors out.** INSUFFICIENT_EVIDENCE
  → block (conservative). The agent's stderr is surfaced.
- **Diff exceeds a review agent's tool budget.** Reuse the Step 7 chunking /
  fan-out pattern to partition the changed fileset across dispatches.
- **`design.md` present but layer-impact reports no touched layers** (e.g.
  `infrastructure_only`). `architect-reviewer` gates OUT — no architectural
  impact means nothing to review; recorded as a skip-with-reason.
- **False-positive finding the operator disagrees with.** The
  `--skip-review-gate` override (with logged reason) is the escape hatch; routine
  use is the cry-wolf failure mode `/metrics` surfaces.
- **This feature's own build is `infrastructure_only`.** `architect-reviewer` is
  skipped on its own build; `code-reviewer` + `security-reviewer` run against the
  harness code (the new Step 7 sub-step + helper).

## Cross-References

- `docs/adrs/F-2026-06-02-build-review-agent-gate-001-review-finding-emission-contract.md`
  — the emission contract documented above.
- `docs/adrs/F-2026-06-02-build-review-agent-gate-002-review-gate-helper-script.md`
  — `review_gate.py`'s `plan` + `aggregate` CLI and the skill ↔ helper split.
- `docs/adrs/F-2026-06-02-build-review-agent-gate-003-severity-gated-blocking-and-override.md`
  — the severity model and the override discipline.
- `standards/process/behavioral-runtime-dod.md` — the sibling Step 7 gate
  (Gap A) whose declaration-gated, forward-only, autonomous-routing structure
  this gate mirrors.
- `standards/process/diagnostic-discipline.md` — a sibling structured-evidence
  gate in the same low-friction-dismissal-compounds family.
- `standards/process/subagent-dispatch.md` — the `dispatch_prompt.py` assembler
  the review fan-out reuses.
- `standards/process/contract-completeness.md` — the closed-enum status
  precedent the severity vocabulary follows.
- `scripts/review_gate.py` — the gate helper (`plan` + `aggregate`) that
  implements this contract (task 001).
- `skills/build/SKILL.md` — orchestrates the Step 7 review sub-step, citing this
  standard by path (task 003); does NOT inline the policy.
- `agents/{code-reviewer,security-reviewer,architect-reviewer}.md` — the
  stack-correct review agents (F-2026-06-01, #59) the gate dispatches.

**Origin:** tracker #60; harness-feedback covr-2.0 (the security/quality/
architecture defects that escaped to a human reviewer + CodeQL at PR time); the
F-2026-06-01 (#59) deferral of AC-7, which needed exactly this firing point.
