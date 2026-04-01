"""Tests for guardrail override functionality."""

from __future__ import annotations

import json
from uuid import UUID, uuid4

import psycopg
import pytest


def _create_chain(db: psycopg.Connection) -> dict[str, UUID]:
    """Create a full chain: project -> graph -> node -> agent_run -> agent_output.

    Returns a dict with keys: project_id, graph_id, node_id, run_id, output_id.
    """
    project = db.execute(
        "INSERT INTO projects (name, root_path, classification) "
        "VALUES ('test-project', '/tmp/test', 'greenfield') RETURNING id"
    ).fetchone()
    assert project is not None

    phase = db.execute(
        "INSERT INTO phases (project_id, name, dod_items) "
        "VALUES (%s, 'Build', '[]') RETURNING id",
        (project["id"],),
    ).fetchone()
    assert phase is not None

    graph = db.execute(
        "INSERT INTO execution_graphs (project_id, phase_id, name) "
        "VALUES (%s, %s, 'test-graph') RETURNING id",
        (project["id"], phase["id"]),
    ).fetchone()
    assert graph is not None

    node = db.execute(
        "INSERT INTO execution_nodes (graph_id, node_type, name, agent_type, depth) "
        "VALUES (%s, 'leaf', 'test-node', 'researcher', 0) RETURNING id",
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
        "INSERT INTO agent_outputs (run_id, output_type, accepted) "
        "VALUES (%s, 'research_report', FALSE) RETURNING id",
        (run["id"],),
    ).fetchone()
    assert output is not None

    return {
        "project_id": project["id"],
        "phase_id": phase["id"],
        "graph_id": graph["id"],
        "node_id": node["id"],
        "run_id": run["id"],
        "output_id": output["id"],
    }


def _insert_guardrail_check(
    db: psycopg.Connection,
    output_id: UUID,
    rule_name: str = "anti_pattern_scan",
    passed: bool = False,
    severity: str = "critical",
    violation_details: dict | None = None,
) -> UUID:
    """Insert a guardrail check and return its id."""
    row = db.execute(
        """
        INSERT INTO guardrail_checks (output_id, rule_name, passed, severity, violation_details)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            output_id,
            rule_name,
            passed,
            severity,
            json.dumps(violation_details) if violation_details else None,
        ),
    ).fetchone()
    assert row is not None
    return row["id"]


class TestOverrideGuardrailCheck:
    def test_override_changes_passed_to_true(self, db: psycopg.Connection) -> None:
        """Override a failed check, verify passed becomes True."""
        from etc_platform.guardrails import override_guardrail_check

        chain = _create_chain(db)
        check_id = _insert_guardrail_check(db, chain["output_id"])

        # Verify it starts as failed
        before = db.execute(
            "SELECT passed FROM guardrail_checks WHERE id = %s", (check_id,)
        ).fetchone()
        assert before is not None
        assert before["passed"] is False

        result = override_guardrail_check(db, check_id, reason="Reviewed and acceptable")
        assert result is True

        after = db.execute(
            "SELECT passed FROM guardrail_checks WHERE id = %s", (check_id,)
        ).fetchone()
        assert after is not None
        assert after["passed"] is True

    def test_override_records_reason(self, db: psycopg.Connection) -> None:
        """Verify override_reason, overridden_by, overridden_at are stored."""
        from etc_platform.guardrails import override_guardrail_check

        chain = _create_chain(db)
        check_id = _insert_guardrail_check(db, chain["output_id"])

        override_guardrail_check(
            db, check_id, reason="False positive", overridden_by="admin"
        )

        row = db.execute(
            "SELECT override_reason, overridden_by, overridden_at "
            "FROM guardrail_checks WHERE id = %s",
            (check_id,),
        ).fetchone()
        assert row is not None
        assert row["override_reason"] == "False positive"
        assert row["overridden_by"] == "admin"
        assert row["overridden_at"] is not None

    def test_override_reevaluates_acceptance(self, db: psycopg.Connection) -> None:
        """After overriding last critical failure, agent_output.accepted becomes True."""
        from etc_platform.guardrails import override_guardrail_check

        chain = _create_chain(db)
        output_id = chain["output_id"]

        # Insert one critical failure and one passing check
        check_id = _insert_guardrail_check(
            db, output_id, rule_name="anti_pattern_scan", passed=False, severity="critical"
        )
        _insert_guardrail_check(
            db, output_id, rule_name="output_schema_validation", passed=True, severity="high"
        )

        # Output should be not accepted
        before = db.execute(
            "SELECT accepted FROM agent_outputs WHERE id = %s", (output_id,)
        ).fetchone()
        assert before is not None
        assert before["accepted"] is False

        # Override the critical failure
        override_guardrail_check(db, check_id, reason="Acceptable")

        # Now output should be accepted
        after = db.execute(
            "SELECT accepted FROM agent_outputs WHERE id = %s", (output_id,)
        ).fetchone()
        assert after is not None
        assert after["accepted"] is True

    def test_override_nonexistent_check_returns_false(
        self, db: psycopg.Connection
    ) -> None:
        """Override with fake UUID returns False."""
        from etc_platform.guardrails import override_guardrail_check

        result = override_guardrail_check(db, uuid4(), reason="Doesn't matter")
        assert result is False

    def test_override_already_passed_returns_false(
        self, db: psycopg.Connection
    ) -> None:
        """Override a check that already passed returns False."""
        from etc_platform.guardrails import override_guardrail_check

        chain = _create_chain(db)
        check_id = _insert_guardrail_check(
            db, chain["output_id"], passed=True, severity="critical"
        )

        result = override_guardrail_check(db, check_id, reason="Already passed")
        assert result is False


class TestListGuardrailChecks:
    def test_list_guardrail_checks_returns_results(
        self, db: psycopg.Connection
    ) -> None:
        """Create checks, list them, verify they come back."""
        from etc_platform.guardrails import list_guardrail_checks

        chain = _create_chain(db)
        output_id = chain["output_id"]

        _insert_guardrail_check(
            db, output_id, rule_name="anti_pattern_scan", passed=False, severity="critical"
        )
        _insert_guardrail_check(
            db, output_id, rule_name="output_schema_validation", passed=True, severity="high"
        )

        results = list_guardrail_checks(db, chain["project_id"])
        assert len(results) == 2
        rule_names = {r["rule_name"] for r in results}
        assert "anti_pattern_scan" in rule_names
        assert "output_schema_validation" in rule_names

    def test_list_guardrail_checks_failed_only(
        self, db: psycopg.Connection
    ) -> None:
        """Verify failed_only filter works."""
        from etc_platform.guardrails import list_guardrail_checks

        chain = _create_chain(db)
        output_id = chain["output_id"]

        _insert_guardrail_check(
            db, output_id, rule_name="anti_pattern_scan", passed=False, severity="critical"
        )
        _insert_guardrail_check(
            db, output_id, rule_name="output_schema_validation", passed=True, severity="high"
        )

        all_results = list_guardrail_checks(db, chain["project_id"], failed_only=False)
        assert len(all_results) == 2

        failed_results = list_guardrail_checks(db, chain["project_id"], failed_only=True)
        assert len(failed_results) == 1
        assert failed_results[0]["rule_name"] == "anti_pattern_scan"
        assert failed_results[0]["passed"] is False
