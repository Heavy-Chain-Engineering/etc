# Python profile

Profile-0 of F020. Migrates etc's existing Python tooling defaults into
the profile architecture without behavioral change (F020 BR-007: existing
1014 tests must continue passing after migration).

## Canonical sources

- [PEP 8](https://peps.python.org/pep-0008/) — Python community style canon
- [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html)
- [ruff rule docs](https://docs.astral.sh/ruff/rules/) — the lint rule binding source
- [mypy docs](https://mypy.readthedocs.io/) — the type checker binding source

## Tooling

- **Test runner:** `uv run pytest`
- **Type checker:** `uv run mypy`
- **Linter:** `uv run ruff check`
- **Formatter:** `uv run ruff format`

All four are invoked through `uv run` to use the project venv rather than
whatever happens to be on `$PATH`.

## Files in scope

`**/*.py`, `**/*.pyi`. Excludes `__pycache__/`, `.venv/`, `venv/`, `.tox/`,
`build/`, `dist/`, `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`.

## Per-gate scripts

- `verify-green.sh` — full test/typecheck/lint run
- `check-test-exists.sh` — TDD gate (source needs a sibling test)
- `check-code-quality.sh` — AST-level Python quality checks
- `check-seam-evidence.sh` — integration-test marker presence
- `check-completion-discipline.sh` — pre-stop CI gate

See `docs/audits/F020-language-coupling-audit.md` for the audit that
motivated extracting this profile from the top-level hooks.
