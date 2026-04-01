# Clean Code Standards

## Status: MANDATORY
## Applies to: Backend Developer, Frontend Developer, Code Reviewer

## Size Limits
- Functions: <= 50 lines (soft limit — exceed with justification comment)
- Files: <= 300 lines (soft limit — exceed with justification comment)
- Classes: <= 200 lines
- Parameters: <= 5 per function (use a config/params object beyond that)

## Complexity
- Cyclomatic complexity: <= 10 per function
- Nesting depth: <= 3 levels (use early returns, extract functions)
- No nested ternaries

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
- Magic numbers (use named constants)
- God objects (classes that do everything)
- Feature envy (methods that use another class's data more than their own)
- Premature optimization (measure first, optimize second)
