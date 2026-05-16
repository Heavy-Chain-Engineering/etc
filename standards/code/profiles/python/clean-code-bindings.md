# Python — clean-code bindings

The universal rule is `standards/code/clean-code.md`. This file binds
that rule to Python tooling. Per ADR-F020-002 (rules separate from
bindings) and ADR-F020-006 (etc adopts community canon, never authors).

## Rule → ruff binding

| Rule (universal) | Python binding (ruff) | Severity |
|---|---|---|
| Functions ≤ 50 lines | `PLR0915` (too-many-statements) — fallback to required-reading review where ruff cannot count lines | hard-fail |
| Parameter count ≤ 4 | `PLR0913` (too-many-arguments) | hard-fail |
| Cyclomatic complexity ≤ 10 | `C901` (mccabe-complexity) | hard-fail |
| Dead code prohibited | `F841` (unused-variable), `F811` (redefined-while-unused), `ERA001` (commented-out-code) | hard-fail |
| No commented-out code | `ERA001` | warn |

Invoke via `uv run ruff check src/ tests/`. The reference config lives
at `standards/code/ruff-reference.toml`.

## Type checker binding

Universal rule "public functions have explicit return types" binds to:

- `uv run mypy --strict src/` enforces `--disallow-untyped-defs`
- mypy `--strict` also enforces `--no-implicit-optional` and `--warn-unreachable`

## Formatter binding

`uv run ruff format` produces canonical formatting. The formatter has no
universal-rule equivalent (formatting is purely conventional); this
binding exists so the python profile gates can assert format-cleanliness.

## Source

- [PEP 8](https://peps.python.org/pep-0008/) — community canonical style
- [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html)
- [ruff rule docs](https://docs.astral.sh/ruff/rules/) — per-code reference
- [mypy docs](https://mypy.readthedocs.io/) — type checker reference
