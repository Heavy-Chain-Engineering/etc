"""Tests for guardrail -> retry context injection flow (Task 5).

Covers:
- emit_guardrail_violation() emits GUARDRAIL_VIOLATION events on critical failures
- GuardrailMiddleware.check_and_record() emits violation events when node_id/project_id provided
- RETRY_FAILED_NODE decision type in the orchestrator
- SEMDecision.violation_details field
"""

from __future__ import annotations

import json
import uuid
from unittest.mock import MagicMock, patch
from uuid import UUID

import psycopg
import pytest

from etc_platform.events import EventType
from etc_platform.guardrails import (
    AntiPatternScanRule,
    GuardrailMiddleware,
    GuardrailResult,
    emit_guardrail_violation,
)
from etc_platform.orchestrator import DecisionType, SEMDecision, execute_decision


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_project(db: psycopg.Connection) -> UUID:
    """Insert a project and return the project id."""
    row = db.execute(
        "INSERT INTO projects (name, root_path, classification) "
        "VALUES ('test-project', '/tmp/test', 're-engineering') RETURNING id"
    ).fetchone()
    assert row is not None
    return row["id"]


def _create_graph_and_node(
    db: psycopg.Connection,
    project_id: UUID,
    *,
    status: str = "failed",
    max_retries: int = 3,
) -> tuple[UUID, UUID]:
    """Create phase -> graph -> node chain. Returns (graph_id, node_id)."""
    phase = db.execute(
        "INSERT INTO phases (project_id, name, status, dod_items) "
        "VALUES (%s, 'Build', 'active', '[]'::jsonb) RETURNING id",
        (project_id,),
    ).fetchone()
    assert phase is not None

    graph = db.execute(
        "INSERT INTO execution_graphs (project_id, phase_id, name, status) "
        "VALUES (%s, %s, 'test-graph', 'running') RETURNING id",
        (project_id, phase["id"]),
    ).fetchone()
    assert graph is not None

    node = db.execute(
        "INSERT INTO execution_nodes "
        "(graph_id, node_type, name, agent_type, status, assignment, max_retries) "
        "VALUES (%s, 'leaf', 'test-node', 'researcher', %s, %s, %s) RETURNING id",
        (graph["id"], status, json.dumps({"task": "research something"}), max_retries),
    ).fetchone()
    assert node is not None

    return graph["id"], node["id"]


def _create_output_for_node(
    db: psycopg.Connection, node_id: UUID
) -> UUID:
    """Create agent_run -> agent_output chain for a node. Returns output_id."""
    run = db.execute(
        "INSERT INTO agent_runs (node_id, agent_type, model, status) "
        "VALUES (%s, 'researcher', 'test', 'completed') RETURNING id",
        (node_id,),
    ).fetchone()
    assert run is not None

    output = db.execute(
        "INSERT INTO agent_outputs (run_id, output_type) "
        "VALUES (%s, 'research_report') RETURNING id",
        (run["id"],),
    ).fetchone()
    assert output is not None

    return output["id"]


# ===========================================================================
# emit_guardrail_violation
# ===========================================================================


