"""Tests for RunEngine — run command orchestration (Task 11)."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch
from uuid import UUID, uuid4

from typer.testing import CliRunner

from etc_platform.config import EtcConfig
from etc_platform.graph_engine import GraphEngine
from etc_platform.run_engine import RunEngine

if TYPE_CHECKING:
    import psycopg

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _setup_project(db: psycopg.Connection) -> tuple[UUID, UUID]:
    """Create a project with an active Build phase.

    Returns (project_id, phase_id).
    """
    project = db.execute(
        "INSERT INTO projects (name, root_path, classification) "
        "VALUES ('p', '/tmp', 'greenfield') RETURNING id"
    ).fetchone()
    assert project is not None
    pid = project["id"]

    phase = db.execute(
        "INSERT INTO phases (project_id, name, status) "
        "VALUES (%s, 'Build', 'active') RETURNING id",
        (pid,),
    ).fetchone()
    assert phase is not None

    return pid, phase["id"]


def _setup_graph_with_ready_node(
    db: psycopg.Connection, pid: UUID, phase_id: UUID
) -> tuple[UUID, UUID]:
    """Create a running graph with a ready node.

    Returns (graph_id, node_id).
    """
    graph = db.execute(
        "INSERT INTO execution_graphs (project_id, phase_id, name, status) "
        "VALUES (%s, %s, 'test-graph', 'running') RETURNING id",
        (pid, phase_id),
    ).fetchone()
    assert graph is not None

    node = db.execute(
        "INSERT INTO execution_nodes (graph_id, node_type, name, agent_type, status, assignment) "
        "VALUES (%s, 'leaf', 'test-node', 'researcher', 'ready', '{\"task\": \"do research\"}') RETURNING id",
        (graph["id"],),
    ).fetchone()
    assert node is not None

    return graph["id"], node["id"]


# ===========================================================================
# TestRunEngine
# ===========================================================================


class TestRunEngine:
    def test_get_pending_actions_empty(self, db: psycopg.Connection) -> None:
        """No pending actions when project has no graphs or ready nodes."""
        pid, phase_id = _setup_project(db)
        config = EtcConfig()
        engine = RunEngine(pid, config=config)

        actions = engine.get_pending_actions(db)
        assert actions == []

    def test_get_pending_actions_with_ready_nodes(self, db: psycopg.Connection) -> None:
        """Reports ready nodes as pending actions."""
        pid, phase_id = _setup_project(db)
        graph_id, node_id = _setup_graph_with_ready_node(db, pid, phase_id)

        config = EtcConfig()
        engine = RunEngine(pid, config=config)

        actions = engine.get_pending_actions(db)
        assert len(actions) >= 1

        # Should find the ready node action
        deploy_actions = [a for a in actions if a["action"] == "deploy_agent"]
        assert len(deploy_actions) == 1
        assert deploy_actions[0]["node_id"] == node_id

    def test_check_graph_completions_none(self, db: psycopg.Connection) -> None:
        """No completions when graph has incomplete nodes."""
        pid, phase_id = _setup_project(db)
        graph_id, node_id = _setup_graph_with_ready_node(db, pid, phase_id)

        config = EtcConfig()
        engine = RunEngine(pid, config=config)

        completed = engine.check_graph_completions(db)
        assert completed == []

    def test_check_graph_completions_marks_complete(self, db: psycopg.Connection) -> None:
        """Marks a graph as completed when all nodes are done."""
        pid, phase_id = _setup_project(db)

        # Create a graph with a single completed node
        graph = db.execute(
            "INSERT INTO execution_graphs (project_id, phase_id, name, status) "
            "VALUES (%s, %s, 'done-graph', 'running') RETURNING id",
            (pid, phase_id),
        ).fetchone()
        assert graph is not None
        graph_id = graph["id"]

        db.execute(
            "INSERT INTO execution_nodes (graph_id, node_type, name, agent_type, status) "
            "VALUES (%s, 'leaf', 'done-node', 'researcher', 'completed')",
            (graph_id,),
        )

        config = EtcConfig()
        engine = RunEngine(pid, config=config)

        completed = engine.check_graph_completions(db)
        assert graph_id in completed

        # Verify graph status was updated
        row = db.execute(
            "SELECT status FROM execution_graphs WHERE id = %s", (graph_id,)
        ).fetchone()
        assert row is not None
        assert row["status"] == "completed"

    def test_get_status(self, db: psycopg.Connection) -> None:
        """get_status returns comprehensive project status."""
        pid, phase_id = _setup_project(db)
        graph_id, node_id = _setup_graph_with_ready_node(db, pid, phase_id)

        config = EtcConfig()
        engine = RunEngine(pid, config=config)

        status = engine.get_status(db)

        assert "phase" in status
        assert status["phase"]["name"] == "Build"
        assert status["phase"]["status"] == "active"
        assert "dod" in status
        assert "active_graphs" in status
        assert len(status["active_graphs"]) == 1
        assert "node_counts" in status
        assert status["node_counts"]["ready"] >= 1
        assert "recent_events" in status

    def test_run_once_no_actions(self, db: psycopg.Connection) -> None:
        """run_once returns summary with no actions taken when nothing to do."""
        pid, phase_id = _setup_project(db)

        config = EtcConfig()
        engine = RunEngine(pid, config=config)

        result = engine.run_once(db)

        assert "actions_taken" in result
        assert result["actions_taken"] == 0
        assert "deployed" in result
        assert "completed_graphs" in result

    def test_run_once_deploys_ready_nodes(self, db: psycopg.Connection) -> None:
        """run_once deploys agents for ready nodes."""
        pid, phase_id = _setup_project(db)
        graph_id, node_id = _setup_graph_with_ready_node(db, pid, phase_id)

        config = EtcConfig()
        engine = RunEngine(pid, config=config)

        mock_run_id = uuid4()

        with patch.object(
            engine.agent_runner, "deploy", return_value=mock_run_id
        ):
            result = engine.run_once(db)

        assert result["actions_taken"] >= 1
        assert len(result["deployed"]) == 1
        assert result["deployed"][0] == mock_run_id


# ===========================================================================
# TestRunCLI
# ===========================================================================


cli_runner = CliRunner()


class TestRunEngineCompositeFiltering:
    def test_deploy_skips_composite_nodes(self, db: psycopg.Connection) -> None:
        """deploy_ready_nodes does not attempt to deploy composite nodes."""
        pid, phase_id = _setup_project(db)
        config = EtcConfig()
        engine = RunEngine(pid, config=config)

        graph_id = GraphEngine.create_graph(db, pid, phase_id, "g")
        composite = GraphEngine.add_node(db, graph_id, "group", "composite")
        GraphEngine.add_node(
            db, graph_id, "task", "leaf",
            agent_type="researcher", parent_node_id=composite, depth=1,
        )
        GraphEngine.start_graph(db, graph_id)

        mock_run_id = uuid4()

        with patch.object(
            engine.agent_runner, "deploy", return_value=mock_run_id
        ):
            # Only the leaf should be deployed, not the composite
            run_ids = engine.deploy_ready_nodes(db)

        assert len(run_ids) == 1

        composite_node = GraphEngine.get_node(db, composite)
        assert composite_node["status"] == "running"  # activated, not deployed

    def test_pending_actions_skip_composite_nodes(self, db: psycopg.Connection) -> None:
        """get_pending_actions does not include composite nodes."""
        pid, phase_id = _setup_project(db)
        config = EtcConfig()
        engine = RunEngine(pid, config=config)

        graph_id = GraphEngine.create_graph(db, pid, phase_id, "g")
        composite = GraphEngine.add_node(db, graph_id, "group", "composite")
        GraphEngine.add_node(
            db, graph_id, "task", "leaf",
            agent_type="researcher", parent_node_id=composite, depth=1,
        )
        GraphEngine.start_graph(db, graph_id)

        actions = engine.get_pending_actions(db)
        deploy_actions = [a for a in actions if a["action"] == "deploy_agent"]
        assert len(deploy_actions) == 1
        assert deploy_actions[0]["node_name"] == "task"


class TestRunCLI:
    def test_run_command_exists(self) -> None:
        """The 'run' command is registered on the app."""
        from etc_platform.cli import app

        result = cli_runner.invoke(app, ["run", "--help"])
        assert result.exit_code == 0
        assert "autonomous" in result.output.lower() or "auto" in result.output.lower()

    def test_agents_command_exists(self) -> None:
        """The 'agents' command is registered on the app."""
        from etc_platform.cli import app

        result = cli_runner.invoke(app, ["agents", "--help"])
        assert result.exit_code == 0
        assert "agent" in result.output.lower()
