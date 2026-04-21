"""Tests for ProjectMetrics — observability module (Task 14)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest

from etc_platform.metrics import ProjectMetrics

if TYPE_CHECKING:
    from uuid import UUID

    import psycopg

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PHASE_NAMES = [
    "Bootstrap", "Spec", "Design", "Decompose",
    "Build", "Verify", "Ship", "Evaluate",
]


def _create_project(db: psycopg.Connection) -> UUID:
    row = db.execute(
        "INSERT INTO projects (name, root_path, classification) "
        "VALUES ('metrics-test', '/tmp', 'greenfield') RETURNING id"
    ).fetchone()
    assert row is not None
    return row["id"]


def _create_all_phases(db: psycopg.Connection, project_id: UUID) -> dict[str, UUID]:
    phases: dict[str, UUID] = {}
    for name in PHASE_NAMES:
        row = db.execute(
            "INSERT INTO phases (project_id, name) VALUES (%s, %s) RETURNING id",
            (project_id, name),
        ).fetchone()
        assert row is not None
        phases[name] = row["id"]
    return phases


def _create_graph_node_run(
    db: psycopg.Connection,
    project_id: UUID,
    phase_id: UUID,
    *,
    status: str = "completed",
    tokens_input: int | None = None,
    tokens_output: int | None = None,
    completed_at: datetime | None = None,
    agent_type: str = "researcher",
) -> tuple[UUID, UUID, UUID]:
    """Create graph -> node -> run chain. Returns (graph_id, node_id, run_id)."""
    graph = db.execute(
        "INSERT INTO execution_graphs (project_id, phase_id, name, status) "
        "VALUES (%s, %s, 'g', 'running') RETURNING id",
        (project_id, phase_id),
    ).fetchone()
    assert graph is not None

    node = db.execute(
        "INSERT INTO execution_nodes (graph_id, node_type, name, status) "
        "VALUES (%s, 'leaf', 'n', 'running') RETURNING id",
        (graph["id"],),
    ).fetchone()
    assert node is not None

    run = db.execute(
        "INSERT INTO agent_runs (node_id, agent_type, model, status, "
        "  tokens_input, tokens_output, completed_at) "
        "VALUES (%s, %s, 'test', %s, %s, %s, %s) RETURNING id",
        (node["id"], agent_type, status, tokens_input, tokens_output, completed_at),
    ).fetchone()
    assert run is not None

    return graph["id"], node["id"], run["id"]


# ===========================================================================
# TestMetrics
# ===========================================================================


class TestMetrics:

    def test_token_usage(self, db: psycopg.Connection) -> None:
        """Token usage aggregates across all runs in the project."""
        pid = _create_project(db)
        phases = _create_all_phases(db, pid)

        # Two runs with known token counts
        _create_graph_node_run(
            db, pid, phases["Build"], tokens_input=100, tokens_output=200,
        )
        _create_graph_node_run(
            db, pid, phases["Build"], tokens_input=300, tokens_output=400,
        )

        usage = ProjectMetrics.get_token_usage(db, pid)

        assert usage["input_tokens"] == 400
        assert usage["output_tokens"] == 600
        assert usage["total_tokens"] == 1000

    def test_token_usage_empty(self, db: psycopg.Connection) -> None:
        """Token usage returns zeros when no runs exist."""
        pid = _create_project(db)
        usage = ProjectMetrics.get_token_usage(db, pid)
        assert usage["input_tokens"] == 0
        assert usage["output_tokens"] == 0
        assert usage["total_tokens"] == 0

    def test_agent_velocity(self, db: psycopg.Connection) -> None:
        """Agent velocity counts completed and failed runs."""
        pid = _create_project(db)
        phases = _create_all_phases(db, pid)

        now = datetime.now(UTC)
        # 2 completed runs with duration
        _create_graph_node_run(
            db, pid, phases["Build"], status="completed",
            tokens_input=10, tokens_output=20,
            completed_at=now,
        )
        _create_graph_node_run(
            db, pid, phases["Build"], status="completed",
            tokens_input=10, tokens_output=20,
            completed_at=now,
        )
        # 1 failed run
        _create_graph_node_run(
            db, pid, phases["Build"], status="failed",
        )

        velocity = ProjectMetrics.get_agent_velocity(db, pid)

        assert velocity["total_runs"] == 3
        assert velocity["completed"] == 2
        assert velocity["failed"] == 1

    def test_agent_velocity_empty(self, db: psycopg.Connection) -> None:
        """Agent velocity returns zeros when no runs exist."""
        pid = _create_project(db)
        velocity = ProjectMetrics.get_agent_velocity(db, pid)
        assert velocity["total_runs"] == 0
        assert velocity["completed"] == 0
        assert velocity["failed"] == 0
        assert velocity["avg_duration_seconds"] is None

    def test_phase_duration(self, db: psycopg.Connection) -> None:
        """Phase duration reports timestamps and durations for each phase."""
        pid = _create_project(db)
        phases = _create_all_phases(db, pid)

        now = datetime.now(UTC)
        earlier = now - timedelta(hours=2)

        # Mark Bootstrap as completed with timestamps
        db.execute(
            "UPDATE phases SET status = 'completed', entered_at = %s, completed_at = %s "
            "WHERE id = %s",
            (earlier, now, phases["Bootstrap"]),
        )
        # Mark Spec as active with only entered_at
        db.execute(
            "UPDATE phases SET status = 'active', entered_at = %s WHERE id = %s",
            (now, phases["Spec"]),
        )

        durations = ProjectMetrics.get_phase_duration(db, pid)
        assert len(durations) == 8

        # Bootstrap should have a duration (roughly 7200 seconds)
        bootstrap = durations[0]
        assert bootstrap["name"] == "Bootstrap"
        assert bootstrap["status"] == "completed"
        assert bootstrap["duration_seconds"] is not None
        assert bootstrap["duration_seconds"] >= 7199  # allow small clock drift

        # Spec should have no duration (no completed_at)
        spec = durations[1]
        assert spec["name"] == "Spec"
        assert spec["status"] == "active"
        assert spec["duration_seconds"] is None

    def test_guardrail_stats(self, db: psycopg.Connection) -> None:
        """Guardrail stats count pass/fail across rules."""
        pid = _create_project(db)
        phases = _create_all_phases(db, pid)

        # Create output chain
        graph = db.execute(
            "INSERT INTO execution_graphs (project_id, phase_id, name, status) "
            "VALUES (%s, %s, 'g', 'running') RETURNING id",
            (pid, phases["Build"]),
        ).fetchone()
        node = db.execute(
            "INSERT INTO execution_nodes (graph_id, node_type, name, status) "
            "VALUES (%s, 'leaf', 'n', 'running') RETURNING id",
            (graph["id"],),
        ).fetchone()
        run = db.execute(
            "INSERT INTO agent_runs (node_id, agent_type, model, status) "
            "VALUES (%s, 'researcher', 'test', 'completed') RETURNING id",
            (node["id"],),
        ).fetchone()
        output = db.execute(
            "INSERT INTO agent_outputs (run_id, output_type) VALUES (%s, 'research_report') RETURNING id",
            (run["id"],),
        ).fetchone()

        # Insert guardrail checks
        db.execute(
            "INSERT INTO guardrail_checks (output_id, rule_name, passed, severity) "
            "VALUES (%s, 'anti_pattern_scan', true, 'critical')",
            (output["id"],),
        )
        db.execute(
            "INSERT INTO guardrail_checks (output_id, rule_name, passed, severity) "
            "VALUES (%s, 'output_schema_validation', true, 'high')",
            (output["id"],),
        )
        db.execute(
            "INSERT INTO guardrail_checks (output_id, rule_name, passed, severity) "
            "VALUES (%s, 'anti_pattern_scan', false, 'critical')",
            (output["id"],),
        )

        stats = ProjectMetrics.get_guardrail_stats(db, pid)
        assert stats["total_checks"] == 3
        assert stats["passed"] == 2
        assert stats["failed"] == 1
        assert stats["pass_rate"] == pytest.approx(2 / 3)
        assert "anti_pattern_scan" in stats["by_rule"]
        assert stats["by_rule"]["anti_pattern_scan"]["passed"] == 1
        assert stats["by_rule"]["anti_pattern_scan"]["failed"] == 1
        assert stats["by_rule"]["output_schema_validation"]["passed"] == 1

    def test_guardrail_stats_empty(self, db: psycopg.Connection) -> None:
        """Guardrail stats return zeros when no checks exist."""
        pid = _create_project(db)
        stats = ProjectMetrics.get_guardrail_stats(db, pid)
        assert stats["total_checks"] == 0
        assert stats["pass_rate"] is None

    def test_project_summary(self, db: psycopg.Connection) -> None:
        """Project summary combines all metrics."""
        pid = _create_project(db)
        phases = _create_all_phases(db, pid)

        # Add some data
        _create_graph_node_run(
            db, pid, phases["Build"], tokens_input=50, tokens_output=100,
        )

        summary = ProjectMetrics.get_project_summary(db, pid)
        assert summary["project_id"] == pid
        assert "token_usage" in summary
        assert summary["token_usage"]["total_tokens"] == 150
        assert "agent_velocity" in summary
        assert summary["agent_velocity"]["total_runs"] == 1
        assert "phase_durations" in summary
        assert len(summary["phase_durations"]) == 8
        assert "guardrail_stats" in summary
