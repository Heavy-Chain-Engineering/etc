# SDLC Dashboard — Project Configuration

## Project Overview

This is the **getting-started** onboarding project for the etc coding harness. It builds a web dashboard that monitors SDLC project progress.

## Tech Stack

- **Language:** Python 3.11+
- **Backend:** FastAPI + Uvicorn
- **Frontend:** Vanilla HTML + CSS + JavaScript (no build step)
- **Data:** JSON file reads from `.sdlc/state.json` and `.taskmaster/tasks/tasks.json`
- **Testing:** pytest

## Standards

This project follows all standards in `~/.claude/standards/`:
- TDD workflow (write tests first)
- Clean code conventions
- Python typing standards (strict mypy)

## Test Runner

```bash
pytest tests/ -v --tb=short
```

## Coverage Threshold

95% minimum — automated code gen has no excuse for low coverage

## Directory Structure

```
getting-started/
├── app.py              # FastAPI application entry point
├── static/             # HTML, CSS, JS
│   ├── index.html
│   ├── style.css
│   └── app.js
├── src/                # Backend modules
│   ├── readers.py      # JSON file readers
│   └── models.py       # Data models
├── tests/              # pytest tests
│   ├── test_readers.py
│   └── test_models.py
├── spec/               # PRD and design docs
│   └── prd.md
├── .claude/            # This file
│   └── CLAUDE.md
├── .sdlc/              # Workflow state (init with tracker.py)
│   └── state.json
└── pyproject.toml
```

## How to Use the Harness

This project is designed to be built using the full etc harness. Tell Claude Code:

```
"Use the sem agent to build this project. The PRD is in spec/prd.md. Start from the Spec phase."
```

The SEM will walk through Spec → Design → Decompose → Build → Ship → Evaluate.
