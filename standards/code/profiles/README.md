# Language profiles

This directory contains per-profile content for F020's language-agnostic
harness. Each subdirectory at `standards/code/profiles/<profile>/` is a
self-contained bundle declaring (i) detection rules, (ii) per-rule tool
bindings, (iii) per-gate executable scripts.

See `docs/audits/F022-language-coupling-audit.md` for the audit that
motivated this architecture and the six ADRs at `docs/adrs/F020-001..006`
for the load-bearing decisions.

## Acceptance bar for new profiles

A profile is accepted into etc ONLY if its target language has all three:

1. **A published canonical style guide or community-recognized authority.**
   Examples: PEP 8 + Google Python Style Guide for Python; Rust API Guidelines
   + the official Rust Style Guide; Apple Swift API Design Guidelines;
   Airbnb JavaScript Style Guide; Google C++ Style Guide. See
   [Kristories/awesome-guidelines](https://github.com/Kristories/awesome-guidelines)
   for the curated meta-repo.

2. **A community-standard linter command.** Examples: `ruff check` for Python;
   `eslint` for JS/TS; `golangci-lint run` for Go; `cargo clippy` for Rust.
   The linter must be invocable as a single command and produce machine-readable
   output.

3. **A community-standard test runner command.** Examples: `pytest` for Python;
   `npm test` / `jest` / `vitest` for JS/TS; `go test ./...` for Go;
   `cargo test` for Rust.

Languages lacking any of these are explicitly declined. The bar exists to
ensure each profile is reproducible across operators and CI environments.

## Profile structure

```
standards/code/profiles/<profile>/
├── detection.yaml                      # markers + file globs + canonical sources
├── README.md                           # profile-specific introduction
├── clean-code-bindings.md              # universal clean-code rule -> tool bindings
├── error-handling-bindings.md          # universal error-handling rule -> tool bindings
├── import-discipline-bindings.md       # universal import-discipline rule -> tool bindings
├── verify-green.sh                     # per-profile verify-green gate
├── check-test-exists.sh                # per-profile TDD gate
├── check-code-quality.sh               # per-profile quality gate
├── check-seam-evidence.sh              # per-profile integration-seam gate
└── check-completion-discipline.sh      # per-profile completion-discipline gate
```

## detection.yaml schema

```yaml
profile: python                         # MUST match directory name
markers:                                # any-of activates the profile
  - pyproject.toml
  - setup.py
  - uv.lock
file_globs:                             # fnmatch patterns this profile claims
  - "**/*.py"
  - "**/*.pyi"
exclude_globs:                          # paths to exclude from this profile
  - "**/__pycache__/**"
  - "**/.venv/**"
canonical_sources:                      # URLs cited by every *-bindings.md
  - https://google.github.io/styleguide/pyguide.html
  - https://peps.python.org/pep-0008/
```

## Path-overlap tie-break

When two profiles' `file_globs` both claim the same file (e.g., a `.py`
script in a node project's `scripts/` directory), the **more-specific glob
wins**. Specificity is measured by the number of literal characters in the
pattern (not counting `*`, `?`, `[`, `]`).

Equally specific globs break ties **alphabetically by profile name**.

Operators can override via `.etc_sdlc/profiles.yaml exclude_paths:` per
profile.

## Operator override file

`.etc_sdlc/profiles.yaml` (optional) lets the operator:

- `pin: [profile]` — explicit profile list overriding auto-detect
- `add: [profile]` — profiles to activate that auto-detect missed
- `exclude_paths:` — per-profile path exclusions

See the F020 spec for the full schema.

## Bindings file format

Every `<rule>-bindings.md` file MUST contain:

1. The universal rule (one-line restatement of the rule from
   `standards/code/<rule>.md` for human readability).
2. The per-tool ENFORCEMENT (specific lint codes, type checker flags,
   formatter settings that enforce the rule for this profile).
3. A `## Source` section naming at least one external URL or document
   (per ADR-F020-006: etc adopts community canon, never authors).

A test enforces the `## Source` section presence per F020 AC-009.
