"""Tests for the SEM Orchestrator — stateless decision loop (Task 6)."""

from __future__ import annotations

from uuid import UUID

import psycopg
from pydantic_ai.models.test import TestModel

from etc_platform.config import EtcConfig
from etc_platform.events import EventType, emit_event
from etc_platform.intake import add_source_material
from etc_platform.knowledge import contribute_knowledge
from etc_platform.orchestrator import (
    SEM_SYSTEM_PROMPT,
    DecisionType,
    SEMDecision,
    SEMDeps,
    SEMOrchestrator,
    _build_user_prompt,
    execute_decision,
    load_scoped_state,
    sem_agent,
)
from etc_platform.phases import PhaseEngine

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_project(db: psycopg.Connection) -> UUID:
    """Insert a project and all 8 phases, return the project id."""
    row = db.execute(
        "INSERT INTO projects (name, root_path, classification) "
        "VALUES ('test-project', '/tmp/test', 'greenfield') RETURNING id"
    ).fetchone()
    assert row is not None
    pid = row["id"]
    for phase_name in PhaseEngine.PHASE_ORDER:
        db.execute(
            "INSERT INTO phases (project_id, name, dod_items) VALUES (%s, %s, '[]')",
            (pid, phase_name),
        )
    return pid


def _create_graph_and_nodes(
    db: psycopg.Connection, project_id: UUID, phase_name: str = "Build"
) -> tuple[UUID, UUID, list[UUID]]:
    """Create an execution graph with 2 leaf nodes, return (graph_id, phase_id, [node_ids])."""
    phase = db.execute(
        "SELECT id FROM phases WHERE project_id = %s AND name = %s",
        (project_id, phase_name),
    ).fetchone()
    assert phase is not None
    phase_id = phase["id"]

    graph = db.execute(
        "INSERT INTO execution_graphs (project_id, phase_id, name, status) "
        "VALUES (%s, %s, 'test-graph', 'running') RETURNING id",
        (project_id, phase_id),
    ).fetchone()
    assert graph is not None
    graph_id = graph["id"]

    node_ids = []
    for i in range(2):
        node = db.execute(
            "INSERT INTO execution_nodes (graph_id, node_type, name, agent_type, status, depth) "
            "VALUES (%s, 'leaf', %s, 'researcher', 'pending', 0) RETURNING id",
            (graph_id, f"node-{i}"),
        ).fetchone()
        assert node is not None
        node_ids.append(node["id"])

    return graph_id, phase_id, node_ids


# ===========================================================================
# SEMDecision model tests
# ===========================================================================


class TestSEMDecision:
    def test_decision_types_defined(self) -> None:
        """All expected decision types exist in the enum."""
        expected = {
            "deploy_agent",
            "advance_phase",
            "check_dod",
            "wait",
            "request_human_input",
            "mark_node_ready",
            "retry_failed_node",
            "design_topology",
        }
        actual = {dt.value for dt in DecisionType}
        assert expected == actual

    def test_decision_model_validates(self) -> None:
        """SEMDecision accepts valid data."""
        decision = SEMDecision(
            decision_type=DecisionType.DEPLOY_AGENT,
            reasoning="Node is ready to be deployed",
            agent_type="researcher",
            node_id="some-node-id",
        )
        assert decision.decision_type == DecisionType.DEPLOY_AGENT
        assert decision.reasoning == "Node is ready to be deployed"
        assert decision.agent_type == "researcher"

    def test_decision_model_minimal(self) -> None:
        """SEMDecision works with just the required fields."""
        decision = SEMDecision(
            decision_type=DecisionType.WAIT,
            reasoning="Nothing to do right now",
        )
        assert decision.agent_type is None
        assert decision.node_id is None
        assert decision.reason is None
        assert decision.phase_id is None
        assert decision.question is None

    def test_decision_model_advance_phase(self) -> None:
        decision = SEMDecision(
            decision_type=DecisionType.ADVANCE_PHASE,
            reasoning="DoD is met",
            reason="All items checked",
        )
        assert decision.reason == "All items checked"

    def test_decision_model_request_human_input(self) -> None:
        decision = SEMDecision(
            decision_type=DecisionType.REQUEST_HUMAN_INPUT,
            reasoning="Need clarification",
            question="What framework should we use?",
        )
        assert decision.question == "What framework should we use?"

    def test_decision_type_enum_is_str(self) -> None:
        """DecisionType values are strings (for JSON serialization)."""
        assert isinstance(DecisionType.DEPLOY_AGENT, str)
        assert DecisionType.DEPLOY_AGENT == "deploy_agent"


# ===========================================================================
# SEM System Prompt
# ===========================================================================


