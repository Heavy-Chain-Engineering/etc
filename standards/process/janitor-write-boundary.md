# Janitor Write Boundary

## Status: MANDATORY
## Applies to: The `/janitor` skill (`skills/janitor/SKILL.md`), the janitor fix-subagent (`agents/janitor.md`), and the mechanical boundary check (`scripts/janitor_boundary_check.py`).

To earn Dependabot-grade trust, janitor must be *structurally* unable to touch
anything that matters. Worktree isolation (ADR-001) guarantees janitor cannot
corrupt the operator's working tree; this standard guarantees the *content* of
any janitor PR stays inside a small, flawless-only blast radius. It is the single
source of truth for what janitor may NOT write and how many files one run may
touch (spec BR-006 / BR-013, AC-013).

Both the janitor prompt and `janitor_boundary_check.py` read this file. Neither
hardcodes a copy. If the two ever disagree on whether a diff is in-bounds, the
mechanical scan wins and the run aborts with no PR (spec edge 5). This is
defense-in-depth: the prompt is advisory, the scan is the rail.

This standard is **fail-closed**. Any path the parser cannot classify, any glob
it cannot evaluate, any malformed section below — every ambiguity aborts the run.
Janitor never proceeds on doubt.

---

## Forbidden Path Classes (BR-006)

Janitor's write set excludes every path matching the patterns below. Each class
maps to a named rule; the boundary check reports the violated rule by name
(AC-004). Some classes are evaluated dynamically against git/PR state at run time
(marked **dynamic** — not expressible as a static glob) and are enforced by the
boundary check directly, not by the glob list.

| Rule | Class | Enforcement |
|------|-------|-------------|
| `intent-files` | Intent/spec/decision artifacts — `spec/`, feature `spec.md` & `design.md`, `docs/adrs/`, `INVARIANTS.md`, `DOMAIN.md`, `PRODUCT.md`, `RELEASES.md` | static glob |
| `harness-control` | Harness control surfaces — `hooks/`, `spec/etc_sdlc.yaml`, the installer (`install.sh`), the compiler | static glob |
| `secrets` | Secrets / credentials — `.env*`, key/credential material | static glob |
| `ci-workflows` | CI workflow definitions — `.github/workflows/` | static glob |
| `schemas-deps` | Schemas, migrations, lockfiles, dependency lists | static glob |
| `behavior-changing-logic` | Edits that change runtime behavior (not pure lint/format/dead-code/whitespace) | semantic, prompt + category gate (see note) |
| `untested-files` | Source files with no covering test | **dynamic** (test-coverage probe) |
| `public-facing-copy` | Operator/customer-facing copy (READMEs, published docs, marketing) | static glob |
| `active-feature-dirs` | Active feature directories — `.etc_sdlc/features/active/**` | static glob |
| `open-pr-files` | Any file touched by a currently-open PR | **dynamic** (`gh pr` query) |
| `recently-committed` | Any file with a commit in the last 24 hours | **dynamic** (git log probe) |
| `cross-context` | A change spanning 2+ bounded contexts | **dynamic** (path-root analysis) |
| `file-count-ceiling` | A diff touching more than the file-count ceiling | numeric ceiling (below) |

**Note on `behavior-changing-logic`:** this is a semantic property of the *edit*,
not of the *path*, so it cannot be a glob. It is enforced by (a) the v1
category gate — janitor only performs lint/format, test-proven dead-code removal,
and whitespace/EOF/import-order normalization (spec BR-004), none of which change
behavior — and (b) the green verification gate (BR-009). The boundary check does
not attempt to prove behavioral equivalence; the category restriction is the
control.

---

## Machine-Parseable Forbidden-Path List

The fenced block below is the authoritative static-glob list. **Parsing contract
for `janitor_boundary_check.py` (Task 002):**

1. Locate the single fenced code block whose info string is exactly
   `janitor-forbidden-globs`. There is exactly one such block in this file.
2. Read it line by line.
3. Discard blank lines and lines whose first non-whitespace character is `#`
   (comments).
4. Each remaining line is `<rule-name><TAB or run-of-spaces><glob>` — split on
   the first run of whitespace: the left token is the rule name reported on
   violation, the right token is a single POSIX glob pattern (relative to repo
   root, `/`-separated, `**` = any depth).
5. Canonicalize every diff path with `Path.resolve()` relative to the repo root
   **before** matching (no `..`/symlink escape — spec Security Considerations).
6. A diff path is forbidden if it matches ANY glob. Match using `pathlib`
   `PurePosixPath.match` semantics extended for `**`, or `fnmatch` with `**`
   normalized — the patterns are written to work with `**` meaning "zero or more
   path segments."
7. If this block is absent, empty, or any line fails the `<rule><ws><glob>`
   shape, the parser MUST abort the run (fail-closed). Do not proceed on a
   malformed list.

