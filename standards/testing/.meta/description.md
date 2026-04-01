# standards/testing/

**Purpose:** 3 testing standards that define coverage requirements, test structure, naming conventions, tiered test strategy, and LLM evaluation practices. These standards ensure that every test is meaningful, isolated, and maintainable across all projects.

## Key Components
- `testing-standards.md` -- (Status: MANDATORY) 98% line and branch coverage minimum enforced by pyproject.toml, Stop hook, and CI. Four test tiers: Tier 1 deterministic/unit (every commit), Tier 2 integration (every push), Tier 3 LLM output evaluation (every PR), Tier 4 regression golden answers (every PR). AAA pattern (Arrange/Act/Assert). Fixture rules: conftest.py for shared fixtures, factory fixtures, no assertions in fixtures. Mocking rules: mock only external I/O, system time, randomness -- never mock core business logic. Prefer fakes over mocks. Async testing with pytest-asyncio (auto mode) and httpx AsyncClient.
- `test-naming.md` -- (Status: MANDATORY) Pattern: `test_should_<expected_behavior>_when_<condition>`. Test names must describe expected behavior AND condition in domain language. One assertion per test. Test file names mirror production files: `test_<module>.py`.
- `llm-evaluation.md` -- (Status: MANDATORY for LLM projects) LLM evaluations are first-class pytest tests, not a separate runner. Golden answer tests with SME-validated expected outputs using semantic similarity (not exact match). Failure mode separation: diagnose retrieval vs. generation vs. ingestion problems. Test markers: `@pytest.mark.llm_eval`, `@pytest.mark.golden_answer`. Cost awareness: run on PR (not every commit), use cheapest model that validates behavior, cache responses where determinism is acceptable.

## Dependencies
- Referenced by `backend-developer.md`, `frontend-developer.md`, `verifier.md`, and `code-reviewer.md` agent definitions
- Coverage threshold enforced by `hooks/verify-green.sh` (98% via pytest-cov)
- Test naming enforced during code review by `code-reviewer.md`
- LLM evaluation standards applied by `verifier.md` and CI pipeline

## Patterns
- **Tests as documentation:** Test names describe system behavior in domain language, serving as living documentation of expected behavior.
- **Tiered test strategy:** Tests are organized by speed and scope (unit -> integration -> LLM eval -> regression), with each tier running at the appropriate CI gate.
- **Failure mode isolation:** LLM tests are designed to diagnose whether failures come from retrieval, generation, or ingestion -- not just pass/fail.

## Constraints
- 98% line and branch coverage is non-negotiable. `# pragma: no cover` requires a justification comment AND a linked issue.
- No logic in tests (no if/else, no loops, no try/except).
- No test interdependence -- each test must run in isolation.
- No flaky tests -- quarantine and fix rather than retry.
- Never mock core business logic, domain models, or validation rules.
