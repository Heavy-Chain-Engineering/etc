"""Tests for Knowledge CLI commands — list, conflicts, resolve."""

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING

import psycopg
import pytest
from psycopg.rows import dict_row
from typer.testing import CliRunner

from etc_platform.cli import app

if TYPE_CHECKING:
    from uuid import UUID

runner = CliRunner()

# Point CLI commands at the test database
os.environ["ETC_DATABASE_URL"] = "postgresql://etc:etc_dev@localhost:5433/etc_platform_test"

PHASES = ["Bootstrap", "Spec", "Design", "Decompose", "Build", "Verify", "Ship", "Evaluate"]


@pytest.fixture
def project_with_knowledge(pg_dsn: str, setup_test_db: None):
    """Create a project with knowledge entries that CLI commands can see (committed)."""
    with psycopg.connect(pg_dsn, row_factory=dict_row) as conn:
        row = conn.execute(
            "INSERT INTO projects (name, root_path, classification) "
            "VALUES ('knowledge-proj', '/tmp', 'greenfield') RETURNING id"
        ).fetchone()
        assert row is not None
        project_id = row["id"]

        for phase in PHASES:
            conn.execute(
                "INSERT INTO phases (project_id, name, dod_items) VALUES (%s, %s, '[]')",
                (project_id, phase),
            )

        # Add some knowledge entries
        conn.execute(
            "INSERT INTO knowledge_entries (project_id, scope, key, value) "
            "VALUES (%s, 'project', 'entity:User', %s::jsonb)",
            (project_id, json.dumps({"fields": ["name", "email"]})),
        )
        conn.execute(
            "INSERT INTO knowledge_entries (project_id, scope, key, value) "
            "VALUES (%s, 'phase', 'design:pattern', %s::jsonb)",
            (project_id, json.dumps("repository")),
        )

        conn.commit()

    yield project_id

    # Cleanup
    with psycopg.connect(pg_dsn, row_factory=dict_row) as conn:
        conn.execute("DELETE FROM projects WHERE id = %s", (project_id,))
        conn.commit()


@pytest.fixture
def project_with_conflicts(pg_dsn: str, setup_test_db: None):
    """Create a project with conflicting knowledge entries from different contributors."""
    with psycopg.connect(pg_dsn, row_factory=dict_row) as conn:
        row = conn.execute(
            "INSERT INTO projects (name, root_path, classification) "
            "VALUES ('conflict-proj', '/tmp', 'greenfield') RETURNING id"
        ).fetchone()
        assert row is not None
        project_id = row["id"]

        for phase in PHASES:
            conn.execute(
                "INSERT INTO phases (project_id, name, dod_items) VALUES (%s, %s, '[]')",
                (project_id, phase),
            )

        # Create the FK chain needed for agent_runs (used as contributed_by)
        phase = conn.execute(
            "SELECT id FROM phases WHERE project_id = %s AND name = 'Build'",
            (project_id,),
        ).fetchone()
        assert phase is not None

        graph = conn.execute(
            "INSERT INTO execution_graphs (project_id, phase_id, name, status) "
            "VALUES (%s, %s, 'g', 'running') RETURNING id",
            (project_id, phase["id"]),
        ).fetchone()
        assert graph is not None

        node = conn.execute(
            "INSERT INTO execution_nodes (graph_id, node_type, name, status) "
            "VALUES (%s, 'leaf', 'n', 'running') RETURNING id",
            (graph["id"],),
        ).fetchone()
        assert node is not None

        run1 = conn.execute(
            "INSERT INTO agent_runs (node_id, agent_type, model, status) "
            "VALUES (%s, 'researcher', 'test', 'completed') RETURNING id",
            (node["id"],),
        ).fetchone()
        assert run1 is not None

        run2 = conn.execute(
            "INSERT INTO agent_runs (node_id, agent_type, model, status) "
            "VALUES (%s, 'designer', 'test', 'completed') RETURNING id",
            (node["id"],),
        ).fetchone()
        assert run2 is not None

        # Create conflicting entries: same key, different scope_ids, different contributors
        entry1 = conn.execute(
            "INSERT INTO knowledge_entries (project_id, scope, scope_id, key, value, contributed_by) "
            "VALUES (%s, 'node', %s, 'entity:VendorType', %s::jsonb, %s) RETURNING id",
            (project_id, run1["id"], json.dumps({"fields": ["a", "b"]}), run1["id"]),
        ).fetchone()
        assert entry1 is not None

        entry2 = conn.execute(
            "INSERT INTO knowledge_entries (project_id, scope, scope_id, key, value, contributed_by) "
            "VALUES (%s, 'node', %s, 'entity:VendorType', %s::jsonb, %s) RETURNING id",
            (project_id, run2["id"], json.dumps({"fields": ["x", "y"]}), run2["id"]),
        ).fetchone()
        assert entry2 is not None

        conn.commit()

    yield {
        "project_id": project_id,
        "entry1_id": entry1["id"],
        "entry2_id": entry2["id"],
        "run1_id": run1["id"],
        "run2_id": run2["id"],
    }

    # Cleanup
    with psycopg.connect(pg_dsn, row_factory=dict_row) as conn:
        conn.execute("DELETE FROM projects WHERE id = %s", (project_id,))
        conn.commit()


