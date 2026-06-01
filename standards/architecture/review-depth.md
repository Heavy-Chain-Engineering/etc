# Review Depth — Engage With Architecture, Not Surface Lint

## Status: MANDATORY
## Applies to: Architect, Architect Reviewer, Discovery (archaeology), and any review-class pass

## The Rule

A review, an architecture pass, or a system archaeology dig MUST engage with the
**architecture** — and must not stop at **surface lint**.

- **Architecture** (the reviewer's job — what a tool cannot judge): module
  boundaries and responsibilities; data flow across tiers; coupling and
  cohesion; dependency direction (inward, per `layer-boundaries.md`); whether
  abstractions earn their keep (`abstraction-rules.md`); invariants and
  contracts at trust/tier boundaries; and the **masquerade gap** — what the
  system *claims* to be versus what it *actually does* (the discovery
  archaeology lens).
- **Surface lint** (NOT the reviewer's value — the machine's job): formatting,
  whitespace, import order, line length, naming nits, style preferences.
  Linters, formatters, and the per-wave `verify-green` gate already enforce
  these. A review whose findings are only surface lint has added **no
  architectural value** — it has done the linter's job and skipped its own.

The test: *would a linter or formatter have caught this finding?* If yes, it is
surface lint — let the tool own it, and spend the review's attention on the
structural questions a tool cannot answer.

## Always In Force

- The architect (`/architect`) reasons about boundaries, data flow, and the
  Layer Impact Analysis at this depth — not at the depth of style.
- The architect-reviewer (`agents/architect-reviewer.md`) reviews structure,
  coupling, and pattern fitness; it explicitly does NOT review line-level code
  quality (that is the code-reviewer's lane) and never reduces a review to lint.
- Discovery (`/discovery`) digs for the truth the code executes — the
  masquerade, the load-bearing complexity, the hidden workflows — not a shallow
  file inventory.

This is not licence to ignore lint; it is a statement of where each layer's
*value* lives. Lint is owned by tools at the wave boundary; architecture is
owned by the human-or-agent reviewer who can see what the tool cannot.

## Cross-References

- `standards/architecture/layer-boundaries.md` — dependency direction, layer
  violations (an architectural finding class).
- `standards/architecture/abstraction-rules.md` — whether an abstraction earns
  its cost (an architectural finding class).
- `standards/process/code-review-process.md` — the code-reviewer's line-level
  checklist (the surface/quality lane this standard is distinct from).
- `agents/architect-reviewer.md` — the reviewer that embodies this depth.

## Origin

Crystallized 2026-06-01 from a recurring instinct across the harness: the
`/janitor` pass deferring a 250-file `ruff format` sweep because the *value* is
architectural, not cosmetic; the architect-reviewer's standing posture ("the
real architecture is what the code does, not what the README claims"); and the
`/discovery` masquerade lens. The principle is single-sourced here and cited by
path so it cannot drift between the skills and agents that share it.
