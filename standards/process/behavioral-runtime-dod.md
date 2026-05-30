# Behavioral / Runtime Definition-of-Done Gate (Gap A)

## Status: MANDATORY
## Applies to: /build

## The Problem

etc's Definition of Done is **structural, never behavioral**. Every existing gate
reads a *proxy* for correctness — spec-enforcer reads artifacts, verify-green runs
mostly mock-backed tests, coverage/lint/stub-grep read structure. None can observe
"button click → no network call." The covr.care `pbj` retro proved the cost: F001
shipped with 738 tests green, spec-enforcer COMPLIANT, and a release tag — while the
running app rendered 0 rows and saving produced 0 network traffic. One feature became
seven tags, ~45 correction turns, and the defect reached a paying client.

This standard defines the **single source of truth** for the missing layer: before a
**clean** release tag, the assembled app is stood up with **real data + real auth**
and every spec-declared user-outcome AC is proven at runtime — OR explicitly deferred.

This standard is cited by-path; it is **not** duplicated by the SKILL, dispatcher, or
gate script. Those modules cite this file and implement what it pins.

## Lineage

Gap A is the **Consumer-Driven-Contracts *consumer*** of Gap B's liveness producer.
Gap B (`standards/process/contract-completeness.md`) *produces* the liveness
declaration at authoring time; Gap A *consumes* it at build/release time and proves
the code honors it. Gap B's ADR-001 named this producer/consumer split; ADR-002
versioned the liveness block precisely because Gap A ships later. **Do not duplicate
the liveness-block schema, the conflict rule, or the contract classes here** — they
live in their own MANDATORY standards.

Decisions binding this standard (the three Gap A ADRs):

- `docs/adrs/F-2026-05-30-behavioral-runtime-dod-gate-001-runtime-verify-profile-contract.md`
  — runtime-verify as a conductor-invoked per-profile script with a thin JSON contract.
- `docs/adrs/F-2026-05-30-behavioral-runtime-dod-gate-002-milestone-vs-clean-release-tag-routing.md`
  — milestone-vs-clean release tag routing.
- `docs/adrs/F-2026-05-30-behavioral-runtime-dod-gate-003-declaration-gated-totalization-release-rerun.md`
  — declaration-gated totalization with an authoritative release-time re-run.

Named industry prior art: Build-Verification / pre-promotion smoke gate; Pact's
`can-i-deploy` (release gated on all required consumers verified); Consumer-Driven
Contracts (the deferred-verification half Gap B ADR-001 named).

## The Declaration-Gated Rule

The gate is **declaration-gated, never blanket**. Building in waves means a half-built,
non-working system is a **legal intermediate state**. The gate consumes Gap B's liveness
block (`state.yaml.spec_phase.contract_completeness.liveness[]`); each user-outcome AC
carries a `live_at` (a milestone/wave id, or the literal `deferred`).

- **Per-wave (firing point: /build Step 6c sibling).** At a wave close, runtime-verify
  fires **ONLY** for ACs whose `live_at == <current wave>`. ACs declared live in a later
  wave, or `deferred`, are not checked now. A live AC returning `fail` blocks the wave
  close with the profile's evidence surfaced verbatim (zero-tolerance, mirroring
  verify-green). **Half-built waves are legal** — silence on not-yet-live ACs is correct,
  not a gap.

- **At release (firing point: /build Step 7.6 totalization).** The gate **totalizes**:
  *every* user-outcome AC MUST be either **verified-live** OR explicitly
  **deferred-with-reason**. The release re-run is **authoritative** (ADR-003) — all
  declared-live ACs are re-run against the assembled app, not trusted from per-wave
  records. There is no third state at release: an AC that is neither verified-live nor
  declared-deferred-with-reason hard-blocks the release.

The wave→live-AC mapping derives from `live_at`. The wave-planner is a **consumer** and
never re-declares liveness; the spec is the source of truth (if a wave names an AC live
but the spec's `live_at` names a different wave, the spec wins and the mismatch surfaces
as a planning warning).

## The runtime-verify Profile Contract