class TestSEMSystemPrompt:
    def test_system_prompt_is_nonempty_string(self) -> None:
        assert isinstance(SEM_SYSTEM_PROMPT, str)
        assert len(SEM_SYSTEM_PROMPT) > 100  # Should be substantial

    def test_system_prompt_mentions_key_concepts(self) -> None:
        prompt_lower = SEM_SYSTEM_PROMPT.lower()
        assert "phase" in prompt_lower
        assert "definition of done" in prompt_lower or "dod" in prompt_lower
        assert "deploy" in prompt_lower or "agent" in prompt_lower
        assert "delegate" in prompt_lower or "orchestrat" in prompt_lower


# ===========================================================================
# load_scoped_state
# ===========================================================================


class TestLoadScopedState:
    def test_loads_current_phase(self, db: psycopg.Connection) -> None:
        pid = _create_project(db)
        PhaseEngine.activate_phase(db, pid, "Bootstrap")

        triggering_event = {"event_type": "node_ready", "project_id": str(pid)}
        state = load_scoped_state(db, pid, triggering_event)

        assert state["current_phase"] is not None
        assert state["current_phase"]["name"] == "Bootstrap"
        assert state["current_phase"]["status"] == "active"

    def test_loads_none_phase_when_no_phases_active(self, db: psycopg.Connection) -> None:
        """If no phase is activated yet, current_phase falls back to first pending."""
        pid = _create_project(db)
        triggering_event = {"event_type": "node_ready", "project_id": str(pid)}
        state = load_scoped_state(db, pid, triggering_event)
        # PhaseEngine.get_current_phase returns the first pending phase
        assert state["current_phase"] is not None
        assert state["current_phase"]["name"] == "Bootstrap"

    def test_loads_dod_status(self, db: psycopg.Connection) -> None:
        pid = _create_project(db)
        PhaseEngine.activate_phase(db, pid, "Bootstrap")

        # Add a DoD item to Bootstrap
        phase = db.execute(
            "SELECT id FROM phases WHERE project_id = %s AND name = 'Bootstrap'",
            (pid,),
        ).fetchone()
        assert phase is not None
        PhaseEngine.add_dod_item(db, phase["id"], "Project initialized", "automatic")

        triggering_event = {"event_type": "node_ready", "project_id": str(pid)}
        state = load_scoped_state(db, pid, triggering_event)

        assert state["dod_status"] is not None
        assert state["dod_status"]["total"] == 1
        assert state["dod_status"]["checked"] == 0
        assert state["dod_status"]["passed"] is False

    def test_loads_dod_status_none_when_no_phase(self, db: psycopg.Connection) -> None:
        """When there are no phases at all, dod_status should be None."""
        # Create a project with NO phases
        row = db.execute(
            "INSERT INTO projects (name, root_path, classification) "
            "VALUES ('bare-project', '/tmp/bare', 'greenfield') RETURNING id"
        ).fetchone()
        assert row is not None
        pid = row["id"]

        triggering_event = {"event_type": "node_ready", "project_id": str(pid)}
        state = load_scoped_state(db, pid, triggering_event)
        assert state["current_phase"] is None
        assert state["dod_status"] is None

    def test_loads_ready_nodes(self, db: psycopg.Connection) -> None:
        pid = _create_project(db)
        PhaseEngine.activate_phase(db, pid, "Build")
        graph_id, phase_id, node_ids = _create_graph_and_nodes(db, pid, "Build")

        # Mark one node as 'ready'
        db.execute(
            "UPDATE execution_nodes SET status = 'ready' WHERE id = %s",
            (node_ids[0],),
        )

        triggering_event = {"event_type": "node_ready", "project_id": str(pid)}
        state = load_scoped_state(db, pid, triggering_event)

        assert len(state["ready_nodes"]) == 1
        assert state["ready_nodes"][0]["id"] == node_ids[0]
        assert state["ready_nodes"][0]["status"] == "ready"

    def test_loads_no_ready_nodes_when_none_exist(self, db: psycopg.Connection) -> None:
        pid = _create_project(db)
        triggering_event = {"event_type": "node_ready", "project_id": str(pid)}
        state = load_scoped_state(db, pid, triggering_event)
        assert state["ready_nodes"] == []

    def test_loads_recent_events(self, db: psycopg.Connection) -> None:
        pid = _create_project(db)

        # Emit 12 events — should only get latest 10
        for i in range(12):
            emit_event(db, pid, EventType.AGENT_STARTED, f"actor-{i}", {"i": i})

        triggering_event = {"event_type": "agent_started", "project_id": str(pid)}
        state = load_scoped_state(db, pid, triggering_event)

        assert len(state["recent_events"]) == 10

    def test_triggering_event_included(self, db: psycopg.Connection) -> None:
        pid = _create_project(db)
        triggering_event = {
            "event_type": "agent_completed",
            "project_id": str(pid),
            "actor": "test-agent",
        }
        state = load_scoped_state(db, pid, triggering_event)
        assert state["triggering_event"] == triggering_event

    def test_loads_execution_graphs(self, db: psycopg.Connection) -> None:
        pid = _create_project(db)
        PhaseEngine.activate_phase(db, pid, "Build")
        graph_id, phase_id, node_ids = _create_graph_and_nodes(db, pid, "Build")

        triggering_event = {"event_type": "node_ready", "project_id": str(pid)}
        state = load_scoped_state(db, pid, triggering_event)

        assert len(state["execution_graphs"]) == 1
        assert state["execution_graphs"][0]["id"] == graph_id
        assert state["execution_graphs"][0]["status"] == "running"


