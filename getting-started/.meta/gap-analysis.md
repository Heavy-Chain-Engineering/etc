# Gap Analysis — getting-started (Greenfield)

## Date: 2026-02-25
## Status: Greenfield — everything needs to be built

## What Exists
- `spec/prd.md` — Complete PRD with P0/P1/P2 requirements
- `INVARIANTS.md` — 4 invariants defined (no hardcoded paths, response_model on endpoints, no writes to state files, test coverage)
- `README.md` — Project readme
- `.sdlc/state.json` — Initialized tracker state

## What is Missing

### Code (all of it)
- [ ] `app.py` — FastAPI application entry point
- [ ] `src/readers.py` — JSON file readers for state.json and tasks.json
- [ ] `src/models.py` — Pydantic data models for API responses
- [ ] `src/__init__.py` — Package init
- [ ] `static/index.html` — Dashboard HTML
- [ ] `static/style.css` — Dashboard styles
- [ ] `static/app.js` — Dashboard JavaScript (polling, rendering)

### Tests
- [ ] `tests/test_readers.py` — Tests for JSON readers
- [ ] `tests/test_models.py` — Tests for data models
- [ ] `tests/conftest.py` — Shared fixtures

### Infrastructure
- [ ] `pyproject.toml` — Project configuration, dependencies
- [ ] `requirements.txt` — Or equivalent dependency spec

### Documentation
- [ ] API documentation
- [ ] Setup/run instructions

## Architecture Concerns
- None — greenfield, clean slate to implement correctly
- Key constraint: read-only access to state files (INV-003)
- Key constraint: all endpoints need response_model (INV-002)

## Recommendations
1. Proceed to Spec phase — PRD already exists and is thorough
2. Design phase should formalize the API contract and component boundaries
3. Decompose should break P0 into ~5-8 tasks ordered by dependency
4. Build using TDD: models first, then readers, then endpoints, then frontend
