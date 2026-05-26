# PRD: F-2026-05-26 — Layered Architecture Review

## Summary

A real production bug shipped unindexed queries because nothing in the architect step forced the thought: "we're adding SQL → that's the data-access layer → doing a good job there means considering indexes, query plans, N+1, pagination, and migration safety." This is one symptom of a deeper gap — `/architect` does not systematically reason about **which architectural layers a change touches** or **what doing a good job at each layer requires**. Quality attributes stay implicit, so they get skipped under time pressure.

This feature adds a **Layer Impact Analysis** phase to `/architect`, built on a declarative **rubric registry**. The registry defines the system's architectural layers and, for each, a **rubric** — a structured set of quality criteria (with quality-attribute names drawn from ISO/IEC 25010). `/architect` detects which layers the incoming change touches and **walks the matrix cell by cell**, forcing an explicit answer or a reasoned N/A for each rubric item of each touched layer. The output is a structured Layer Impact Analysis table written into `design.md`, plus ATAM-style risks / sensitivity points / tradeoffs. `/build` enforces completeness via a design.md gate (advisory by default; per-feature `layer_review_mandatory` escalation hardens it to a block).

The design synthesizes established practice: arc42's layer × crosscutting-concept structure, ATAM's scenario-to-risk analysis, AWS Well-Architected's per-pillar question discipline, STRIDE-per-element's per-cell forcing function, ISO 25010's quality taxonomy, and the fitness-function graduation path from Building Evolutionary Architectures (each rubric item carries a `mechanizable` flag for future automation — no fitness function is built in this feature). The data-access rubric ships as the flagship (the proven gap); all core layers ship with real criteria.

Forward-only: applies to designs authored from the F-2026-05-26 release tag onward.

## Scope

### In Scope

