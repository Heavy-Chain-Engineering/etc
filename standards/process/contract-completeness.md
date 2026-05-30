# Contract-Completeness for /spec and /architect

## Status: MANDATORY
## Applies to: /spec, /architect

## The Problem

etc specs today are *feature-complete* — they describe what the user sees — but
not *contract-complete*: they do not pin what the system guarantees. The
covr.care `pbj` build is the verified consequence. One feature became seven
feature tags and ~45 correction turns, with the dominant product-ownable cost
coming from contracts the spec never pinned:

- A **time-format gap** the spec never decided spawned 8 contradictory regexes
  across the build and a silent `total_hours = 0` P0.
- **Federally-required fields** were specified as UI columns instead of
  API-response obligations, so the API returned them blank and the UI rendered
  blank — "user sees X" was satisfied on paper while "API returns X" was not.
- A **`{code, spec, prototype}` conflict** had no tie-breaker; the build
  guessed differently each tag until a rule was invented at tag 6.

Critically, covr F006 ran the **full** `/spec`+`/architect` pipeline and still
surfaced 19 gaps — proving the Socratic phases do not probe contract level
today. This is an etc-harness gap, not merely a spec-author gap.

This standard defines the contract that closes the gap at authorship: before a
spec or design is finalized, each of five contract classes is elicited and
warned-when-missing, so the build never has to guess a guarantee the author
could have pinned.

## Lineage (Established Vocabulary)

These five contract classes are not novel; they map onto 40 years of named
requirements-engineering prior art (per
`docs/adrs/F-2026-05-29-contract-completeness-001-adopt-established-vocabulary.md`).
The feature keeps the name **contract-completeness** = ISO 29148's *completeness*
characteristic applied to *contracts*.

