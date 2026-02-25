# Error Handling Standards

## Status: MANDATORY
## Applies to: Backend Developer, Frontend Developer, Code Reviewer

## Core Rules
1. **Never silently swallow errors.** Empty `except` blocks are forbidden.
2. **Catch specific exceptions.** Never `except Exception` without re-raising or explicit justification.
3. **Fail fast.** Validate at system boundaries (API input, external service responses). Trust internal code.
4. **Errors are values.** Where appropriate, use result types instead of exceptions for expected failure modes.

## Exception Hierarchy
- Define domain-specific exceptions that extend a base project exception
- Exception names describe the problem: `DocumentNotFoundError`, `ChunkingFailedError`
- Include context in exception messages (what was attempted, what went wrong)

## Logging
- Log at the appropriate level: ERROR for failures, WARNING for degraded behavior, INFO for state changes
- Include correlation IDs in log messages for traceability
- Never log secrets, tokens, or PII

## API Error Responses
- Use appropriate HTTP status codes (400 for bad input, 404 for not found, 500 for internal errors)
- Return structured error responses with: error code, human message, request ID
- Never expose internal stack traces in API responses

## What NOT to Do
- Don't use exceptions for control flow
- Don't catch and re-raise without adding context
- Don't log and re-raise (choose one — the handler should decide)
- Don't return `None` to indicate failure (use explicit error types or raise)
