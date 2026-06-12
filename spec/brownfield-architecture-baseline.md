# PRD: Brownfield Architecture Baseline — Discover → Verify → Ratify → Enforce

## Summary

When etc initializes an organically-grown brownfield codebase, it produces descriptive context (what exists) but no normative context (what new code must conform to). Agents then place code by inference from inconsistent precedent — and since every wrong placement has some sibling precedent, the agent confidently does the wrong thing. The covr PBJ build is the verified consequence (forensic workflow `wf_a4e993ba-0ce`, 2026-06-10): the repo *had* a layering doc (`docs/folder-structure.md`, Nov 2025), a team `AGENTS.md` pointing at it, and two golden-exemplar domains (`libs/people`, `libs/marketplace`) — but etc's init never discovered or wired any of them (grep: 0 hits across all tier-0 and build artifacts), etc's own generated DOMAIN.md was factually wrong about the system boundary (it called a React app "the legacy PHP scheduler" and never mentioned the second repo that owns every URL), and the conventions the team could articulate on demand existed nowhere in writing until a human authored them mid-crisis, two days before merge. The result: a 48-hour human cleanup scramble, a post-merge rework wave concentrated at 32–45% of the hottest files, and a team that partially lost confidence in the AI rollout.

This feature adds an **architecture-baseline phase** to `/init-project` for brownfield repos, built as a four-step loop. **DISCOVER** finds the repo's existing normative artifacts (convention docs, ADRs, lint/boundary configs, generators) and measures pattern consistency to rank golden-exemplar candidates and detect cross-repo seams. **VERIFY** treats every discovered doc as a claim, not a fact — weak-process teams have weak docs, so each load-bearing claim is checked against the tree and classified VERIFIED / STALE / ASPIRATIONAL / CONTRADICTED before anything enters agent context; etc's own generated artifacts get the same fact-check. **RATIFY** has a human bless the target: a golden-exemplar registry, do-not-copy markers, a repo-boundary map for multi-repo systems, and an architecture-confidence score — persisted as a tier-0 human doc plus a versioned machine-readable companion. **ENFORCE** turns the ratified baseline into machine-checked conformance (preferring the project's native fitness-function tooling, falling back to an F020-profile-generated checker) and ships a **rule-and-sweep skill**: mid-build, a human states a rule, the rule lands in the baseline, the AI sweeps the repo for violations and fixes them, and the rule joins the checker — the in-flight arm of lessons-terminate-in-gates, field-validated at covr.

The feature supports two entry shapes as first-class: single-repo (`/init-project` inside a repo) and **workspace mode** (`/init-project` in a directory containing N repos), which produces per-repo baselines plus one workspace-level cross-repo seam map — the artifact whose absence produced covr's "worked locally, broke in dev" failures. Until a human ratifies the baseline, `/build` hard-blocks on the repo and `/spec` warns loudly; ratification is never automated. This is Gap D of the PBJ retro family, completing the loop with Gap A (behavioral runtime gate), Gap B (contract completeness), and Gap C (prototype as intent).

## Scope

### In Scope

- **A new architecture-baseline phase in `/init-project`** (slotting between Phase 1 tech-scaffold and Phase 2 domain-scaffold per GA-001), running for brownfield repos; greenfield repos get a trivial baseline seeded from the scaffold itself.
- **DISCOVER:** find existing normative artifacts (convention/architecture docs, `AGENTS.md`/`CONTRIBUTING.md`, ADRs, lint/module-boundary configs, generators/templates); measure pattern consistency across modules implementing the same concern; rank golden-exemplar candidates; flag concerns with 2+ competing live patterns; **cross-repo seam detection** (env-var-loaded remote frontends, schemas/migrations for databases the repo does not serve, sibling-repo references, embed/loader shims).
- **VERIFY:** classify every load-bearing claim in discovered artifacts as `VERIFIED` / `STALE` / `ASPIRATIONAL` / `CONTRADICTED` with file-level evidence; only `VERIFIED` claims flow into agent context silently; everything else surfaces at ratification. **Self-check included:** etc's own generated artifacts (DOMAIN.md, PROJECT.md, `.meta/`) get the same fact-check on re-init.
- **RATIFY:** interactive human blessing producing (a) a golden-exemplar registry, (b) anti-pattern / do-not-copy markers, (c) a repo-boundary map when seams were detected, (d) an architecture-confidence score with documented inputs. Persisted as a tier-0 human doc + machine-readable companion under `.etc_sdlc/` with `schema_version` (GA-002), wired into the tier-0 read order and role manifests.
- **ENFORCE:** generate conformance rules into the project's native fitness-function tool where one exists, else a generated checker via the F020 profile mechanism (GA-003); the **rule-and-sweep skill** (GA-007: in scope) — rule capture mid-build → baseline append → repo-wide sweep-and-fix → rule joins the checker.
- **Unratified gating:** `/build` hard-blocks on a brownfield repo with an unratified baseline; `/spec` and `/architect` warn loudly with recorded override (GA-005), reusing the WARN + recorded-override machinery (GA-004).
- **Workspace mode:** `/init-project` from a directory containing N repos runs per-repo init + baseline for each, plus one workspace-level cross-repo seam map and workspace confidence score (GA-006).
- **Test fixtures** exercising the loop's logic (synthetic brownfield repos: stale-doc fixture, competing-patterns fixture, cross-repo-seam fixture, no-docs fixture), plus the pre-release acceptance run: roll covr back to its pre-init state and run `/init-project` against the real repos.
- **Compiler registration:** all new skills/standards/agents declared in `spec/etc_sdlc.yaml` (declared-vs-disk parity).

### Out of Scope

- **Authoring brand-new architecture for a chaotic repo.** Ratification surfaces undecided concerns as named decisions; designing the target architecture is the human's (or `/architect`'s) job.
- **The Backstage-style scaffolder/generator** (creating new modules FROM exemplars). The registry names exemplars; generating from them is a future feature.
- **CI pipeline wiring in the host project.** The checker is generated and runnable; adding it to the host's CI is a recommendation in init output, not an etc-performed change.
- **Gap A/B/C surfaces** — runtime verification, contract completeness, prototype handling are shipped siblings, not re-implemented here.
- **Retroactive cleanup of existing violations** (beyond what rule-and-sweep is explicitly invoked for). The baseline governs new code; paying down old debt is the host team's roadmap.
- **Auto-ratification.** No baseline is ever blessed without a human.

