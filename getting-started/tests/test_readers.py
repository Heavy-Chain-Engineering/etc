"""Tests for src/readers.py — JSON file readers for SDLC state and tasks."""

from pathlib import Path

import pytest

from src.readers import read_sdlc_state, read_task_summary


class TestReadSdlcState:
    """Tests for the read_sdlc_state function."""

    def test_should_return_state_when_given_valid_file(
        self, valid_state_path: Path
    ) -> None:
        result = read_sdlc_state(valid_state_path)
        assert result.error is None
        assert result.current_phase == "Build"
        assert len(result.phases) == 7
        assert result.dod_progress.completed == 1
        assert result.dod_progress.total == 3
        assert result.dod_progress.percentage == pytest.approx(33.3, abs=0.1)

    def test_should_return_error_when_file_missing(
        self, missing_file_path: Path
    ) -> None:
        result = read_sdlc_state(missing_file_path)
        assert result.error is not None
        assert "not found" in result.error.lower() or "no such file" in result.error.lower()
        assert result.current_phase == "Unknown"

    def test_should_return_error_when_json_malformed(
        self, malformed_json_path: Path
    ) -> None:
        result = read_sdlc_state(malformed_json_path)
        assert result.error is not None
        assert result.current_phase == "Unknown"

    def test_should_handle_minimal_state_when_phases_incomplete(
        self, minimal_state_path: Path
    ) -> None:
        result = read_sdlc_state(minimal_state_path)
        assert result.error is None
        assert result.current_phase == "Bootstrap"
        # Should still have all 7 phases (missing ones filled in as pending)
        assert len(result.phases) == 7

    def test_should_parse_transitions_when_present(
        self, valid_state_path: Path
    ) -> None:
        result = read_sdlc_state(valid_state_path)
        assert len(result.transitions) == 2
        assert result.transitions[0].from_phase == "Bootstrap"
        assert result.transitions[0].to_phase == "Spec"

    def test_should_compute_dod_progress_for_active_phase(
        self, valid_state_path: Path
    ) -> None:
        result = read_sdlc_state(valid_state_path)
        # Build phase has 3 DoD items, 1 done
        assert result.dod_progress.total == 3
        assert result.dod_progress.completed == 1

    def test_should_identify_phase_statuses_correctly(
        self, valid_state_path: Path
    ) -> None:
        result = read_sdlc_state(valid_state_path)
        phase_map = {p.name: p.status for p in result.phases}
        assert phase_map["Bootstrap"] == "completed"
        assert phase_map["Spec"] == "completed"
        assert phase_map["Build"] == "active"
        assert phase_map["Ship"] == "pending"
        assert phase_map["Evaluate"] == "pending"


class TestReadTaskSummary:
    """Tests for the read_task_summary function."""

    def test_should_return_summary_when_given_valid_file(
        self, valid_tasks_path: Path
    ) -> None:
        result = read_task_summary(valid_tasks_path)
        assert result.error is None
        assert result.total == 5
        assert result.completed == 2
        assert result.in_progress == 1
        assert result.pending == 1
        assert result.blocked == 1

    def test_should_return_error_when_file_missing(
        self, missing_file_path: Path
    ) -> None:
        result = read_task_summary(missing_file_path)
        assert result.error is not None
        assert result.total == 0

    def test_should_return_error_when_json_malformed(
        self, malformed_json_path: Path
    ) -> None:
        result = read_task_summary(malformed_json_path)
        assert result.error is not None
        assert result.total == 0

    def test_should_return_zero_counts_when_no_tasks(
        self, empty_tasks_path: Path
    ) -> None:
        result = read_task_summary(empty_tasks_path)
        assert result.error is None
        assert result.total == 0
        assert result.completed == 0
        assert result.in_progress == 0
        assert result.pending == 0
        assert result.blocked == 0

    def test_should_include_task_list_when_requested(
        self, valid_tasks_path: Path
    ) -> None:
        result = read_task_summary(valid_tasks_path)
        assert len(result.tasks) == 5
        assert result.tasks[0].title == "Setup project"
        assert result.tasks[0].status == "done"

    def test_should_handle_unknown_statuses_gracefully(
        self, tmp_path: Path
    ) -> None:
        """Tasks with unknown statuses should not crash the reader."""
        tasks_file = tmp_path / "tasks.json"
        tasks_file.write_text(
            '{"tasks": [{"id": 1, "title": "Mystery", "status": "mystery-status"}]}'
        )
        result = read_task_summary(tasks_file)
        assert result.error is None
        assert result.total == 1
        # Unknown status counts should not show up in known buckets
        assert result.completed == 0
        assert result.in_progress == 0
        assert result.pending == 0
        assert result.blocked == 0
