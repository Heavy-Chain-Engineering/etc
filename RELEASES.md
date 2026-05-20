# Releases

Shipped features, newest first. Each entry is a finalized PRD with tests, audit trail, and verification report. Internal release tags follow `etc/release/<YYYY-MM-DD>` and the per-feature tag scheme `etc/feature/F<NNN>/{spec,architect/{start,done},build/phase-N/{start,done},release}`.

## F021 — TypeScript profile (2026-05-16)

The F020 proof case on a second language. `standards/code/profiles/typescript/` mirrors the python shape: `detection.yaml` (markers `package.json` + `tsconfig.json`; globs `*.ts`, `*.tsx`, `*.mts`, `*.cts`; excludes `node_modules`, `dist`, `build`, `.d.ts`), `README.md`, three rule-binding files citing [Google TypeScript Style Guide](https://google.github.io/styleguide/tsguide.html) + [typescript-eslint rules](https://typescript-eslint.io/rules/) + Airbnb JS, and gate scripts (`verify-green.sh` running `npm test` + `tsc --noEmit` + `eslint`; `check-test-exists.sh` requiring sibling `*.test.ts` / `*.spec.ts`). 9 integration tests against `tests/fixtures/typescript-repo/`. Closes the proof loop: the architecture works for any language with a community-canonical style guide + linter + test runner.

## F020 — Language-agnostic harness via profile architecture (2026-05-16, in progress)

Introduces a **profile** primitive at `standards/code/profiles/<profile>/` bundling detection markers, per-rule tool bindings, and per-gate executable scripts. `scripts/detect_profiles.py` walks marker files and writes `.etc_sdlc/profiles.lock`; `scripts/profile_loader.py` resolves file → profile via fnmatch; `scripts/dispatch_profile.sh` is the centralized dispatch helper. Monorepos activate every detected profile, scoped by file path. Files without a matching profile produce stderr WARN + exit 0 (no silent skip, no hard block). Six ADRs at `docs/adrs/F020-001..006`.

**Currently profile-aware:** `hooks/verify-green.sh`, `hooks/check-test-exists.sh`, `hooks/check-code-quality.sh`, and four profiles at `standards/code/profiles/{python,typescript,go,rust}/`. **Not yet:** two more hooks (`check-seam-evidence`, `check-completion-discipline`), tier-0 standards Python-vocabulary purge, three agent manifests, SessionStart staleness check, additional profiles (java, swift, terraform, markdown).

etc adopts community-canonical style guides ([Google styleguide](https://github.com/google/styleguide), [Kristories/awesome-guidelines](https://github.com/Kristories/awesome-guidelines), PEP 8, Airbnb, Rust API Guidelines, Effective Go) and never authors its own. Originating audit: `docs/audits/F020-language-coupling-audit.md`.

## F019 — Chief Efficiency Officer

Stop-hook reflection layer per Anthropic's large-codebase guidance. `chief-efficiency-officer.sh` captures every turn end to `.etc_sdlc/efficiency/turn-events.jsonl`, computes active engagement on the current task (sleep gaps > 5 min subtracted, env-tunable via `CEO_IDLE_THRESHOLD_MINUTES`), writes evidence-cited proposals to `.etc_sdlc/efficiency/proposals/`, and updates a rolling daily report at `.etc_sdlc/efficiency/daily/<YYYY-MM-DD>.md`. New PreToolUse hook `sandbox-bypass-tracker.sh` audits every `dangerouslyDisableSandbox: true` invocation. New `/efficiency` skill (`review`, `today`, `baseline`, `mute`). Evidence-based ONLY — every observation cites data points + baseline + gap; no hallucinated narrative.

## F018 — Google DESIGN.md spec

Adopts Google's official DESIGN.md spec (Apache 2.0, https://github.com/google-labs-code/design.md) as canonical `/design` output. Impeccable's freeform DESIGN.md → input; Google's spec (YAML frontmatter + canonical Markdown sections) → output. `scripts/design_md_compose.py` extracts hex colors with role-mapping, typography tokens, brand-voice prose, and anti-references. `npx @google/design.md lint` runs as best-effort validator. New operator commands: `/design --lint`, `/design --export {tailwind|css-tailwind|json-tailwind|dtcg}`, `/design --refresh`, `/design --spec`.

## F017 — `/journey` skill

SME-led customer-journey capture. 6 plain-English Socratic questions (plus 1 optional emotion question), saved to `docs/mvp/journeys/J-NNN-<slug>.md`. Pairs with `/spec` via `journey_refs:` in `state.yaml.spec_phase`. `/build` Step 7.4 fails on empty `journey_refs` unless `infrastructure_only: true`. Built for non-technical SMEs — forbidden vocabulary: "acceptance criteria", "stakeholder", "user story"; encouraged: "what they click", "where they get stuck", "how they feel". The intersection of journeys IS the MVP.

## F016 — Merge discipline at scale

Three carve-outs of the R2-R7 bundle. **R2 (cross-feature collision detection at wave-plan time):** `scripts/cross_feature_collision_check.py` scans every in-flight feature's `files_in_scope` and reports overlaps before /build executes. **R3 (Mergiraf preflight):** `install.sh` emits non-blocking INFO if Mergiraf isn't on PATH. **R7 (submission/merged schema):** `state.yaml.build.submission` + `state.yaml.build.merged` per the Stripe Minions distinction. Distinctive market position: no surveyed competitor ships cross-feature scanning.

## F015 — Spec→ADR coupling gate

`/build` Step 7.5. After `verification.md` and BEFORE the release tag, `scripts/spec_coupling_check.py` scans `spec.md` (and `design.md` if present) for scope-change markers anchored to AC/BR/ADR references. Each finding must be covered by a decision memo at `.etc_sdlc/features/{slug}/decisions/*.md` OR an ADR appendix. Uncovered → exit 2 BLOCKS release tag write.

## F014 — `/build --autonomous`

Wraps Anthropic's `/goal`. Derives a completion-condition from `state.yaml` + spec ACs, sets `/goal` at Step 2, then SKIPS confirmation gates at Steps 3 + 5. On Step 7 NON-COMPLIANT, `/goal`'s Haiku evaluator drives the remediation loop. `--max-turns N` (default 50, hard cap 200) bounds runaway. Closes the "30-40 confirmation prompts per day at team scale" friction.

## F013 — `install.sh` CLI UX + `--scope` flag

`--client {claude|antigravity}`, `--scope {global|project}`, `--help`. Backward compatible. Closes the "hooks bleeding cross-project" complaint by enabling per-project installs.

## F012 — Auto-checkpoint Stop hook

`hooks/auto-checkpoint.sh` blocks session-end (exit 2) when context ≥ 85% AND `.etc_sdlc/checkpoint.md` is > 30 min stale (or absent), forcing the model to checkpoint before stopping. Tunable via `CHECKPOINT_CTX_THRESHOLD` and `CHECKPOINT_STALE_MINUTES`.

## F011 — `/design` phase wraps impeccable

Adds Socratic design-context capture via `/impeccable teach`, conditional tier-0 promotion of PRODUCT.md + DESIGN.md, file-watch designer-iteration loop. Deprecates homeless `ux-designer` + `ui-designer` agents.

## F010 — Stacked PRs from `/build`

One squash-commit per wave on a layered branch chain via `gh-stack`. Soft warning at 500 LOC/layer. Single-wave builds skip stacking and ship as a single PR. Attacks the 4-hour-reconciliation pain at agentic-AI scale.

## F009 — Two-state directory lifecycle

`features/active/` and `features/shipped/`, plus separate `.etc_sdlc/rejections/`. Forward-only; existing flat-path features remain in place.

## F008 — Implicit-dependency rejection at wave-plan time

`/build` wave planner rejects implicit dependencies via file-set overlap detection.

## F007 — Stub-marker grep at verify time

spec-enforcer greps deliverables for stub markers (`TODO`, `FIXME`, etc.) before the release tag is written.

## F006 — `/spec` and `/architect` distinct phases

PMs can spec without writing architecture; architects can design without re-running intent capture. `/spec --include-architect` chains both.

## F005 — Per-phase completion reports

`/build` writes per-phase completion reports with AC pass/fail, deferred items, known gaps.

## F004 — Windows install + compile compatibility fixes

## F003 — Orphan-surface dispatch-time wiring contract

Third-layer defense in depth.

## F002 — spec-enforcer reachability evidence at verify time

Second-layer defense.

## F001 — User-flow completeness at spec time

First-layer defense in depth.
