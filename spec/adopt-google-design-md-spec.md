# F018 — Adopt Google's DESIGN.md spec (alongside F011 impeccable wrap)

**Status:** spec (review before /build)
**Author role:** Engineer (Jason / HCE)
**Date:** 2026-05-13
**Source:** Google Labs Code (https://github.com/google-labs-code/design.md, Apache 2.0, alpha)

## Problem

F011 ships a `/design` skill that wraps impeccable to produce two artifacts: `PRODUCT.md` (product context) and `DESIGN.md` (brand voice, aesthetic direction, anti-references). Impeccable's `DESIGN.md` is freeform prose — it captures the WHY of a design system but isn't structurally parseable by AI agents or design tooling.

In 2026-04, Google Labs Code shipped an official **DESIGN.md format specification** at https://github.com/google-labs-code/design.md (Apache 2.0, alpha). It defines:

- **YAML frontmatter** with strict schema: `version`, `name`, `description`, `colors`, `typography`, `rounded`, `spacing`, `components` — all with documented token shapes and reference syntax (`{colors.primary}`)
- **Canonical Markdown sections** in fixed order: Overview, Colors, Typography, Layout, Elevation & Depth, Shapes, Components, Do's and Don'ts
- **CLI tooling** (`@google/design.md` npm package) with `lint` (7 rules), `diff` (regression detection), `export` (Tailwind v3/v4 + W3C DTCG), `spec` (format documentation)
- **Programmatic library** for parsing + validation

Two `DESIGN.md` files with the same name now exist in the wild — impeccable's freeform version and Google's structured spec. Operators reading either are going to be confused. AI agents that have been trained on Google's spec won't recognize impeccable's freeform output.

## Solution

Adopt Google's `DESIGN.md` spec as etc's canonical `/design` output format. Impeccable's freeform output becomes the **input** to a transform; the **artifact** that ships is a Google-spec DESIGN.md.

### Conceptual marriage

Impeccable captures the **WHY**: brand voice, aesthetic direction, anti-references, do's and don'ts. Google's spec separates that WHY (Markdown prose) from the **WHAT** (YAML frontmatter tokens). The two are complementary:

| Impeccable output | Goes into Google's DESIGN.md |
|-------------------|-------------------------------|
| Brand voice + aesthetic direction (freeform prose) | Markdown `## Overview` + `## Do's and Don'ts` sections |
| Anti-references (freeform prose) | Markdown `## Do's and Don'ts` (the "Don'ts" half) |
| Specific color choices (when impeccable elicits them) | YAML `colors:` token map |
| Typography choices | YAML `typography:` token map |
| Spacing / rounding / layout decisions | YAML `spacing:`, `rounded:`, plus Markdown `## Layout` |
| Component definitions | YAML `components:` map + Markdown `## Components` |

### Pipeline

`/design` Phase 5 (the write-artifacts phase) is augmented:

1. **Today (F011):** Impeccable writes its freeform `PRODUCT.md` + `DESIGN.md` to the repo root. /design captures `state.yaml.design_phase.impeccable_version_pinned` + `tier_0_promoted` + `completed_at`.

2. **F018 addition:** After impeccable writes, /design invokes `scripts/design_md_compose.py <impeccable_DESIGN.md> <product.md> --out DESIGN.md` which:
   - Parses impeccable's freeform DESIGN.md for token-shaped content
   - Reads PRODUCT.md for `name` + `description` frontmatter fields
   - Emits a Google-spec-conformant DESIGN.md (YAML frontmatter + canonical sections in order)
   - Validates the result via `npx @google/design.md lint`
   - On lint errors: surface findings; offer Pattern A retry path
   - On lint warnings: surface findings; proceed

3. **The freeform impeccable DESIGN.md** is preserved as `DESIGN-impeccable.md` (intermediate artifact). The user-facing canonical artifact is `DESIGN.md` in Google's format.

### Operator-facing commands

`/design --lint` — runs `npx @google/design.md lint DESIGN.md` against the current root DESIGN.md and surfaces findings.

`/design --export <format>` — runs `npx @google/design.md export --format <format> DESIGN.md` for `tailwind`, `css-tailwind`, `json-tailwind`, or `dtcg`.

`/design --spec` — prints Google's format spec (useful for AI agent prompts).

`/design --refresh` — re-runs the compose step from impeccable's freeform output (e.g., after refining impeccable artifacts manually).

## Acceptance Criteria

- **AC-01:** `scripts/design_md_compose.py` exists. CLI: `python3 design_md_compose.py <impeccable_design_md_path> <product_md_path> --out <output_path>`. Exit codes 0 (success), 1 (usage / IO error), 2 (compose failed — surface stderr).
- **AC-02:** Compose output passes `npx @google/design.md lint` with zero ERRORS (warnings + info are allowed). The compose script invokes the linter as a final validation step and exits non-zero if lint reports errors.
- **AC-03:** YAML frontmatter includes the required fields: `name` (from PRODUCT.md), `version: "alpha"` (until Google's spec hits 1.0), `description` (from PRODUCT.md if present).
- **AC-04:** YAML frontmatter `colors`, `typography`, `spacing`, `rounded` maps are populated when impeccable's freeform DESIGN.md mentions specific values; otherwise omitted (Google's spec allows absent maps).
- **AC-05:** Canonical Markdown sections are present in correct order: `## Overview`, `## Colors`, `## Typography`, `## Layout`, `## Elevation & Depth`, `## Shapes`, `## Components`, `## Do's and Don'ts`. Sections without content are omitted entirely (per Google's `missing-sections` rule — info, not error).
- **AC-06:** Impeccable's freeform DESIGN.md is preserved at `DESIGN-impeccable.md` (NOT overwritten). The user-facing `DESIGN.md` is the Google-spec output.
- **AC-07:** `skills/design/SKILL.md` Phase 5 documents the compose step. The dispatch sequence is: impeccable writes → compose → lint → finalize → write to repo root.
- **AC-08:** `install.sh` preflight INFO for `@google/design.md`. Pattern matches the F010 / F011 / F016 preflight INFOs — non-blocking, INFO-only:
  ```
  INFO: @google/design.md not detected. /design phase output (etc F018+) validates against Google's DESIGN.md spec. Install via: npm install -g @google/design.md (or use npx). Features without /design work without it.
  ```
- **AC-09:** `tier-0-design-preflight.sh` hook updated: when `state.yaml.design_phase.tier_0_promoted == true` AND DESIGN.md is present at repo root, the hook ALSO checks that DESIGN.md begins with `---` (frontmatter delimiter). Absent or malformed frontmatter → block (exit 2) with a message pointing at `/design --refresh`.
- **AC-10:** `/design --lint`, `/design --export <format>`, `/design --refresh`, `/design --spec` modes documented in SKILL.md.
- **AC-11:** `docs/design/DESIGN-md-format.md` — etc-side operator explainer doc: what the spec is, why we adopted it, how it relates to impeccable's PRODUCT.md, how `/design --refresh` works, how the YAML schema maps to common design-system concepts. Link to Google's repo for authoritative spec.
- **AC-12:** `docs/design/example-DESIGN.md` — an anonymized canonical example. Single, complete, lint-clean DESIGN.md showing the full schema with realistic token names. Sourced/adapted from Google's `/examples` directory or written fresh.
- **AC-13:** `tests/test_design_md_compose.py` — 12+ contract tests covering: AC-01 (CLI shape), AC-03 (required frontmatter fields), AC-05 (canonical section order), AC-06 (impeccable original preserved), and the compose's lint-on-output behavior. Uses pytest tmp_path + fixture impeccable artifacts.
- **AC-14:** `tests/test_design_skill_md_lint.py` — grep tests confirming SKILL.md documents the compose step, the lint invocation, and the --lint/--export/--refresh modes. Plus a content test confirming SKILL.md mentions Google's spec by URL.
- **AC-15:** `tests/test_install_sh_google_designmd_preflight.py` — grep tests for the new preflight INFO line + non-blocking behavior.
- **AC-16:** README.md updated: F018 row in shipping table + brief mention of DESIGN.md adoption in the /design skill description. Test count updated.
- **AC-17:** `spec/etc_sdlc.yaml` registration unchanged (skill name `design` already exists from F011; F018 doesn't add a new skill, just extends `/design`'s Phase 5).
- **AC-18:** `spec/adopt-google-design-md-spec.md` — PRD copy per F009 convention.

## Out of Scope (deferred to follow-ups)

- **Real-time DESIGN.md preview in the browser extension.** F011's file-watch contract handles designer-iteration via JSON deltas; F018 doesn't extend that to live DESIGN.md preview.
- **DESIGN.md versioning semantics.** Google's spec is alpha; v1.0 may introduce version-pinning conventions. F018 writes `version: "alpha"` and lets v2 handle proper semver.
- **Component-spec ↔ DESIGN.md round-trip.** F011's `component-specs.md` doesn't yet flow into DESIGN.md's `components:` map. Manual mapping for now; auto-flow is its own feature.
- **`@google/design.md` library API integration.** F018 invokes the CLI (`npx @google/design.md lint`); a future feature could import the TypeScript library for richer error reporting.
- **Multi-engagement DESIGN.md namespacing.** Single DESIGN.md per repo (single-engagement assumption from F017 carries over).
- **Tailwind / DTCG export round-trip.** F018 surfaces `--export` as a passthrough; doesn't validate or store the exported artifacts.
- **Auto-migration of existing freeform DESIGN.md.** Operators with F011-era DESIGN.md files run `/design --refresh` to produce the Google-spec version. No automatic batch migration.

## Technical Notes

- **`@google/design.md`** is currently alpha. The compose script pins `version: "alpha"` in frontmatter to align. When Google's spec hits 1.0, update the pin via `state.yaml.design_phase.google_designmd_version_pinned` (mirroring F011's `impeccable_version_pinned` convention).
- **The compose script is Python** (consistent with etc's other scripts/*.py) but invokes the linter via subprocess to `npx`. No node-side wrapper.
- **Lint rules** the compose targets (per Google's spec):
  - `broken-ref` (error): every `{colors.primary}` reference resolves to a defined token
  - `missing-primary` (warning): warn if `colors.primary` absent
  - `contrast-ratio` (warning): WCAG AA 4.5:1 for component text/background pairs
  - `orphaned-tokens` (warning): every color is referenced by at least one component
  - `section-order` (warning): canonical section order enforced
- **Backward compatibility:** F011 features filed BEFORE F018 ships keep their freeform DESIGN.md. F018's gate (AC-09 tier-0-preflight) only fires when DESIGN.md exists AT all — F011 features that didn't trigger conditional tier-0 stay unchanged.
- **License compatibility:** Google's `@google/design.md` is Apache 2.0; etc is private commercial. CLI invocation via npx is fine; no source bundling.

## Resolved Design Decisions

These got resolved during /spec rather than as open questions:

1. **Single DESIGN.md output (Google's spec).** Impeccable's freeform output is preserved as `DESIGN-impeccable.md` (intermediate). The repo-root `DESIGN.md` is canonical-spec format. Operators read one file, AI agents parse one schema.
2. **Compose runs on every /design invocation.** Not opt-in. /design's Phase 5 always emits the Google-spec DESIGN.md (assuming `@google/design.md` is available; otherwise SKILL.md falls back to a stub message recommending operator install).
3. **Lint errors block; warnings inform.** Errors fail Phase 5 with a Pattern A retry path. Warnings print and proceed. Info-level findings appear in verification.md.
4. **No auto-migration of legacy F011 DESIGN.md.** Operators with existing freeform DESIGN.md files run `/design --refresh` to produce the Google-spec version. The legacy file is preserved at `DESIGN-impeccable.md` automatically by the compose script.
5. **Hook update is conservative.** `tier-0-design-preflight.sh` only checks that DESIGN.md has frontmatter present (the `---` delimiter); the linter is invoked at compose-time, not at every edit. Operator-facing hook stays fast.

## Risks

1. **Google's spec is alpha — breaking changes are possible.** Mitigation: pin `version: "alpha"` and lint against the operator-installed `@google/design.md` version. If Google ships a breaking change, /design's lint surfaces it and operators rerun `/design --refresh`.
2. **`@google/design.md` install via npm fails for offline operators.** Mitigation: SKILL.md compose step is conditionally skipped when the CLI is absent. /design still produces impeccable's freeform output; the Google-spec DESIGN.md is generated when the CLI is available.
3. **Impeccable's freeform output may not contain enough token specificity.** Mitigation: when the compose can't extract a token, it omits the YAML field rather than fabricating. Lint surfaces missing primary color as a warning, operator decides whether to refine via `/design --refresh`.
4. **`@google/design.md` adds a Node.js dependency to etc.** Mitigation: SKILL.md flags this as a soft dependency. The compose script falls back gracefully when npx is absent. Operators on Node-free environments use F011's freeform DESIGN.md.

## Dependencies

- **`@google/design.md`** npm package (Apache 2.0, alpha). Install: `npm install -g @google/design.md` or run via `npx @google/design.md`.
- **Node.js** (for the CLI). Most operator machines already have it for impeccable (F011); F018 doesn't add a new toolchain.
- **PyYAML** for the compose script (already required by etc).
- **No other new third-party deps.**

## Sequencing

- **F018 (this PRD)**: compose pipeline + install.sh preflight + hook update + docs + tests.
- **F-TBD (deferred follow-up)**: `/design --export` to Tailwind / DTCG with stored artifacts under `dist/design-tokens/`.
- **F-TBD (deferred follow-up)**: component-specs.md ↔ DESIGN.md components map round-trip.
- **F-TBD (deferred follow-up)**: file-watch contract extended to live DESIGN.md preview in impeccable's browser extension.

## Source

- Google Labs Code DESIGN.md spec: https://github.com/google-labs-code/design.md (Apache 2.0, alpha)
- F011 spec: spec/design-phase-wrapping-impeccable.md (impeccable wrap)
- Operator direction 2026-05-13: "Google has an official DESIGN.md spec now. I'd like to adopt and follow that."
- Spec written 2026-05-13; ready for /build review.
