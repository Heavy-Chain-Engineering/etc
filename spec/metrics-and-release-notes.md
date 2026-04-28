# PRD: Metrics, Release Notes, and Feature Numbering

## Summary

etc has gained traction with non-engineers — SMEs, PMs, and other non-developer roles are now driving `/spec` and `/build` end-to-end and reporting that they ship work they could not have shipped before. The harness has no mechanism to prove this claim: there are no outcome metrics, release notes are written by hand or skipped, feature directories are slug-only without stable IDs, and there is no audit trail beyond raw git history. This PRD defines a minimum-viable layer that turns the anecdote into evidence — three coupled features that ship in sequence: feature numbering (`F<NNN>-<slug>`), automatic release-note generation at `/build` close, and outcome-driven metrics surfaced via a `/metrics` command.

The architectural commitment is a three-layer split with one source of truth per layer. **Process** metrics derive deterministically from git tags laid down by the harness at known points; **outcome** metrics derive from a structured, machine-readable `value-hypothesis.yaml` written at `/spec` time and validated against measured evidence post-ship; **cost/activity** metrics derive from a per-project SQLite telemetry database. The headline metric is *"% of shipped features whose value hypothesis was validated within its window,"* broken out by author role (Engineer, SME, PM, Designer, …) captured via a new question in the `/spec` Socratic loop. Anti-Goodhart by construction: the harness writes tags automatically, demands a hypothesis at spec time, and skips legacy features in the outcome layer rather than letting them dilute the rate.

This work also formalizes the feature directory as the unit of audit. Every artifact about feature `F042` — spec, value hypothesis, tasks, build phases, release notes, lessons learned, hotfixes — lives under `.etc_sdlc/features/F042-<slug>/`. Cross-references between artifacts cite by stable ID; slugs are mutable, IDs are not. The 9 existing slug-only features in `.etc_sdlc/features/` are grandfathered; `F<NNN>` numbering applies forward-only.

## Scope

### In Scope

- **Feature directory naming:** `F<NNN>-<slug>` allocated by `/spec` (3-digit zero-padded, race-free via atomic `mkdir`)
- **Author-role capture:** a new Pattern B question added to the `/spec` Socratic loop with options (SME, Engineer, PM, Designer, Other free-form); written to `state.yaml` and `value-hypothesis.yaml`
- **`value-hypothesis.yaml` emission at `/spec`:** structured fields (who, current_cost, predicted, how_we_know, status, validation, schema_version) written to `.etc_sdlc/features/F<NNN>-<slug>/`
- **Git auto-tagging:** 5 tag points under the `etc/feature/F<NNN>/*` namespace, written from inside the `/spec` and `/build` skill bodies (spec finalization, phase start/done, release, hotfix completion)
- **Release notes:** `release-notes.md` generated at `/build` Step 7/8 terminal close, citing PRD ID, phases closed, AC pass/fail summary, deferred items
- **Three-layer metrics architecture:** process (git tags), outcome (`value-hypothesis.yaml` + validation evidence), cost (`.etc_sdlc/telemetry.db` SQLite)
- **`/metrics` skill:** new skill at `skills/metrics/SKILL.md`, registered in `spec/etc_sdlc.yaml`, emits a weekly markdown report unifying the three layers; broken out by author role
- **Validation-evidence CLI:** extension to `~/.claude/scripts/tasks.py` (or sibling) supporting `validate <feature_id> --measured <value> --evidence <path|url>`; updates `value-hypothesis.yaml` `status` and `validation.*` fields
- **Telemetry DB:** `.etc_sdlc/telemetry.db` (SQLite) created on first hook write; schema covers token spend, agent-invocation counts, build durations, hotfix events
- **Schema versioning:** integer `schema_version: 1` field on `value-hypothesis.yaml` for forward compatibility
- **Grandfather migration:** 9 existing slug-only feature directories remain unchanged; `/metrics` outcome layer skips features without `value-hypothesis.yaml`

### Out of Scope

- Cross-project metrics aggregation (`/metrics --global`) — deferred to a future PRD
- Phone-home or remote telemetry — all data stays local in v1
- Real-time dashboards, web UI, or interactive visualization
- Backfill of `value-hypothesis.yaml` for legacy features (grandfathered = skipped)
- Auto-validation of hypotheses — humans run `tasks.py validate` with measured values
- Retroactive renumbering of existing slug-only features to `F<NNN>` form
- Hard schema enforcement on `T<NNN>` task IDs and `H<NNN>` hotfix IDs (the brief named these as conventions; v1 ships only `F<NNN>` enforcement)
- Tag pruning, archival, or rollup tooling for long-lived projects (`--prune-pre-vN` deferred)
- Replacing or deprecating any existing `/build` Step 7/8 behavior — release-notes generation is additive

