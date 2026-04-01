# standards/security/

**Purpose:** 2 security standards that define data classification and handling rules plus an OWASP-based security checklist. Applied by the security-reviewer agent on every code change that handles user input, authentication, or external data, and referenced by backend-developer and code-reviewer agents.

## Key Components
- `data-handling.md` -- (Status: MANDATORY) Data classification: Internal (business logic artifacts), Confidential (API keys, credentials, PII -- encrypted at rest), Public (API responses, docs). Sanitization rules: sanitize at trust boundaries, strip/escape HTML/JS, validate MIME types, truncate oversized inputs. Database rules: parameterized queries only, PII encrypted at rest, connection pooling with limits. Logging rules: never log passwords/tokens/API keys/credit card numbers/SSNs, redact PII, include correlation IDs.
- `owasp-checklist.md` -- (Status: MANDATORY) Six categories: Input validation (Pydantic models at API boundary, no raw SQL, file upload validation), Authentication/authorization (tokens as env vars, validated on every request, least privilege, secure session management), Secrets management (no secrets in source code, Gitleaks in CI, env vars or secrets manager, `.env` in `.gitignore`), Injection prevention (ORM for SQL, never shell-execute user input, XSS sanitization, SSRF URL allowlisting), Data protection (no PII at DEBUG level, no internal IDs/stack traces in production responses, HTTPS everywhere, database TLS), Dependencies (keep updated via Dependabot, review licenses, pin versions in lockfile).

## Dependencies
- Referenced by `security-reviewer.md`, `backend-developer.md`, and `code-reviewer.md` agent definitions
- Secrets enforcement backed by Gitleaks in CI pipeline
- SQL injection prevention enforced by ORM/parameterized query patterns
- Dependency management enforced by lockfile and Dependabot configuration
- `SecurityScanRule` guardrail in `platform/` checks for SQL injection, XSS, hardcoded secrets, and insecure deserialization

## Patterns
- **Defense in depth:** Security is enforced at multiple layers -- Pydantic input validation, ORM parameterized queries, Gitleaks CI scanning, security-reviewer agent, and SecurityScanRule guardrail middleware.
- **Trust boundary focus:** Sanitization happens at system boundaries (API input, external service responses), not scattered throughout business logic.

## Constraints
- Both standards are MANDATORY.
- No secrets in source code, ever -- this is both a standard rule and a CI gate (Gitleaks).
- Never construct SQL strings manually -- use ORM or parameterized queries exclusively.
- Never pass user input to shell execution functions.
- API responses must never expose internal IDs, stack traces, or debug information in production.
