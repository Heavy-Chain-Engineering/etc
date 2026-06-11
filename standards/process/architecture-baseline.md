# Architecture Baseline — Discover → Verify → Ratify → Enforce

## Status: MANDATORY
## Applies to: /init-project, /build, /spec, /architect, /rule-sweep

## The Problem

When etc initializes an organically-grown brownfield codebase, it produces
**descriptive** context (what exists) but no **normative** context (what new code
must conform to). Agents then place code by inference from inconsistent precedent —
and because every wrong placement has *some* sibling precedent, the agent
confidently does the wrong thing.

The covr.care `pbj` build is the verified consequence:

- Existing layering docs and golden exemplars went **undiscovered** — the agent
  never saw the team's own conventions.
- etc's own generated `DOMAIN.md` carried a **factually wrong** system-boundary
  claim that no step ever checked against the tree.
- Unwritten conventions were **authored mid-crisis**, after the wrong code had
  already shipped.

This standard defines the **single source of truth** for the fix: a four-stage
loop run at `/init-project` time that turns a brownfield repo's scattered,
unverified, undiscovered conventions into one ratified baseline that downstream
phases can trust. The loop is **DISCOVER → VERIFY → RATIFY → ENFORCE**.

This standard is cited by-path; it is **not** duplicated by the SKILL, the CLI
(`scripts/baseline.py`), the dispatcher, or the gate scripts. Those modules cite
this file and implement what it pins. The YAML schema, exit codes, and wire
contracts live in `design.md` and the ADRs — this standard owns the *semantics*,
not the format.

## The Four-Stage Loop

The loop is a new phase inside `/init-project` plus three downstream consumers,
organized around one load-bearing artifact — the machine baseline at
`.etc_sdlc/architecture-baseline.yaml` — and its generated human twin
`ARCHITECTURE.md` at the repo root (ADR-001). No stage talks to another except
through that file.

### 1. DISCOVER — find the normative artifacts

A read-only parallel agent fan-out (the discovery-surveyor) inventories candidate
**normative** artifacts (convention docs, ADRs, lint configs, generators,
reference implementations, agent docs), ranks **exemplar candidates** by measured
pattern adherence, and detects **cross-repo seams** (env-var-loaded remote
frontends, shared auth/session, shared data schemas). Output is a draft inventory
and seam record — claims about what *should* govern the repo, not yet trusted.

DISCOVER answers *"what conventions claim authority here?"* — it does not yet
believe any of them.

### 2. VERIFY — check every claim against the tree

Every claim a discovered artifact makes is checked against the actual code and
classified into the **claim classification enum** (closed set):

| Classification | Meaning | Enters agent context? |
|---|---|---|
| `VERIFIED` | The claim matches the tree (evidence: matching paths/files cited). | **Yes — silently.** Only VERIFIED claims become tier-0 normative context. |
| `STALE` | The claim was once true but the tree has moved on. | No — surfaced for ratification. |
| `ASPIRATIONAL` | The claim describes an intended-but-unrealized convention. | No — surfaced for ratification. |
| `CONTRADICTED` | The tree actively does the opposite of the claim. | No — surfaced for ratification. |

This is the **verify-don't-honor** rule (ADR-003): a discovered doc is *untrusted
input*. A wrong doc costs **one ratification decision**, never a misbuilt feature.
**Only `VERIFIED` claims enter agent context, and they enter silently** — no
ceremony for a claim the tree already confirms. Everything else is escalated to a
human in RATIFY. VERIFY is evidence-based, not exhaustive: on giant repos sampling
is bounded and the discovery report names what was sampled (never a silent
truncation).

### 3. RATIFY — a human blesses the baseline

A sequential, interactive matrix walk over every non-`VERIFIED` claim and every
competing-pattern concern. The human:

- adopts, supersedes, or records-a-decision-for each non-VERIFIED claim;
- **blesses exemplars** ("copy this for new features like X");
- marks **do-not-copy** zones (superseded generations, migration targets);
- confirms the **cross-repo boundary map**;
- accepts the computed **confidence** (low/medium/high, with auditable inputs).

