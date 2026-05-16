# TypeScript — import-discipline bindings

The universal rule is `standards/code/import-discipline.md`. This file
binds that rule to TypeScript tooling. Per ADR-F020-002 (rules separate
from bindings) and ADR-F020-006 (etc adopts community canon, never authors).

## Rule → eslint binding

| Rule (universal) | TypeScript binding (eslint) |
|---|---|
| All imports at top of file | `import/first` (eslint-plugin-import) |
| No mid-module imports (except documented circular-dep break) | `import/first` with `// eslint-disable-next-line import/first` + documenting why |
| No circular imports | `import/no-cycle` (max-depth: 1) |
| Absolute imports only (or path-aliased) | `import/no-relative-parent-imports` — disallows `../../` traversal across module boundaries |
| One import per declaration | `import/no-duplicates` |
| No wildcard imports | `import/no-namespace` (allow targeted exceptions for type-only namespaces) |
| Unused imports prohibited | `@typescript-eslint/no-unused-vars` |
| Imports grouped by source | `import/order` (groups: builtin, external, internal, parent, sibling, index) |

Invoke via `npx eslint .` (assumes `eslint-plugin-import` and
`@typescript-eslint/eslint-plugin` are installed in the project's
devDependencies — both are part of the typescript-eslint recommended
preset).

## Circular-dependency escape hatch

```typescript
// Mid-module import required to break circular dependency:
// services/user imports api/routes for the route registry; routes need
// user-service for handler injection.
// eslint-disable-next-line import/first
import { registerUserRoutes } from "../api/routes";
```

The disable comment plus the rationale comment is the explicit
acknowledgment. eslint allows the line; reviewers see the rationale.

## Source

- [Google TypeScript Style Guide §Imports](https://google.github.io/styleguide/tsguide.html#imports)
- [eslint-plugin-import rules](https://github.com/import-js/eslint-plugin-import)
- [typescript-eslint no-unused-vars](https://typescript-eslint.io/rules/no-unused-vars/)