## Requirements

### BR-001: Baseline phase slots between init Phases 1 and 2
The architecture-baseline phase runs inside `/init-project` after Phase 1 (tech scaffold / `.meta/` survey via `project-bootstrapper`) and before Phase 2 (DOMAIN.md). It consumes Phase 1's survey output and never re-implements `project-bootstrapper` logic. It is invocable standalone via `--phase=baseline`, with the standard precondition check that Phase 1 artifacts exist.

### BR-002: Mode detection
On a brownfield repo, the full DISCOVER -> VERIFY -> RATIFY -> ENFORCE loop runs. On a greenfield repo, a trivial baseline is seeded from the scaffold itself (the scaffold IS the ratified pattern) with no verification pass. Mode detection reuses `project-bootstrapper`'s existing brownfield/greenfield determination.

### BR-003: DISCOVER — normative-artifact inventory
Discovery produces an inventory of candidate normative artifacts: convention/architecture docs (glob + content heuristics over `docs/**`, root-level `AGENTS.md`, `CONTRIBUTING.md`, `CLAUDE.md`-class files), ADR directories, lint/module-boundary configs, code generators/templates, and named reference implementations. Every inventory entry records its path, type, and last-modified date. An empty inventory is a valid result and is recorded as such.

### BR-004: DISCOVER — exemplar candidates and pattern-consistency measurement
Discovery measures pattern consistency across modules implementing the same concern (layering, naming, file placement) and produces: (a) a ranked list of golden-exemplar candidates with the evidence for each, and (b) a list of concerns where 2+ competing live patterns coexist, each with example paths per pattern. Ranking evidence cites real paths, never summaries alone.

