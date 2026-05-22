# Clean Code Standards

<!-- forward-only: vocabulary purity enforced from F022 release tag onward -->

## Status: MANDATORY
## Applies to: Backend Developer, Frontend Developer, Code Reviewer

## Size Limits
- Functions: <= 50 lines (soft limit — exceed with justification comment)
  - **Enforce:** linter rule (per-profile) / **Fallback:** required-reading
- Files: <= 300 lines (soft limit — exceed with justification comment)
  - **Enforce:** none / **Fallback:** required-reading
- Classes: <= 200 lines
  - **Enforce:** none / **Fallback:** required-reading
- Parameters: <= 5 per function (use a config/params object beyond that)
  - **Enforce:** linter rule (per-profile)

## Complexity
- Cyclomatic complexity: <= 10 per function
  - **Enforce:** linter rule (per-profile)
- Nesting depth: <= 3 levels (use early returns, extract functions)
  - **Enforce:** none / **Fallback:** required-reading
- No nested ternaries
  - **Enforce:** none / **Fallback:** required-reading

## Principles
- **Single Responsibility:** One reason to change per module/class/function
- **DRY:** Don't Repeat Yourself — but only abstract after the pattern appears twice
- **YAGNI:** Don't build what you don't need yet
- **Least Surprise:** Code should do what its name suggests, nothing more
- **Fail Fast:** Validate inputs early, return/raise immediately on invalid state

## Naming
- Boolean variables/functions: `is_`, `has_`, `can_`, `should_` prefix
- Functions that return values: noun or noun phrase (`get_user`, `calculate_score`)
- Functions that perform actions: verb phrase (`send_notification`, `validate_input`)
- Avoid generic names: `data`, `info`, `manager`, `handler`, `processor`, `utils`

## What to Avoid
- Dead code (unused functions, unreachable branches, commented-out code)
  - **Enforce:** linter rule (per-profile)
- No commented-out code
  - **Enforce:** linter rule (per-profile)
- Magic numbers (use named constants)
  - **Enforce:** none / **Fallback:** required-reading
- God objects (classes that do everything)
- Feature envy (methods that use another class's data more than their own)
- Premature optimization (measure first, optimize second)

## Profile Bindings

Tool-specific enforcement (linter rule codes, command invocations,
config snippets) lives in per-language bindings — not in this file.
The rules above are tool-agnostic; the bindings name the tool.

- [Python bindings](./profiles/python/clean-code-bindings.md)