Each profile MAY ship `standards/code/profiles/<p>/runtime-verify.sh` — the behavioral
sibling of the F020 structural `verify-green.sh`, one level up. The profile **owns
stand-up and teardown**; the conductor owns orchestration and routing.

**Wire contract (transient JSON pipe — inputs as stdin JSON, never shell args):**

- **stdin:** `{"feature_path": <str>, "live_ac_ids": ["AC-3", …]}`
- **stdout:** `{"results": [{"ac_id": <str>, "status": "pass"|"fail"|"no-test", "evidence": <str>}]}`
- **exit 0** = ran (read per-AC `status`); **exit ≠ 0** = profile could not stand up
  (whole-profile error).

Field rules: `ac_id` matches `^AC-\d+$`; `status` is the closed enum
`pass | fail | no-test`; `evidence` is a free-form string, sanitized (strip
`[\x00-\x1f\x7f]`), `≤512` chars. AC ids and paths cross to the profile as JSON on
stdin — **never interpolated into a shell string** (metacharacter-injection defense).

**Stand-up obligations (the whole point of the gate):**

- Real data + real auth. Profiles **MUST NOT** stub authentication — `canActivate:()=>true`
  and equivalents are the exact defect this gate exists to catch.
- Credentials are env-bound / secret-manager-sourced, **never hardcoded**.
- Seed/fixture data reproduces declared outcomes without leaking real PII; fixtures
  mirror real response shapes (`lessons-fake-client-fidelity`).
- **Mandatory teardown.** A timed-out or failed stand-up MUST tear down (containers,
  ports, seeded rows) so a failed gate does not poison the next run.

**Dispatcher:** the conductor reads `.etc_sdlc/profiles.lock`, iterates active profiles,
invokes each `runtime-verify.sh`, and aggregates per-profile results. A missing profile
script or absent `profiles.lock` → **warn-and-skip** (parity with `hooks/verify-green.sh`).
This is a conductor-invoked script, **not** a Stop hook (ADR-001 — dissolves the #47
SubagentStop gap).

## The AC→Test Binding Convention

A live AC is proven by an e2e/smoke test **tagged with its AC id**. The profile selects
tests by id; **a live AC with no matching test returns `no-test`, which is a gate
failure** (a declared-live outcome with no runtime assertion cannot pass).

- **Python (CLI reference profile):** `@pytest.mark.ac("AC-3")` marker, or a
  `test_ac_3_*` name fallback.
- **Other profiles:** the equivalent stack-native tag keyed to the same `^AC-\d+$` id.

