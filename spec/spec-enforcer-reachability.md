# PRD: spec-enforcer Reachability Evidence for User-Facing Acceptance Criteria

## Summary

The `spec-enforcer` agent is the harness's verify-time gate: `/build` Step 7 dispatches it via the Agent tool against every PRD's deliverable, and a `NON_COMPLIANT` verdict blocks the release tag and `release-notes.md` from being written. The agent assumes non-compliance until proven otherwise and cites file:line evidence for every per-AC verdict it emits. But its evidence model is structurally blind to one specific failure mode that F001-user-flow-completeness (Layer 1) just specced for: an acceptance criterion that names a user-facing surface (a route, modal, wizard step, or sidebar entry) can be marked `SATISFIED` when the only evidence is a unit test that imports the target component directly with vitest and asserts the contract. The component compiles, the contract test passes, but the navigation path that's supposed to lead a real user to the surface is never wired up. F4 capability-entitlements shipped 7 such orphan surfaces past a verified-COMPLIANT spec-enforcer pass; the user found them all in under 60 seconds of real app use.

This PRD adds a verify-time guardrail to spec-enforcer that closes the loop on F001's spec-time guardrail. When an AC carries a User-flow sentence in the canonical form `"As {role}, navigate from {parent route} via {affordance label}, complete {happy path}, observe {outcome}."`, the agent must additionally verify reachability — i.e., that the navigation path the AC describes actually exists in the deliverable. The agent accepts three evidence forms, in order of preference: (1) **E2E test** — a Playwright/Cypress/equivalent test that navigates from `{parent route}`, clicks the affordance matching `{affordance label}`, completes `{happy path}`, and asserts `{outcome}`; (2) **static nav-graph reference** — a single grep proof showing the `{affordance label}` or `{parent route}` substring appears in a parent file outside the AC's own component dir (signaling a real `<Link>`, sidebar entry, or tab definition); (3) **manual reachability proof** — a screencap, screen recording, or operator-attested log entry naming the artifact path, an ISO8601 timestamp, and a free-form operator name recorded verbatim. A unit test that imports the component directly is necessary but not sufficient for any AC bearing a User-flow sentence. The agent marks the AC `NOT_SATISFIED` if zero evidence forms are found and `INSUFFICIENT_EVIDENCE` if an attempted form was inconclusive — the existing fail-closed pipeline behavior treats both as `NON_COMPLIANT` and blocks the release.

This PRD is **layer 2 of a three-layer defense in depth**. Layer 1 (F001 — done) closed the spec-time hole by requiring User-flow sentences in user-facing ACs at AC authorship. Layer 3 (the `docs/agent-prompt-template.md` "Wiring is part of the deliverable" clause + `/build` Step 6 wiring pre-validation) closes the dispatch-time hole and is a separate sibling PRD. This PRD's intervention is the verify-time half of the contract: F001 wrote the User-flow sentence into the AC; F002 makes spec-enforcer treat that sentence as a reachability obligation rather than free-form narrative. Together with Layer 3, the F4-class orphan-surface defect cannot recur — it would have to evade three independent gates to ship.

## Scope

### In Scope
- Append a new `## Reachability Evidence` section to `standards/process/user-flow-completeness.md` (the existing F001 doc) defining the three-tier evidence taxonomy (E2E, static nav-graph reference, manual reachability proof), the per-tier evidence-format contract, the loose-substring static-reference grep rule (per GA-003), the free-form manual-attestation contract (per GA-004), and the trigger condition (only ACs with a User-flow sentence — per GA-002).
- Edits to `agents/spec-enforcer.md` to:
  - Add a User-flow-sentence detection step in the per-AC evaluation flow (regex: AC begins with or contains the canonical `As {role}, navigate from` prefix).
  - Add the reachability-evidence check for every detected user-facing AC.
  - Bump the hard tool budget from 12 → 16 calls (per GA-006), share envelope across reachability checks.
  - Document the loose-substring static-reference grep rule, the manual-proof free-form attestation contract, and the verdict mapping (NOT_SATISFIED for zero evidence; INSUFFICIENT_EVIDENCE for attempted-but-inconclusive; preserves existing fail-closed pipeline behavior).
  - Cite the new standards-doc section by path.
  - Preserve all existing JSON output schema fields and verdict states (COMPLIANT / NON_COMPLIANT / INSUFFICIENT_EVIDENCE / BLOCKED) — no breaking changes.
- Edits to `skills/build/SKILL.md` Step 7's spec-enforcer dispatch prompt to declare that User-flow sentences mean reachability evidence is required and to point at the new standards-doc section by path.
- A new contract test file `tests/test_spec_enforcer_reachability.py` with grep-based assertions over `dist/agents/spec-enforcer.md`, the appended standards-doc section, and the updated `dist/skills/build/SKILL.md` Step 7 dispatcher prompt.
- Compile pipeline integration via existing `python3 compile-sdlc.py spec/etc_sdlc.yaml` — the recursive copy already ships edited agents, skills, and standards. No compiler edits.
- Forward-only behavior: legacy ACs without a User-flow sentence pass through unchanged (per GA-002 + F001 BR-007).

