"""Tests for the topology CLI commands (etc topology show/approve/reject)."""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from typing import Any, Generator
from unittest.mock import patch
from uuid import UUID

import psycopg
import pytest
from typer.testing import CliRunner

from etc_platform.cli import app

runner = CliRunner()


@pytest.fixture(autouse=True)
def _set_test_dsn() -> None:
    """Point CLI commands at the test database and clean up pool after each test."""
    os.environ["ETC_DATABASE_URL"] = (
        "postgresql://etc:etc_dev@localhost:5433/etc_platform_test"
    )
    yield
    # Close the connection pool that may have been created by CLI invocations,
    # so it doesn't hold connections that block setup_test_db from recreating the DB.
    from etc_platform.db import close_pool

    close_pool()


@pytest.fixture
def patch_get_conn(db: psycopg.Connection):
    """Patch get_conn so that CLI commands use the test transaction.

    This makes data inserted via the ``db`` fixture visible to CLI commands
    and ensures all writes are rolled back together with the test transaction.
    """

    # Save the real commit so we can suppress it during tests
    real_commit = db.commit

    @contextmanager
    def _fake_get_conn() -> Generator[psycopg.Connection, None, None]:
        # Temporarily replace commit with a no-op so CLI commands don't
        # commit the test transaction (which would break rollback isolation).
        db.commit = lambda: None  # type: ignore[assignment]
        try:
            yield db
        finally:
            db.commit = real_commit  # type: ignore[assignment]

    with patch("etc_platform.db.get_conn", _fake_get_conn):
        yield


def _create_project_with_topology_event(
    db: psycopg.Connection,
    *,
    awaiting_approval: bool = True,
) -> tuple[UUID, UUID, dict]:
    """Helper: create a project, activate the Decompose phase, and insert a
    topology_designed event.  Returns (project_id, phase_id, plan_dict).
    """
    # Create project
    row = db.execute(
        "INSERT INTO projects (name, root_path, classification) "
        "VALUES ('topo-test', '.', 'greenfield') RETURNING id"
    ).fetchone()
    project_id = row["id"]

    # Create phases (same as cli init)
    phases = [
        "Bootstrap", "Spec", "Design", "Decompose",
        "Build", "Verify", "Ship", "Evaluate",
    ]
    for name in phases:
        db.execute(
            "INSERT INTO phases (project_id, name, dod_items) VALUES (%s, %s, '[]')",
            (project_id, name),
        )

    # Activate Decompose phase
    db.execute(
        "UPDATE phases SET status = 'active' WHERE project_id = %s AND name = 'Decompose'",
        (project_id,),
    )
    # Complete prior phases
    for name in ["Bootstrap", "Spec", "Design"]:
        db.execute(
            "UPDATE phases SET status = 'completed' WHERE project_id = %s AND name = %s",
            (project_id, name),
        )

    phase_row = db.execute(
        "SELECT id FROM phases WHERE project_id = %s AND name = 'Decompose'",
        (project_id,),
    ).fetchone()
    phase_id = phase_row["id"]

    # Build a plan dict matching TopologyPlan schema
    plan_dict: dict[str, Any] = {
        "layers": [
            {
                "name": "domain-research",
                "dimension": "bounded_context",
                "nodes": [
                    {"name": "R01-compliance", "agent_type": "researcher", "assignment": {}},
                    {"name": "R02-vendors", "agent_type": "researcher", "assignment": {}},
                    {"name": "R03-insurance", "agent_type": "researcher", "assignment": {}},
                ],
            },
            {
                "name": "synthesis",
                "dimension": "synthesis",
                "nodes": [
                    {"name": "synthesis", "agent_type": "researcher", "assignment": {}},
                ],
            },
        ],
        "reduce_strategy": "single_synthesis",
        "estimated_agents": 4,
        "reasoning": "Two domain researchers plus synthesis",
    }

    payload = {
        "action": "topology_designed",
        "plan": plan_dict,
        "reasoning": "test reasoning",
        "awaiting_approval": awaiting_approval,
    }

    db.execute(
        "INSERT INTO events (project_id, event_type, actor, payload) "
        "VALUES (%s, 'phase_gate_reached', 'sem', %s)",
        (project_id, json.dumps(payload)),
    )

    return project_id, phase_id, plan_dict


# =========================================================================
# Command existence tests (no DB needed)
# =========================================================================


class TestTopologyCommandsExist:
    """Verify that topology commands are registered.

    These tests only check that Typer recognises the commands — they do NOT
    need a real database, so we assert solely on the absence of
    ``"No such command"`` in the output.
    """

    def test_topology_show_command_exists(self) -> None:
        result = runner.invoke(app, ["topology", "show", "--help"])
        assert result.exit_code == 0
        assert "No such command" not in (result.output or "")

    def test_topology_approve_command_exists(self) -> None:
        result = runner.invoke(app, ["topology", "approve", "--help"])
        assert result.exit_code == 0
        assert "No such command" not in (result.output or "")

    def test_topology_reject_command_exists(self) -> None:
        result = runner.invoke(app, ["topology", "reject", "--help"])
        assert result.exit_code == 0
        assert "No such command" not in (result.output or "")

    def test_topology_help(self) -> None:
        result = runner.invoke(app, ["topology", "--help"])
        assert result.exit_code == 0
        assert "Topology" in result.output


# =========================================================================
# Show command
# =========================================================================