## Requirements

### BR-001: Feature ID allocation
Every feature created via `/spec` receives a project-scoped feature ID of the form `F<NNN>` (3-digit zero-padded, e.g., `F001`). The ID is computed as `max(existing F-IDs in .etc_sdlc/features/) + 1`. The feature directory is named `F<NNN>-<slug>` where `<slug>` is the kebab-case spec title.

### BR-002: ID immutability
A feature's `F<NNN>` ID is fixed at creation time. The harness never renumbers, reuses, or reassigns IDs. Slug renames are permitted (the slug is purely cosmetic in the directory name); ID renames are forbidden.

### BR-003: Atomic ID allocation
Concurrent `/spec` invocations on the same project must receive distinct IDs. Allocation uses POSIX atomic `mkdir()` semantics: an attempt to create `F<NNN>-<slug>` that returns `EEXIST` triggers a re-read of the maximum and a retry at `F<NNN+1>`.

### BR-004: Author-role attribution
Every `/spec` invocation captures an author role via a new Pattern B question in the Socratic loop. Roles offered: SME, Engineer, PM, Designer, Other (free-form). The value is written to `state.yaml`, `value-hypothesis.yaml.author_role`, and is queryable by `/metrics`.

### BR-005: Mandatory value hypothesis
Every `/spec` session that writes `spec.md` also writes `value-hypothesis.yaml` in the same feature directory. The file contains, at minimum: `schema_version`, `feature_id`, `author_role`, `who`, `current_cost`, `predicted`, `how_we_know`, `status`, `validation`. If the user cannot answer a hypothesis field, `/spec` prompts (Pattern B) until all required fields are populated; the file is never written with placeholders.

### BR-006: Hypothesis schema versioning
`value-hypothesis.yaml` carries an integer `schema_version` field (initial value: `1`). Readers (notably `/metrics`) accept the current and prior versions; unknown future versions log a warning and skip the file rather than crashing.

### BR-007: Canonical git tag points
The harness lays down git tags at exactly 5 lifecycle moments, all under the `etc/feature/F<NNN>/*` namespace:
1. `etc/feature/F<NNN>/spec` — at `/spec` Phase 5 completion
2. `etc/feature/F<NNN>/build/phase-<N>/start` — at `/build` Step 6 wave entry per phase
3. `etc/feature/F<NNN>/build/phase-<N>/done` — at `/build` Step 6 wave exit per phase
4. `etc/feature/F<NNN>/release` — at `/build` Step 7 terminal-phase close
5. `etc/feature/F<NNN>/hotfix/H<MMM>` — at `/hotfix` completion

### BR-008: Tag append-only
Tags written by the harness are never deleted, retagged, or rewritten. Tag history is the audit trail; mutation breaks deterministic process metrics.

### BR-009: Mandatory release notes
Every `/build` that successfully closes its terminal phase writes `release-notes.md` to the feature directory. The file rolls up: PRD title and ID, phases closed, per-phase AC pass/fail summary citing each completion report, deferred items, and known limitations.

### BR-010: Three-layer metric separation
`/metrics` reads three independent sources and reports per layer: **process** (from git tags), **outcome** (from `value-hypothesis.yaml` + validation evidence), **cost/activity** (from `.etc_sdlc/telemetry.db`). The layers do not cross-derive — outcome metrics are never inferred from cost data, and vice versa.

### BR-011: Validation lifecycle
`value-hypothesis.yaml.status` follows a fixed state machine: `pending` (initial) → `{validated | invalidated}` (set by `tasks.py validate <id>`) or → `unmeasured` (auto-set by `/metrics` when `window_days` has elapsed since the `release` tag without an explicit validation).

### BR-012: Author-role-broken-out reporting
`/metrics` segments the headline rate (% hypothesis-validated) and supporting metrics by author role. Reports show counts and percentages per role, with totals.

