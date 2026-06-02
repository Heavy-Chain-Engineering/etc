# Agent Manifest Profile Awareness

Agents that enforce code quality read the right tool-specific rules for the
project's active language profiles — without hardcoding any language. This
standard documents the convention that makes that possible at two levels:

1. **Header level** — two declarative placeholder tokens in each manifest's YAML
   frontmatter (`${profiles}` / `${profile_bindings_template}`) that **mark** a
   manifest as profile-aware.
2. **Body level** — the manifest body itself must (a) **self-resolve** the active
   profile at start, before its heuristics run, and (b) contain **no
   language-specific operative tool/path** outside a bindings reference.

The header marker is the declarative signal; the body self-resolve step is the
load-bearing mechanism that actually delivers per-profile bindings to the agent.

> **History.** F022 introduced the frontmatter placeholders and described a
> *dispatch-time* substitution layer as the resolution mechanism, deferring that
> code to a follow-up PRD. That follow-up found there is no etc-owned seam in
> Claude Code's agent dispatch in which a substitution could live (ADR-001).
> Resolution therefore moved into the agent body. The header convention below is
> unchanged; the "Resolution Semantics" section is retained as historical context
> and superseded by **Body-Level Conformance**.

## Status: MANDATORY

## Applies to: Agent manifests under `agents/*.md`

A manifest is **profile-aware** if and only if it carries the marker — i.e. it
includes `${profiles}` and `${profile_bindings_template}` in its frontmatter
(ADR-003). The marker is what the body-conformance check keys on to decide which
manifests it scans.

This standard governs the four review/dev/verify agents brought into the
convention: `agents/code-reviewer.md`, `agents/backend-developer.md`,
`agents/security-reviewer.md`, `agents/verifier.md` — plus any other manifest
that carries the marker (e.g. `agents/code-simplifier.md`). All manifests
modified after the F022 release tag that include code-quality standards in their
`required_reading:` list MUST adopt this convention. Legacy manifests that do not
carry the marker and are not modified are out of scope and remain byte-unchanged
(see Forward-Only below).

## Contract

A profile-aware agent manifest MUST:

1. Express `language:` as the placeholder `${profiles}` rather than a
   hardcoded language name.
2. Include `${profile_bindings_template}` in its `required_reading:` list at
   the position where per-profile bindings files should be injected.
3. Not duplicate the placeholder in multiple positions.

A manifest that hardcodes `language: python` (or any other language name) is
non-conformant after the F022 release tag.

## Frontmatter Convention

```yaml
---
name: backend-developer
language: ${profiles}
required_reading:
  - standards/code/clean-code.md
  - standards/code/error-handling.md
  - ${profile_bindings_template}
  - standards/process/tdd-workflow.md
---
```

`${profiles}` and `${profile_bindings_template}` are **literal strings** that
appear verbatim in the committed manifest file. They are not Bash variable
references, not Python f-string syntax, and not a generalized templating
language. The dispatch layer reads these exact strings and substitutes them.
No other template syntax is defined or supported.

## Resolution Semantics (historical — superseded by Body-Level Conformance)

> **Superseded by ADR-001.** The dispatch-time substitution described in this
> section was never built: Claude Code's agent loader reads `agents/*.md`
> directly and exposes no etc-owned seam between "CC loads the manifest" and "the
> agent runs," and agents install globally to `~/.claude` while `profiles.lock`
> is per-project, so install-time resolution is also infeasible. Resolution is
> now performed **by the agent body itself** at start — see **Body-Level
> Conformance** below. The semantics here are retained to document the original
> intent and the per-profile binding path convention
> (`standards/code/profiles/<profile>/<rule>-bindings.md`), which the resolver
> still returns.

At dispatch time, the agent-dispatch path in the Skills layer:

1. Reads `.etc_sdlc/profiles.lock` to obtain the active profile set (one
   profile name per line, e.g., `python`, `typescript`).
2. Replaces `${profiles}` with the list of active profile names. If no
   profiles are active, `language:` resolves to an empty list.