### Out of Scope
- **Layer 1 (F001 — done).** AC authorship gate. The User-flow sentence already exists; this PRD verifies it.
- **Layer 3 (sibling PRD).** `docs/agent-prompt-template.md` "Wiring is part of the deliverable" clause + `/build` Step 6 wiring pre-validation. That layer catches agents shipping orphan surfaces at dispatch time.
- **`SpecComplianceRule` guardrail at `platform/src/etc_platform/guardrails.py:554`.** This is v2 platform code not currently exercised by the harness; aligning the guardrail to the new evidence taxonomy is a future PRD.
- **Backfill of legacy ACs.** Forward-only per GA-002. Legacy ACs without a User-flow sentence pass through spec-enforcer's existing evaluation unchanged.
- **Retroactive scanning of past spec-enforcer reports.** Per the Layer 1 forward-only convention, no re-evaluation of historical verdicts.
- **Automated CI-evidence harvesting.** spec-enforcer reads what's in the deliverable; it does not call CI APIs to fetch test-run artifacts. Out of scope; future PRD if useful.
- **Automatic E2E-test discovery.** spec-enforcer searches the deliverable for E2E tests via the same grep budget as everything else; it does not invoke a separate test-discovery agent or static analyzer.
- **Changes to spec-enforcer's output JSON shape.** The existing schema (`scope`, `prd_path`, `deliverable`, `totals`, `violations`, `satisfied`, `not_applicable`, `insufficient_evidence`, `verdict`, `blocking_acs`, `budget_exhausted`, `notes`) is preserved verbatim. Reachability metadata fits into the existing `evidence` string field per AC.
- **Changes to `/build` Step 7 dispatcher logic beyond the prompt text.** The Agent-tool dispatch shape, the post-dispatch result handling, the release-tag/release-notes-on-COMPLIANT-only rule — all unchanged.
- **Changes to other agents.** verifier, code-reviewer, security-reviewer, architect-reviewer, technical-writer, etc. are unchanged.
- **Changes to the User-flow sentence form itself.** The canonical form, the signal lists, the conflict-default rule — all unchanged from F001.
- **Tier reorganization of `standards/`.** New content lands as an appended section to the existing F001 doc; no new directories.

## Requirements

### BR-001: Reachability Evidence Section in user-flow-completeness.md
A new section MUST be appended to `standards/process/user-flow-completeness.md` (the existing F001 doc) titled `## Reachability Evidence` (or equivalent header reflecting the same concept). The section MUST define:

- The trigger: an AC carries a User-flow sentence (canonical prefix `As {role}, navigate from`) — this is the only condition that activates the reachability check.
- The three evidence forms in preference order:
  1. **E2E test (preferred)** — a test file that programmatically navigates from `{parent route}`, interacts with `{affordance label}`, completes `{happy path}`, and asserts `{outcome}`. Acceptable frameworks include Playwright, Cypress, or any equivalent (the standard documents the contract; framework choice is the AC's deliverable team's decision).
  2. **Static nav-graph reference** — a single grep finds the `{affordance label}` substring or the `{parent route}` substring in any file outside the AC's own component dir. The grep is loose by design (per GA-003): false positives are acceptable because spec-enforcer records the file:line of the match for human review.
  3. **Manual reachability proof** — a screencap, screen recording, or operator-attested log entry naming the artifact path, an ISO8601 timestamp, and a free-form operator name (per GA-004). spec-enforcer records the operator name verbatim and trusts it; audit accountability lives in the evidence record, not in a runtime identity gate.
- The verdict mapping: NOT_SATISFIED when zero evidence forms are found; INSUFFICIENT_EVIDENCE when an attempted form was inconclusive (e.g., grep found a match but the file:line context is ambiguous, or a manual proof has missing metadata).
- A scope note: the rule applies only to ACs with a User-flow sentence per F001; legacy ACs and backend-only ACs pass through unchanged.

### BR-002: User-Flow Sentence Detection in spec-enforcer
`agents/spec-enforcer.md` MUST gain an explicit per-AC detection step that recognizes the canonical User-flow sentence prefix `As {role}, navigate from` (or any sentence beginning with `As ` and containing the literal `, navigate from `). Detected ACs trigger the reachability check; non-detected ACs follow the existing per-AC evaluation flow unchanged.

### BR-003: Three-Tier Reachability Evidence Check
For each detected user-facing AC, `agents/spec-enforcer.md` MUST attempt to find evidence in this order, stopping at the first form found:

1. **E2E test grep.** A grep for the `{parent route}` literal in deliverable test files (paths matching `*test*` or `*spec*` extensions outside vitest unit-test paths) AND for the `{affordance label}` substring in the same hit set. Hit = SATISFIED with `evidence: <test_file_path>: <quoted line>`.
2. **Static nav-graph reference grep.** A grep for `{affordance label}` or `{parent route}` substring in any file outside the AC's own component dir. Hit = SATISFIED with `evidence: <file_path>:<line>: <quoted match>`.
3. **Manual reachability proof.** Look for an explicit `surface_status: reachable_manual` or `manual_reachability_proof` record in the deliverable (the AC body, the spec.md Edge Cases section, or a sibling proof artifact). Found = SATISFIED with `evidence: <artifact_path> @ <ISO8601> by <operator_name>` recorded verbatim.