class TestTopologyShow:
    def test_show_no_active_project(self, db, patch_get_conn) -> None:
        result = runner.invoke(app, ["topology", "show"])
        assert result.exit_code == 0
        assert "No active project" in result.output

    def test_show_no_pending_topology(self, db, patch_get_conn) -> None:
        # Create a project but no topology event
        db.execute(
            "INSERT INTO projects (name, root_path, classification) "
            "VALUES ('empty-proj', '.', 'greenfield')"
        )
        # Need phases so _require_active_project finds it
        db.execute(
            "INSERT INTO phases (project_id, name, dod_items) "
            "SELECT id, 'Bootstrap', '[]' FROM projects WHERE name = 'empty-proj'"
        )
        db.execute(
            "UPDATE projects SET status = 'active' WHERE name = 'empty-proj'"
        )
        result = runner.invoke(app, ["topology", "show"])
        assert result.exit_code == 0
        assert "No pending topology" in result.output

    def test_show_renders_topology_tree(self, db, patch_get_conn) -> None:
        _create_project_with_topology_event(db)
        result = runner.invoke(app, ["topology", "show"])
        assert result.exit_code == 0
        # Check key pieces of the rendered tree
        assert "domain-research" in result.output
        assert "R01-compliance" in result.output
        assert "R02-vendors" in result.output
        assert "R03-insurance" in result.output
        assert "synthesis" in result.output
        assert "researcher" in result.output
        assert "single_synthesis" in result.output

    def test_show_skips_already_approved(self, db, patch_get_conn) -> None:
        """A topology with awaiting_approval=false should not be shown."""
        _create_project_with_topology_event(db, awaiting_approval=False)
        result = runner.invoke(app, ["topology", "show"])
        assert result.exit_code == 0
        assert "No pending topology" in result.output


# =========================================================================
# Approve command
# =========================================================================


class TestTopologyApprove:
    def test_approve_no_active_project(self, db, patch_get_conn) -> None:
        result = runner.invoke(app, ["topology", "approve"])
        assert result.exit_code == 0
        assert "No active project" in result.output

    def test_approve_no_pending_topology(self, db, patch_get_conn) -> None:
        db.execute(
            "INSERT INTO projects (name, root_path, classification) "
            "VALUES ('empty-proj', '.', 'greenfield')"
        )
        db.execute(
            "INSERT INTO phases (project_id, name, dod_items) "
            "SELECT id, 'Bootstrap', '[]' FROM projects WHERE name = 'empty-proj'"
        )
        result = runner.invoke(app, ["topology", "approve"])
        assert result.exit_code == 0
        assert "No pending topology" in result.output

    def test_approve_creates_graph_and_event(self, db, patch_get_conn) -> None:
        project_id, phase_id, plan_dict = _create_project_with_topology_event(db)
        result = runner.invoke(app, ["topology", "approve"])
        assert result.exit_code == 0
        assert "approved" in result.output.lower()

        # Verify execution graph was created
        graph = db.execute(
            "SELECT * FROM execution_graphs WHERE project_id = %s",
            (project_id,),
        ).fetchone()
        assert graph is not None

        # Verify nodes were created
        nodes = db.execute(
            "SELECT * FROM execution_nodes WHERE graph_id = %s ORDER BY depth, name",
            (graph["id"],),
        ).fetchall()
        assert len(nodes) >= 4  # 3 researchers + 1 synthesis

        # Verify approval event was emitted
        approval_event = db.execute(
            "SELECT * FROM events WHERE project_id = %s AND event_type = 'human_response' "
            "AND payload->>'action' = 'topology_approved' "
            "ORDER BY created_at DESC LIMIT 1",
            (project_id,),
        ).fetchone()
        assert approval_event is not None


# =========================================================================
# Reject command
# =========================================================================


class TestTopologyReject:
    def test_reject_no_active_project(self, db, patch_get_conn) -> None:
        result = runner.invoke(app, ["topology", "reject", "too few agents"])
        assert result.exit_code == 0
        assert "No active project" in result.output

    def test_reject_no_pending_topology(self, db, patch_get_conn) -> None:
        db.execute(
            "INSERT INTO projects (name, root_path, classification) "
            "VALUES ('empty-proj', '.', 'greenfield')"
        )
        db.execute(
            "INSERT INTO phases (project_id, name, dod_items) "
            "SELECT id, 'Bootstrap', '[]' FROM projects WHERE name = 'empty-proj'"
        )
        result = runner.invoke(app, ["topology", "reject", "not enough agents"])
        assert result.exit_code == 0
        assert "No pending topology" in result.output

    def test_reject_emits_event(self, db, patch_get_conn) -> None:
        project_id, _, _ = _create_project_with_topology_event(db)
        reason = "Need separate insurance sub-domains"
        result = runner.invoke(app, ["topology", "reject", reason])
        assert result.exit_code == 0
        assert "rejected" in result.output.lower()

        # Verify rejection event
        rejection_event = db.execute(
            "SELECT * FROM events WHERE project_id = %s AND event_type = 'human_response' "
            "AND payload->>'action' = 'topology_rejected' "
            "ORDER BY created_at DESC LIMIT 1",
            (project_id,),
        ).fetchone()
        assert rejection_event is not None
        assert rejection_event["payload"]["reason"] == reason

    def test_reject_does_not_create_graph(self, db, patch_get_conn) -> None:
        project_id, _, _ = _create_project_with_topology_event(db)
        runner.invoke(app, ["topology", "reject", "bad plan"])
        graph = db.execute(
            "SELECT * FROM execution_graphs WHERE project_id = %s",
            (project_id,),
        ).fetchone()
        assert graph is None