@pytest.fixture
def empty_project(pg_dsn: str, setup_test_db: None):
    """Create a project with no knowledge entries."""
    with psycopg.connect(pg_dsn, row_factory=dict_row) as conn:
        row = conn.execute(
            "INSERT INTO projects (name, root_path, classification) "
            "VALUES ('empty-knowledge-proj', '/tmp', 'greenfield') RETURNING id"
        ).fetchone()
        assert row is not None
        project_id = row["id"]

        for phase in PHASES:
            conn.execute(
                "INSERT INTO phases (project_id, name, dod_items) VALUES (%s, %s, '[]')",
                (project_id, phase),
            )
        conn.commit()

    yield project_id

    # Cleanup
    with psycopg.connect(pg_dsn, row_factory=dict_row) as conn:
        conn.execute("DELETE FROM projects WHERE id = %s", (project_id,))
        conn.commit()


# ============================================================================
# Command existence tests
# ============================================================================


class TestKnowledgeCommandExists:
    def test_knowledge_list_command_exists(self) -> None:
        result = runner.invoke(app, ["knowledge", "list", "--help"])
        assert result.exit_code == 0
        assert "No such command" not in (result.output or "")

    def test_knowledge_conflicts_command_exists(self) -> None:
        result = runner.invoke(app, ["knowledge", "conflicts", "--help"])
        assert result.exit_code == 0
        assert "No such command" not in (result.output or "")

    def test_knowledge_resolve_command_exists(self) -> None:
        result = runner.invoke(app, ["knowledge", "resolve", "--help"])
        assert result.exit_code == 0
        assert "No such command" not in (result.output or "")


# ============================================================================
# knowledge list
# ============================================================================


class TestKnowledgeList:
    def test_list_shows_entries(self, project_with_knowledge: UUID) -> None:
        result = runner.invoke(app, ["knowledge", "list"])
        assert result.exit_code == 0
        assert "entity:User" in result.output
        assert "design:pattern" in result.output

    def test_list_shows_scope(self, project_with_knowledge: UUID) -> None:
        result = runner.invoke(app, ["knowledge", "list"])
        assert result.exit_code == 0
        assert "project" in result.output.lower()

    def test_list_empty_project(self, empty_project: UUID) -> None:
        result = runner.invoke(app, ["knowledge", "list"])
        assert result.exit_code == 0
        assert "no knowledge" in result.output.lower() or "empty" in result.output.lower()

    def test_list_no_active_project(self, setup_test_db: None, pg_dsn: str) -> None:
        # Clean out all projects first
        with psycopg.connect(pg_dsn, row_factory=dict_row) as conn:
            conn.execute("DELETE FROM projects")
            conn.commit()
        try:
            result = runner.invoke(app, ["knowledge", "list"])
            assert result.exit_code == 0
            assert "no active project" in result.output.lower()
        finally:
            pass


# ============================================================================
# knowledge conflicts
# ============================================================================


