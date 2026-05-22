# Diagnostic Discipline

## Status: MANDATORY
## Applies to: All agents, all skills, all sessions that invoke quality-enforcement tooling

To go well is to go quickly. By going well, we can sustainably go quickly. We
don't want to be sloppy.

This standard defends against the *low-friction-dismissal-compounds* anti-pattern:
when a quality-enforcement tool emits a diagnostic and the agent attributes it to
environmental noise without producing evidence — then repeats the dismissal as a
template for the next diagnostic, then the next — until legitimate signals accumulate
as silent failure. The contract is structural: dismissal requires a parseable evidence
block. Paraphrases cannot route around a shape-based requirement.

---

## Contract

When a quality-enforcement tool (type-checker, linter, formatter, security scanner,
or any tool the active F020 profile binds) emits a diagnostic that surfaces in the
agent's context — via `<new-diagnostics>` system reminders, verify-green output,
lefthook output, or any equivalent signal — the agent MUST emit a parseable evidence
block before dismissing the diagnostic.

**When the contract fires:**

- Any `<new-diagnostics>` system reminder appears in the agent's context.
- Any quality-tool output surfaces in verify-green stderr or lefthook stdout.
- Any IDE-integration diagnostic signal appears in any form.

**When the contract does not fire:**

- The diagnostic has already been addressed (the error is fixed in source).
- The tool re-run confirms the error is real (`evidence_type: error-is-real`); this is
  not a dismissal — it is an acknowledgment. The agent MUST proceed to fix the error.
- No quality-tool signal of any kind has appeared in the agent's context in the current
  session.

**Required fields (all four, all non-empty):**

| Field | Requirement |
|---|---|
| `tool_rerun_command` | Verbatim shell command executed to reproduce or refute the diagnostic |
| `tool_rerun_output` | Verbatim stdout+stderr captured from the re-run |
| `attribution` | One-line clause naming the dismissal reason |
| `evidence_type` | Controlled enum — one of: `interpreter-diff` \| `version-diff` \| `upstream-issue` \| `repro` \| `error-is-real` |

A dismissal without a complete evidence block is non-compliant. Empty fields signal
the agent went through the motions without actually doing the work.

---

## Required Evidence Block

The evidence block is a YAML structure emitted inline in the agent's response. Exactly
one block is permitted per dismissed diagnostic. Two or more blocks for the same
diagnostic are rejected as ambiguous.

**Schema:**

```yaml
tool_rerun_command: "<verbatim shell command the agent executed>"
tool_rerun_output:  "<verbatim stdout+stderr captured from the re-run>"
attribution:        "<one-line dismissal reason>"
evidence_type:      <interpreter-diff | version-diff | upstream-issue | repro | error-is-real>
```

**`evidence_type` enum definitions:**

| Value | Meaning |
|---|---|
| `interpreter-diff` | The tool is running against a different interpreter or runtime than the project uses (e.g., wrong virtual environment) |
| `version-diff` | The installed tool version differs from the project's pinned version, producing a spurious diagnostic |
| `upstream-issue` | The diagnostic is a known upstream bug in the tool itself, with a reference |
| `repro` | The agent attempted to reproduce the error in a controlled context and could not; evidence-of-absence provided |
| `error-is-real` | The tool re-run confirms the error exists in the project's canonical environment — this is not a dismissal; the agent MUST fix the error |

**Validation rules** (enforced by `scripts/diagnostic_evidence.py::validate_block`):

1. Exactly one YAML evidence block present (zero or two or more → rejected).
2. All four fields present and non-empty.
3. `evidence_type` is a member of the controlled enum (case-insensitive).
4. The block is parseable by `yaml.safe_load` (no arbitrary Python object tags).

**Multiple diagnostics in one turn:** When two or more distinct quality-tool
diagnostics surface in the same `<new-diagnostics>` payload, the agent MUST emit one
evidence block per distinct diagnostic. A single block covering multiple diagnostics
is rejected.

---

## Audit Log

Each dismissal event is appended as a JSONL row to
`.etc_sdlc/efficiency/turn-events.jsonl` (the F019 audit surface). Two `event_type`
values are defined for F021:

| `event_type` | Meaning |
|---|---|
| `diagnostic_dismissal_with_evidence` | Evidence block present and passes `validate_block` |
| `diagnostic_dismissal_missing_evidence` | Block absent or fails validation |

**Row schema:**

