# ADR F-2026-06-06-design-token-conformance-gate-001: v1 is colors-only and advisory; spacing/typography/radii + a blocking default are deferred

**Date:** 2026-06-06
**Status:** Accepted

**Context:**
etc's `/design` phase ships `DESIGN.md` (Layer 1, narrative intent) and
`design-tokens.json` (Layer 2, machine-readable tokens), but has no Layer-3
enforcement that a project's code actually uses the tokens instead of hardcoding
design values. A conformance gate could enforce every token category (colors,
spacing, typography, radii, motion, breakpoints) and could block builds by
default. Doing all of that at once would be a large, noisy surface introduced
before any operator has tuned it against a real project — exactly the cry-wolf /
dead-gate failure mode etc guards against, where an over-eager gate trains the
operator to reach for the override on routine noise.

**Decision:**
v1 is deliberately scoped (YAGNI), with the deferrals recorded here so a reviewer
can accept or expand them:

1. **Colors only.** The gate detects hardcoded color literals (hex
   `#rgb`/`#rrggbb`/`#rrggbbaa` and CSS `rgb()`/`rgba()`/`hsl()`/`hsla()`) not
   defined in `design-tokens.json`. Spacing, typography, and radii conformance
   are a **documented follow-up**, not v1. Colors are the highest-signal,
   lowest-ambiguity category (a hex literal is unambiguously a color; `16px`
   could be spacing, a font size, or a border width), so they are the right
   first slice to prove the gate-shape on.
2. **Advisory by default.** The gate exits 0 even when violations exist; only
   `--strict` makes a `VIOLATIONS` verdict exit non-zero (exit 2). v1 must NOT
   block any build until the operator explicitly opts in. A blocking/strict
   **default** is **deferred pending operator confirmation** — promoting it is a
   one-line default change once the gate has earned trust on real projects.
3. **A missing/unreadable/empty/unparseable tokens file is a hard error (exit
   1), never a false "clean".** The conservative choice: an unreadable contract
   is an error to surface, not a silent pass.

**Consequences:**
- *Easier:* a small, high-signal surface the operator can adopt without noise;
  the advisory default means zero risk of blocking an existing build on day one;
  the deferred categories and the blocking default are explicit, reviewable
  decisions rather than silent omissions.
- *Harder:* spacing/typography/radii conformance and a blocking default require
  follow-up work; until then a project can still hardcode non-color design
  values. This is an accepted, documented v1 limitation, not an oversight.
- A reviewer may **override** either deferral: expand the category set, or flip
  the default to blocking, by accepting the corresponding follow-up. The
  conservative defaults are chosen precisely so that expanding them is a
  deliberate, reviewed act.