### BR-005: DISCOVER — cross-repo seam detection
Discovery scans for signals that the analyzed repo is not the whole system: env-var-loaded remote frontends/services, schema or migration files for databases the repo does not serve, references to sibling repos in docs/config, and embed/loader shims. Any hit produces a seam record naming the signal and the implied external owner. Seam records cap the confidence score (BR-009) and require either the sibling repo's path or an explicit `boundary-unknown` acknowledgment at ratification.

### BR-006: VERIFY — claims, not facts
Every load-bearing claim in a discovered artifact is checked against the tree before it may enter agent context. Each claim is classified `VERIFIED` (code agrees, with file-level evidence), `STALE` (code moved on), `ASPIRATIONAL` (described pattern exists nowhere or only partially), or `CONTRADICTED` (code does the opposite). Only `VERIFIED` claims flow into tier-0 context silently; all other classifications surface at ratification. A discovered doc is never honored wholesale.

### BR-007: VERIFY — self-check of etc-generated artifacts
On re-init (or when etc tier-0 artifacts already exist), DOMAIN.md, PROJECT.md, and `.meta/` descriptions receive the same claim-verification pass as third-party docs. Factual errors (e.g., misidentified system components) are surfaced as `CONTRADICTED` findings at ratification — never silently retained.

### BR-008: RATIFY — human blessing is mandatory and interactive
Ratification is an interactive session (Pattern A/B per `standards/process/interactive-user-input.md`) in which a human confirms or amends: the golden-exemplar registry, anti-pattern/do-not-copy markers, the repo-boundary map (when seams exist), and the resolution of every non-`VERIFIED` claim and every competing-patterns concern (pick a winner, mark both acceptable, or record as an open decision). No baseline reaches `ratified` status without this session. Pre-drafted recommendations are allowed; auto-acceptance is not.

### BR-009: RATIFY — architecture-confidence score
The baseline records a confidence score with documented inputs: pattern-consistency measurements, count of competing-pattern concerns, claim-verification outcomes, stalled-migration signals, and seam records. Unresolved seams or a feature entry point resolving outside the analyzed repo cap the score at LOW. The score and its inputs are written to the machine-readable baseline and surfaced in the init completion report.

### BR-010: Baseline artifacts — human doc + versioned machine companion
The ratified baseline persists as (a) a human-readable tier-0 document wired into the tier-0 read order and role-manifest `default_consumes`, and (b) a machine-readable companion under `.etc_sdlc/` carrying `schema_version`, ratification status (`unratified` | `ratified`), ratified-by/at, the exemplar registry, do-not-copy markers, rules list, claim ledger, seam records, and the confidence score. Downstream consumers (gates, checker generation, rule-and-sweep) read only the machine file.

### BR-011: ENFORCE — native-tool-first conformance
Checker generation prefers configuring the project's existing fitness-function tooling (e.g., Nx module boundaries, dependency-cruiser, ESLint boundary plugins, ArchUnit) from the ratified rules. When no native tool covers a rule class, a standalone checker script is generated via the F020 profile mechanism (a `baseline-verify` sibling of `verify-green.sh`). The checker runs locally on demand and as part of etc's build gates; host-CI wiring is recommended in the completion report, not performed.

### BR-012: ENFORCE — rule-and-sweep skill
A new skill captures a human-stated rule mid-build, appends it to the baseline's rules list (with provenance: who, when, triggering incident), dispatches a repo-wide sweep that finds and fixes violations, and registers the rule with the conformance checker. The sweep reports files changed and violations remaining; partial sweeps are recorded, never silently dropped.

