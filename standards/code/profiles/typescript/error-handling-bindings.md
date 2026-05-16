# TypeScript — error-handling bindings

The universal rule is `standards/code/error-handling.md`. This file
binds that rule to TypeScript tooling. Per ADR-F020-002 (rules separate
from bindings) and ADR-F020-006 (etc adopts community canon, never authors).

## Rule → TypeScript idiom binding

| Rule (universal) | TypeScript binding |
|---|---|
| Never silently swallow errors | `try { ... } catch (e) {}` with empty body is forbidden; eslint `no-empty` (catch-flavor) + `@typescript-eslint/no-misused-promises` for async flows |
| Catch specific errors | Catch with `instanceof <ErrorClass>` discrimination; `catch (e: unknown)` is the only acceptable bare form (per Google TS Style Guide), and the body MUST narrow via `instanceof` before accessing fields |
| Errors are values for expected failures | Return discriminated unions (`Result<T, E>` pattern) or `T \| null` for not-found; reserve `throw` for unexpected failures (bugs, infrastructure errors, contract violations) |
| Domain-specific exception hierarchy | Extend a base project `<Project>Error` class; do NOT extend `Error` directly in domain layer (loses prototype chain context in older TS targets) |
| Exception messages carry context | `throw new ValidationError(`Expected positive int for quantity, got ${quantity}`)` — never bare `throw new Error("Invalid")` |
| Re-throwing preserves the cause | Use `throw new Wrapper(message, { cause: originalError })` (ES2022 `Error.cause`); never swallow the originating traceback |

Invoke via `npx eslint .`.

## Universal-rule exceptions

Same fire-and-forget logging pattern as the Python profile:

```typescript
try {
  await cleanup();
} catch (e: unknown) {
  logger.error("cleanup failed; continuing", { cause: e });
}
```

eslint can't distinguish "intentional log-and-continue" from "silent
swallow." Reviewers must.

## Source

- [Google TypeScript Style Guide §Exceptions](https://google.github.io/styleguide/tsguide.html#exceptions)
- [typescript-eslint no-misused-promises](https://typescript-eslint.io/rules/no-misused-promises/)
- [TC39 Error.cause](https://tc39.es/proposal-error-cause/) — ES2022 standard for re-throw chaining
