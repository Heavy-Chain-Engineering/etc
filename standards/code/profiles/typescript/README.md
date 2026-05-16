# TypeScript profile

F021 — the proof case that F020's profile architecture supports a second
language. Per F020 BR-009 + ADR-F020-006 (adopt-and-cite), etc does not
author TypeScript style; it points at community canon.

## Canonical sources

- [Google TypeScript Style Guide](https://google.github.io/styleguide/tsguide.html) — primary canon
- [typescript-eslint rules](https://typescript-eslint.io/rules/) — the lint rule binding source
- [Airbnb JavaScript Style Guide](https://github.com/airbnb/javascript) — secondary reference for JS-shape conventions; the TS-specific rules from Google override where they conflict

## Tooling assumptions

The profile assumes the operator's project has:

- **Test runner:** `npm test` (delegates to whatever's in `package.json` scripts — vitest, jest, mocha all fine)
- **Type checker:** `npx tsc --noEmit` (uses local `node_modules/.bin/tsc`)
- **Linter:** `npx eslint` (uses local `node_modules/.bin/eslint`)
- **Formatter:** `npx prettier --check` (when prettier is in the project's deps)

Profile gate scripts use `npx` rather than hardcoding npm/pnpm/yarn so
the operator's package manager choice is respected. Missing tools cause
the gate to emit a clear stderr ERROR per F020 EC-007.

## Files in scope

`**/*.ts`, `**/*.tsx`, `**/*.mts`, `**/*.cts`. Excludes `node_modules/`,
`dist/`, `build/`, `.next/`, `.turbo/`, `coverage/`, and `*.d.ts`
(declaration files — generated, not authored).

## Per-gate scripts

- `verify-green.sh` — `npm test` + `tsc --noEmit` + `eslint`
- `check-test-exists.sh` — `.ts/.tsx` source under `src/` needs a sibling `*.test.ts` or `*.spec.ts` file

Other gates (check-code-quality, check-seam-evidence,
check-completion-discipline) follow the same pattern when they migrate.

## Why TypeScript second

Per the F020 audit: TypeScript is the second-most-common partner stack
after Python and the language where etc's `frontend-developer` and
`frontend-dashboard-refactorer` agents already produce work. Closing
the hook gap for TS unlocks full enforcement on every codebase that
ships customer-facing frontends — most of HCE's partner book.