| Field | Type | Required | Notes |
|---|---|---|---|
| `ts` | ISO-8601 UTC string | always | Emission timestamp |
| `event_type` | string enum | always | One of the two values above |
| `feature_id` | string \| null | optional | Resolved from most-recent active feature directory; null when unresolvable |
| `wave_num` | int \| null | optional | Populated by Step 6c-adjacent emissions |
| `tool_name` | string \| null | optional | Tool that emitted the original diagnostic |
| `evidence_type` | string \| null | optional | Enum value from accepted block; null on missing-evidence events |
| `decision` | string enum | always | `accepted` \| `rejected` \| `unresolved` |
| `reason` | string \| null | optional | Rule name or failure reason on missing-evidence events |

**Invariants:**

- The audit log is append-only. No F021 code truncates it.
- Existing F019 readers tolerate unknown `event_type` values (forward-compatible).
- No PII, no source-code excerpts, no secrets appear in any payload field.
- `feature_id` resolution is best-effort; null is acceptable.

The emitter is `scripts/diagnostic_evidence.py::emit_event`. `/metrics` does not
surface these counts in this release; the data is captured forward-compatibly for a
future reporting PRD.

---

## Investigation Cycle Bound

Diagnostic investigation is time-bounded. The default bound is `DIAGNOSTIC_INVESTIGATION_TURNS=5` turns elapsed between a diagnostic surfacing and the agent emitting a compliant evidence block.

The bound is env-overrideable: set `DIAGNOSTIC_INVESTIGATION_TURNS` to any positive
integer in the environment before invoking the Stop hook. Non-numeric values are
rejected with a stderr warning and the default of 5 is used.

**Rationale:** Five turns matches the F019 stuck-loop-detection precedent (same
cognitive-load discipline, same override mechanism). It is long enough to allow a
genuine investigation (re-run the tool, inspect the environment, check upstream
issues) and short enough that an unresolved diagnostic is surfaced before it
compounds.

`hooks/check-completion-discipline.sh` uses `DIAGNOSTIC_INVESTIGATION_TURNS` as its
lookback window in the Step 1.5 residual scan. If a `<new-diagnostics>` reminder
appears at turn N and no evidence block is found in turns N through N+5, a Pattern B
warning is surfaced to stderr. This warning does not block the stop — the structural
defense is the per-wave gate at Step 6c.

**EC-001 (stop before window closes):** If the operator issues a stop command before
the investigation window closes, the Pattern B warning fires but does not block the
stop. The unresolved diagnostic is captured in the audit log as
`diagnostic_dismissal_missing_evidence` with `reason: investigation_window_incomplete`.
The operator's stop decision dominates.

---

## Forward-Only

This standard applies to features built after the F021 release tag
(`etc/feature/F021/release`). Features whose release tag predates `etc/feature/F021/release`
are not subject to evidence-block enforcement on past dismissals.

The `check-completion-discipline.sh` Step 1.5 extension and the `/build` Step 6c
per-wave gate fire on all subsequent build invocations regardless of the age of the
feature being built. The distinction is:

- **Past dismissals in F001–F020 features:** not retroactively invalidated; no audit-log
  entries are backfilled; prior `phase-N/done` tags are not invalidated.
- **New dismissals in any feature (including ongoing F001–F020 work) after F021 ships:**
  subject to this standard.

**Quality-tool errors that exist before F021 ships:** pre-existing errors are the operator's responsibility. The harness
does not document a migration path, baseline-capture mechanism, or grandfathering
exception. On first `/build` invocation against a project that has pre-existing errors,
the Step 6c gate will fail. The operator must resolve pre-existing errors using their
own tooling and judgment before `/build` will proceed. No migration path is documented
here by design: legacy debt is a project-level concern, and exposing the harness to
it would re-introduce the very compounding failure this standard defends against.

---

## Forbidden Phrases (Illustrative — Not Enforcement)

The following phrases have been observed as autoregressive dismissal templates — phrases
the model generates fluently without evidence because prior context makes them plausible:

- `"host-env false positive"`
- `"stale cache"`
- `"noise"`
- `"tooling drift"`
- `"diagnostic engine running elsewhere"`
- `"the IDE is confused"`

This list is DOCUMENTATION, not the enforcement contract. Literal phrase-matching would
be defeated by the first paraphrase. The enforcement contract is structural (the
Required Evidence Block — see Contract above), so paraphrases cannot route around it.

The seed list may grow over time via manual edits to this file, typically after a
`/postmortem` session surfaces a new dismissal template. Automated growth is
explicitly out of scope for F021.

---

## Examples

The following examples may reference specific tools by name. Normative sections above
do not.

**Example 1 — Environment mismatch (Pyright).**

A `<new-diagnostics>` reminder surfaces a `reportMissingImports` warning. The agent
suspects the type-checker is resolving the wrong environment.

```yaml
tool_rerun_command: "python3 -m pyright --pythonpath $(which python3) src/auth/login.py"
tool_rerun_output:  "0 errors, 0 warnings, 0 informations"
attribution:        "Diagnostic does not reproduce when pyright is pointed at the active venv interpreter"
evidence_type:      interpreter-diff
```

