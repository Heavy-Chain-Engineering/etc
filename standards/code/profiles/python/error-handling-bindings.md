# Python — error-handling bindings

The universal rule is `standards/code/error-handling.md`. This file
binds that rule to Python tooling. Per ADR-F020-002 (rules separate from
bindings) and ADR-F020-006 (etc adopts community canon, never authors).

## Rule → Python idiom binding

| Rule (universal) | Python binding |
|---|---|
| Never silently swallow errors | `except SomeError: pass` is forbidden; ruff `BLE001` catches blind-except; ruff `S110` catches try/except/pass |
| Catch specific exceptions | `except Exception:` without re-raise is flagged; prefer named exception classes |
| Errors are values for expected failures | Use Result-like patterns (`pydantic.BaseModel` with `success`/`error` union, or `Optional[T]` for not-found) instead of exceptions for business-rule violations |
| Domain-specific exception hierarchy | Inherit from a base project `<Project>Error`; do NOT inherit from `Exception` directly in domain layer |
| Exception messages carry context | `raise ValueError(f"Expected positive int for quantity, got {quantity!r}")` — never bare `raise ValueError("Invalid")` |
| `raise X from e` for context-preserving re-raises | When re-raising, use `from` to chain; never swallow the originating traceback |

Invoke via `uv run ruff check src/ tests/`.

## Universal-rule exceptions

The "never swallow" rule has one allowed pattern for fire-and-forget
side effects:

```python
try:
    cleanup()
except Exception:
    logger.exception("cleanup failed; continuing")
```

The `logger.exception` call captures the traceback; the `continuing`
context is explicit. This is documented because ruff cannot distinguish
"intentional log-and-continue" from "silent swallow" — reviewers must.

## Source

- [PEP 8](https://peps.python.org/pep-0008/) §Programming Recommendations on exceptions
- [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html#24-exceptions)
- [ruff BLE rules](https://docs.astral.sh/ruff/rules/#flake8-blind-except-ble)
- [ruff S rules](https://docs.astral.sh/ruff/rules/#flake8-bandit-s) — security-flavored try/except
