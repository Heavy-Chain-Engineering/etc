"""SEM Orchestrator — stateless decision loop that drives the SDLC.

Architectural constraint C2: the SEM is stateless between decisions.
Each decision cycle:
    1. LISTEN for event (Postgres NOTIFY)
    2. Load relevant state from Postgres (scoped query)
    3. Call LLM with SEM prompt + scoped context (via PydanticAI)
    4. Execute decision (deploy agent, check gate, etc.)
    5. Write result to Postgres
    6. Back to 1 (fresh context for next decision)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import UUID

import psycopg
from pydantic import BaseModel
from pydantic_ai import Agent

from etc_platform.config import EtcConfig, load_config
from etc_platform.events import EventBus, EventType, emit_event
from etc_platform.phases import PhaseEngine

logger = logging.getLogger(__name__)


# ===========================================================================
# Decision model — structured output from PydanticAI
# ===========================================================================


class DecisionType(str, Enum):
    DEPLOY_AGENT = "deploy_agent"
    ADVANCE_PHASE = "advance_phase"
    CHECK_DOD = "check_dod"
    WAIT = "wait"
    REQUEST_HUMAN_INPUT = "request_human_input"
    MARK_NODE_READY = "mark_node_ready"
    RETRY_FAILED_NODE = "retry_failed_node"
    DESIGN_TOPOLOGY = "design_topology"


class SEMDecision(BaseModel):
    decision_type: DecisionType
    reasoning: str
    # For DEPLOY_AGENT:
    agent_type: str | None = None
    node_id: str | None = None
    # For ADVANCE_PHASE:
    reason: str | None = None
    # For CHECK_DOD:
    phase_id: str | None = None
    # For REQUEST_HUMAN_INPUT:
    question: str | None = None
    # For RETRY_FAILED_NODE:
    violation_details: str | None = None


# ===========================================================================
# Dependencies for PydanticAI
# ===========================================================================


@dataclass
class SEMDeps:
    conn: psycopg.Connection
    project_id: UUID
    config: EtcConfig


# ===========================================================================
# SEM System Prompt
# ===========================================================================

SEM_SYSTEM_PROMPT = """\
You are the Software Engineering Manager (SEM) orchestrator for the ETC Platform.
You are a stateless decision-maker: each time you are called, you receive the current
project state and must decide the single best next action.

You NEVER write code, do research, or perform any work yourself.
You ONLY make decisions and delegate all work to specialized agents.

Your responsibilities:
1. Assess the current SDLC phase and its Definition of Done (DoD).
2. Determine if the DoD is met and the project should advance to the next phase.
3. Identify ready execution nodes that need agents deployed to work on them.
4. Detect failed nodes that may need to be retried.
5. Recognize when human input is needed and request it.
6. When nothing is actionable, decide to wait.

Decision types you can make:
- DEPLOY_AGENT: Deploy a specialized agent to work on a ready execution node.
  Provide agent_type and node_id.
- ADVANCE_PHASE: Move the project to the next SDLC phase (only when DoD is fully met).
  Provide the reason for advancement.
- CHECK_DOD: Evaluate the Definition of Done for the current phase.
  Provide the phase_id to check.
- WAIT: No action needed right now. The system will wake you on the next event.
- REQUEST_HUMAN_INPUT: Ask the human operator a question when you lack information.
  Provide the question to ask.
- MARK_NODE_READY: Mark an execution node as ready when its dependencies are satisfied.
  Provide the node_id.
- RETRY_FAILED_NODE: Retry a failed execution node, optionally with violation context.
  Provide node_id and optionally violation_details from guardrail failures.
- DESIGN_TOPOLOGY: Design an execution topology for the current phase.
  Used when in Decompose phase with source materials triaged but no execution graph.

