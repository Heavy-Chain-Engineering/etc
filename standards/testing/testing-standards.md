# Testing Standards

## Status: MANDATORY
## Applies to: Backend Developer, Frontend Developer, Verifier, Code Reviewer

## Coverage Requirements
- **50% line coverage minimum on the scoped harness layer** (`scripts/` +
  `hooks/helpers/` per `[tool.coverage.run]`; F020 honest-coverage scope)
- Enforced by: `pyproject.toml` (`fail_under = 50`). There is no CI pipeline
  and no Stop-hook coverage check today — the pyproject floor, applied when
  the suite runs with `--cov`, is the only mechanism. Do not cite phantom
  enforcers.
- The floor is a RATCHET: raise it as measured coverage genuinely improves
  (a drift test pins this number to pyproject's `fail_under`); never lower
  it to silence a failure.
- Coverage may not decrease between PRs
- `# pragma: no cover` requires a justification comment AND linked issue

## Test Tiers

| Tier | Marker | Runs When | Tests | Speed |
|------|--------|-----------|-------|-------|
| 1: Deterministic | `unit` | Every commit (hook + CI) | Schemas, math, normalization, business rules | Seconds |
| 2: Integration | `integration` | Every push (CI) | Database, external service interactions | Minutes |
| 3: LLM Output | `llm_eval` | Every PR (CI) | Golden answers, hallucination detection | Minutes |
| 4: Regression | `golden_answer` | Every PR (CI) | Cross-run comparison, pass/fail delta | Minutes |

## Test Structure (AAA Pattern)

```python
def test_should_behavior_when_condition():
    # Arrange — set up preconditions
    input_data = create_test_input()

    # Act — execute the behavior under test
    result = function_under_test(input_data)

    # Assert — verify the outcome
    assert result == expected_outcome
```

## Fixture Design
- Fixtures provide test data and dependencies, not test logic
- Use `conftest.py` for shared fixtures (scoped appropriately)
- Factory fixtures for creating domain objects with sensible defaults
- Never put assertions in fixtures

## Mocking Rules
- Mock only: external I/O (network, filesystem, database), system time, randomness
- Never mock: core business logic, domain models, validation rules
- Use dependency injection to make mocking easy (don't patch internals)
- Prefer fakes over mocks when behavior matters more than call verification

## Async Testing
- Use `pytest-asyncio` with `mode = "auto"`
- Async fixtures with `@pytest.fixture` (pytest-asyncio handles async automatically)
- Use `httpx.AsyncClient` with `ASGITransport` for API testing

## What NOT to Do
- No print statements in tests
  - **Enforce:** ruff(T201)
- No logic in tests (no if/else, no loops, no try/except)
  - **Enforce:** ruff(PT018) / **Fallback:** required-reading
- No test interdependence (each test runs in isolation)
- No testing implementation details (test behavior, not structure)
- No flaky tests (if a test is flaky, quarantine and fix it — don't retry)
  - **Enforce:** none / **Fallback:** required-reading

## Running the suite under the agent sandbox
A red pytest result from inside the agent command-sandbox is not, by itself, a
failure signal — the sandbox can fail a correct test by denying network, file,
or socket access. Before judging a red run, apply
[`../process/sandboxed-pytest-discipline.md`](../process/sandboxed-pytest-discipline.md):
classify the failure as sandbox-caused or code-caused, and re-run any
sandbox-caused failure WITHOUT the sandbox to get the authoritative verdict.
Never report green from a run you know was sandbox-degraded.
