# ADR F-2026-06-01-profile-driven-agent-bodies-001: Agent-body self-resolution (no etc dispatch seam in CC)

**Date:** 2026-06-01
**Status:** Accepted

**Context:**
F022 added the `${profiles}` / `${profile_bindings_template}` placeholders to
agent manifest headers and explicitly deferred "the dispatch code that performs
this substitution" to a follow-up PRD — which was never built. Research for this
feature found why: Claude Code's agent loader reads `agents/*.md` directly and has
no knowledge of etc's `profiles.lock` convention, and there is no etc-owned hook or
shim between "CC loads the manifest" and "the agent runs." So a resolver that
substitutes the placeholders *at dispatch* (the spec's BR-001 framing) has nowhere
to live. Install-time resolution is also infeasible — agents install globally to
`~/.claude` but `profiles.lock` is per-project, so install cannot know the target
repo's stack.

**Decision:**
Resolve the active profile in the **agent body**, not at dispatch. Each
profile-aware agent gains a Before-Starting step that runs a thin resolver
(`scripts/resolve_agent_profile.py`, reusing `profile_loader.active_profiles()`),
which reads the project's `profiles.lock` and returns the active profile names, the
per-profile bindings paths to read, and a toolchain summary. The agent reads those
bindings and its de-hardcoded heuristics reference "the active profile's configured
commands." This reframes BR-001 from "resolve at dispatch" to "the agent
self-resolves at start."

**Consequences:**
- *Easier:* works within Claude Code as-is — no agent-loader change, no dispatch
  shim, no install-time stack knowledge required. Deterministic (the resolver reads
  the lock, not the model's guess). Reuses the existing, tested `profile_loader`.
- *Harder:* every profile-aware agent must actually run the resolve step; a
  forgotten step degrades the agent to its profile-neutral generic fallback rather
  than stack-correct heuristics. Mitigated by (a) the body-conformance check
  (ADR-002) which keeps bodies honest, and (b) a profile-neutral fallback so a
  missed resolve never reverts to Python-by-default.
- The F022 standard's "Resolution Semantics" (dispatch-time substitution) is
  superseded by this ADR; `agent-manifest-profile-awareness.md` is extended to
  state self-resolution as the mechanism.
- If Claude Code ever exposes a real agent-dispatch hook, the retained frontmatter
  marker (ADR-003) lets a future dispatch-time resolver be added without reworking
  the manifests.
