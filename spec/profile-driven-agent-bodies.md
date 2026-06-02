# PRD: Profile-Driven Agent Bodies — Stack-Correct Review/Dev/Verify

## Summary

ETC's `code-reviewer`, `backend-developer`, `security-reviewer`, and `verifier`
agents are templated for Python/FastAPI and silently no-op on any other stack. On
a TypeScript/NestJS/React monorepo they ran and surfaced ~0 actionable findings;
the issues they should have caught (controller-layering violations, unsafe ID
generation, a multi-tenant scope leak, a data-retention leak) escaped to a human
reviewer and CodeQL at PR time — roughly two developer-days, recurring on every
non-Python project.

The root cause is two unbuilt links, not one. F022 added the `${profiles}` /
`${profile_bindings_template}` *placeholders* to three manifest headers but
explicitly deferred the dispatch-time resolver to a follow-up PRD that was never
built — so the per-profile bindings never actually reach the agent (the
placeholders are inert literal strings). And independently, the agents' concrete
heuristics *in the body* (`Glob test_*.py`, `grep @router.get`, `uv run pytest`)
were never de-Pythonized. This feature owns both links: build the resolver so the
active-profile bindings inject, and make the four bodies profile-neutral so they
search by the injected conventions — plus a conformance check so a manifest body
can never silently re-hardcode to *any* language. The crucial discipline (per the
field report): fixing Python-hardcoding by adding TypeScript-hardcoding is the
same bug relocated.