# ===========================================================================
# execute_decision
# ===========================================================================


class TestExecuteDecision:
    def test_deploy_agent_updates_node_status(self, db: psycopg.Connection) -> None:
        pid = _create_project(db)
        PhaseEngine.activate_phase(db, pid, "Build")
        graph_id, phase_id, node_ids = _create_graph_and_nodes(db, pid, "Build")

        # Mark node as ready first
        db.execute(
            "UPDATE execution_nodes SET status = 'ready' WHERE id = %s",
            (node_ids[0],),
        )

        decision = SEMDecision(
            decision_type=DecisionType.DEPLOY_AGENT,
            reasoning="Node is ready",
            agent_type="researcher",
            node_id=str(node_ids[0]),
        )
        execute_decision(db, pid, decision)

        node = db.execute(
            "SELECT status, started_at FROM execution_nodes WHERE id = %s",
            (node_ids[0],),
        ).fetchone()
        assert node is not None
        assert node["status"] == "running"
        assert node["started_at"] is not None

    def test_deploy_agent_emits_event(self, db: psycopg.Connection) -> None:
        pid = _create_project(db)
        PhaseEngine.activate_phase(db, pid, "Build")
        graph_id, phase_id, node_ids = _create_graph_and_nodes(db, pid, "Build")

        db.execute(
            "UPDATE execution_nodes SET status = 'ready' WHERE id = %s",
            (node_ids[0],),
        )

        decision = SEMDecision(
            decision_type=DecisionType.DEPLOY_AGENT,
            reasoning="Deploy it",
            agent_type="researcher",
            node_id=str(node_ids[0]),
        )
        execute_decision(db, pid, decision)

        event = db.execute(
            "SELECT * FROM events WHERE project_id = %s AND event_type = 'agent_started' "
            "ORDER BY created_at DESC LIMIT 1",
            (pid,),
        ).fetchone()
        assert event is not None
        assert event["actor"] == "sem"
        assert event["payload"]["node_id"] == str(node_ids[0])

    def test_advance_phase_calls_phase_engine(self, db: psycopg.Connection) -> None:
        pid = _create_project(db)
        PhaseEngine.activate_phase(db, pid, "Bootstrap")

        # Add and check a DoD item so advance is allowed
        phase = db.execute(
            "SELECT id FROM phases WHERE project_id = %s AND name = 'Bootstrap'",
            (pid,),
        ).fetchone()
        assert phase is not None
        PhaseEngine.add_dod_item(db, phase["id"], "Project init", "automatic")
        PhaseEngine.check_dod_item(db, phase["id"], 0, "test")

        decision = SEMDecision(
            decision_type=DecisionType.ADVANCE_PHASE,
            reasoning="DoD is met",
            reason="All items checked",
        )
        execute_decision(db, pid, decision)

        current = PhaseEngine.get_current_phase(db, pid)
        assert current is not None
        assert current["name"] == "Spec"
        assert current["status"] == "active"

    def test_check_dod_returns_status(self, db: psycopg.Connection) -> None:
        pid = _create_project(db)
        PhaseEngine.activate_phase(db, pid, "Bootstrap")

        phase = db.execute(
            "SELECT id FROM phases WHERE project_id = %s AND name = 'Bootstrap'",
            (pid,),
        ).fetchone()
        assert phase is not None
        PhaseEngine.add_dod_item(db, phase["id"], "Item 1", "automatic")
        PhaseEngine.add_dod_item(db, phase["id"], "Item 2", "automatic")
        PhaseEngine.check_dod_item(db, phase["id"], 0, "test")

        decision = SEMDecision(
            decision_type=DecisionType.CHECK_DOD,
            reasoning="Check progress",
            phase_id=str(phase["id"]),
        )
        execute_decision(db, pid, decision)

        # Should emit a PHASE_GATE_REACHED event with DoD results
        event = db.execute(
            "SELECT * FROM events WHERE project_id = %s AND event_type = 'phase_gate_reached' "
            "ORDER BY created_at DESC LIMIT 1",
            (pid,),
        ).fetchone()
        assert event is not None
        assert event["payload"]["total"] == 2
        assert event["payload"]["checked"] == 1
        assert event["payload"]["passed"] is False

    def test_wait_emits_only_audit_event(self, db: psycopg.Connection) -> None:
        """WAIT emits a sem_decision audit event but no type-specific event."""
        pid = _create_project(db)

        # Count events before
        before = db.execute(
            "SELECT count(*) as cnt FROM events WHERE project_id = %s", (pid,)
        ).fetchone()
        assert before is not None

        decision = SEMDecision(
            decision_type=DecisionType.WAIT,
            reasoning="Nothing to do",
        )
        execute_decision(db, pid, decision)

        # Only the universal sem_decision audit event should be emitted
        after = db.execute(
            "SELECT count(*) as cnt FROM events WHERE project_id = %s", (pid,)
        ).fetchone()
        assert after is not None
        assert after["cnt"] == before["cnt"] + 1

        # And it should be a sem_decision event
        event = db.execute(
            "SELECT * FROM events WHERE project_id = %s AND event_type = 'sem_decision' "
            "ORDER BY created_at DESC LIMIT 1",
            (pid,),
        ).fetchone()
        assert event is not None
        assert event["payload"]["decision_type"] == "wait"

    def test_request_human_input_emits_event(self, db: psycopg.Connection) -> None:
        pid = _create_project(db)

        decision = SEMDecision(
            decision_type=DecisionType.REQUEST_HUMAN_INPUT,
            reasoning="Need clarification on requirements",
            question="What database should we use?",
        )
        execute_decision(db, pid, decision)

        event = db.execute(
            "SELECT * FROM events WHERE project_id = %s AND event_type = 'human_response' "
            "ORDER BY created_at DESC LIMIT 1",
            (pid,),
        ).fetchone()
        assert event is not None
        assert event["payload"]["question"] == "What database should we use?"
        assert event["actor"] == "sem"

    def test_mark_node_ready_updates_status(self, db: psycopg.Connection) -> None:
        pid = _create_project(db)
        PhaseEngine.activate_phase(db, pid, "Build")
        graph_id, phase_id, node_ids = _create_graph_and_nodes(db, pid, "Build")

        decision = SEMDecision(
            decision_type=DecisionType.MARK_NODE_READY,
            reasoning="Dependencies met",
            node_id=str(node_ids[0]),
        )
        execute_decision(db, pid, decision)

        node = db.execute(
            "SELECT status FROM execution_nodes WHERE id = %s", (node_ids[0],)
        ).fetchone()
        assert node is not None
        assert node["status"] == "ready"

    def test_mark_node_ready_emits_event(self, db: psycopg.Connection) -> None:
        pid = _create_project(db)
        PhaseEngine.activate_phase(db, pid, "Build")
        graph_id, phase_id, node_ids = _create_graph_and_nodes(db, pid, "Build")

        decision = SEMDecision(
            decision_type=DecisionType.MARK_NODE_READY,
            reasoning="Dependencies met",
            node_id=str(node_ids[0]),
        )
        execute_decision(db, pid, decision)

        event = db.execute(
            "SELECT * FROM events WHERE project_id = %s AND event_type = 'node_ready' "
            "ORDER BY created_at DESC LIMIT 1",
            (pid,),
        ).fetchone()
        assert event is not None
        assert event["payload"]["node_id"] == str(node_ids[0])

    def test_design_topology_decision_type_exists(self) -> None:
        """DESIGN_TOPOLOGY is a valid DecisionType enum member."""
        assert DecisionType.DESIGN_TOPOLOGY == "design_topology"
        assert DecisionType.DESIGN_TOPOLOGY.value == "design_topology"

    def test_execute_design_topology_stores_plan(self, db: psycopg.Connection) -> None:
        """DESIGN_TOPOLOGY calls assess_topology and stores the plan as an event."""
        pid = _create_project(db)
        PhaseEngine.activate_phase(db, pid, "Decompose")

        # Add source materials so assess_topology uses the LLM path
        add_source_material(db, pid, "CX Workflows", "spreadsheet", "domain_truth", "primary")

        decision = SEMDecision(
            decision_type=DecisionType.DESIGN_TOPOLOGY,
            reasoning="Source materials triaged, ready to design topology",
        )

        test_model = TestModel(
            custom_output_args={
                "layers": [
                    {
                        "name": "domain-research",
                        "dimension": "bounded_context",
                        "nodes": [
                            {"name": "R01", "agent_type": "researcher", "assignment": {"scope": "cx"}},
                        ],
                    },
                ],
                "reduce_strategy": "single_synthesis",
                "estimated_agents": 2,
                "reasoning": "One researcher plus synthesis",
            }
        )

        from unittest.mock import patch as mock_patch

        from etc_platform.topology import assess_topology as real_assess

        # Patch assess_topology at the topology module level so the local import picks it up
        def patched_assess(conn, project_id, **kwargs):
            return real_assess(conn, project_id, model_override=test_model)

        with mock_patch("etc_platform.topology.assess_topology", side_effect=patched_assess):
            execute_decision(db, pid, decision)

        # Verify a phase_gate_reached event was emitted with the plan
        event = db.execute(
            "SELECT * FROM events WHERE project_id = %s AND event_type = 'phase_gate_reached' "
            "ORDER BY created_at DESC LIMIT 1",
            (pid,),
        ).fetchone()
        assert event is not None
        payload = event["payload"]
        assert payload["action"] == "topology_designed"
        assert "plan" in payload
        assert payload["plan"]["estimated_agents"] == 2
        assert len(payload["plan"]["layers"]) == 1

    def test_execute_design_topology_emits_event(self, db: psycopg.Connection) -> None:
        """DESIGN_TOPOLOGY event payload has plan and awaiting_approval."""
        pid = _create_project(db)
        PhaseEngine.activate_phase(db, pid, "Decompose")

        # No materials: assess_topology returns minimal plan without LLM
        decision = SEMDecision(
            decision_type=DecisionType.DESIGN_TOPOLOGY,
            reasoning="Design the topology now",
        )

        execute_decision(db, pid, decision)

        event = db.execute(
            "SELECT * FROM events WHERE project_id = %s AND event_type = 'phase_gate_reached' "
            "ORDER BY created_at DESC LIMIT 1",
            (pid,),
        ).fetchone()
        assert event is not None
        payload = event["payload"]
        assert payload["action"] == "topology_designed"
        assert payload["awaiting_approval"] is True
        assert payload["reasoning"] == "Design the topology now"
        assert "plan" in payload
        # No materials = minimal plan
        assert payload["plan"]["estimated_agents"] == 1


