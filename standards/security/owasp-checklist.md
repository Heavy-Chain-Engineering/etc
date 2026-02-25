# OWASP Security Checklist

## Status: MANDATORY
## Applies to: Security Reviewer, Backend Developer, Code Reviewer

## Input Validation
- All user input validated at API boundary (Pydantic models)
- No raw SQL queries — use parameterized queries via SQLAlchemy ORM
- File uploads: validate type, size, and content (not just extension)
- URL parameters and path variables validated against expected patterns

## Authentication and Authorization
- API keys and tokens stored as environment variables, never in source
- Auth tokens validated on every request (middleware or dependency)
- Principle of least privilege for all service accounts
- Session management: secure cookies, proper expiration, no predictable IDs

## Secrets Management
- No secrets in source code, ever (Gitleaks enforces this in CI)
- Use environment variables or secrets manager
- `.env` files in `.gitignore`
- Rotate API keys on any suspected exposure

## Injection Prevention
- SQL: Use ORM (SQLAlchemy) — never construct SQL strings manually
- Command: Never pass user input to shell execution functions
- XSS: Sanitize all output rendered in HTML templates
- SSRF: Validate and allowlist external URLs before fetching

## Data Protection
- PII logged only when necessary, and never at DEBUG level
- API responses never include internal IDs, stack traces, or debug info in production
- Use HTTPS for all external communication
- Database connections use TLS

## Dependencies
- Keep dependencies updated (Dependabot or equivalent)
- Review dependency licenses for compatibility
- Pin dependency versions in lockfile