### BR-013: Unratified gating
On a brownfield repo whose machine baseline is missing or `unratified`, `/build` hard-blocks with a message naming the ratification command; `/spec` and `/architect` emit a loud UNRATIFIED warning and may proceed with a recorded override (non-empty reason, surfaced downstream). Gating reuses the existing hook + WARN/override machinery — no parallel mechanism.

### BR-014: Workspace mode
`/init-project` invoked in a directory containing N git repos (and not itself a repo root with source) offers workspace mode: per-repo init + baseline for each repo (each self-contained), plus exactly one workspace-level seam map recording cross-repo ownership of URLs/routing, auth/session, and data/schema, and a workspace-level confidence score. Seam detection findings from each repo feed the workspace map. A repo later used standalone retains a complete baseline.

### BR-015: Forward-only and idempotent
Already-initialized projects are never auto-mutated: re-running init on a repo with an existing baseline enters review mode (re-verify claims, surface drift, offer amendments) rather than regeneration. All writes follow `/init-project`'s existing idempotency rules — no silent overwrites.

### BR-016: Test fixtures + covr acceptance
Fixture repos exercise each loop mechanism: a stale-doc fixture (doc claims contradicted by code), a competing-patterns fixture, a cross-repo-seam fixture (two-repo workspace), and a no-docs fixture (empty inventory path). Contract tests pin the machine-baseline schema, the unratified gates, and checker generation. Before release, the acceptance run: roll covr-2.0/covr-legacy back to their pre-init state and run `/init-project` in workspace mode against the real repos, verifying it discovers `folder-structure.md`, flags the DOMAIN.md `apps/php` error class, surfaces `libs/people` as an exemplar candidate, and detects the legacy seam.

### BR-017: Compiler registration
Every new skill, standard, agent, and hook ships declared in `spec/etc_sdlc.yaml`; the declared-vs-disk parity gate passes. New standards (e.g., `standards/process/architecture-baseline.md`) are installer-swept including any non-`.md` companions.

## Acceptance Criteria

1. Running `/init-project` on a brownfield fixture repo executes the architecture-baseline phase after Phase 1 and before Phase 2; the completion report contains a baseline section with DISCOVER / VERIFY / RATIFY / ENFORCE sub-results. `--phase=baseline` runs it standalone and blocks with a clear message when Phase 1 artifacts are absent.
2. On the stale-doc fixture, discovery inventories the convention doc and the verify pass classifies its false claim `CONTRADICTED` with file-level evidence; the claim text does not appear in any tier-0 artifact or agent-context injection.
3. On the competing-patterns fixture, discovery reports the concern with 2+ live patterns including example paths per pattern, and ranks golden-exemplar candidates with cited real paths.
4. On the cross-repo-seam fixture, discovery emits a seam record naming the signal and the implied external owner, and the confidence score is capped at LOW until the seam is resolved (sibling path supplied or `boundary-unknown` acknowledged) at ratification.
5. On the no-docs fixture, discovery records an empty inventory as a valid result and ratification still produces a baseline from pattern measurement alone.
6. Self-check: on a fixture whose existing DOMAIN.md contains a deliberately false architectural claim, re-init surfaces it as `CONTRADICTED` at ratification; it is never silently retained.
7. Completing ratification writes the machine baseline (`schema_version: 1`, status `ratified`, ratified_by/at, exemplar registry, do-not-copy markers, rules list, claim ledger, seam records, confidence score) and the human tier-0 baseline doc, wired into the tier-0 read order and role-manifest `default_consumes`.
8. Aborting or skipping ratification leaves status `unratified`; `/build` against that repo hard-blocks with a message naming the ratification command.
9. `/spec` on an unratified brownfield repo emits a loud UNRATIFIED warning; proceeding records an override with a non-empty reason that surfaces downstream.
10. On a fixture with a native boundary tool, ratified rules are generated into that tool's config; on a fixture without one, a `baseline-verify` profile script is generated; running the checker against a deliberately violating file exits non-zero naming the violated rule.
11. Invoking rule-and-sweep with a stated rule appends it to the baseline rules list with provenance (who/when/trigger), sweeps the repo, fixes the planted violations, reports files-changed and violations-remaining, and the conformance checker subsequently flags new violations of that rule.
12. `/init-project` in a two-repo workspace fixture runs per-repo init + baseline for both repos and writes exactly one workspace-level seam map (URL/routing, auth/session, data/schema ownership) plus a workspace confidence score; each repo's baseline remains complete when the repo is used standalone.
13. Re-running init on a ratified repo with no drift writes zero files and reports "already present"; with planted drift, it enters review mode and surfaces the drift without auto-mutating.
14. The compile parity gate passes with every new skill, standard, agent, and hook declared in `spec/etc_sdlc.yaml`.
15. Pre-release acceptance: `/init-project` in workspace mode against the two real client repos rolled back to pre-init state (a) inventories and verifies the existing layering doc, (b) surfaces the known-good exemplar domain as a ranked candidate, (c) classifies the known-false tier-0 system-boundary claim class as `CONTRADICTED`, and (d) emits a seam record for the legacy embed/loader mechanism. (Run locally against client repos; results recorded anonymized.)

