"""Agent Retry and Error Handling — automatic retry with violation context injection.

Provides exponential backoff retry logic for failed agent execution nodes,
including context augmentation with guardrail violation details so retried
agents can correct their output.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import psycopg

from etc_platform.agent_runtime import AgentRunner

logger = logging.getLogger(__name__)


# ===========================================================================
# RetryPolicy
# ===========================================================================


@dataclass
class RetryPolicy:
    """Configurable retry policy with exponential backoff."""

    max_retries: int = 3
    backoff_base: float = 1.0  # seconds
    backoff_multiplier: float = 5.0
    backoff_max: float = 30.0

    def get_delay(self, attempt: int) -> float:
        """Exponential backoff: base * multiplier^attempt, capped at backoff_max."""
        delay = self.backoff_base * (self.backoff_multiplier ** attempt)
        return min(delay, self.backoff_max)


# ===========================================================================
# should_retry
# ===========================================================================


def should_retry(conn: psycopg.Connection, node_id: UUID) -> bool:
    """Check if a failed node is eligible for retry.

    A node is eligible when:
    - Its status is 'failed'
    - Its retry_count < max_retries

    Args:
        conn: Database connection.
        node_id: The execution node to check.

    Returns:
        True if the node is eligible for retry.
    """
    row = conn.execute(
        "SELECT status, retry_count, max_retries FROM execution_nodes WHERE id = %s",
        (node_id,),
    ).fetchone()

    if row is None:
        return False

    return row["status"] == "failed" and row["retry_count"] < row["max_retries"]


# ===========================================================================
# prepare_retry
# ===========================================================================


def prepare_retry(
    conn: psycopg.Connection,
    node_id: UUID,
    violation_details: str | None = None,
) -> dict[str, Any]:
    """Prepare a node for retry.

    - Increments retry_count
    - Sets status to 'retrying'
    - Builds augmented context with violation details (if provided)

    Args:
        conn: Database connection.
        node_id: The execution node to prepare.
        violation_details: Optional string describing why the previous attempt failed.

    Returns:
        Dict with: node_id, retry_count, augmented_context.
    """
    row = conn.execute(
        """
        UPDATE execution_nodes
        SET retry_count = retry_count + 1,
            status = 'retrying'
        WHERE id = %s
        RETURNING retry_count
        """,
        (node_id,),
    ).fetchone()
    assert row is not None

    augmented_context: str | None = None
    if violation_details is not None:
        augmented_context = (
            f"PREVIOUS ATTEMPT FAILED:\n"
            f"{violation_details}\n\n"
            f"Please address the issues above in this retry attempt."
        )

    return {
        "node_id": node_id,
        "retry_count": row["retry_count"],
        "augmented_context": augmented_context,
    }


# ===========================================================================
# execute_retry
# ===========================================================================


def execute_retry(
    conn: psycopg.Connection,
    node_id: UUID,
    agent_runner: AgentRunner,
    violation_details: str | None = None,
    model_override: Any | None = None,
) -> UUID | None:
    """Full retry flow for a failed node.

    1. Check should_retry -> if not, return None
    2. Prepare retry (increment count, build context)
    3. Set node status to 'running'
    4. Deploy agent with augmented assignment
    5. Return the run_id

    Args:
        conn: Database connection.
        node_id: The execution node to retry.
        agent_runner: AgentRunner instance for deploying agents.
        violation_details: Optional string describing why the previous attempt failed.
        model_override: Optional model override for testing.

    Returns:
        The run_id UUID if retry was initiated, or None if ineligible.
    """
    if not should_retry(conn, node_id):
        return None

    # Prepare: increment retry_count, set status to 'retrying', build augmented context
    retry_info = prepare_retry(conn, node_id, violation_details=violation_details)

    # Set node to running
    conn.execute(
        "UPDATE execution_nodes SET status = 'running' WHERE id = %s",
        (node_id,),
    )

    # Load the node to get agent_type and original assignment
    node = conn.execute(
        "SELECT agent_type, assignment FROM execution_nodes WHERE id = %s",
        (node_id,),
    ).fetchone()
    assert node is not None

    agent_type = node["agent_type"] or "researcher"

    # Build the assignment, augmenting with retry context if available
    original_assignment = node["assignment"]
    if isinstance(original_assignment, str):
        try:
            assignment = json.loads(original_assignment)
        except (json.JSONDecodeError, TypeError):
            assignment = {"task": original_assignment}
    elif isinstance(original_assignment, dict):
        assignment = dict(original_assignment)
    else:
        assignment = {}

    if retry_info["augmented_context"] is not None:
        assignment["retry_context"] = retry_info["augmented_context"]

    # Deploy the agent
    run_id = agent_runner.deploy(
        conn=conn,
        node_id=node_id,
        agent_type=agent_type,
        assignment=assignment,
        model_override=model_override,
    )

    logger.info(
        "Retry #%d for node %s initiated (run_id=%s)",
        retry_info["retry_count"],
        node_id,
        run_id,
    )

    return run_id


# ===========================================================================
# get_failed_nodes
# ===========================================================================


def get_failed_nodes(conn: psycopg.Connection, project_id: UUID) -> list[dict]:
    """Get all failed nodes for a project that are eligible for retry.

    Returns nodes where status='failed' and retry_count < max_retries.

    Args:
        conn: Database connection.
        project_id: The project to query.

    Returns:
        List of node dicts.
    """
    rows = conn.execute(
        """
        SELECT en.*
        FROM execution_nodes en
        JOIN execution_graphs eg ON en.graph_id = eg.id
        WHERE eg.project_id = %s
          AND en.status = 'failed'
          AND en.retry_count < en.max_retries
        ORDER BY en.name
        """,
        (project_id,),
    ).fetchall()
    return [dict(r) for r in rows]


# ===========================================================================
# retry_all_eligible
# ===========================================================================


def retry_all_eligible(
    conn: psycopg.Connection,
    project_id: UUID,
    agent_runner: AgentRunner,
    model_override: Any | None = None,
) -> list[UUID]:
    """Find all failed eligible nodes and retry them.

    Args:
        conn: Database connection.
        project_id: The project to retry failed nodes for.
        agent_runner: AgentRunner instance for deploying agents.
        model_override: Optional model override for testing.

    Returns:
        List of run_id UUIDs for the retried nodes.
    """
    failed_nodes = get_failed_nodes(conn, project_id)
    run_ids: list[UUID] = []

    for node in failed_nodes:
        run_id = execute_retry(
            conn=conn,
            node_id=node["id"],
            agent_runner=agent_runner,
            model_override=model_override,
        )
        if run_id is not None:
            run_ids.append(run_id)

    logger.info(
        "retry_all_eligible for project %s: %d nodes retried",
        project_id,
        len(run_ids),
    )

    return run_ids