3. Replaces `${profile_bindings_template}` with one entry per active profile
   per rule-binding file, following the path convention:
   `standards/code/profiles/<profile>/<rule>-bindings.md`. For example, with
   `python` active and rules `clean-code`, `error-handling`,
   `import-discipline`, three entries are injected.
4. If no profiles are active, the `${profile_bindings_template}` entry is
   dropped from the resolved list entirely. The agent runs on top-level rules
   only.

This resolution is **string substitution only**. It is not a generalized
templating engine. Conditional logic, loops, and any syntax beyond the two
named placeholders are out of scope.

**Resolution mechanism (current):** the dispatch-time substitution above was
never implemented. The follow-up that was deferred to "a follow-up PRD"
established that the substitution has nowhere to live (ADR-001), so resolution
moved into the agent body. See **Body-Level Conformance** for the mechanism that
is actually load-bearing today.

## Body-Level Conformance

The frontmatter marker declares intent; it does not, on its own, get
profile-correct bindings in front of the agent (Claude Code reads the
placeholders as literal strings). Two body-level rules carry that load. Both
apply to every profile-aware manifest (any manifest carrying the marker).

### Rule 1 — Agent-body self-resolution (ADR-001)

A profile-aware agent MUST resolve its active profile **in a Before-Starting
step**, before any of its body heuristics execute. Concretely, the agent body:

1. Runs the resolver as its first Before-Starting action:

   ```bash
   python3 ~/.claude/scripts/resolve_agent_profile.py resolve
   ```

   The resolver reuses `profile_loader.active_profiles()` to read the project's
   `profiles.lock` and returns the active profile names, the per-profile
   **bindings paths** the agent should read, and a toolchain summary. It is
   read-only over `profiles.lock`, returns binding *paths* (it never opens them),
   and **exits 0 on any completed read** — an absent or empty lock yields empty
   profiles plus a "no active profile; top-level rules only" note and never
   crashes.
2. **Reads the returned bindings** before its heuristics run, and drives those
   heuristics from "the active profile's configured commands" rather than any
   named tool.
3. On an absent/stale lock or unsupported stack, falls back to profile-neutral
   generic heuristics with a stated limitation — **never** Python-by-default.

The self-resolve step — not the frontmatter marker — is what actually delivers
the bindings. A forgotten resolve step degrades the agent to its generic
fallback; the conformance check (Rule 2) is the backstop that keeps the body
honest.

### Rule 2 — Body conformance: no hardcoded operative tool/path (ADR-002)

A profile-aware manifest **body** MUST NOT name a language-specific operative
tool or path outside a bindings reference. "Fixing Python-hardcoding by adding
TypeScript-hardcoding is the same bug relocated" — so the rule forbids *any*
single-stack operative token, not just Python ones.

This is enforced by:

```bash
python3 ~/.claude/scripts/manifest_body_conformance.py check <manifest.md...>
```

a deny-list scan (a sibling of `scripts/layer_review.py`) that flags operative
language-tool tokens — `pytest`, `ruff`, `mypy`, `uv run`, `@router.`,
`pip audit`, `pyproject`, `src/`, and the like — appearing in a profile-aware
manifest body. Exit codes:

- **0** — every scanned profile-aware body is clean.
- **2** — a body names an operative token outside an allowed context; stdout
  lists `<manifest>:<line>: <token>` per violation.
- **1** — usage or I/O error.

**Operative vs. illustrative (the over-fire foil).** The check is the #54/#46
over-fire family's foil: it MUST NOT fire on a token that is merely *illustrative*
or *referenced*, only on one used as an operative instruction. It excludes
fenced code blocks, clearly-illustrative/example mentions, and lines that
reference the profile bindings (reusing `layer_review`'s fenced/section-exclusion
approach). The intent — operative-instruction-only — is fixed by this standard;
the precise token set and matching rule are finalized at build time.

> The resolver (`resolve_agent_profile.py`) and the conformance check
> (`manifest_body_conformance.py`) are implemented by sibling tasks of this
> feature. This standard defines the convention they enforce; it does not
> implement them.

## Forward-Only

This convention applies to agent manifests created or modified after the F022
release tag, and the body-level rules apply to every manifest carrying the
marker.

