"""SDLC Dashboard — FastAPI application entry point.

Serves the dashboard frontend and API endpoints for reading
SDLC state and TaskMaster task data.

Usage:
    python3 app.py
"""

from __future__ import annotations

import os
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from src.models import SDLCStateResponse, TaskSummaryResponse
from src.readers import read_sdlc_state, read_task_summary

# File paths from environment or sensible defaults relative to CWD (INV-001)
SDLC_STATE_PATH = Path(
    os.environ.get("SDLC_STATE_PATH", ".sdlc/state.json")
)
TASKS_PATH = Path(
    os.environ.get("TASKS_PATH", ".taskmaster/tasks/tasks.json")
)

app = FastAPI(
    title="SDLC Dashboard",
    description="Monitor SDLC project progress in real time.",
    version="0.1.0",
)

# Mount static files for the frontend
_static_dir = Path(__file__).parent / "static"
if _static_dir.is_dir():
    app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    """Redirect root to the dashboard."""
    return RedirectResponse(url="/static/index.html")


@app.get("/api/state", response_model=SDLCStateResponse)  # INV-002
def get_state() -> SDLCStateResponse:
    """Return the current SDLC state from .sdlc/state.json."""
    return read_sdlc_state(SDLC_STATE_PATH)


@app.get("/api/tasks", response_model=TaskSummaryResponse)  # INV-002
def get_tasks() -> TaskSummaryResponse:
    """Return the task summary from .taskmaster/tasks/tasks.json."""
    return read_task_summary(TASKS_PATH)


if __name__ == "__main__":
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8080,
        reload=True,
    )
