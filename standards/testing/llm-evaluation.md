# LLM Evaluation Standards

## Status: MANDATORY (for projects with LLM integration)
## Applies to: Backend Developer, Verifier

## Principle
LLM evaluations are first-class pytest tests, not a separate evaluation runner.
They use the same test infrastructure, markers, and reporting as all other tests.

## Golden Answer Tests
- SME-validated expected outputs for known inputs
- Stored as parametrized test data
- Test both the answer AND the reasoning structure
- Tolerance thresholds for non-deterministic outputs (semantic similarity, not exact match)

## Failure Mode Separation
When an LLM test fails, diagnose WHY:
- **Retrieval problem:** The right context chunks were not surfaced
- **Generation problem:** Right chunks found, LLM misinterpreted
- **Ingestion problem:** Information was not in the corpus at all

Test fixtures should isolate each component to enable this diagnosis.

## Test Markers

```python
@pytest.mark.llm_eval       # Requires API keys, validates reasoning quality
@pytest.mark.golden_answer   # SME-validated assertions, regression tracking
```

## Cost Awareness
- LLM eval tests run on PR (not every commit) to manage API costs
- Use the cheapest model that validates the behavior (eval does not require production model)
- Cache LLM responses in CI where determinism is acceptable

## What NOT to Do
- Don't assert exact string matches on LLM output (use semantic comparison)
- Don't skip LLM evals because they cost tokens — they catch real bugs
- Don't mix retrieval and generation tests — isolate failure modes
