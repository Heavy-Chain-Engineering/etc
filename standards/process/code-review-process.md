# Code Review Process

## Status: MANDATORY
## Applies to: Code Reviewer

## Pre-Review

Before reviewing any code, read:
1. All files in `~/.claude/standards/` (engineering standards)
2. All files in `.claude/standards/` (project standards, if they exist)
3. `.meta/description.md` in the working directory (local context)

## Review Checklist

This checklist is for defensive security review of authorized codebases owned by the operator. All findings are for remediation, not exploitation.

### Critical (must fix before merge)
- Security vulnerabilities (injection, XSS, auth bypass, secrets in source)
- Silent error swallowing (empty catch blocks, ignored return values)
- Data corruption risks (race conditions, missing validation)
- Test gaps (modified production code without corresponding test changes)
- Coverage regression (coverage decreased from baseline)

### Warning (should fix)
- Naming that doesn't match domain language (see Domain Modeler standards)
- Functions exceeding 50 lines
- Files exceeding 300 lines
- Dead code (unused imports, unreachable branches, commented-out code)
- Missing type annotations on public interfaces
- Layer violations (UI importing data layer, business logic depending on framework)

### Suggestion (consider improving)
- Opportunities for clearer naming
- Potential for reducing duplication (but only if pattern appears 2+ times)
- Performance improvements (only if measurable)
- Documentation gaps in complex logic

## Review Output Format

Report issues organized by severity (Critical, Warning, Suggestion).
For each issue:
1. **File and line** — exact location
2. **What** — what the code does
3. **Why it's a problem** — concrete impact, not theoretical
4. **How to fix** — specific code example

## Rules

- Never approve code that has Critical issues
- Never approve code where coverage decreased
- Apply standards consistently — no exceptions for "quick fixes"
- If unsure about a domain concept, escalate to Domain Modeler
