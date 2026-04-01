"""Project metrics and observability — token usage, agent velocity, phase durations, guardrail stats.

Provides read-only aggregate queries over the platform's Postgres tables
for dashboards, CLI reporting, and operational visibility.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import psycopg


class ProjectMetrics:
    """Static methods that query aggregate metrics for a project."""

    @staticmethod
    def get_token_usage(conn: psycopg.Connection, project_id: UUID) -> dict[str, Any]:
        """Token usage per project: total input/output tokens.

        Joins agent_runs -> execution_nodes -> execution_graphs to scope by project.

        Returns:
            {"input_tokens": int, "output_tokens": int, "total_tokens": int}
        """
        row = conn.execute(
            """
            SELECT COALESCE(SUM(ar.tokens_input), 0)  AS input_tokens,
                   COALESCE(SUM(ar.tokens_output), 0) AS output_tokens
            FROM agent_runs ar
            JOIN execution_nodes en ON ar.node_id = en.id
            JOIN execution_graphs eg ON en.graph_id = eg.id
            WHERE eg.project_id = %s
            """,
            (project_id,),
        ).fetchone()
        assert row is not None

        return {
            "input_tokens": row["input_tokens"],
            "output_tokens": row["output_tokens"],
            "total_tokens": row["input_tokens"] + row["output_tokens"],
        }

    @staticmethod
    def get_agent_velocity(conn: psycopg.Connection, project_id: UUID) -> dict[str, Any]:
        """Agent stats: total runs, completed, failed, avg duration in seconds.

        Returns:
            {
                "total_runs": int,
                "completed": int,
                "failed": int,
                "avg_duration_seconds": float | None,
            }
        """
        row = conn.execute(
            """
            SELECT COUNT(*)                                          AS total_runs,
                   COUNT(*) FILTER (WHERE ar.status = 'completed')   AS completed,
                   COUNT(*) FILTER (WHERE ar.status = 'failed')      AS failed,
                   AVG(EXTRACT(EPOCH FROM (ar.completed_at - ar.started_at)))
                       FILTER (WHERE ar.completed_at IS NOT NULL)    AS avg_duration_seconds
            FROM agent_runs ar
            JOIN execution_nodes en ON ar.node_id = en.id
            JOIN execution_graphs eg ON en.graph_id = eg.id
            WHERE eg.project_id = %s
            """,
            (project_id,),
        ).fetchone()
        assert row is not None

        avg_dur = row["avg_duration_seconds"]
        if avg_dur is not None:
            avg_dur = float(avg_dur)

        return {
            "total_runs": row["total_runs"],
            "completed": row["completed"],
            "failed": row["failed"],
            "avg_duration_seconds": avg_dur,
        }

    @staticmethod
    def get_phase_duration(conn: psycopg.Connection, project_id: UUID) -> list[dict[str, Any]]:
        """Duration per phase (entered_at to completed_at).

        Returns a list of dicts for each phase, ordered by SDLC sequence:
            [{"name": str, "status": str, "entered_at": datetime|None,
              "completed_at": datetime|None, "duration_seconds": float|None}, ...]
        """
        rows = conn.execute(
            """
            SELECT name, status, entered_at, completed_at,
                   EXTRACT(EPOCH FROM (completed_at - entered_at)) AS duration_seconds
            FROM phases
            WHERE project_id = %s
            ORDER BY array_position(
                ARRAY['Bootstrap','Spec','Design','Decompose','Build','Verify','Ship','Evaluate'],
                name
            )
            """,
            (project_id,),
        ).fetchall()

        result: list[dict[str, Any]] = []
        for r in rows:
            dur = r["duration_seconds"]
            if dur is not None:
                dur = float(dur)
            result.append({
                "name": r["name"],
                "status": r["status"],
                "entered_at": r["entered_at"],
                "completed_at": r["completed_at"],
                "duration_seconds": dur,
            })
        return result

    @staticmethod
    def get_guardrail_stats(conn: psycopg.Connection, project_id: UUID) -> dict[str, Any]:
        """Guardrail pass/fail rates across all outputs in the project.

        Returns:
            {
                "total_checks": int,
                "passed": int,
                "failed": int,
                "pass_rate": float | None,
                "by_rule": {rule_name: {"passed": int, "failed": int}, ...},
            }
        """
        rows = conn.execute(
            """
            SELECT gc.rule_name, gc.passed, COUNT(*) AS cnt
            FROM guardrail_checks gc
            JOIN agent_outputs ao ON gc.output_id = ao.id
            JOIN agent_runs ar ON ao.run_id = ar.id
            JOIN execution_nodes en ON ar.node_id = en.id
            JOIN execution_graphs eg ON en.graph_id = eg.id
            WHERE eg.project_id = %s
            GROUP BY gc.rule_name, gc.passed
            """,
            (project_id,),
        ).fetchall()

        total = 0
        passed = 0
        failed = 0
        by_rule: dict[str, dict[str, int]] = {}

        for r in rows:
            cnt = r["cnt"]
            total += cnt
            if r["passed"]:
                passed += cnt
            else:
                failed += cnt

            rule = r["rule_name"]
            if rule not in by_rule:
                by_rule[rule] = {"passed": 0, "failed": 0}
            if r["passed"]:
                by_rule[rule]["passed"] += cnt
            else:
                by_rule[rule]["failed"] += cnt

        return {
            "total_checks": total,
            "passed": passed,
            "failed": failed,
            "pass_rate": (passed / total) if total > 0 else None,
            "by_rule": by_rule,
        }

    @staticmethod
    def get_project_summary(conn: psycopg.Connection, project_id: UUID) -> dict[str, Any]:
        """Full project metrics summary combining all above.

        Returns:
            {
                "project_id": UUID,
                "token_usage": {...},
                "agent_velocity": {...},
                "phase_durations": [...],
                "guardrail_stats": {...},
            }
        """
        return {
            "project_id": project_id,
            "token_usage": ProjectMetrics.get_token_usage(conn, project_id),
            "agent_velocity": ProjectMetrics.get_agent_velocity(conn, project_id),
            "phase_durations": ProjectMetrics.get_phase_duration(conn, project_id),
            "guardrail_stats": ProjectMetrics.get_guardrail_stats(conn, project_id),
        }
