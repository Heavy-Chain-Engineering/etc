"""JSON file readers for SDLC state and TaskMaster tasks.

Reads .sdlc/state.json and .taskmaster/tasks/tasks.json from disk.
All file paths are passed as parameters (INV-001).
Files are opened read-only and never written to (INV-003).
"""

from __future__ import annotations

import json
from pathlib import Path

from src.models import (
    DoDItem,
    DoDProgress,
    PhaseInfo,
    PhaseTransition,
    SDLCStateResponse,
    TaskInfo,
    TaskSummaryResponse,
)

PHASE_ORDER = [
    "Bootstrap",
    "Spec",
    "Design",
    "Decompose",
    "Build",
    "Ship",
    "Evaluate",
]


def _make_error_state(error_msg: str) -> SDLCStateResponse:
    """Create an error SDLCStateResponse."""
    return SDLCStateResponse(
        current_phase="Unknown",
        phases=[],
        transitions=[],
        dod_progress=DoDProgress(completed=0, total=0, percentage=0.0),
        error=error_msg,
    )


def _make_error_tasks(error_msg: str) -> TaskSummaryResponse:
    """Create an error TaskSummaryResponse."""
    return TaskSummaryResponse(
        total=0,
        completed=0,
        in_progress=0,
        pending=0,
        blocked=0,
        deferred=0,
        cancelled=0,
        tasks=[],
        error=error_msg,
    )


def read_sdlc_state(path: Path) -> SDLCStateResponse:
    """Read and parse .sdlc/state.json into a structured response.

    Args:
        path: Path to the state.json file.

    Returns:
        SDLCStateResponse with parsed data, or an error message if reading fails.
    """
    try:
        content = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return _make_error_state(f"File not found: {path}")
    except OSError as exc:
        return _make_error_state(f"Error reading file: {exc}")

    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        return _make_error_state(f"Invalid JSON: {exc}")

    current_phase = data.get("current_phase", "Unknown")
    raw_phases = data.get("phases", {})

    # Build phase list in canonical order, filling in missing phases
    phases: list[PhaseInfo] = []
    for phase_name in PHASE_ORDER:
        phase_data = raw_phases.get(phase_name, {})
        dod_raw = phase_data.get("dod", [])
        dod_items = [
            DoDItem(item=d.get("item", ""), done=d.get("done", False))
            for d in dod_raw
        ]

        entered_at = phase_data.get("entered_at")
        completed_at = phase_data.get("completed_at")

        if phase_name == current_phase:
            status = "active"
        elif completed_at is not None:
            status = "completed"
        else:
            status = "pending"

        phases.append(
            PhaseInfo(
                name=phase_name,
                status=status,
                entered_at=entered_at,
                completed_at=completed_at,
                dod_items=dod_items,
            )
        )

    # Parse transitions
    raw_transitions = data.get("transitions", [])
    transitions = [
        PhaseTransition(
            from_phase=t.get("from", t.get("from_phase", "")),
            to_phase=t.get("to", t.get("to_phase", "")),
            reason=t.get("reason", ""),
            timestamp=t.get("timestamp", ""),
        )
        for t in raw_transitions
    ]

    # Compute DoD progress for current phase
    active_phase = next((p for p in phases if p.status == "active"), None)
    if active_phase and active_phase.dod_items:
        total = len(active_phase.dod_items)
        completed = sum(1 for d in active_phase.dod_items if d.done)
        percentage = round((completed / total) * 100, 1) if total > 0 else 0.0
    else:
        total = 0
        completed = 0
        percentage = 0.0

    dod_progress = DoDProgress(
        completed=completed,
        total=total,
        percentage=percentage,
    )

    return SDLCStateResponse(
        current_phase=current_phase,
        phases=phases,
        transitions=transitions,
        dod_progress=dod_progress,
        error=None,
    )


def read_task_summary(path: Path) -> TaskSummaryResponse:
    """Read and parse .taskmaster/tasks/tasks.json into a structured response.

    Args:
        path: Path to the tasks.json file.

    Returns:
        TaskSummaryResponse with parsed data, or an error message if reading fails.
    """
    try:
        content = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return _make_error_tasks(f"File not found: {path}")
    except OSError as exc:
        return _make_error_tasks(f"Error reading file: {exc}")

    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        return _make_error_tasks(f"Invalid JSON: {exc}")

    raw_tasks = data.get("tasks", [])

    tasks: list[TaskInfo] = []
    counts: dict[str, int] = {
        "done": 0,
        "in-progress": 0,
        "pending": 0,
        "blocked": 0,
        "deferred": 0,
        "cancelled": 0,
    }

    for t in raw_tasks:
        status = t.get("status", "pending")
        task = TaskInfo(
            id=t.get("id", 0),
            title=t.get("title", ""),
            status=status,
            priority=t.get("priority"),
            description=t.get("description"),
        )
        tasks.append(task)
        if status in counts:
            counts[status] += 1

    return TaskSummaryResponse(
        total=len(tasks),
        completed=counts["done"],
        in_progress=counts["in-progress"],
        pending=counts["pending"],
        blocked=counts["blocked"],
        deferred=counts["deferred"],
        cancelled=counts["cancelled"],
        tasks=tasks,
        error=None,
    )
