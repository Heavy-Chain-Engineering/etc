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
git clone https://github.com/your-fork/etc-system-engineering.git
cd etc-system-engineering
uv sync           # Install dependencies
uv run pytest     # Run 109 tests
```

## Key Principles

- **The DSL is the source of truth.** Don't edit `dist/` or `settings-hooks.json` directly — modify `spec/etc_sdlc.yaml` and recompile.
- **Command hooks must be deterministic.** They check binary conditions (file exists? pattern matches?) and return exit 0 or exit 2. No ambiguity.
- **Prompt/agent hooks are for judgment.** Use them when the decision requires reasoning, not when a grep would do.
- **Every hook needs tests.** Add tests in `tests/` before submitting. The `conftest.py` fixtures make this straightforward.
- **Fail early and loud.** Hooks should never swallow errors. If something is wrong, block and explain why.

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
uv run pytest              # All 109 tests
uv run pytest -k dangerous # Just the dangerous-commands tests
uv run pytest --tb=long    # Full tracebacks on failure
```

## Code Style

- Python 3.11+, strict typing
- Test names: `test_should_<behavior>_when_<condition>`
- Hook scripts: bash, no external dependencies beyond jq and python3
