# Value Hypothesis Standard

## Status: MANDATORY

## Applies to: `/spec` skill, `/metrics` skill, `tasks.py validate` CLI, any reader of `value-hypothesis.yaml`

---

## Why This Exists (Anti-Goodhart Rationale)

Goodhart's Law: when a measure becomes a target, it ceases to be a good measure. Free-form "value statements" in PRDs are the classic victim — they are written to satisfy a process gate, not to be tested. After ship, nobody checks them, because there is nothing to check: no baseline, no threshold, no deadline, no measurement method.

`value-hypothesis.yaml` is the structural defense. By demanding a *testable* hypothesis at `/spec` time — with a numeric baseline, a numeric prediction, a direction, a measurement window, and a concrete method — the harness makes the hypothesis falsifiable before anyone has written a line of code. The status field then creates accountability: a feature is not done until it is `validated`, `invalidated`, or `unmeasured` (which is itself a signal that the team did not measure what it predicted). The headline `/metrics` rate — *% of shipped features whose hypothesis was validated within its window* — is meaningful only because the denominator is structurally honest.

This is anti-Goodhart by construction:
- The harness writes the hypothesis at spec time, not post-hoc.
- The harness auto-transitions `pending → unmeasured` when the window lapses without a measurement. Nobody can quietly let a hypothesis expire.
- The validation CLI (`tasks.py validate`) is mechanical: the measured value either crosses the threshold or it does not. Human judgment enters only in choosing what to measure, not in whether the threshold was met.

See BR-005, BR-006, BR-011, AC-004 through AC-006, AC-014, AC-015 in the feature spec for the normative requirements behind this standard.

---

## Schema

Every `/spec` session that produces a `spec.md` also writes `value-hypothesis.yaml` in the same feature directory. The file is never written with placeholder values; `/spec` prompts (Pattern B) until every required field has a non-null value (AC-005).

```yaml
schema_version: 1                        # integer; increment on breaking schema change
feature_id: "F042"                        # F<NNN>, assigned by /spec at Phase 5
author_role: "PM"                         # one of: SME, Engineer, PM, Designer, Other

who: "Enterprise customers onboarding via CSV import"   # who experiences the problem

current_cost:
  value: 4.5                             # numeric baseline
  unit: "hours per onboarding"           # human-readable unit
  source: "Support ticket analysis, Q4 2025 (n=23)"

predicted:
  value: 1.0                             # numeric target
  unit: "hours per onboarding"
  direction: "decrease"                  # "increase" | "decrease"
  threshold: 1.5                         # crossing this value counts as validated
                                         # for direction:decrease, measured <= threshold
                                         # for direction:increase, measured >= threshold

how_we_know: >
  We will sample 10 onboarding sessions in the 30 days post-ship,
  measure wall-clock time from first login to first successful import,
  and compute the median. Evidence stored in docs/measurements/F042-onboarding.md.

window_days: 30                          # days after the release tag before auto-unmeasured

status: "pending"                        # see Lifecycle below

validation:
  measured_at: null                      # ISO-8601 UTC timestamp, set by tasks.py validate
  measured_value: null                   # numeric, set by tasks.py validate
  evidence: null                         # path or URL, set by tasks.py validate
```

### Field reference

| Field | Type | Required | Notes |
|---|---|---|---|
| `schema_version` | integer | yes | Currently `1`. Forward-compat rule applies (see below). |
| `feature_id` | string | yes | Matches the feature directory `F<NNN>`. Immutable after write. |
| `author_role` | string | yes | Captured in the `/spec` Socratic loop (Pattern B). |
| `who` | string | yes | One sentence describing who experiences the problem being solved. |
| `current_cost.value` | number | yes | Numeric baseline. Must be measurable in the same unit as `predicted.value`. |
| `current_cost.unit` | string | yes | Human-readable unit. |
| `current_cost.source` | string | yes | Where the baseline came from. |
| `predicted.value` | number | yes | The target value after the feature ships. |
| `predicted.unit` | string | yes | Same unit as `current_cost.unit`. |
| `predicted.direction` | string | yes | `"increase"` or `"decrease"`. Any other value is rejected at the CLI. |
| `predicted.threshold` | number | yes | The value that the measurement must cross to count as validated. |
| `how_we_know` | string | yes | Concrete measurement method. Must name who measures, what they measure, and where the evidence lands. |
| `window_days` | integer | yes | Days from the `etc/feature/F<NNN>/release` git tag until `/metrics` auto-transitions to `unmeasured`. |
| `status` | string | yes | State machine value. Set by the harness; do not edit manually. |
| `validation.measured_at` | string or null | yes | Null until `tasks.py validate` runs. |
| `validation.measured_value` | number or null | yes | Null until `tasks.py validate` runs. |
| `validation.evidence` | string or null | yes | Null until `tasks.py validate` runs. Path must resolve inside the project working tree. |

---

## Lifecycle

The `status` field follows a fixed state machine. Manual edits to `status` are not supported; use the harness tooling.