# ===========================================================================
# SEMOrchestrator
# ===========================================================================


class TestSEMOrchestrator:
    def test_init_with_defaults(self) -> None:
        """Orchestrator initializes with default config."""
        from uuid import uuid4

        pid = uuid4()
        orch = SEMOrchestrator(project_id=pid)
        assert orch.project_id == pid
        assert orch.config is not None

    def test_init_with_custom_config(self) -> None:
        from uuid import uuid4

        config = EtcConfig(max_concurrent_agents=5)
        pid = uuid4()
        orch = SEMOrchestrator(project_id=pid, config=config)
        assert orch.config.max_concurrent_agents == 5

    def test_make_decision_with_mock_agent(self, db: psycopg.Connection) -> None:
        """make_decision loads state and returns a structured SEMDecision via PydanticAI."""
        pid = _create_project(db)
        PhaseEngine.activate_phase(db, pid, "Bootstrap")

        config = EtcConfig()
        orch = SEMOrchestrator(project_id=pid, config=config)

        triggering_event = {"event_type": "node_ready", "project_id": str(pid)}

        # Use TestModel to avoid real API calls
        test_model = TestModel(
            custom_output_args={
                "decision_type": "wait",
                "reasoning": "Nothing to do yet",
            }
        )

        with sem_agent.override(model=test_model):
            decision = orch.make_decision(db, triggering_event)

        assert isinstance(decision, SEMDecision)
        assert decision.decision_type == DecisionType.WAIT
        assert decision.reasoning == "Nothing to do yet"

    def test_make_decision_deploy_agent(self, db: psycopg.Connection) -> None:
        """make_decision can return a DEPLOY_AGENT decision."""
        pid = _create_project(db)
        PhaseEngine.activate_phase(db, pid, "Build")
        graph_id, phase_id, node_ids = _create_graph_and_nodes(db, pid, "Build")

        # Mark a node as ready
        db.execute(
            "UPDATE execution_nodes SET status = 'ready' WHERE id = %s",
            (node_ids[0],),
        )

        config = EtcConfig()
        orch = SEMOrchestrator(project_id=pid, config=config)

        triggering_event = {"event_type": "node_ready", "project_id": str(pid)}

        test_model = TestModel(
            custom_output_args={
                "decision_type": "deploy_agent",
                "reasoning": "Ready node found",
                "agent_type": "researcher",
                "node_id": str(node_ids[0]),
            }
        )

        with sem_agent.override(model=test_model):
            decision = orch.make_decision(db, triggering_event)

        assert decision.decision_type == DecisionType.DEPLOY_AGENT
        assert decision.node_id == str(node_ids[0])

    def test_handle_event_full_cycle(self, db: psycopg.Connection) -> None:
        """handle_event does a full cycle: load state -> decide -> execute."""
        pid = _create_project(db)
        PhaseEngine.activate_phase(db, pid, "Build")
        graph_id, phase_id, node_ids = _create_graph_and_nodes(db, pid, "Build")

        db.execute(
            "UPDATE execution_nodes SET status = 'ready' WHERE id = %s",
            (node_ids[0],),
        )

        config = EtcConfig()
        orch = SEMOrchestrator(project_id=pid, config=config)

        event_payload = {"event_type": "node_ready", "project_id": str(pid)}

        test_model = TestModel(
            custom_output_args={
                "decision_type": "deploy_agent",
                "reasoning": "Deploy the ready node",
                "agent_type": "researcher",
                "node_id": str(node_ids[0]),
            }
        )

        # Mock get_conn to return our test db connection
        with sem_agent.override(model=test_model):
            orch.handle_event(db, event_payload)

        # Verify the node was updated to 'running'
        node = db.execute(
            "SELECT status FROM execution_nodes WHERE id = %s", (node_ids[0],)
        ).fetchone()
        assert node is not None
        assert node["status"] == "running"

        # Verify an agent_started event was emitted
        event = db.execute(
            "SELECT * FROM events WHERE project_id = %s AND event_type = 'agent_started' "
            "ORDER BY created_at DESC LIMIT 1",
            (pid,),
        ).fetchone()
        assert event is not None

    def test_handle_event_wait_is_safe(self, db: psycopg.Connection) -> None:
        """handle_event with a WAIT decision does not crash."""
        pid = _create_project(db)
        PhaseEngine.activate_phase(db, pid, "Bootstrap")

        config = EtcConfig()
        orch = SEMOrchestrator(project_id=pid, config=config)

        event_payload = {"event_type": "agent_completed", "project_id": str(pid)}

        test_model = TestModel(
            custom_output_args={
                "decision_type": "wait",
                "reasoning": "Nothing actionable",
            }
        )

        with sem_agent.override(model=test_model):
            # Should not raise
            orch.handle_event(db, event_payload)

    def test_sem_agent_uses_structured_output(self) -> None:
        """The sem_agent is configured with SEMDecision as output_type."""
        assert sem_agent._output_type == SEMDecision  # noqa: SLF001

    def test_sem_agent_uses_deps_type(self) -> None:
        """The sem_agent is configured with SEMDeps."""
        assert sem_agent._deps_type == SEMDeps  # noqa: SLF001