- **Rubric registry** — `standards/architecture/layer-rubrics.yaml`: a declarative file defining each architectural layer and its rubric items. Each rubric item carries: `id`, `layer`, `criterion` (the question the architect must answer), `quality_attribute` (an ISO 25010 characteristic), `severity_if_missed` (CRITICAL/HIGH/MEDIUM/LOW), `mechanizable` (bool — can this become an automated /build check later), and `detection_signals` are defined per-layer (not per-item).
- **Core layers (rows)** — data-access, domain/service, API-contract, presentation/frontend, infra-ops — plus a **cross-cutting concerns** section (authn/authz, caching, observability/logging, i18n, secrets/security) walked separately from the layers.
- **Flagship data-access rubric** — the deepest rubric, covering: index coverage for new query-filter/join columns, estimated vs actual row counts, full-table-scan avoidance, N+1 query patterns, pagination / bounded result sets, migration safety (online/concurrent index builds, lock avoidance on large tables), and transaction boundaries (no external calls inside a transaction).
- **Real rubrics for the other core layers** — not stubs. Domain/service (idempotency, error/retry, service boundaries, side-effect isolation); API-contract (versioning, backward compatibility, request/response validation, pagination contracts, rate limits); presentation/frontend (loading/error/empty states, accessibility, perf budget, responsive behavior, state ownership); infra-ops (deployment/rollback, config/secrets handling, observability/metrics/logging, scaling/resource limits).
- **`standards/architecture/layered-architecture-review.md`** — the standards doc: how the phase works, the layer + quality-attribute model, the rubric-authoring guide, the per-cell forcing rule, and the rationale citing the prior art (arc42, ATAM, Well-Architected, STRIDE, ISO 25010, fitness functions). The registry is the data; this doc is the prose anchor.
- **`scripts/layer_review.py`** — stdlib + PyYAML CLI with two subcommands: `detect --design <path>` (parse the registry, scan design.md/spec.md for per-layer detection signals, emit the touched layers as JSON) and `check --design <path>` (verify the design's Layer Impact Analysis section has an explicit answer or reasoned N/A for every rubric item of every touched layer; emit unfilled cells + exit non-zero on incompleteness). Both /architect and /build call this — single source of truth for detection + completeness.
- **`/architect` Layer Impact Analysis phase** — a new phase (after Phase 2 research, before/within design-writing): invoke `layer_review.py detect`, then for each touched layer walk its rubric, forcing an explicit answer or reasoned N/A per item, and emit a structured Layer Impact Analysis table into design.md plus a Risks/Tradeoffs subsection. /architect remains interactive and does NOT Agent-dispatch (respects SKILL.md:45-52).
- **`/build` Step 1c completeness gate** — extend the existing design-coupling check: run `layer_review.py check`; if a touched layer has an unfilled rubric item, WARN (advisory) and record it in verification.md; hard-block only when `architect_phase.layer_review_mandatory` is true.
- **`mechanizable` graduation roadmap** — each rubric item is authored with a `mechanizable` flag so a follow-up feature can graduate flagged items to automated /build fitness functions. No fitness function is built in this feature.
- **Tests** — registry-schema contract tests; `layer_review.py` unit tests (detection per layer, completeness check, reasoned-N/A acceptance, registry-absent error); /architect phase-prose contract tests; /build gate-prose contract tests. Coverage of `scripts/layer_review.py` ≥95%.

### Out of Scope

- **Building any fitness function / automated /build check.** The `mechanizable` flag sets the roadmap; mechanization is a deferred follow-up feature.
- **Runtime profiling / EXPLAIN-plan execution / live DB connection.** The phase reasons over the design + spec text, not a running system.
- **Auto-filling the rubric answers.** /architect prompts the architect (interactively) to answer; it does not fabricate answers. (The matrix forces the answer to be made, not invented.)
- **Per-project custom layer taxonomies.** v1 ships one registry of core layers. Per-project override of the registry is a deferred follow-up.
- **NoSQL / non-RDBMS data tiers in the data-access rubric.** The flagship rubric is RDBMS-focused for v1; other storage tiers are follow-up rubric entries.
- **Replacing /architect's existing Socratic questions.** The phase is additive; the existing 6 intent-capture questions remain.
- **A standalone reviewer agent.** Superseded — the rubric registry + matrix-walk replaces the "data-reviewer agent" framing (the original task #33 shape).

## Requirements

### BR-001: Rubric registry file + schema
`standards/architecture/layer-rubrics.yaml` exists. Top-level keys: `layers` (list) and `cross_cutting_concerns` (list). Each layer has: `id`, `name`, `detection_signals` (list of substring/regex tokens), and `rubric` (list of rubric items). Each rubric item has: `id`, `criterion`, `quality_attribute` (an ISO 25010 characteristic), `severity_if_missed` (CRITICAL|HIGH|MEDIUM|LOW), `mechanizable` (bool).

### BR-002: Core layers enumerated
The registry defines at least these five layers: `data-access`, `domain-service`, `api-contract`, `presentation-frontend`, `infra-ops`, plus a `cross_cutting_concerns` section with at least: authn/authz, caching, observability, i18n, secrets.

### BR-003: Flagship data-access rubric
The `data-access` layer rubric contains criteria covering, at minimum: index coverage for new query-filter/join columns; estimated vs actual row counts; full-table-scan avoidance; N+1 detection; pagination / bounded result sets; migration safety (online/concurrent build, large-table lock avoidance); transaction boundaries. Each maps to an ISO 25010 attribute (mostly `performance_efficiency` and `reliability`).

### BR-004: Real rubrics for all other core layers
Each non-flagship core layer has at least three real rubric items (not placeholders), each with a `criterion`, a `quality_attribute`, a `severity_if_missed`, and a `mechanizable` flag.

### BR-005: ISO 25010 quality-attribute vocabulary
Every rubric item's `quality_attribute` is one of the ISO/IEC 25010 product-quality characteristics (functional_suitability, performance_efficiency, compatibility, usability, reliability, security, maintainability, portability). The standards doc lists the allowed values.

### BR-006: /architect layer detection
`/architect` invokes `python3 ~/.claude/scripts/layer_review.py detect --design <path>` to determine which layers the change touches, using the registry's per-layer `detection_signals` scanned against the spec/design text. Detection excludes fenced code blocks and explicit "Out of Scope"/"Future" sections (F015-style exclusion).

### BR-007: Matrix-walk forcing function
For each touched layer, `/architect` walks that layer's rubric and produces, for each rubric item, EITHER an explicit answer OR a reasoned N/A (a non-empty justification). An unanswered rubric item is not permitted — the walk is the forcing function. The walk is interactive (Pattern A/B), never Agent-dispatched.

### BR-008: Layer Impact Analysis output in design.md
`/architect` writes a `## Layer Impact Analysis` section into design.md containing, per touched layer, a table of (rubric item id, criterion, answer-or-N/A, severity), plus a `### Risks / Sensitivity / Tradeoffs` subsection (ATAM-style) capturing any risks the walk surfaced.

### BR-009: Shared detection + completeness via layer_review.py
`scripts/layer_review.py` is the single source of truth for both layer detection (`detect`) and Layer Impact Analysis completeness checking (`check`). Both /architect and /build invoke the CLI; neither reimplements detection or checking inline.

### BR-010: /build Step 1c completeness gate
`/build` Step 1c is extended: when design.md is present, run `layer_review.py check --design <design path>`. If a touched layer has an unfilled rubric item, emit a WARNING to stderr and record it in verification.md under a "Layer Impact Analysis" subsection, then PROCEED (advisory default). When `architect_phase.layer_review_mandatory` is true, an unfilled rubric item with `severity_if_missed: CRITICAL` HARD-fails the build until filled or explicitly overridden.

### BR-011: layer_review_mandatory escalation
`/architect` records `architect_phase.layer_review_mandatory: <bool>` in state.yaml. Default false (advisory). The operator opts into the hard gate per feature, mirroring F006's `design_mandatory`.

### BR-012: mechanizable flag
Every rubric item carries a `mechanizable: true|false` flag indicating whether the criterion can graduate to an automated /build fitness-function check in a follow-up feature. No fitness function is built in this feature; the flag is roadmap metadata.

### BR-013: Forward-only
The Layer Impact Analysis phase and the /build gate fire for designs authored from the F-2026-05-26 release tag onward. Legacy designs (pre-release) are not retroactively analyzed; the gate is cosmetic on legacy designs that get rebuilt.

### BR-014: Read-and-reason, not auto-answer
`layer_review.py` and the /architect phase never fabricate rubric answers. The phase forces the architect to MAKE each decision (or justify N/A); it does not invent answers on the architect's behalf.

## Acceptance Criteria

1. **AC-001**: `standards/architecture/layer-rubrics.yaml` exists and parses as YAML with top-level `layers` and `cross_cutting_concerns` keys; each layer has `id`, `name`, `detection_signals`, `rubric`; each rubric item has `id`, `criterion`, `quality_attribute`, `severity_if_missed`, `mechanizable`. A schema test asserts every field is present on every item.

2. **AC-002**: The registry defines the five core layers (`data-access`, `domain-service`, `api-contract`, `presentation-frontend`, `infra-ops`) and a `cross_cutting_concerns` section with ≥5 entries.

3. **AC-003**: The `data-access` rubric contains items covering index coverage, row-count estimation, full-table-scan avoidance, N+1, pagination, migration safety, and transaction boundaries (≥7 items). A test asserts each topic is present by criterion-text match.

4. **AC-004**: Each non-flagship core layer has ≥3 rubric items with all required fields populated (no empty `criterion`).

5. **AC-005**: Every rubric item's `quality_attribute` is one of the 8 ISO 25010 characteristics. A test asserts the closed vocabulary.

6. **AC-006**: `scripts/layer_review.py detect --design <path>` parses the registry, scans the design text against per-layer `detection_signals` (excluding fenced code blocks + Out-of-Scope/Future sections), and emits the touched layers as JSON. A test with a fixture design touching only data-access returns exactly `["data-access"]`.

7. **AC-007**: `scripts/layer_review.py check --design <path>` exits 0 when every touched layer's rubric items each have an answer or reasoned N/A in the design's Layer Impact Analysis table, and exits non-zero (listing the unfilled cells) when any are missing. Tests cover both the complete and incomplete fixtures.

8. **AC-008**: A reasoned N/A (non-empty justification) satisfies the completeness check; an empty or whitespace-only answer does not. A test asserts both.

9. **AC-009**: `skills/architect/SKILL.md` contains a Layer Impact Analysis phase that (a) invokes `layer_review.py detect`, (b) walks each touched layer's rubric forcing an answer-or-reasoned-N/A per item, (c) writes a `## Layer Impact Analysis` table + Risks/Tradeoffs subsection into design.md, and (d) records `architect_phase.layer_review_mandatory` in state.yaml. The phase prose explicitly does NOT Agent-dispatch.

10. **AC-010**: `skills/build/SKILL.md` Step 1c invokes `layer_review.py check`; on an unfilled rubric item it WARNS + records to verification.md and proceeds (advisory), UNLESS `layer_review_mandatory` is true and the unfilled item is `severity_if_missed: CRITICAL`, in which case it hard-blocks.

11. **AC-011**: `standards/architecture/layered-architecture-review.md` exists, documents the layer + ISO-25010 model, the per-cell forcing rule, the rubric-authoring guide, and cites the prior art (arc42, ATAM, Well-Architected, STRIDE, ISO 25010, fitness functions). It names `standards/architecture/layer-rubrics.yaml` as the registry.

12. **AC-012**: `tests/test_layer_review.py` exists covering AC-001..AC-008 (registry schema, detection, completeness, reasoned-N/A) plus EC fixtures; coverage of `scripts/layer_review.py` ≥95%.

13. **AC-013**: Every rubric item carries a boolean `mechanizable` flag; a test asserts the flag is present and boolean on every item.

## Edge Cases

1. **EC-001**: A design touching no recognized layer (e.g., a pure docs/standards feature) — `detect` returns `[]`; /architect writes a Layer Impact Analysis section stating "no architectural layers touched"; /build's gate finds nothing to check and proceeds with no warning.

2. **EC-002**: A rubric item is legitimately not applicable (e.g., a read-only feature has no migration) — a reasoned N/A ("read-only; no schema change") satisfies the completeness check. Empty N/A does not.

3. **EC-003**: `standards/architecture/layer-rubrics.yaml` is absent or malformed — `layer_review.py` exits non-zero with a clear error (`registry not found` / `registry parse error: <detail>`); /architect surfaces it via Pattern B and stops the phase rather than reasoning against a missing registry.

4. **EC-004**: A legacy design (pre-F-2026-05-26) is rebuilt — detection may fire cosmetically but the gate is forward-only; legacy designs are not retroactively blocked unless the operator opts into mandatory mode.

5. **EC-005**: A cross-cutting concern is touched (e.g., the change adds caching) — it is walked from the `cross_cutting_concerns` section separately from the layer rows; its rubric items appear in their own subsection of the Layer Impact Analysis table.

6. **EC-006**: Layer-detection signals appear only inside a fenced code block or an explicit "Out of Scope"/"Future" section of the design — detection excludes those regions (F015-style), avoiding false-positive layer detection.

7. **EC-007**: `layer_review_mandatory` is true but every touched layer's rubric is complete — the build proceeds (mandatory mode blocks only on unfilled CRITICAL items).

8. **EC-008**: A touched layer has only non-CRITICAL unfilled items under mandatory mode — the build WARNS (records them) but does not hard-block; mandatory mode's hard block is reserved for CRITICAL-severity unfilled items to avoid friction on hygiene-level criteria.
