# PRD: Spec-Enforcer Stub-Marker Grep (F007)

## Summary

F007 adds a verify-time stub-marker grep step to spec-enforcer's per-AC verification path. After spec-enforcer determines an AC is SATISFIED, a new Step 2d runs grep on each cited evidence file against three rule classes: universal hard-fail patterns (`TODO\(F[0-9]+\)`, `FIXME`, `XXX`), universal warning patterns (`stub until task <NNN>` and two variants), and a per-project hard-fail token list read from `.etc_sdlc/stub-tokens.txt`. Files matching `tests/`, `__tests__/`, `*.test.*`, or `*.spec.*` path patterns are skipped. Any unsuppressed hit downgrades the verdict to `INSUFFICIENT_EVIDENCE` with the matched line as evidence.

F007 is the verify-time half of the stub-detection three-layer defense. F008 (wave-planner implicit-dependency rejection) is the plan-time half. Together they mirror F001-F003's three-layer orphan-surface defense — independent gates on independent artifacts that do not trust each other. The contracts live in a new standards doc at `standards/process/stub-marker-grep.md`, cross-referenced from `standards/process/user-flow-completeness.md`.

The motivating incident was venlink-platform F005-discussion-threads (2026-05-05): five gates failed in series and shipped a live `TODO(F005-013)` plus a `<div data-testid="composer-stub" />` empty state to production. spec-enforcer was dispatched three times; all three returned COMPLIANT despite the stubs in cited files. The user found the bug visually on `localhost:5174`. F007's stub grep is the smallest mechanical gate that doesn't trust the layers below it — it reads the file directly.

## Scope

### In Scope

