# ADR F-2026-06-01-profile-driven-agent-bodies-002: Body-conformance as an over-fire-safe deny-list scan

**Date:** 2026-06-01
**Status:** Accepted

**Context:**
The field incident was caused by agent bodies hardcoded to one language's tools.
The fix must not silently relapse — and the block's own warning is that "fixing
Python-hardcoding by adding TypeScript-hardcoding is the same bug relocated." So a
check is needed that fails any profile-aware manifest body that names a
language-specific operative tool/path. The risk is the over-fire family (#54
layer-review, #46 spec-coupling): a check that flags an *illustrative* mention (an
example in prose, a fenced snippet, a reference to the profile bindings) trains the
operator to ignore it.

**Decision:**
Add `scripts/manifest_body_conformance.py`, a sibling of `layer_review.py`: a
deny-list scan that flags operative language-tool tokens (`pytest`, `ruff`, `mypy`,
`uv run`, `@router.`, `pip audit`, `pyproject`, `src/`, …) appearing in a
profile-aware manifest body, and **excludes** fenced code blocks, clearly-
illustrative/example contexts, and lines that reference the profile bindings
(reusing `layer_review.scannable_text`'s exclusion approach). Exit 0 when clean,
exit 2 with `<manifest>:<line>: <token>` per violation, exit 1 on usage/IO error.
The intent (operative vs. illustrative distinction) is fixed; the precise token set
and matching rule are finalized at build.

**Consequences:**
- *Easier:* mechanical, testable, matches the established helper-script + exit-code
  precedent; makes "no re-hardcoding to any language" enforceable rather than
  aspirational.
- *Harder:* the deny-list must be maintained as new profiles/tools appear, and the
  illustrative-vs-operative matching must be tuned to avoid false positives — the
  explicit #54/#46 foil. A token genuinely needed in an example is written inside a
  fence or flagged as illustrative.
- The check is the backstop for ADR-001's self-resolution: even if an agent's
  resolve step is correct, a body that still names a Python tool is caught here.