### BR-013: Grandfather skip in outcome layer
Features without `value-hypothesis.yaml` (the 9 grandfathered legacy features, plus any feature not produced by `/spec`) are excluded from the outcome-metric layer. They may appear in process metrics (if they have `etc/feature/...` tags) and cost metrics (if telemetry events exist), but they never appear in the validated/invalidated/unmeasured counts.

### BR-014: Per-project locality
All metrics data — telemetry DB, value-hypothesis files, tags, release notes — lives under the project's working tree (`.etc_sdlc/` and `.git/`). Nothing is written to `~/.claude/` or any global path for metrics purposes. No phone-home in v1.

## Acceptance Criteria

1. **AC-001** — Given `/spec` is invoked with a feature title, when the spec is finalized at Phase 5, then `.etc_sdlc/features/F<NNN>-<slug>/` exists where `F<NNN>` is `max-existing + 1` zero-padded to 3 digits and `<slug>` is the kebab-case title.
2. **AC-002** — Given two `/spec` invocations run concurrently in the same project, when both attempt allocation, then they receive distinct `F<NNN>` IDs and both succeed.
3. **AC-003** — Given `/spec` is invoked, when the Socratic loop runs, then a Pattern B question "What's your role?" is asked with options {SME, Engineer, PM, Designer, Other free-form}; the answer is written to `state.yaml.author_role` and `value-hypothesis.yaml.author_role`.
4. **AC-004** — Given `/spec` finalizes at Phase 5, then `value-hypothesis.yaml` exists with all required fields populated: `schema_version`, `feature_id`, `author_role`, `who`, `current_cost`, `predicted`, `how_we_know`, `status: pending`, `validation: {measured_at: null, measured_value: null, evidence: null}`.
5. **AC-005** — Given any required hypothesis field is missing during `/spec` finalization, when Phase 5 begins, then `/spec` prompts via Pattern B until every required field has a non-null value; `spec.md` is NOT written until `value-hypothesis.yaml` is complete.
6. **AC-006** — Given a `value-hypothesis.yaml` with `schema_version: 1`, when `/metrics` reads it, then it is processed; given `schema_version > 1`, when `/metrics` reads it, then it logs a warning and excludes the file from the report.
7. **AC-007** — Given `/spec` completes Phase 5 for feature `F<NNN>`, when Phase 5 finalizes, then git tag `etc/feature/F<NNN>/spec` is created at the current HEAD commit.
8. **AC-008** — Given `/build` enters Step 6 for wave `N` of feature `F<NNN>`, when the wave begins, then `etc/feature/F<NNN>/build/phase-<N>/start` is created; when the wave completes successfully, then `etc/feature/F<NNN>/build/phase-<N>/done` is created.
9. **AC-009** — Given `/build` closes the terminal phase for feature `F<NNN>`, when Step 7 succeeds, then `etc/feature/F<NNN>/release` is created.
10. **AC-010** — Given any tag under `etc/feature/...` exists, when the harness operates, then no harness code path deletes, force-updates, or moves the tag.
11. **AC-011** — Given `/build` closes the terminal phase for feature `F<NNN>`, when Step 7/8 emits artifacts, then `.etc_sdlc/features/F<NNN>-<slug>/release-notes.md` exists and contains: PRD title and ID, list of phases closed, per-phase AC pass/fail summary citing each completion-report path, deferred items, and known limitations.
12. **AC-012** — Given `/metrics` is invoked, when it runs, then it reads exactly three sources (git tags via `git for-each-ref refs/tags/etc/`, `value-hypothesis.yaml` files in `.etc_sdlc/features/*/`, `.etc_sdlc/telemetry.db`) and emits three labeled sections (Process, Outcome, Cost) with no cross-derivation between layers.
13. **AC-013** — Given a feature `F<NNN>` has `value-hypothesis.yaml` with `status: pending`, when the user runs `tasks.py validate F<NNN> --measured <value> --evidence <path|url>`, then the file's `status` is set to `validated` if the measured value crosses the predicted threshold (per `direction`) or `invalidated` otherwise, `validation.measured_at` is set to current ISO-8601 UTC timestamp, `validation.measured_value` is set to `<value>`, `validation.evidence` is set to `<path|url>`.
14. **AC-014** — Given a feature's `value-hypothesis.yaml` has `status: pending` and `(now - release_tag_date) > window_days`, when `/metrics` runs, then the file's `status` is auto-updated to `unmeasured` before the report is computed.
15. **AC-015** — Given `/metrics` is invoked, when the report is rendered, then the headline metric (% hypothesis-validated) is shown with a breakdown by `author_role` plus an overall total, with both counts and percentages.
16. **AC-016** — Given a feature directory has no `value-hypothesis.yaml`, when `/metrics` runs, then the feature is excluded from outcome-layer counts (validated/invalidated/unmeasured/total) but may appear in process and cost layers.
17. **AC-017** — Given `/metrics` is invoked, when it gathers data, then no read or write occurs outside the project working tree (no `~/.claude/` writes, no network calls).
18. **AC-018** — Given the harness writes a telemetry event, when the event is recorded, then it lands in `.etc_sdlc/telemetry.db` with at minimum: `event_id` (UUID), `feature_id` (nullable), `event_type` (controlled enum), `timestamp` (ISO-8601 UTC), `payload` (JSON), `schema_version` (integer).
19. **AC-019** — Given `spec/etc_sdlc.yaml` registers `/metrics` and the harness is recompiled, when `python3 compile-sdlc.py` runs, then `dist/skills/metrics/SKILL.md` is produced; when `./install.sh` runs, then `~/.claude/skills/metrics/SKILL.md` exists.

