# Data Handling Standards

## Status: MANDATORY
## Applies to: Backend Developer, Security Reviewer

## Data Classification
- **Internal:** Business logic artifacts, intermediate computations — never leave the system
- **Confidential:** API keys, user credentials, PII — encrypted at rest, restricted access
- **Public:** API responses, documentation — safe to expose

## Sanitization Rules
- Sanitize all data crossing trust boundaries (user input to system, system to external API)
- Strip or escape HTML/JS in user-provided text before storage
- Validate file content matches declared MIME type
- Truncate oversized inputs at the API boundary

## Database
- Use parameterized queries exclusively (ORM handles this)
- PII columns encrypted at rest where feasible
- Database credentials rotated on schedule
- Connection pooling with connection limits

## Logging
- Never log: passwords, tokens, API keys, credit card numbers, full SSNs
- Redact PII in log output (mask all but last 4 digits, etc.)
- Include correlation/request IDs for traceability
- Log retention follows data retention policy