Sources in play: {code, spec, prototype}; conflicts resolved per source-of-truth-conflict-rule. Prototype references derived from client work MUST be anonymized — no client names, paths, or code in etc artifacts or fixtures.

## Edge Cases

1. **Empty inventory (no docs at all).** Discovery records the empty result; verification is a no-op; ratification proceeds from pattern measurement alone. A repo with no docs and no consistent patterns yields a LOW-confidence baseline whose ratification session consists mostly of open decisions — that is a valid, honest outcome, not an error.
2. **Discovered doc is entirely aspirational** (describes a target architecture nobody built). Every claim classifies `ASPIRATIONAL`; at ratification the human may adopt it as the target anyway — aspirational docs are legitimate ratification *input*, they just never enter context unlabeled.
3. **Conflicting normative docs** (two convention docs disagree). Both surface at ratification as a competing-claims pair; the human picks, and the loser gets a do-not-copy/superseded marker. Neither is honored silently.
4. **Monorepo vs. workspace ambiguity.** A directory containing multiple packages inside ONE git repo is a monorepo (single baseline); workspace mode triggers only on multiple git repos. A workspace containing one repo degrades to single-repo mode with a note.
5. **Seam detected but sibling repo unavailable.** Ratification requires the explicit `boundary-unknown` acknowledgment; the confidence score stays LOW and the baseline records the unresolved seam so `/spec` and `/architect` see it on every feature touching that surface.
6. **Ratification session abandoned midway.** Partial decisions persist with status `unratified`; re-running resumes from the recorded decisions rather than restarting. `/build` stays blocked.
7. **Operator overrides the UNRATIFIED warning on every feature.** Overrides accumulate visibly (each with its recorded reason) and are surfaced in `/metrics` — mass-override is never aggregated away. The hard `/build` block cannot be overridden by prose; it requires either ratification or an explicit `infrastructure_only`-style declaration in the baseline (e.g., a repo declared `baseline-exempt: docs-only repo`).
8. **Rule-and-sweep finds violations it cannot safely fix** (behavior-changing rewrites). The sweep fixes the mechanical subset, reports the remainder as a violations-remaining list with paths, and never force-fixes; the rule still joins the checker so new violations are caught.
9. **Native tool exists but cannot express a ratified rule** (e.g., naming conventions in a dependency-graph tool). Per-rule fallback: that rule goes to the generated checker while graph rules go to the native tool — the split is recorded in the baseline.
10. **Greenfield repo.** The trivial baseline is seeded from the scaffold (status `ratified` implicitly, since the human chose the scaffold); no verification pass, no gating friction on day one.
11. **Re-init after a real architecture migration** (the team legitimately changed direction). Review mode classifies old baseline claims against the new tree; mass `STALE` results prompt a re-ratification session rather than warning spam.
12. **Client-derived content.** Fixtures, generated templates, and any prototype-derived reference shapes must be anonymized — no client names, repo paths, or copied client code anywhere in etc artifacts. Contract test greps fixtures for known client identifiers.
13. **Giant repos.** Discovery's pattern measurement samples bounded sets per concern (it does not read the whole tree); the bound and its dropped-coverage note appear in the discovery report — silent truncation is not allowed.

