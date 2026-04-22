"""Run Engine — ties together SEM orchestrator, graph engine, agent runtime, and phase engine.

This is the "mechanical" run loop that does not require an LLM call itself.
It finds ready nodes, deploys agents, checks for graph completions, and
evaluates DoD status. The SEM LLM decision loop is a layer above this.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from etc_platform.agent_runtime import AgentRunner
from etc_platform.config import EtcConfig, load_config
from etc_platform.events import EventType, emit_event
from etc_platform.graph_engine import GraphEngine
from etc_platform.phases import PhaseEngine

if TYPE_CHECKING:
    from uuid import UUID

    import psycopg

logger = logging.getLogger(__name__)


class RunEngine:
    """Orchestrates one mechanical run cycle: deploy agents, check completions, evaluate DoD."""

    def __init__(self, project_id: UUID, config: EtcConfig | None = None) -> None:
        self.project_id = project_id
        self.config = config or load_config()
        self.agent_runner = AgentRunner(config=self.config)

    # ------------------------------------------------------------------
    # Core cycle
    # ------------------------------------------------------------------

    def run_once(self, conn: psycopg.Connection) -> dict[str, Any]:
        """Execute one decision cycle without the SEM LLM call.

        This is the "mechanical" run that does not need an LLM:
        1. Check for ready nodes -> deploy agents
        2. Check for completed graphs -> mark graphs complete
        3. Evaluate DoD -> report status

        Returns a summary dict of what happened.
        """
        deployed = self.deploy_ready_nodes(conn)
        completed_graphs = self.check_graph_completions(conn)
        status = self.get_status(conn)

        actions_taken = len(deployed) + len(completed_graphs)

        return {
            "actions_taken": actions_taken,
            "deployed": deployed,
            "completed_graphs": completed_graphs,
            "status": status,
        }

    # ------------------------------------------------------------------
    # Pending actions
    # ------------------------------------------------------------------

    def get_pending_actions(self, conn: psycopg.Connection) -> list[dict[str, Any]]:
        """Query Postgres for actionable items.

        Returns list of action dicts describing:
        - Ready nodes that need agents deployed
        - Graphs with all nodes completed (need to be marked complete)
        - Phase DoD that might be met
        """
        actions: list[dict[str, Any]] = []

        # 1. Ready nodes across all active graphs for this project
        ready_nodes = conn.execute(
            """
            SELECT en.id AS node_id, en.name, en.agent_type, en.assignment,
                   eg.id AS graph_id, eg.name AS graph_name
            FROM execution_nodes en
            JOIN execution_graphs eg ON en.graph_id = eg.id
            WHERE eg.project_id = %s
              AND eg.status = 'running'
              AND en.status = 'ready'
              AND en.node_type != 'composite'
            ORDER BY en.depth, en.name
            """,
            (self.project_id,),
        ).fetchall()

        for node in ready_nodes:
            actions.append({
                "action": "deploy_agent",
                "node_id": node["node_id"],
                "node_name": node["name"],
                "agent_type": node["agent_type"],
                "graph_id": node["graph_id"],
                "graph_name": node["graph_name"],
            })

        # 2. Graphs that might be complete (all nodes completed)
        running_graphs = conn.execute(
            """
            SELECT eg.id AS graph_id, eg.name,
                   COUNT(*) AS total,
                   COUNT(*) FILTER (WHERE en.status = 'completed') AS done
            FROM execution_graphs eg
            JOIN execution_nodes en ON en.graph_id = eg.id
            WHERE eg.project_id = %s AND eg.status = 'running'
            GROUP BY eg.id, eg.name
            HAVING COUNT(*) = COUNT(*) FILTER (WHERE en.status = 'completed')
            """,
            (self.project_id,),
        ).fetchall()

        for graph in running_graphs:
            actions.append({
                "action": "complete_graph",
                "graph_id": graph["graph_id"],
                "graph_name": graph["name"],
            })

        # 3. Check if phase DoD might be met
        current_phase = PhaseEngine.get_current_phase(conn, self.project_id)
        if current_phase is not None:
            dod_result = PhaseEngine.evaluate_dod(conn, current_phase["id"])
            if dod_result["passed"]:
                actions.append({
                    "action": "phase_gate_reached",
                    "phase_id": current_phase["id"],
                    "phase_name": current_phase["name"],
                    "dod": dod_result,
                })

        return actions

    # ------------------------------------------------------------------
    # Deploy ready nodes
    # ------------------------------------------------------------------

    def deploy_ready_nodes(self, conn: psycopg.Connection) -> list[UUID]:
        """Find all ready nodes across active graphs and deploy agents.

        Returns list of run_ids created.
        NOTE: For tests, use model_override or mock AgentRunner.deploy
              to avoid real API calls.
        """
        ready_nodes = conn.execute(
            """
            SELECT en.id AS node_id, en.agent_type, en.assignment,
                   eg.id AS graph_id
            FROM execution_nodes en
            JOIN execution_graphs eg ON en.graph_id = eg.id
            WHERE eg.project_id = %s
              AND eg.status = 'running'
              AND en.status = 'ready'
              AND en.node_type != 'composite'
            ORDER BY en.depth, en.name
            """,
            (self.project_id,),
        ).fetchall()

        run_ids: list[UUID] = []
        for node in ready_nodes:
            assignment = node["assignment"] if node["assignment"] else {}
            agent_type = node["agent_type"] or "researcher"

            # Mark node as running before deploying
            GraphEngine.mark_node_running(conn, node["node_id"])

            try:
                run_id = self.agent_runner.deploy(
                    conn=conn,
                    node_id=node["node_id"],
                    agent_type=agent_type,
                    assignment=assignment,
                )
                run_ids.append(run_id)
                logger.info(
                    "Deployed agent %s for node %s (run_id=%s)",
                    agent_type,
                    node["node_id"],
                    run_id,
                )
            except Exception as exc:
                logger.error(
                    "Failed to deploy agent for node %s: %s",
                    node["node_id"],
                    exc,
                )
                GraphEngine.mark_node_failed(conn, node["node_id"])

        return run_ids

    # ------------------------------------------------------------------
    # Check graph completions
    # ------------------------------------------------------------------

    def check_graph_completions(self, conn: psycopg.Connection) -> list[UUID]:
        """Check all running graphs for completion.

        Returns list of graph_ids that were completed.
        """
        running_graphs = conn.execute(
            "SELECT id FROM execution_graphs WHERE project_id = %s AND status = 'running'",
            (self.project_id,),
        ).fetchall()

        completed: list[UUID] = []
        for graph in running_graphs:
            graph_id = graph["id"]
            if GraphEngine.check_graph_complete(conn, graph_id):
                completed.append(graph_id)
                logger.info("Graph %s completed", graph_id)

                emit_event(
                    conn=conn,
                    project_id=self.project_id,
                    event_type=EventType.AGENT_COMPLETED,
                    actor="run_engine",
                    payload={
                        "graph_id": str(graph_id),
                        "message": "Graph completed — all nodes done",
                    },
                )

        return completed

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def get_status(self, conn: psycopg.Connection) -> dict[str, Any]:
        """Return comprehensive project status.

        Includes:
        - Current phase + DoD
        - Active graphs
        - Node counts by status
        - Recent events
        """
        # Current phase
        current_phase = PhaseEngine.get_current_phase(conn, self.project_id)
        phase_info: dict[str, Any] = {}
        dod_info: dict[str, Any] = {}

        if current_phase is not None:
            phase_info = {
                "name": current_phase["name"],
                "status": current_phase["status"],
            }
            dod_info = PhaseEngine.evaluate_dod(conn, current_phase["id"])

        # Active graphs
        active_graphs = conn.execute(
            "SELECT id, name, status FROM execution_graphs "
            "WHERE project_id = %s AND status IN ('pending', 'running') "
            "ORDER BY created_at",
            (self.project_id,),
        ).fetchall()

        # Node counts by status
        node_counts_rows = conn.execute(
            """
            SELECT en.status, COUNT(*) AS cnt
            FROM execution_nodes en
            JOIN execution_graphs eg ON en.graph_id = eg.id
            WHERE eg.project_id = %s
            GROUP BY en.status
            """,
            (self.project_id,),
        ).fetchall()
        node_counts = {row["status"]: row["cnt"] for row in node_counts_rows}

        # Recent events (last 10)
        recent_events = conn.execute(
            "SELECT id, event_type, actor, created_at FROM events "
            "WHERE project_id = %s ORDER BY created_at DESC LIMIT 10",
            (self.project_id,),
        ).fetchall()

        return {
            "phase": phase_info,
            "dod": dod_info,
            "active_graphs": [dict(g) for g in active_graphs],
            "node_counts": node_counts,
            "recent_events": [dict(e) for e in recent_events],
        }
