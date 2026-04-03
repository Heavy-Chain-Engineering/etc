# Contributing to etc

Thanks for your interest in contributing to etc (Engineering Team, Codified).

## How to Contribute

1. **Fork the repo** and create a feature branch
2. **Edit the DSL** — `spec/etc_sdlc.yaml` is the single source of truth
3. **Compile** — `python3 compile-sdlc.py spec/etc_sdlc.yaml`
4. **Test** — `uv run pytest`
5. **Submit a PR** with a clear description of what changed and why

## Development Setup

```bash
git clone https://github.com/Heavy-Chain-Engineering/etc.git
cd etc
uv sync           # Install dependencies
uv run pytest     # Run 123 tests
```

## Key Principles

- **The DSL is the source of truth.** Don't edit `dist/` directly — modify `spec/etc_sdlc.yaml` and recompile.
- **Command hooks must be deterministic.** They check binary conditions (file exists? pattern matches?) and return exit 0 or exit 2. No ambiguity.
- **Prompt/agent hooks are for judgment.** Use them when the decision requires reasoning, not when a grep would do.
- **Every hook needs tests.** Add tests in `tests/` before submitting. The `conftest.py` fixtures make this straightforward.
- **Fail early and loud.** Hooks should never swallow errors. If something is wrong, block and explain why.
- **Never `git add -A`.** Stage specific files by name. The harness blocks blind staging.

## What to Contribute

- **New gates** — engineering practices you enforce in your team that belong in the DSL
- **Improved hook scripts** — better regex patterns, fewer false positives, clearer error messages
- **Better prompts** — the role/prompt text for prompt and agent hooks can always be refined
- **Bug fixes** — if a hook blocks something it shouldn't (or allows something it shouldn't)
- **Documentation** — especially real-world usage examples

## What Not to Change

- Don't loosen existing gates without discussion — the harness is intentionally strict
- Don't add dependencies beyond pytest and pyyaml unless there's a strong reason
- Don't modify compiled artifacts in `dist/` — they're regenerated from the DSL

## Running Tests

```bash
uv run pytest              # All 123 tests
uv run pytest -k dangerous # Just the dangerous-commands tests
uv run pytest --tb=long    # Full tracebacks on failure
```

## Using Templates

When creating new artifacts, start from the templates in `~/.claude/templates/`:

- `adr.md.tmpl` — Architecture Decision Records
- `agent.md.tmpl` — Agent definitions with frontmatter
- `task.yaml.tmpl` — Task files for `/implement`
- `invariant.md.tmpl` — INVARIANTS.md entries

## Code Style

- Python 3.11+, strict typing
- Test names: `test_should_<behavior>_when_<condition>`
- Hook scripts: bash, no external dependencies beyond jq and python3
- Commit messages: conventional commits (feat:, fix:, docs:, chore:)