On completion `scripts/baseline.py ratify` performs the **one-way
`unratified → ratified` transition** and renders `ARCHITECTURE.md`. The transition
is one-way **by design**: there is deliberately no de-ratify command (supersede by
re-running the phase). `ratified_by` is **attestation, not authentication** — a
recorded operator name whose accountability lives in the audit record and git
history, mirroring the spec-enforcer operator-attestation precedent.

### 4. ENFORCE — native-tool-first conformance + rule-and-sweep

Ratified rules are mechanized **native-tool-first** (ADR-004): a rule lands in the
project's own fitness-function / lint tool where one exists, so conformance
survives after etc leaves; otherwise it lands in a per-profile `baseline-verify.sh`
checker dispatched by the `hooks/baseline-verify.sh` conductor (the F020
warn-and-skip fallback — python reference profile first, others warn-and-skip).
`/build` runs the checker at **wave gates** (after `verify-green`). The
`/rule-sweep` skill captures a new rule mid-build via `baseline.py append-rule`,
sweeps the repo, and re-runs the checker — rules **accrete without reopening
ratification**.

## The Three-State Gate

`/build`, `/spec`, and `/architect` consume the baseline through a single token —
`baseline.py status <repo_root>` prints exactly one of `missing | unratified |
ratified | malformed`. **Callers branch on the TOKEN, never the exit code.**
`missing` and `malformed` are *computed*, never stored; the stored status enum is
only `{unratified, ratified}`.

| State | `/build` behavior | `/spec` + `/architect` behavior |
|---|---|---|
| **missing** | **SOFT** — emit the EXACT verbatim backfill offer naming `/init-project --phase=baseline`, then **PROCEED**. (Every legacy repo lives here; zero upgrade friction.) | WARN with recorded override. |
| **unratified** | **HARD STOP** naming the ratify command. This is the **recorded-intent** state — an operator started ratification and abandoned it — so it is **not** a heuristic false positive. This is the scoped ADR-002 deviation from advisory-default (see below). | WARN with recorded override. |
| **malformed** | **STOP as an infrastructure failure.** A corrupt ratification record is **never** treated as ratified. | STOP / treat as infrastructure failure (never silently "pass"). |
| **ratified** | **PASS** — gates proceed and the `baseline-verify` conformance checker runs at each wave gate. | PASS — VERIFIED claims are available as normative context. |

The `missing` warning string is **exact and contract-pinned** — it is the same
"verbatim, never paraphrased" discipline the runtime-DoD and contract-completeness
gates use, so the backfill offer is testable and never drifts.

### Why `unratified` hard-blocks (the ADR-002 deviation)

The house gate posture is **advisory-default** — hard-block only on a recorded
escalation flag, because cry-wolf false positives destroy gate trust (the
F007/F008 lesson; layered-review ADR-003). This standard **deviates** by
hard-blocking on `unratified`, and the deviation is **scoped to recorded-intent
states only**:

- `unratified` is reachable **only** after an operator initiated the baseline
  phase and then abandoned ratification. It is a recorded intent, not a guess —
  exactly the class advisory-default does not protect.
- `missing` — the ambiguous state where every legacy project lives — keeps the
  **soft** path, preserving advisory-default's rationale precisely where it
  applies.

Future gate authors **must not** cite this as license to hard-block on heuristics.
The deviation applies **only** to recorded-intent states. The full rationale is in
ADR-002; it is **not** duplicated here.

### The baseline-exempt hatch

A repo may be declared `baseline-exempt` with a **recorded, non-empty reason**.
An exempt repo is treated as `missing` (soft path) and never hard-blocks — the
escape valve for a repo whose operators deliberately decline ratification (e.g., a
throwaway prototype, a repo etc only reads). The exemption is recorded and
auditable, never silent, mirroring the WARN+recorded-override discipline used by
the contract-completeness gate. It is the *only* sanctioned way out of the
`unratified` hard-stop other than finishing ratification.

## Forward-Only

A `missing` baseline **never blocks anything** — legacy repos get the soft warning
plus the backfill offer and proceed. `ARCHITECTURE.md` is a brownfield-only,
forward-only artifact: it is added to `check-tier-0.sh`'s self-exemption list
**only** (so it is creatable), and its presence is **never** added to any block
condition. No existing artifact is auto-mutated. A future `schema_version` higher
than known triggers **warn-and-skip**, never a crash (the contract-completeness
ADR-002 forward-compat precedent).