Zero forms found → NOT_SATISFIED with `evidence: "no reachability evidence: AC carries User-flow sentence but no E2E test, static reference, or manual proof was found"`. Attempted-but-inconclusive (e.g., E2E test grep found a partial match, no static reference, no manual proof) → INSUFFICIENT_EVIDENCE per the existing schema.

### BR-004: Tool Budget Bump
`agents/spec-enforcer.md` MUST raise the hard tool budget from 12 to 16 calls total (per GA-006). The per-tool sub-budgets MUST be updated proportionally — proposed: Read 8, Grep 8, Glob 4, Bash 2, Total 16 — though the exact per-tool split may be tuned in implementation as long as the total cap is 16. Reachability checks share the existing envelope; no separate sub-budget. Budget exhaustion before all user-facing ACs check → INSUFFICIENT_EVIDENCE for unchecked ACs (existing fail-closed rule).

### BR-005: Spec-Enforcer Cites the Standards-Doc Section
`agents/spec-enforcer.md` MUST reference `standards/process/user-flow-completeness.md` (specifically the new Reachability Evidence section) by path in the per-AC evaluation step. The agent MUST NOT duplicate the evidence taxonomy inline; the standards doc is the single source of truth.

### BR-006: /build Dispatcher Prompt Update
`skills/build/SKILL.md` Step 7's spec-enforcer dispatch prompt MUST be updated to:

- Declare that ACs containing User-flow sentences require reachability evidence per `standards/process/user-flow-completeness.md`.
- Cite the new standards-doc section by path.
- Preserve the existing dispatch shape (Agent-tool call with `subagent_type: "spec-enforcer"`, the spec-path argument, the COMPLIANT/NON-COMPLIANT result handling, the release-tag/release-notes gating).

### BR-007: JSON Schema Preservation
The spec-enforcer JSON output schema MUST be preserved verbatim. No new top-level fields, no renamed fields, no removed fields. Reachability evidence fits into the existing per-AC `evidence` string field (the field is already free-form text). Verdict states remain COMPLIANT / NON_COMPLIANT / INSUFFICIENT_EVIDENCE / BLOCKED. The pipeline downstream of spec-enforcer (release-tag and release-notes gating in /build Step 7) is unchanged.

### BR-008: Contract Test Coverage
A new test file `tests/test_spec_enforcer_reachability.py` MUST exist and pass, containing at minimum:

- `test_standard_doc_has_reachability_section` — confirms `standards/process/user-flow-completeness.md` contains a `## Reachability Evidence` section (or equivalent) and the three evidence-form names verbatim.
- `test_standard_doc_documents_evidence_forms` — greps the standards doc for E2E, static-reference, and manual-proof contract language including the `{affordance label}` / `{parent route}` references and the loose-substring rule.
- `test_agent_documents_user_flow_sentence_detection` — greps `dist/agents/spec-enforcer.md` for the canonical-prefix detection logic (`As ` + `, navigate from`).
- `test_agent_documents_three_evidence_forms` — greps the compiled agent for the three evidence-form check steps in the prescribed order.
- `test_agent_budget_is_16` — greps the compiled agent for the bumped budget total of 16 (and confirms no surviving "12 across all tools" string).
- `test_agent_cites_standards_doc` — greps the compiled agent for `standards/process/user-flow-completeness.md` by path.
- `test_build_dispatcher_cites_standards_doc` — greps `dist/skills/build/SKILL.md` Step 7 for the standards-doc path and the reachability-evidence requirement language.
- `test_agent_preserves_existing_json_schema` — confirms the schema lines (top-level fields, verdict states) in the compiled agent are byte-equivalent to the existing schema.

### BR-009: Compile Pipeline Integration
`python3 compile-sdlc.py spec/etc_sdlc.yaml` MUST complete without error after the standards-doc, agent, and skill edits. The compiled `dist/agents/spec-enforcer.md`, `dist/skills/build/SKILL.md`, and `dist/standards/process/user-flow-completeness.md` MUST be byte-identical to their sources. No edits to `compile-sdlc.py` itself are required.

### BR-010: Forward-Only Behavior
The reachability check fires only on ACs containing a User-flow sentence (per GA-002). Legacy specs whose ACs predate F001 — and ACs explicitly marked `surface_status: backend_only` per F001 — pass through spec-enforcer's existing per-AC evaluation flow unchanged. The PRD adds no validator, scanner, or skill step that retroactively flags legacy specs in `.etc_sdlc/features/*/spec.md`.

## Acceptance Criteria

