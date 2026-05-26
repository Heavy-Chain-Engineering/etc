# Layered Architecture Review

## Status: MANDATORY
## Applies to: Architect, Backend Developer, Code Reviewer

## What This Is

The **Layer Impact Analysis** phase of `/architect`. It detects which architectural
layers a change touches and walks a per-layer quality rubric, forcing an explicit
answer — or a reasoned N/A — for every rubric item of every touched layer.

The registry is the data: [`layer-rubrics.yaml`](layer-rubrics.yaml) defines the
layers, their detection signals, and their rubric items. **This document is the
prose rationale.** When the two disagree, the registry is the source of truth for
the layer/rubric data; this doc explains why the mechanism is shaped the way it is.

## Why It Exists

A real production bug shipped **unindexed queries** because nothing in the architect
step forced the thought: *"we're adding SQL → that's the data-access layer → doing a
good job there means considering indexes, query plans, N+1, pagination, and migration
safety."* The quality attribute (performance) stayed implicit, so it was skipped under
time pressure.

The fix is not "remember to think about indexes." Memory and diligence do not scale and
do not survive deadline pressure. The fix is **structural completeness**: a matrix where
every applicable cell *must* be answered. You cannot forget the data-layer performance
question when the table has a cell for it and an empty cell fails the gate.

> **Thesis: completeness is structural, not a matter of diligence.** The same insight
> that makes STRIDE-per-element and AWS Well-Architected work — walk every cell, answer
> every applicable question — applied to architectural layers.

## The Layer Model

A change is decomposed into the layers it touches. Each layer is a *row*; the architect
walks that row's rubric only if the change touches it. The registry enumerates five core
layers plus a cross-cutting-concerns section.

| Layer | id | Scope (one line) |
|---|---|---|
| Data Access | `data-access` | Schema, queries, indexes, migrations, transactions — everything touching the store. |
| Domain / Service | `domain-service` | Business logic, orchestration, idempotency, side-effect isolation, service boundaries. |
| API Contract | `api-contract` | The wire contract: versioning, backward compatibility, request/response validation, pagination, rate limits. |
| Presentation / Frontend | `presentation-frontend` | UI surface: loading/error/empty states, accessibility, perf budget, responsive behavior, state ownership. |
| Infra / Ops | `infra-ops` | Deployment, rollback, config/secrets handling, observability, scaling and resource limits. |

**Cross-cutting concerns** span layers and are walked separately, in their own section:
authn/authz, caching, observability/logging, i18n, and secrets/security. They are not a
sixth layer — a single change can touch caching *and* the data-access layer — so they get
their own subsection in the Layer Impact Analysis output (EC-005).

This model is the **quality axis**. See the cross-reference to `layer-boundaries.md` below
for the orthogonal **structural axis**.

## The Quality-Attribute Vocabulary (ISO/IEC 25010)

Every rubric item names the quality attribute it protects, drawn from the eight
ISO/IEC 25010 product-quality characteristics. This is a **closed vocabulary** — a schema
test asserts every `quality_attribute` is one of these eight:

| `quality_attribute` | What it covers |
|---|---|
| `functional_suitability` | Does it do the right thing, completely and correctly? |
| `performance_efficiency` | Time behavior, resource use, capacity (the data-layer bug class). |
| `compatibility` | Co-existence and interoperability with other systems/versions. |
| `usability` | Learnability, operability, error protection, accessibility. |
| `reliability` | Maturity, availability, fault tolerance, recoverability. |
| `security` | Confidentiality, integrity, authenticity, accountability. |
| `maintainability` | Modularity, reusability, analyzability, modifiability, testability. |
| `portability` | Adaptability, installability, replaceability. |

ISO 25010 is the column vocabulary because it is canonical, vendor-neutral, and stable.
Rubric items are not free to invent quality words; they bind to this taxonomy so risks
can be aggregated and reasoned about consistently across layers.

## The Per-Cell Forcing Rule

This is the heart of the mechanism.

