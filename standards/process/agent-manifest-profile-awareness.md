# Agent Manifest Profile Awareness

Agents that enforce code quality read the right tool-specific rules for the
project's active language profiles — without hardcoding any language. This
standard documents the frontmatter convention that makes that possible: two
placeholder tokens in each manifest's YAML header that the dispatch layer
resolves at the moment the agent is invoked, based on the project's live
`profiles.lock`.

## Status: MANDATORY

## Applies to: Agent manifests under `agents/*.md`

Applies to manifests that include code-quality standards in their
`required_reading:` list. Currently: `agents/backend-developer.md`,
`agents/code-reviewer.md`, `agents/code-simplifier.md`. All manifests
modified after the F022 release tag MUST adopt this convention. Manifests
unchanged before that tag are not retroactively required to update (see
Forward-Only below).

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

## Resolution Semantics

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

**Out of scope:** the dispatch code that performs this substitution. That code
lives in the Skills layer and will be wired in a follow-up PRD. This standard
defines WHAT the convention is and WHERE it integrates; it does not specify HOW
the substitution is implemented.

## Forward-Only

This convention applies to agent manifests created or modified after the F022
release tag. Legacy manifests (those unchanged between F001 and F021) are not
retroactively required to update. When a legacy manifest is modified for any
reason after the F022 release tag, it MUST be brought into conformance with
this standard as part of that change.

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
