# ADR-002: Read-Only JSON File Access Pattern

## Status: Accepted
## Date: 2026-02-25

## Context
The dashboard reads `.sdlc/state.json` and `.taskmaster/tasks/tasks.json`. These files are managed by other tools (tracker.py, TaskMaster). INV-003 prohibits writes. Files may not exist, may be malformed, or may be written to concurrently.

## Decision
Implement a reader module (`src/readers.py`) that:
1. Takes file paths as parameters (not hardcoded — INV-001)
2. Opens files in read-only mode
3. Reads entire content into memory atomically (single `read()` call)
4. Parses JSON in memory
5. Returns typed Pydantic models on success, or a structured error on failure
6. Never writes, never holds file handles open

## Consequences
- **Pro:** Clean separation of data access from API logic
- **Pro:** Testable in isolation with fixture files
- **Pro:** Graceful degradation when files are missing or malformed
- **Con:** Re-reads file on every API call (no caching)
- **Accepted risk:** For a local tool polling every 5s, the re-read overhead is negligible