1. `standards/process/user-flow-completeness.md` contains a new `## Reachability Evidence` section appended after the existing F001 content, naming all three evidence forms (E2E test, static nav-graph reference, manual reachability proof) verbatim, and stating the trigger condition (User-flow sentence presence).
2. The Reachability Evidence section documents the three evidence forms in preference order (E2E first, static-reference second, manual third) and specifies, for each, the per-form contract: file-path-and-line evidence shape for forms 1 and 2; artifact-path + ISO8601 + free-form operator name for form 3.
3. The Reachability Evidence section explicitly documents the loose-substring static-reference rule (per GA-003): a single grep finds `{affordance label}` OR `{parent route}` substring in any file outside the AC's own component dir, and false positives are acceptable because the agent records the file:line for human review.
4. The Reachability Evidence section explicitly documents the free-form manual-attestation contract (per GA-004): operator name accepted as any string and recorded verbatim by spec-enforcer; no harness-identity gate.
5. The Reachability Evidence section documents the verdict mapping: zero evidence forms found → NOT_SATISFIED; attempted-but-inconclusive → INSUFFICIENT_EVIDENCE; both states preserve the existing fail-closed pipeline behavior.
6. `agents/spec-enforcer.md` contains a per-AC detection step that recognizes the User-flow sentence prefix (`As ` + `, navigate from`) and triggers the reachability check only on detected ACs.
7. `agents/spec-enforcer.md` documents the three-tier reachability evidence check in BR-003's prescribed order (E2E test grep → static nav-graph reference grep → manual reachability proof record), with the agent stopping at the first form found.
8. `agents/spec-enforcer.md` declares a hard tool budget total of 16 calls (up from 12), with the budget table updated to show new per-tool caps. The literal string "16 across all tools" (or equivalent) appears verbatim; the prior "12 across all tools" string does not survive.
9. `agents/spec-enforcer.md` references `standards/process/user-flow-completeness.md` by path in the per-AC reachability check step. The signal lists and evidence-form contracts are NOT duplicated inline in the agent body.
10. `agents/spec-enforcer.md` JSON schema (top-level fields and verdict-state enum) is preserved verbatim from the pre-edit version. No top-level fields added, removed, or renamed. Verdict states remain `COMPLIANT | NON_COMPLIANT | INSUFFICIENT_EVIDENCE | BLOCKED`.
11. `skills/build/SKILL.md` Step 7 spec-enforcer dispatch prompt is updated to reference the new Reachability Evidence section by path and to declare that User-flow sentences require reachability evidence per the standard. The Agent-tool dispatch shape, the post-dispatch result handling, and the release-tag/release-notes-on-COMPLIANT-only rule are unchanged.
12. The PRD adds no validator, scanner, or skill step that retroactively scans `.etc_sdlc/features/*/spec.md` for User-flow / reachability compliance. Legacy specs and ACs marked `surface_status: backend_only` pass through spec-enforcer's existing per-AC evaluation unchanged. Verified by absence of a retroactive scanner in the changed-file set.
13. A new test file `tests/test_spec_enforcer_reachability.py` exists and contains at minimum the eight tests enumerated in BR-008. Running `pytest tests/test_spec_enforcer_reachability.py -q` reports all tests passing.
14. `python3 compile-sdlc.py spec/etc_sdlc.yaml` completes without error after the agent, standards-doc, and dispatcher-prompt edits. The compiled `dist/agents/spec-enforcer.md`, `dist/standards/process/user-flow-completeness.md`, and `dist/skills/build/SKILL.md` are byte-identical to their sources.
15. Existing tests in the repository continue to pass after the changes. Running `pytest tests/ -q` reports no new failures introduced by this refactor (regression baseline).
16. spec-enforcer's behavior on a legacy AC (no User-flow sentence) is unchanged: the agent evaluates such ACs through its existing per-AC flow with no reachability check fired. Verified by a contract-test scenario in `tests/test_spec_enforcer_reachability.py` that exercises a legacy-style AC fixture (the test asserts the agent's documentation states this fall-through behavior; no live spec-enforcer dispatch in the test).

## Edge Cases