## Edge Cases

1. **Non-git repository.** Given `/spec` or `/build` runs in a directory without `.git/`, tag writes (BR-007) cannot succeed. The harness logs a warning, skips the tag write, and continues; the feature's process-metric layer reports as "untagged" rather than failing the whole pipeline.
2. **Repository with no commits yet.** Given `/spec` runs before the first commit (no HEAD), tag writes cannot reference a commit. Behavior is identical to (1): warn, skip tag, continue.
3. **`/spec` aborted before Phase 5.** Given the user kills the session during the Socratic loop, the feature directory is left intact for `/spec --resume`. `F<NNN>` is consumed (allocator does not roll back); the next `/spec` allocates `F<NNN+1>`. ID gaps are acceptable; ID reuse is not.
4. **`/build` failure mid-execution.** Given `/build` halts at an escalated wave or failed test, neither `etc/feature/F<NNN>/release` nor `release-notes.md` is written. Phase start/done tags remain. The feature shows in process metrics as "incomplete." `/build --resume` continues from the last completed wave.
5. **Corrupt or YAML-invalid `value-hypothesis.yaml`.** `/metrics` logs an error naming the file and the parser message, excludes the feature from the outcome layer, and continues. Build-time tooling refuses to write to the file until it parses.
6. **F-ID exhaustion at `F999`.** v1 supports 999 features per project. The next allocation errors clearly: "Project has reached the v1 feature ID ceiling (999). Upgrade to 4-digit IDs is a future PRD." No silent overflow.
7. **Author role "Other" with custom value.** `/metrics` groups all distinct "Other" values under a single `Other` bucket in the role breakdown. Distinct custom values are listed as a footnote; they do not get individual rows.
8. **SQLite concurrent write contention.** DB opened in WAL mode (`PRAGMA journal_mode=WAL`). Write retries on `SQLITE_BUSY` with exponential backoff (max 3 attempts). On exhaustion, the event is logged to `.etc_sdlc/telemetry-overflow.jsonl` for later replay.
9. **Re-`/spec` on an existing slug.** `/spec` refuses with "Feature `F<NNN>-<slug>` already exists. Use `/spec --refine F<NNN>` to revise it, or pick a new title." No silent overwrite, no re-allocation.
10. **Validation threshold direction mismatch.** Given `predicted.direction: decrease` and `predicted.threshold: 30` but `--measured 45`, the comparison `45 <= 30` is false → `status: invalidated`. Incoherent direction values (not `increase` or `decrease`) are rejected at the CLI with a clear message.

## Technical Constraints

**Codebase patterns to follow:**
- Skills live at `skills/<name>/SKILL.md` and are registered in `spec/etc_sdlc.yaml`. Recompile via `python3 compile-sdlc.py spec/etc_sdlc.yaml`; deploy via `./install.sh`.
- Modifications to existing skills are direct edits to source files in this repo, not the installed copies in `~/.claude/skills/`. Compile + install pipeline is authoritative.
- CLI extensions follow the `~/.claude/scripts/tasks.py` pattern.
- Tests live at `tests/test_<feature>.py`. `tests/test_spec_three_state.py` is the reference.
- Python 3.11+, `uv`-managed; tests run via `uv run python -m pytest`.
- TDD enforced by PreToolUse hook (`check-test-exists.sh`); test must exist before source edit.
- Identifier conventions: kebab-case slugs/filenames; snake_case Python; 3-digit zero-padded numeric IDs.

