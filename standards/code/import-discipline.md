# Import Discipline

<!-- forward-only: vocabulary purity enforced from F022 release tag onward -->

## Status: MANDATORY
## Applies to: Backend Developer, Frontend Developer, Code Reviewer

For language-specific tooling that enforces these rules, see the per-profile
binding files under `standards/code/profiles/<profile>/import-discipline-bindings.md`
(e.g. `standards/code/profiles/python/import-discipline-bindings.md`).

## Motivation

VenLink audit (2026-04-16) found mid-module imports in 3 files with no documentation of why. Mid-module imports obscure dependency graphs, make circular import debugging harder, and violate the principle that a file's dependencies should be visible at the top.

## Rules

### All imports at module top

All imports MUST appear at the top of the file, after module docstrings and any language-mandated preamble (e.g. `__future__` annotations in Python). Linters MUST flag any import not at the top of the module.

### Circular break documentation

When a mid-module import is genuinely required to break a circular dependency, it MUST be documented with an inline comment that names the dependency edge being broken. The documentation is required even when the linter suppression is in place -- a suppression on its own is not sufficient documentation. The exact comment shape is language-specific and lives in the per-profile binding.

### Import ordering

Imports follow the standard three-section ordering:

1. Standard library
2. Third-party packages
3. Local/project imports

Each section is separated by a blank line. Sorting MUST be automated by the language's canonical import sorter; manual reordering is forbidden.

### Absolute imports only

Relative imports (e.g. `from . import foo`) are forbidden. Use absolute imports only. This makes dependency graphs explicit and greppable via literal module paths.

## What NOT to Do

- Don't use mid-module imports to avoid fixing circular dependencies -- fix the dependency graph instead
- Don't suppress the linter's top-of-file import rule without the documenting `# circular-break:` (or per-language equivalent) comment
- Don't manually reorder imports -- defer to the language's canonical sorter
- Don't import individual names from large modules (except language-blessed cases such as typing and dataclass primitives)
