# F017 — `/journey` skill: SME-led journey capture for MVP discovery

**Status:** spec (review before /build)
**Author role:** Engineer (Jason / HCE)
**Date:** 2026-05-13
**Source:** Venlink harness-feedback 2026-05-13 (Julie/legal/contract-execution interview)

## Problem

A 6-month-old codebase, 12+ shipped features, 4000+ tests, full domain model
coverage, a confident SME — and the team felt "talking past each other" on
MVP scope. Cause: every PRD is **capability-shape** ("the platform can do
X"). None are **journey-shape** ("Julie clicks Y, sees Z, signs a contract").

The intersection of capabilities is unconstrained — adding capabilities is
additive without converging. The intersection of journeys IS the MVP — every
journey names a small set of features that must work together for a real
customer to experience value. Without journey artifacts, a PRD pile cannot
self-organize toward an MVP; it accumulates capability surface area while
shipping nothing a single user can complete end-to-end.

The Julie interview surfaced this in one sitting: a captured journey
("Julie's contract-execution journey") immediately exposed three platform-
category gaps (template management, document automation, e-sign) that no
PRD had described. The SME knew the journey because she lived it. No PRD
captured it because PRDs are written in capability-shape by engineers.

## Solution

Ship `/journey` — a new skill, sibling to `/spec`, paired with `/spec`
through a `journey_refs:` field. Three pillars:

### 1. Low-ceremony entry (SME-friendly)

`/journey` accepts a one-liner OR freeform text dump as the seed:

```
/journey
/journey "Julie executes a contract"
/journey --from-text path/to/sme-notes.md     # paste a Slack thread / interview transcript
/journey --from-voice                         # placeholder for future voicemode integration
```

The first prompt is **plain English**, not engineering jargon:

```
Tell me about this journey. Who does this work, and what are they trying
to get done? Don't worry about format — talk like you're describing it
to a colleague.
```

The skill accepts any answer the SME gives — narrative paragraphs, bullet
points, a Slack-conversation-style dump. The Socratic loop refines from
there.

### 2. Socratic refinement (journey-shape, not capability-shape)

Six prompts, asked **one at a time** via Pattern B (the visual marker, same
as `/spec`). Each prompt is plain-English and journey-shape:

```
1. Who is doing this work? Name, role, what they care about.
2. What kicks this off? An email? A scheduled event? A customer call?
3. Walk me through what they do. Step by step. Click, type, decide.
4. When does it work well? What does "done" feel like to them?
5. When does it go wrong? Where do they get stuck or frustrated?
6. What tools and systems do they touch along the way?
```

Plus one optional emotion-arc question for SMEs who want to capture the
human dimension:

```
7. (Optional) How do they feel at each step? Confident? Anxious? Confused?
```

These are journey-shape questions. They cannot be answered by listing
capabilities. The SME's lived experience IS the answer.

### 3. Templated output to `docs/mvp/journeys/J-NNN-<slug>.md`

The skill writes the refined journey to a stable per-engagement directory.
Journey IDs (`J-NNN`) are allocated by a new `scripts/journey_id.py`
mirroring `scripts/feature_id.py`'s POSIX-atomic pattern.

Output template (frontmatter + body):

```markdown
---
journey_id: J-007
title: Julie executes a contract
actor: Julie Reyes
actor_role: Legal counsel, contracting team
trigger: Sales rep emails: "We need a contract drafted for Acme Corp"
outcome: Counter-signed contract stored in CRM with executed PDF attached
status: draft | refined | locked
captured_at: 2026-05-13T14:00:00Z
captured_by: Engineer (J. Vertrees) + SME (Julie R.)
sources: [voice, slack-thread, paste]
---

# J-007 — Julie executes a contract

## Actor
Julie Reyes, legal counsel on the contracting team. Her job is contract
execution — receiving sales requests, drafting agreements from templates,
negotiating terms, and recording executed contracts.

## Trigger
A sales rep sends an email with deal details and asks for a contract draft.
Usually 1-5 per day, varying complexity.

## Outcome
A counter-signed PDF stored in the CRM, linked to the opportunity, with the
key terms (price, term length, parties) extracted into structured fields.

## Steps
1. Sales rep email lands in Julie's inbox.
2. Julie opens the deal in Salesforce, reviews terms.
3. Julie picks a contract template from `legal/templates/`.
4. Julie fills variables (party names, dollar amount, term, jurisdiction).
5. Julie sends to sales for redline.
6. Sales emails customer; customer redlines.
7. Julie reconciles redlines, sends final.
8. Customer e-signs (DocuSign).
9. Julie counter-signs.
10. Julie uploads executed PDF to Salesforce, populates structured fields.

## Failure modes
- Wrong template picked → contract has wrong terms → discovered after signature.
- Variables filled inconsistently → audit issues.
- DocuSign envelope expires before customer signs → re-send hassle.
- Counter-signature missed → "executed" never reached.
- Salesforce fields not populated → reporting wrong, renewals missed.

## Tools / Systems touched
Salesforce (lead/opportunity/account), Microsoft Word (template editing),
DocuSign (e-sign), email (Outlook), shared drive (template library).

## Emotional journey
- Steps 1-3: confident, routine.
- Steps 4-5: focused (variable-fill is detail-heavy; mistakes are costly).
- Steps 6-7: anxious if redlines are aggressive.
- Steps 8-9: relief (signature secured).
- Step 10: tedious (manual Salesforce data entry; "I did this work twice").

## Open questions
- Are template variables versioned? What happens to in-flight contracts when
  templates change?
- Who owns the redline workflow if Julie is OOO?
- How are escalations to senior counsel triggered?
```

Status field tracks progression: `draft` → `refined` (after Socratic loop)
→ `locked` (operator declares the journey stable; subsequent edits create a
new version).

## Two feature categories: customer-facing vs infrastructure

Not every feature serves a customer journey. A library upgrade, a CI
tooling improvement, a harness-internal refactor — these don't trace to
"Julie clicks a contract". The harness MUST first-class both categories:

### Customer-facing features

Trace to one or more captured journeys. Journey-refs MANDATORY. The
release tag won't ship until journey lineage is documented.

Examples: contract execution (J-007), expense submission (J-012), customer
onboarding (J-019).

### Infrastructure features

Internal to the platform. Don't trace to a customer's lived experience.
Journey-refs INTENTIONALLY ABSENT, marked by `infrastructure_only: true`
in state.yaml. The /build journey-gate explicitly passes when this
sentinel is set.

Examples: F010 stacked-PRs, F015 spec→ADR coupling, F016 cross-feature
collision detection — every feature shipped to etc itself this session
is infrastructure. A library upgrade (Python 3.12 → 3.13) is
infrastructure. CI tooling is infrastructure.

**Both categories are first-class.** The harness doesn't punish
infrastructure work for not having a journey — it just asks you to
declare which category you're in. Forcing operators to choose
infrastructure-only vs customer-facing IS the discipline; it forces
the question "is anyone actually going to use this?"

## Integration with `/spec`

`/spec` Phase 1 grows one new question at the end of the existing six
(after the author-role question):

```
Which captured journey(s) does this feature serve? Choose one:
  • Enter J-NNN IDs (comma-separated, e.g. "J-007, J-012")
  • Type 'new' to capture a journey via /journey first
  • Type 'infrastructure' to mark this as platform/tooling work with
    no user-journey trace (library upgrade, harness internals, CI, etc.)
```

Three resolutions write distinct shapes to `state.yaml.spec_phase`:

- **List of J-NNN IDs**: validated against `docs/mvp/journeys/`. Writes
  `journey_refs: [J-007, J-012]`. Unknown IDs → Pattern B re-ask with
  the list of known IDs.
- **`new`**: `/spec` dispatches `/journey` via the Skill tool, captures
  the journey, then resumes /spec with the new J-NNN in journey_refs.
- **`infrastructure`**: writes `infrastructure_only: true` + leaves
  `journey_refs` absent. /build's Step 7.4 gate honors this sentinel.
  The Pattern B prompt asks for a one-line **reason** ("library upgrade",
  "CI pipeline", "harness internals") which is recorded as
  `infrastructure_reason: "<text>"` and surfaces in verification.md +
  release-notes.md. Forces the operator to articulate WHY this work
  doesn't have a customer trace.

## Integration with `/build`

`/build` Step 7 gains a new sub-check (Step 7.4, between verification.md
write and the F015 spec→ADR coupling gate):

- Read `state.yaml.spec_phase.journey_refs`.
- If empty AND `infrastructure_only: true` → pass.
- If empty AND no sentinel → exit 2 with message:

  ```
  JOURNEY LINEAGE MISSING

  This feature has no captured user journey. Every shipped feature must
  trace to a customer's lived experience OR be explicitly marked as
  infrastructure-only.

  Resolution:
    A) Run /journey to capture the journey this feature serves, then
       update state.yaml.spec_phase.journey_refs.
    B) If this is infrastructure work (build tooling, dependencies,
       hooks), update spec.md to declare infrastructure_only: true
       in the spec preamble; /spec --refine will write the sentinel.

  Override (logged to verification.md + release-notes.md):
    /build --skip-journey-check="<reason>"
  ```

- If `journey_refs` non-empty: verify each referenced journey exists at
  `docs/mvp/journeys/J-<NNN>-*.md`. Missing journey → exit 2 with the
  list of missing IDs.

Like F015's spec→ADR coupling, the override flag requires a non-empty
inline reason, logged to `verification.md` and `release-notes.md` for
audit-trail.

## MVP discovery (deferred to v2)

Once enough journeys are captured, a future companion skill `/mvp` (or
`/journey --intersect`) computes the **intersection of journeys** — the
minimum set of features that must all work for any one journey to
complete. That's the MVP. F017 ships the capture machinery; MVP
intersection analysis is its own feature.

## Acceptance Criteria

- **AC-01:** New skill at `skills/journey/SKILL.md` documents the 6+1
  Socratic prompts, the output template, the J-NNN allocator, and the
  refinement loop (draft → refined → locked).
- **AC-02:** `scripts/journey_id.py allocate-next docs/mvp/journeys "<slug>"`
  POSIX-atomically allocates the next J-NNN and creates the directory
  entry, mirroring `feature_id.py`'s contract. Exit codes 0/1/2 match.
- **AC-03:** `/journey` accepts a one-liner argument (`/journey "Julie executes
  a contract"`), no-arg form (interactive opener), `--from-text <path>`
  for paste-style input, and `--from-voice` (which today emits a stub
  message: "Voice capture deferred to F-TBD; please paste text or run
  /journey with no args").
- **AC-04:** Six Socratic prompts are asked **one at a time** via Pattern B
  (visual marker). The wording is **plain English, not engineering jargon**
  — verified by SKILL.md content tests grep'ing for "click", "type",
  "decide", "feel", and confirming NO occurrence of "acceptance criteria",
  "BR-", "stakeholder", "use case".
- **AC-05:** After the Socratic loop, the skill writes
  `docs/mvp/journeys/J-<NNN>-<slug>.md` with the frontmatter + body
  template documented above. `status` starts at `draft`.
- **AC-06:** A second pass through the skill (`/journey --refine J-NNN`) can
  load an existing journey, present the body to the SME for review, accept
  per-section edits via Pattern B, and bump `status: refined`.
- **AC-07:** `/spec` Phase 1 includes a new (seventh) journey-refs question
  after the author-role question. Answer accepts: a comma-separated list of
  J-NNN IDs, the literal `new` (which dispatches /journey via Skill tool),
  or the literal `none` (which writes `infrastructure_only: true` to
  state.yaml).
- **AC-08:** `state.yaml.spec_phase` gains an optional `journey_refs: [J-NNN, ...]`
  field and an optional `infrastructure_only: true` sentinel. Both are
  documented in `skills/spec/SKILL.md`. Legacy state.yaml files without
  these fields are tolerated (backward compatible).
- **AC-09:** `/build` Step 7 (new sub-step 7.4) reads `journey_refs` +
  `infrastructure_only` from state.yaml. Empty journey_refs without the
  sentinel → exit 2 with the JOURNEY LINEAGE MISSING message + remediation
  hints. Sentinel set → pass. journey_refs non-empty AND every referenced
  file exists → pass.
- **AC-10:** `--skip-journey-check="<reason>"` operator override with
  mandatory non-empty reason. Reason logged to verification.md +
  release-notes.md under a "Journey Lineage Gate" subsection.
- **AC-11:** `tests/test_journey_skill.py` covers AC-01 through AC-06
  (skill-text content + Pattern B usage + allocator behavior + output
  template shape). `tests/test_journey_id.py` covers AC-02 (allocator
  CLI). `tests/test_build_journey_gate.py` covers AC-09 + AC-10.
- **AC-12:** README "Skills" section adds a `/journey` entry with plain-
  English description aimed at SMEs ("If you're a domain expert
  describing how your work actually happens"). F017 row added to shipping
  table. `docs/mvp/` and `docs/mvp/journeys/` directories committed (with
  README.md placeholders explaining the layout) so customers see the
  intended location.
- **AC-13:** `spec/etc_sdlc.yaml` registers the new skill (`source:
  skills/journey/SKILL.md`) so it survives the compile→install pipeline.

## Out of Scope (deferred to follow-up features)

- **Voice capture** via Claude Code's voicemode MCP. AC-03 ships the
  `--from-voice` flag as a stub that emits a defer message. Real voice
  capture is its own feature (needs MCP integration, transcript handling,
  speaker-attribution).
- **MVP intersection analysis.** F017 captures journeys; `/mvp` (or
  `/journey --intersect`) computes the minimum-feature-set is a separate
  ship.
- **Journey graph queries** ("show me every journey that touches
  Salesforce"). Deferred.
- **Multi-actor journeys** (handoff between actors mid-journey). v1
  assumes a single actor per journey; multi-actor is a v2 concern with
  its own template extension.
- **Backporting `journey_refs` to F001-F016 shipped features.** Existing
  features stay as-is. The gate only fires for features filed AFTER F017
  ships (detected via whether the spec.md was created before or after
  the F017 release tag).
- **Journey versioning.** v1 tracks `status: draft/refined/locked`. v2
  may introduce journey-version semantics (J-007.v2 supersedes J-007.v1).
- **PII handling in journey content.** SMEs naturally include real actor
  names and customer details. F017 captures whatever the SME says.
  Production deployments needing PII redaction handle it via a separate
  process (out of scope here).

## Technical Notes

- **Allocator contract:** `scripts/journey_id.py allocate-next <root> <slug>`
  reads existing `J-\d+` directories under `<root>`, finds max, allocates
  max+1, prints `J<NNN> <full_path>` to stdout. POSIX-atomic via `mkdir`
  (same primitive feature_id.py uses).
- **SME-facing vs engineer-facing language:** SKILL.md MUST avoid the
  vocabulary that confuses non-technical operators. Forbidden phrases
  (validated by AC-04 tests): "acceptance criteria", "BR-", "stakeholder",
  "use case", "user story", "Definition of Ready". Encouraged phrases:
  "what they click", "what they type", "what frustrates them", "how they
  feel".
- **Refinement loop:** the `--refine` path reads the existing journey,
  presents each section, and asks "Anything to add or correct?" Pattern B,
  one section at a time. Operator can answer "skip" to leave a section
  unchanged.
- **Storage layout:** `docs/mvp/journeys/J-NNN-<slug>.md`. The `docs/mvp/`
  parent leaves room for adjacent artifacts (intersection analysis,
  graph, persona files) without committing to their format now.
- **Backward compatibility:** legacy state.yaml files (without
  `journey_refs`) are tolerated. The /build journey-gate only fires when
  the spec.md was filed after the F017 release tag — detected by reading
  state.yaml.spec_phase.completed_at and comparing to the F017 release
  tag's commit date. Legacy features always pass.
- **Customer-facing surface:** etc ships to HCE customers as a private
  commercial product. The `/journey` skill is **THE differentiator** for
  non-technical-SME teams — most AI dev tools assume the user is an
  engineer; etc's /journey is built FOR the SME. Worth marketing-side
  attention when this ships.

## Dependencies

- Python 3.11+ (already required).
- PyYAML (already required).
- No new third-party deps.

## Risks

1. **SMEs may resist structured capture.** The "low ceremony" entry path
   (paste text dump, narrate freeform) mitigates this. The Socratic loop
   refines AFTER the SME has felt heard.
2. **Journey artifacts proliferate without governance.** The lock state
   (refined → locked) and the `/mvp` intersection (deferred to v2) are
   the governance mechanisms. v1 ships capture; v2 ships analysis.
3. **/build journey-gate blocks legacy features on resume.** Mitigated by
   the backward-compat date check — only features filed after F017 ships
   are gated.
4. **`--skip-journey-check` becomes the new normal.** Trust-chain lesson
   from F007+F008+F015: bypasses get used until the gate is decorative.
   Mandatory inline reason + audit-trail logging is the disincentive.

## Resolved Design Decisions (2026-05-13 operator review)

These were Open Questions during draft; the operator resolved them
before /build:

1. **Voice capture in v1?** → **NO (defer to v2).** v1 ships
   `--from-voice` as a stub message ("Voice capture deferred to F-TBD;
   please paste text or run /journey with no args"). Real voicemode
   MCP integration is its own feature when that surface is more mature.

2. **Journey gate on legacy F001-F016?** → **NO (date-check).** The
   /build Step 7.4 gate reads state.yaml.spec_phase.completed_at and
   compares to the F017 release tag's commit date. Features filed
   BEFORE F017 ships pass automatically. Features filed AFTER must
   either have journey_refs or infrastructure_only: true. No
   retroactive backfill of legacy features.

3. **Canonical example journey shipped with the skill?** → **YES,
   anonymized.** Ship `docs/mvp/journeys/J-001-contract-execution.md`
   based on the Julie example from the feedback memo, with actor name
   abstracted to "Counsel" and no real customer names. The example IS
   the SME-onboarding accelerator — they see what "good" looks like
   before authoring their own.

4. **Position in the SDLC pipeline?** → **/spec is the entry point for
   ALL features; /journey is dispatched on-demand from /spec.** The
   pipeline diagram stays: `strategy → research → (design | strategy)
   → spec → architect → build → release`. The /spec Phase 1 journey-
   refs question dispatches /journey when the operator answers `new`.
   Infrastructure features (library upgrades, CI tooling, harness
   internals) answer `infrastructure` and skip /journey entirely.
   Customer-facing features trace to one or more journeys.

5. **Mandatory vs optional journey-refs question?** → **MANDATORY**
   (one of `<list>`, `new`, `infrastructure`). Forcing the operator to
   choose between "customer-facing" and "infrastructure" IS the
   discipline. The infrastructure path is fully supported but requires
   declaring it explicitly + giving a one-line reason.

6. **Personas as first-class artifacts?** → **NO in v1 (inline).** Each
   journey embeds actor details inline. If personas start getting
   reused across journeys, v2 extracts them to
   `docs/mvp/personas/P-NNN-*.md`. v1 stays simple.

7. **Multi-engagement namespacing?** → **NO in v1 (flat).** Etc is
   currently single-engagement per repo; journeys live at
   `docs/mvp/journeys/` flat. Multi-engagement deployments (consultants
   running multiple clients in one repo) are a v2 concern that may
   introduce `docs/mvp/<engagement>/journeys/` namespacing.

## Sequencing

- **F017 (this PRD): /journey capture + /spec integration + /build gate.**
  Single-actor, single-journey-per-feature, no voice, no MVP analysis.
- **F-TBD (deferred): voice capture via voicemode MCP.**
- **F-TBD (deferred): /mvp intersection analysis (the load-bearing
  reason this whole thing exists).**
- **F-TBD (deferred): personas + multi-actor journeys + journey
  versioning.**

## Source

- Venlink-platform harness-feedback 2026-05-13. Julie/legal/contract-
  execution interview. Three platform-category gaps surfaced from one
  journey capture that no prior PRD addressed.
- Operator direction 2026-05-13: SME-friendly Socratic loop, voice OR
  freeform text entry, templated output. "Super excited."
- This spec consolidates the feedback memo intent into a buildable PRD
  with explicit ACs, /spec + /build integration points, and out-of-scope
  deferrals.