**Libraries / dependencies (no new third-party additions for v1):**
- SQLite via Python stdlib (`sqlite3`) for `.etc_sdlc/telemetry.db`. `PRAGMA journal_mode=WAL` for concurrent access.
- PyYAML for `value-hypothesis.yaml` read/write (already in scope).
- POSIX `os.mkdir` for atomic feature-ID allocation. No file-locking library.
- `subprocess` for `git tag` and `git for-each-ref`. No GitPython or libgit2 binding.

**INVARIANTS.md rules that apply:**
`INVARIANTS.md` does not currently exist at repo root, so no existing invariants apply. Candidate invariants for a future PRD: every `value-hypothesis.yaml` has a `schema_version` integer; every `release-notes.md` has a corresponding `etc/feature/F<NNN>/release` tag; every `F<NNN>` ID maps to exactly one directory.

**Gray-area resolutions (full detail in `gray-areas.md`):**
- **GA-001 (user)** — author role captured inside the `/spec` Socratic loop (Pattern B). Roles: SME, Engineer, PM, Designer, Other.
- **GA-002 (user)** — existing 9 slug-only features grandfathered. `F<NNN>` numbering forward-only.
- **GA-003 (user)** — `/metrics` outcome layer skips features without `value-hypothesis.yaml`.
- **GA-004 (research)** — git tag writes performed inside skill bodies, not in PreToolUse/Stop hooks.
- **GA-005 (research)** — validation-evidence collection extends `tasks.py` CLI pattern.
- **GA-006 (research)** — concurrent feature-ID allocation handled by POSIX atomic `mkdir()`.

**Pattern A / Pattern B compliance:**
Every user prompt in `/spec`'s new role-capture flow uses Pattern B. The `tasks.py validate` CLI is non-interactive. `/metrics` is non-interactive output.

## Security Considerations

1. **CLI input validation (`tasks.py validate`).** Feature-ID regex-validated against `^F\d{3}$`. `--measured` parsed as numeric (int or float) with explicit type check before write. `--evidence` canonicalized via `os.path.realpath` and rejected if it resolves outside the project working tree. Malformed input rejected with clear errors.
2. **Path traversal prevention.** All harness-written paths and user-input paths are resolved relative to the project root. Symbolic links are not followed when resolving `--evidence` paths. Absolute paths outside the project root are rejected at the CLI boundary.
3. **Commercial-sensitive data in `value-hypothesis.yaml`.** `who` / `current_cost` / `predicted` may contain customer names, financial baselines, market segmentation. Documented risk: projects handling sensitive content should add `.etc_sdlc/` to `.gitignore` or restrict repo access. v1 ships no encryption-at-rest, redaction, or content classification (deferred).
4. **Telemetry DB confidentiality.** `.etc_sdlc/telemetry.db` may capture token counts, prompt fragments, agent context. Per-project locality (BR-014) is the v1 control; project git permissions govern exposure. No phone-home, no `~/.claude/` writes for metrics. Recommend gitignore for sensitive projects.
5. **Tag mutation and namespace integrity.** Tags under `etc/feature/...` are append-only by harness convention (BR-008, AC-010). v1 does not ship a server-side pre-receive hook. Risk: upstream `git push --force` could rewrite tags and corrupt process metrics. Mitigation: documentation; future PRD optional pre-receive hook template.
6. **Schema enforcement at telemetry write time.** Every row inserted into `.etc_sdlc/telemetry.db` is validated against the v1 schema (column types, required-field presence, `event_type` enum). Malformed payloads rejected and routed to `.etc_sdlc/telemetry-overflow.jsonl`. The DB never accepts schema violations.
7. **Secrets in `--evidence`.** Users may inadvertently paste credentials, tokens, or internal URLs. v1 ships a CLI help note. No automated secret scanning (deferred to a future security PRD).
8. **Author-role free-form input ("Other") sanitization.** Length-capped at 64 characters; control characters stripped; YAML/shell escape characters never passed through unsanitized. `/metrics` aggregates "Other" values without rendering raw content into shell commands.

## Module Structure

