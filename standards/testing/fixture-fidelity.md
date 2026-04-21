# Fixture Fidelity

## Status: MANDATORY
## Applies to: Backend Developer, Frontend Developer, Code Reviewer, Verifier

## Motivation

VenLink audit (2026-04-16), finding 7: A dev endpoint returned an invented response shape that no production endpoint would ever produce. Tests passed against this fake, but the integration failed in production because downstream code expected the real API response shape. The "fake client" antipattern silently corrupted all downstream agents that consumed the response.

## Rules

### Dev endpoints must call the same service methods as production
- **Enforce:** none / **Fallback:** required-reading

Dev/test endpoints MUST delegate to the same service layer methods that production endpoints use. A dev endpoint that constructs its own response bypasses the service layer's validation, transformation, and error handling -- producing shapes that cannot occur in production.

```python
# BAD: Dev endpoint invents its own response
@app.get("/dev/search")
async def dev_search():
    return {"results": [{"id": 1, "text": "fake"}]}  # Invented shape

# GOOD: Dev endpoint calls the same service
@app.get("/dev/search")
async def dev_search(service: SearchService = Depends()):
    return await service.search(query="test", limit=10)
```

### Test doubles must mirror real API response shapes
- **Enforce:** none / **Fallback:** required-reading

When mocking an external API, the mock response MUST be derived from actual API documentation or a captured production response. Never invent response shapes.

```python
# BAD: Invented response shape
mock_response = {"data": {"items": [{"id": 1}]}}

# GOOD: Response shape from API docs or captured response
# Source: Stripe API docs, 2026-03-15
mock_response = {
    "object": "list",
    "data": [{"id": "pi_123", "object": "payment_intent", "amount": 1000}],
    "has_more": False,
    "url": "/v1/payment_intents",
}
```

### The "fake client" antipattern

A fake client is a test double that returns responses the real client would never produce. This antipattern is particularly dangerous because:

1. Tests pass (the fake is internally consistent)
2. Integration tests pass (they use the same fake)
3. Production fails (the real API returns a different shape)

Prevention: When creating test doubles for external services, always start from the real API's response schema. If the API documentation is unavailable, escalate to the team -- do not guess.

### Response shape validation

Where possible, validate test doubles against the same Pydantic models used to parse production responses. If a test double cannot be deserialized by the production response model, it is invalid.

```python
# Validate that the mock matches the production model
mock_data = {"id": "pi_123", "amount": 1000, "currency": "usd"}
PaymentIntent.model_validate(mock_data)  # Fails if shape is wrong
```

## What NOT to Do

- Don't invent API response shapes for test doubles -- derive from docs or captured responses
- Don't create dev endpoints that skip the service layer
- Don't assume a test double is correct because tests pass -- validate against production models
- Don't skip fixture fidelity checks because "it's just a test" -- tests are the specification
