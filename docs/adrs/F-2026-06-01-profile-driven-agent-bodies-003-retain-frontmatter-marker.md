# ADR F-2026-06-01-profile-driven-agent-bodies-003: Retain the `${profiles}` frontmatter as the profile-aware marker

**Date:** 2026-06-01
**Status:** Accepted

**Context:**
ADR-001 moves the load-bearing profile resolution into the agent body
(self-resolution), which raises the question of what to do with the F022
frontmatter placeholders `${profiles}` and `${profile_bindings_template}`. Claude
Code reads them as literal strings (it doesn't substitute them), so one option is
to remove them as dead weight. But etc tooling can still key on them.

**Decision:**
Retain `${profiles}` + `${profile_bindings_template}` in the frontmatter as the
**profile-aware marker**. The body-conformance check (ADR-002) uses the marker to
decide which manifests it scans (a manifest is "profile-aware" iff it carries the
marker), and any future real Claude Code agent-dispatch hook could resolve them
without reworking the manifests. The body self-resolve step is what actually
delivers the bindings; the marker is the declarative signal that the manifest opts
into the profile system.

**Consequences:**
- *Easier:* non-breaking (no churn to the three manifests that already carry the
  marker); gives the conformance check a clean "is this manifest in the convention?"
  signal; preserves a forward path if CC ever exposes a dispatch seam.
- *Harder:* the placeholders remain partly vestigial from Claude Code's literal-read
  perspective — a reader could mistake them for an active substitution. Mitigated by
  the extended `agent-manifest-profile-awareness.md`, which documents that the marker
  is declarative and the body self-resolves.
- `security-reviewer` and `verifier` adopt the marker as part of this feature so all
  four agents are uniformly detectable by the conformance check.