# ===========================================================================
# SEMDeps
# ===========================================================================


class TestSEMDeps:
    def test_deps_dataclass(self, db: psycopg.Connection) -> None:
        from uuid import uuid4

        pid = uuid4()
        config = EtcConfig()
        deps = SEMDeps(conn=db, project_id=pid, config=config)
        assert deps.conn is db
        assert deps.project_id == pid
        assert deps.config is config


# ===========================================================================
# Dynamic SEM Prompt Construction (Task 8)
# ===========================================================================


def _create_two_agent_runs(db: psycopg.Connection, project_id: UUID) -> tuple[UUID, UUID]:
    """Helper: create the required FK chain and return two distinct agent_run ids."""
    phase = db.execute(
        "SELECT id FROM phases WHERE project_id = %s AND name = 'Build'",
        (project_id,),
    ).fetchone()
    assert phase is not None

    graph = db.execute(
        "INSERT INTO execution_graphs (project_id, phase_id, name, status) "
        "VALUES (%s, %s, 'conflict-graph', 'running') RETURNING id",
        (project_id, phase["id"]),
    ).fetchone()
    assert graph is not None

    node = db.execute(
        "INSERT INTO execution_nodes (graph_id, node_type, name, status) "
        "VALUES (%s, 'leaf', 'conflict-node', 'running') RETURNING id",
        (graph["id"],),
    ).fetchone()
    assert node is not None

    run1 = db.execute(
        "INSERT INTO agent_runs (node_id, agent_type, model, status) "
        "VALUES (%s, 'researcher', 'test', 'completed') RETURNING id",
        (node["id"],),
    ).fetchone()
    assert run1 is not None

    run2 = db.execute(
        "INSERT INTO agent_runs (node_id, agent_type, model, status) "
        "VALUES (%s, 'researcher', 'test', 'completed') RETURNING id",
        (node["id"],),
    ).fetchone()
    assert run2 is not None

    return run1["id"], run2["id"]


