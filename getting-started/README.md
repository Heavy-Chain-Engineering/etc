# SDLC Dashboard

A web dashboard that monitors SDLC project progress in real time. It reads from the harness's own state files (`.sdlc/state.json` and `.taskmaster/tasks/tasks.json`) and renders a visual overview of where a project stands.

## Features

### P0 (Core)
- **Phase indicator** — Shows the current SDLC phase prominently in the header
- **Phase timeline** — Visual timeline of all 7 phases (Bootstrap, Spec, Design, Decompose, Build, Ship, Evaluate) with current highlighted and completed marked
- **DoD checklist** — Current phase's definition-of-done items with check/uncheck status
- **DoD progress bar** — Percentage of DoD items completed
- **Task summary** — Total/completed/in-progress/pending/blocked counts from TaskMaster
- **Auto-refresh** — Dashboard polls every 5 seconds for updates

### P1 (Enhancements)
- **Phase transition history** — Table showing all phase transitions with timestamps and reasons
- **Task breakdown chart** — Horizontal bar chart of task counts by status
- **Dark mode** — Toggle between light and dark themes (preference saved in localStorage)

## Quick Start

```bash
# Install dependencies
pip install fastapi uvicorn

# Start the dashboard
python3 app.py
```

Open your browser to [http://localhost:8000](http://localhost:8000).

## Tech Stack

- **Backend:** Python 3.11+ / FastAPI / Uvicorn
- **Frontend:** Vanilla HTML + CSS + JavaScript (no build step)
- **Data:** Read-only access to `.sdlc/state.json` and `.taskmaster/tasks/tasks.json`
- **Testing:** pytest (36 tests, 96% coverage)

## API Endpoints

| Endpoint | Method | Description | Response Model |
|----------|--------|-------------|---------------|
| `/` | GET | Redirects to dashboard | — |
| `/api/state` | GET | Current SDLC state | `SDLCStateResponse` |
| `/api/tasks` | GET | Task summary | `TaskSummaryResponse` |
| `/static/*` | GET | Static files (HTML/CSS/JS) | — |
| `/docs` | GET | Auto-generated API docs | — |

## Configuration

File paths can be overridden via environment variables:

```bash
SDLC_STATE_PATH=path/to/state.json TASKS_PATH=path/to/tasks.json python3 app.py
```

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/ -v --tb=short

# Run tests with coverage
pytest tests/ -v --cov=src --cov-report=term-missing
```

## Project Structure

```
getting-started/
├── app.py                    # FastAPI entry point
├── src/
│   ├── __init__.py
│   ├── models.py             # Pydantic response models
│   └── readers.py            # JSON file readers
├── static/
│   ├── index.html            # Dashboard HTML
│   ├── style.css             # Styles (light + dark themes)
│   └── app.js                # Polling + rendering logic
├── tests/
│   ├── __init__.py
│   ├── conftest.py           # Shared fixtures
│   ├── test_models.py        # Model tests (16)
│   ├── test_readers.py       # Reader tests (13)
│   ├── test_app.py           # API endpoint tests (7)
│   └── fixtures/             # Test JSON files
├── spec/
│   ├── prd.md                # Product requirements
│   ├── domain-model.md       # Domain model
│   ├── edge-cases.md         # Edge cases & error scenarios
│   ├── system-design.md      # System design
│   └── adrs/                 # Architecture Decision Records
├── .sdlc/state.json          # SDLC tracker state
├── .taskmaster/tasks/        # TaskMaster tasks
├── pyproject.toml            # Project config
└── INVARIANTS.md             # Project invariants
```

## Invariants

- **INV-001:** No hardcoded file paths — all paths from config/env
- **INV-002:** All FastAPI endpoints have `response_model`
- **INV-003:** Dashboard never writes to `.sdlc/` or `.taskmaster/` files
- **INV-004:** Every Python module in `src/` has a corresponding test file
