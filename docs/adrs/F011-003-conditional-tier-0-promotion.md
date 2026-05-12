# ADR-F011-003: Conditional tier-0 promotion of PRODUCT.md + DESIGN.md

**Date:** 2026-05-11
**Status:** Accepted

**Context:**
Etc currently enforces tier-0 preflight on DOMAIN.md + PROJECT.md — Edit/Write operations are blocked until those files exist at repo root. This makes engineering context structurally enforceable. F011 introduces PRODUCT.md + DESIGN.md (impeccable's design context) as analogous root files for user-facing-surface features. Three tier-0 postures were considered: (a) always tier-0 (every repo, every feature, every commit requires PRODUCT.md + DESIGN.md); (b) conditional tier-0 (required only when the feature has a user-facing surface); (c) never tier-0 (files exist as soft convention; no hook enforcement).

The deciding force is **applicability**. Backend-only features (billing infra, observability, governance) have no UI surface and would be blocked by always-tier-0 with no benefit. Never-tier-0 loses the structural-enforcement parallel etc applies to DOMAIN.md/PROJECT.md.

A second consideration is hook architecture. The existing tier-0-preflight hook is not present at the expected path in this repo (`hooks/tier-0-preflight.sh` was not found during F011 codebase research). Three implementations were considered: (a) new hook file at `hooks/tier-0-design-preflight.sh`; (b) locate-and-extend the existing tier-0 hook (currently absent); (c) defer entirely to F013 (install.sh UX) which already touches install.sh + hooks.

**Decision:**
Conditional tier-0. The new hook at `hooks/tier-0-design-preflight.sh` fires on PreToolUse Edit/Write events; it reads `state.yaml.design_phase.tier_0_promoted` from the closest enclosing feature directory and blocks if `tier_0_promoted == true` AND PRODUCT.md OR DESIGN.md missing at repo root. The `tier_0_promoted` field is set to `true` automatically when `/design` Phase 5 completes successfully on a feature with a user-facing surface (≥1 AC classified user-facing per F001's signal list). Features without a user-facing surface skip the check.

The hook is a new file, not an extension of the existing missing-tier-0 hook (separate concern, future PRD).

**Consequences:**
- **Easier:** Backend-only features don't trigger PRODUCT/DESIGN preflight; matches the `(design | strategy)` mid-funnel branch routing in the 6-phase pipeline; mirrors DOMAIN.md/PROJECT.md's "block edits until present" discipline for the design domain.
- **Harder:** Requires accurate user-facing-surface detection (reuses F001 BR-002 signal list); false negatives → tier-0 doesn't fire when it should; the new hook coexists with (rather than replaces) the existing-but-currently-missing tier-0-preflight hook.
- **Deferred:** Consolidation with the existing tier-0 hook once it's located. Cryptographic signing of state.yaml (operator can manually bypass by editing the file; F011 accepts the operator-level trust model).
- **Cannot defer:** The new hook implementation (must be in F011's release).
- **Related ADRs:** None — this is a self-contained hook design.
