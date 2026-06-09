# Design-Token Conformance — the Layer-3 Enforcement Gate

## Status: MANDATORY
## Applies to: /design (advisory output step), Backend/Frontend Developer

## The Problem

etc's `/design` phase already produces two of the three layers of an AI-ready
design system, but the third — enforcement — is missing:

| Layer | Artifact | Form | What it gives |
|---|---|---|---|
| **Layer 1 — Intent** | `DESIGN.md` | Narrative | The *why* and *what* of the design, in prose an agent reads as intent. |
| **Layer 2 — Tokens** | `design-tokens.json` | Machine-readable | The canonical, named design values (colors, spacing, typography) an agent and a build can resolve deterministically. |
| **Layer 3 — Conformance** | this gate | Deterministic check | Proof that the project's *code actually uses the tokens* instead of hardcoding design values. |

Without Layer 3, Layers 1–2 are a contract no one enforces. A project can ship a
design-tokens.json and then hardcode `#3b82f6` in fifty stylesheets — the tokens
become documentation, not a source of truth. This standard pins the Layer-3
gate: **declare the contract (the tokens), enforce it with a deterministic
gate** — the same gate-family as the build review gate
(`standards/process/build-review-gate.md`). A read-only helper script with a JSON
contract and a clear exit-code policy; not an LLM judgment call.

## v1 Scope (colors only, advisory by default)

v1 is deliberately tight (YAGNI — the deferrals are recorded as ADR decisions, so
a reviewer can accept or expand them):

- **Colors only.** The gate detects hardcoded **color** literals in source that
  are NOT defined in the project's `design-tokens.json`: hex (`#rgb`, `#rrggbb`,
  `#rrggbbaa`) and CSS color functions (`rgb()`/`rgba()`/`hsl()`/`hsla()`).
  Spacing, typography, and radii conformance are a **documented follow-up**, not
  v1 (see ADR-001).
- **Advisory by default.** The gate exits 0 even when violations exist. Only
  `--strict` turns a `VIOLATIONS` verdict into a non-zero (exit 2) blocking
  result. v1 **must not block any build** until the operator explicitly opts in —
  conservative by design (see ADR-001). A `--skip-design-token-gate <reason>`
  flag gives parity with the other release-gate skip flags: the reason is
  mandatory, non-empty, and logged verbatim.

## The Violation Definition

The gate parses `design-tokens.json` into a normalized set of allowed color
values, then scans the provided source for color literals. Normalization makes
equivalent spellings compare equal:

- Hex is **lowercased**, and 3-digit forms are **expanded to 6-digit**, so `#FFF`
  and `#ffffff` are the same allowed color.
- CSS color functions are lowercased with internal whitespace stripped, so
  `rgb(255, 0, 0)` and `rgb(255,0,0)` are the same allowed color.

A hardcoded color literal in source whose normalized value is **not** in the
allowed set is a **violation**, reported as `{file, line, value, kind: "color"}`.
The tokens file itself, and the `node_modules/`, `dist/`, `build/`, and `.git/`
trees, are always skipped (vendored/generated/VCS trees are never authored
source).

The token-file parser tolerates the common shapes: a flat `{name: value}` map,
nested groups, and the W3C design-tokens `{ "$value": "...", "$type": "color" }`
leaf shape. It recursively collects leaf strings that look like colors and
ignores non-color leaves (spacing, font names, numbers, booleans).

## The Contract (JSON + exit codes)

The gate is `scripts/design_token_gate.py`, a read-only helper that mirrors
`scripts/review_gate.py` (ADR-002):

```
design_token_gate.py scan --tokens <design-tokens.json>
    (--files <f...> | --dir <d> [--include <glob,glob>])
    [--strict] [--skip-design-token-gate "<reason>"]
```

stdout: `{tokens_file, scanned_files, allowed_color_count, violations, verdict}`
where `verdict ∈ {CLEAN, VIOLATIONS}`.

| Exit | Meaning |
|---|---|
| **0** | Advisory default — even a `VIOLATIONS` verdict does not block. Also the path under a non-empty `--skip-design-token-gate` reason (logged). |
| **2** | `--strict` AND violations present — the opt-in blocking path. |
| **1** | Usage error (no `--files`/`--dir`, empty skip reason) OR a missing/unreadable/empty/unparseable tokens file. A bad tokens file is **never** a false "clean". |

The default directory include globs are `*.css,*.scss,*.less,*.js,*.jsx,*.ts,*.tsx`.

## How it Composes with /design

This is **Layer 3** of `/design`. After Phase 5 writes `design-tokens.json`
(Layer 2), the operator MAY run `design_token_gate.py scan` over the project's
existing code to check Layer-3 conformance. In v1 this is **advisory** and lives
on the `/design` output side — it is **not** forced into `/build`'s blocking
path. The `/design` SKILL references it briefly; it does not inline the policy
(the lessons-terminate-in-gates discipline — the policy lives in this standard,
cited by path).

## Forward-Only

The gate is advisory from this feature's release tag onward. It does not block
any existing build, and there is no retroactive enforcement against
already-shipped projects. A blocking/strict default is deferred pending operator
confirmation (ADR-001).

## Lineage

- `docs/adrs/F-2026-06-06-design-token-conformance-gate-001-colors-advisory-v1-scope.md`
  — v1 = colors only, advisory by default; spacing/typography/radii + a
  blocking default deferred.
- `docs/adrs/F-2026-06-06-design-token-conformance-gate-002-helper-script-json-contract.md`
  — a deterministic helper + JSON contract mirroring `review_gate.py`; how it
  composes with `/design` as Layer 3.

## Cross-References

- `standards/process/build-review-gate.md` — the sibling "declare the contract,
  enforce with a deterministic gate" standard whose helper-script + JSON-contract
  shape this gate mirrors.
- `scripts/review_gate.py` — the proven helper template.
- `scripts/design_token_gate.py` — this gate's helper.
- `skills/design/SKILL.md` — the `/design` phase whose Phase 5 output references
  this gate as Layer 3 (advisory in v1), citing this standard by path.

**Origin:** tracker #69; the AI-ready 3-layer design-system pattern (DESIGN.md
narrative → design-tokens.json machine-readable → this conformance gate).
