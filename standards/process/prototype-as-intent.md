# Prototype-as-Intent Rule

## Status: MANDATORY
## Applies to: /design

## The Problem

A `/design` run may take a **prototype** as input — a shadcn/Vite mock, a
Figma export, a reference implementation, an impeccable-style `DESIGN.md`
artifact. A prototype *demonstrates* intent: information architecture,
interaction, outcomes. It also *happens to be coded* a particular way: CSS
classes, design tokens, DOM/element structure, fetch/auth wiring. When the
two are conflated, the build transcribes the implementation as if it were the
requirement.

In the covr.care `pbj` build, exactly this happened. A shadcn/Vite prototype
was transcribed literally: `covr-warning-*` Tailwind tokens that **did not
exist** were copied into the design; bare `axios` calls and anchors shipped
with **no auth and no base-URL**; `<ul>/<li>` markup inherited the host app's
CSS by accident; and "EMPLOYEE INFO" / "Name Name" scaffolding rows were
ingested as **real CMS worker profiles** — a P0. Affordances were guessed
wrong: the Hours column was deferred **three times** because no one had marked
it REQUIRED.

This standard makes the prototype-as-intent discipline a permanent, MANDATORY
rule so no `/design` run ever has to invent it again.

## The Rule

When a prototype is a **declared** `/design` input
(`state.yaml.design_phase.prototype.declared = true`):

1. **Intent-only.** Treat the prototype as intent — IA, interaction, outcomes.
   Its CSS classes, design tokens, DOM/element structure, and fetch/auth
   wiring are **ILLUSTRATIVE, never canonical**. They MUST NOT be carried into
   `design-tokens.json` or `component-specs.md` as the implementation. The
   prototype shows *that* a surface persists X and *how it reads*; the build
   wires the real auth, the real markup, the real tokens. [AC-3, AC-8]

2. **REQUIRED vs ILLUSTRATIVE.** Every affordance enumerated in
   `component-specs.md` is marked **REQUIRED** or **ILLUSTRATIVE** —
   grep-able, co-located with the affordance. An affordance that is neither
   clearly required nor clearly illustrative **defaults to REQUIRED and is
   flagged for review** (the Hours column was deferred 3× by guessing the
   other way). [AC-4]

3. **Component-lib-first.** Reference the project's **real component library**
   and **real design tokens**. `design-tokens.json` is sourced from the
   declared `component_lib_path`, **never** from the prototype's token names.
   Provenance over coincidence: a prototype token that *happens* to match a
   real token is still sourced from the library, not copied from the mock. The
   discipline is global; the lib location is project-supplied (a project with
   no component library declares the gap and proceeds). [AC-2, AC-7]

4. **Data fidelity + clean template.** Seed/fixture data MUST reproduce
   **every value the prototype displays**. The ingestible template carries
   **no scaffolding rows** (e.g. "Name Name", "EMPLOYEE INFO") in the
   ingestible range. `/design` *declares* this requirement into its output;
   build-time enforcement (Gap A's runtime/clean-template gate) *executes* it
   — declare-not-execute. [AC-5, AC-6]

The declaration is always **recorded, never silently inferred**: a prototype
is in play only when the operator declares it.

## Always In Force

This rule is **standing and MANDATORY**. It is **never re-litigated per
feature** — adopting it is the default whenever a prototype is declared, not a
per-build decision. No `/design` run may opt out of, weaken, or re-derive the
intent-only discipline.

What *is* per-feature is whether a prototype is declared at all. A
non-prototype `/design` run (`declared = false`) applies no prototype hygiene
and behaves exactly as today — the rule is fixed, only the *operand* (a
declared prototype) varies. Legacy design artifacts are never auto-mutated.

## Cross-References

- `standards/process/contract-completeness.md` — the contract classes the
  prototype helps populate; this rule keeps prototype *implementation* out of
  those contracts.
- `standards/process/source-of-truth-conflict-rule.md` — when a declared
  prototype is an in-play source in a `{code, spec, prototype}` conflict, that
  rule arbitrates; this rule ensures the prototype is treated intent-only even
  when it is in play.
- `docs/adrs/F-2026-05-30-prototype-as-intent-design-001-explicit-prototype-declaration.md`
  — explicit prototype declaration, not heuristic detection.
- `docs/adrs/F-2026-05-30-prototype-as-intent-design-002-component-lib-first-standing-standard.md`
  — component-lib-first as a global standing standard.
- `docs/adrs/F-2026-05-30-prototype-as-intent-design-003-declare-not-execute-boundary.md`
  — `/design` declares data-fidelity; build (Gap A) executes.

**Lineage:** design tokens as a single source of truth + component-code-as-SSOT
handoff (UXPin Merge) — the production component library is canonical, not the
prototype's approximations. Explicit declaration over heuristic inference is
the trilogy principle (Gap B declares contracts, Gap A verifies at runtime, Gap
C reads the prototype for intent).

**Origin:** covr.care `pbj` build retrospective (2026-05-29) — a shadcn/Vite
prototype transcribed literally: non-existent `covr-warning-*` tokens, no-auth
`axios`, host-CSS-inheriting markup, and "Name Name" scaffolding rows ingested
as real worker profiles (P0).