## How to Verify

- **The loop and its semantics are pinned here, implemented elsewhere.** Confirm
  `skills/init-project/SKILL.md` runs DISCOVER→VERIFY→RATIFY and
  `--phase=baseline` is the backfill path; confirm `scripts/baseline.py status`
  emits exactly the four tokens and `ratify` performs a one-way transition.
- **Three-state gate.** `skills/build/SKILL.md` branches on the status token per
  the table above; the `missing` warning is contract-test-pinned verbatim;
  `unratified` and `malformed` STOP; `ratified` runs `baseline-verify` at wave
  gates. `skills/spec/SKILL.md` and `skills/architect/SKILL.md` WARN-with-recorded-
  override on the non-ratified states.
- **Claim ledger.** Only `VERIFIED` claims are injected as normative context
  (`hooks/inject-standards.sh` conditional `ARCHITECTURE.md` summary); non-VERIFIED
  claims require a ratification `resolution` before `baseline.py ratify` succeeds.
- **Exempt hatch.** A `baseline-exempt` repo carries a recorded non-empty reason
  and follows the soft path.

## Cross-References

- `standards/process/lessons-terminate-in-gates.md` — the standing rule that a
  lesson must terminate in a built gate, not memory. This standard **is** the gate
  the covr brownfield-discovery lesson terminates in; **not duplicated here.**
- `standards/process/contract-completeness.md` — Gap B's authoring-time contract
  capture and its WARN-with-recorded-override machinery, which this standard's
  exempt-hatch and `/spec`+`/architect` override paths reuse; **not duplicated
  here.**
- `standards/process/behavioral-runtime-dod.md` — Gap A's runtime DoD gate; the
  `baseline-verify` conformance checker mirrors `runtime-verify`'s
  conductor-invoked, JSON-results, warn-and-skip dispatcher shape one surface over.
  **Not duplicated here.**
- `docs/adrs/F-2026-06-10-brownfield-architecture-baseline-001-baseline-artifact-pair.md`
  — the machine-YAML source + generated `ARCHITECTURE.md` twin, root placement.
- `docs/adrs/F-2026-06-10-brownfield-architecture-baseline-002-three-state-gate-deviation.md`
  — the three-state gate and the scoped advisory-default deviation (the rationale
  for the `unratified` hard-block; **not duplicated here**).
- `docs/adrs/F-2026-06-10-brownfield-architecture-baseline-003-verify-claims-not-honor-docs.md`
  — verify-don't-honor + the parallel discovery fan-out engine; the claim
  classification enum semantics.
- `docs/adrs/F-2026-06-10-brownfield-architecture-baseline-004-native-tool-first-conformance.md`
  — native-tool-first conformance with the F020 per-profile fallback.
- `docs/adrs/F-2026-06-10-brownfield-architecture-baseline-005-workspace-topology.md`
  — per-repo baselines plus the workspace seam map and read-only mirrors.
- `scripts/baseline.py` — the single owner of the three YAML formats: schema,
  validation, `status`, the one-way `ratify` transition, `append-rule`, seam sync,
  and `ARCHITECTURE.md` rendering. This standard states the RULE; the CLI carries
  the format.
- `skills/init-project/SKILL.md` — the DISCOVER/VERIFY/RATIFY phase and the
  `--phase=baseline` backfill path.
- `skills/build/SKILL.md` — the Step 1c-sibling three-state gate and the
  wave-gate `baseline-verify` run.
- `skills/rule-sweep/SKILL.md` — mid-build rule capture and repo-wide sweep.

**Origin:** covr.care `pbj` build — existing layering docs and golden exemplars
went undiscovered, etc's generated `DOMAIN.md` carried a factually wrong
system-boundary claim, and unwritten conventions were authored mid-crisis. The fix
is to discover, verify, ratify, and enforce the baseline *before* the first agent
places code. See `spec/discovery.md` and project memory for the full failure-mode
analysis.