class TestLoadScopedStateProjectContext:
    """Tests for project context fields added in Task 8."""

    def test_load_scoped_state_includes_project_info(self, db: psycopg.Connection) -> None:
        """State dict includes project_info with name and classification."""
        pid = _create_project(db)
        triggering_event = {"event_type": "test", "project_id": str(pid)}

        state = load_scoped_state(db, pid, triggering_event)

        assert "project_info" in state
        assert state["project_info"]["name"] == "test-project"
        assert state["project_info"]["classification"] == "greenfield"

    def test_load_scoped_state_includes_material_summary(self, db: psycopg.Connection) -> None:
        """State dict includes material_summary with priority counts."""
        pid = _create_project(db)

        # Add source materials with different priorities
        add_source_material(
            db, pid, "spec.pdf", "pdf", "requirements", "primary",
        )
        add_source_material(
            db, pid, "api-export.code", "code", "implementation_artifact", "high",
        )
        add_source_material(
            db, pid, "notes.document", "document", "domain_truth", "high",
        )

        triggering_event = {"event_type": "test", "project_id": str(pid)}
        state = load_scoped_state(db, pid, triggering_event)

        assert "material_summary" in state
        assert state["material_summary"]["primary"] == 1
        assert state["material_summary"]["high"] == 2

    def test_load_scoped_state_includes_conflicts(self, db: psycopg.Connection) -> None:
        """State dict includes unresolved_conflicts from knowledge entries."""
        pid = _create_project(db)
        run1_id, run2_id = _create_two_agent_runs(db, pid)

        # Create knowledge conflict: same key, different contributors, different scope_ids
        contribute_knowledge(
            db, pid, "entity:VendorType", {"fields": ["a"]},
            scope="node", scope_id=run1_id, contributed_by=run1_id,
        )
        contribute_knowledge(
            db, pid, "entity:VendorType", {"fields": ["b"]},
            scope="node", scope_id=run2_id, contributed_by=run2_id,
        )

        triggering_event = {"event_type": "test", "project_id": str(pid)}
        state = load_scoped_state(db, pid, triggering_event)

        assert "unresolved_conflicts" in state
        assert len(state["unresolved_conflicts"]) == 1
        assert state["unresolved_conflicts"][0]["key"] == "entity:VendorType"
        assert state["unresolved_conflicts"][0]["contributor_count"] == 2


