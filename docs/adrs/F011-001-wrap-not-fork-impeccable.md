# ADR-F011-001: Wrap impeccable via Skill tool, do not fork

**Date:** 2026-05-11
**Status:** Accepted

**Context:**
F011 introduces a `/design` phase that needs the design-conversation machinery impeccable already provides (Socratic capture via `/impeccable teach`, persistence to PRODUCT.md + DESIGN.md, load-on-every-command via `load-context.mjs`, 27 anti-pattern rules, 7 reference domains). Three integration shapes were considered: (a) wrap impeccable via the Skill tool (invoke as-is, preserving auth context, accepting impeccable as an external dependency); (b) fork impeccable's source into etc's distribution (vendor the code, ship as a single unit); (c) re-implement impeccable's machinery natively in etc (write our own Socratic + persistence + anti-pattern layer).

Impeccable is Apache 2.0, v3.0.7+ (production-ready, May 2026), already publishes a Claude Code skill, and implements byte-identically the same four-stage architectural pattern etc uses everywhere else (Socratic capture → root-markdown persistence → load-on-every-command → directive output enforcement). Two independent projects converged on the same shape.

**Decision:**
Wrap impeccable via the Skill tool. `/design` Phase 1 dispatches `/impeccable teach` via `Skill.dispatch(...)` (NOT subprocess; preserves auth context per F006 BR-010 chain semantics). Etc owns only the orchestration glue (`skills/design/SKILL.md`) and the etc-native state surface (`state.yaml.design_phase`, `value-hypothesis.design_author_role`, `gray-areas-design.md`, `design-tokens.json`, `component-specs.md`, git tags). Impeccable owns the design conversation, the PRODUCT.md + DESIGN.md schemas, and the anti-pattern enforcement.

Version pinning: ≥v3.0.7, < next-major (v4.0). Major-version bumps require explicit re-spec.

**Consequences:**
- **Easier:** Preserves upstream impeccable updates with zero maintenance debt; license stays Apache 2.0 without F011 incorporating impeccable's code into etc's distribution; impeccable's 27 anti-pattern rules + 7 reference domains stay current automatically.
- **Harder:** F011 depends on impeccable's continued upstream maintenance + Skill tool compatibility; supply-chain trust extends to impeccable upstream (mitigated by version pinning + pbakaus maintainer reputation per the Security Considerations section of design.md).
- **Deferred:** SBOM tracking, static analysis of impeccable's source, fork-and-vendor migration path if impeccable upstream becomes unmaintained.
- **Cannot defer:** Version-pinning contract (lives in `skills/design/SKILL.md` Phase 1 detection logic).
- **Related ADRs:** ADR-F011-005 (partial-wrap discipline) constrains what /design does with impeccable's output. Together they define the wrap surface.
