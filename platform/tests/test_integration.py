"""End-to-end integration tests — Task 14.

Exercises cross-module flows: init -> graph creation -> agent deployment ->
guardrails -> phase gate. All tests use the real Postgres DB (via the `db`
fixture) but never call the real Claude API.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch, MagicMock
from uuid import UUID, uuid4

import psycopg
import pytest

from etc_platform.config import EtcConfig
from etc_platform.events import EventType, emit_event
from etc_platform.graph_engine import GraphEngine, build_fanout_graph
from etc_platform.guardrails import GuardrailMiddleware
from etc_platform.intake import add_source_material, list_source_materials, triage_summary
from etc_platform.knowledge import (
    contribute_knowledge,
    detect_conflicts,
    query_knowledge,
    resolve_conflict,
)
from etc_platform.phases import PhaseEngine
from etc_platform.run_engine import RunEngine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PHASE_NAMES = [
    "Bootstrap", "Spec", "Design", "Decompose",
    "Build", "Verify", "Ship", "Evaluate",
]


def _create_project(db: psycopg.Connection) -> UUID:
    """Insert a project and return its id."""
    row = db.execute(
        "INSERT INTO projects (name, root_path, classification) "
        "VALUES ('e2e-test', '/tmp', 'greenfield') RETURNING id"
    ).fetchone()
    assert row is not None
    return row["id"]


def _create_all_phases(db: psycopg.Connection, project_id: UUID) -> dict[str, UUID]:
    """Insert all 8 SDLC phases and return {name: phase_id}."""
    phases: dict[str, UUID] = {}
    for name in PHASE_NAMES:
        row = db.execute(
            "INSERT INTO phases (project_id, name) VALUES (%s, %s) RETURNING id",
            (project_id, name),
        ).fetchone()
        assert row is not None
        phases[name] = row["id"]
    return phases


def _setup_output_chain(
    db: psycopg.Connection,
    project_id: UUID,
    phase_id: UUID,
    output_type: str = "research_report",
) -> tuple[UUID, UUID, UUID, UUID, UUID]:
    """Create the full FK chain: graph -> node -> run -> output.

    Returns (graph_id, node_id, run_id, output_id, project_id).
    """
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
        "INSERT INTO agent_runs (node_id, agent_type, model, status) "
        "VALUES (%s, 'researcher', 'test-model', 'completed') RETURNING id",
        (node["id"],),
    ).fetchone()
    assert run is not None

    output = db.execute(
        "INSERT INTO agent_outputs (run_id, output_type) VALUES (%s, %s) RETURNING id",
        (run["id"], output_type),
    ).fetchone()
    assert output is not None

    return graph["id"], node["id"], run["id"], output["id"], project_id


# ===========================================================================
# TestFullProjectLifecycle
# ===========================================================================


class TestFullProjectLifecycle:
    """Test the complete flow from init to phase gate."""

    def test_init_to_bootstrap(self, db: psycopg.Connection) -> None:
        """Create project, add phases, activate Bootstrap, add DoD, check DoD."""
        # 1. Insert project
        pid = _create_project(db)

        # 2. Insert all 8 phases
        phases = _create_all_phases(db, pid)
        assert len(phases) == 8

        # 3. Activate Bootstrap phase
        PhaseEngine.activate_phase(db, pid, "Bootstrap")
        current = PhaseEngine.get_current_phase(db, pid)
        assert current is not None
        assert current["name"] == "Bootstrap"
        assert current["status"] == "active"

        # 4. Add DoD items
        PhaseEngine.add_dod_item(db, phases["Bootstrap"], "Source materials ingested", "automatic")
        PhaseEngine.add_dod_item(db, phases["Bootstrap"], "Domain model drafted", "agent_verified")

        # 5. Check DoD items (both unchecked)
        dod = PhaseEngine.evaluate_dod(db, phases["Bootstrap"])
        assert dod["total"] == 2
        assert dod["checked"] == 0
        assert dod["passed"] is False

        # 6. Check both items -> DoD should pass
        PhaseEngine.check_dod_item(db, phases["Bootstrap"], 0, "integration_test")
        PhaseEngine.check_dod_item(db, phases["Bootstrap"], 1, "integration_test")
        dod = PhaseEngine.evaluate_dod(db, phases["Bootstrap"])
        assert dod["total"] == 2
        assert dod["checked"] == 2
        assert dod["passed"] is True

        # 7. Advance to Spec phase
        next_phase = PhaseEngine.advance_phase(
            db, pid, reason="Bootstrap DoD met", approved_by="integration_test"
        )
        assert next_phase == "Spec"

        # 8. Verify transition recorded
        transitions = db.execute(
            "SELECT * FROM phase_transitions WHERE project_id = %s", (pid,)
        ).fetchall()
        assert len(transitions) == 1
        assert transitions[0]["from_phase"] == "Bootstrap"
        assert transitions[0]["to_phase"] == "Spec"

        # Verify current phase is now Spec
        current = PhaseEngine.get_current_phase(db, pid)
        assert current is not None
        assert current["name"] == "Spec"
        assert current["status"] == "active"

    def test_source_material_triage(self, db: psycopg.Connection) -> None:
        """Add source materials, verify triage summary."""
        pid = _create_project(db)

        # Add multiple source materials with different types/classifications
        add_source_material(
            db, pid, "Legacy DB Export", "export",
            classification="implementation_artifact", priority="primary",
        )
        add_source_material(
            db, pid, "Business Process Doc", "document",
            classification="business_operations", priority="high",
        )
        add_source_material(
            db, pid, "Requirements Spec", "pdf",
            classification="requirements", priority="primary",
        )
        add_source_material(
            db, pid, "Domain Truth", "document",
            classification="domain_truth", priority="medium",
        )

        # Verify listing
        materials = list_source_materials(db, pid)
        assert len(materials) == 4

        # Verify triage summary counts
        summary = triage_summary(db, pid)
        assert summary["total"] == 4
        assert summary["by_classification"]["implementation_artifact"] == 1
        assert summary["by_classification"]["business_operations"] == 1
        assert summary["by_classification"]["requirements"] == 1
        assert summary["by_classification"]["domain_truth"] == 1
        assert summary["by_priority"]["primary"] == 2
        assert summary["by_priority"]["high"] == 1
        assert summary["by_priority"]["medium"] == 1

    def test_fanout_graph_lifecycle(self, db: psycopg.Connection) -> None:
        """Build fan-out graph, complete nodes, verify graph completion."""
        pid = _create_project(db)
        phases = _create_all_phases(db, pid)
        PhaseEngine.activate_phase(db, pid, "Build")

        # Build fan-out graph with 3 leaf nodes + 1 reduce
        agents = [
            {"name": "researcher-1", "agent_type": "researcher", "assignment": {"task": "research A"}},
            {"name": "researcher-2", "agent_type": "researcher", "assignment": {"task": "research B"}},
            {"name": "researcher-3", "agent_type": "researcher", "assignment": {"task": "research C"}},
        ]
        reduce_agent = {"name": "synthesizer", "agent_type": "synthesizer", "assignment": {"task": "merge"}}

        graph_id = build_fanout_graph(
            db, pid, phases["Build"], "research-fanout", agents, reduce_agent=reduce_agent,
        )

        # Verify graph is running
        graph = GraphEngine.get_graph(db, graph_id)
        assert graph is not None
        assert graph["status"] == "running"

        # Verify leaf nodes are ready (no dependencies)
        all_nodes = GraphEngine.list_nodes(db, graph_id)
        assert len(all_nodes) == 4  # 3 leaves + 1 reduce
        leaves = [n for n in all_nodes if n["node_type"] == "leaf"]
        reduce_nodes = [n for n in all_nodes if n["node_type"] == "reduce"]
        assert len(leaves) == 3
        assert len(reduce_nodes) == 1

        # All leaves should be ready
        ready = GraphEngine.get_ready_nodes(db, graph_id)
        assert len(ready) == 3
        for leaf in ready:
            assert leaf["status"] == "ready"

        # Reduce should NOT be ready (depends on leaves)
        reduce_node = reduce_nodes[0]
        assert reduce_node["status"] == "pending"

        # Mark leaf nodes completed one by one
        for leaf in leaves:
            GraphEngine.mark_node_running(db, leaf["id"])
            GraphEngine.mark_node_completed(db, leaf["id"])

        # After all leaves done, verify reduce node becomes ready
        ready = GraphEngine.get_ready_nodes(db, graph_id)
        assert len(ready) == 1
        assert ready[0]["id"] == reduce_node["id"]

        # Mark reduce completed
        GraphEngine.mark_node_running(db, reduce_node["id"])
        GraphEngine.mark_node_completed(db, reduce_node["id"])

        # Verify graph is complete
        assert GraphEngine.check_graph_complete(db, graph_id) is True
        graph = GraphEngine.get_graph(db, graph_id)
        assert graph["status"] == "completed"

    def test_knowledge_sharing(self, db: psycopg.Connection) -> None:
        """Test knowledge contribution, querying, and conflict detection."""
        pid = _create_project(db)
        phases = _create_all_phases(db, pid)
        PhaseEngine.activate_phase(db, pid, "Spec")

        # Create graph + 2 agent runs
        graph_id = GraphEngine.create_graph(db, pid, phases["Spec"], "knowledge-test")
        node1_id = GraphEngine.add_node(db, graph_id, "agent-1", "leaf", agent_type="researcher")
        node2_id = GraphEngine.add_node(db, graph_id, "agent-2", "leaf", agent_type="researcher")

        run1 = db.execute(
            "INSERT INTO agent_runs (node_id, agent_type, model, status) "
            "VALUES (%s, 'researcher', 'test', 'completed') RETURNING id",
            (node1_id,),
        ).fetchone()
        assert run1 is not None
        run1_id = run1["id"]

        run2 = db.execute(
            "INSERT INTO agent_runs (node_id, agent_type, model, status) "
            "VALUES (%s, 'researcher', 'test', 'completed') RETURNING id",
            (node2_id,),
        ).fetchone()
        assert run2 is not None
        run2_id = run2["id"]

        # Agent 1 contributes knowledge
        k1_id = contribute_knowledge(
            db, pid, key="api_base_url", value="https://api.example.com/v1",
            scope="project", contributed_by=run1_id,
        )

        # Verify queryable
        entry = query_knowledge(db, pid, "api_base_url")
        assert entry is not None
        assert entry["value"] == "https://api.example.com/v1"

        # Agent 2 contributes conflicting knowledge (same key, different value, different contributor)
        k2_id = contribute_knowledge(
            db, pid, key="api_base_url", value="https://api.example.com/v2",
            scope="project", contributed_by=run2_id,
        )

        # The newest entry supersedes the old one (contribute_knowledge auto-supersedes)
        # So there should be no conflict because only the latest is non-superseded.
        # To create a real conflict, we need entries with different scope_ids
        # or we insert them differently. Let's use scope_id to create a real conflict.

        # Clean slate: use node-scoped entries so both remain non-superseded
        k3_id = contribute_knowledge(
            db, pid, key="db_host", value="db1.internal",
            scope="node", scope_id=node1_id, contributed_by=run1_id,
        )
        k4_id = contribute_knowledge(
            db, pid, key="db_host", value="db2.internal",
            scope="node", scope_id=node2_id, contributed_by=run2_id,
        )

        # Both entries exist and are non-superseded (different scope_ids)
        # But detect_conflicts looks at same key + different contributors (regardless of scope_id)
        conflicts = detect_conflicts(db, pid)
        db_host_conflicts = [c for c in conflicts if c["key"] == "db_host"]
        assert len(db_host_conflicts) == 1
        assert db_host_conflicts[0]["contributor_count"] == 2

        # Resolve conflict: pick k3 as winner, k4 as loser
        resolve_conflict(db, k3_id, [k4_id])

        # After resolution, no more conflicts for db_host
        conflicts = detect_conflicts(db, pid)
        db_host_conflicts = [c for c in conflicts if c["key"] == "db_host"]
        assert len(db_host_conflicts) == 0

    def test_guardrail_pipeline(self, db: psycopg.Connection) -> None:
        """Test agent output -> guardrail checks -> acceptance/rejection."""
        pid = _create_project(db)
        phases = _create_all_phases(db, pid)
        PhaseEngine.activate_phase(db, pid, "Build")

        # Create full chain: project -> phase -> graph -> node -> run -> output
        _, _, _, output_id, _ = _setup_output_chain(db, pid, phases["Build"])

        mw = GuardrailMiddleware()

        # Run guardrails on valid content -> should pass
        valid_content = (
            "## Summary\nClean research report.\n"
            "## Findings\nAll good.\n"
            "## Recommendations\nShip it.\n"
        )
        results = mw.check_and_record(db, output_id, valid_content, "research_report")
        assert all(r.passed for r in results)

        # Verify accepted in DB
        out_row = db.execute(
            "SELECT accepted FROM agent_outputs WHERE id = %s", (output_id,)
        ).fetchone()
        assert out_row is not None
        assert out_row["accepted"] is True

        # Verify guardrail_checks records
        checks = db.execute(
            "SELECT * FROM guardrail_checks WHERE output_id = %s", (output_id,)
        ).fetchall()
        assert len(checks) == 2

        # Now test with a second output that has invalid content
        run2 = db.execute(
            "INSERT INTO agent_runs (node_id, agent_type, model, status) "
            "VALUES ((SELECT en.id FROM execution_nodes en "
            "  JOIN execution_graphs eg ON en.graph_id = eg.id "
            "  WHERE eg.project_id = %s LIMIT 1), 'researcher', 'test', 'completed') "
            "RETURNING id",
            (pid,),
        ).fetchone()
        assert run2 is not None

        output2 = db.execute(
            "INSERT INTO agent_outputs (run_id, output_type) VALUES (%s, 'research_report') RETURNING id",
            (run2["id"],),
        ).fetchone()
        assert output2 is not None

        # Content with anti-pattern -> critical fail
        bad_content = (
            "## Summary\n## Findings\n## Recommendations\n"
            "is_active, is_deleted, has_permission, can_edit flags detected."
        )
        results = mw.check_and_record(db, output2["id"], bad_content, "research_report")
        has_fail = any(not r.passed for r in results)
        assert has_fail

        out_row2 = db.execute(
            "SELECT accepted FROM agent_outputs WHERE id = %s", (output2["id"],)
        ).fetchone()
        assert out_row2 is not None
        assert out_row2["accepted"] is False

    def test_run_engine_cycle(self, db: psycopg.Connection) -> None:
        """Test RunEngine.run_once with ready nodes."""
        pid = _create_project(db)
        phases = _create_all_phases(db, pid)
        PhaseEngine.activate_phase(db, pid, "Build")

        # Build a graph with ready nodes
        graph_id = build_fanout_graph(
            db, pid, phases["Build"], "run-engine-test",
            agents=[
                {"name": "worker-1", "agent_type": "researcher", "assignment": {"task": "A"}},
                {"name": "worker-2", "agent_type": "researcher", "assignment": {"task": "B"}},
            ],
        )

        # Create RunEngine
        config = EtcConfig()
        engine = RunEngine(pid, config=config)

        # Mock AgentRunner.deploy to avoid real API calls
        mock_run_id = uuid4()
        with patch.object(engine.agent_runner, "deploy", return_value=mock_run_id) as mock_deploy:
            result = engine.run_once(db)

        # Verify nodes were deployed
        assert result["actions_taken"] >= 2
        assert len(result["deployed"]) == 2
        assert mock_deploy.call_count == 2

        # Verify status returned
        assert "status" in result
        assert "phase" in result["status"]
        assert result["status"]["phase"]["name"] == "Build"

    def test_event_audit_trail(self, db: psycopg.Connection) -> None:
        """Verify events are recorded throughout the lifecycle."""
        pid = _create_project(db)
        phases = _create_all_phases(db, pid)

        # Perform various actions that emit events

        # 1. Activate and advance phase (emits PHASE_GATE_REACHED)
        PhaseEngine.activate_phase(db, pid, "Bootstrap")
        PhaseEngine.add_dod_item(db, phases["Bootstrap"], "Ready", "automatic")
        PhaseEngine.check_dod_item(db, phases["Bootstrap"], 0, "test")
        PhaseEngine.advance_phase(db, pid, reason="Done", approved_by="test")

        # 2. Emit custom events
        emit_event(db, pid, EventType.AGENT_STARTED, actor="test", payload={"node": "n1"})
        emit_event(db, pid, EventType.AGENT_COMPLETED, actor="test", payload={"node": "n1"})

        # 3. Query events table
        events = db.execute(
            "SELECT * FROM events WHERE project_id = %s ORDER BY created_at", (pid,)
        ).fetchall()

        # Should have: PHASE_GATE_REACHED + AGENT_STARTED + AGENT_COMPLETED
        assert len(events) >= 3

        event_types = [e["event_type"] for e in events]
        assert "phase_gate_reached" in event_types
        assert "agent_started" in event_types
        assert "agent_completed" in event_types

        # Verify audit trail completeness — each event has project_id, actor, and timestamp
        for evt in events:
            assert evt["project_id"] == pid
            assert evt["actor"] is not None
            assert evt["created_at"] is not None


# ===========================================================================
# TestResilience
# ===========================================================================


class TestResilience:
    """Test crash recovery and restart behavior (C3)."""

    def test_status_queryable_after_partial_run(self, db: psycopg.Connection) -> None:
        """Verify project status is queryable mid-execution."""
        pid = _create_project(db)
        phases = _create_all_phases(db, pid)
        PhaseEngine.activate_phase(db, pid, "Build")

        # Create a graph with multiple nodes in different states
        graph_id = GraphEngine.create_graph(db, pid, phases["Build"], "partial-graph")
        n1 = GraphEngine.add_node(db, graph_id, "done-node", "leaf", agent_type="researcher")
        n2 = GraphEngine.add_node(db, graph_id, "running-node", "leaf", agent_type="researcher")
        n3 = GraphEngine.add_node(db, graph_id, "ready-node", "leaf", agent_type="researcher")
        GraphEngine.start_graph(db, graph_id)

        # Simulate partial execution
        GraphEngine.mark_node_running(db, n1)
        GraphEngine.mark_node_completed(db, n1)
        GraphEngine.mark_node_running(db, n2)
        # n3 stays ready

        # Query status via RunEngine
        config = EtcConfig()
        engine = RunEngine(pid, config=config)
        status = engine.get_status(db)

        # Verify accurate state reported
        assert status["phase"]["name"] == "Build"
        assert status["phase"]["status"] == "active"
        assert "completed" in status["node_counts"]
        assert status["node_counts"]["completed"] == 1
        assert "running" in status["node_counts"]
        assert status["node_counts"]["running"] == 1
        assert "ready" in status["node_counts"]
        assert status["node_counts"]["ready"] == 1
        assert len(status["active_graphs"]) == 1

    def test_pending_actions_after_restart(self, db: psycopg.Connection) -> None:
        """Simulate restart: ready nodes are still actionable."""
        pid = _create_project(db)
        phases = _create_all_phases(db, pid)
        PhaseEngine.activate_phase(db, pid, "Build")

        # Create a graph with ready nodes
        graph_id = build_fanout_graph(
            db, pid, phases["Build"], "restart-test",
            agents=[
                {"name": "w1", "agent_type": "researcher", "assignment": {"task": "X"}},
                {"name": "w2", "agent_type": "researcher", "assignment": {"task": "Y"}},
            ],
        )

        # Create a NEW RunEngine (simulates a fresh process after restart)
        config = EtcConfig()
        fresh_engine = RunEngine(pid, config=config)

        # Get pending actions — ready nodes should be found
        actions = fresh_engine.get_pending_actions(db)

        deploy_actions = [a for a in actions if a["action"] == "deploy_agent"]
        assert len(deploy_actions) == 2

        # Verify the ready nodes are the ones we created
        node_names = {a["node_name"] for a in deploy_actions}
        assert "w1" in node_names
        assert "w2" in node_names
