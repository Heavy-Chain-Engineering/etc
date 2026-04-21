# Bugs and gaps surfaced during the 4.7 migration audit

This document tracks defects in the etc harness that were found during
the 4.6 → 4.7 prompt-literalism audit. Some were fixed in-flight because
they overlapped with the migration scope; others are tracked here as
separate follow-up work.

**Last updated:** 2026-04-21 (Phase 2 Batches 1-4 complete, Batch 5 running)

---

## Category A — Already fixed in-flight

These defects were discovered during audit subagent runs and fixed
as part of the same edit because deleting them was zero-additional-
scope given the file was already being modified. Documented here for
traceability.

### A1. `code-reviewer.md` referenced three non-existent standards files

**Severity:** High (silent failure under 4.7)
**Origin:** Pre-migration tech debt
**Detection:** Batch 2 audit of `agents/code-reviewer.md`
**Fix:** Replaced `quality-standards.md`, `naming-conventions.md`,
`test-standards.md` with the actual file `testing-standards.md` plus
the other real standards files relevant to code review scope.
**Commit:** `b5b39e4` (feat(4.7-migration): Phase 2 Batch 2)
**Impact if unfixed:** Under 4.7, the agent would read what exists and
silently skip what doesn't. Under 4.6 generalization, it might have
inferred similar content from training. Either way, behavior was
untrustworthy — the agent's Before Starting contract was a promise
the harness couldn't keep.

### A2. `multi-tenant-auditor.md` had no Before Starting section

**Severity:** High (AP-013 violation; no forced-reads mechanism)
**Origin:** Pre-migration
**Detection:** Batch 4 audit
**Fix:** Added a full "Before Starting (Non-Negotiable)" section
listing the standards and skills the agent depends on. Also added
`disallowedTools: [Write, Edit, NotebookEdit]` frontmatter to match
sibling auditor roles (read-only posture). Removed the old
"Required Skills" tail section that was semantically serving the same
role without mechanical enforcement.
**Commit:** `af32757` (feat(4.7-migration): Phase 2 Batch 4)
**Impact if unfixed:** The agent might do security-adjacent
multi-tenant auditing without reading the relevant OWASP and data-
handling standards. Under 4.7, "Required Skills" advisory language
wouldn't trigger reads.

### A3. `frontend-dashboard-refactorer.md` had no Before Starting section

**Severity:** High (AP-013 violation)
**Origin:** Pre-migration
**Detection:** Batch 4 audit
**Fix:** Added Before Starting, Output Format, and Boundaries sections
mirroring the pattern in `frontend-developer.md` and `code-simplifier.md`.
**Commit:** `af32757`
**Impact if unfixed:** Same class as A2 — references without
enforcement.

### A4. AP-001 grep pattern was incomplete

**Severity:** Low (audit-tool defect, not harness defect)
**Origin:** Spec authoring (mine)
**Detection:** Phase 1 self-review on `agents/backend-developer.md`
— the narrow pattern missed "idiomatic" and "strict typing."
**Fix:** Expanded AP-001 grep to include
`idiomatic|strict typing|proper|robust|well-designed`. Re-baselined
the before.txt counts with the expanded pattern. Documented the
revision in the spec with a "Revision history" note.
**Commit:** `15935a7` (AP-013 addition + Phase 1 closure)
**Impact if unfixed:** 6 AP-001 matches across the harness would have
been missed. Each a minor 4.7 literalism footgun.

### A5. `ci-gate.sh` hardcoded `src/ tests/` paths

