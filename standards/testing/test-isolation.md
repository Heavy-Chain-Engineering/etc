# Test Isolation

## Status: MANDATORY
## Applies to: Backend Developer, Frontend Developer, Code Reviewer, Verifier

## Motivation

VenLink audit (2026-04-16), finding 6: A test asserted exact counts on a global mutable `_handlers` defaultdict. The assertion was fragile -- it broke whenever another test registered handlers, requiring 3 fix attempts before the root cause (shared mutable state) was identified. Total debugging time: 30 minutes.

## Rules

### No assertions on module-level mutable state
- **Enforce:** hook(check-code-quality CQ-001) / **Fallback:** required-reading

Tests MUST NOT assert on module-level mutable collections (dicts, lists, sets, defaultdicts). These collections accumulate state across test runs and produce non-deterministic results depending on test execution order.

### The fragile assertion antipattern

Do not do this:

```python
# BAD: Asserting on global state
from myapp.events import _handlers

def test_should_register_handler():
    register_handler("click", my_handler)
    assert len(_handlers["click"]) == 1  # Fragile: count depends on test order
```

Instead, use fixture lifecycle to control state:

```python
# GOOD: Fixture provides isolated state
@pytest.fixture
def handler_registry():
    registry = defaultdict(list)
    yield registry
    registry.clear()

def test_should_register_handler(handler_registry):
    register_handler("click", my_handler, registry=handler_registry)
    assert len(handler_registry["click"]) == 1
```

### Required fixture lifecycle patterns

- **Setup:** Create fresh state in the fixture
- **Yield:** Provide the state to the test
- **Teardown:** Clean up after the test (explicit clear or context manager)

Never rely on module-level state being in a "known" condition. If a test needs a global registry, inject it via dependency injection and provide a clean instance per test.

### Test ordering independence

Every test MUST produce the same result regardless of execution order. Use `pytest-randomly` to verify this property. If a test fails when run in isolation but passes in a suite (or vice versa), it has a state leak.

## What NOT to Do

- Don't assert on global collections (dicts, lists, sets) that accumulate across tests
- Don't rely on test execution order for correct behavior
- Don't use module-level mutable state as a test communication channel
- Don't patch global state without restoring it in teardown
