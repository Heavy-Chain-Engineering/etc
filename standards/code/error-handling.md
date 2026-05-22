# Error Handling Standards

<!-- forward-only: vocabulary purity enforced from F022 release tag onward -->

## Status: MANDATORY
## Applies to: Backend Developer, Frontend Developer, Code Reviewer

For language-specific tooling that enforces these rules, see the per-profile
binding files under `standards/code/profiles/<profile>/error-handling-bindings.md`
(e.g. `standards/code/profiles/python/error-handling-bindings.md`).

## Rules
1. **Never silently swallow errors.** Empty `except` / catch-all blocks are forbidden.
2. **Catch specific errors.** Never catch the root exception/error type without re-raising or explicit justification.
3. **Fail fast.** Validate at system boundaries (API input, external service responses). Trust internal code.
4. **Errors are values.** For expected failure modes (not-found lookups, validation failures, known business-rule violations), use result types or domain error returns instead of raised exceptions. Reserve raised exceptions for unexpected failures (infrastructure errors, programming bugs, contract violations).

## Exception Hierarchy
- Define domain-specific exceptions that extend a base project exception
- Exception names describe the problem: `DocumentNotFoundError`, `ChunkingFailedError`
- Include context in exception messages (what was attempted, what went wrong)

## Logging
- Log at the matching level: ERROR for failures, WARNING for degraded behavior, INFO for state changes, DEBUG for diagnostic detail
- Include correlation IDs in log messages for traceability
- Never log secrets, tokens, or PII

## API Error Responses
- Use HTTP status codes matching the failure mode: 400 for bad input, 401 for missing auth, 403 for forbidden, 404 for not found, 409 for conflict, 422 for validation failure, 500 for internal errors
- Return structured error responses with: error code, human message, request ID
- Never expose internal stack traces in API responses

## What NOT to Do
- Don't use exceptions for control flow
- Don't catch and re-raise without adding context
- Don't log and re-raise (choose one — the handler should decide)
- Don't return a null/empty sentinel to indicate failure (use explicit error types or raise)
