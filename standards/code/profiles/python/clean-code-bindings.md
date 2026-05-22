# Python Bindings — Clean Code

Cross-reference: `standards/code/clean-code.md` (the rule set this binds).

This file binds the universal clean-code rules to Python tooling. Per
ADR-F020-002 (rules separate from bindings) and ADR-F020-006 (etc adopts
community canon, never authors). Section headings mirror the rule file
so a reader can map binding to rule by H2.

## Tooling

- **Linter / formatter:** `uv run ruff check` and `uv run ruff format`.
  Reference config at `standards/code/ruff-reference.toml`.
- **Type checker:** `uv run mypy --strict src/`.
- **Test runner:** `uv run pytest`.

All four are invoked through `uv run` to use the project venv.

## Size Limits

| Rule (universal) | Python binding | Severity |
|---|---|---|
| Functions <= 50 lines | `ruff(PLR0915)` — too-many-statements; fallback to required-reading review (PLR0915 counts statements, not lines) | hard-fail |
| Files <= 300 lines | none — required-reading review | warn |
| Classes <= 200 lines | none — required-reading review | warn |
| Parameters <= 5 per function | `ruff(PLR0913)` — too-many-arguments | hard-fail |

## Complexity

| Rule (universal) | Python binding | Severity |
|---|---|---|
| Cyclomatic complexity <= 10 per function | `ruff(C901)` — mccabe-complexity | hard-fail |
| Nesting depth <= 3 levels | none — required-reading review | warn |
| No nested ternaries | none — required-reading review | warn |

## What to Avoid

| Rule (universal) | Python binding | Severity |
|---|---|---|
| Dead code (unused functions, unreachable branches, commented-out code) | `ruff(F841, F811, ERA001)` | hard-fail |
| No commented-out code | `ruff(ERA001)` | hard-fail |
| Magic numbers | none — required-reading review | warn |

## Type checker binding

The universal rule "public functions have explicit return types" binds
to mypy:

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