- **Design by Contract** (Meyer) — format contracts and response-DTO
  obligations are pre/postconditions. `accept-on-input` is a precondition (the
  client's obligation); `storage` / `wire` / `display` format and the
  response-DTO guarantee are postconditions (the supplier's guarantee).
- **Consumer-Driven Contracts** (Pact) — DTO obligations reflect what the
  *consumer* needs, not what the provider happens to implement. The deferred
  build-time half (checking code *honors* the contract) is the **CDC verify
  half**, named future work (Gap A #51 + a contract-testing follow-up).
- **Specification by Example / ATDD** (Adzic) — the per-outcome liveness
  declaration and its "fully-functional" acceptance statement are acceptance
  examples. Adzic's communication-gap thesis *is* the pbj thesis.
- **ISO/IEC/IEEE 29148** — the umbrella property: requirements (and therefore
  contracts) must be **complete, unambiguous, and verifiable**.
- **Definition of Ready** (Scrum/Agile) — the gate. We add contract criteria to
  an existing named DoR gate; we do not invent an SDLC step.

The prior art independently confirms the F006 phase split: DbC pre/postconditions
on *data* are architecture (`/architect`); Specification-by-Example acceptance
examples are *intent* (`/spec`).

## The Five Contract Classes

Each class is elicited in one phase per the F006 intent-vs-architecture split.
Each is declared as a **canonical sentence appended to the relevant AC**
(BR-008) — grep-able and co-located with the AC it constrains, exactly as
`user-flow-completeness.md` appends its User-flow sentence.

| # | Contract class | Phase | Lineage |
|---|----------------|-------|---------|
| 1 | Per-outcome **liveness + milestone** | `/spec` | Specification by Example / ATDD |
| 2 | **Source-of-truth conflict** (in-play sources) | `/spec` | — (see sibling standard) |
| 3 | **Open-question → BLOCKER** | `/spec` | Definition of Ready |
| 4 | **Format contracts** (storage/wire/display/accept) | `/architect` | Design by Contract (pre/postconditions) |
| 5 | **Response-DTO obligations** | `/architect` | Design by Contract + Consumer-Driven Contracts |

### Canonical Declaration Sentences (BR-008)

Each contract class has one grep-able sentence form. The forcing function is
that the sentence cannot be written without naming the element the gap omits.

**1. Liveness + milestone** *(appended to each user-outcome AC)*

> `"Live at {milestone-id|deferred}; fully-functional means: {one acceptance statement}."`

Example:

> `"Live at wave-2; fully-functional means: on save, a network call persists the drawer edit and a reload shows it."`

When `deferred`, the sentence must carry a reason:

> `"Live at deferred ({reason}); fully-functional means: {acceptance statement}."`

**2. Source-of-truth conflict** *(appended once, at the feature level)*

> `"Sources in play: {subset of code, spec, prototype}; conflicts resolved per source-of-truth-conflict-rule."`

The rule itself — majority of `{code, spec, prototype}` wins, escalate dissent,
spec-authoritative copy marked `[SPEC-WINS]` — is a separate **MANDATORY**
standard at `standards/process/source-of-truth-conflict-rule.md`. **Do not
duplicate it here.** This standard only captures *which* sources are in play for
a given feature; the conflict rule is always in force and never re-litigated per
feature.

**3. Open-question → BLOCKER** *(appended to the AC the question blocks)*

> `"BLOCKER: {unresolved contract question} — owner: {named owner}."`

A BLOCKER lets a spec proceed in a flagged, auditable state rather than only
hard-rejecting. It is written to `state.yaml` (see Liveness Block schema below)
and surfaced downstream. It never auto-clears; clearing it is an explicit
operator action.

**4. Format contract** *(appended to each AC naming a boundary-crossing field)*

> `"Format of {field}: storage={…}; wire={…}; display={…}; accept-on-input={…}."`

Example:

> `"Format of clock_in: storage=UTC ISO8601; wire=HH:mm; display=h:mm a; accept-on-input=^([01]\d|2[0-3]):[0-5]\d$."`

If the build would need a regex, the design has already decided what it matches.
A field may legitimately omit a line that does not apply (e.g., a field never
displayed has no `display=`); omission is explicit, not silent.

**5. Response-DTO obligation** *(appended to each AC naming an externally/federally-required field)*

> `"API-response guarantee: {DTO/endpoint} returns {field} ({type/constraints})."`

Example:

> `"API-response guarantee: GET /timesheets returns total_hours (non-null decimal, federally required)."`

This is the pbj fix: **"user sees X" ≠ "API returns X."** A required field is
declared as a response-DTO guarantee, not merely a UI column.

## Detection Signal Lists (Skill-Prose, GA-002)

Detection is **skill-prose** in `/spec` and `/architect` reading the signal
lists below — exactly like `user-flow-completeness.md`'s signal list.
**There is NO new Python detector** (GA-002): no function signature, no parser,
no module. The skill classifies each AC against these lists and runs the
matching elicitation step. The lists are deliberately loose; false positives are
disambiguated by the author at the Phase-3 elicitation step, never silently.

### Signal list A — user-outcome AC (triggers liveness elicitation, `/spec`)

An AC describes a user outcome when ANY of these is present:

- **Observable-outcome verbs:** `see`, `view`, `observe`, `appears`, `shows`,
  `displays`, `persists`, `survives reload`, `is saved`, `is sent`, `receives`.
- **A user-facing surface** as classified by `user-flow-completeness.md`'s
  signal list (route paths, UI nouns, user verbs).
- **A state change the user can later confirm** — "on save…", "after submit…",
  "the record now…".

A pure-internal AC (no observable outcome, no user-facing surface) is **not** a
user-outcome AC; the liveness check stays silent (no false-positive WARN on
internal logic — Edge Case 1).

### Signal list B — boundary-crossing field (triggers format-contract elicitation, `/architect`)

A field crosses a boundary — and therefore needs a format contract — when ANY of
these is present:

- **Field is read or written across a tier:** persisted to storage, sent over
  the wire (HTTP/JSON/protobuf), rendered for display, or accepted from input.
- **Type with a representation choice:** time, date, datetime, duration,
  money/currency, decimal/precision, enum, timezone, locale-sensitive string,
  ID/slug format, phone, email.
- **The AC or design implies a regex, parse, or format conversion** — any
  "format as…", "parse…", "validate…", "must match…" phrasing.

A field used only inside one tier with no representation choice (e.g., a boolean
flag passed between two internal functions) is **not** boundary-crossing; the
check stays silent.

### Signal list C — externally/federally-required field (triggers DTO-obligation elicitation, `/architect`)

A field carries a response-DTO obligation when ANY of these is present:

- **Regulatory / compliance language:** `federally required`, `regulatory`,
  `compliance`, `audit`, `legally mandated`, `mandated by {authority}`,
  `required by {standard}`.
- **An external consumer depends on the field:** named in an integration,
  export, report, downstream system, partner API, or CSV/PDF deliverable.
- **The field is specified as visible** (a UI column, a report row, an exported
  value) **but its API-return path is unstated** — the exact pbj failure shape.

If a required field is mentioned only as a UI column with no API-response
guarantee, classification C fires and `/architect` WARNs.

### Dedup rule

A field referenced by several ACs needs **one** declaration; the check dedupes
by field name and does not demand duplicate sentences across ACs (Edge Case 8).

## Enforcement Model (WARN-with-Recorded-Override)

All five contract checks are **WARN + recorded-override** — none hard-blocks
(per `docs/adrs/F-2026-05-29-contract-completeness-003-warn-with-recorded-override.md`,
BR-006). This mirrors `user-flow-completeness.md`'s "Enforcement Model
(WARN-with-YES/NO Gate)" and reuses its code paths (BR-010): Phase 3 per-AC
elicitation, Phase 4 WARN gate, deferral, sanitization — no forked module.
Legitimate exceptions exist (backend-only ACs, genuinely-internal logic,
`infrastructure_only` features, intentionally-deferred outcomes), which is why
the gate guides rather than strangles.

### Phase 3 — Auto-detection and per-AC elicitation

After the AC section is drafted, the skill classifies each AC against the signal
lists above and, for each match, presents the AC with a prefilled canonical
declaration sentence drafted from surrounding prose, prompting the author via
`AskUserQuestion` (Pattern A) to:

1. **Accept the draft sentence (Recommended)** — appended verbatim to the AC.
2. **Refine — I have changes** — a Pattern B (`**▶ Your answer needed:**`)
   follow-up captures the revised sentence, then re-prompts.
3. **Mark not-applicable** — the AC is recorded as exempt (e.g.,
   `surface_status: backend_only` for liveness, or "no boundary-crossing field"
   for format) and no sentence is required.

An AC that already contains the canonical sentence form for its class is treated
as already-compliant; the elicitation step is skipped for that AC.

### Phase 4 — Definition-of-Ready gate

The skill enumerates ACs flagged in Phase 3 and checks whether each carries its
required declaration sentence. If any is missing, the gate enters a **WARN** and
presents the offending AC list via `AskUserQuestion` (Pattern A):

1. **No, fix the missing contracts first (Recommended)** — return to Phase 3.
2. **Yes, proceed — these contracts are intentionally deferred** — for each
   offending AC, record an override in
   `state.yaml.spec_phase.contract_completeness.overrides[]` with a **non-empty
   reason**, and surface it downstream into `verification.md` / `release-notes`.

The gate does **NOT** hard-block. Selecting "Yes, proceed" is recorded so the
deferral is auditable; it is not a policy violation. **Silent dismissal is
prohibited** — every override carries a reason and is surfaced downstream.

### Override visibility (integrity control)

If an operator defers *every* contract, all deferrals are listed **loudly** in
`verification.md` / `release-notes`; mass-deferral must stay conspicuous, never
aggregated-away (Edge Case 4). Silent aggregation would reproduce the F001
"green-but-broken" failure — the audit trail's loudness is a property of the
gate. WARN+override is gameable by mass-deferral at this tier; it is *mitigated*
by override-visibility and *eliminated* only by Gap A (#51) totalizing liveness
at release.

### Forward-only (BR-007)

Detection runs on **current artifacts only**. Legacy specs/designs predating this
standard are **never auto-mutated**. Re-running the checks on a legacy artifact
offers the author the same accept / refine / defer escape hatches and changes
nothing on disk unless the author acts (Edge Cases 5, 7).

## Liveness Block Schema (BR-009 Producer Interface)

The one new persisted structure is the **liveness block**, written by `/spec`
under `state.yaml.spec_phase.contract_completeness`. This block is the
**published producer interface that the behavioral/runtime DoD gate (Gap A,
tracker #51) consumes** — Gap A is `blocked-by` this feature and reads this block
without re-specifying it. Per
`docs/adrs/F-2026-05-29-contract-completeness-002-versioned-liveness-interface.md`,
the block is **versioned**.

Format/DTO contracts deliberately get **no** machine block — they live as
canonical sentences in `design.md` (DbC-style, human + grep), because per YAGNI
they have no known machine consumer; only liveness does. Machine-readability is
added when a consumer appears, not speculatively.

```yaml
spec_phase:
  contract_completeness:
    schema_version: 1                 # ADR-002: versioned producer interface
    liveness:
      - ac_id: AC-3
        outcome: "saving a drawer edit persists and survives reload"
        live_at: wave-2               # milestone id, or the literal "deferred"
        acceptance_statement: "on save, a network call persists X; a reload shows it"
        deferred_reason: null         # REQUIRED (non-null) iff live_at == "deferred"
    blockers:
      - question: "<unresolved contract question>"
        owner: "<named owner>"
        raised_at: "<ISO8601>"
    overrides:                         # WARN-override audit trail (BR-006)
      - contract_class: format|dto|liveness|conflict|blocker
        ref: "<AC id or field name>"
        reason: "<operator override reason>"
        recorded_at: "<ISO8601>"
    conflict_sources: [code, spec, prototype]   # which sources are in play
```

### Invariants

- `schema_version` is present and an integer.
- `deferred_reason` is non-empty iff `live_at == "deferred"`.
- Every `override.reason` and every `blocker.owner` is non-empty.
- All free-form fields are sanitized at the capture site (BR-011): strip
  `[\x00-\x1f\x7f]`, cap length. Nothing unsanitized reaches `state.yaml`,
  `verification.md`, or `release-notes`.
- The block is written **merge-preserve** — `contract_completeness` slots
  alongside existing `spec_phase` keys without clobbering them.

### Forward-compatibility contract (warn-and-skip)

A consumer (Gap A, or any future liveness reader) that encounters a
`schema_version` **higher than it knows MUST warn-and-skip — never crash** (the
`value-hypothesis.yaml` / `/metrics` forward-compat precedent). This lets Gap A
evolve the liveness shape (e.g., add a verification-method field) without
breaking on features specced today at v1, and lets old features stay readable by
a future consumer. The block being versioned means it cannot be casually
reshaped: changing it requires a version bump plus the warn-and-skip path — the
deliberate cost of BR-009.

### Consumer contract (Consumer-Driven)

Each `liveness[]` entry guarantees `{ac_id, outcome, live_at,
acceptance_statement, deferred_reason?}`. The shape reflects what Gap A needs —
this is a Consumer-Driven Contract. The consumer reads the array, tolerates
unknown higher versions by warn-and-skip, and never crashes.

## Scope

This standard governs **authoring-time capture + WARN** in `/spec` and
`/architect`. The following are explicitly **out of scope** (named, not vague):

- **Build/runtime verification that code honors the contracts** — the CDC/
  contract-testing **verify half**. Gap A (#51) + a contract-testing follow-up.
- **The behavioral/runtime DoD gate itself (Gap A, #51).** This standard
  *produces* the liveness declaration; it does not *consume* it.
- **Auto-inventing contracts.** The phases *elicit* (and may research-fill with
  citation); they never guess a format/DTO the operator did not confirm.
- **Retrofitting existing specs** (forward-only, BR-007).

`/architect`-gated checks (format, DTO) are simply **not evaluated** when
`/architect` is skipped (`chain_later` / `non_engineering`) — the gate does not
silently "pass"; `/build` Step 1c's design-absent warning is the backstop
(Edge Case 6).

## Worked Example (pbj total_hours)

The canonical reference is the covr.care `pbj` failure that motivated this
standard.

### Before (feature-complete, not contract-complete — violates this standard)

> "AC-7: The timesheet view shows each employee's total hours for the pay
> period."

This is feature-complete: it names what the user sees. It pins no liveness, no
time format, and no API-response guarantee for the federally-required
`total_hours`. The build guessed a time format (8 contradictory regexes), shipped
a silent `total_hours = 0` P0, and rendered the federally-required field blank
because it was specified as a UI column, not a response-DTO obligation.

### After (contract-complete — compliant)

> "AC-7: The timesheet view shows each employee's total hours for the pay
> period."
>
> `"Live at wave-2; fully-functional means: opening the timesheet view issues a network call that returns computed total_hours, and a reload shows the same value."`
>
> `"Format of clock_in: storage=UTC ISO8601; wire=HH:mm; display=h:mm a; accept-on-input=^([01]\d|2[0-3]):[0-5]\d$."`
>
> `"API-response guarantee: GET /timesheets returns total_hours (non-null decimal, federally required)."`

The liveness sentence forces a real acceptance statement (the future Gap A
consumes it). The format sentence pins the one time format the build otherwise
guessed eight times. The DTO sentence makes the federally-required field an API
guarantee, not a blank UI column.

## Cross-References

- `standards/process/source-of-truth-conflict-rule.md` — the MANDATORY
  `{code, spec, prototype}` conflict rule (majority wins, escalate dissent,
  `[SPEC-WINS]`). Cited by contract class #2; **not duplicated here.**
- `standards/process/user-flow-completeness.md` — the near-exact structural
  precedent this standard mirrors and whose gate machinery it reuses (BR-010);
  also the source of the user-facing-surface signals referenced in signal list A.
- `standards/process/interactive-user-input.md` — Pattern A (`AskUserQuestion`)
  and Pattern B (`**▶ Your answer needed:**`) rules governing Phase 3
  elicitation and the Phase 4 gate.
- `skills/spec/SKILL.md` — implements liveness + conflict-source capture +
  open-question→BLOCKER (intent-tier classes 1–3).
- `skills/architect/SKILL.md` — implements format + response-DTO contracts
  (architecture-tier classes 4–5).
- `hooks/inject-standards.sh` — injects a summary of this standard into every
  subagent's onboarding context.
- `docs/adrs/F-2026-05-29-contract-completeness-001-adopt-established-vocabulary.md`
  — the DbC/CDC/SbE/29148 lineage decision.
- `docs/adrs/F-2026-05-29-contract-completeness-002-versioned-liveness-interface.md`
  — the versioned-liveness-block decision.
- `docs/adrs/F-2026-05-29-contract-completeness-003-warn-with-recorded-override.md`
  — the WARN+recorded-override enforcement decision.

**Origin:** covr.care `pbj` build retrospective
(`origin/feature/DEV-00000-PBJ-Kickoff-AI`); one feature → seven tags, ~45
correction turns; covr F006 surfaced 19 gaps despite the full `/spec`+`/architect`
pipeline. See project memory for the full failure-mode analysis.