## Technical Constraints

Intent-level constraints captured in Phase 1 and the gray-area session (architectural detail belongs to /architect):

- **Compose, never replace:** the baseline phase slots into the existing `/init-project` four-phase flow and delegates survey work to `project-bootstrapper` as-is (GA-001).
- **Forward-only:** already-initialized projects are never auto-mutated (BR-015).
- **Human ratification is mandatory** — no auto-blessing under any flag (BR-008).
- **Stack-agnostic:** checker generation and any per-stack logic ride the F020 profile mechanism; no language assumptions in the core loop (GA-003).
- **Reuse existing machinery:** WARN + recorded-override model and hook-based gating; no parallel enforcement mechanism (GA-004).
- **Artifact shape:** human tier-0 doc + versioned machine companion under `.etc_sdlc/`, mirroring profiles.lock and the contract-completeness producer-interface pattern (GA-002).

## Security Considerations

- **Free-form input sanitization:** all ratification-session and rule-and-sweep free-form inputs (rule text, decision rationales, owner names) strip control characters (`[\x00-\x1f\x7f]`) and are length-capped before persisting, matching the established /spec capture-site contract.
- **No automatic Read of operator-supplied paths:** sibling-repo paths supplied at seam resolution are recorded as strings; reads happen only through normally-hooked agent actions.
- **Client-information hygiene:** fixtures, templates, and prototype-derived reference shapes carry no client names, paths, or copied client code; a contract test greps fixtures for known client identifiers (Edge Case 12).
- **Generated checker safety:** generated checker scripts are read-only analyzers (exit codes + reports); they never modify the tree. Rule-and-sweep modifications go through the normal hooked Edit/Write path.

## Research Notes

- **Field evidence (primary):** 7-agent forensic workflow `wf_a4e993ba-0ce` (2026-06-10) over a two-repo client system. Key findings: existing normative doc + two golden exemplars undiscovered by init (grep 0 hits); etc-generated DOMAIN.md contained a CONTRADICTED-class system-boundary claim; 2-4 competing live patterns per backend concern; the human team produced a 422-line conventions doc + a bespoke pattern checker within 48 hours once violations were visible — proving rules are articulable on demand and enforcement is cheap once ratification exists; "worked locally, broke in dev" traced to undocumented cross-repo seams (stub-per-route, session-injection shell, shared DB).
- **Prior art:** architecture fitness functions (ArchUnit, dependency-cruiser, Nx module boundaries) are the established conformance layer — the gap is ratified rules as input, not tooling. Golden Paths (Spotify/Backstage) are the prior art for blessed exemplars. No established tool verifies doc claims against the tree — the VERIFY step is etc-novel.
- **Harness integration points:** `skills/init-project/SKILL.md` (phase ordering), `agents/project-bootstrapper.md` (survey output), `hooks/check-tier-0.sh` (read-order enforcement), `standards/code/profiles/` + `.etc_sdlc/profiles.lock` (F020), `standards/process/contract-completeness.md` (override model + versioned schema precedent), `spec/etc_sdlc.yaml` (declared-vs-disk parity).
- **Adjacent follow-ups surfaced by the same forensics (separate seeds, NOT this feature):** QA-findings-terminate-in-gates; env-parity as first-class input to the behavioral runtime gate; merge/PR-size discipline + harness-artifact containment; ceremony-decay floor; parallel human/AI scaffold-collision rule.