class TestKnowledgeConflicts:
    def test_conflicts_shows_conflicts(self, project_with_conflicts: dict) -> None:
        result = runner.invoke(app, ["knowledge", "conflicts"])
        assert result.exit_code == 0
        assert "entity:VendorType" in result.output

    def test_conflicts_shows_contributor_count(self, project_with_conflicts: dict) -> None:
        result = runner.invoke(app, ["knowledge", "conflicts"])
        assert result.exit_code == 0
        # Should show the two competing entries
        assert "2" in result.output

    def test_no_conflicts(self, project_with_knowledge: UUID) -> None:
        result = runner.invoke(app, ["knowledge", "conflicts"])
        assert result.exit_code == 0
        assert "no unresolved conflicts" in result.output.lower()

    def test_conflicts_no_active_project(self, setup_test_db: None, pg_dsn: str) -> None:
        with psycopg.connect(pg_dsn, row_factory=dict_row) as conn:
            conn.execute("DELETE FROM projects")
            conn.commit()
        try:
            result = runner.invoke(app, ["knowledge", "conflicts"])
            assert result.exit_code == 0
            assert "no active project" in result.output.lower()
        finally:
            pass


# ============================================================================
# knowledge resolve
# ============================================================================


class TestKnowledgeResolve:
    def test_resolve_marks_loser(self, project_with_conflicts: dict, pg_dsn: str) -> None:
        winner_id = str(project_with_conflicts["entry1_id"])
        result = runner.invoke(
            app, ["knowledge", "resolve", "entity:VendorType", winner_id]
        )
        assert result.exit_code == 0
        assert "resolved" in result.output.lower()

        # Verify the loser is superseded in DB
        with psycopg.connect(pg_dsn, row_factory=dict_row) as conn:
            loser = conn.execute(
                "SELECT superseded_by FROM knowledge_entries WHERE id = %s",
                (project_with_conflicts["entry2_id"],),
            ).fetchone()
            assert loser is not None
            assert loser["superseded_by"] == project_with_conflicts["entry1_id"]

    def test_resolve_winner_remains_active(self, project_with_conflicts: dict, pg_dsn: str) -> None:
        winner_id = str(project_with_conflicts["entry1_id"])
        result = runner.invoke(
            app, ["knowledge", "resolve", "entity:VendorType", winner_id]
        )
        assert result.exit_code == 0

        # Winner should not be superseded
        with psycopg.connect(pg_dsn, row_factory=dict_row) as conn:
            winner = conn.execute(
                "SELECT superseded_by FROM knowledge_entries WHERE id = %s",
                (project_with_conflicts["entry1_id"],),
            ).fetchone()
            assert winner is not None
            assert winner["superseded_by"] is None

    def test_resolve_emits_event(self, project_with_conflicts: dict, pg_dsn: str) -> None:
        winner_id = str(project_with_conflicts["entry1_id"])
        result = runner.invoke(
            app, ["knowledge", "resolve", "entity:VendorType", winner_id]
        )
        assert result.exit_code == 0

        # Verify an event was emitted
        with psycopg.connect(pg_dsn, row_factory=dict_row) as conn:
            event = conn.execute(
                "SELECT * FROM events WHERE project_id = %s AND event_type = 'human_response' "
                "ORDER BY created_at DESC LIMIT 1",
                (project_with_conflicts["project_id"],),
            ).fetchone()
            assert event is not None
            assert "knowledge_conflict_resolved" in (event["payload"].get("action", "") if event["payload"] else "")

    def test_resolve_invalid_uuid(self, project_with_conflicts: dict) -> None:
        result = runner.invoke(
            app, ["knowledge", "resolve", "entity:VendorType", "not-a-uuid"]
        )
        assert result.exit_code != 0 or "invalid" in result.output.lower()

    def test_resolve_no_conflict_for_key(self, project_with_knowledge: UUID) -> None:
        # entity:User has no conflict in project_with_knowledge
        result = runner.invoke(
            app, ["knowledge", "resolve", "entity:User", "00000000-0000-0000-0000-000000000000"]
        )
        # Should indicate no conflict found
        assert "no conflict" in result.output.lower() or result.exit_code != 0

    def test_resolve_no_active_project(self, setup_test_db: None, pg_dsn: str) -> None:
        with psycopg.connect(pg_dsn, row_factory=dict_row) as conn:
            conn.execute("DELETE FROM projects")
            conn.commit()
        try:
            result = runner.invoke(
                app, ["knowledge", "resolve", "some-key", "00000000-0000-0000-0000-000000000000"]
            )
            assert result.exit_code == 0
            assert "no active project" in result.output.lower()
        finally:
            pass