Always provide clear reasoning for your decision. Be concise but thorough.
Prioritize: unblocking work > advancing phases > checking DoD > waiting.
"""


# ===========================================================================
# PydanticAI Agent (module-level singleton for override support in tests)
# ===========================================================================

sem_agent: Agent[SEMDeps, SEMDecision] = Agent(
    "anthropic:claude-sonnet-4-20250514",
    deps_type=SEMDeps,
    output_type=SEMDecision,
    system_prompt=SEM_SYSTEM_PROMPT,
    defer_model_check=True,
)


# ===========================================================================
# State loading
# ===========================================================================


def load_scoped_state(
    conn: psycopg.Connection,
    project_id: UUID,
    triggering_event: dict[str, Any],
) -> dict[str, Any]:
    """Load the relevant state for a SEM decision, scoped to the project.

    Returns a dict with:
        - current_phase: dict or None
        - dod_status: dict or None (if there is a current phase)
        - execution_graphs: list of active graphs
        - ready_nodes: list of nodes in 'ready' status
        - recent_events: last 10 events
        - triggering_event: the event that triggered this decision
        - project_info: dict with name and classification
        - material_summary: dict mapping priority -> count
        - unresolved_conflicts: list of knowledge conflict dicts
    """
    # Current phase
    current_phase = PhaseEngine.get_current_phase(conn, project_id)

    # DoD status for current phase
    dod_status = None
    if current_phase is not None:
        dod_status = PhaseEngine.evaluate_dod(conn, current_phase["id"])

    # Execution graphs (active ones for this project)
    graphs = conn.execute(
        "SELECT * FROM execution_graphs WHERE project_id = %s "
        "AND status IN ('pending', 'running') "
        "ORDER BY created_at",
        (project_id,),
    ).fetchall()
    execution_graphs = [dict(g) for g in graphs]

    # Ready nodes — nodes with status 'ready' across all active graphs
    ready_nodes_rows = conn.execute(
        """
        SELECT en.*
        FROM execution_nodes en
        JOIN execution_graphs eg ON en.graph_id = eg.id
        WHERE eg.project_id = %s AND en.status = 'ready'
        ORDER BY en.depth, en.name
        """,
        (project_id,),
    ).fetchall()
    ready_nodes = [dict(n) for n in ready_nodes_rows]

    # Recent events (last 10)
    recent_rows = conn.execute(
        "SELECT * FROM events WHERE project_id = %s "
        "ORDER BY created_at DESC LIMIT 10",
        (project_id,),
    ).fetchall()
    recent_events = [dict(e) for e in recent_rows]

    # Project classification and name
    project_row = conn.execute(
        "SELECT name, classification FROM projects WHERE id = %s",
        (project_id,),
    ).fetchone()
    project_info = dict(project_row) if project_row else {}

    # Source material summary
    material_rows = conn.execute(
        """
        SELECT priority, COUNT(*) as cnt
        FROM source_materials WHERE project_id = %s
        GROUP BY priority
        ORDER BY array_position(ARRAY['primary','high','medium','context_only'], priority)
        """,
        (project_id,),
    ).fetchall()
    material_summary = {r["priority"]: r["cnt"] for r in material_rows}

    # Unresolved knowledge conflicts
    from etc_platform.knowledge import detect_conflicts

    conflicts = detect_conflicts(conn, project_id)

    return {
        "current_phase": current_phase,
        "dod_status": dod_status,
        "execution_graphs": execution_graphs,
        "ready_nodes": ready_nodes,
        "recent_events": recent_events,
        "triggering_event": triggering_event,
        "project_info": project_info,
        "material_summary": material_summary,
        "unresolved_conflicts": conflicts,
    }


# ===========================================================================
# Decision execution
# ===========================================================================


def execute_decision(
    conn: psycopg.Connection,
    project_id: UUID,
    decision: SEMDecision,
) -> None:
    """Execute a SEM decision by updating Postgres state.

    Each decision type maps to specific database operations:
    - DEPLOY_AGENT: Update node to 'running', emit AGENT_STARTED event
    - ADVANCE_PHASE: Call PhaseEngine.advance_phase()
    - CHECK_DOD: Evaluate DoD and emit results as event
    - WAIT: No-op (log only)
    - REQUEST_HUMAN_INPUT: Emit HUMAN_RESPONSE event with the question
    - MARK_NODE_READY: Update node to 'ready', emit NODE_READY event
    """
    logger.info(
        "Executing decision: %s — %s",
        decision.decision_type.value,
        decision.reasoning,
    )

    # Universal audit trail: record every SEM decision as an event
    emit_event(
        conn=conn,
        project_id=project_id,
        event_type=EventType.SEM_DECISION,
        actor="sem",
        payload={
            "decision_type": decision.decision_type.value,
            "reasoning": decision.reasoning,
            "agent_type": decision.agent_type,
            "node_id": decision.node_id,
            "phase_id": decision.phase_id,
            "reason": decision.reason,
            "question": decision.question,
            "violation_details": decision.violation_details,
        },
    )

    if decision.decision_type == DecisionType.DEPLOY_AGENT:
        _execute_deploy_agent(conn, project_id, decision)
    elif decision.decision_type == DecisionType.ADVANCE_PHASE:
        _execute_advance_phase(conn, project_id, decision)
    elif decision.decision_type == DecisionType.CHECK_DOD:
        _execute_check_dod(conn, project_id, decision)
    elif decision.decision_type == DecisionType.WAIT:
        logger.info("SEM decided to WAIT: %s", decision.reasoning)
    elif decision.decision_type == DecisionType.REQUEST_HUMAN_INPUT:
        _execute_request_human_input(conn, project_id, decision)
    elif decision.decision_type == DecisionType.MARK_NODE_READY:
        _execute_mark_node_ready(conn, project_id, decision)
    elif decision.decision_type == DecisionType.RETRY_FAILED_NODE:
        _execute_retry_failed_node(conn, project_id, decision)
    elif decision.decision_type == DecisionType.DESIGN_TOPOLOGY:
        _execute_design_topology(conn, project_id, decision)
    else:
        logger.warning("Unknown decision type: %s", decision.decision_type)


def _execute_deploy_agent(
    conn: psycopg.Connection, project_id: UUID, decision: SEMDecision
) -> None:
    """Update node status to 'running' and emit AGENT_STARTED event.

    Note: Actual agent runtime (spawning Claude API calls) is Task 7.
    For now, we just update the state.
    """
    assert decision.node_id is not None, "DEPLOY_AGENT requires node_id"

    now = datetime.now(timezone.utc)
    conn.execute(
        "UPDATE execution_nodes SET status = 'running', started_at = %s WHERE id = %s",
        (now, decision.node_id),
    )

    emit_event(
        conn=conn,
        project_id=project_id,
        event_type=EventType.AGENT_STARTED,
        actor="sem",
        payload={
            "node_id": decision.node_id,
            "agent_type": decision.agent_type,
            "reasoning": decision.reasoning,
        },
    )


def _execute_advance_phase(
    conn: psycopg.Connection, project_id: UUID, decision: SEMDecision
) -> None:
    """Advance to the next SDLC phase via PhaseEngine."""
    reason = decision.reason or decision.reasoning
    next_phase = PhaseEngine.advance_phase(
        conn=conn,
        project_id=project_id,
        reason=reason,
        approved_by="sem",
    )
    logger.info("Advanced to phase: %s", next_phase)


def _execute_check_dod(
    conn: psycopg.Connection, project_id: UUID, decision: SEMDecision
) -> None:
    """Evaluate DoD and emit results as a PHASE_GATE_REACHED event."""
    assert decision.phase_id is not None, "CHECK_DOD requires phase_id"

    dod_result = PhaseEngine.evaluate_dod(conn, UUID(decision.phase_id))

    emit_event(
        conn=conn,
        project_id=project_id,
        event_type=EventType.PHASE_GATE_REACHED,
        actor="sem",
        payload={
            "phase_id": decision.phase_id,
            "total": dod_result["total"],
            "checked": dod_result["checked"],
            "passed": dod_result["passed"],
        },
    )

    logger.info(
        "DoD check: %d/%d items checked, passed=%s",
        dod_result["checked"],
        dod_result["total"],
        dod_result["passed"],
    )


def _execute_request_human_input(
    conn: psycopg.Connection, project_id: UUID, decision: SEMDecision
) -> None:
    """Emit a HUMAN_RESPONSE event with the question for the operator."""
    emit_event(
        conn=conn,
        project_id=project_id,
        event_type=EventType.HUMAN_RESPONSE,
        actor="sem",
        payload={
            "question": decision.question,
            "reasoning": decision.reasoning,
        },
    )


def _execute_mark_node_ready(
    conn: psycopg.Connection, project_id: UUID, decision: SEMDecision
) -> None:
    """Update node status to 'ready' and emit NODE_READY event."""
    assert decision.node_id is not None, "MARK_NODE_READY requires node_id"

    conn.execute(
        "UPDATE execution_nodes SET status = 'ready' WHERE id = %s",
        (decision.node_id,),
    )

    emit_event(
        conn=conn,
        project_id=project_id,
        event_type=EventType.NODE_READY,
        actor="sem",
        payload={
            "node_id": decision.node_id,
            "reasoning": decision.reasoning,
        },
    )


def _execute_retry_failed_node(
    conn: psycopg.Connection, project_id: UUID, decision: SEMDecision
) -> None:
    """Retry a failed node with violation context."""
    assert decision.node_id is not None, "RETRY_FAILED_NODE requires node_id"

    from etc_platform.agent_runtime import AgentRunner
    from etc_platform.retry import execute_retry

    runner = AgentRunner()
    execute_retry(
        conn=conn,
        node_id=UUID(decision.node_id),
        agent_runner=runner,
        violation_details=decision.violation_details,
    )


def _execute_design_topology(
    conn: psycopg.Connection, project_id: UUID, decision: SEMDecision
) -> None:
    """Design a topology by calling the topology builder and storing the plan."""
    from etc_platform.topology import assess_topology

    plan = assess_topology(conn, project_id)

    # Store the plan as an event for human review
    emit_event(
        conn=conn,
        project_id=project_id,
        event_type=EventType.PHASE_GATE_REACHED,
        actor="sem",
        payload={
            "action": "topology_designed",
            "plan": plan.model_dump(),
            "reasoning": decision.reasoning,
            "awaiting_approval": True,
        },
    )

    logger.info(
        "Topology designed: %d layers, %d estimated agents",
        len(plan.layers),
        plan.estimated_agents,
    )


# ===========================================================================
# SEMOrchestrator
# ===========================================================================


class SEMOrchestrator:
    """Stateless SEM orchestrator — the heart of the ETC platform.

    Each decision cycle loads fresh state from Postgres (C2: stateless between
    decisions), calls PydanticAI for a structured decision, and executes it.
    """

    def __init__(
        self,
        project_id: UUID,
        config: EtcConfig | None = None,
    ) -> None:
        self.project_id = project_id
        self.config = config or load_config()

    def make_decision(
        self,
        conn: psycopg.Connection,
        triggering_event: dict[str, Any],
    ) -> SEMDecision:
        """Load scoped state, call PydanticAI agent, return structured decision.

        This is the core decision function. It:
        1. Loads relevant state from Postgres
        2. Builds a user prompt with the state context
        3. Calls the SEM agent for a structured SEMDecision
        """
        state = load_scoped_state(conn, self.project_id, triggering_event)
        deps = SEMDeps(conn=conn, project_id=self.project_id, config=self.config)

        # Build the user prompt with the current state
        user_prompt = _build_user_prompt(state)

        result = sem_agent.run_sync(user_prompt, deps=deps)
        return result.output

    def handle_event(
        self,
        conn: psycopg.Connection,
        event_payload: dict[str, Any],
    ) -> None:
        """Event handler: load state -> decide -> execute.

        One atomic decision cycle. This is what the event bus calls.
        """
        logger.info(
            "Handling event for project %s: %s",
            self.project_id,
            event_payload.get("event_type", "unknown"),
        )

        decision = self.make_decision(conn, event_payload)

        logger.info(
            "SEM decided: %s — %s",
            decision.decision_type.value,
            decision.reasoning,
        )

        execute_decision(conn, self.project_id, decision)

    def run(self, timeout: float | None = None) -> None:
        """Main event loop: listen for events, handle each one.

        This is the blocking entry point for the SEM. It:
        1. Creates an EventBus connected to Postgres
        2. Registers a handler for ALL event types
        3. Listens for NOTIFY events in a loop
        """
        from etc_platform.db import get_conn, get_dsn

        dsn = get_dsn()
        bus = EventBus(dsn)

        # Register handler for all event types
        for event_type in EventType:
            bus.register_handler(event_type.value, self._on_event)

        logger.info("SEM orchestrator starting for project %s", self.project_id)

        if timeout is not None:
            bus.listen_loop(timeout=timeout)
        else:
            bus.listen_loop()

    def _on_event(self, event_payload: dict[str, Any]) -> None:
        """Internal event callback — wraps handle_event with a DB connection."""
        from etc_platform.db import get_conn

        with get_conn() as conn:
            self.handle_event(conn, event_payload)


# ===========================================================================
# Helpers
# ===========================================================================


def _build_user_prompt(state: dict[str, Any]) -> str:
    """Build a user prompt summarizing the current project state for the SEM."""
    parts: list[str] = []

    parts.append("=== Current Project State ===\n")

    # Project info
    info = state.get("project_info", {})
    if info:
        parts.append(f"Project: {info.get('name', 'Unknown')} ({info.get('classification', 'Unknown')})")

        # Anti-pattern warning for re-engineering projects
        if info.get("classification") == "re-engineering":
            parts.append(
                "\u26a0 RE-ENGINEERING PROJECT: Legacy system patterns are anti-patterns. "
                "Do NOT reproduce them."
            )

    # Source material summary
    mat_summary = state.get("material_summary", {})
    if mat_summary:
        parts.append(f"\nSource Materials: {sum(mat_summary.values())} total")
        for priority, count in mat_summary.items():
            parts.append(f"  - {priority}: {count}")

    # Unresolved conflicts
    conflicts = state.get("unresolved_conflicts", [])
    if conflicts:
        parts.append(f"\n\u26a0 Unresolved Knowledge Conflicts: {len(conflicts)}")
        for c in conflicts[:3]:  # Show top 3
            parts.append(f"  - Key: {c['key']} ({c['contributor_count']} contributors)")

    # Current phase
    phase = state["current_phase"]
    if phase:
        parts.append(f"Current Phase: {phase['name']} (status: {phase['status']})")
    else:
        parts.append("Current Phase: None (no phases found)")

    # DoD status
    dod = state["dod_status"]
    if dod:
        parts.append(
            f"DoD Status: {dod['checked']}/{dod['total']} items checked, "
            f"passed={dod['passed']}"
        )
    else:
        parts.append("DoD Status: N/A")

    # Execution graphs
    graphs = state["execution_graphs"]
    if graphs:
        parts.append(f"\nExecution Graphs ({len(graphs)} active):")
        for g in graphs:
            parts.append(f"  - {g['name']} (status: {g['status']})")
    else:
        parts.append("\nExecution Graphs: None")

    # Ready nodes
    ready = state["ready_nodes"]
    if ready:
        parts.append(f"\nReady Nodes ({len(ready)}):")
        for n in ready:
            parts.append(
                f"  - {n['name']} (type: {n['node_type']}, agent: {n.get('agent_type', 'N/A')})"
            )
    else:
        parts.append("\nReady Nodes: None")

    # Recent events
    events = state["recent_events"]
    if events:
        parts.append(f"\nRecent Events ({len(events)}):")
        for e in events[:5]:  # Show top 5 in prompt
            parts.append(f"  - {e['event_type']} by {e.get('actor', 'unknown')}")
    else:
        parts.append("\nRecent Events: None")

    # Triggering event
    trigger = state["triggering_event"]
    parts.append(f"\nTriggering Event: {trigger.get('event_type', 'unknown')}")

    parts.append("\n=== What should we do next? ===")

    return "\n".join(parts)
