---
version: alpha
name: Example Project
description: A canonical example showing the full DESIGN.md schema with realistic token names.
colors:
  primary: '#3b82f6'
  accent: '#f59e0b'
  background: '#ffffff'
  surface: '#f5f5f5'
  text: '#0a0a0a'
  muted: '#6b7280'
typography:
  body:
    fontFamily: Inter
    fontSize: 16px
  heading:
    fontFamily: Source Serif Pro
    fontSize: 24px
    fontWeight: '600'
  mono:
    fontFamily: Fira Code
    fontSize: 14px
spacing:
  '1': 4px
  '2': 8px
  '3': 12px
  '4': 16px
  '6': 24px
  '8': 32px
rounded:
  small: 4px
  medium: 8px
  large: 12px
components:
  button:
    backgroundColor: '{colors.primary}'
    textColor: '{colors.background}'
    typography: '{typography.body}'
    rounded: '{rounded.small}'
  card:
    backgroundColor: '{colors.surface}'
    textColor: '{colors.text}'
    rounded: '{rounded.medium}'
---

# Example Project

This example illustrates a complete, lint-clean DESIGN.md following
Google's spec. Use it as a reference when manually refining your own
DESIGN.md or as a prompt for AI agents that need to understand the
schema.

## Overview

A clean, minimalist visual identity built for clarity and trust. The
brand voice is confident but not loud — like a trusted advisor, not a
salesperson. Colors are restrained, with a single bold primary that
anchors action surfaces. Typography pairs a humanist sans-serif for
body copy with a transitional serif for editorial moments.

The design system prioritizes readability over decoration. Whitespace
is generous; visual hierarchy is established through type weight and
size, not color or ornament.

## Colors

Color tokens are defined in the YAML frontmatter above. Reference via
`{colors.<name>}` syntax in component definitions.

- `primary`: action surfaces (buttons, links, focus indicators)
- `accent`: highlight states and secondary CTAs
- `background`: page surface
- `surface`: card/panel surface, slightly off-white for separation
- `text`: body copy and headings
- `muted`: secondary text, metadata, captions

## Typography

Typography tokens defined in YAML frontmatter. Reference via
`{typography.<name>}`.

- `body`: Inter at 16px for paragraph copy
- `heading`: Source Serif Pro at 24px / 600 weight for section
  titles and h1-h2
- `mono`: Fira Code at 14px for code, addresses, IDs

## Layout

Spacing scale follows a 4px baseline. Use the `{spacing.N}` tokens
rather than raw pixel values for vertical rhythm and horizontal
padding. Layouts target a max-width of 1200px for content surfaces.

## Elevation & Depth

Surfaces use rounded corners (`{rounded.<scale>}`) rather than shadows
to establish hierarchy. When shadows are necessary, they're soft and
short-distance — never dramatic.

## Shapes

All corner radii pull from the `rounded` token scale. Avoid mixing
arbitrary radii — pick a token, use it consistently.

## Components

The `button` component:
- backgroundColor: `{colors.primary}`
- textColor: `{colors.background}`
- typography: `{typography.body}`
- rounded: `{rounded.small}`

The `card` component:
- backgroundColor: `{colors.surface}`
- textColor: `{colors.text}`
- rounded: `{rounded.medium}`

## Do's and Don'ts

**Do:**
- Use `{colors.primary}` only on interactive surfaces (buttons, links).
- Pair `body` typography with `heading` for editorial pages.
- Keep accent color usage to <10% of any given surface.

**Don't:**
- Don't add new colors to the system without updating this file.
- Don't use saturated reds — they conflict with the calm brand voice.
- Don't combine `mono` with `heading` typography (visual mismatch).
- Don't introduce hard shadows; depth is established through `rounded`
  and surface color, not light.
