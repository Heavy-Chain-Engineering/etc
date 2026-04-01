# getting-started -- Project Description

## Purpose
SDLC Dashboard: a web-based monitoring tool that reads `.sdlc/state.json` and `.taskmaster/tasks/tasks.json` to render a visual overview of project progress through the SDLC lifecycle.

## Status
Built and tested. All P0 and P1 features implemented.

## Architecture
- **Backend:** Python 3.11+ / FastAPI / Uvicorn
- **Frontend:** Vanilla HTML + CSS + JS (no build step)
- **Data:** Read-only access to `.sdlc/state.json` and `.taskmaster/tasks/tasks.json`
- **Testing:** pytest, 36 tests, 96% coverage (threshold: 80%)
- **Entry point:** `python3 app.py` starts server on port 8000

## Directory Map
```
getting-started/
├── app.py              # FastAPI application entry point
├── static/             # HTML, CSS, JS frontend
│   ├── index.html      # Dashboard layout
│   ├── style.css       # Light/dark theme styles
│   └── app.js          # Polling and rendering
├── src/                # Backend modules
│   ├── models.py       # Pydantic response models
│   └── readers.py      # JSON file readers
├── tests/              # 36 pytest tests
│   ├── conftest.py     # Shared fixtures
│   ├── test_models.py  # 16 model tests
│   ├── test_readers.py # 13 reader tests
│   ├── test_app.py     # 7 API endpoint tests
│   └── fixtures/       # Test JSON files
├── spec/               # PRD, design docs, ADRs
├── .sdlc/              # Workflow state
├── .taskmaster/        # Task definitions
├── pyproject.toml      # Project config
└── INVARIANTS.md       # 4 project invariants (all passing)
```

## API Endpoints
- `GET /` -- Redirects to dashboard
- `GET /api/state` -- SDLC state (response_model: SDLCStateResponse)
- `GET /api/tasks` -- Task summary (response_model: TaskSummaryResponse)
- `GET /static/*` -- Static file serving
- `GET /docs` -- Auto-generated OpenAPI docs

## Invariants
- INV-001: No hardcoded file paths (PASS)
- INV-002: All endpoints have response_model (PASS)
- INV-003: No writes to state files (PASS)
- INV-004: All modules have test files (PASS)