`standards/code/profiles/python/runtime-verify.sh` is the v1 reference implementation,
dogfoodable on this repo with no mocks. The web/Playwright profile (the load-bearing
pbj case, which cannot be exercised on etc's own CLI repo) is a declared follow-up.

## Milestone-vs-Clean Tag Routing

At Step 7.6 totalization, the terminal tag is routed by the totalized result:

| Condition | Outcome |
|-----------|---------|
| Every user-outcome AC **verified-live** | Clean tag `etc/feature/<id>/release`; feature moves to `shipped/`. |
| Any AC declared **`deferred`** (non-empty reason) + the rest verified | Milestone tag `etc/feature/<id>/milestone/<NNN>`; deferred set surfaced **loudly**; **not** a clean release; **not** moved to `shipped/` as a clean release. |
| Any **declared-live** AC `fail` or `no-test` | **Hard block** (exit 2; no tag; no `shipped/` move); routed to remediation like the 7.4/7.5 gates. |

Tag grammar (ADR-002): `etc/feature/<id>/release` (leaf, clean) and
`etc/feature/<id>/milestone/<NNN>` (under `milestone/`) are safe siblings. **A bare
`etc/feature/<id>/milestone` tag is FORBIDDEN** — it collides with the git ref hierarchy
under `milestone/<NNN>` (F025 git-ref-hierarchy lesson); `<NNN>` is a monotonic,
never-reused sequence. `git_tags.py` enforces the exit-code discipline (0 created / 1
degrade / 2 hard) and the bare-`milestone` rejection guard.

**Loud deferral surfacing (anti-gaming).** The deferred set is written to **both**
`verification.md` and `release-notes.md`. Mass deferral lists **every** deferral and is
**never** aggregated into a count — silent aggregation would re-enable the F001
green-but-broken failure (parity with the Gap B override-visibility invariant).

**Autonomous routing.** Under `/build --autonomous`, a hard-block (declared-live but
broken) routes through the existing `/goal` remediation loop (re-run until live ACs pass
or max-turns; on max-turns, stop with the live-AC failure surfaced — never a silent clean
tag). A declared-deferred → milestone outcome is a **LEGAL terminal state**: autonomous
accepts it and stops, and never tries to force a declared-deferred AC live.

## Opt-Out Hatches (Reuse, Do Not Fork)

All hatches reuse existing mechanisms; none introduces a new opt-out surface.

- **`infrastructure_only` (whole-feature exempt).** `state.yaml.spec_phase.infrastructure_only:
  true` exempts the entire feature from the runtime gate — no runtime-verify is
  dispatched. (This very feature's dogfood case: a harness-meta feature with no web
  surface.)
- **Per-AC `live_at: deferred(reason)` (granular).** The granular opt-out, owned by the
  Gap B liveness block. The reason MUST be non-empty (reuses Gap B's non-empty-reason
  invariant — an empty reason is rejected at spec/totalization time). A deferred AC routes
  to the milestone tag, never blocks.
- **F007/F008 stub-detection (live-vs-deferred classification).** Stub-detection
  (`standards/process/stub-marker-grep.md`) gains a live-vs-deferred classification layer:
  a stub backing a **declared-deferred** outcome is **legal**; a stub backing a
  **declared-live** outcome is a **BLOCKER**.
- **Per-profile time cap (default 600s, overridable per-feature).** A runtime-verify
  exceeding the cap is recorded as `fail` (no-evidence) and routed to remediation/deferral
  — the resource bound on stand-up; a false-fail is loud, never a silent skip.

## Forward-Only

The gate runs **only** when a liveness block is present, or `infrastructure_only` is set
(which exempts). Legacy features with no `contract_completeness.liveness` block are
**never gated and never auto-mutated** (parity with Gap B BR-007). A liveness block whose
`schema_version` is higher than known triggers **warn-and-skip**, not a crash (Gap B
ADR-002 forward-compat contract). A present-but-empty `liveness: []` (no user-outcome ACs)
totalizes trivially → clean release.

## Cross-References

- `standards/process/contract-completeness.md` — Gap B, the liveness **producer**; owns
  the liveness-block schema, the five contract classes, and the `live_at` /
  `deferred_reason` invariants this gate consumes. **Not duplicated here.**
- `standards/process/source-of-truth-conflict-rule.md` — the standing `{code, spec,
  prototype}` tie-breaker when sources disagree about a declared outcome.
- `standards/process/stub-marker-grep.md` — F007/F008 stub-detection, extended here with
  the live-vs-deferred stub classification.
- `standards/process/user-flow-completeness.md` — the WARN-gate machinery and surfacing
  pattern this gate's loud-deferral surfacing mirrors.
- `standards/code/profiles/python/README.md` — the python profile whose
  `runtime-verify.sh` is the v1 reference implementation.
- `hooks/verify-green.sh` — the F020 structural-gate dispatcher whose shape the
  runtime-verify dispatcher mirrors one level up.
- `skills/build/SKILL.md` — implements the Step 6c per-wave sibling, the Step 7.6
  totalization, tag routing, and autonomous routing pinned here.
- `scripts/runtime_totalization_check.py` — the Step 7.6 gate (exit 0/1/2, structured
  report) that implements totalization and tag routing.
- `scripts/git_tags.py` — milestone tag grammar + the bare-`milestone` rejection guard.

**Origin:** covr.care `pbj` build retrospective; one feature → seven tags, ~45 correction
turns; F001 shipped 738 tests green + COMPLIANT + a release tag with 0 rows / 0 network
traffic. Gap A (#51) of the pbj retro. Root cause: `spec/pbj-retro-harness-gaps.md` §4;
memory `lessons-pbj-behavioral-gate-and-feedback-loop-leak.md`.
