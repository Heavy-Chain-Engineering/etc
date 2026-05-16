# ADR-F020-002: Universal rules separate from per-profile bindings

**Date:** 2026-05-16
**Status:** Accepted
**Context:** Tier-0 standards like `clean-code.md`, `error-handling.md`, and `import-discipline.md` contain language-agnostic CONCEPTS (function size limit, never silently swallow errors, deps visible at top) wrapped in Python VOCABULARY (ruff codes like PLR0915, `raise/except` examples, E402 references). Three options: (a) keep everything as-is and add per-language siblings; (b) duplicate full standards trees per profile (`profiles/python/clean-code.md`, `profiles/go/clean-code.md`, each with their own full text); (c) split rules from bindings — rules at top level, bindings under profiles/.
**Decision:** Rules stay at `standards/code/clean-code.md` (the universal RULE). Bindings move to `standards/code/profiles/<profile>/clean-code-bindings.md` (the per-tool ENFORCEMENT). Agents read both at dispatch time: the rule for understanding, the binding for the lint code that flags it.
**Consequences:** *Positive:* lowest duplication; one place to refine the rule; per-profile drift is concentrated in a single bindings file. *Negative:* agents must read TWO files per rule (rule + binding) — a small extra context cost; the rule and the binding must stay in sync (the binding could cite a lint code that doesn't match the rule's intent).
