# Python Conventions

## Status: MANDATORY
## Applies to: Backend Developer, Code Reviewer

## Language Version
- Python 3.14+ (use modern syntax: type unions with `|`, pattern matching, etc.)

## Naming
- `snake_case` for functions, methods, variables, modules
  - **Enforce:** ruff(N802, N806)
- `PascalCase` for classes
  - **Enforce:** ruff(N801)
- `UPPER_SNAKE_CASE` for constants
  - **Enforce:** none / **Fallback:** required-reading
- Private members prefixed with `_` (single underscore)
- No abbreviations in public APIs (use `document` not `doc`, `configuration` not `cfg`)
- Names should reflect domain language (see project domain standards)

## Imports
- Standard library first, then third-party, then local — separated by blank lines
  - **Enforce:** ruff(I001)
- Absolute imports only (no relative imports)
  - **Enforce:** ruff(I001)
- Import modules, not individual names (except for typing and dataclasses)
- Ruff isort handles sorting — do not manually reorder
- No mid-module imports (see standards/code/import-discipline.md)
  - **Enforce:** ruff(E402) / **Fallback:** required-reading (justified circular breaks)

## Structure
- One class per file for domain models and services
- Related utilities may share a file
- `__init__.py` exports public API only — no implementation in init files
- Package structure mirrors domain boundaries

## Pydantic
- All data structures are Pydantic `BaseModel` subclasses
- Use `Field()` with descriptions for API-facing models
- Validators for domain invariants (not just type checking)
- Settings via `pydantic-settings` with environment variable binding

## FastAPI
- Router per domain concern (not per HTTP method)
- Dependency injection for services, database sessions, settings
- Response models explicitly declared
- Status codes explicitly set (no implicit 200)

## Async
- `async/await` for all I/O operations
- Never mix sync and async database calls
- Use `asyncio.gather()` for concurrent independent operations
- AsyncGenerator for streaming responses
