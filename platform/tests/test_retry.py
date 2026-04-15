"""Tests for Agent Retry and Error Handling (Task 13)."""

from __future__ import annotations

import uuid
from unittest.mock import patch
from uuid import UUID

import psycopg

from etc_platform.agent_runtime import AgentRunner
from etc_platform.config import EtcConfig
from etc_platform.retry import (
    RetryPolicy,
    execute_retry,
    get_failed_nodes,
    prepare_retry,
    retry_all_eligible,
    should_retry,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _setup_project(db: psycopg.Connection) -> tuple[UUID, UUID]:
    """Create project -> phase -> graph chain. Returns (project_id, graph_id)."""
    project = db.execute(
        "INSERT INTO projects (name, root_path, classification) "
        "VALUES ('p', '/tmp', 'greenfield') RETURNING id"
    ).fetchone()
    assert project is not None
    pid = project["id"]

    phase = db.execute(
        "INSERT INTO phases (project_id, name) VALUES (%s, 'Build') RETURNING id",
        (pid,),
    ).fetchone()
    assert phase is not None

    graph = db.execute(
        "INSERT INTO execution_graphs (project_id, phase_id, name, status) "
        "VALUES (%s, %s, 'g', 'running') RETURNING id",
        (pid, phase["id"]),
    ).fetchone()
    assert graph is not None

    return pid, graph["id"]


def _insert_node(
    db: psycopg.Connection,
    graph_id: UUID,
    *,
    status: str = "failed",
    max_retries: int = 3,
    retry_count: int = 0,
    name: str = "n",
    agent_type: str = "researcher",
    assignment: str | None = None,
) -> UUID:
    """Insert an execution_node and return its id."""
    row = db.execute(
        "INSERT INTO execution_nodes "
        "(graph_id, node_type, name, agent_type, status, max_retries, retry_count, assignment) "
        "VALUES (%s, 'leaf', %s, %s, %s, %s, %s, %s) RETURNING id",
        (graph_id, name, agent_type, status, max_retries, retry_count, assignment),
    ).fetchone()
    assert row is not None
    return row["id"]


# ===========================================================================
# RetryPolicy
# ===========================================================================


class TestRetryPolicy:
    def test_default_values(self) -> None:
        """RetryPolicy has sensible defaults."""
        policy = RetryPolicy()
        assert policy.max_retries == 3
        assert policy.backoff_base == 1.0
        assert policy.backoff_multiplier == 5.0
        assert policy.backoff_max == 30.0

    def test_get_delay_first_attempt(self) -> None:
        """First attempt delay is base * multiplier^0 = base * 1."""
        policy = RetryPolicy()
        # attempt 0: 1.0 * 5.0^0 = 1.0
        assert policy.get_delay(0) == 1.0

    def test_get_delay_exponential(self) -> None:
        """Delay grows exponentially with attempt number."""
        policy = RetryPolicy()
        # attempt 1: 1.0 * 5.0^1 = 5.0
        assert policy.get_delay(1) == 5.0
        # attempt 2: 1.0 * 5.0^2 = 25.0
        assert policy.get_delay(2) == 25.0

    def test_get_delay_capped(self) -> None:
        """Delay is capped at backoff_max."""
        policy = RetryPolicy()
        # attempt 3: 1.0 * 5.0^3 = 125.0 -> capped to 30.0
        assert policy.get_delay(3) == 30.0
        # Very high attempt should still be capped
        assert policy.get_delay(100) == 30.0


# ===========================================================================
# should_retry
# ===========================================================================


class TestShouldRetry:
    def test_failed_node_eligible(self, db: psycopg.Connection) -> None:
        """A failed node with retry_count < max_retries is eligible."""
        _pid, graph_id = _setup_project(db)
        node_id = _insert_node(db, graph_id, status="failed", max_retries=3, retry_count=0)

        assert should_retry(db, node_id) is True

    def test_max_retries_exceeded(self, db: psycopg.Connection) -> None:
        """A failed node with retry_count >= max_retries is NOT eligible."""
        _pid, graph_id = _setup_project(db)
        node_id = _insert_node(db, graph_id, status="failed", max_retries=3, retry_count=3)

        assert should_retry(db, node_id) is False

    def test_non_failed_node_not_eligible(self, db: psycopg.Connection) -> None:
        """A node that is not in 'failed' status is NOT eligible for retry."""
        _pid, graph_id = _setup_project(db)
        node_id = _insert_node(db, graph_id, status="running", max_retries=3, retry_count=0)

        assert should_retry(db, node_id) is False


# ===========================================================================
# prepare_retry
# ===========================================================================


class TestPrepareRetry:
    def test_increments_retry_count(self, db: psycopg.Connection) -> None:
        """prepare_retry increments the node's retry_count by 1."""
        _pid, graph_id = _setup_project(db)
        node_id = _insert_node(db, graph_id, status="failed", max_retries=3, retry_count=0)

        result = prepare_retry(db, node_id)

        row = db.execute(
            "SELECT retry_count FROM execution_nodes WHERE id = %s", (node_id,)
        ).fetchone()
        assert row is not None
        assert row["retry_count"] == 1
        assert result["retry_count"] == 1

    def test_sets_retrying_status(self, db: psycopg.Connection) -> None:
        """prepare_retry sets the node status to 'retrying'."""
        _pid, graph_id = _setup_project(db)
        node_id = _insert_node(db, graph_id, status="failed", max_retries=3, retry_count=0)

        prepare_retry(db, node_id)

        row = db.execute(
            "SELECT status FROM execution_nodes WHERE id = %s", (node_id,)
        ).fetchone()
        assert row is not None
        assert row["status"] == "retrying"

    def test_augmented_context_with_violations(self, db: psycopg.Connection) -> None:
        """When violation_details is provided, augmented_context includes them."""
        _pid, graph_id = _setup_project(db)
        node_id = _insert_node(db, graph_id, status="failed", max_retries=3, retry_count=0)

        violation = "Missing required section: ## Summary"
        result = prepare_retry(db, node_id, violation_details=violation)

        assert "PREVIOUS ATTEMPT FAILED" in result["augmented_context"]
        assert violation in result["augmented_context"]
        assert "Please address the issues above" in result["augmented_context"]

    def test_augmented_context_without_violations(self, db: psycopg.Connection) -> None:
        """When no violation_details, augmented_context is None."""
        _pid, graph_id = _setup_project(db)
        node_id = _insert_node(db, graph_id, status="failed", max_retries=3, retry_count=0)

        result = prepare_retry(db, node_id)

        assert result["augmented_context"] is None


# ===========================================================================
# execute_retry
# ===========================================================================


class TestExecuteRetry:
    def test_retries_eligible_node(self, db: psycopg.Connection) -> None:
        """execute_retry deploys an agent and returns a run_id for an eligible node."""
        _pid, graph_id = _setup_project(db)
        node_id = _insert_node(db, graph_id, status="failed", max_retries=3, retry_count=0)

        config = EtcConfig()
        runner = AgentRunner(config=config)

        mock_run_id = uuid.uuid4()
        with patch.object(runner, "deploy", return_value=mock_run_id):
            result = execute_retry(db, node_id, runner)

        assert result == mock_run_id

        # Node status should be 'running'
        row = db.execute(
            "SELECT status FROM execution_nodes WHERE id = %s", (node_id,)
        ).fetchone()
        assert row is not None
        assert row["status"] == "running"

    def test_returns_none_for_ineligible(self, db: psycopg.Connection) -> None:
        """execute_retry returns None if the node is not eligible for retry."""
        _pid, graph_id = _setup_project(db)
        node_id = _insert_node(db, graph_id, status="failed", max_retries=3, retry_count=3)

        config = EtcConfig()
        runner = AgentRunner(config=config)

        result = execute_retry(db, node_id, runner)
        assert result is None

    def test_retry_with_violation_context(self, db: psycopg.Connection) -> None:
        """execute_retry passes violation context through to the agent deployment."""
        _pid, graph_id = _setup_project(db)
        node_id = _insert_node(
            db,
            graph_id,
            status="failed",
            max_retries=3,
            retry_count=0,
            assignment='{"task": "Write code"}',
        )

        config = EtcConfig()
        runner = AgentRunner(config=config)

        mock_run_id = uuid.uuid4()
        violation = "Output missing ## Summary section"
        with patch.object(runner, "deploy", return_value=mock_run_id) as mock_deploy:
            result = execute_retry(
                db, node_id, runner, violation_details=violation
            )

        assert result == mock_run_id

        # Verify deploy was called and the assignment contains the augmented context
        mock_deploy.assert_called_once()
        call_kwargs = mock_deploy.call_args
        # The assignment passed to deploy should include augmented context
        assignment_arg = call_kwargs.kwargs.get("assignment") or call_kwargs[1].get("assignment")
        if assignment_arg is None:
            # positional args: conn, node_id, agent_type, assignment, model_override
            assignment_arg = call_kwargs[0][3] if len(call_kwargs[0]) > 3 else call_kwargs.kwargs["assignment"]
        assert "PREVIOUS ATTEMPT FAILED" in assignment_arg.get("retry_context", "")


# ===========================================================================
# get_failed_nodes
# ===========================================================================


class TestGetFailedNodes:
    def test_returns_eligible_failed_nodes(self, db: psycopg.Connection) -> None:
        """Returns failed nodes where retry_count < max_retries."""
        pid, graph_id = _setup_project(db)
        node1_id = _insert_node(db, graph_id, status="failed", max_retries=3, retry_count=0, name="n1")
        node2_id = _insert_node(db, graph_id, status="failed", max_retries=3, retry_count=1, name="n2")

        failed = get_failed_nodes(db, pid)

        node_ids = {n["id"] for n in failed}
        assert node1_id in node_ids
        assert node2_id in node_ids

    def test_excludes_max_retries_exceeded(self, db: psycopg.Connection) -> None:
        """Does not return nodes that have exhausted all retries."""
        pid, graph_id = _setup_project(db)
        eligible_id = _insert_node(db, graph_id, status="failed", max_retries=3, retry_count=1, name="eligible")
        exhausted_id = _insert_node(db, graph_id, status="failed", max_retries=3, retry_count=3, name="exhausted")

        failed = get_failed_nodes(db, pid)

        node_ids = {n["id"] for n in failed}
        assert eligible_id in node_ids
        assert exhausted_id not in node_ids

    def test_empty_when_no_failures(self, db: psycopg.Connection) -> None:
        """Returns an empty list when no nodes are in failed status."""
        pid, graph_id = _setup_project(db)
        _insert_node(db, graph_id, status="completed", max_retries=3, retry_count=0, name="done")

        failed = get_failed_nodes(db, pid)
        assert failed == []


# ===========================================================================
# retry_all_eligible
# ===========================================================================


class TestRetryAllEligible:
    def test_retries_all_failed(self, db: psycopg.Connection) -> None:
        """Retries all eligible failed nodes and returns run_ids."""
        pid, graph_id = _setup_project(db)
        _insert_node(db, graph_id, status="failed", max_retries=3, retry_count=0, name="n1")
        _insert_node(db, graph_id, status="failed", max_retries=3, retry_count=1, name="n2")

        config = EtcConfig()
        runner = AgentRunner(config=config)

        mock_ids = [uuid.uuid4(), uuid.uuid4()]
        with patch.object(runner, "deploy", side_effect=mock_ids):
            run_ids = retry_all_eligible(db, pid, runner)

        assert len(run_ids) == 2
        assert all(isinstance(rid, UUID) for rid in run_ids)

    def test_empty_when_none_eligible(self, db: psycopg.Connection) -> None:
        """Returns an empty list when no nodes are eligible for retry."""
        pid, graph_id = _setup_project(db)
        _insert_node(db, graph_id, status="completed", max_retries=3, retry_count=0, name="done")

        config = EtcConfig()
        runner = AgentRunner(config=config)

        run_ids = retry_all_eligible(db, pid, runner)
        assert run_ids == []