class TestEmitGuardrailViolation:
    def test_emits_event_on_critical_failure(self, db: psycopg.Connection) -> None:
        """A critical failure emits a GUARDRAIL_VIOLATION event."""
        pid = _create_project(db)
        graph_id, node_id = _create_graph_and_node(db, pid)
        output_id = uuid.uuid4()

        results = [
            GuardrailResult(
                rule_name="domain_fidelity_check",
                passed=False,
                severity="critical",
                violation_details={"axiom_violations": [{"axiom": "test"}]},
            ),
        ]

        emit_guardrail_violation(db, pid, output_id, node_id, results)

        event = db.execute(
            "SELECT * FROM events WHERE project_id = %s AND event_type = %s",
            (pid, "guardrail_violation"),
        ).fetchone()
        assert event is not None
        payload = event["payload"]
        assert payload["node_id"] == str(node_id)
        assert payload["output_id"] == str(output_id)
        assert len(payload["critical_failures"]) == 1
        assert payload["critical_failures"][0]["rule_name"] == "domain_fidelity_check"

    def test_no_event_when_no_critical_failures(self, db: psycopg.Connection) -> None:
        """Non-critical failures do not trigger a violation event."""
        pid = _create_project(db)

        results = [
            GuardrailResult(
                rule_name="schema_validation",
                passed=False,
                severity="high",
            ),
        ]

        emit_guardrail_violation(db, pid, uuid.uuid4(), uuid.uuid4(), results)

        event = db.execute(
            "SELECT * FROM events WHERE project_id = %s AND event_type = %s",
            (pid, "guardrail_violation"),
        ).fetchone()
        assert event is None

    def test_no_event_when_all_pass(self, db: psycopg.Connection) -> None:
        """Passing critical checks do not trigger a violation event."""
        pid = _create_project(db)

        results = [
            GuardrailResult(
                rule_name="anti_pattern_scan",
                passed=True,
                severity="critical",
            ),
        ]

        emit_guardrail_violation(db, pid, uuid.uuid4(), uuid.uuid4(), results)

        event = db.execute(
            "SELECT * FROM events WHERE project_id = %s AND event_type = %s",
            (pid, "guardrail_violation"),
        ).fetchone()
        assert event is None

    def test_multiple_critical_failures(self, db: psycopg.Connection) -> None:
        """Multiple critical failures are all included in the event payload."""
        pid = _create_project(db)
        graph_id, node_id = _create_graph_and_node(db, pid)
        output_id = uuid.uuid4()

        results = [
            GuardrailResult(
                rule_name="domain_fidelity_check",
                passed=False,
                severity="critical",
                violation_details={"axiom_violations": [{"axiom": "A1"}]},
            ),
            GuardrailResult(
                rule_name="anti_pattern_scan",
                passed=False,
                severity="critical",
                violation_details={"boolean_flag_sets": ["is_active, has_perm"]},
            ),
            GuardrailResult(
                rule_name="schema_validation",
                passed=False,
                severity="high",  # not critical, should be excluded
            ),
        ]

        emit_guardrail_violation(db, pid, output_id, node_id, results)

        event = db.execute(
            "SELECT * FROM events WHERE project_id = %s AND event_type = %s",
            (pid, "guardrail_violation"),
        ).fetchone()
        assert event is not None
        assert len(event["payload"]["critical_failures"]) == 2


# ===========================================================================
# check_and_record emits violation
# ===========================================================================


class TestCheckAndRecordEmitsViolation:
    def test_check_and_record_emits_on_critical_failure(
        self, db: psycopg.Connection
    ) -> None:
        """check_and_record emits GUARDRAIL_VIOLATION when node_id/project_id given."""
        pid = _create_project(db)
        graph_id, node_id = _create_graph_and_node(db, pid)
        output_id = _create_output_for_node(db, node_id)

        # AntiPatternScanRule is critical severity
        middleware = GuardrailMiddleware(rules=[AntiPatternScanRule()])

        # Content with anti-pattern that triggers critical failure
        bad_content = (
            "is_active, has_premium, can_export, should_notify "
            "-- these boolean flags control behavior"
        )

        results = middleware.check_and_record(
            conn=db,
            output_id=output_id,
            content=bad_content,
            output_type="research_report",
            node_id=node_id,
            project_id=pid,
        )

        # Verify we actually got a critical failure
        has_critical_fail = any(
            not r.passed and r.severity == "critical" for r in results
        )
        assert has_critical_fail, "Test setup: expected a critical failure from anti-pattern content"

        # Verify violation event emitted
        event = db.execute(
            "SELECT * FROM events WHERE project_id = %s AND event_type = %s",
            (pid, "guardrail_violation"),
        ).fetchone()
        assert event is not None
        assert event["payload"]["node_id"] == str(node_id)

    def test_check_and_record_no_event_without_ids(
        self, db: psycopg.Connection
    ) -> None:
        """check_and_record does NOT emit when node_id/project_id are missing (backward compat)."""
        pid = _create_project(db)
        graph_id, node_id = _create_graph_and_node(db, pid)
        output_id = _create_output_for_node(db, node_id)

        middleware = GuardrailMiddleware(rules=[AntiPatternScanRule()])
        bad_content = (
            "is_active, has_premium, can_export, should_notify flags everywhere"
        )

        # Call without node_id/project_id (old signature)
        results = middleware.check_and_record(
            conn=db,
            output_id=output_id,
            content=bad_content,
            output_type="research_report",
        )

        # Should still return results
        assert isinstance(results, list)

        # No violation event should exist
        event = db.execute(
            "SELECT * FROM events WHERE project_id = %s AND event_type = %s",
            (pid, "guardrail_violation"),
        ).fetchone()
        assert event is None

    def test_check_and_record_no_event_when_passes(
        self, db: psycopg.Connection
    ) -> None:
        """check_and_record does NOT emit when all checks pass."""
        pid = _create_project(db)
        graph_id, node_id = _create_graph_and_node(db, pid)
        output_id = _create_output_for_node(db, node_id)

        middleware = GuardrailMiddleware(rules=[AntiPatternScanRule()])

        results = middleware.check_and_record(
            conn=db,
            output_id=output_id,
            content="Clean research content with no anti-patterns.",
            output_type="research_report",
            node_id=node_id,
            project_id=pid,
        )

        assert all(r.passed for r in results)

        event = db.execute(
            "SELECT * FROM events WHERE project_id = %s AND event_type = %s",
            (pid, "guardrail_violation"),
        ).fetchone()
        assert event is None


