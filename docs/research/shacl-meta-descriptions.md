# Research: SHACL as .meta/ Description Format

**Status:** Not started
**Priority:** Medium — foundational if validated
**Source:** https://github.com/kurtcagle/shacl-methodology

## Hypothesis

The current `.meta/description.md` files are free-form markdown — useful for human orientation but not machine-validatable. SHACL (Shapes Constraint Language) offers a constraint-driven, shape-first alternative that could replace or enhance `.meta/` with formal descriptions that are both human-readable and programmatically enforceable.

## Why This Matters

- `.meta/` descriptions drift from code because nothing validates them
- SHACL shapes are constraints — they can be *checked*, not just read
- The methodology is explicitly governance-first, iterative, and exit-criteria-gated — mirrors our SDLC philosophy
- LLM-assisted with guardrails is a stated design principle of the SHACL methodology

## Key Questions

1. Can SHACL shapes describe module boundaries, dependencies, and patterns in a way that agents can consume?
2. Is the overhead of RDF/Turtle worth the formalism vs. structured markdown?
3. Could guardrails validate `.meta/` descriptions against SHACL shapes (self-enforcing descriptions)?
4. What's the minimal viable adoption — full ontology or just shape constraints on the `.meta/` format?
5. How does this interact with the bootstrapper (generates descriptions) and reconciliation (validates them)?

## SHACL Methodology Summary

From Kurt Cagle's 8-year enterprise knowledge graph practice:

- **Shape-first, not class-hierarchy-first** — describes data constraints, not inheritance trees
- **Constraint-driven, not inference-driven** — validates what IS, doesn't infer what COULD BE
- **10-phase methodology**: governance → namespace → use cases → taxonomy → schema → shapes → validation → review → transformers → ongoing governance
- **Iterative phases 2-7** with defined re-entry points
- **Exit-criteria gated** — observable completion conditions

## Potential Integration Points

- `.meta/description.md` → `.meta/shape.ttl` (or both)
- Guardrail rule: "does this module's actual structure satisfy its SHACL shape?"
- Bootstrapper generates initial shapes from code analysis
- Reconciliation validates shapes against current code state