class TestBuildUserPromptProjectContext:
    """Tests for project context in _build_user_prompt (Task 8)."""

    def _base_state(self, **overrides: object) -> dict:
        """Build a minimal state dict for _build_user_prompt."""
        state: dict = {
            "current_phase": {"name": "Spec", "status": "active"},
            "dod_status": {"total": 3, "checked": 1, "passed": False},
            "execution_graphs": [],
            "ready_nodes": [],
            "recent_events": [],
            "triggering_event": {"event_type": "test"},
            "project_info": {},
            "material_summary": {},
            "unresolved_conflicts": [],
        }
        state.update(overrides)
        return state

    def test_build_user_prompt_includes_project_context(self) -> None:
        """Prompt contains the project name and classification."""
        state = self._base_state(
            project_info={"name": "Acme Corp", "classification": "greenfield"},
        )
        prompt = _build_user_prompt(state)

        assert "Acme Corp" in prompt
        assert "greenfield" in prompt

    def test_build_user_prompt_reengineering_warning(self) -> None:
        """Re-engineering projects get an anti-pattern warning in the prompt."""
        state = self._base_state(
            project_info={"name": "LegacyApp", "classification": "re-engineering"},
        )
        prompt = _build_user_prompt(state)

        assert "RE-ENGINEERING PROJECT" in prompt
        assert "anti-pattern" in prompt.lower()

    def test_build_user_prompt_no_reengineering_warning_for_greenfield(self) -> None:
        """Greenfield projects do NOT get the re-engineering anti-pattern warning."""
        state = self._base_state(
            project_info={"name": "NewApp", "classification": "greenfield"},
        )
        prompt = _build_user_prompt(state)

        assert "RE-ENGINEERING PROJECT" not in prompt

    def test_build_user_prompt_shows_material_summary(self) -> None:
        """Prompt shows source material counts by priority."""
        state = self._base_state(
            material_summary={"primary": 1, "high": 2, "medium": 3},
        )
        prompt = _build_user_prompt(state)

        assert "Source Materials: 6 total" in prompt
        assert "primary: 1" in prompt
        assert "high: 2" in prompt
        assert "medium: 3" in prompt

    def test_build_user_prompt_shows_conflicts(self) -> None:
        """Prompt shows unresolved knowledge conflicts."""
        state = self._base_state(
            unresolved_conflicts=[
                {"key": "entity:VendorType", "contributor_count": 2},
                {"key": "entity:Order", "contributor_count": 3},
            ],
        )
        prompt = _build_user_prompt(state)

        assert "Unresolved Knowledge Conflicts: 2" in prompt
        assert "entity:VendorType" in prompt
        assert "2 contributors" in prompt
        assert "entity:Order" in prompt

    def test_build_user_prompt_no_conflicts_section_when_empty(self) -> None:
        """When there are no conflicts, the conflicts section is omitted."""
        state = self._base_state(unresolved_conflicts=[])
        prompt = _build_user_prompt(state)

        assert "Unresolved Knowledge Conflicts" not in prompt


