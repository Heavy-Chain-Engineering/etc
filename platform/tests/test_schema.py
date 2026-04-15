"""Tests for database schema — verifies all tables, columns, constraints, and indexes exist."""

from __future__ import annotations

import psycopg
import pytest

EXPECTED_TABLES = [
    "projects",
    "source_materials",
    "phases",
    "phase_transitions",
    "execution_graphs",
    "execution_nodes",
    "execution_node_dependencies",
    "agent_runs",
    "agent_outputs",
    "guardrail_checks",
    "events",
    "knowledge_entries",
]


class TestSchemaExists:
    def test_all_tables_exist(self, db: psycopg.Connection) -> None:
        result = db.execute(
            """
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
            ORDER BY table_name
            """
        ).fetchall()
        tables = [r["table_name"] for r in result]
        for expected in EXPECTED_TABLES:
            assert expected in tables, f"Table '{expected}' missing from schema"

    def test_table_count(self, db: psycopg.Connection) -> None:
        result = db.execute(
            """
            SELECT count(*) as cnt FROM information_schema.tables
            WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
            """
        ).fetchone()
        assert result is not None
        assert result["cnt"] == len(EXPECTED_TABLES)


class TestProjectsTable:
    def test_insert_project(self, db: psycopg.Connection) -> None:
        row = db.execute(
            """
            INSERT INTO projects (name, root_path, classification)
            VALUES ('test-project', '/tmp/test', 'greenfield')
            RETURNING id, name, status, created_at
            """
        ).fetchone()
        assert row is not None
        assert row["name"] == "test-project"
        assert row["status"] == "active"
        assert row["created_at"] is not None

    def test_classification_check_constraint(self, db: psycopg.Connection) -> None:
        with pytest.raises(psycopg.errors.CheckViolation):
            db.execute(
                """
                INSERT INTO projects (name, root_path, classification)
                VALUES ('bad', '/tmp', 'invalid_type')
                """
            )

    def test_status_check_constraint(self, db: psycopg.Connection) -> None:
        with pytest.raises(psycopg.errors.CheckViolation):
            db.execute(
                """
                INSERT INTO projects (name, root_path, classification, status)
                VALUES ('bad', '/tmp', 'greenfield', 'bogus')
                """
            )


class TestPhasesTable:
    def test_insert_all_phases(self, db: psycopg.Connection) -> None:
        project = db.execute(
            "INSERT INTO projects (name, root_path, classification) VALUES ('p', '/tmp', 'greenfield') RETURNING id"
        ).fetchone()
        assert project is not None
        pid = project["id"]

        phases = ["Bootstrap", "Spec", "Design", "Decompose", "Build", "Verify", "Ship", "Evaluate"]
        for phase in phases:
            db.execute(
                "INSERT INTO phases (project_id, name, dod_items) VALUES (%s, %s, '[]')",
                (pid, phase),
            )

        result = db.execute(
            "SELECT count(*) as cnt FROM phases WHERE project_id = %s", (pid,)
        ).fetchone()
        assert result is not None
        assert result["cnt"] == 8

    def test_phase_unique_per_project(self, db: psycopg.Connection) -> None:
        project = db.execute(
            "INSERT INTO projects (name, root_path, classification) VALUES ('p', '/tmp', 'greenfield') RETURNING id"
        ).fetchone()
        assert project is not None
        pid = project["id"]

        db.execute("INSERT INTO phases (project_id, name, dod_items) VALUES (%s, 'Build', '[]')", (pid,))
        with pytest.raises(psycopg.errors.UniqueViolation):
            db.execute("INSERT INTO phases (project_id, name, dod_items) VALUES (%s, 'Build', '[]')", (pid,))

    def test_invalid_phase_name(self, db: psycopg.Connection) -> None:
        project = db.execute(
            "INSERT INTO projects (name, root_path, classification) VALUES ('p', '/tmp', 'greenfield') RETURNING id"
        ).fetchone()
        assert project is not None
        with pytest.raises(psycopg.errors.CheckViolation):
            db.execute(
                "INSERT INTO phases (project_id, name, dod_items) VALUES (%s, 'InvalidPhase', '[]')",
                (project["id"],),
            )


