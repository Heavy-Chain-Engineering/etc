# ADR-001: Explicit prototype declaration, not heuristic detection

**Date:** 2026-05-30
**Status:** Accepted
**Feature:** F-2026-05-30-prototype-as-intent-design (Gap C)

**Context:** Gap C applies intent-only treatment to a prototype input to `/design`. The
gate can only fire if `/design` knows a prototype is present. Two detection strategies
exist: heuristic (infer from input shape — a `.tsx`/`.vue` mock, a Figma link, a
shadcn/Vite scaffold) or explicit (the operator declares it). The #54 incident — the
layer detector over-firing on harness-meta features because it keyed on prose
vocabulary — is direct evidence that subject-matter heuristics over- and under-fire.
The trilogy's other two features already chose explicit declaration (Gap B's
conflict-sources `AskUserQuestion`, Gap A's per-AC liveness).

**Decision:** `/design` detects a prototype by **explicit operator declaration** — a
Phase-1 question ("Is a prototype/mock an input? If so, where?") plus `--prototype <path>`
and `--component-lib <path>` flags. The declaration records
`state.yaml.design_phase.prototype: {declared, path, component_lib_path}`. The operator
naming the path is also how `/design` locates the prototype to extract intent and the
component library to source real tokens. No heuristic inference is performed.

**Consequences:**
- *Easier:* zero false-positives/negatives; deterministic; the operator who supplies a
  prototype is exactly the one who knows where it and the component lib live. Consistent
  with the trilogy's "declare intent, never infer it" principle.
- *Harder:* an operator who forgets to declare a prototype gets no hygiene — mitigated by
  the Phase-1 question being mandatory (a yes/no answer is required, like /spec's journey
  question).
- *Constrains:* future prototype-handling features inherit the explicit-declaration
  contract; no detector is added that a later feature would have to keep accurate.