1. **AC has User-flow sentence but `{parent route}` and `{affordance label}` are placeholders not literal text** — the AC author left literal `{role}` or `{parent route}` strings in the AC. spec-enforcer's grep will look for `{parent route}` literally and find nothing. The agent must fall through to manual proof and likely return NOT_SATISFIED with evidence "User-flow sentence contains unfilled placeholder slot — verify the AC has been instantiated with concrete role/route/affordance values." This catches a class of drafting errors that F001 does not enforce at spec-time.
2. **Multiple user-facing ACs share an E2E test** — one Playwright spec covers ACs 12, 13, and 14 (all user-facing for the same wizard). spec-enforcer's per-AC grep fires three times against the same file. Acceptable: each AC's grep records the file:line independently; the budget cost is 3 greps. If budget pressure hits in a large PRD, BR-004's INSUFFICIENT_EVIDENCE rule applies.
3. **Static-reference grep matches a comment, not a wiring** — `// TODO: link from /admin/orgs to wizard` matches the static-reference rule. spec-enforcer records the file:line and returns SATISFIED. False-positive risk acknowledged in the standards doc per GA-003. Mitigation is human review of the recorded evidence; a future PRD could tighten the rule.
4. **Manual proof artifact path doesn't exist** — the AC names a screencap at `proofs/wizard-reach-2026-04-30.mp4` but the file is missing from the deliverable. spec-enforcer marks the AC INSUFFICIENT_EVIDENCE with evidence "manual proof artifact path provided but file not found." Pipeline treats as NON_COMPLIANT.
5. **AC has User-flow sentence but no surface to verify** — sentence reads `As a system operator, navigate from /api/health via the curl command...` (CLI/API "navigation"). The standards doc's scope note (from F001) explicitly excludes CLI/API surfaces; spec-enforcer should treat this as a configuration error in the AC, falling through to NOT_SATISFIED with evidence "User-flow sentence is for non-web/app surface — out of scope per `standards/process/user-flow-completeness.md` scope note."
6. **Multiple parent routes for one surface** — F001's User-flow sentence form covers one path. spec-enforcer's grep tests for the named `{parent route}` and `{affordance label}`. If the deliverable wires the surface from a different parent (e.g., AC says "from `/orgs`" but deliverable wires from `/admin/orgs`), spec-enforcer records the mismatch. Author can refine the AC's User-flow sentence to match the deliverable wiring, or update the deliverable to match the AC.
7. **Legacy AC resumed under the new rule** — a pre-F001 AC has no User-flow sentence; spec-enforcer's detection step skips the reachability check for that AC (per BR-010). Legacy-AC fall-through is verified by AC16. No false-positive triggering of the reachability check on legacy ACs.
8. **Tool budget exhausts on a 25-AC PRD** — the bumped 16-call total still isn't enough for a PRD with many user-facing ACs. spec-enforcer marks the unchecked ACs INSUFFICIENT_EVIDENCE per BR-004. Pipeline treats the verdict as NON_COMPLIANT, which is correct fail-closed behavior. Operator can decompose the PRD into smaller sub-PRDs (Layer 1's Phase 2.75 classifier already encourages this) or the agent's budget can be tuned in a follow-up PRD.
9. **AC author manually wrote a User-flow sentence on an AC that's actually backend-only** — say a webhook AC begins "As a webhook subscriber, navigate from..." in a misuse of the form. spec-enforcer's grep looks for the literal `{parent route}` string and returns NOT_SATISFIED for absence. The author corrects the AC during the next /spec resume by either rewriting the sentence or marking the AC `surface_status: backend_only`.
10. **Compile pipeline fails after edits** — `compile-sdlc.py` is required to succeed (AC14). If it fails, source and dist/ are out of sync — the dist agent would not have the new detection logic, and the rule would silently not fire in installed harnesses. Treat as P0 blocker; the PR cannot merge until compile passes.
11. **spec-enforcer encounters a circular Read on its own evidence files** — the agent reading `agents/spec-enforcer.md` (its own definition) during evaluation. This was already possible pre-PRD; the bumped budget makes it slightly more permissive. Acceptable risk; the existing anti-loop discipline (no exploratory reads, one Read per AC) covers it.
12. **Manual proof with truncated or malformed timestamp** — operator provides `2026-04-30` (no time component) or `4/30/26` (wrong format). spec-enforcer is permissive in recording; downstream auditors see what was provided. The standards doc states ISO8601 is preferred but doesn't enforce it via the agent (out of scope; future PRD if tightening is needed).
13. **Standards-doc section header drifts from what spec-enforcer cites** — spec-enforcer cites `standards/process/user-flow-completeness.md` by path but does not cite a specific section anchor. If a future edit moves the Reachability Evidence section content elsewhere in the file, the citation still resolves but downstream readers may need to scroll. Acceptable: section structure is governed by the doc itself; spec-enforcer just needs the file path.

## Technical Constraints

