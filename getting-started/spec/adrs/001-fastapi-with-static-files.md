# ADR-001: FastAPI with Static File Serving

## Status: Accepted
## Date: 2026-02-25

## Context
We need a web server that serves both a REST API (for reading SDLC state) and static files (HTML/CSS/JS dashboard). The PRD requires `python3 app.py` to start everything with no additional setup beyond `pip install fastapi uvicorn`.

## Decision
Use FastAPI as the application framework with:
- API endpoints under `/api/` prefix
- Static file serving via `StaticFiles` mount at `/static/`
- Root route `/` redirects or serves `index.html`

## Consequences
- **Pro:** Single process, single `python3 app.py` command
- **Pro:** FastAPI provides automatic OpenAPI docs at `/docs`
- **Pro:** Pydantic models give us response validation for free (satisfies INV-002)
- **Con:** FastAPI's static file serving is basic — no caching headers, no gzip
- **Accepted risk:** Performance is not a concern for a local development tool
