# PRD: F020 — Language-Agnostic Harness via Profile Architecture

## Summary

etc was built by Python engineers for Python codebases. Hooks hardcode `pytest`/`mypy`/`ruff`; standards cite ruff rule codes; agent manifests bake in `uv run` invocations. The audit at `docs/audits/F022-language-coupling-audit.md` inventoried 24 hard-coupled surfaces. The cost: an operator who installs etc on a TypeScript / Go / Rust / React Native / C++ / Terraform codebase gets a half-working harness — DOMAIN.md and PROJECT.md author correctly, but TDD gates silently no-op, `verify-green` never fires, and standards read as "this codebase should be Python." That ceiling caps etc's reach to a single ecosystem.

F020 introduces a **profile architecture** that makes language and framework support a first-class harness primitive. A profile is a thin wrapper that names a target stack (python, typescript, go, rust, terraform, k8s, markdown, ...), declares its detection markers (`pyproject.toml`, `package.json`, `go.mod`, `*.tf`, ...), binds the rule set to tooling (the universal "function size limit" rule binds to ruff `PLR0915` for python, eslint `max-lines-per-function` for typescript, golangci-lint `funlen` for go), and points to the community-canonical authority (`google/styleguide`, `rust-lang/api-guidelines`, Airbnb JS, PEP 8). etc does NOT author its own style guides — it adopts and cites them.

Universal RULES live at `standards/code/*.md` (clean-code, error-handling, import-discipline — concepts that survive any language). Tool BINDINGS live under `standards/code/profiles/<profile>/*-bindings.md`. Detection runs at install time and per-session; monorepos with multiple stacks activate every detected profile, scoped by file path. Hooks that find no profile emit a stderr warning and exit cleanly — closing the silent-skip failure mode where non-Python work historically escaped enforcement. The Python migration ships first as profile-0 (no regression on the existing 1014-test suite); TypeScript ships next as the proof case for a second profile; Go, Rust, Terraform, Markdown follow as separate F-features. Success: an operator runs `/init-project` on a React Native / Rust / C++ codebase and verify-green.sh fires their native test command without manual config.

## Scope

### In Scope