**Severity:** Medium (hook failed with E902 on this repo's layout)
**Origin:** Shipped earlier in this session (v1.7.1 haiku/sonnet fix)
**Detection:** Observed during development; ci-gate false-positive
ruff error on non-existent `src/` dir in the etc repo
**Fix:** Rewrote `ci-gate.sh` to discover actual source directories
from what exists (src/, tests/, hooks/, scripts/, platform/src/).
**Commit:** `395757b`
**Impact if unfixed:** Hook fired false-positive lint errors on every
Stop event in this repo. Noisy and wastes operator attention.

### A6. `scripts/tasks.py` path referenced incorrectly in skills

**Severity:** Medium (broke consumer project installs)
**Origin:** Pre-migration
**Detection:** Consumer project reported missing `scripts/tasks.py`
after installing
**Fix:** Changed all skill references from `python3 scripts/tasks.py`
to `python3 ~/.claude/scripts/tasks.py` (the actual install path).
**Commit:** `94be4f7`
**Impact if unfixed:** Consumer projects broke on first task
operation.

### A7. Kuzu graph DB archived

**Severity:** Low (spec-authoring issue, not harness)
**Origin:** KG POC PRD authored mid-session
**Detection:** Operator flagged it
**Fix:** Rewrote the graph DB section of the KG POC PRD to specify
evaluation criteria rather than lock in a specific tool. Added web
research instruction.
**Commit:** (same as KG POC PRD writeup)
**Impact if unfixed:** Implementer would spin up on archived tooling.

---

## Category B — Still to fix (tracked)

These defects were discovered during the audit but are out of scope
for the migration (which is bounded to the AP catalog). They are
tracked here as follow-up work.

### B1. `architect.md` has "proceed with best judgment"

**Severity:** Low (semantic AP-001 cousin that escaped the grep)
**Origin:** Pre-migration
**Detection:** Batch 3 audit flagged but did not fix (catalog
discipline)
**Proposed fix:** Either (a) expand AP-001 pattern to include
`best judgment|common sense|reasonable` and re-audit, OR (b)
targeted rewrite of the specific phrase in `agents/architect.md`
to "proceed using: (a) patterns observable in existing ADRs in
docs/adr/, and (b) conservative defaults — prefer reversibility,
prefer simplicity, recommend deferral in ADR Context section"
mirroring backend-developer's Error Recovery pattern.
**Priority:** P3 (low blast radius, specific to architect agent)
**Estimated effort:** 15 minutes

### B2. AP-001 grep may still miss semantic variants

**Severity:** Low (audit-tool quality)
**Origin:** This migration
**Detection:** B1 revealed at least one semantic AP-001 variant
("best judgment") not in the current pattern
**Proposed fix:** Audit pass across the whole harness for other
semantic variants: `best judgment`, `common sense`, `reasonable`,
`sensible`, `appropriate patterns`, `natural`, `expected`. If
found, add to AP-001 and re-audit the affected files. Estimate
after running the sweep.
**Priority:** P2 (addresses completeness of the migration's own
audit tool)
**Estimated effort:** 1 hour (sweep + targeted fixes)

### B3. Unregistered agents question

**Severity:** N/A (not a bug; an operator decision)
**Origin:** Earlier session discussion (session around v1.7 spec-
enforcer registration)
**Detection:** 24 agent .md files on disk, but only 21 registered
in `spec/etc_sdlc.yaml` during Phase 0 baseline. The 3 unregistered:
`frontend-dashboard-refactorer`, `gemini-analyzer`,
`multi-tenant-auditor`. (spec-enforcer was registered in v1.7.)
**Status:** All three are now 4.7-clean thanks to the migration.
Operator should decide: keep unregistered, or add to YAML and ship.
**Priority:** P3 (decision, not fix)
**Estimated effort:** 30 minutes if registering all three
(add YAML entries, recompile, test)

### B4. Compile-time detection of AP-013 violations

**Severity:** Medium (missing mechanical enforcement)
**Origin:** This migration revealed the AP-013 pattern
**Detection:** Phase 1 / AP-013 addition
**Proposed fix:** Extend `compile-sdlc.py --audit-enforcement` (or
add a new `--audit-references` flag) to scan each agent definition
for file references and verify the AP-013 enforcement paths. Report
violations in the compile output. This moves the AP-013 check from
"post-hoc grep pass" to "compile-time mechanical check."
**Priority:** P1 (prevents regression after the migration ships)
**Estimated effort:** 4 hours (spec + implement + tests)

### B5. Pattern-testing for prompt files

**Severity:** Low (testability gap)
**Origin:** This migration
**Detection:** No automated test currently verifies that agent
definitions contain zero AP-NNN matches. The migration is a
one-time sweep; drift after will reintroduce.
**Proposed fix:** Add `tests/test_agent_prompts_ap_free.py` that
greps every `agents/*.md` for every AP-NNN pattern and fails on any
match. Mark AP-012 exceptions (security-reviewer,
multi-tenant-auditor, architect-reviewer, hotfix-responder) via a
frontmatter key like `ap-012: defensive-framed: true` so the test
can skip them with justification.
**Priority:** P1 (prevents drift after migration)
**Estimated effort:** 3 hours

### B7. `/implement` and `/build` contract divergence

**Severity:** Medium (parallel orchestrators that aren't actually parallel)
**Origin:** Pre-migration
**Detection:** Phase 3 `/implement` audit surfaced it
**Proposed fix:** Operator decision required on each gap:
  1. `/build` has `state.yaml` + `--resume` protocol; `/implement` has neither. Should `/implement` gain resume capability, or is it intentionally session-only?
  2. `/build` has AskUserQuestion confirmation gates at Steps 3 and 5; `/implement` dispatches without user confirmation. Should `/implement` add gates?
  3. `/build` dispatches `spec-enforcer` adversarially in Step 7; `/implement` does AC verification in-context. Should `/implement` also dispatch `spec-enforcer`?
  4. `/build` reads `standards/process/interactive-user-input.md` in Before Starting; `/implement` does not. Consequence of #2 — resolves when #2 does.
  5. Task YAML shape and `tasks.py` contract ARE aligned. No issue.

**Priority:** P2 (not a blocker for 4.7 migration; but these two skills
overlap in scope and their divergence creates operator confusion about
which to use when)
**Estimated effort:** 2 hours to align (assuming the operator decides
`/implement` should be a true parallel orchestrator) OR 30 minutes to
document the intentional differences (assuming they should stay separate)

### B6. AP-008 enforcement needs a positive check, not just absence

**Severity:** Low (absence-based rule is hard to audit)
**Origin:** This migration
**Detection:** AP-008 is "absence of verbosity directive" — grep
can't detect its absence; manual inspection required
**Proposed fix:** Define a required marker phrase for verbosity
directives (e.g., `**Response format` or `## Response Format`).
The grep test (B5) then becomes positive: "file must contain this
phrase."
**Priority:** P2
**Estimated effort:** 1 hour (define marker + update spec + audit
all files for compliance)

---

## Category C — Open questions / investigation needed

### C1. Do skills also need this audit?

Phase 3 of the migration spec covers skills audit. It's sequenced
after Phase 2 (agents) because skills reference each other and need
sequential treatment. Once Phase 2 completes, Phase 3 will likely
surface similar bugs in `skills/*/SKILL.md` files.
**Priority:** Sequenced per migration plan, not a new ticket

### C2. Are standards docs AP-clean?

Phase 4 of the migration spec covers standards docs. Some standards
files are directive ("apply these rules") and will need the same
literalism treatment as agents.
**Priority:** Sequenced per migration plan

### C3. Should `inject-standards.sh` be audited for what it injects?

If the hook injects vague content, the injected content inherits the
same literalism problems. Investigate whether the hook's inputs are
4.7-safe.
**Priority:** P2 (related to the migration but not in current scope)
**Estimated effort:** 30 minutes investigation

---

## Fix plan

### Immediate (during current 4.7 migration)

These ride on the migration commits; no separate ticket needed.

- Batch 5 completion (SEM, hotfix-responder, project-bootstrapper) —
  in progress as of 2026-04-21
- Phase 3 (skills) per migration spec section 8
- Phase 4 (hooks + standards) per migration spec section 9
- Phase 5 (ship) per migration spec section 10

### Post-migration — ordered by priority

1. **B4:** Compile-time AP-013 check (P1, 4 hours)
2. **B5:** Prompt-file test in `tests/` (P1, 3 hours)
3. **B6:** Positive marker for AP-008 (P2, 1 hour; composes with B5)
4. **B2:** AP-001 semantic variant sweep (P2, 1 hour)
5. **C3:** `inject-standards.sh` audit (P2, 30 min investigation)
6. **B1:** `architect.md` "best judgment" targeted fix (P3, 15 min)
7. **B3:** Unregistered agents decision (P3, 30 min if registering)

Total post-migration effort: ~9-10 hours, mostly mechanical.

### Roadmap integration

When the v1.8 `/roadmap` skill ships (currently in-progress in a
worktree), these items can migrate from this document into
`.etc_sdlc/roadmap/` as structured entries. Until then, this file
is the source of truth for post-migration follow-up.

---

## Insight: what the migration taught us about the harness

The migration was scoped to 4.7 literalism repair, but in practice
surfaced a broader class of latent issues. The pattern: **any prompt
surface that relied on inference was fragile in ways we hadn't
measured**. Missing files, missing structure, vague directives — all
were "working" under 4.6 generalization and "silently failing" under
4.7 literalism.

The fix is not migration-specific. It's a shift in how we author
prompt surfaces: enumerate, don't imply; enforce mechanically, don't
trust the model; test the prompt artifacts themselves (B5) the same
way we test code.

The migration is one pass of repair. The post-migration work (B4, B5,
B6) is the machinery to prevent the problem from coming back.