**Files to MODIFY:**
- `skills/spec/SKILL.md` — Pattern B role-capture (Phase 1); `feature_id.allocate_next()`, hypothesis-field prompting, `value-hypothesis.yaml` write, `etc/feature/F<NNN>/spec` tag, `state.yaml.author_role` (Phase 5).
- `skills/build/SKILL.md` — `etc/feature/F<NNN>/build/phase-<N>/start|done` tags (Step 6); `etc/feature/F<NNN>/release` tag and `release-notes.md` via `release_notes.build()` (Step 7); summary names release artifacts (Step 8).
- `skills/hotfix/SKILL.md` — `etc/feature/F<NNN>/hotfix/H<MMM>` tag at completion.
- `spec/etc_sdlc.yaml` — Register `metrics` skill under `skills:` with `source: skills/metrics/SKILL.md`.
- `scripts/tasks.py` — `validate <feature_id> --measured <value> --evidence <path|url>` subcommand; input validation; atomic update of `value-hypothesis.yaml`.
- `README.md` — Add `/metrics` to skills list; update install summary.

**Files to CREATE:**
- `skills/metrics/SKILL.md` — Non-interactive skill. Reads three layers; emits weekly markdown report with role breakdown. Auto-transitions `pending → unmeasured` past window.
- `scripts/feature_id.py` — `allocate_next(features_dir, slug) -> (feature_id, feature_path)` (POSIX-atomic mkdir, EEXIST retry, F999 ceiling); `slugify(title) -> str`.
- `scripts/value_hypothesis.py` — `load`, `dump`, `validate_schema`, `transition_status`. Schema-aware; rejects malformed YAML and invalid transitions.
- `scripts/telemetry.py` — `connect(db_path)` (WAL mode), `record(event)` (validation, retry, overflow JSONL fallback), `aggregate(filter)`.
- `scripts/release_notes.py` — `build(feature_dir) -> str`. Walks `build/phase-*/completion-report.md`; assembles roll-up.
- `scripts/git_tags.py` — `write_tag(name, ref="HEAD")` with non-git/no-HEAD graceful degradation; `list_etc_tags()`.

**Tests to CREATE:**
- `tests/test_feature_id.py` — atomic allocator, race-on-EEXIST, F999 ceiling, slugify edges.
- `tests/test_value_hypothesis.py` — schema-version handling, status transitions, malformed YAML.
- `tests/test_telemetry.py` — WAL setup, concurrent-write retry, overflow fallback, schema rejection.
- `tests/test_release_notes.py` — roll-up correctness, missing-phase handling, citation paths.
- `tests/test_git_tags.py` — happy path, non-git/no-HEAD degradation, immutability negative test.
- `tests/test_spec_role_capture.py` — Pattern B role question, "Other" sanitization, file writes.
- `tests/test_build_release.py` — release tag + notes on terminal close; neither on mid-build failure.
- `tests/test_tasks_validate.py` — CLI arg validation, validated/invalidated transitions per direction.
- `tests/test_metrics.py` — three-layer aggregation, role breakdown, grandfather skip, unmeasured auto-transition.

**Documentation to CREATE:**
- `docs/standards/process/feature-numbering.md` — F<NNN> standard: ID stability, slug mutability, allocation rule, ceiling.
- `docs/standards/process/value-hypothesis.md` — schema, lifecycle, anti-Goodhart rationale, examples.

## Research Notes

**Codebase findings (full detail in `research/codebase.md`):**
- `/spec` Phase 5 and `/build` Steps 6–8 are the integration points for tag writes and artifact emission.
- 9 existing slug-only features in `.etc_sdlc/features/` (grandfathered).
- 8 existing version-only git tags; `etc/feature/*` namespace is collision-free.
- `INVARIANTS.md` does not exist at repo root; new invariants deferred to a future PRD.
- `~/.claude/scripts/tasks.py` is the canonical CLI extension target.
- Python 3.11+, uv-managed; sqlite3 stdlib and PyYAML are sufficient — no new third-party dependencies.

**Best practices applied (canonical):**
- POSIX atomic `mkdir()` for race-free ID allocation.
- Integer `schema_version` for forward-compatible YAML schemas.
- Org-prefixed (`etc/`) tag namespace for filterability.
- Anti-Goodhart via mechanical enforcement: harness writes tags automatically; hypothesis required at spec time.

**Antipatterns:**
`.etc_sdlc/antipatterns.md` does not exist. No prior antipatterns to incorporate.

**Gray-area resolutions:** 6 entries in `gray-areas.md` (3 user-decided, 3 research-decided).
