# Ruff Audit: Standards-to-Rules Mapping

## Status: REFERENCE
## Applies to: Code Reviewer, Verifier

This document maps every enforceable rule in `standards/code/*.md` and `standards/testing/*.md` to its ruff equivalent. Use this as the cross-reference when adding new rules to standards docs or updating the reference ruff config.

## How to Read This Table

- **Enabled**: Rule is in `ruff-reference.toml` select list and fires automatically
- **Partial**: Ruff rule covers some but not all of the standard's intent
- **None**: No ruff rule exists; enforcement is via hook or required-reading only

---

## standards/code/clean-code.md

| Rule | Ruff Code | Status | Notes |
|------|-----------|--------|-------|
| Functions <= 50 lines | PLR0915 | Partial | PLR0915 counts statements, not lines; approximation |
| Files <= 300 lines | — | None | No ruff rule for file length |
| Classes <= 200 lines | — | None | No ruff rule for class length |
| Parameters <= 5 | PLR0913 | Enabled | `max-args = 5` in pylint config |
| Cyclomatic complexity <= 10 | C901 | Enabled | `max-complexity = 10` in mccabe config |
| Nesting depth <= 3 | — | None | No ruff rule for nesting depth |
| No nested ternaries | — | None | No ruff rule |
| No dead code (unused functions) | F841, F811 | Enabled | Unused variables and redefined names |
| No commented-out code | ERA001 | Enabled | Eradicate detects commented-out code |
| No magic numbers | — | None | No ruff rule for magic numbers |

## standards/code/error-handling.md

| Rule | Ruff Code | Status | Notes |
|------|-----------|--------|-------|
| No empty except blocks | E722, B001 | Enabled | E722 = bare except, B001 = bare except in bugbear |
| Catch specific exceptions | BLE001 | Enabled | Blind exception catch |
| Exception names with Error suffix | N818 | Enabled | pep8-naming error-suffix-on-exception-name |
| Don't use exceptions for control flow | — | None | Semantic rule, not lintable |
| Don't catch and re-raise without context | TRY201, TRY301 | Enabled | Verbose raise / raise within try |
| Don't return None for failure | — | None | Semantic rule, not lintable |

## standards/code/python-conventions.md

| Rule | Ruff Code | Status | Notes |
|------|-----------|--------|-------|
| snake_case functions/variables | N802, N806 | Enabled | Function and variable naming |
| PascalCase classes | N801 | Enabled | Class naming |
| UPPER_SNAKE_CASE constants | — | None | No ruff rule for constant naming convention |
| Absolute imports only | I001 | Enabled | isort import sorting enforces absolute imports |
| Import sorting (stdlib/third-party/local) | I001 | Enabled | isort handles ordering |
| No mid-module imports | E402 | Enabled | Module-level import not at top of file |

## standards/code/typing-standards.md

| Rule | Ruff Code | Status | Notes |
|------|-----------|--------|-------|
| All functions fully annotated | ANN001, ANN002, ANN003, ANN201 | Enabled | Missing arg/return type annotations |
| No Any in production code | ANN401 | Enabled | Dynamically typed expressions |
| Use pipe union syntax | UP007 | Enabled | Use `X \| Y` instead of `Union[X, Y]` |
| Use lowercase generics | UP006 | Enabled | Use `list[str]` instead of `List[str]` |
| cast() requires comment | — | None | Semantic rule, not lintable |

## standards/code/import-discipline.md

| Rule | Ruff Code | Status | Notes |
|------|-----------|--------|-------|
| No mid-module imports | E402 | Enabled | Circular breaks require documentation |

## standards/testing/testing-standards.md

| Rule | Ruff Code | Status | Notes |
|------|-----------|--------|-------|
| No print statements in tests | T201 | Enabled | flake8-print no-print |
| No logic in tests (if/else, loops) | PT018 | Partial | PT018 catches composite assertions; if/else requires reading |
| No flaky test patterns | — | None | Semantic rule, not lintable |

## standards/testing/test-naming.md

| Rule | Ruff Code | Status | Notes |
|------|-----------|--------|-------|
| test_should_*_when_* pattern | — | None | Naming convention not enforced by ruff |
| One assertion per test | — | None | Not lintable |

## standards/testing/llm-evaluation.md

| Rule | Ruff Code | Status | Notes |
|------|-----------|--------|-------|
| Don't assert exact string matches | — | None | Semantic rule, not lintable |

---

## Summary

| Category | Enforced by Ruff | Hook-enforced | Guidance Only |
|----------|-----------------|---------------|---------------|
| clean-code.md | 4 | 0 | 6 |
| error-handling.md | 4 | 0 | 2 |
| python-conventions.md | 5 | 0 | 1 |
| typing-standards.md | 4 | 0 | 1 |
| import-discipline.md | 1 | 0 | 0 |
| testing-standards.md | 2 | 0 | 1 |
| test-naming.md | 0 | 0 | 2 |
| llm-evaluation.md | 0 | 0 | 1 |
| **Total** | **20** | **0** | **14** |

Note: Hook-enforced rules (CQ-001: global mutable state, CQ-002: no-op functions) are not ruff rules. They are enforced by `hooks/check-code-quality.sh` via AST analysis.