# ===========================================================================
# RETRY_FAILED_NODE decision type
# ===========================================================================


class TestRetryFailedNodeDecision:
    def test_decision_type_exists(self) -> None:
        """RETRY_FAILED_NODE is a valid DecisionType."""
        assert DecisionType.RETRY_FAILED_NODE == "retry_failed_node"

    def test_sem_decision_accepts_violation_details(self) -> None:
        """SEMDecision can be constructed with violation_details."""
        d = SEMDecision(
            decision_type=DecisionType.RETRY_FAILED_NODE,
            reasoning="Guardrail violation on domain fidelity",
            node_id="some-uuid",
            violation_details="Domain fidelity check failed: contradicted axiom X",
        )
        assert d.violation_details is not None
        assert d.decision_type == DecisionType.RETRY_FAILED_NODE

    def test_sem_decision_violation_details_optional(self) -> None:
        """violation_details defaults to None."""
        d = SEMDecision(
            decision_type=DecisionType.RETRY_FAILED_NODE,
            reasoning="Retry without specific context",
            node_id="some-uuid",
        )
        assert d.violation_details is None

    def test_execute_retry_failed_node(self, db: psycopg.Connection) -> None:
        """execute_decision with RETRY_FAILED_NODE calls execute_retry."""
        pid = _create_project(db)
        graph_id, node_id = _create_graph_and_node(db, pid, status="failed")

        decision = SEMDecision(
            decision_type=DecisionType.RETRY_FAILED_NODE,
            reasoning="Guardrail failure, retrying",
            node_id=str(node_id),
            violation_details="Anti-pattern detected: boolean flags",
        )

        mock_run_id = uuid.uuid4()
        with patch(
            "etc_platform.retry.execute_retry", return_value=mock_run_id
        ) as mock_retry:
            execute_decision(db, pid, decision)

        mock_retry.assert_called_once()
        call_kwargs = mock_retry.call_args
        assert call_kwargs.kwargs.get("violation_details") == "Anti-pattern detected: boolean flags"

    def test_execute_retry_failed_node_requires_node_id(
        self, db: psycopg.Connection
    ) -> None:
        """RETRY_FAILED_NODE without node_id raises AssertionError."""
        pid = _create_project(db)

        decision = SEMDecision(
            decision_type=DecisionType.RETRY_FAILED_NODE,
            reasoning="Retry",
            node_id=None,
        )

        with pytest.raises(AssertionError, match="RETRY_FAILED_NODE requires node_id"):
            execute_decision(db, pid, decision)
