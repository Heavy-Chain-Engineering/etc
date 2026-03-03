# standards/code/

**Purpose:** 4 code standards that define quality expectations for all implementation work: size limits, complexity thresholds, naming conventions, error handling patterns, Python-specific conventions, and type system requirements. Applied by backend-developer, frontend-developer, code-reviewer, and verifier agents.

## Key Components
- `clean-code.md` -- (Status: MANDATORY) Size limits (functions <= 50 lines, files <= 300 lines, classes <= 200 lines, parameters <= 5), cyclomatic complexity <= 10, nesting depth <= 3. Principles: Single Responsibility, DRY (abstract after 2 occurrences), YAGNI, Least Surprise, Fail Fast. Naming conventions for booleans (`is_`, `has_`, `can_`), return functions (noun phrases), action functions (verb phrases). Bans generic names (`data`, `info`, `manager`, `handler`, `utils`).
- `error-handling.md` -- (Status: MANDATORY) Core rules: never silently swallow errors, catch specific exceptions, fail fast at system boundaries, errors as values where appropriate. Requires domain-specific exception hierarchy with context in messages. Logging at appropriate levels with correlation IDs, never logging secrets. Structured API error responses with error code, human message, request ID -- never exposing stack traces.
- `python-conventions.md` -- (Status: MANDATORY) Python 3.14+ with modern syntax. Naming: `snake_case` functions/variables, `PascalCase` classes, `UPPER_SNAKE_CASE` constants, no abbreviations in public APIs. Absolute imports only, one class per file for domain models. Pydantic `BaseModel` for all data structures with `Field()` descriptions. FastAPI router per domain concern with explicit status codes. `async/await` for all I/O.
- `typing-standards.md` -- (Status: MANDATORY) mypy strict mode enabled. No `Any` in production code. Full annotations on all function signatures and class attributes. Modern syntax: `|` union, `list[str]` lowercase generics, `type` aliases. Pydantic models for all DTOs and domain entities. Prefer `typing.Protocol` over ABC for structural subtyping. Third-party stub exceptions require `type: ignore[import-untyped]` with comment.

## Dependencies
- Referenced by `backend-developer.md`, `frontend-developer.md`, `code-reviewer.md`, and `verifier.md` agent definitions
- Typing standards enforced by mypy in `verify-green.sh` hook and CI pipeline
- Clean code standards enforced by ruff linter in `verify-green.sh` hook
- Python conventions enforced by ruff isort (import ordering) and ruff formatter

## Patterns
- **Concrete thresholds over vague guidance:** Every rule has a specific number (50 lines, 98% coverage, complexity <= 10) rather than subjective descriptions like "keep functions short."
- **Framework-aware:** Standards reference specific frameworks (Pydantic, FastAPI, SQLAlchemy) with opinionated conventions for each.

## Constraints
- All 4 standards are MANDATORY -- no exceptions without explicit human override.
- Python version target is 3.14+ -- agents should use modern syntax features (union `|`, pattern matching, lowercase generics).
- No `Any` types in production code -- this is enforced by mypy strict mode.
- Ruff handles import sorting -- agents must not manually reorder imports.
