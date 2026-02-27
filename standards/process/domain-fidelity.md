# Domain Fidelity

## Status: MANDATORY
## Applies to: All agents (especially Researcher, PM, Architect, Domain Modeler)

## The Rule

Every agent must understand the domain correctly before producing any artifact. A wrong domain understanding cascades through every downstream phase — wrong PRDs, wrong architecture, wrong implementation. Getting the domain wrong is the most expensive mistake the harness can make.

**Research and specification exist to establish 100% fidelity to the domain and model — NOT to rush to implementation.**

## Domain Briefing Document

Every project SHOULD have a `docs/domain-briefing.md` (or equivalent) that establishes the non-negotiable truths about the domain. This file is injected into every agent as shared context.

### What Goes in a Domain Briefing

**Domain axioms** — statements that are TRUE about this domain and must never be contradicted:

```markdown
# Domain Briefing — [Project Name]

## Domain Axioms (non-negotiable truths)

1. [Technology X] is used for [domain purpose], NOT [common/default purpose].
   Example: "OPA/Rego is the compliance policy engine — the core product. It is NOT used for infrastructure RBAC or authorization."

2. [Core concept] means [domain-specific meaning].
   Example: "A 'compliance plan' is a first-class entity that a product has. It contains evidence items."

3. [Relationship] works this way, not that way.
   Example: "Compliance is relationship-scoped — a vendor's compliance status depends on which customer relationship is being evaluated."

## Anti-Patterns (common misunderstandings)

- Do NOT assume [X] means [common meaning]. In this domain, [X] means [domain meaning].
- Do NOT default to [common pattern]. This domain requires [domain-specific pattern].

## Key Terminology

| Term | Meaning in This Domain | Common Meaning (WRONG here) |
|------|----------------------|---------------------------|
| [term] | [correct meaning] | [incorrect default] |
```

### When to Create It

- **Before research begins** if the human knows the domain well enough to state axioms
- **After initial research** if the domain is unfamiliar — the researcher produces a DRAFT, the human corrects it, and the corrected version becomes the briefing
- **Iteratively** as understanding deepens — update it when new axioms are discovered

## Domain Fidelity Verification

### For the Researcher

After completing research but BEFORE producing the final report:

1. **State your understanding of core concepts** — explicitly write out what you believe each key technology, entity, and relationship means in THIS domain
2. **Flag where your understanding might default to common usage** — if a technology has a well-known primary use case that differs from how this domain uses it, call it out
3. **Ask the human to verify** — "Here is my understanding of the core domain concepts. Please correct anything I got wrong before I finalize the research report."

### For the SEM

When deploying agents for ANY phase:

1. **Check if `docs/domain-briefing.md` exists** — if it does, include it in every agent's briefing
2. **If it doesn't exist and the domain is non-trivial** — ask the human: "Should we create a domain briefing before proceeding? This prevents agents from misunderstanding core concepts."
3. **After research completes** — verify the researcher's domain understanding before proceeding to Spec

### For the PM and Architect

Before writing PRDs or ADRs:

1. **Read the domain briefing** — internalize the axioms
2. **Cross-check every technology choice against the axioms** — if you're recommending a technology, verify that your understanding of its role matches the domain briefing
3. **If a concept feels ambiguous** — stop and ask. Never assume. The cost of asking is minutes; the cost of assuming wrong is rebuilding.

## Why This Matters

A technology like OPA/Rego has a well-known primary use case (infrastructure policy). An AI agent defaults to that understanding because that's what most training data shows. But in a compliance product, OPA/Rego IS the product — it evaluates compliance policies, not infrastructure policies. This is not a subtle distinction. It's the difference between building the right system and building the wrong one.

**The domain briefing is the antidote to default assumptions.** It forces explicit statements about what things mean HERE, not what they mean in general.

## Cascade Risk

Domain errors compound exponentially:

```
Wrong domain understanding
  → Wrong research conclusions
    → Wrong PRD requirements
      → Wrong architecture decisions
        → Wrong implementation
          → System that solves the wrong problem
```

Every phase downstream trusts the phase upstream. If research gets the domain wrong, everything built on that research is wrong. This is why domain fidelity is checked EARLY and EXPLICITLY, not discovered during user testing.
