# ADR F-2026-06-06-design-token-conformance-gate-002: a deterministic helper script + JSON contract mirroring review_gate.py, composing with /design as Layer 3

**Date:** 2026-06-06
**Status:** Accepted

**Context:**
The Layer-3 design-token conformance check needs to: parse `design-tokens.json`
into a normalized allowed-color set (tolerating the flat, nested, and W3C
`$value` token shapes), scan source files (or a directory with include globs) for
hardcoded color literals, decide which are violations, and report a verdict with
a clear blocking policy. This mechanical work could be an LLM judgment inside a
skill body, or a deterministic helper script. The build review gate (#60) faced
the analogous "skill orchestrates vs. helper does the mechanics" choice and
landed on a helper (`scripts/review_gate.py`) with a JSON contract and a clear
exit-code policy.

**Decision:**
A new `scripts/design_token_gate.py` helper owns all the mechanical work,
**mirroring `scripts/review_gate.py` exactly**: read-only, argv-list subprocess
only (never `shell=True`), a CLI with a subcommand, JSON output to stdout, a
clear exit-code contract, ~100% line+branch coverage, and no module-level mutable
globals (CQ-001 — `Final`/tuples/frozensets only).

CLI surface:
- `design_token_gate.py scan --tokens <design-tokens.json> (--files <f...> |
  --dir <d> [--include <glob,glob>]) [--strict] [--skip-design-token-gate
  "<reason>"]` → stdout JSON `{tokens_file, scanned_files, allowed_color_count,
  violations, verdict}` where `verdict ∈ {CLEAN, VIOLATIONS}`.
- Exit 0 = advisory default (even a `VIOLATIONS` verdict proceeds; also the
  non-empty `--skip-design-token-gate` path). Exit 2 = `--strict` AND violations.
  Exit 1 = usage error OR a missing/unreadable/empty/unparseable tokens file
  (never a false clean).

**Composition with /design (Layer 3):**
The gate is the deterministic Layer-3 enforcement of the AI-ready 3-layer design
system: Layer 1 `DESIGN.md` (narrative intent) → Layer 2 `design-tokens.json`
(machine-readable tokens) → **Layer 3** this gate (proof the code uses the
tokens). It rides the broad `scripts/` copy (`compile_scripts` copies every file
in `scripts/` into `dist/scripts/` — verified, NOT the narrowed-glob failure
mode), so it lands in an install with no per-script yaml entry. The `/design`
SKILL Phase 5 (Output) references it **briefly** as an advisory step the operator
MAY run after writing `design-tokens.json`; the policy lives in
`standards/process/design-token-conformance.md`, cited by path, NOT inlined (the
lessons-terminate-in-gates discipline). It is **not** forced into `/build`'s
blocking path in v1.

**Consequences:**
- *Easier:* deterministic, unit-testable mechanics isolated from any LLM call;
  consistent with `review_gate.py` and every other etc gate helper; the contract
  is a stable JSON shape a future `/build` step or a strict-mode adoption can
  consume without re-deriving the logic.
- *Harder:* one more helper to maintain and keep dist-mirrored (it rides the
  broad `scripts/` copy, like its siblings — verified, not the narrowed-glob
  failure mode). The skill references the helper rather than embedding the scan,
  keeping the skill body an orchestrator.
- The JSON contract + exit-code policy make a future expansion (more token
  categories per ADR-001, or a `/build` Layer-3 sub-step) an additive change, not
  a rewrite.