class TestExecutionNodes:
    def _setup_graph(self, db: psycopg.Connection) -> tuple:
        project = db.execute(
            "INSERT INTO projects (name, root_path, classification) VALUES ('p', '/tmp', 'greenfield') RETURNING id"
        ).fetchone()
        assert project is not None
        pid = project["id"]

        phase = db.execute(
            "INSERT INTO phases (project_id, name, dod_items) VALUES (%s, 'Build', '[]') RETURNING id",
            (pid,),
        ).fetchone()
        assert phase is not None

        graph = db.execute(
            "INSERT INTO execution_graphs (project_id, phase_id, name) VALUES (%s, %s, 'test-graph') RETURNING id",
            (pid, phase["id"]),
        ).fetchone()
        assert graph is not None

        return pid, phase["id"], graph["id"]

    def test_leaf_node(self, db: psycopg.Connection) -> None:
        _, _, gid = self._setup_graph(db)
        node = db.execute(
            """
            INSERT INTO execution_nodes (graph_id, node_type, name, agent_type, depth)
            VALUES (%s, 'leaf', 'research-agent-1', 'researcher', 0)
            RETURNING id, status
            """,
            (gid,),
        ).fetchone()
        assert node is not None
        assert node["status"] == "pending"

    def test_node_dependencies(self, db: psycopg.Connection) -> None:
        _, _, gid = self._setup_graph(db)
        n1 = db.execute(
            "INSERT INTO execution_nodes (graph_id, node_type, name, depth) VALUES (%s, 'leaf', 'n1', 0) RETURNING id",
            (gid,),
        ).fetchone()
        n2 = db.execute(
            "INSERT INTO execution_nodes (graph_id, node_type, name, depth) VALUES (%s, 'reduce', 'n2', 0) RETURNING id",
            (gid,),
        ).fetchone()
        assert n1 is not None and n2 is not None

        db.execute(
            "INSERT INTO execution_node_dependencies (node_id, depends_on_node_id) VALUES (%s, %s)",
            (n2["id"], n1["id"]),
        )

        deps = db.execute(
            "SELECT depends_on_node_id FROM execution_node_dependencies WHERE node_id = %s",
            (n2["id"],),
        ).fetchall()
        assert len(deps) == 1
        assert deps[0]["depends_on_node_id"] == n1["id"]

    def test_composite_node_with_children(self, db: psycopg.Connection) -> None:
        _, _, gid = self._setup_graph(db)
        parent = db.execute(
            "INSERT INTO execution_nodes (graph_id, node_type, name, depth) VALUES (%s, 'composite', 'layer-1', 0) RETURNING id",
            (gid,),
        ).fetchone()
        assert parent is not None

        for i in range(3):
            db.execute(
                "INSERT INTO execution_nodes (graph_id, parent_node_id, node_type, name, depth) VALUES (%s, %s, 'leaf', %s, 1)",
                (gid, parent["id"], f"child-{i}"),
            )

        children = db.execute(
            "SELECT count(*) as cnt FROM execution_nodes WHERE parent_node_id = %s",
            (parent["id"],),
        ).fetchone()
        assert children is not None
        assert children["cnt"] == 3


class TestEventsAndNotify:
    def test_insert_event(self, db: psycopg.Connection) -> None:
        project = db.execute(
            "INSERT INTO projects (name, root_path, classification) VALUES ('p', '/tmp', 'greenfield') RETURNING id"
        ).fetchone()
        assert project is not None

        event = db.execute(
            """
            INSERT INTO events (project_id, event_type, actor, payload)
            VALUES (%s, 'agent_completed', 'system', '{"node_id": "abc"}')
            RETURNING id, created_at
            """,
            (project["id"],),
        ).fetchone()
        assert event is not None
        assert event["created_at"] is not None

    def test_notify_trigger_exists(self, db: psycopg.Connection) -> None:
        result = db.execute(
            """
            SELECT trigger_name FROM information_schema.triggers
            WHERE event_object_table = 'events' AND trigger_name = 'events_notify'
            """
        ).fetchone()
        assert result is not None


class TestKnowledgeEntries:
    def test_scoped_knowledge(self, db: psycopg.Connection) -> None:
        project = db.execute(
            "INSERT INTO projects (name, root_path, classification) VALUES ('p', '/tmp', 'greenfield') RETURNING id"
        ).fetchone()
        assert project is not None

        entry = db.execute(
            """
            INSERT INTO knowledge_entries (project_id, scope, key, value)
            VALUES (%s, 'project', 'entity:VendorType', '{"fields": ["name", "type"]}')
            RETURNING id
            """,
            (project["id"],),
        ).fetchone()
        assert entry is not None

    def test_knowledge_superseding(self, db: psycopg.Connection) -> None:
        project = db.execute(
            "INSERT INTO projects (name, root_path, classification) VALUES ('p', '/tmp', 'greenfield') RETURNING id"
        ).fetchone()
        assert project is not None
        pid = project["id"]

        v1 = db.execute(
            "INSERT INTO knowledge_entries (project_id, scope, key, value) VALUES (%s, 'project', 'k', '\"v1\"') RETURNING id",
            (pid,),
        ).fetchone()
        v2 = db.execute(
            "INSERT INTO knowledge_entries (project_id, scope, key, value) VALUES (%s, 'project', 'k', '\"v2\"') RETURNING id",
            (pid,),
        ).fetchone()
        assert v1 is not None and v2 is not None

        db.execute(
            "UPDATE knowledge_entries SET superseded_by = %s WHERE id = %s",
            (v2["id"], v1["id"]),
        )

        current = db.execute(
            "SELECT value FROM knowledge_entries WHERE project_id = %s AND key = 'k' AND superseded_by IS NULL",
            (pid,),
        ).fetchone()
        assert current is not None
        assert current["value"] == "v2"


class TestCascadeDeletes:
    def test_delete_project_cascades(self, db: psycopg.Connection) -> None:
        project = db.execute(
            "INSERT INTO projects (name, root_path, classification) VALUES ('p', '/tmp', 'greenfield') RETURNING id"
        ).fetchone()
        assert project is not None
        pid = project["id"]

        db.execute("INSERT INTO phases (project_id, name, dod_items) VALUES (%s, 'Build', '[]')", (pid,))
        db.execute(
            "INSERT INTO events (project_id, event_type, actor) VALUES (%s, 'test', 'system')",
            (pid,),
        )
        db.execute(
            "INSERT INTO source_materials (project_id, name, type, classification, priority) VALUES (%s, 'doc', 'pdf', 'requirements', 'primary')",
            (pid,),
        )

        db.execute("DELETE FROM projects WHERE id = %s", (pid,))

        for table in ["phases", "events", "source_materials"]:
            result = db.execute(
                f"SELECT count(*) as cnt FROM {table} WHERE project_id = %s", (pid,)
            ).fetchone()
            assert result is not None
            assert result["cnt"] == 0, f"Cascade delete failed for {table}"