# ===========================================================================
# Decision Audit Trail (Task 13)
# ===========================================================================


class TestDecisionAuditTrail:
    """Tests for universal SEM decision recording."""

    def test_execute_decision_records_sem_decision_event(self, db: psycopg.Connection) -> None:
        """Every execute_decision call should emit a sem_decision event."""
        pid = _create_project(db)

        decision = SEMDecision(
            decision_type=DecisionType.WAIT,
            reasoning="Nothing to do right now",
        )
        execute_decision(db, pid, decision)

        events = db.execute(
            "SELECT * FROM events WHERE project_id = %s AND event_type = 'sem_decision'",
            (pid,),
        ).fetchall()
        assert len(events) == 1
        assert events[0]["payload"]["decision_type"] == "wait"
        assert events[0]["payload"]["reasoning"] == "Nothing to do right now"

    def test_deploy_agent_records_both_audit_and_type_event(self, db: psycopg.Connection) -> None:
        """DEPLOY_AGENT should emit both sem_decision and agent_started events."""
        pid = _create_project(db)
        PhaseEngine.activate_phase(db, pid, "Build")
        graph_id, phase_id, node_ids = _create_graph_and_nodes(db, pid, "Build")

        db.execute(
            "UPDATE execution_nodes SET status = 'ready' WHERE id = %s",
            (node_ids[0],),
        )

        decision = SEMDecision(
            decision_type=DecisionType.DEPLOY_AGENT,
            reasoning="Node is ready",
            agent_type="researcher",
            node_id=str(node_ids[0]),
        )
        execute_decision(db, pid, decision)

        # Check sem_decision event
        audit_events = db.execute(
            "SELECT * FROM events WHERE project_id = %s AND event_type = 'sem_decision'",
            (pid,),
        ).fetchall()
        assert len(audit_events) == 1
        assert audit_events[0]["payload"]["decision_type"] == "deploy_agent"
        assert audit_events[0]["payload"]["agent_type"] == "researcher"
        assert audit_events[0]["payload"]["node_id"] == str(node_ids[0])

        # Check agent_started event still emitted too
        agent_events = db.execute(
            "SELECT * FROM events WHERE project_id = %s AND event_type = 'agent_started'",
            (pid,),
        ).fetchall()
        assert len(agent_events) == 1

    def test_audit_event_captures_all_fields(self, db: psycopg.Connection) -> None:
        """The audit event payload captures all SEMDecision fields."""
        pid = _create_project(db)

        decision = SEMDecision(
            decision_type=DecisionType.REQUEST_HUMAN_INPUT,
            reasoning="Need clarification",
            question="What database?",
        )
        execute_decision(db, pid, decision)

        event = db.execute(
            "SELECT * FROM events WHERE project_id = %s AND event_type = 'sem_decision'",
            (pid,),
        ).fetchone()
        assert event is not None
        payload = event["payload"]
        assert payload["decision_type"] == "request_human_input"
        assert payload["reasoning"] == "Need clarification"
        assert payload["question"] == "What database?"
        assert payload["agent_type"] is None
        assert payload["node_id"] is None
        assert payload["phase_id"] is None

    def test_audit_event_actor_is_sem(self, db: psycopg.Connection) -> None:
        """The audit event actor should always be 'sem'."""
        pid = _create_project(db)

        decision = SEMDecision(
            decision_type=DecisionType.WAIT,
            reasoning="Idle",
        )
        execute_decision(db, pid, decision)

        event = db.execute(
            "SELECT * FROM events WHERE project_id = %s AND event_type = 'sem_decision'",
            (pid,),
        ).fetchone()
        assert event is not None
        assert event["actor"] == "sem"

    def test_multiple_decisions_create_multiple_audit_events(self, db: psycopg.Connection) -> None:
        """Each execute_decision call creates a separate audit event."""
        pid = _create_project(db)

        for i in range(3):
            decision = SEMDecision(
                decision_type=DecisionType.WAIT,
                reasoning=f"Wait cycle {i}",
            )
            execute_decision(db, pid, decision)

        events = db.execute(
            "SELECT * FROM events WHERE project_id = %s AND event_type = 'sem_decision' "
            "ORDER BY created_at",
            (pid,),
        ).fetchall()
        assert len(events) == 3
        assert events[0]["payload"]["reasoning"] == "Wait cycle 0"
        assert events[1]["payload"]["reasoning"] == "Wait cycle 1"
        assert events[2]["payload"]["reasoning"] == "Wait cycle 2"
