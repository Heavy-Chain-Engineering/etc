# Typing Standards

## Status: MANDATORY
## Applies to: Backend Developer, Code Reviewer, Verifier

## mypy Configuration
- Strict mode enabled (`--strict`)
- No `Any` types in production code
- `warn_return_any = true`
- `disallow_untyped_defs = true`

## Type Annotation Rules
- All function signatures fully annotated (parameters and return type)
- All class attributes annotated
- Use `|` union syntax (not `Optional` or `Union`)
- Use `list[str]` lowercase generics (not `List[str]`)
- Use `type` aliases for complex types

## Pydantic Models
- All data transfer objects are Pydantic `BaseModel` subclasses
- Domain entities use Pydantic models with validators
- Settings objects use `pydantic-settings.BaseSettings`
- Use `model_validator` for cross-field validation

## Protocol Over ABC
- Prefer `typing.Protocol` for structural subtyping
- Use ABC only when shared implementation is needed
- Keep protocols small and focused (Interface Segregation)

## Exceptions
- Third-party library stubs may use `type: ignore[import-untyped]` with comment
- Test files may relax annotations (configured in ruff per-file-ignores)
- `cast()` requires a comment explaining why it's necessary
