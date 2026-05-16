# TypeScript — clean-code bindings

The universal rule is `standards/code/clean-code.md`. This file binds
that rule to TypeScript tooling. Per ADR-F020-002 (rules separate from
bindings) and ADR-F020-006 (etc adopts community canon, never authors).

## Rule → eslint binding

| Rule (universal) | TypeScript binding (eslint) | Severity |
|---|---|---|
| Functions ≤ 50 lines | `max-lines-per-function` (max 50, skipBlankLines, skipComments) | hard-fail |
| Parameter count ≤ 4 | `max-params` (max 4) | hard-fail |
| Cyclomatic complexity ≤ 10 | `complexity` (max 10) | hard-fail |
| Dead code prohibited | `@typescript-eslint/no-unused-vars`, `no-unreachable` | hard-fail |
| No commented-out code | `no-warning-comments` (TODO/FIXME audit) | warn |
| Prefer `const` for non-reassigned bindings | `prefer-const` | warn |
| No `any` (use `unknown` for genuinely-untyped values) | `@typescript-eslint/no-explicit-any` | warn |

Invoke via `npx eslint .`. Reference eslint config can be derived from
[typescript-eslint's recommended preset](https://typescript-eslint.io/getting-started)
extended with the rule overrides above.

## Type checker binding

Universal rule "public functions have explicit return types" binds to:

- `tsc --noEmit --strict`
- TSConfig: `"strict": true`, `"noImplicitAny": true`,
  `"strictNullChecks": true`, `"noImplicitReturns": true`

The Google TypeScript Style Guide [Explicit Types](https://google.github.io/styleguide/tsguide.html#explicit-types)
section establishes the contract.

## Formatter binding

`npx prettier --check .` produces canonical formatting. No universal-rule
equivalent (formatting is purely conventional); the binding exists so
the typescript profile gates can assert format-cleanliness when prettier
is in the project's deps. Skipped silently if prettier is absent.

## Source

- [Google TypeScript Style Guide](https://google.github.io/styleguide/tsguide.html) — primary
- [typescript-eslint rules](https://typescript-eslint.io/rules/) — per-rule reference
- [Airbnb JavaScript Style Guide](https://github.com/airbnb/javascript) — JS-shape conventions where they don't conflict with Google TS
