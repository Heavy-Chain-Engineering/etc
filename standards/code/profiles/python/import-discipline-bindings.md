# Python — import-discipline bindings

The universal rule is `standards/code/import-discipline.md`. This file
binds that rule to Python tooling. Per ADR-F020-002 (rules separate from
bindings) and ADR-F020-006 (etc adopts community canon, never authors).

## Rule → ruff binding

| Rule (universal) | Python binding (ruff) |
|---|---|
| All imports at top of file | `E402` (module-level-import-not-at-top-of-file) |
| No mid-module imports (except documented circular-dep break) | `E402` with `# noqa: E402` comment + documenting why |
| Absolute imports only | `TID252` (relative-imports) configured to forbid |
| One import per line | `E401` (multiple-imports-on-one-line) |
| No wildcard imports | `F403`, `F405` (wildcard-import flags) |
| Unused imports prohibited | `F401` (unused-import) |
| `__future__` imports first | Convention: `from __future__ import annotations` is the first non-docstring line |

Invoke via `uv run ruff check src/ tests/`.

## Circular-dependency escape hatch

When a mid-module import is genuinely required to break a circular
dependency, document it inline:

```python
# Mid-module import required to break circular dependency:
# domain.user_service imports api.routes for the route registry; routes
# need user_service for handler injection.
from api.routes import register_user_routes  # noqa: E402
```

The `# noqa: E402` plus the comment is the explicit acknowledgment. Ruff
allows the line; reviewers see the rationale.

## Source

- [PEP 8](https://peps.python.org/pep-0008/) §Imports
- [Google Python Style Guide §2.2 Imports](https://google.github.io/styleguide/pyguide.html#22-imports)
- [ruff E402 docs](https://docs.astral.sh/ruff/rules/module-import-not-at-top-of-file/)
- [ruff TID252 docs](https://docs.astral.sh/ruff/rules/relative-imports/)
