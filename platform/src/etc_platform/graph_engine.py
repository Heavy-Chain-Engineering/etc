"""Graph Engine — execution graph scheduling with fan-out/reduce patterns (C4)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from uuid import UUID

    import psycopg


class GraphEngine:
    """Manages execution graphs: creation, node scheduling, and lifecycle."""

    @staticmethod
    def create_graph(
        conn: psycopg.Connection,
        project_id: UUID,
        phase_id: UUID,
        name: str,
        description: str | None = None,
    ) -> UUID:
        """Create a new execution graph. Returns graph_id."""
        row = conn.execute(
            """
            INSERT INTO execution_graphs (project_id, phase_id, name, description)
            VALUES (%s, %s, %s, %s)
            RETURNING id
            """,
            (project_id, phase_id, name, description),
        ).fetchone()
        assert row is not None
        return row["id"]

    @staticmethod
    def get_graph(conn: psycopg.Connection, graph_id: UUID) -> dict[str, Any] | None:
        """Get graph details by id."""
        row = conn.execute(
            "SELECT * FROM execution_graphs WHERE id = %s", (graph_id,)
        ).fetchone()
        if row is None:
            return None
        return dict(row)

    @staticmethod
    def add_node(
        conn: psycopg.Connection,
        graph_id: UUID,
        name: str,
        node_type: str,
        agent_type: str | None = None,
        assignment: dict[str, Any] | None = None,
        parent_node_id: UUID | None = None,
        depth: int = 0,
        max_retries: int = 1,
    ) -> UUID:
        """Add a node to the graph. Returns node_id."""
        row = conn.execute(
            """
            INSERT INTO execution_nodes
                (graph_id, name, node_type, agent_type, assignment, parent_node_id, depth, max_retries)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                graph_id,
                name,
                node_type,
                agent_type,
                json.dumps(assignment) if assignment is not None else None,
                parent_node_id,
                depth,
                max_retries,
            ),
        ).fetchone()
        assert row is not None
        return row["id"]

    @staticmethod
    def add_dependency(
        conn: psycopg.Connection,
        node_id: UUID,
        depends_on_node_id: UUID,
    ) -> None:
        """Add a dependency: node_id depends on depends_on_node_id."""
        conn.execute(
            """
            INSERT INTO execution_node_dependencies (node_id, depends_on_node_id)
            VALUES (%s, %s)
            """,
            (node_id, depends_on_node_id),
        )

    @staticmethod
    def get_ready_nodes(
        conn: psycopg.Connection,
        graph_id: UUID,
    ) -> list[dict[str, Any]]:
        """Find nodes that are ready to execute.

        A node is READY when:
        - It is NOT a composite node (composites are structural, never deployed)
        - Its status is 'ready' (promoted by start_graph) OR
          its status is 'pending' AND all dependencies are 'completed'
        - Its parent composite (if any) is in 'running' status

        This is the core scheduling primitive (C4).
        """
        rows = conn.execute(
            """
            SELECT n.*
            FROM execution_nodes n
            WHERE n.graph_id = %s
              AND n.node_type != 'composite'
              AND (
                  n.status = 'ready'
                  OR (
                      n.status = 'pending'
                      AND NOT EXISTS (
                          SELECT 1
                          FROM execution_node_dependencies d
                          JOIN execution_nodes dep ON dep.id = d.depends_on_node_id
                          WHERE d.node_id = n.id
                            AND dep.status != 'completed'
                      )
                      AND EXISTS (
                          SELECT 1
                          FROM execution_node_dependencies d
                          WHERE d.node_id = n.id
                      )
                  )
              )
              AND (
                  n.parent_node_id IS NULL
                  OR EXISTS (
                      SELECT 1 FROM execution_nodes p
                      WHERE p.id = n.parent_node_id
                        AND p.status = 'running'
                  )
              )
            ORDER BY n.depth, n.name
            """,
            (graph_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    @staticmethod
    def mark_node_running(conn: psycopg.Connection, node_id: UUID) -> None:
        """Mark a node as running with started_at timestamp."""
        now = datetime.now(UTC)
        conn.execute(
            "UPDATE execution_nodes SET status = 'running', started_at = %s WHERE id = %s",
            (now, node_id),
        )

    @staticmethod
    def mark_node_completed(
        conn: psycopg.Connection,
        node_id: UUID,
        output_path: str | None = None,
    ) -> None:
        """Mark a node as completed. Cascades completion to parent composites."""
        now = datetime.now(UTC)
        conn.execute(
            "UPDATE execution_nodes SET status = 'completed', completed_at = %s, output_path = %s WHERE id = %s",
            (now, output_path, node_id),
        )

        # Check if parent composite should auto-complete
        node = conn.execute(
            "SELECT parent_node_id FROM execution_nodes WHERE id = %s", (node_id,)
        ).fetchone()
        if node and node["parent_node_id"] is not None:
            GraphEngine._check_and_complete_ancestors(conn, node["parent_node_id"])

        # After ancestor rollup, activate any composites that are now unblocked
        node_row = conn.execute(
            "SELECT graph_id FROM execution_nodes WHERE id = %s", (node_id,)
        ).fetchone()
        if node_row:
            GraphEngine.activate_pending_composites(conn, node_row["graph_id"])

    @staticmethod
    def _check_and_complete_ancestors(conn: psycopg.Connection, composite_id: UUID) -> None:
        """Walk up the tree, completing composites whose children are all done."""
        current: UUID | None = composite_id
        while current is not None:
            row = conn.execute(
                """
                SELECT COUNT(*) AS total,
                       COUNT(*) FILTER (WHERE status = 'completed') AS done
                FROM execution_nodes WHERE parent_node_id = %s
                """,
                (current,),
            ).fetchone()
            assert row is not None

            if row["total"] > 0 and row["done"] == row["total"]:
                now = datetime.now(UTC)
                conn.execute(
                    "UPDATE execution_nodes SET status = 'completed', completed_at = %s WHERE id = %s",
                    (now, current),
                )
                parent = conn.execute(
                    "SELECT parent_node_id FROM execution_nodes WHERE id = %s",
                    (current,),
                ).fetchone()
                current = parent["parent_node_id"] if parent else None
            else:
                break

    @staticmethod
    def activate_pending_composites(conn: psycopg.Connection, graph_id: UUID) -> list[UUID]:
        """Activate composite nodes whose dependencies are all completed.

        Sets the composite to 'running' and promotes its no-dep children to 'ready'.
        Returns list of activated composite node IDs.
        """
        # Find pending composites with all deps completed
        composites = conn.execute(
            """
            SELECT n.id
            FROM execution_nodes n
            WHERE n.graph_id = %s
              AND n.node_type = 'composite'
              AND n.status = 'pending'
              AND NOT EXISTS (
                  SELECT 1
                  FROM execution_node_dependencies d
                  JOIN execution_nodes dep ON dep.id = d.depends_on_node_id
                  WHERE d.node_id = n.id
                    AND dep.status != 'completed'
              )
              AND EXISTS (
                  SELECT 1
                  FROM execution_node_dependencies d
                  WHERE d.node_id = n.id
              )
              AND (
                  n.parent_node_id IS NULL
                  OR EXISTS (
                      SELECT 1 FROM execution_nodes p
                      WHERE p.id = n.parent_node_id AND p.status = 'running'
                  )
              )
            """,
            (graph_id,),
        ).fetchall()

        activated: list[UUID] = []
        now = datetime.now(UTC)
        for row in composites:
            cid = row["id"]
            conn.execute(
                "UPDATE execution_nodes SET status = 'running', started_at = %s WHERE id = %s",
                (now, cid),
            )
            # Promote no-dep children of this composite to 'ready'
            conn.execute(
                """
                UPDATE execution_nodes
                SET status = 'ready'
                WHERE parent_node_id = %s
                  AND status = 'pending'
                  AND node_type != 'composite'
                  AND id NOT IN (
                      SELECT DISTINCT node_id FROM execution_node_dependencies
                  )
                """,
                (cid,),
            )
            activated.append(cid)

        return activated

    @staticmethod
    def mark_node_failed(conn: psycopg.Connection, node_id: UUID) -> None:
        """Mark a node as failed. Propagates to parent if retries exhausted."""
        conn.execute(
            "UPDATE execution_nodes SET status = 'failed' WHERE id = %s",
            (node_id,),
        )

        # Check if retries are exhausted and propagate to parent
        node = conn.execute(
            "SELECT parent_node_id, retry_count, max_retries FROM execution_nodes WHERE id = %s",
            (node_id,),
        ).fetchone()
        if (
            node
            and node["parent_node_id"] is not None
            and node["retry_count"] >= node["max_retries"]
        ):
            GraphEngine.mark_node_failed(conn, node["parent_node_id"])

    @staticmethod
    def reset_subtree(conn: psycopg.Connection, composite_node_id: UUID) -> None:
        """Reset a composite and all its descendants to pending."""
        conn.execute(
            """
            WITH RECURSIVE descendants AS (
                SELECT id FROM execution_nodes WHERE id = %s
                UNION ALL
                SELECT n.id FROM execution_nodes n
                JOIN descendants d ON n.parent_node_id = d.id
            )
            UPDATE execution_nodes
            SET status = 'pending', started_at = NULL, completed_at = NULL
            WHERE id IN (SELECT id FROM descendants)
            """,
            (composite_node_id,),
        )

    @staticmethod
    def check_graph_complete(conn: psycopg.Connection, graph_id: UUID) -> bool:
        """Check if all nodes in the graph are completed.

        If so, mark the graph as completed. Returns True if complete.
        """
        row = conn.execute(
            """
            SELECT COUNT(*) AS total,
                   COUNT(*) FILTER (WHERE status = 'completed') AS done
            FROM execution_nodes
            WHERE graph_id = %s
            """,
            (graph_id,),
        ).fetchone()
        assert row is not None

        if row["total"] == 0:
            return False

        if row["done"] == row["total"]:
            now = datetime.now(UTC)
            conn.execute(
                "UPDATE execution_graphs SET status = 'completed', completed_at = %s WHERE id = %s",
                (now, graph_id),
            )
            return True

        return False

    @staticmethod
    def start_graph(conn: psycopg.Connection, graph_id: UUID) -> None:
        """Set graph status to 'running'. Activate root composites and ready root leaves."""
        conn.execute(
            "UPDATE execution_graphs SET status = 'running' WHERE id = %s",
            (graph_id,),
        )

        # Step 1: Activate root-level composite nodes (no deps) -> 'running'
        conn.execute(
            """
            UPDATE execution_nodes
            SET status = 'running', started_at = NOW()
            WHERE graph_id = %s
              AND status = 'pending'
              AND node_type = 'composite'
              AND parent_node_id IS NULL
              AND id NOT IN (
                  SELECT DISTINCT node_id FROM execution_node_dependencies
              )
            """,
            (graph_id,),
        )

        # Step 2: Ready root-level leaf/reduce nodes (no deps, no parent) -> 'ready'
        #         AND children of running composites (no deps) -> 'ready'
        conn.execute(
            """
            UPDATE execution_nodes
            SET status = 'ready'
            WHERE graph_id = %s
              AND status = 'pending'
              AND node_type != 'composite'
              AND id NOT IN (
                  SELECT DISTINCT node_id FROM execution_node_dependencies
              )
              AND (
                  parent_node_id IS NULL
                  OR parent_node_id IN (
                      SELECT id FROM execution_nodes
                      WHERE graph_id = %s AND status = 'running' AND node_type = 'composite'
                  )
              )
            """,
            (graph_id, graph_id),
        )

    @staticmethod
    def get_node(conn: psycopg.Connection, node_id: UUID) -> dict[str, Any] | None:
        """Get a node by id."""
        row = conn.execute(
            "SELECT * FROM execution_nodes WHERE id = %s", (node_id,)
        ).fetchone()
        if row is None:
            return None
        return dict(row)

    @staticmethod
    def list_nodes(
        conn: psycopg.Connection,
        graph_id: UUID,
    ) -> list[dict[str, Any]]:
        """List all nodes in a graph, ordered by depth then name."""
        rows = conn.execute(
            "SELECT * FROM execution_nodes WHERE graph_id = %s ORDER BY depth, name",
            (graph_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def build_fanout_graph(
    conn: psycopg.Connection,
    project_id: UUID,
    phase_id: UUID,
    name: str,
    agents: list[dict[str, Any]],
    reduce_agent: dict[str, Any] | None = None,
    description: str | None = None,
) -> UUID:
    """Build a complete fan-out/reduce graph in one call.

    Creates:
    - One graph
    - N leaf nodes (the fan-out agents), all at depth 0
    - Optionally 1 reduce node at depth 1 that depends on ALL leaf nodes
    - Auto-starts the graph (marks graph as running, leaf nodes as ready)

    Returns graph_id.
    """
    graph_id = GraphEngine.create_graph(conn, project_id, phase_id, name, description)

    leaf_ids: list[UUID] = []
    for agent in agents:
        node_id = GraphEngine.add_node(
            conn,
            graph_id,
            name=agent["name"],
            node_type="leaf",
            agent_type=agent.get("agent_type"),
            assignment=agent.get("assignment"),
            depth=0,
        )
        leaf_ids.append(node_id)

    if reduce_agent is not None:
        reduce_id = GraphEngine.add_node(
            conn,
            graph_id,
            name=reduce_agent["name"],
            node_type="reduce",
            agent_type=reduce_agent.get("agent_type"),
            assignment=reduce_agent.get("assignment"),
            depth=1,
        )
        for leaf_id in leaf_ids:
            GraphEngine.add_dependency(conn, reduce_id, leaf_id)

    GraphEngine.start_graph(conn, graph_id)

    return graph_id