Out of band: `/build` never dispatches the review agents at all (only
spec-enforcer) — that firing-point gap is tracked separately (#60) and is not in
this feature.

Source: harness-feedback (covr-2.0 PR #3072, 2026-06-01) + the verified root-cause
research in `research/codebase.md`.

## Scope

### In Scope
- **Manifest placeholder resolver** (the deferred F022 follow-up): at agent
  dispatch, resolve `${profiles}` and `${profile_bindings_template}` from the
  active profile set so the correct per-profile bindings reach the agent.
- **Profile-neutral bodies** for `code-reviewer`, `backend-developer`,
  `security-reviewer`, `verifier`: concrete heuristics reference the project's
  configured test/lint/typecheck commands and active-profile conventions (via the
  injected bindings), never a named language tool/path.
- **Convention adoption**: bring `security-reviewer` (and the remaining `verifier`
  defaults) fully into the `${profiles}` / `${profile_bindings_template}`
  convention.
- **Body-conformance check**: fail any profile-aware manifest whose body names a
  language-specific operative tool/path outside a bindings reference — extends
  `standards/process/agent-manifest-profile-awareness.md` from header-only to
  body-level.

### Out of Scope
- Build-time *dispatch* of the review agents in `/build` Step 7 (#60 — separate
  feature). This feature makes the agents stack-correct *when dispatched*; giving
  them an automatic firing point in the pipeline is its own work.
- New per-language profiles (python/typescript/go/rust already exist as the
  substrate).
- **Re-hardcoding to TypeScript or any single stack** (explicit anti-pattern, not
  a solution).

## Requirements

### BR-001: Placeholder resolution
At agent dispatch, `${profiles}` and `${profile_bindings_template}` in a
profile-aware manifest resolve from the active profile set (`profiles.lock`) so
the matching per-profile bindings reach the agent; no literal placeholder string
leaks into the agent's effective context.

### BR-002: Profile-neutral bodies
The four agents' body heuristics reference the project's configured commands +
active-profile conventions (sourced from the injected bindings), never named
`pytest`/`ruff`/`mypy`/`@router.`/`src/`/`pip audit`/`pyproject` as operative
instructions.

### BR-003: Convention adoption
`security-reviewer` and `verifier` carry the `${profiles}` +
`${profile_bindings_template}` convention; `verifier`'s existing stack-detection
is preserved/reconciled, not duplicated.

### BR-004: No re-hardcoding
Substituting one language's tokens for another's is non-conformant; bodies must be
profile-driven.

### BR-005: Body-conformance check
A check fails any profile-aware manifest whose body names a language-specific
operative tool/path outside a bindings reference, and passes the four conformed
manifests. It extends `agent-manifest-profile-awareness.md` from header-only to
body-level.

### BR-006: Forward-only
Legacy manifests not in the convention and not modified are byte-unchanged; the
four named agents are brought into conformance here.

### BR-007: Stack-correct outcome
On a non-Python project the four agents reference the project's real toolchain and
surface stack-correct findings rather than ~0.

## Acceptance Criteria

1. With `typescript` active in `profiles.lock`, the dispatched `code-reviewer`'s
   effective required-reading contains the typescript bindings — not the literal
   `${profile_bindings_template}` string.
2. With no profile active, the placeholders resolve to the top-level/empty form:
   no crash, no literal placeholder leak, the agent runs on top-level rules.
3. The bodies of all four agents contain no hardcoded language tool/path token
   (`pytest`, `ruff`, `mypy`, `@router.`, `src/`, `pip audit`, `pyproject`) used
   as an operative instruction outside a bindings reference.
4. `security-reviewer` and `verifier` carry the `${profiles}` +
   `${profile_bindings_template}` convention in frontmatter + required_reading.
5. The body-conformance check fails a manifest whose body names a
   language-specific operative tool outside a bindings reference, and passes the
   four conformed manifests.
6. On a TypeScript/Nest fixture project, each of the four agents references the
   project's configured commands (jest/vitest, eslint, tsc) via the injected
   bindings, not pytest/ruff/mypy.
7. On that fixture, a seeded defect of a class each agent owns (e.g. a
   controller-layering smell; an unsafe `Math.random()` ID) is surfaced — not
   zero findings.
8. Forward-only: a legacy manifest not in the convention and not modified this
   feature is byte-unchanged.

## Edge Cases

1. `profiles.lock` absent/stale → resolution degrades to top-level rules with a
   warning; the agent still runs; no literal placeholder leaks.
2. Polyglot monorepo (multiple active profiles) → bindings for every active
   profile inject.
3. A body that names a tool *illustratively* (an example) vs. as an operative
   instruction → the conformance check must not over-fire on bindings-referenced
   or clearly-illustrative mentions (the #54/#46 over-fire family is the foil).
4. `verifier` already partly stack-detecting → its detection is
   reconciled/preserved, not duplicated or fought.
5. Unsupported stack (no matching profile) → agents fall back to profile-neutral
   generic heuristics + a stated limitation, never Python-by-default.

## Research Notes

- Profile detection + loader exist and are tested (`detect_profiles.py`,
  `profile_loader.py`, `dispatch_profile.sh`, `check-profiles-fresh.sh`); the
  verify-green/quality-gate path is genuinely profile-aware.
- `standards/process/agent-manifest-profile-awareness.md` (F022) defines the
  manifest placeholder convention and explicitly defers the dispatch-time resolver
  to "a follow-up PRD" — that follow-up was never built (no resolver in
  scripts/skills/hooks; `profile_loader.py` has no manifest-render API; the three
  header-aware agents carry inert literal placeholders and do not self-resolve).
- Hardcoding sites: `code-reviewer.md` (`tests/**/test_*.py`, `@router.get`,
  `src/`), `backend-developer.md` (`uv run pytest`, `src/`, "Tech Stack: FastAPI"),
  `security-reviewer.md` (`@router.`, `pip audit`, `pyproject` — not in the
  convention), `verifier.md` (least broken — already detects pytest vs
  jest/vitest, some Python defaults remain).
- Companion #60: `/build` Step 7 dispatches only spec-enforcer — no review-agent
  firing point (separate feature).
- The resolver's exact dispatch integration point and the body-rewrite approach
  are architecture decisions deferred to `/architect`.
- No `INVARIANTS.md`, no `.etc_sdlc/antipatterns.md` present.