```
               /spec Phase 5 writes file
                        │
                        ▼
                    [ pending ]
                   /           \
                  /             \
    tasks.py validate        window_days elapsed
    (measured value           without validate
     provided)                (/metrics auto-transitions)
         │                         │
         ▼                         ▼
  [ validated ]            [ unmeasured ]
  [ invalidated ]
```

- **`pending`** — Initial state. Written by `/spec` at Phase 5. The feature has shipped or is about to ship; no measurement has been recorded yet.
- **`validated`** — `tasks.py validate` was run, a measurement was recorded, and the measured value crossed `predicted.threshold` in the correct `predicted.direction`.
- **`invalidated`** — `tasks.py validate` was run, a measurement was recorded, and the measured value did *not* cross the threshold. The hypothesis was falsified.
- **`unmeasured`** — `/metrics` detected that `window_days` days have elapsed since the `etc/feature/F<NNN>/release` git tag and no `tasks.py validate` was run. The team did not measure the outcome they predicted. `unmeasured` is not a neutral state — it is a signal of process failure that the `/metrics` headline rate reflects.

State transitions are one-way: `validated`, `invalidated`, and `unmeasured` are terminal. There is no transition back to `pending`.

To record a measurement:

```bash
tasks.py validate F042 --measured 1.2 --evidence docs/measurements/F042-onboarding.md
```

The CLI sets `status` to `validated` or `invalidated`, records `measured_at` (current ISO-8601 UTC), `measured_value`, and `evidence`.

---

## Forward Compatibility

`schema_version` is an integer. The rule is:

- **Known version (`1`):** read and process normally.
- **Unknown future version (> `1`):** log a warning naming the file and the version found, skip the file, and continue. The `/metrics` report notes how many files were skipped for this reason. The harness never crashes on an unknown schema version (AC-006).

This rule applies to every reader: `/metrics`, `tasks.py validate`, and any tooling introduced by future PRDs. Readers must never assume the current schema version is the only version.

---

## Examples

### Example 1 — `status: validated`

A PM shipped a CSV import feature and measured onboarding time 3 weeks post-release.

```yaml
schema_version: 1
feature_id: "F042"
author_role: "PM"

who: "Enterprise customers onboarding via CSV import"

current_cost:
  value: 4.5
  unit: "hours per onboarding"
  source: "Support ticket analysis, Q4 2025 (n=23)"

predicted:
  value: 1.0
  unit: "hours per onboarding"
  direction: "decrease"
  threshold: 1.5

how_we_know: >
  Sample 10 onboarding sessions in the 30 days post-ship.
  Measure wall-clock time from first login to first successful import.
  Compute median. Evidence in docs/measurements/F042-onboarding.md.

window_days: 30

status: "validated"

validation:
  measured_at: "2026-03-14T10:22:00Z"
  measured_value: 1.1
  evidence: "docs/measurements/F042-onboarding.md"
```

The measured median was 1.1 hours. Because `direction: decrease` and `1.1 <= 1.5` (the threshold), `tasks.py validate` set `status: validated`.

---

### Example 2 — `status: unmeasured`

An engineer shipped a query-caching feature. The 14-day measurement window elapsed with no call to `tasks.py validate`.

```yaml
schema_version: 1
feature_id: "F051"
author_role: "Engineer"

who: "Internal dashboard users running ad-hoc report queries"

current_cost:
  value: 8.3
  unit: "seconds median query latency (p50)"
  source: "APM dashboard export 2026-03-01, sample window 7 days"

predicted:
  value: 2.0
  unit: "seconds median query latency (p50)"
  direction: "decrease"
  threshold: 4.0

how_we_know: >
  Pull p50 query latency from APM for the same dashboard report type,
  14 days post-ship, minimum 500 query sample. Compare to the baseline
  export. Evidence: link to APM report snapshot.

window_days: 14

status: "unmeasured"

validation:
  measured_at: null
  measured_value: null
  evidence: null
```

`/metrics` auto-transitioned `status` from `pending` to `unmeasured` when it detected that 14 days had elapsed since the `etc/feature/F051/release` tag and no validation had been recorded. This feature counts against the headline rate as an outcome that was not measured.

---

## Cross-References

- **Spec:** `.etc_sdlc/features/metrics-and-release-notes/spec.md`
- **Normative requirements:** BR-005, BR-006, BR-011
- **Acceptance criteria:** AC-004, AC-005, AC-006, AC-014, AC-015
- **Sibling standard:** `docs/standards/process/feature-numbering.md` — `F<NNN>` ID allocation and immutability rules
- **Validation CLI:** `~/.claude/scripts/tasks.py validate` — see `tasks.py --help validate` for argument reference
- **Measurement outcome:** `/metrics` outcome layer — reads all `value-hypothesis.yaml` files in `.etc_sdlc/features/*/`, skips features without the file (GA-003), segments results by `author_role`

---

## Origin

Adopted alongside the metrics-and-release-notes feature (`F<NNN>`). The anti-Goodhart design rationale and the three-layer metrics architecture are specified in `.etc_sdlc/features/metrics-and-release-notes/spec.md`. Gray-area decisions shaping this standard (GA-001 through GA-006) are recorded in `.etc_sdlc/features/metrics-and-release-notes/gray-areas.md`.
