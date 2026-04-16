# Import Discipline

## Status: MANDATORY
## Applies to: Backend Developer, Frontend Developer, Code Reviewer

## Motivation

VenLink audit (2026-04-16) found mid-module imports in 3 files with no documentation of why. Mid-module imports obscure dependency graphs, make circular import debugging harder, and violate the principle that a file's dependencies should be visible at the top.

## Rules

### All imports at module top
- **Enforce:** ruff(E402) / **Fallback:** required-reading

All imports MUST appear at the top of the file, after module docstrings and `__future__` imports. Ruff E402 fires on any import not at the top of the module.

### Circular break documentation

When a mid-module import is genuinely required to break a circular dependency, it MUST be documented with a comment in this format:

```python
# circular-break: module_a -> module_b
from module_b import SomeClass  # noqa: E402
```

The `# circular-break:` comment is the documentation. The `# noqa: E402` suppresses the ruff violation. Both are required -- the noqa alone is not sufficient documentation.

### Import ordering

Imports follow the standard three-section ordering, enforced by isort (ruff I001):

1. Standard library
2. Third-party packages
3. Local/project imports

Each section separated by a blank line. Ruff isort handles sorting automatically.

### Absolute imports only

Relative imports (`from . import foo`) are forbidden. Use absolute imports only. This makes dependency graphs explicit and grep-friendly.

## What NOT to Do

- Don't use mid-module imports to avoid fixing circular dependencies -- fix the dependency graph instead
- Don't suppress E402 without the `# circular-break:` documentation comment
- Don't manually reorder imports -- let ruff isort handle it
- Don't import individual names from large modules (except typing and dataclasses)
