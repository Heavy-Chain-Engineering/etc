# System Design — SDLC Dashboard

## Component Architecture

```
┌─────────────────────────────────────────────────────┐
│                    Browser                           │
│  ┌───────────────────────────────────────────────┐  │
│  │  static/index.html + style.css + app.js       │  │
│  │                                                │  │
│  │  - Fetches /api/state and /api/tasks every 5s │  │
│  │  - Renders phase timeline, DoD checklist,     │  │
│  │    task summary, progress bar                 │  │
│  │  - Handles errors gracefully                  │  │
│  └───────────────────────────────────────────────┘  │
└────────────────────┬────────────────────────────────┘
                     │ HTTP GET (polling)
                     ▼
┌─────────────────────────────────────────────────────┐
│                  FastAPI (app.py)                     │
│                                                      │
│  Routes:                                             │
│  ├── GET /          → redirect to /static/index.html │
│  ├── GET /api/state → SDLCState (phase, DoD, history)│
│  ├── GET /api/tasks → TaskSummary (counts by status) │
│  └── /static/       → StaticFiles mount              │
│                                                      │
│  Dependencies:                                       │
│  ├── src/models.py  → Pydantic response models       │
│  └── src/readers.py → JSON file reading functions     │
└──────────┬─────────────────────────┬────────────────┘
           │ read                    │ read
           ▼                         ▼
    .sdlc/state.json      .taskmaster/tasks/tasks.json
```

## API Contract

### GET /api/state
**Response model:** `SDLCStateResponse`
```json
{
  "current_phase": "Build",
  "phases": [
    {
      "name": "Bootstrap",
      "status": "completed",
      "entered_at": "2026-02-25T10:00:00Z",
      "completed_at": "2026-02-25T10:05:00Z",
      "dod_items": [
        {"item": "...", "done": true}
      ]
    }
  ],
  "transitions": [
    {"from_phase": "Bootstrap", "to_phase": "Spec", "reason": "...", "timestamp": "..."}
  ],
  "dod_progress": {"completed": 3, "total": 6, "percentage": 50.0},
  "error": null
}
```

### GET /api/tasks
**Response model:** `TaskSummaryResponse`
```json
{
  "total": 12,
  "completed": 5,
  "in_progress": 2,
  "pending": 3,
  "blocked": 1,
  "deferred": 1,
  "cancelled": 0,
  "tasks": [...],
  "error": null
}
```

## Module Responsibilities

### app.py
- FastAPI application setup
- Route definitions with response_model (INV-002)
- Static file mount
- Uvicorn startup

### src/models.py
- Pydantic models for all API responses
- Phase, DoDItem, PhaseTransition, TaskSummary
- All models are strict — no extra fields allowed

### src/readers.py
- `read_sdlc_state(path: Path) -> SDLCStateResponse`
- `read_task_summary(path: Path) -> TaskSummaryResponse`
- Both return structured responses, never raise exceptions to callers
- File paths passed as parameters (INV-001)

### static/index.html
- Dashboard layout: header, phase timeline, DoD section, task section
- No framework — semantic HTML

### static/style.css
- Clean, modern styling
- CSS custom properties for theming (dark mode toggle)
- Grid/flexbox layout

### static/app.js
- `fetchState()` and `fetchTasks()` — API calls
- `renderTimeline()`, `renderDoD()`, `renderTasks()` — DOM updates
- `startPolling()` — 5s interval
- Error handling for network failures

## UX Flow

1. User runs `python3 app.py`
2. Browser opens to `http://localhost:8000`
3. Dashboard loads, fetches /api/state and /api/tasks
4. Phase timeline shows all 7 phases with current highlighted
5. DoD checklist shows current phase's items
6. Progress bar shows completion percentage
7. Task summary shows counts
8. Every 5 seconds, data refreshes automatically
9. If files are missing, friendly error messages appear instead of broken UI

## Technical Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| JSON file locked during read | Low | Low | Atomic read, catch IOError |
| Large tasks.json slows response | Low | Low | Simple aggregation, no complex processing |
| Browser caching stale API responses | Medium | Medium | Set Cache-Control: no-cache on API responses |