- **File touchpoints (small, surgical):** the refactor edits three existing files (`agents/spec-enforcer.md`, `skills/build/SKILL.md`, `standards/process/user-flow-completeness.md`) and creates one new file (`tests/test_spec_enforcer_reachability.py`). No Python source changes outside the new test file. No edits to `compile-sdlc.py`, `feature_id.py`, `git_tags.py`, `value_hypothesis.py`, or any other script under `scripts/`.
- **Compile pipeline:** `python3 compile-sdlc.py spec/etc_sdlc.yaml` already recursively copies `agents/<name>.md` → `dist/agents/<name>.md`, `standards/<name>/` → `dist/standards/<name>/`, and `skills/<name>/` → `dist/skills/<name>/`. Running the compiler after the edits ships all three modified files without compiler code changes.
- **Agent definition format:** `agents/spec-enforcer.md` has YAML frontmatter (`name`, `description`, `tools`, `model`, `disallowedTools`, `maxTurns`) followed by Markdown body. The frontmatter SHOULD remain unchanged in this PRD; only the body sections receive edits. Specifically, the `Tool Budget (Hard Limit)` section's table (currently lines 38-46) gets bumped totals; the `Process` section (currently lines 63-79) gains the User-flow sentence detection step and the three-tier evidence check.
- **JSON schema preservation as a hard contract:** the schema lines 85-132 in `agents/spec-enforcer.md` MUST remain verbatim. AC10 enforces this. The reachability evidence flows into the existing per-AC `evidence` string field; no new fields are introduced. Downstream consumers (`/build` Step 7's release-tag/release-notes-on-COMPLIANT-only rule, any future programmatic parsers of the agent's output) MUST continue to work without modification.
- **Single source of truth for the rule:** `standards/process/user-flow-completeness.md` is authoritative. The agent body and the /build dispatcher prompt reference the doc by path and MUST NOT duplicate the evidence-form contracts inline. Doc-first updates keep the three places in sync (per F001's Technical Constraint precedent).
- **Pattern A / Pattern B compliance:** this PRD adds NO new user-facing prompts. spec-enforcer is an adversarial verifier; /build Step 7 is a programmatic dispatcher. There are no Pattern-A `AskUserQuestion` calls or Pattern-B visual markers added by this PRD. (The /spec process used Pattern A and Pattern B during this session, but that's the spec-authoring lane, not the spec-enforcer agent's behavior.)
- **Backward compatibility:**
  - The existing eight-section spec-enforcer body order (Response Format, Tool Budget, Before Starting, Process, Output Format, Boundaries, Coordination) is unchanged. New content lands as additions to existing sections, not new top-level sections.
  - The existing JSON schema is preserved verbatim per AC10.
  - The existing verdict states (COMPLIANT / NON_COMPLIANT / INSUFFICIENT_EVIDENCE / BLOCKED) are unchanged.
  - The /build Step 7 dispatch contract (Agent-tool call shape, post-dispatch result handling, release-tag gating) is unchanged.
- **Forward-only application:** the rule applies only to ACs containing a User-flow sentence. The PRD adds no validator, scanner, or hook that retroactively flags legacy specs in `.etc_sdlc/features/*/spec.md`. spec-enforcer's existing per-AC evaluation flow is the fallback for legacy ACs (per BR-010).
- **Test precedent:** contract tests follow `tests/test_user_flow_completeness.py` (the F001 contract test) and `tests/test_init_project.py::TestSkillMdContract` — grep-based assertions over the compiled `dist/agents/spec-enforcer.md`, `dist/skills/build/SKILL.md`, and `dist/standards/process/user-flow-completeness.md`. Same compile-fixture pattern (autouse session-scoped fixture invoking `compile-sdlc.py`) with the explicit module-level `_ = _compile_sdlc` reference workaround for Pyright's "is not accessed" hint. No fixture-PRD interactive testing — the contract tests verify agent *content*, not agent *behavior*.
- **Tool budget interaction:** the bumped 12→16 budget MUST be reflected in the agent body's table verbatim (AC8). Per-tool sub-budgets are tunable but the total cap is 16. The bump is documented as motivated by reachability checks; future tuning is a follow-up PRD if needed.
- **F001 dependency:** this PRD assumes F001 has shipped (the User-flow sentence form, the standards doc, the Phase 3/4 /spec edits are all live). If F001 is reverted, this PRD's reachability check would still fire on any AC matching the canonical-prefix pattern, but no PRD authored after F001's revert would carry such sentences — degrading gracefully to no-op.
- **Missing infrastructure:** `INVARIANTS.md` and `.etc_sdlc/antipatterns.md` do not exist in this repo. Both reads are conditional per /spec's "Before Starting"; absence is recorded in research notes, not blocked on.
- **Scope boundary marker:** Layer 3 sibling PRD owns dispatch-time wiring enforcement. This PRD's Module Structure enumerates only Layer 2 files; Layer 3 files (`docs/agent-prompt-template.md`, `/build` Step 6 wiring pre-validation) are out of scope.

## Security Considerations

This feature does not handle authentication, user input validation at system boundaries, data storage, file uploads, external APIs, or authorization. It is a documentation refactor of an agent definition and a skill body, plus an appended section to an existing standards doc, plus a new contract test. None of the auto-populate categories from the /spec security table apply directly. The security-relevant considerations are:

- **Manual reachability proof's free-form operator name is recorded verbatim into the spec-enforcer JSON output.** The downstream consumer is /build Step 7 and any post-build auditor reading `release-notes.md` or the spec-enforcer's stdout. Pattern: same as F001's "Other" sanitization contract — strip control characters (regex `[\x00-\x1f\x7f]`) and cap the operator-name string at 64 characters before recording. The agent body MUST document this. Mitigates log-injection and CSV-injection attacks against downstream auditing tools that may parse the JSON output.
- **Manual reachability proof's artifact path is recorded verbatim and not opened by spec-enforcer.** Critical: spec-enforcer MUST NOT `Read` the artifact file (no automatic `Read <artifact_path>`). This prevents a hostile AC from pointing the agent at `/etc/passwd`, `~/.aws/credentials`, or arbitrary files outside the project tree. The agent records the path string for human review only. The standards doc MUST document this constraint.
- **Static-reference grep operates on author-supplied `{affordance label}` and `{parent route}` strings.** Both come from the AC's User-flow sentence, which is authored by the spec author in their /spec session — no untrusted external input. Pathological inputs (a spec author embedding shell-special characters in `{affordance label}` to escape the grep) at most cause the grep to fail or return no matches; there is no shell-eval of the values. The agent MUST use the Grep tool (not raw shell) for the static-reference check to ensure no shell-substitution path exists.
- **Tool budget bump (12→16) does not weaken sandbox boundaries.** The agent's `tools: Read, Grep, Glob, Bash` and `disallowedTools: [Write, Edit, NotebookEdit]` frontmatter is unchanged. The budget increase only affects how many evidence-gathering calls the agent can make; it does NOT grant new capabilities. The agent remains read-only and cannot mutate the deliverable.
- **No secret material.** The PRD does not read, write, or embed credentials, tokens, API keys, or secrets. The new standards-doc section, the agent edits, and the contract test are public-style content meant for repo and harness distribution.
- **Citation integrity for the standards doc.** Agent-body and /build dispatcher references to `standards/process/user-flow-completeness.md` are free-form text strings, not runtime-fetched URLs. A misspelled path leads to a missing-file error if a downstream agent attempts to read the doc, not a security issue.
- **Forward-only is a security-adjacent property.** Because legacy specs are not modified retroactively (BR-010), there is no risk of the rule corrupting historical artifacts or invalidating audit trails. Pre-existing `spec.md` files retain their original content and `etc/feature/F<NNN>/spec` git tags.
- **Contract test is read-only.** `tests/test_spec_enforcer_reachability.py` performs grep-style assertions over committed repository files and the compiled `dist/` outputs. No network calls, no shell escapes, no file writes outside the pytest temp-dir fixtures.
- **Agent's existing fail-closed discipline is preserved.** spec-enforcer's existing rule — INSUFFICIENT_EVIDENCE on budget exhaustion is treated as NON_COMPLIANT downstream — is the security-relevant invariant: the verifier MUST NOT silently soften a verdict because evidence was missed. The reachability check inherits this discipline directly.
- **The bumped budget does not weaken the agent's anti-loop rules.** The "no exploratory reads", "one verdict per AC", "no let me check one more file" rules in the agent body are unchanged. The 16-call cap is the same kind of hard limit the prior 12-call cap was, just dimensioned for the additional reachability work.

## Module Structure

Files to create or modify:

- **Modified:** `standards/process/user-flow-completeness.md` — append a new `## Reachability Evidence` section after the existing F001 content. Defines the three evidence forms (E2E, static nav-graph reference, manual reachability proof), the per-form contract, the loose-substring static-reference rule (per GA-003), the free-form manual-attestation contract (per GA-004), the verdict mapping, and the trigger condition (User-flow sentence presence). Spec-enforcer-MUST-NOT-Read-artifact constraint documented per Security Considerations.
- **Modified:** `agents/spec-enforcer.md` — add User-flow sentence detection step (BR-002), three-tier evidence check (BR-003), bumped tool budget total to 16 (BR-004), citation of the standards doc by path (BR-005), free-form-operator-name sanitization (control-char strip + 64-char cap per Security Considerations), explicit no-automatic-Read-of-artifact-path rule. Frontmatter preserved (no `tools`/`disallowedTools` changes); JSON schema preserved verbatim (BR-007 / AC10).
- **Modified:** `skills/build/SKILL.md` — Step 7 spec-enforcer dispatch prompt updated to declare that User-flow-sentenced ACs require reachability evidence per `standards/process/user-flow-completeness.md` (BR-006). Dispatch shape, post-dispatch handling, and release-tag/release-notes-on-COMPLIANT-only rule are unchanged.
- **Created:** `tests/test_spec_enforcer_reachability.py` — the eight grep-based contract tests enumerated in BR-008. Uses the same autouse session-scoped compile fixture pattern as `tests/test_user_flow_completeness.py` (with the explicit `_ = _compile_fixture` reference workaround for Pyright's "is not accessed" hint).
- **Created:** `.etc_sdlc/features/F002-spec-enforcer-reachability/spec.md` — this PRD.
- **Created:** `.etc_sdlc/features/F002-spec-enforcer-reachability/value-hypothesis.yaml` — outcome contract (BR-005 of metrics-and-release-notes).
- **Created:** `.etc_sdlc/features/F002-spec-enforcer-reachability/state.yaml` — Phase 2.75 classification (`research-assisted`) + author_role: SME/PM.
- **Created:** `.etc_sdlc/features/F002-spec-enforcer-reachability/gray-areas.md` — 6 entries (3 research-decided, 3 user-decided per Phase 2.5).
- **Created:** `.etc_sdlc/features/F002-spec-enforcer-reachability/research/` — at least `codebase.md` capturing Phase 2 codebase findings.
- **Created (byte-identical copy):** `spec/spec-enforcer-reachability.md` — for browsability and backward compatibility.
- **Regenerated (not hand-edited):** `dist/agents/spec-enforcer.md`, `dist/skills/build/SKILL.md`, `dist/standards/process/user-flow-completeness.md` — outputs of `python3 compile-sdlc.py spec/etc_sdlc.yaml` after the source edits.

Files explicitly NOT touched:

- `compile-sdlc.py` — the recursive copy already handles new and edited files; no compiler changes are required.
- Any agent other than `spec-enforcer.md` — verifier, code-reviewer, security-reviewer, architect-reviewer, technical-writer, devops-engineer, sem, hotfix-responder, etc. are unchanged.
- Any skill other than `/build` — `/spec`, `/decompose`, `/implement`, `/init-project`, `/hotfix`, `/postmortem`, `/retrospective`, `/discovery`, `/roadmap`, `/metrics` are unchanged.
- Any other doc under `standards/process/`, `standards/architecture/`, `standards/code/`, `standards/git/`, `standards/quality/`, `standards/security/`, or `standards/testing/` — read-only references.
- `platform/src/etc_platform/guardrails.py` (the `SpecComplianceRule` v2 platform component, line 554) — not exercised by the harness; aligning it to the new evidence taxonomy is a future PRD.
- F001's User-flow sentence form, signal lists, conflict-default rule, Phase 3/4 /spec edits, and `hooks/inject-standards.sh` HEREDOC section — all unchanged.
- `docs/agent-prompt-template.md` — out of scope; Layer 3 sibling PRD owns it.
- `/build` skill's other steps (1–6, 8) — only Step 7's dispatcher prompt is touched.
- Legacy specs in `.etc_sdlc/features/*/spec.md` — forward-only (BR-010 / AC12).
- spec-enforcer's JSON output schema — preserved verbatim (BR-007 / AC10).
- `spec/etc_sdlc.yaml` — the agent and skill are hand-authored Markdown, not YAML-generated.

## Research Notes

**Codebase:**
- Agent source at `agents/spec-enforcer.md` (169 lines). Already has structured JSON output with per-AC `evidence` string field; reachability evidence fits naturally without schema changes.
- Existing hard tool budget: 12 calls total (Read 6 / Grep 6 / Glob 3 / Bash 2). Strict anti-loop discipline. Reachability checks must fit inside this envelope (bumped to 16 per GA-006).
- /build dispatches the agent at `skills/build/SKILL.md:443` via the Agent tool. Dispatcher prompt is generic; this PRD shapes both the agent definition AND the dispatcher prompt to declare reachability requirements.
- Design doc at `docs/architecture/spec-enforcer-design.md` (2026-02-28, Approved) names two surfaces: (a) `SpecComplianceRule` guardrail in `platform/src/etc_platform/guardrails.py:554` (NOT in harness scope); (b) the standalone agent (this PRD's target).
- F001 already produced `standards/process/user-flow-completeness.md` with the canonical sentence form, signal lists, conflict-default rule, and Phase 3/4 /spec edits. The Reachability Evidence section appends to that doc.
- No existing tests for the spec-enforcer agent. F002 introduces the precedent.
- Compile pipeline (`compile-sdlc.py`) recursively copies `agents/<name>.md` → `dist/agents/<name>.md` — same as skills and standards. No compiler edit needed.

**Best practices (light pass — proposal grounded in F001 + audit-evidence convention):**
- "Evidence taxonomy" pattern is standard in compliance tooling (audit / SOC2 control-evidence frameworks): preferred form (automated) → fallback (static reference) → last-resort (operator attestation). The three-tier ordering proposed maps to that convention.
- Adversarial-pass agents typically distinguish between "evidence absent" (NOT_SATISFIED) and "evidence ambiguous" (INSUFFICIENT_EVIDENCE). spec-enforcer already has both in its schema; the reachability check uses the existing distinction (per GA-005), no new verdict state.

**Antipatterns:** No `.etc_sdlc/antipatterns.md`. Nothing to incorporate.

**Three-block context (from concomitant 2026-05-01 harness feedback):**
- This PRD is **Layer 2** of a three-layer defense in depth.
- **Layer 1** (F001 — done): /spec-time gate. User-flow sentence required at AC authorship.
- **Layer 2** (this PRD): verify-time gate. spec-enforcer requires reachability evidence for ACs bearing User-flow sentences.
- **Layer 3** (sibling PRD — not yet specced): dispatch-time gate. `docs/agent-prompt-template.md` "Wiring is part of the deliverable" clause + `/build` Step 6 pre-validation.
- Each layer catches a different failure mode at a different harness phase. All three are needed for the F4-class defect to be structurally impossible.

**Process standards consulted:**
- `standards/process/interactive-user-input.md` — read-only reference; no new prompts in this PRD's deliverable surface.
- `standards/process/user-flow-completeness.md` — F001's deliverable, this PRD's append target.
- `standards/process/harness-feedback-loop.md` — defines the harness-feedback emission contract that produced both F001's and this PRD's input.
