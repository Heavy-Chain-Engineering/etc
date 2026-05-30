# ADR-002: Component-lib-first as a global standing standard (location is local)

**Date:** 2026-05-30
**Status:** Accepted
**Feature:** F-2026-05-30-prototype-as-intent-design (Gap C)

**Context:** The pbj build copied the prototype's `covr-warning-*` Tailwind tokens (which
didn't exist) and its raw DOM/CSS as canonical, instead of referencing the project's real
component library and design tokens. The fix forced on tag 6 — "look at
`@libs/components/src/` first" — was a per-project rediscovery. Industry handoff practice
(design-tokens-as-single-source-of-truth; UXPin Merge's component-code-as-SSOT) says the
production component library *is* the canonical layer; prototypes reference real tokens,
never approximate them. The question: is "component-lib-first" a per-project rule or a
universal discipline?

**Decision:** The discipline is a **global standing standard**:
`standards/process/prototype-as-intent.md` (sibling of `source-of-truth-conflict-rule.md`)
states that a declared prototype's classes/tokens/DOM/fetch are **illustrative, never
canonical**; the implementation references the project's real component library + real
design tokens. The component-library **location** is project/profile-specific — supplied
by the operator via `--component-lib <path>` (recorded in
`state.yaml.design_phase.prototype.component_lib_path`). `design-tokens.json` is sourced
from that path, never from prototype token names. This is the same split Gap B used for
the conflict rule: the rule is global and never re-litigated; the operand (here, the lib
path) is per-feature.

**Consequences:**
- *Easier:* the "use the component lib first" lesson is encoded once, applied to every
  prototype-driven design; `design-tokens.json` carries real, grep-able tokens that the
  build can trust. Legible to any engineer (the standard names the discipline).
- *Harder:* a project with no component library yet must declare that gap (Edge Case 2);
  the standard must stay technology-neutral (it names the discipline, not a specific lib).
- *Constrains:* `design-tokens.json` provenance — tokens come from the declared lib path,
  and a coinciding prototype token name does not make the prototype the source (Edge Case 5).