```janitor-forbidden-globs
# rule-name                glob
intent-files               spec/**
intent-files               .etc_sdlc/features/**/spec.md
intent-files               .etc_sdlc/features/**/design.md
intent-files               docs/adrs/**
intent-files               INVARIANTS.md
intent-files               **/INVARIANTS.md
intent-files               DOMAIN.md
intent-files               **/DOMAIN.md
intent-files               PRODUCT.md
intent-files               **/PRODUCT.md
intent-files               RELEASES.md
intent-files               **/RELEASES.md
harness-control            hooks/**
harness-control            spec/etc_sdlc.yaml
harness-control            install.sh
harness-control            **/install.sh
harness-control            scripts/compile*.py
harness-control            scripts/install*.py
secrets                    .env
secrets                    .env.*
secrets                    **/.env
secrets                    **/.env.*
secrets                    **/*.pem
secrets                    **/*.key
secrets                    **/secrets.*
ci-workflows               .github/workflows/**
schemas-deps               **/migrations/**
schemas-deps               **/alembic/**
schemas-deps               **/*.sql
schemas-deps               **/schema.prisma
schemas-deps               uv.lock
schemas-deps               poetry.lock
schemas-deps               Pipfile.lock
schemas-deps               package-lock.json
schemas-deps               yarn.lock
schemas-deps               pnpm-lock.yaml
schemas-deps               **/requirements*.txt
schemas-deps               pyproject.toml
schemas-deps               **/pyproject.toml
schemas-deps               package.json
schemas-deps               **/package.json
public-facing-copy         README.md
public-facing-copy         **/README.md
public-facing-copy         docs/**
public-facing-copy         CHANGELOG.md
public-facing-copy         **/CHANGELOG.md
active-feature-dirs        .etc_sdlc/features/active/**
```

---

## File-Count Ceiling (BR-006 / AC-005)

A single janitor run's worktree diff MUST touch no more than **3** files. A diff
touching 4 or more files fires the `file-count-ceiling` rule and aborts with no
PR. The same integer also caps the survey-select batch (design: batch-max 3).

The ceiling is published below in a machine-parseable form. **Parsing contract
for Task 002:** locate the single fenced block whose info string is exactly
`janitor-ceiling`; it contains exactly one line of the form `key = integer`. Read
the key `max_files`; its value is the integer ceiling. A run is in violation when
`count(changed_files) > max_files`. If the block is absent, holds a non-integer,
or holds more than the `max_files` key, abort (fail-closed); do not fall back to a
hardcoded default.

```janitor-ceiling
max_files = 3
```

---

## Dynamic Rules (not in the glob list)

These rules depend on repository state at run time and are enforced by
`janitor_boundary_check.py` directly. They are documented here so the standard
remains the single source of truth, but they are intentionally NOT in the
`janitor-forbidden-globs` block (a glob cannot express "committed in the last 24
hours").

- **`open-pr-files`** — a changed path appears in the file list of any currently
  open PR (`gh pr list --state open` joined with `gh pr view --json files`). A
  candidate that is also an in-flight file is skipped and reported as skipped
  (spec edge 6).
- **`recently-committed`** — a changed path has any commit with author/commit
  date within the last 24 hours (`git log --since="24 hours ago" -- <path>`).
- **`untested-files`** — a changed source file has no covering test. For
  category (b) dead-code removal this is doubly enforced: the category itself
  requires the existing test suite to prove the code unreached (spec edge 9).
- **`cross-context`** — the changed paths span 2 or more bounded contexts
  (distinct top-level package/context roots). A single run stays within one
  context.

When `gh` or git state is unavailable for a dynamic rule, the rule fails closed:
the run aborts rather than assuming the path is safe.

---

## Precedence

1. The mechanical scan (`janitor_boundary_check.py`) is authoritative over the
   prompt. Disagreement → scan wins, run aborts (spec edge 5).
2. Any ambiguity, parse failure, or unavailable state → abort, no PR
   (fail-closed; spec Security Considerations).
3. This file is the only source. Neither the prompt nor the check may embed a
   second copy of the list or the ceiling (AC-013).

---

## Rationale

Janitor is the *find-fix-and-ship* counterpart to F019's observe-and-propose
Chief Efficiency Officer. Shipping autonomously is only safe if the blast radius
is mechanically bounded. The forbidden-path list keeps janitor out of every
surface where a "trivial" edit could carry meaning a machine cannot see — intent
and decision records, active in-flight work, dependency and schema surfaces, the
harness's own control plane, secrets, and customer-facing words. The 3-file
ceiling keeps each PR tight enough for a human to review in one sitting, which is
the merge-confidence lever that earns category promotion (BR-008). Together they
make the trust in janitor *earned structurally* rather than hoped-for.

---

## Background

- Spec: `.etc_sdlc/features/active/F-2026-05-29-janitor-autonomous-cleanup/spec.md`
  (BR-005 mechanical check, BR-006 write boundary, BR-013 this standard, AC-004 /
  AC-005 / AC-013).
- Design: `.../design.md` (ADR-001 worktree isolation; boundary check API
  contract; path-traversal canonicalization).
- Cousins: F019 Chief Efficiency Officer (observe-and-propose), F015 spec-coupling
  (structured evidence at a lifecycle boundary), the `check-*.sh` path-scoping
  precedent that `janitor_boundary_check.py` follows.