- Edit `agents/spec-enforcer.md` to add Step 2d (stub-grep post-pass on SATISFIED ACs) immediately after Step 2c. The new step cites `standards/process/stub-marker-grep.md` rather than duplicating contracts inline (matches F002's citation pattern).
- Bump spec-enforcer's tool budget from 16 → 20 total. Per-tool: Read=8, Grep=8→12, Glob=4, Bash=2.
- Create `standards/process/stub-marker-grep.md` with the full stub-detection contract: universal hard-fail patterns, universal warning patterns, per-project token list semantics, tests-path skip rules, verdict mapping, and security constraints. Cross-reference from `standards/process/user-flow-completeness.md` (one-line "See also" pointer).
- Define the universal **hard-fail** regex set: `TODO\(F[0-9]+\)`, `FIXME`, `XXX`. Any match overrides SATISFIED to INSUFFICIENT_EVIDENCE.
- Define the universal **warning** regex set (case-insensitive): `stub\s+until\s+task\s+[0-9]+`, `placeholder\s+until\s+task\s+[0-9]+`, `until\s+task\s+[0-9]+\s+lands`. Any match downgrades to INSUFFICIENT_EVIDENCE with a "warning-class" evidence note.
- Define the per-project hard-fail token list: `.etc_sdlc/stub-tokens.txt`. One regex per line, `#` for comments, blank lines skipped, empty file = no extra patterns. Matches act as hard-fail (per GA-005).
- Define the tests-path skip set: `tests/`, `__tests__/`, `*.test.*`, `*.spec.*`. Cited files matching any of these path patterns are skipped entirely (no grep run, no hits recorded).
- Compile spec-enforcer source to `dist/agents/spec-enforcer.md` (byte-identical via `compile-sdlc.py`).
- Add `tests/test_spec_enforcer_stub_grep.py` mirroring `tests/test_spec_enforcer_reachability.py`'s pattern: session-scoped autouse compile fixture, `_ = _compile_sdlc` Pyright workaround, module-scoped text fixtures, region-restricted greps for each contract clause.
- Update `hooks/inject-standards.sh` to include a one-section summary of the stub-marker-grep contract for subagent onboarding context.

### Out of Scope

- Wave-planner implicit-dependency rejection (that's F008, separate PRD).
- Pre-commit hook stub-grep on the human's machine (F007 only changes the spec-enforcer agent).
- Retroactive grep on F001-F005 cited files (forward-only convention per BR-007 of F001).
- The "third gate" requiring non-test artifacts for user-facing ACs (deferred to F010+ per GA-007; saved to memory).
- Any changes to `/spec`, `/build`, or other agents.
- Per-project warning-class token list (only hard-fail per-project tokens; warning-class would require a second config file, unjustified for v1).
- Configurable test-skip path list (`.etc_sdlc/stub-skip-paths.txt` was a GA-006 alternative; rejected in favor of fixed industry-convention patterns).

## Requirements

### BR-001: Stub-grep step location and trigger

spec-enforcer's per-AC verification path gains a new **Step 2d** inserted immediately after Step 2c (Reachability Recording Rules). Step 2d runs as a **post-pass on SATISFIED ACs only** — ACs with verdicts NOT_SATISFIED, NOT_APPLICABLE, INSUFFICIENT_EVIDENCE, or BLOCKED are not subject to the stub grep. The post-pass discipline guarantees Step 2d only DOWNGRADES verdicts; it never promotes anything.

### BR-002: Universal hard-fail patterns

Any match of the patterns `TODO\(F[0-9]+\)`, `FIXME`, or `XXX` in a cited evidence file (subject to BR-005 path skipping) overrides the AC's SATISFIED verdict to `INSUFFICIENT_EVIDENCE`. Hard-fail patterns are case-sensitive (these are conventional code-comment markers; lowercasing them creates false-positive risk on prose).

### BR-003: Universal warning patterns

Any match of the patterns `stub\s+until\s+task\s+[0-9]+`, `placeholder\s+until\s+task\s+[0-9]+`, or `until\s+task\s+[0-9]+\s+lands` (case-insensitive) downgrades the AC to `INSUFFICIENT_EVIDENCE` with a "warning-class" evidence note distinguishing them from hard-fail hits. Warning matches signal probable but lower-confidence stubs.

### BR-004: Per-project hard-fail token list

spec-enforcer reads `.etc_sdlc/stub-tokens.txt` if present. Each non-blank, non-`#`-prefixed line is treated as an additional regex pattern. All entries act as **hard-fail** (per GA-005). Empty file = no extra patterns. Absent file = no extra patterns. The harness regex set never grows; project-specific tokens (e.g., `composer-stub`, `InlineComposerStub`) live here.

### BR-005: Tests-path skip set

Cited files whose paths contain any of the substrings `tests/`, `__tests__/`, `.test.`, or `.spec.` are skipped entirely — no grep run, no hits recorded. The skip applies before any pattern matching and is fixed (not configurable in v1, per GA-006).

### BR-006: Verdict mapping

- **Hard-fail hit** (universal BR-002 OR per-project BR-004): AC verdict becomes `INSUFFICIENT_EVIDENCE`. Evidence string format: `<file>:<line>: <quoted match>` prefixed with `stub-marker (hard-fail): `.
- **Warning hit** (universal BR-003 only): AC verdict becomes `INSUFFICIENT_EVIDENCE`. Evidence string format: `<file>:<line>: <quoted match>` prefixed with `stub-marker (warning): `.
- **Multiple hits in one file**: record the FIRST hit only (avoids verbose evidence; the operator opens the file to find the rest).
- **Hard-fail and warning both present**: hard-fail wins (its evidence is recorded).

### BR-007: Tool budget bump

spec-enforcer's tool budget rises from **16 → 20 total**. Per-tool maxima: Read=8, **Grep=8→12** (the +4 lands here, since each cited file adds one grep), Glob=4, Bash=2. The Tool Budget table in the agent body is updated to reflect the new totals; the existing anti-loop rules ("budget exhaustion = emit verdict", "no exploratory reads", "one verdict per AC") remain verbatim.

### BR-008: Standards doc location and citation pattern

The full stub-detection contract lives at a NEW standards doc `standards/process/stub-marker-grep.md`. The agent body (Step 2d) references this doc by path rather than duplicating contracts inline (matches F002's citation pattern at `agents/spec-enforcer.md:81`). `standards/process/user-flow-completeness.md` gains a one-line "See also" pointer to the new doc near its existing Cross-References section.

### BR-009: Test contract

A new test file `tests/test_spec_enforcer_stub_grep.py` mirrors `tests/test_spec_enforcer_reachability.py`'s pattern: session-scoped autouse `_compile_sdlc` fixture + `_ = _compile_sdlc` Pyright workaround + module-scoped text fixtures for the agent dist body and the standards doc + region-restricted greps that scope each assertion to its target Step or section. Tests cover hard-fail patterns (BR-002), warning patterns (BR-003), per-project token list semantics (BR-004), tests-path skipping (BR-005), verdict mapping (BR-006), tool budget (BR-007), and standards-doc citation (BR-008).

### BR-010: Forward-only

F007 applies to NEW agent verifications. spec-enforcer runs that have already reported COMPLIANT for F001-F005 are not retroactively scanned. The new behavior takes effect on the first dispatch after install.sh deploys the new agent body to `~/.claude/agents/spec-enforcer.md`. Matches BR-007 of F001 (forward-only convention).

## Acceptance Criteria

1. **Agent body — Step 2d added** — `agents/spec-enforcer.md` contains a new Step 2d header inserted between Step 2c and Step 3. Its body declares the post-pass-on-SATISFIED-only trigger condition (does not run on NOT_SATISFIED, NOT_APPLICABLE, INSUFFICIENT_EVIDENCE, or BLOCKED ACs).
2. **Agent body — citation pattern** — Step 2d cites `standards/process/stub-marker-grep.md` by path. The agent body does NOT duplicate the regex sets, the per-project token list spec, or the verdict mapping inline.
3. **Agent body — tool budget** — `agents/spec-enforcer.md` Tool Budget table shows total 20, Read=8, Grep=12, Glob=4, Bash=2. The literal string "16 across all tools" does NOT appear anywhere in the file.
4. **Standards doc — exists with required sections** — `standards/process/stub-marker-grep.md` exists at the source path and contains the five contract sections verbatim by header: `## Universal Hard-Fail Patterns`, `## Universal Warning Patterns`, `## Per-Project Token List`, `## Tests-Path Skip`, `## Verdict Mapping`.
5. **Standards doc — security constraints** — `standards/process/stub-marker-grep.md` contains a `## Security Constraints` section naming: (a) no automatic Read of cited files (only Grep is invoked), (b) control-character stripping on `.etc_sdlc/stub-tokens.txt` entries via regex `[\x00-\x1f\x7f]`, (c) maximum 1024-character cap on each token-list entry to bound regex compilation cost.
6. **Cross-reference** — `standards/process/user-flow-completeness.md` Cross-References section gains a `See also: standards/process/stub-marker-grep.md` line referencing F007 by feature ID.
7. **Hook injection** — `hooks/inject-standards.sh` contains a new section with header `### Stub-Marker Grep Contract for spec-enforcer` summarizing the universal hard-fail patterns, the warning patterns, the per-project token list, and a path pointer to `standards/process/stub-marker-grep.md`.
8. **Test fixture** — `tests/test_spec_enforcer_stub_grep.py` exists with a session-scoped autouse `_compile_sdlc` fixture identical in shape to F002's, plus the module-level `_ = _compile_sdlc` Pyright workaround.
9. **Test — agent body** — Tests in the new file assert `dist/agents/spec-enforcer.md` contains: the Step 2d header, the path reference to `standards/process/stub-marker-grep.md`, and the budget total `20 across all tools`.
10. **Test — standards doc** — Tests assert `standards/process/stub-marker-grep.md` contains all five contract section headers AND the Security Constraints section AND the literal hard-fail patterns `TODO\(F[0-9]+\)`, `FIXME`, `XXX`.
11. **Test — hook** — Tests assert `hooks/inject-standards.sh` contains the new `### Stub-Marker Grep Contract for spec-enforcer` section header AND a path reference to the standards doc.
12. **Test — cross-reference** — Tests assert `standards/process/user-flow-completeness.md` contains the literal substring `standards/process/stub-marker-grep.md` in its Cross-References section.
13. **Compile parity** — `diff -q agents/spec-enforcer.md dist/agents/spec-enforcer.md` exits 0 after `compile-sdlc.py spec/etc_sdlc.yaml` runs (byte-identical compile).
14. **Regression baseline** — Full pytest suite passes (≥ 697 baseline tests + the new F007 tests, no regressions).
15. **Preservation + changeset scope** — No F001-F005 release-notes.md, verification.md, or task YAML files are modified by this build; the changeset is exactly: `agents/spec-enforcer.md`, `dist/agents/spec-enforcer.md` (compiled), `standards/process/stub-marker-grep.md`, `standards/process/user-flow-completeness.md` (cross-ref line), `hooks/inject-standards.sh`, `tests/test_spec_enforcer_stub_grep.py`, plus the F007 PRD copy at `spec/spec-enforcer-stub-grep.md`.

## Edge Cases

1. **Empty `.etc_sdlc/stub-tokens.txt`** — file exists but contains only comments, blank lines, or nothing. Behavior: no extra patterns added; treated identically to file absence.
2. **Malformed regex in `.etc_sdlc/stub-tokens.txt`** — operator writes a syntactically invalid regex. Behavior: skip the offending line with a stderr warning naming the line number and the malformed pattern; the rest of the file's patterns are still loaded. Verification of the current AC is NOT blocked on operator config error.
3. **Cited evidence file does not exist on disk** — spec-enforcer was handed an evidence path that no longer resolves. Behavior: skip the file with no hits recorded.
4. **Cited evidence file is binary** — e.g., an image, PDF, or compiled binary. Behavior: rely on grep's `-I` flag (or equivalent) to skip binary files automatically.
5. **Cited file matches BOTH the tests-path skip set AND contains hard-fail tokens** — the skip wins (BR-005). The grep is never run; no hits recorded.
6. **Multiple matches in one cited file** — record the FIRST hit only (BR-006). The operator opens the file to find the rest. Avoids verbose evidence strings while preserving the failure signal.
7. **AC has no cited evidence at all** — spec-enforcer's SATISFIED verdict requires evidence; if there's no evidence, the AC was never really SATISFIED. Step 2d simply has nothing to scan and no-ops cleanly.
8. **Cited file path is absolute and outside the project tree** — e.g., `/etc/passwd`, `~/.aws/credentials`. Behavior: out-of-scope evidence cite. spec-enforcer skips the file entirely (no Grep, no Read) and records a verdict of `INSUFFICIENT_EVIDENCE` with note `out-of-scope evidence path`. Mirrors F002's "no automatic Read of artifact paths" security rule.
9. **Tool budget exhausted mid-Step-2d** — per the existing anti-loop rules in the agent body's Tool Budget section, emit verdict with `budget_exhausted: true`. ACs already verified retain their verdicts; ACs not yet reached become `INSUFFICIENT_EVIDENCE`.
10. **`.etc_sdlc/stub-tokens.txt` entry exceeds the 1024-char cap** — line is truncated to 1024 chars, a stderr warning names the affected line number, and the truncated pattern is loaded.
11. **Cited file contains a TODO referencing F007 itself during the F007 build** — the universal hard-fail pattern `TODO\(F[0-9]+\)` fires; verdict downgrades to `INSUFFICIENT_EVIDENCE`. This is correct behavior: the F007 build should not ship with unfinished `TODO(F007-xxx)` markers in its own deliverable.
12. **F007's own AC verification triggers stub grep on F007 deliverables** — the meta-property: spec-enforcer's first run after F007 ships will scan F007's own files. Any hard-fail pattern in `agents/spec-enforcer.md`, `standards/process/stub-marker-grep.md`, or the test file would fail F007's own COMPLIANT verdict. This is a feature, not a bug: F007 must dogfood its own contract. Build-time discipline: keep the F007 deliverables clean of stub markers from the first commit.

## Technical Constraints

- **Forward-only convention.** Per BR-007 of F001, F007 applies to NEW spec-enforcer dispatches after install.sh deploys the updated agent body. No retroactive scan of F001-F005 cited files.
- **Sonnet/Opus-1M child-dispatch workaround.** Every Agent-tool call during /build MUST pass `model: opus` override.
- **F002 standards-doc citation pattern.** The agent body cites `standards/process/stub-marker-grep.md` by path; contracts are NOT duplicated inline.
- **F002 test fixture pattern.** `tests/test_spec_enforcer_stub_grep.py` MUST use the session-scoped autouse `_compile_sdlc` fixture + `_ = _compile_sdlc` Pyright workaround + module-scoped text fixtures.
- **`compile-sdlc.py` byte-identical compile.** After every edit to `agents/spec-enforcer.md`, the build agent runs `python3 compile-sdlc.py spec/etc_sdlc.yaml`; `diff -q` MUST exit 0.
- **Python 3.11+** (existing repo standard); `from __future__ import annotations` per existing convention.
- **PEP 686 future-proofing.** All file-open sites in F007's deliverables pass `encoding="utf-8"` explicitly.
- **Pyright workaround inventory.** `_ = _compile_sdlc` autouse-fixture reference (always); `# pyright: ignore[reportMissingImports]  # noqa: E402` if any sys.path-manipulated runtime imports appear.
- **Hook injection respects existing structure.** `hooks/inject-standards.sh` placement TBD by reading the current file at /build time.
- **No INVARIANTS.md, no `.etc_sdlc/antipatterns.md`.** Both absent in this repo.

## Security Considerations

1. **No automatic Read of cited evidence files.** Step 2d uses Grep ONLY — never Read. Combined with rule 4 below, this prevents directory-traversal exploits via hostile evidence cites.
2. **Control-character stripping on `.etc_sdlc/stub-tokens.txt`.** Each line is sanitized via regex `[\x00-\x1f\x7f]` before being compiled as a regex pattern. Mirrors F001 / F002 / F003's "Other" sanitization contract.
3. **Maximum line-length cap on `.etc_sdlc/stub-tokens.txt` (1024 chars).** Bounds worst-case regex-compilation time and protects against catastrophic backtracking from operator-supplied patterns.
4. **Out-of-scope evidence cite handling.** Cited file paths that resolve outside the project tree are skipped entirely. Mirrors F002's rule for manual-reachability artifact paths.
5. **First-hit-only recording bounds evidence size.** Per BR-006, only the first match per file is recorded.
6. **Matched-line sanitization in evidence.** When recording the matched line into the evidence JSON field, spec-enforcer strips control chars (regex `[\x00-\x1f\x7f]`) and caps the line at 256 chars.
7. **Grep tool budget interaction is a security mitigation.** The 12-call Grep cap (BR-007) bounds worst-case I/O regardless of how many cited files exist.
8. **`.etc_sdlc/stub-tokens.txt` write protection is repo-level, not F007's responsibility.**
9. **Malformed-regex skip is fail-safe.** Per Edge Case 2, an invalid regex causes that line to be skipped with a stderr warning rather than rejecting the file or blocking the AC.

## Module Structure

### Created

- `standards/process/stub-marker-grep.md` — new standards doc (~150-200 lines). Defines the universal hard-fail pattern set, the universal warning pattern set, the per-project token list spec, the tests-path skip rules, the verdict mapping, and the security constraints. Cited by `agents/spec-enforcer.md` Step 2d. Cross-referenced from `standards/process/user-flow-completeness.md` and `hooks/inject-standards.sh`.
- `tests/test_spec_enforcer_stub_grep.py` — new contract-test module (~200-250 lines). Session-scoped autouse `_compile_sdlc` fixture, `_ = _compile_sdlc` Pyright workaround, module-scoped text fixtures for `dist/agents/spec-enforcer.md` and the new standards doc and `hooks/inject-standards.sh`. Tests assert the agent body contains Step 2d + standards-doc citation + budget=20; the standards doc contains all five contract sections + security; the hook contains the new section; the cross-reference exists in `user-flow-completeness.md`.

### Modified

- `agents/spec-enforcer.md` — add Step 2d header + body (post-pass on SATISFIED ACs only, citing the new standards doc). Update Tool Budget table from 16 → 20 total (Grep 8 → 12). The literal "16 across all tools" must be replaced with "20 across all tools".
- `dist/agents/spec-enforcer.md` — compiled output via `compile-sdlc.py spec/etc_sdlc.yaml`. Byte-identical to source. NOT hand-edited; only `compile-sdlc.py` writes here.
- `standards/process/user-flow-completeness.md` — add a single line in the existing Cross-References section: `- standards/process/stub-marker-grep.md — stub-detection defense (F007), companion to the user-flow completeness defense.` No other changes.
- `hooks/inject-standards.sh` — add a new section with header `### Stub-Marker Grep Contract for spec-enforcer` summarizing the universal hard-fail patterns + universal warning patterns + per-project token list + path pointer to `standards/process/stub-marker-grep.md`. Placement: structural location matching existing F001/F002/F003 sections — exact line determined by reading the current file at /build time.

### Created at /spec time (already exist)

- `.etc_sdlc/features/F007-spec-enforcer-stub-grep/spec.md` — this PRD.
- `.etc_sdlc/features/F007-spec-enforcer-stub-grep/value-hypothesis.yaml` — outcome contract per BR-005 of metrics-and-release-notes.
- `.etc_sdlc/features/F007-spec-enforcer-stub-grep/state.yaml` — Phase 2.75 classification + author_role.
- `.etc_sdlc/features/F007-spec-enforcer-stub-grep/gray-areas.md` — 7 entries (4 research + 3 user).
- `.etc_sdlc/features/F007-spec-enforcer-stub-grep/research/codebase.md` — Phase 2 codebase findings.
- `spec/spec-enforcer-stub-grep.md` — byte-identical copy of the spec.md above, for browsability.

### NOT in scope (do not touch)

- `agents/*.md` other than `spec-enforcer.md`.
- `skills/*.md` of any kind. /spec, /build, /implement, /decompose all unchanged.
- `scripts/*.py` other than the implicit invocation of `compile-sdlc.py`. No new helper scripts.
- `.etc_sdlc/features/F001-*` through `F005-*`. Forward-only.
- `dist/skills/**` and `dist/agents/*.md` other than `spec-enforcer.md`.

## Research Notes

**Codebase findings (Phase 2):**
- `agents/spec-enforcer.md` current tool budget is 16 total (set by F002). Step structure: Step 1 → Step 2 → Step 2a (User-flow Detection) → Step 2b (Three-Tier Reachability) → Step 2c (Recording Rules) → Step 3 (Emit JSON). Step 2d slots cleanly between 2c and 3.
- F002 established the precedent of citing standards docs from the agent body rather than duplicating contracts inline. F007 adopts the same pattern with a new standards doc rather than extending `user-flow-completeness.md` (already 380+ lines).
- Test pattern: `tests/test_spec_enforcer_reachability.py` is the gold standard — session-scoped autouse compile fixture, `_ = _compile_sdlc` Pyright workaround, module-scoped text fixtures, region-restricted greps.
- Compile pipeline: `agents/spec-enforcer.md` → `dist/agents/spec-enforcer.md` via `compile-sdlc.py` (byte-identical).
- `INVARIANTS.md` absent. `.etc_sdlc/antipatterns.md` absent. `.etc_sdlc/stub-tokens.txt` absent (this PRD introduces the file).

**Best Practices (precedent):**
- Forward-only convention is repo-wide (BR-007 from F001).
- Standards-doc-citation-from-agent-body pattern is established (F002).
- Universal-vs-per-project regex split prevents harness-regex bloat.

**Antipatterns:** No `.etc_sdlc/antipatterns.md` file exists; absence noted.
