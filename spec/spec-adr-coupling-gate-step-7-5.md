# F015 — Spec→ADR coupling enforcement at /build Step 7.5

**Status:** spec
**Author role:** Engineer (Jason / HCE)
**Date:** 2026-05-13
**Source:** Venlink proposal 2026-05-11 (proposal 2)

## Problem

A real venlink incident: F011 BR-012 specified "ETL backfills address_id for every existing entry." Implementation ran 1,936 ALS normalization calls — 87% returned no_results, 13% returned silently-wrong street-level matches. Resolution required a manual decision memo (48 file-sections of spec changes enumerated) + ADR-049 scope-clarification appendix + ADR-050 forbidden-paths update — all written post-hoc under pressure, after the terminal phase was already in motion. The harness had no gate that would have forced this documentation before the release tag.

Scope drift during build is a normal event in any complex feature. What's NOT normal is shipping the release tag without documenting what changed and why.

## Solution

Add **Step 7.5** to `/build` — a release-tag gate that scans `spec.md` (and `design.md` if present) for scope-change markers and blocks the release tag unless each marker is covered by a decision memo or ADR appendix.

Position: AFTER `verification.md` is written (Step 7 item 4) and BEFORE the release tag is written (Step 7 item 5). The release tag is the load-bearing artifact this gate guards.

## Solution: three sharp design choices (vs. naive grep)

The naive proposal (grep for "deferred", "removed", etc.) over-flags day-one Out-of-Scope sections. This spec addresses three concerns the venlink proposal flagged but deferred:

### 1. Marker detection is AC-number-anchored

A marker word counts as a scope-change finding ONLY if it appears in the same paragraph or bullet as an `AC-\d+` or `BR-\d+` reference, OR an ADR identifier (`ADR-\d+`), OR a backticked quoted phrase from the spec. Plain narrative use ("we deferred the v2 spec last quarter") is excluded.

This eliminates the false-positive density that would otherwise make the gate decorative.

### 2. Skip flag requires a mandatory inline reason

`--skip-spec-coupling-check="<reason>"` (with non-empty `<reason>`) is the override. The reason is logged into both `verification.md` and `release-notes.md` so the audit trail is preserved. `--skip-spec-coupling-check` with no value or empty string → exit 1 with error.

Trust-chain lesson from F007+F008: bypasses get used until the gate is decorative. A skip with an inline reason becomes its own memo.

### 3. Spec anchor via git tag

At Step 7.5, diff `spec.md` against the `etc/feature/F<NNN>/spec/done` git tag. Only flag markers added since that tag. Falls back to "scan whole file" if tag is missing (older pre-F015 features) with a single stderr warning.

This eliminates flagging Out-of-Scope sections that were in the spec at filing — only changes during the build trigger the gate.

## Acceptance Criteria

- **AC-01:** New `scripts/spec_coupling_check.py` CLI: `python3 spec_coupling_check.py <feature_dir>` exits 0 if all findings covered (or none found), exits 2 if any finding uncovered, exits 1 on usage/IO error.
- **AC-02:** Detector recognizes the markers: `deferred`, `scope-narrowed`, `scope narrowed`, `removed`, `out-of-scope`, `out of scope`, `not in scope`, `explicitly excluded`, `no longer in scope` (case-insensitive).
- **AC-03:** A marker counts as a finding ONLY when it appears in the same paragraph/bullet as an AC/BR/ADR reference or a backtick-quoted spec phrase. Bare narrative use is excluded.
- **AC-04:** Markers inside fenced code blocks (` ``` `) are excluded.
- **AC-05:** Markers inside a section header whose literal text is "Out of Scope" or "Not in Scope" are excluded (they're boundary statements, not scope changes).
- **AC-06:** When `etc/feature/F<NNN>/spec/done` git tag exists, the detector diffs current `spec.md` against that tag and flags only markers added since the tag. When the tag is missing, the detector scans the whole file and emits a single stderr warning explaining the lack of anchor.
- **AC-07:** Coverage check: a finding is covered if there exists a file at `.etc_sdlc/features/{slug}/decisions/*.md` containing the AC/BR/ADR reference from the finding. The decisions/ directory may not exist — that's fine; absence = no covered findings (which means uncovered findings will block).
- **AC-08:** Coverage check: a finding is also covered if there exists a file at `docs/adrs/*.md` modified since the spec/start (or spec/done if start missing) git tag, containing the AC/BR/ADR reference AND one of: "Scope clarification", "scope-narrowed", "appendix" (case-insensitive).
- **AC-09:** On block (exit 2): the script writes a structured report to stdout listing each uncovered finding with `file:line` reference and remediation options (decision memo path template, ADR appendix template).
- **AC-10:** `skills/build/SKILL.md` Step 7 is amended: the spec_coupling_check.py invocation runs AFTER `verification.md` is written and BEFORE the release tag is written. Non-zero exit 2 BLOCKS release tag write. Exit 0 proceeds normally.
- **AC-11:** SKILL.md documents `--skip-spec-coupling-check="<reason>"` operator override. Skip with no reason or empty reason → exit 1. Skip reason is appended to `verification.md` and `release-notes.md` under a "Spec Coupling Gate" subsection.
- **AC-12:** `tests/test_spec_coupling_check.py` covers AC-02 through AC-09 with fixture spec files, fixture decisions/, fixture ADRs, and fixture git tags (synthetic git repos via `git init` + temp dir).
- **AC-13:** README's `/build` description mentions Step 7.5 + the F015 row in the shipping table.

## Out of Scope

- **Cross-feature coupling.** This gate only checks one feature's spec against its own decisions/ + relevant ADRs. F015 (R2 cross-feature collision detection) is a separate concern.
- **Quality assessment of decision memos.** The gate checks existence + AC/BR cross-reference, not memo prose quality.
- **Auto-generating decision memos.** The gate emits a remediation hint with a template path; the operator writes the memo content.
- **Backporting to F001-F010.** Pre-F015 features can use `--skip-spec-coupling-check="legacy: spec predates F015 gate"` if they ever re-run /build.
- **Renaming or moving existing markers.** This is forward-only; existing specs are untouched.

## Technical Notes

- The detector lives in `scripts/spec_coupling_check.py` (not inline in SKILL.md) so it's unit-testable as a Python module. SKILL.md just invokes it via Bash with `<feature_dir>` and reads the exit code.
- Git-tag diff uses `git show <tag>:<path>` to retrieve the spec-at-tag content, then a line-by-line comparison against current content. Lines NOT in the tag-version are the "added since" set.
- Coverage check uses regex on memo/ADR content for the AC-NN / BR-NN / ADR-NN tokens — no semantic comparison needed.
- The script is bash-callable; tests dispatch via `subprocess.run`.

## Dependencies

- `git` (already required by etc).
- Python 3.11+ (already required).
- No new third-party Python dependencies.
