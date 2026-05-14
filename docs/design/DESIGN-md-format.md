# DESIGN.md Format — etc adopts Google's official spec (F018)

This doc explains how etc's `/design` skill produces a canonical
`DESIGN.md` that conforms to Google Labs Code's
[official DESIGN.md format spec](https://github.com/google-labs-code/design.md)
(Apache 2.0, currently alpha).

If you're an operator running `/design`, you don't need to memorize any
of this — the skill handles it. This doc explains the WHY in case you
want to refine output by hand or integrate with downstream tools.

## What `/design` produces

Three files at your repo root after `/design` runs:

| File | What it is |
|------|------------|
| `PRODUCT.md` | impeccable's product-context capture (unchanged from F011) |
| `DESIGN-impeccable.md` | impeccable's freeform brand voice / aesthetic direction (intermediate) |
| `DESIGN.md` | the canonical Google-spec format — YAML frontmatter + canonical Markdown sections |

`DESIGN.md` is what AI coding agents read. `DESIGN-impeccable.md` is for
you to refine when you want richer prose to flow into the next
`/design --refresh` compose.

## Anatomy of a DESIGN.md

```markdown
---
version: alpha
name: Acme Platform
description: A workflow automation tool for small teams.
colors:
  primary: '#3b82f6'
  background: '#ffffff'
  text: '#0a0a0a'
typography:
  body:
    fontFamily: Inter
  heading:
    fontFamily: Source Serif Pro
spacing:
  '1': 4px
  '2': 8px
rounded:
  small: 4px
  large: 12px
---

# Acme Platform

## Overview
<brand voice + aesthetic direction from impeccable>

## Colors
<tokens defined above; reference via {colors.<name>}>

## Typography
<typography tokens; reference via {typography.<name>}>

## Do's and Don'ts
<anti-references from impeccable>
```

### YAML frontmatter

Required fields:
- `version` — currently `"alpha"` (matches Google's spec status)
- `name` — extracted from `PRODUCT.md`'s first h1

Optional fields:
- `description` — first non-empty paragraph after PRODUCT.md's h1
- `colors` — token map; values are hex (`#RRGGBB` or `#RGB`)
- `typography` — token map; each value is an object with `fontFamily`, optionally `fontSize`, `fontWeight`
- `spacing` — token scale (e.g., `'1': 4px`, `'2': 8px`)
- `rounded` — corner-radius scale
- `components` — component definitions referencing tokens (e.g., `backgroundColor: '{colors.primary}'`)

### Canonical Markdown sections

In Google's documented order (etc emits in this order; absent sections
are omitted):

1. `## Overview` — brand voice, aesthetic direction (impeccable's content)
2. `## Colors` — color token explanations
3. `## Typography` — typography token explanations
4. `## Layout` — layout system rationale (not auto-populated; refine via `/design --refresh`)
5. `## Elevation & Depth` — shadow system rationale
6. `## Shapes` — corner-radius rationale
7. `## Components` — component-level documentation
8. `## Do's and Don'ts` — anti-references (impeccable's content)

## Operator commands

After `/design` runs once, use these convenience commands:

```bash
/design --lint           # re-validate DESIGN.md against Google's spec
/design --refresh        # re-compose from DESIGN-impeccable.md + PRODUCT.md
/design --export tailwind     # write Tailwind v4 CSS from your tokens
/design --export json-tailwind # write Tailwind v3 JSON config
/design --export dtcg          # write W3C Design Tokens Format Module JSON
/design --spec           # print Google's format spec (useful for AI agent prompts)
```

All of these wrap `npx @google/design.md <command>`. If the package
isn't installed, install via:

```bash
npm install -g @google/design.md
```

The `install.sh` preflight surfaces this as an INFO message when the
package isn't detected.

## Why etc adopts Google's spec instead of staying with impeccable's freeform

Both formats use the same filename. Impeccable's freeform DESIGN.md
captures the WHY (brand voice, aesthetic direction, anti-references).
Google's spec captures the WHAT (specific tokens, structured sections,
component references). They're complementary, not competing.

etc's `/design` keeps impeccable's WHY-capture (it's the strongest
Socratic loop for non-technical SMEs) and adds Google's WHAT-emission
on top. Single canonical artifact, parseable by AI tooling, structurally
linted.

Future tooling (Tailwind plugins, design-system documentation
generators, AI agents trained on Google's schema) will pick up your
DESIGN.md without custom adapters.

## Token reference syntax

In `## Components` sections, reference tokens via braces:

```markdown
## Components

The `button` uses:
- backgroundColor: `{colors.primary}`
- textColor: `{colors.background}`
- borderRadius: `{rounded.small}`
- typography: `{typography.body}`
```

`@google/design.md lint` catches `broken-ref` errors (references to
undefined tokens). Fix by adding the token to YAML frontmatter or
correcting the reference.

## Linting and warnings

`npx @google/design.md lint DESIGN.md` runs seven rules:

| Rule | Severity | What it catches |
|------|----------|-----------------|
| `broken-ref` | error | `{colors.foo}` where `colors.foo` isn't defined |
| `missing-primary` | warning | no `primary` color defined |
| `contrast-ratio` | warning | component text/background below WCAG AA 4.5:1 |
| `orphaned-tokens` | warning | colors not referenced by any component |
| `token-summary` | info | per-section token count |
| `missing-sections` | info | absent optional sections |
| `missing-typography` | warning | no typography tokens |
| `section-order` | warning | sections out of canonical order |

etc's compose script aims to never emit errors. Warnings are surfaced
during `/design` Phase 4.5 — operator decides whether to refine.

## See also

- [Google Labs Code DESIGN.md spec](https://github.com/google-labs-code/design.md) — the authoritative format definition
- [`docs/design/example-DESIGN.md`](./example-DESIGN.md) — a canonical example
- F011 PRD: `spec/design-phase-wrapping-impeccable.md` — the impeccable wrap
- F018 PRD: `spec/adopt-google-design-md-spec.md` — this adoption
