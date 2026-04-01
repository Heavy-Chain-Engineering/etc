"""Tests for src/models.py — Pydantic data models for the SDLC Dashboard API."""

import pytest
from src.models import (
    DoDItem,
    DoDProgress,
    PhaseInfo,
    PhaseTransition,
    SDLCStateResponse,
    TaskInfo,
    TaskSummaryResponse,
)


class TestDoDItem:
    """Tests for the DoDItem model."""

    def test_should_create_dod_item_when_given_valid_data(self) -> None:
        item = DoDItem(item="Write tests first", done=True)
        assert item.item == "Write tests first"
        assert item.done is True

    def test_should_default_done_to_false_when_not_provided(self) -> None:
        item = DoDItem(item="Some criterion")
        assert item.done is False


class TestDoDProgress:
    """Tests for the DoDProgress model."""

    def test_should_compute_percentage_when_given_completed_and_total(self) -> None:
        progress = DoDProgress(completed=3, total=6, percentage=50.0)
        assert progress.completed == 3
        assert progress.total == 6
        assert progress.percentage == 50.0

    def test_should_handle_zero_total_when_no_items(self) -> None:
        progress = DoDProgress(completed=0, total=0, percentage=0.0)
        assert progress.percentage == 0.0


class TestPhaseInfo:
    """Tests for the PhaseInfo model."""

    def test_should_create_phase_info_when_given_valid_data(self) -> None:
        phase = PhaseInfo(
            name="Build",
            status="active",
            entered_at="2026-02-25T10:00:00Z",
            completed_at=None,
            dod_items=[DoDItem(item="All tests pass", done=False)],
        )
        assert phase.name == "Build"
        assert phase.status == "active"
        assert phase.entered_at == "2026-02-25T10:00:00Z"
        assert phase.completed_at is None
        assert len(phase.dod_items) == 1

    def test_should_default_to_empty_dod_items_when_not_provided(self) -> None:
        phase = PhaseInfo(name="Spec", status="pending")
        assert phase.dod_items == []
        assert phase.entered_at is None
        assert phase.completed_at is None


class TestPhaseTransition:
    """Tests for the PhaseTransition model."""

    def test_should_create_transition_when_given_valid_data(self) -> None:
        t = PhaseTransition(
            from_phase="Bootstrap",
            to_phase="Spec",
            reason="Bootstrap complete",
            timestamp="2026-02-25T10:00:00Z",
        )
        assert t.from_phase == "Bootstrap"
        assert t.to_phase == "Spec"
        assert t.reason == "Bootstrap complete"
        assert t.timestamp == "2026-02-25T10:00:00Z"


class TestSDLCStateResponse:
    """Tests for the SDLCStateResponse model."""

    def test_should_create_state_response_when_given_full_data(self) -> None:
        resp = SDLCStateResponse(
            current_phase="Build",
            phases=[
                PhaseInfo(name="Bootstrap", status="completed"),
                PhaseInfo(name="Build", status="active"),
            ],
            transitions=[],
            dod_progress=DoDProgress(completed=1, total=3, percentage=33.3),
            error=None,
        )
        assert resp.current_phase == "Build"
        assert len(resp.phases) == 2
        assert resp.error is None

    def test_should_create_error_response_when_file_missing(self) -> None:
        resp = SDLCStateResponse(
            current_phase="Unknown",
            phases=[],
            transitions=[],
            dod_progress=DoDProgress(completed=0, total=0, percentage=0.0),
            error="state.json not found",
        )
        assert resp.error == "state.json not found"
        assert resp.current_phase == "Unknown"

    def test_should_default_to_empty_lists_when_not_provided(self) -> None:
        resp = SDLCStateResponse(
            current_phase="Spec",
            dod_progress=DoDProgress(completed=0, total=0, percentage=0.0),
        )
        assert resp.phases == []
        assert resp.transitions == []
        assert resp.error is None


class TestTaskInfo:
    """Tests for the TaskInfo model."""

    def test_should_create_task_info_when_given_valid_data(self) -> None:
        task = TaskInfo(
            id=1,
            title="Build thing",
            status="in-progress",
        )
        assert task.id == 1
        assert task.title == "Build thing"
        assert task.status == "in-progress"

    def test_should_handle_optional_fields_when_not_provided(self) -> None:
        task = TaskInfo(id=1, title="Test", status="pending")
        assert task.priority is None
        assert task.description is None


class TestTaskSummaryResponse:
    """Tests for the TaskSummaryResponse model."""

    def test_should_create_summary_when_given_valid_counts(self) -> None:
        resp = TaskSummaryResponse(
            total=10,
            completed=3,
            in_progress=2,
            pending=4,
            blocked=1,
            deferred=0,
            cancelled=0,
        )
        assert resp.total == 10
        assert resp.completed == 3
        assert resp.error is None

    def test_should_create_error_response_when_tasks_unavailable(self) -> None:
        resp = TaskSummaryResponse(
            total=0,
            completed=0,
            in_progress=0,
            pending=0,
            blocked=0,
            deferred=0,
            cancelled=0,
            error="tasks.json not found",
        )
        assert resp.error == "tasks.json not found"
        assert resp.total == 0

    def test_should_include_tasks_list_when_provided(self) -> None:
        task = TaskInfo(id=1, title="Do it", status="done")
        resp = TaskSummaryResponse(
            total=1,
            completed=1,
            in_progress=0,
            pending=0,
            blocked=0,
            deferred=0,
            cancelled=0,
            tasks=[task],
        )
        assert len(resp.tasks) == 1
        assert resp.tasks[0].title == "Do it"

    def test_should_default_to_empty_tasks_when_not_provided(self) -> None:
        resp = TaskSummaryResponse(
            total=0, completed=0, in_progress=0,
            pending=0, blocked=0, deferred=0, cancelled=0,
        )
        assert resp.tasks == []
