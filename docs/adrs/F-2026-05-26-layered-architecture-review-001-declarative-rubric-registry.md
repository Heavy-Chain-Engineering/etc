# ADR-F-2026-05-26-001: Rubric registry is declarative data (YAML), not embedded code or prose

**Date:** 2026-05-26
**Status:** Accepted

**Context:** The Layer Impact Analysis phase needs a representation of the architectural layers and, per layer, the set of quality criteria (the "rubric") the architect must answer. The operator chose full breadth — all core layers (data-access, domain-service, api-contract, presentation-frontend, infra-ops) plus cross-cutting concerns — so the representation will hold ~30-40 criteria and will grow as layers and criteria are added over time. Three representations were available. (a) Declarative data — a YAML registry the skills read. (b) Prose — the criteria written into `skills/architect/SKILL.md` body and walked by the model reading its own instructions. (c) Embedded code — the criteria as Python data structures inside `layer_review.py`.

The registry has two consumers: `/architect` (reads it to know which layers exist and what to ask) and `/build` Step 1c (reads it to know what completeness means). Whatever the representation, both consumers must agree on it, and adding a layer or a criterion must not require editing skill prose or program logic.

**Decision:** A declarative YAML registry at `standards/architecture/layer-rubrics.yaml`. Top-level `layers` and `cross_cutting_concerns`; each layer carries `id`, `name`, `detection_signals`, and a `rubric` list; each rubric item carries `id`, `criterion`, `quality_attribute` (ISO 25010), `severity_if_missed`, and `mechanizable`. `scripts/layer_review.py` parses it; `standards/architecture/layered-architecture-review.md` is the prose rationale anchor. Adding a layer or criterion is a data edit to the YAML, reviewed in a PR — no skill-prose rewrite, no code change.

This mirrors the F020 profile-registry pattern (per-language vocabulary in `profiles/*.yaml`, rationale in a standards doc, code reads the data) and the F025-001 "data in a standards doc, deterministic engine over it" precedent.

**Consequences:** *Positive:* breadth is maintainable — the operator's full-breadth choice is a YAML file, not 40 paragraphs of skill prose; single source of truth — both /architect and /build read the same file, so detection and completeness can never drift apart; auditable — the entire rubric is one reviewable file; hand-authorable — YAML multi-line strings suit prose criteria; testable — a schema test asserts every item has every required field; no new dependency — PyYAML is already transitive. *Negative:* a YAML registry is one more file to keep in sync with the standards-doc prose (mitigation: the standards doc cites the registry as the source of truth and carries no duplicate criteria list); a malformed registry edit breaks both consumers at once (mitigation: schema test in CI; `layer_review.py` exits non-zero with a clear parse error rather than silently degrading — EC-003).

**Alternatives considered:**

*Prose in SKILL.md* (rejected). Write the layers + criteria into the /architect skill body. *Positive:* no registry file; the model reads its instructions directly. *Negative:* full breadth becomes ~40 paragraphs of skill prose that /build cannot consume (the build gate would need its own copy → guaranteed drift); adding a criterion is a skill-prose edit, not a data edit; no schema validation possible; the F024 dispatch-assembler lesson (mechanize prose into data) argues directly against re-encoding a structured registry as prose.

*Embedded code in layer_review.py* (rejected). The registry as Python dicts/dataclasses inside the engine. *Positive:* no parse step; type-checked. *Negative:* editing the rubric means editing program logic (higher-risk change surface); non-programmers (the operator authoring rubric criteria) edit Python instead of YAML; diverges from the F020 data-driven precedent; the registry stops being a reviewable artifact separate from the engine.

The chosen design keeps the rubric as reviewable data, the engine as a deterministic reader, and the standards doc as the rationale — the same separation F020 and F025 established.

**Related ADRs:**
- F-2026-05-26-002 (matrix-walk forcing function) — consumes this registry.
- F-2026-05-26-003 (architect-reasons / build-enforces) — both consumers read this registry.
- F020 profile-registry pattern (precedent); F025-001 (deterministic engine over standards-doc data).
