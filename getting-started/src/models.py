"""Pydantic data models for the SDLC Dashboard API.

Defines response models for all API endpoints. Every FastAPI endpoint
uses these as response_model to satisfy INV-002.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class DoDItem(BaseModel):
    """A single definition-of-done checklist item."""

    item: str
    done: bool = False


class DoDProgress(BaseModel):
    """Aggregated progress for the current phase's DoD items."""

    completed: int
    total: int
    percentage: float


class PhaseInfo(BaseModel):
    """Information about a single SDLC phase."""

    name: str
    status: str  # "pending" | "active" | "completed"
    entered_at: str | None = None
    completed_at: str | None = None
    dod_items: list[DoDItem] = Field(default_factory=list)


class PhaseTransition(BaseModel):
    """A record of a phase transition."""

    from_phase: str
    to_phase: str
    reason: str
    timestamp: str


class SDLCStateResponse(BaseModel):
    """Response model for GET /api/state."""

    current_phase: str
    phases: list[PhaseInfo] = Field(default_factory=list)
    transitions: list[PhaseTransition] = Field(default_factory=list)
    dod_progress: DoDProgress
    error: str | None = None


class TaskInfo(BaseModel):
    """Information about a single task from TaskMaster."""

    id: int
    title: str
    status: str
    priority: str | None = None
    description: str | None = None


class TaskSummaryResponse(BaseModel):
    """Response model for GET /api/tasks."""

    total: int
    completed: int
    in_progress: int
    pending: int
    blocked: int
    deferred: int
    cancelled: int
    tasks: list[TaskInfo] = Field(default_factory=list)
    error: str | None = None