> **For every touched layer, every rubric item demands EITHER an explicit answer OR a
> reasoned N/A. An empty cell — or a whitespace-only / unjustified N/A — fails the
> `/build` completeness gate.**

This is the STRIDE-per-element discipline (ask all six threat questions of every DFD
element) and the AWS Well-Architected per-pillar discipline (answer every question in the
pillar's set), applied to architectural layers. The walk *is* the forcing function: you
cannot quietly skip "does this new query column have a backing index?" because the rubric
row exists and the gate counts unfilled rows.

A **reasoned N/A** is a first-class, valid answer. "Read-only feature; no schema change,
so migration safety is N/A" satisfies the cell. What does *not* satisfy it is silence —
an empty cell, or a bare "N/A" with no justification (EC-002). The rule forces the decision
to be *made and recorded*, not *invented*: `/architect` prompts the architect to answer
interactively and never fabricates answers on the architect's behalf (BR-014).

### The two-axis walk

```
                 quality attributes (ISO 25010) ─────────────►
                 perf   reliability   security   maintainability  …
  data-access     ●          ●           ○             ○
  domain-service  ○          ●           ○             ●
  api-contract    ○          ●           ○             ●
  …
  (● = a rubric cell that must be answered for a touched layer)
```

`/architect` writes the result as a `## Layer Impact Analysis` table in `design.md` —
one row per rubric item of each touched layer, carrying (item id, criterion,
answer-or-N/A, severity) — plus a `### Risks / Sensitivity / Tradeoffs` subsection in the
ATAM tradition (decision → quality-attribute scenario → risk). `/build` Step 1c re-reads
that table and gates on completeness.

## Rubric-Authoring Guide

The registry is `standards/architecture/layer-rubrics.yaml`. To **add a rubric item** to
an existing layer, or **add a layer**, edit that file. Every rubric item carries exactly
these five fields:

| Field | Type | Meaning |
|---|---|---|
| `id` | string | Stable, unique handle (e.g. `da-index-coverage`). Used in the design.md table and gate output. Never reuse or renumber. |
| `criterion` | string | The question the architect must answer. Phrase it as a question, concrete enough to answer at design time from spec/design text. |
| `quality_attribute` | enum | One of the eight ISO 25010 characteristics above. Closed vocabulary. |
| `severity_if_missed` | enum | `CRITICAL` \| `HIGH` \| `MEDIUM` \| `LOW`. See the scale below. |
| `mechanizable` | bool | Can this criterion graduate to an automated `/build` check later? See the graduation roadmap below. |

To **add a layer**, add an entry under `layers:` (or `cross_cutting_concerns:`) with
`id`, `name`, `detection_signals` (the substring/token list that marks the layer as
touched — detection is per *layer*, not per item), and a `rubric` list. Each non-flagship
core layer carries at least three real rubric items — no placeholders.

### Severity scale

Severity is data-tier-style: it describes the blast radius of *missing* the criterion,
and it determines whether mandatory mode hard-blocks the build.

| Severity | Definition |
|---|---|
| `CRITICAL` | Missing it ships a production-breaking defect: data loss, outage, security breach, or the unindexed-query class. Hard-blocks under mandatory mode. |
| `HIGH` | Significant degradation or a hard-to-reverse mistake: a contract break, a costly migration, a serious perf regression short of outage. |
| `MEDIUM` | Real quality cost that is recoverable: missing pagination contract, weak error handling, a maintainability smell. |
| `LOW` | Hygiene-level: a nicety whose absence is annoying but not damaging. |

Under the default advisory gate, severity only ranks the warnings. Under mandatory mode,
**only unfilled `CRITICAL` items hard-block** — non-critical unfilled items still merely
warn, so the hard gate never fires on hygiene-level friction (EC-008).

## Prior Art

The phase is a lightweight, agent-run synthesis of six established practices. Full
sourcing in the feature's `research/web.md`; the convergent pattern across all of them is
a **two-axis (element × concern) walk where every applicable cell demands an explicit
answer**.

- **arc42 §8, Crosscutting Concepts** — a dedicated section enumerating concerns that span
  building blocks (persistence, performance, security, logging). Source of the *layer ×
  concern* structure. (docs.arc42.org/section-8)
- **ATAM** (SEI/CMU) — scenario-based evaluation producing risks, sensitivity points, and
  tradeoffs from the chain *decision → quality-attribute scenario → risk*. Source of the
  `### Risks / Sensitivity / Tradeoffs` output; we run a lightweight version of its core
  loop, not the 3–4-day workshop. (sei.cmu.edu)
- **AWS Well-Architected** — a fixed question-set walked per pillar, with a tool that
  records every answer and emits a prioritized risk list. Source of the *per-cell question
  discipline*. (aws.amazon.com/architecture/well-architected)
- **STRIDE-per-element** (Microsoft/OWASP) — ask all six threat questions of every DFD
  element; the per-cell table *is* the forcing function. Source of the *per-cell forcing
  rule* applied to layers. (owasp.org Threat Modeling Process)
- **ISO/IEC 25010** — the eight-characteristic product-quality model. Source of the
  *quality-attribute column vocabulary*. (iso25000.com/.../iso-25010)
- **Building Evolutionary Architectures** (Ford, Parsons, Kua, Sadalage) — fitness
  functions automate governance: *"anything in an automated fitness function, you never
  have to review, because the build fails."* Source of the `mechanizable` flag and the
  graduation roadmap below. (thoughtworks.com / Building Evolutionary Architectures, ch. 4)

Two further influences inform the shape without being cited as forcing mechanisms:
Richards & Ford, *Fundamentals of Software Architecture* (derive the -ilities that matter
for *this* system), and Fowler, *PresentationDomainDataLayering* (layering's biggest
benefit is reducing the architect's scope of attention — reason about one layer at a time).

## The `mechanizable` Graduation Roadmap

Each rubric item carries a `mechanizable: true|false` flag. It is roadmap metadata: it
records whether the criterion *could* one day become an automated `/build` fitness function
(per *Building Evolutionary Architectures* — once a check fails the build, no human has to
review it). **No fitness function is built by this feature.** The flag forces an explicit
decision per criterion today and sets the trajectory for a follow-up feature to graduate
flagged items at zero current blast radius.

## Cross-Reference: This Doc Is Orthogonal to `layer-boundaries.md`

These two standards share the word "layer" and must be read together, but they govern
**different axes** and neither restates the other.

| | [`layer-boundaries.md`](layer-boundaries.md) | This doc (`layered-architecture-review.md`) |
|---|---|---|
| Axis | **Structural** — dependency direction *between* layers | **Quality** — doing a good job *at* each layer |
| Asks | "Are the dependencies correct?" (no reverse, no skip-layer imports) | "Did you consider the right quality attributes for this layer?" |
| Example rule | Domain must not import from infrastructure | A new query-filter column must have a backing index |
| Enforced by | Code review / import checks | The Layer Impact Analysis matrix-walk + `/build` gate |

A change can satisfy `layer-boundaries.md` perfectly (clean dependency direction) and still
ship the unindexed-query bug — because that is a *quality* failure at the data-access layer,
not a *structural* one. The two docs are complementary, not redundant.

## Where the Pieces Live

- **`standards/architecture/layer-rubrics.yaml`** — the registry. Single source of truth
  for the layer/rubric data (layers, detection signals, rubric items, severities,
  `mechanizable` flags).
- **`standards/architecture/layered-architecture-review.md`** — this document. The prose
  rationale and authoring guide.
- **`scripts/layer_review.py`** — the engine: `detect` (which layers does this design
  touch?) and `check` (is the Layer Impact Analysis table complete?). Both `/architect`
  and `/build` invoke this CLI; neither reimplements detection or checking.
- **`/architect`** — runs the interactive matrix-walk and writes the `## Layer Impact
  Analysis` table into `design.md`. Interactive only; never Agent-dispatched.
- **`/build` Step 1c** — runs `layer_review.py check`; warns and records to
  `verification.md` by default (advisory), and hard-blocks on unfilled `CRITICAL` items
  only when `architect_phase.layer_review_mandatory` is true.