The four named review/dev/verify agents — `code-reviewer`, `backend-developer`,
`security-reviewer`, and `verifier` — are brought into the convention (header
marker + body self-resolution + body conformance) here. Any other manifest that
carries the `${profiles}` / `${profile_bindings_template}` marker is likewise in
scope for both header and body rules.

Legacy manifests that do not carry the marker and are not modified are **out of
scope and remain byte-unchanged** — the convention is forward-only and is never
retroactively forced onto a manifest that no one touched. When a legacy manifest
is modified for any reason after the F022 release tag, it MUST be brought into
conformance with this standard (header + body) as part of that change.

## Examples

**Before (non-conformant — hardcoded language):**

```yaml
---
name: backend-developer
language: python
required_reading:
  - standards/code/clean-code.md
  - standards/code/profiles/python/clean-code-bindings.md
  - standards/code/error-handling.md
  - standards/code/profiles/python/error-handling-bindings.md
---
```

**After (conformant — profile-aware):**

```yaml
---
name: backend-developer
language: ${profiles}
required_reading:
  - standards/code/clean-code.md
  - standards/code/error-handling.md
  - ${profile_bindings_template}
---
```

**Resolved at dispatch time (Python active):**

```yaml
---
name: backend-developer
language:
  - python
required_reading:
  - standards/code/clean-code.md
  - standards/code/error-handling.md
  - standards/code/profiles/python/clean-code-bindings.md
  - standards/code/profiles/python/error-handling-bindings.md
  - standards/code/profiles/python/import-discipline-bindings.md
---
```

**Resolved at dispatch time (no profile active):**

```yaml
---
name: backend-developer
language: []
required_reading:
  - standards/code/clean-code.md
  - standards/code/error-handling.md
---
```

## Background

This convention applies the same dispatch-time resolution pattern that F020
introduced for hook scripts to a second harness surface: agent manifest
frontmatter.

The architectural parent is **F020-ADR-005 (hook generalization pattern)**,
recorded at `docs/adrs/F020-005-plaintext-profiles-lock.md` and summarized in
`docs/adrs/F020-001-profile-architecture-primitive.md`. F020-ADR-005
established that hooks consult `profiles.lock` at fire time and dispatch to
per-profile scripts rather than hard-wiring tool calls. The agent manifest
convention extends this same "resolve at invocation time, not at authoring
time" philosophy from hooks to manifests.

The rule-vs-binding split that this convention enables is specified in
**F020-ADR-002** (`docs/adrs/F020-002-rules-vs-bindings-split.md`): universal
rules live at `standards/code/<rule>.md`; per-tool bindings live at
`standards/code/profiles/<profile>/<rule>-bindings.md`. An agent that reads
both layers gets the language-agnostic rule AND the project's active tool
enforcement — with zero hardcoding in the manifest itself.

## Anti-patterns

**Hardcoding the language name.**

```yaml
language: python          # non-conformant
language: [python, go]    # non-conformant
```

Hardcoding defeats the purpose: adding TypeScript to the project requires
manually editing every manifest. Use `${profiles}`.

**Hardcoding per-profile binding paths.**

```yaml
required_reading:
  - standards/code/profiles/python/clean-code-bindings.md   # non-conformant
```

This is brittle for the same reason. Use `${profile_bindings_template}`.

**Inventing additional template syntax.**

The substitution layer recognizes exactly two tokens: `${profiles}` and
`${profile_bindings_template}`. Any other `${...}` pattern is not a template
token — it will appear literally in the resolved manifest or cause a dispatch
error, depending on the implementation. Do not extend the syntax without a
follow-up PRD.

**Placing `${profile_bindings_template}` multiple times.**

Insert the placeholder once. The dispatch layer injects all active-profile
binding entries at that single position. Repeating the placeholder produces
duplicate entries in the resolved reading list.

**Omitting the placeholder when profile-specific enforcement is relevant.**

An agent that performs code quality work and does not include
`${profile_bindings_template}` in its `required_reading:` list operates on
universal rules only. This is only correct for agents whose work is genuinely
language-agnostic. Agents like `backend-developer`, `code-reviewer`, and
`code-simplifier` MUST include the placeholder.
