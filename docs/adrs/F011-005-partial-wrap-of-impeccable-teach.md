# ADR-F011-005: Partial wrap of /impeccable teach (post-process for metrics, no loop injection)

**Date:** 2026-05-11
**Status:** Accepted

**Context:**
/design dispatches `/impeccable teach` via the Skill tool (per ADR-F011-001) to capture design context as PRODUCT.md + DESIGN.md. Etc needs to populate its own state.yaml metrics (`design_phase.impeccable_version_pinned`, `tier_0_promoted`, `completed_at`) alongside impeccable's output. Three wrap depths were considered: (a) partial wrap (etc dispatches `/impeccable teach`, lets it run to completion, then post-processes by reading PRODUCT.md + DESIGN.md to populate metrics); (b) full pass-through (etc dispatches and accepts output as-is; metrics populated from /design's own context, not from impeccable's files); (c) deep wrap (etc injects etc-side processing inside impeccable's Socratic loop — e.g., inject etc-specific questions).

The deciding force is **respecting impeccable's contract**. Deep wrap breaks impeccable's loop and couples F011 tightly to impeccable's internal flow — fragile under upstream changes. Full pass-through requires /design to populate metrics from its own context (loses traceability — the metrics are second-hand). Partial wrap reads impeccable's authoritative output as the source of truth for metrics while leaving impeccable's loop untouched.

**Decision:**
Partial wrap. `/design` dispatches `/impeccable teach` via Skill tool, lets it run to completion (impeccable's Socratic capture writes PRODUCT.md + DESIGN.md at repo root), then **read-only post-processes** by:

1. Reading PRODUCT.md + DESIGN.md to verify they exist and are well-formed (per impeccable's documented schemas).
2. Reading impeccable's installed version (via `impeccable --version` or equivalent CLI probe) to populate `state.yaml.design_phase.impeccable_version_pinned`.
3. Scanning the accumulated ACs in spec.md (when /design --retrofit) or the in-session AC draft (when /design runs ahead of /spec) for user-facing-surface signals per F001 BR-002 to determine `tier_0_promoted: bool`.
4. Writing `state.yaml.design_phase.completed_at` as the post-impeccable-teach timestamp.

/design does NOT inject etc-side processing into impeccable's Socratic loop (deep wrap rejected). /design does NOT skip metric population (full pass-through rejected).

**Consequences:**
- **Easier:** state.yaml.design_phase metrics populated automatically from impeccable's authoritative output; impeccable's loop runs untouched (upstream changes don't break F011's wrap); etc owns the metric layer end-to-end without forking impeccable's internals.
- **Harder:** /design must understand PRODUCT.md/DESIGN.md schemas enough to read version + detect user-facing-surface signals; couples F011 lightly to impeccable's file formats (acknowledged in Security Considerations as a documented dependency, mitigated by version pinning per ADR-F011-001).
- **Deferred:** Deeper wrap (etc-side processing inside impeccable's loop — rejected on architectural grounds); ad-hoc impeccable-side configuration (future PRD if `/design` needs to pass project-specific config to `/impeccable teach`).
- **Cannot defer:** The post-process contract — /design's Phase 5 needs to know what to read from impeccable's output.
- **Related ADRs:** ADR-F011-001 (wrap-and-invoke) constrains the dispatch surface; ADR-F011-004 (minimal file-watch schema) constrains what /design does with browser-extension output. Together they define what /design touches in impeccable's surface area.