This block passes `validate_block`. The agent may dismiss the diagnostic.

**Example 2 — Error is real (mypy).**

```yaml
tool_rerun_command: "python3 -m mypy src/billing/invoice.py"
tool_rerun_output:  "src/billing/invoice.py:42: error: Argument 1 to \"charge\" has incompatible type \"str\"; expected \"Decimal\"  [arg-type]"
attribution:        "Re-run confirms type mismatch at invoice.py:42 is a real error in the active environment"
evidence_type:      error-is-real
```

This block is structurally compliant. `error-is-real` is not a dismissal — the agent
MUST proceed to fix `invoice.py:42` immediately. The wave gate at Step 6c will catch
the error if the agent does not.

**Example 3 — Upstream tool bug (eslint).**

```yaml
tool_rerun_command: "npx eslint --version && npx eslint src/components/Button.tsx"
tool_rerun_output:  "v8.57.0\n(node:1234) ExperimentalWarning: ...\n0 problems"
attribution:        "ESLint 8.57.0 has a known false-positive for this rule; upstream issue #16xxx; does not reproduce on re-run in this project's node_modules"
evidence_type:      upstream-issue
```

---

## Background

This standard is the third instance of the *low-friction-dismissal-compounds* family
(after F019 stuck-loop detection and the F021/F022-candidate sandbox-bypass discipline).
Together they form the harness's defense against low-friction agent behaviors that
optimize locally while degrading globally.

**Evidence basis: two same-day incidents (2026-05-20).**

- **Incident 1 (keystone-demo F004):** 13-wave build, 20+ dismissed `<new-diagnostics>`
  reminders, 13 Pyright errors shipped to main, one live runtime bug, 3-4 hours lost.
  The agent generated dismissals autogressively from a template; no re-run evidence was
  produced for any of the 20+ reminders.

- **Incident 2 (project redacted):** 4,323 quality-tool errors in 542 of 1,184 source
  files (46% of codebase), 5,452 test errors, build duration 11 min 38 s — caught at
  terminal Stop but only after multi-wave accumulation. Proves the per-wave gate (Step
  6c) is structurally required; a Stop-only defense is insufficient.

**Family memory:**

- `memory/feedback-diagnostic-dismissal-discipline.md` — first operator report
- `memory/feedback-stuck-loop-detector-proposal.md` — F019 pattern (investigation bound)
- `memory/feedback-sandbox-bypass-discipline.md` — F021/F022-candidate (same family)

**Closest architectural cousins:**

- F019 Chief Efficiency Officer (`hooks/chief-efficiency-officer.sh`) — audit-log surface
  and 5-turn bound precedent
- F020 profile dispatch (`hooks/verify-green.sh`) — per-wave quality gate composed here
- F015 spec-coupling (`hooks/check-spec-coupling.sh`) — structured-evidence at a lifecycle
  boundary (same pattern applied to spec drift)

---

## Anti-patterns

The following anti-patterns are registered for this failure family. Normative sections
above do not name specific tools; anti-pattern descriptions may.

**AP-F021-001 — Template dismissal without re-run.**
The agent emits a phrase like "this appears to be a Pyright host-environment
false positive" without executing the cited tool at all. The evidence block is absent.
Non-compliant. The gate at Step 6c will surface the unfixed error on the next wave.

**AP-F021-002 — lefthook-clean conflated with type/lint/format-clean.**
lefthook runs pre-commit hooks, which may be a subset of the full quality stack.
A clean lefthook exit does not imply zero mypy errors, zero ruff violations, or zero
formatter drift. The Step 6c gate runs the complete profile quality stack, not just
lefthook. Treating lefthook success as evidence of a passing quality gate is
non-compliant reasoning.

**AP-F021-003 — Single block covering multiple diagnostics.**
When two distinct diagnostics surface in one `<new-diagnostics>` payload, emitting
one evidence block with `attribution: "both errors are environment noise"` is rejected
by the validator. One block per diagnostic. This guards against the agent applying a
single canned explanation to a batch of unrelated errors.

**AP-F021-004 — Empty attribution field.**
Emitting `attribution: ""` satisfies the structural shape test only superficially.
`validate_block` rejects empty fields. The agent went through the motions without
doing the investigation.

**AP-F021-005 — Dismissing after error-is-real.**
If the agent's re-run produces an evidence block with `evidence_type: error-is-real`,
the diagnostic is confirmed. Continuing to write code without fixing the error first
is non-compliant. The Step 6c gate will catch the unfixed error at wave boundary; the
only question is how much additional work is wasted before it does.