- **Profile architecture** — the concept, the directory layout (`standards/code/profiles/<profile>/`), the bindings file format, and the contract a new profile must satisfy to be considered "shipped" (the specific minimum-shape contract is set by F021 typescript-profile-spec; this spec defines that the contract EXISTS and is per-profile)
- **Profile detection** — `scripts/detect_profiles.py` (new) walks the repo root, returns the list of activated profiles based on marker files (`pyproject.toml`, `package.json`, `go.mod`, `Cargo.toml`, `pom.xml`, `Gemfile`, `*.tf`, `Package.swift`)
- **Rule-vs-binding split** — every standard under `standards/code/*.md` is audited for Python-vocabulary leakage; rules stay at top level, bindings move under `profiles/<profile>/<rule>-bindings.md`. This applies to `clean-code.md`, `error-handling.md`, `import-discipline.md` in this spec. Other standards (testing/*, process/*) audit follows in their own per-standard PRDs
- **Hook generalization** — `verify-green.sh`, `check-test-exists.sh`, `check-code-quality.sh`, `check-seam-evidence.sh`, `check-completion-discipline.sh` all gain profile-aware dispatch. Each gate consults the active profile(s) and runs the appropriate tooling, OR emits a stderr WARN and exits 0 when no profile matches
- **Python migration as profile-0** — current Python behavior preserved verbatim; existing 1014 tests must continue passing. No new functionality for Python operators; the architecture moves underneath them without disruption
- **Agent manifest updates** — `backend-developer.md`, `code-reviewer.md`, `code-simplifier.md` frontmatter language fields become profile-aware. Manifest required-reading lists reference the rule set; the active profile's bindings get injected at dispatch time
- **Operator-facing override file** — `.etc_sdlc/profiles.yaml` (optional) lets the operator pin profiles, exclude paths, or add a profile that auto-detection missed. The schema is defined here; the population is per-profile and lives in follow-up specs

### Out of Scope

- **Per-profile content** — which canonical guide each non-Python profile cites (Rust API Guidelines vs the official Rust style guide; Airbnb vs Google for JavaScript) is decided in the per-profile follow-up spec. This spec ensures the architecture supports any choice
- **Profile sequencing** — TypeScript next vs Go next is a roadmap decision, not a spec decision
- **Language servers, IDE integrations, refactoring tools** — etc consumes existing tooling; it does not build its own
- **Esoteric languages without canonical toolchains** — etc declines profiles for languages that lack a community-standard linter, type checker, or test runner. The bar is "does this language have an `awesome-guidelines` entry with citable authority?" If no, no profile
- **etc-authored style guides** — etc adopts and cites; it never authors. If a language's community canon is contested (multiple competing style guides), the per-profile spec picks one and documents why
- **Migration of testing/ standards** — `testing-standards.md`, `test-isolation.md`, `seam-evidence.md`, `llm-evaluation.md` are pytest-shaped today. Their generalization is its own follow-up F-feature; they continue to function as today for Python operators and are explicitly NOT in F020's scope

## Requirements

### BR-001: Profile is a first-class harness primitive
Every supported language, framework, format, or platform is represented by a profile. A profile is a directory at `standards/code/profiles/<profile>/` containing at minimum a `bindings.md` file and a `detection.yaml` file. Profiles MUST NOT be implicit or inferred; if no `standards/code/profiles/<profile>/` exists for a stack, that stack is unsupported and the operator sees the WARN-and-skip behavior per BR-008.

### BR-002: Universal rules separate from per-profile bindings
`standards/code/clean-code.md`, `standards/code/error-handling.md`, `standards/code/import-discipline.md` are audited and any Python-vocabulary (specific ruff codes, mypy syntax, `raise/except` examples, `__future__` references) is moved to `standards/code/profiles/python/<rule>-bindings.md`. The top-level rule file states the universal RULE; the bindings file states the per-tool ENFORCEMENT. Agents read both at dispatch time.

### BR-003: Detection is automatic for the common cases
`scripts/detect_profiles.py` (new) walks the repo root in a deterministic order looking for marker files. The marker → profile mapping is declared in each profile's `detection.yaml`. The detector returns a list of activated profile names. It MUST be deterministic — same repo state, same output, same order.

### BR-004: Monorepo detection activates every detected profile
A repo with `pyproject.toml` + `package.json` activates both `python` and `typescript`. Hooks scope their checks by file path — `.py` files go through python gates, `.tsx` files go through typescript gates. The detector returns all matches; the hook layer decides which apply to which file.

### BR-005: Operator override file is supported but optional
`.etc_sdlc/profiles.yaml` (optional) accepts: (a) `pin:` — explicit profile list overriding auto-detect; (b) `exclude_paths:` — paths excluded from a specific profile's gates; (c) `add:` — profiles to activate that auto-detect missed. Schema is defined in F020; the file is absent for 95% of operators.

### BR-006: Profile-aware hook dispatch
Every Python-coupled hook (`verify-green.sh`, `check-test-exists.sh`, `check-code-quality.sh`, `check-seam-evidence.sh`, `check-completion-discipline.sh`) consults the active profile list. For each file the hook receives, it looks up the file's responsible profile via path matching, then invokes that profile's `<gate>.sh` script (e.g., `profiles/python/verify-green.sh`). Bash dispatch table; no Python imports.

### BR-007: Python migration is profile-0 with zero regression
Existing Python behavior is preserved verbatim. The current 1014 tests must continue passing after migration. No new functionality is added for Python operators in this PRD; the architecture moves under them. Migration is a code reorganization, not a feature change for the Python case.

### BR-008: No-profile-detected fallback is WARN-and-skip
When a hook fires on a file with no matching profile, it MUST emit a stderr WARN line naming the file path and the gate that did not apply, then exit 0. Silent skip is forbidden (closes the recurring "silent gap" failure mode). Hard-block is forbidden (greenfield repos must remain workable).

### BR-009: etc adopts canonical style guides; never authors its own
Every per-profile bindings file MUST cite at least one canonical external authority (Google styleguide, Airbnb, Mozilla, Rust API Guidelines, official language docs, awesome-guidelines entries). etc does NOT publish its own style rules for any supported language; it adopts the community canon and binds tooling to it.

### BR-010: Esoteric languages are out of bounds
A profile is only accepted into etc if the target language has (a) a published canonical style guide or community-recognized authority, AND (b) a community-standard linter, AND (c) a community-standard test runner. Languages failing any of these bars are explicitly declined.

### BR-011: Detection runs at install time AND per session
`install.sh` calls `detect_profiles.py` during setup and writes the result to `.etc_sdlc/profiles.lock` (cached). Each agent session re-checks for staleness (newer marker file mtime than `profiles.lock`) and re-runs detection on stale state. Cache invalidation: any marker-file change triggers re-detection.

### BR-012: Agent manifests are profile-aware
`agents/backend-developer.md`, `agents/code-reviewer.md`, `agents/code-simplifier.md` frontmatter no longer names a specific language. The body reads the active profile from `state.yaml` (or `profiles.lock`) and adapts its instructions accordingly. Agents read the rule set + the active profile's bindings.

### BR-013: Tier-0 standards must not contain Python vocabulary post-migration
After the python profile is extracted, `clean-code.md`, `error-handling.md`, `import-discipline.md` MUST NOT reference ruff codes, mypy syntax, `pytest` markers, or `__future__` annotations. Any remaining Python-specific content is moved to `profiles/python/<rule>-bindings.md`. A test enforces this by greping the top-level files for Python tokens.

### BR-014: README and onboarding docs reflect language-agnostic positioning
`README.md` and `skills/init-project/SKILL.md` must remove or qualify any language that suggests etc is Python-only. The README front matter explicitly names supported profiles. Onboarding docs describe profile selection as a first-class concept.

## Acceptance Criteria

1. **AC-001: Profile directory layout exists.** `standards/code/profiles/python/` exists and contains: `detection.yaml`, `clean-code-bindings.md`, `error-handling-bindings.md`, `import-discipline-bindings.md`, `verify-green.sh`, `check-test-exists.sh`, `check-code-quality.sh`, `check-seam-evidence.sh`, `check-completion-discipline.sh`. This is the reference shape every future profile follows. *surface_status: backend_only*

2. **AC-002: Universal rules contain no Python vocabulary.** `standards/code/clean-code.md`, `standards/code/error-handling.md`, `standards/code/import-discipline.md` contain ZERO references to: `ruff`, `mypy`, `pytest`, `__future__`, `pyproject.toml`, specific ruff rule codes (e.g., `PLR0915`), `raise/except` code blocks. A new test `tests/test_rule_vocabulary_purity.py` enforces this via grep. *surface_status: backend_only*

3. **AC-003: `scripts/detect_profiles.py` returns deterministic profile list.** Given a repo with marker files, `python3 scripts/detect_profiles.py` prints one profile name per line to stdout, sorted alphabetically. Same repo state always produces the same output. Exits 0 with empty stdout when no profiles match. *surface_status: backend_only*

4. **AC-004: Monorepo activates every detected profile.** A test fixture repo with both `pyproject.toml` and `package.json` invokes `detect_profiles.py` and receives `python\ntypescript\n` on stdout. Order is alphabetical. *surface_status: backend_only*

5. **AC-005: Operator override file `.etc_sdlc/profiles.yaml` is honored.** When `.etc_sdlc/profiles.yaml` declares `pin: [python]`, `detect_profiles.py` returns only `python` even if `package.json` is also present. When `add: [terraform]` is declared, terraform is included even without `*.tf` files. When `exclude_paths: ["legacy/"]` is declared under a profile, that profile's gates skip files matching those paths. *surface_status: backend_only*

6. **AC-006: All five Python-coupled hooks dispatch by profile.** `verify-green.sh`, `check-test-exists.sh`, `check-code-quality.sh`, `check-seam-evidence.sh`, `check-completion-discipline.sh` each read the active profile list, map the input file to a profile via path matching, and delegate to that profile's `<gate>.sh`. The top-level hook script becomes a dispatch table. *surface_status: backend_only*

7. **AC-007: Existing 1014 tests pass after migration.** After the python profile is extracted and hooks become profile-aware, `uv run pytest` shows 1014 passing tests (or more — new architecture tests are additive). No existing test is deleted or skipped. No existing test changes its assertion to match the migrated paths; the migration preserves observable behavior. *surface_status: backend_only*

8. **AC-008: No-profile-detected fallback emits WARN and exits 0.** When a hook fires on a file with no matching profile, it writes a stderr line beginning `[<gate-name>] WARN: no profile matches <file>` and exits 0. A test fixture with no marker files triggers this behavior for each of the five generalized hooks. Silent exit (no stderr) is a test failure; non-zero exit is a test failure. *surface_status: backend_only*

9. **AC-009: Each profile's bindings file cites a canonical authority.** Every `standards/code/profiles/<profile>/*-bindings.md` file contains a `## Source` section naming at least one external URL or document title. The python profile cites Google Python Style Guide + PEP 8 + ruff rule docs. A test enforces the `## Source` section presence. *surface_status: backend_only*

10. **AC-010: Profile-acceptance criteria documented.** `standards/code/profiles/README.md` exists and documents the three-part bar for a new profile: (a) canonical style guide URL, (b) community-standard linter command, (c) community-standard test runner command. Each must be filled before a profile PR is merged. *surface_status: backend_only*

11. **AC-011: `install.sh` writes `profiles.lock`; session re-detects on stale.** `install.sh` invokes `detect_profiles.py` and writes the result to `.etc_sdlc/profiles.lock` with an mtime. A new hook `hooks/check-profiles-fresh.sh` (or equivalent SessionStart logic) compares marker-file mtimes against `profiles.lock`; staler `profiles.lock` triggers re-detection. *surface_status: backend_only*

12. **AC-012: Three agent manifests are profile-aware.** `agents/backend-developer.md` frontmatter no longer says "writes Python conformant to..."; instead it reads the active profile from `state.yaml` (or `profiles.lock`) and adapts. `agents/code-reviewer.md` and `agents/code-simplifier.md` similarly. A test loads each manifest and asserts no hardcoded language token in frontmatter. *surface_status: backend_only*

13. **AC-013: Test enforces no Python vocabulary in tier-0 standards.** `tests/test_rule_vocabulary_purity.py` (new) greps `standards/code/clean-code.md`, `error-handling.md`, `import-discipline.md` for Python tokens. Any hit fails the test with a specific file:line citation. *surface_status: backend_only*

14. **AC-014: README and `/init-project` reflect profile-based positioning.** `README.md` removes the "Python-mature, multi-language pending" framing and replaces it with the supported-profiles list. `skills/init-project/SKILL.md` Phase 1 names profile detection as part of the setup story. Both are reviewable diffs. *surface_status: backend_only*

15. **AC-015: Reference python profile passes the full standards test suite.** The shipped python profile (the migration baseline) is a working reference. Running `pytest tests/test_python_profile_integration.py` (new) loads the profile, exercises each binding through its associated hook, and verifies green for a sample Python codebase. *surface_status: backend_only*

16. **AC-016: `docs/audits/F022-language-coupling-audit.md` is cross-referenced.** The python profile's top-level `README.md` cites the audit as the source-of-record for what was migrated. This keeps the historical decision trail attached to the artifact. *surface_status: backend_only*

17. **AC-017: Migration is a single coherent /build wave per profile.** The python migration (this PRD) ships as one wave (or two, if size demands): no half-migrated state where some hooks dispatch by profile and others don't. Either the architecture is in place across all five hooks + three agents, or the PR is rejected. *surface_status: backend_only*

## Edge Cases

1. **EC-001: Conflicting markers in same repo.** A repo has `pyproject.toml`, `package.json`, AND `go.mod`. All three profiles activate per BR-004. Hooks file-scope by extension/path. The python profile's `verify-green.sh` runs only against `.py` files; typescript against `.tsx`/`.ts`; go against `*.go`. No profile claims the other's files. Test fixture: `tests/fixtures/triple-stack-monorepo/`.

2. **EC-002: Malformed marker file.** `pyproject.toml` exists but is broken TOML; `package.json` exists but is broken JSON. `detect_profiles.py` MUST NOT crash. It logs a stderr WARN naming the file + parse error and treats that profile as not-matched. Other valid markers still activate their profiles. Detection exit 0 (degrade, don't fail). Test: `tests/fixtures/malformed-pyproject/`.

3. **EC-003: `profiles.yaml` pins a profile that doesn't exist.** Operator writes `pin: [pythn]` (typo). `detect_profiles.py` exits 1 with a stderr message naming the typo + the list of available profiles. Subsequent hook invocations see no resolved profile and emit the BR-008 WARN-and-skip behavior. This is loud-fail at install/detect time, soft-fail at hook time.

4. **EC-004: `profiles.yaml` `pin:` overrides auto-detect even when markers exist.** Operator has `pyproject.toml` but pins `pin: [typescript]`. Detection returns ONLY typescript. The python profile is suppressed; `.py` files fall into the no-profile fallback (BR-008 WARN). The pin overrides for a reason — operator's call. Test: fixture with `pyproject.toml` + a `profiles.yaml` pinning typescript.

5. **EC-005: Overlapping profile paths in a monorepo.** A single file matches multiple profiles' path patterns (e.g., a `.py` script in a node project's `scripts/` directory where the node profile claims `scripts/`). Resolution: the profile with the more-specific path match wins. If equally specific, alphabetical order breaks the tie. Document this resolution in `standards/code/profiles/README.md`.

6. **EC-006: `profiles.lock` is stale.** Operator runs `npm install some-new-dep` which adds a `package.json` entry that didn't exist when `install.sh` ran. `profiles.lock` says `[python]`, but `package.json` is now newer than `profiles.lock`. A SessionStart hook (or per-session check in `detect_profiles.py`) compares mtimes; if any marker file is newer than `profiles.lock`, re-detect automatically and rewrite `profiles.lock`. No operator action required.

7. **EC-007: Profile binding references an uninstalled tool.** Python profile's `verify-green.sh` invokes `uv run pytest`, but `uv` isn't installed. The hook MUST emit a stderr line distinguishing this from "no profile matched" — specifically `[verify-green] ERROR: python profile requires 'uv' but it is not on PATH. Install: <pointer-to-canonical-source>`. Exit 1 (not 2) — operator can see the diagnostic and act, but the gate is not silent.

8. **EC-008: Migration upgrade path — pre-existing Python install without profiles.lock.** Operator pulls the F020 upgrade and their existing install lacks `profiles.lock`. First detection writes it. No data loss; no manual intervention. Test: simulate the upgrade path explicitly.

9. **EC-009: Renaming this PRD's allocated ID.** The allocator gave us F020, but task #21 in the operator's backlog labeled "F020 (candidate)" Windows install portability. This spec's allocated ID is canonical; the task list's candidate label is stale. The operator may relabel task #21 to "F021 (candidate)" after F020 ships. No code-level conflict; documentation-level only.

## Technical Constraints

*Architecture-level details defer to `/architect`. The Phase 5 auto-detect picker chained `/architect` after `/spec` completes. /architect will produce `design.md` with detection algorithm specifics, profile-loading sequence, ADRs for the rules-vs-bindings split, hook dispatch table format, and the migration plan as a series of phased commits.*

## Security Considerations

- **Marker-file parsing:** `detect_profiles.py` parses YAML, TOML, JSON from operator-controlled files. Use safe parsers (PyYAML `safe_load`, `tomllib`, standard `json`); never `eval` or `exec`. Reject pathologically nested input.
- **Override file injection:** `.etc_sdlc/profiles.yaml` is operator-authored. `pin`, `add`, `exclude_paths` values flow into shell command construction in hooks. Sanitize all values: reject any value containing shell metacharacters (`;`, `&`, `|`, `$`, backtick, parentheses). Whitelist profile names against the actual `standards/code/profiles/*/` directories.
- **Path traversal in `exclude_paths`:** `exclude_paths: ["../../other-repo"]` must be rejected. Resolve all paths relative to the repo root and reject any that escape.
- **Race conditions in `profiles.lock`:** Two parallel `install.sh` runs or concurrent agent sessions could write `profiles.lock` simultaneously. Use atomic-rename pattern (write to `profiles.lock.tmp`, then `os.rename`).

## Module Structure

*Detailed module structure deferred to `/architect`. High-level shape:*

- **New scripts:** `scripts/detect_profiles.py`, `scripts/profile_loader.py` (or equivalent — exact shape per /architect)
- **New directory tree:** `standards/code/profiles/python/` containing `detection.yaml`, `clean-code-bindings.md`, `error-handling-bindings.md`, `import-discipline-bindings.md`, `verify-green.sh`, `check-test-exists.sh`, `check-code-quality.sh`, `check-seam-evidence.sh`, `check-completion-discipline.sh`, `README.md`, `## Source` sections per binding
- **Modified standards:** `standards/code/clean-code.md`, `standards/code/error-handling.md`, `standards/code/import-discipline.md` — Python vocabulary removed; rule text remains
- **Modified hooks:** `hooks/verify-green.sh`, `hooks/check-test-exists.sh`, `hooks/check-code-quality.sh`, `hooks/check-seam-evidence.sh`, `hooks/check-completion-discipline.sh` — become dispatch tables
- **New hook:** `hooks/check-profiles-fresh.sh` (SessionStart staleness check)
- **Modified agents:** `agents/backend-developer.md`, `agents/code-reviewer.md`, `agents/code-simplifier.md` — frontmatter profile-aware
- **Modified install.sh:** invoke `detect_profiles.py`, write `profiles.lock`
- **New tests:** `tests/test_detect_profiles.py`, `tests/test_rule_vocabulary_purity.py`, `tests/test_python_profile_integration.py`, fixtures under `tests/fixtures/`
- **Modified README + skill:** `README.md`, `skills/init-project/SKILL.md` — profile-based positioning

## Research Notes

### Codebase audit (Phase 0)

Source: `docs/audits/F022-language-coupling-audit.md` (258 lines, shipped 2026-05-15 in commit `a0775c9`).

24 hard-coupled Python surfaces inventoried:
- **5 hooks:** `verify-green.sh`, `check-test-exists.sh`, `check-code-quality.sh`, `check-seam-evidence.sh`, `check-completion-discipline.sh`
- **14 standards:** `python-conventions.md`, `typing-standards.md`, `ruff-audit.md`, `ruff-reference.toml`, `clean-code.md`, `error-handling.md`, `import-discipline.md`, `testing-standards.md`, `test-isolation.md`, `seam-evidence.md`, `llm-evaluation.md`, `definition-of-done.md`, `guardrail-rules.md`, `metrics.md`
- **3 agents:** `backend-developer.md`, `code-reviewer.md`, `code-simplifier.md` (verifier.md has partial detection)
- **2 skills:** `build/SKILL.md`, `implement/SKILL.md`

Key insight from audit: standards split cleanly into RULES (universal: function size, error policy, import hygiene) and BINDINGS (language-specific: ruff codes, mypy syntax). The split is the migration target.

Frontend agents (`frontend-developer.md`, `frontend-dashboard-refactorer.md`) are already TS-coded — proves the multi-language pattern works at the agent layer. Gap is hooks + standards.

### Web research (Phase 2)

- **[Kristories/awesome-guidelines](https://github.com/Kristories/awesome-guidelines)** — curated meta-repo. 40+ programming languages, 8+ web/CMS frameworks, plus categories for API design (HAL, JSON:API, Microsoft REST, Google Cloud API), accessibility (WCAG 2.1), DevOps (SemVer, CI/CD), and documentation (Mailchimp Content Style Guide). Cites Google, Airbnb, Mozilla, Microsoft, Alibaba, Databricks, LinkedIn, Twitter, Uber. **This is the entry-point for sourcing per-profile content.**
- **[google/styleguide](https://github.com/google/styleguide)** — 14 languages with Google authority: C++, C#, Swift, Objective-C, Java, Python, R, Shell, HTML/CSS, JavaScript, TypeScript, AngularJS, Common Lisp, Vimscript. External: Dart, Kotlin. Normative + citable.
- **Per-language canonical sources:** Rust API Guidelines, Go Code Review Comments, PEP 8 + Hitchhiker's Guide, Apple Swift API Design Guidelines, Kotlin coding conventions, Airbnb JS/Ruby/CSS, Mozilla C++/JS.
- **Implication for spec:** etc does NOT need to author style guides — they exist, well-tested, community-canonical. etc adopts and cites. This is the foundation of BR-009 and BR-010.

### Antipatterns check (Phase 2)

`.etc_sdlc/antipatterns.md` is absent in this repository. No prior antipatterns apply.

### Gray-area resolutions (Phase 2.5)

See `gray-areas-spec.md` in this feature directory. Four resolutions:
- GA-001 (naming = `profile`, decided by research)
- GA-002 (rules at top level + bindings under profiles/, decided by user)
- GA-003 (warn + skip on no-profile-detected, decided by user)
- GA-004 (all detected profiles activate scoped by file path in monorepos, decided by user)
