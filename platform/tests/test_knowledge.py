"""Tests for Knowledge Graph — shared working memory with scoping, versioning, and conflict detection."""

from __future__ import annotations

from uuid import UUID

import psycopg
import pytest

from etc_platform.knowledge import (
    VALID_SCOPES,
    contribute_knowledge,
    delete_knowledge,
    detect_conflicts,
    get_knowledge_history,
    list_knowledge,
    query_knowledge,
    resolve_conflict,
)


def _create_project(db: psycopg.Connection) -> UUID:
    """Helper: insert a project and return its id."""
    row = db.execute(
        "INSERT INTO projects (name, root_path, classification) "
        "VALUES ('p', '/tmp', 'greenfield') RETURNING id"
    ).fetchone()
    assert row is not None
    return row["id"]


def _create_two_agent_runs(db: psycopg.Connection, project_id: UUID) -> tuple[UUID, UUID]:
    """Helper: create the required FK chain and return two distinct agent_run ids."""
    phase = db.execute(
        "INSERT INTO phases (project_id, name) VALUES (%s, 'Build') RETURNING id",
        (project_id,),
    ).fetchone()
    assert phase is not None

    graph = db.execute(
        "INSERT INTO execution_graphs (project_id, phase_id, name, status) "
        "VALUES (%s, %s, 'g', 'running') RETURNING id",
        (project_id, phase["id"]),
    ).fetchone()
    assert graph is not None

    node = db.execute(
        "INSERT INTO execution_nodes (graph_id, node_type, name, status) "
        "VALUES (%s, 'leaf', 'n', 'running') RETURNING id",
        (graph["id"],),
    ).fetchone()
    assert node is not None

    run1 = db.execute(
        "INSERT INTO agent_runs (node_id, agent_type, model, status) "
        "VALUES (%s, 'researcher', 'test', 'completed') RETURNING id",
        (node["id"],),
    ).fetchone()
    assert run1 is not None

    run2 = db.execute(
        "INSERT INTO agent_runs (node_id, agent_type, model, status) "
        "VALUES (%s, 'researcher', 'test', 'completed') RETURNING id",
        (node["id"],),
    ).fetchone()
    assert run2 is not None

    return run1["id"], run2["id"]


class TestValidScopes:
    def test_valid_scopes_set(self) -> None:
        """VALID_SCOPES contains the four allowed scope values."""
        assert VALID_SCOPES == {"project", "phase", "graph", "node"}


class TestContributeKnowledge:
    def test_creates_entry(self, db: psycopg.Connection) -> None:
        """contribute_knowledge inserts a row into knowledge_entries."""
        pid = _create_project(db)
        contribute_knowledge(db, pid, "entity:User", {"fields": ["name", "email"]})

        row = db.execute(
            "SELECT * FROM knowledge_entries WHERE project_id = %s AND key = 'entity:User'",
            (pid,),
        ).fetchone()
        assert row is not None
        assert row["value"] == {"fields": ["name", "email"]}
        assert row["scope"] == "project"
        assert row["scope_id"] is None
        assert row["contributed_by"] is None
        assert row["superseded_by"] is None

    def test_returns_uuid(self, db: psycopg.Connection) -> None:
        """contribute_knowledge returns the new entry's UUID."""
        pid = _create_project(db)
        entry_id = contribute_knowledge(db, pid, "entity:User", {"fields": ["name"]})
        assert isinstance(entry_id, UUID)

        row = db.execute(
            "SELECT id FROM knowledge_entries WHERE id = %s", (entry_id,)
        ).fetchone()
        assert row is not None

    def test_supersedes_existing(self, db: psycopg.Connection) -> None:
        """Contributing with same key+scope+scope_id supersedes the old entry."""
        pid = _create_project(db)
        old_id = contribute_knowledge(db, pid, "entity:User", {"version": 1})
        new_id = contribute_knowledge(db, pid, "entity:User", {"version": 2})

        assert old_id != new_id

        # Old entry should be marked as superseded by new
        old = db.execute(
            "SELECT superseded_by FROM knowledge_entries WHERE id = %s", (old_id,)
        ).fetchone()
        assert old is not None
        assert old["superseded_by"] == new_id

        # New entry should NOT be superseded
        new = db.execute(
            "SELECT superseded_by FROM knowledge_entries WHERE id = %s", (new_id,)
        ).fetchone()
        assert new is not None
        assert new["superseded_by"] is None

    def test_different_keys_not_superseded(self, db: psycopg.Connection) -> None:
        """Entries with different keys are not superseded."""
        pid = _create_project(db)
        id1 = contribute_knowledge(db, pid, "entity:User", {"v": 1})
        id2 = contribute_knowledge(db, pid, "entity:Order", {"v": 1})

        row1 = db.execute(
            "SELECT superseded_by FROM knowledge_entries WHERE id = %s", (id1,)
        ).fetchone()
        assert row1 is not None
        assert row1["superseded_by"] is None

        row2 = db.execute(
            "SELECT superseded_by FROM knowledge_entries WHERE id = %s", (id2,)
        ).fetchone()
        assert row2 is not None
        assert row2["superseded_by"] is None

    def test_different_scopes_not_superseded(self, db: psycopg.Connection) -> None:
        """Same key with different scopes are not superseded."""
        pid = _create_project(db)
        id1 = contribute_knowledge(db, pid, "entity:User", {"v": 1}, scope="project")
        id2 = contribute_knowledge(db, pid, "entity:User", {"v": 2}, scope="phase")

        row1 = db.execute(
            "SELECT superseded_by FROM knowledge_entries WHERE id = %s", (id1,)
        ).fetchone()
        assert row1 is not None
        assert row1["superseded_by"] is None

    def test_invalid_scope_raises(self, db: psycopg.Connection) -> None:
        """contribute_knowledge raises ValueError for an invalid scope."""
        pid = _create_project(db)
        with pytest.raises(ValueError, match="Invalid scope"):
            contribute_knowledge(db, pid, "entity:User", {"v": 1}, scope="invalid")


class TestQueryKnowledge:
    def test_returns_latest(self, db: psycopg.Connection) -> None:
        """query_knowledge returns the latest non-superseded entry."""
        pid = _create_project(db)
        contribute_knowledge(db, pid, "entity:User", {"version": 1})
        new_id = contribute_knowledge(db, pid, "entity:User", {"version": 2})

        result = query_knowledge(db, pid, "entity:User")
        assert result is not None
        assert result["id"] == new_id
        assert result["value"] == {"version": 2}

    def test_excludes_superseded(self, db: psycopg.Connection) -> None:
        """query_knowledge does not return superseded entries."""
        pid = _create_project(db)
        old_id = contribute_knowledge(db, pid, "entity:User", {"version": 1})
        contribute_knowledge(db, pid, "entity:User", {"version": 2})

        result = query_knowledge(db, pid, "entity:User")
        assert result is not None
        assert result["id"] != old_id

    def test_returns_none_for_missing(self, db: psycopg.Connection) -> None:
        """query_knowledge returns None when no matching key exists."""
        pid = _create_project(db)
        result = query_knowledge(db, pid, "nonexistent")
        assert result is None

    def test_filters_by_scope(self, db: psycopg.Connection) -> None:
        """query_knowledge filters by scope when specified."""
        pid = _create_project(db)
        contribute_knowledge(db, pid, "entity:User", {"scope": "project"}, scope="project")
        contribute_knowledge(db, pid, "entity:User", {"scope": "phase"}, scope="phase")

        result = query_knowledge(db, pid, "entity:User", scope="phase")
        assert result is not None
        assert result["value"] == {"scope": "phase"}
        assert result["scope"] == "phase"

    def test_filters_by_scope_id(self, db: psycopg.Connection) -> None:
        """query_knowledge filters by scope_id when specified."""
        pid = _create_project(db)
        run1_id, run2_id = _create_two_agent_runs(db, pid)

        # Use run UUIDs as scope_ids for distinct scoping
        contribute_knowledge(
            db, pid, "entity:User", {"for": "scope1"}, scope="node", scope_id=run1_id
        )
        contribute_knowledge(
            db, pid, "entity:User", {"for": "scope2"}, scope="node", scope_id=run2_id
        )

        result = query_knowledge(db, pid, "entity:User", scope="node", scope_id=run1_id)
        assert result is not None
        assert result["value"] == {"for": "scope1"}


class TestListKnowledge:
    def test_lists_non_superseded(self, db: psycopg.Connection) -> None:
        """list_knowledge returns only non-superseded entries."""
        pid = _create_project(db)
        contribute_knowledge(db, pid, "entity:User", {"version": 1})
        contribute_knowledge(db, pid, "entity:User", {"version": 2})
        contribute_knowledge(db, pid, "entity:Order", {"version": 1})

        results = list_knowledge(db, pid)
        assert len(results) == 2
        keys = [r["key"] for r in results]
        assert "entity:User" in keys
        assert "entity:Order" in keys

    def test_filters_by_scope(self, db: psycopg.Connection) -> None:
        """list_knowledge filters by scope when specified."""
        pid = _create_project(db)
        contribute_knowledge(db, pid, "entity:User", {"v": 1}, scope="project")
        contribute_knowledge(db, pid, "entity:Order", {"v": 1}, scope="phase")

        results = list_knowledge(db, pid, scope="phase")
        assert len(results) == 1
        assert results[0]["key"] == "entity:Order"

    def test_empty_project(self, db: psycopg.Connection) -> None:
        """list_knowledge returns empty list for a project with no entries."""
        pid = _create_project(db)
        results = list_knowledge(db, pid)
        assert results == []

    def test_ordered_by_key(self, db: psycopg.Connection) -> None:
        """list_knowledge returns entries ordered by key."""
        pid = _create_project(db)
        contribute_knowledge(db, pid, "z:last", {"v": 1})
        contribute_knowledge(db, pid, "a:first", {"v": 1})
        contribute_knowledge(db, pid, "m:middle", {"v": 1})

        results = list_knowledge(db, pid)
        keys = [r["key"] for r in results]
        assert keys == ["a:first", "m:middle", "z:last"]


class TestGetKnowledgeHistory:
    def test_shows_all_versions(self, db: psycopg.Connection) -> None:
        """get_knowledge_history returns all entries for a key, including superseded."""
        pid = _create_project(db)
        contribute_knowledge(db, pid, "entity:User", {"version": 1})
        contribute_knowledge(db, pid, "entity:User", {"version": 2})
        contribute_knowledge(db, pid, "entity:User", {"version": 3})

        history = get_knowledge_history(db, pid, "entity:User")
        assert len(history) == 3
        versions = [h["value"]["version"] for h in history]
        # All three versions should appear
        assert set(versions) == {1, 2, 3}

    def test_ordered_by_created_desc(self, db: psycopg.Connection) -> None:
        """get_knowledge_history returns entries ordered by created_at descending (newest first)."""
        pid = _create_project(db)
        # Insert with explicit timestamps to guarantee ordering
        # (now() returns the same value within a transaction)
        id1 = db.execute(
            "INSERT INTO knowledge_entries (project_id, scope, key, value, created_at) "
            "VALUES (%s, 'project', 'entity:User', %s::jsonb, '2025-01-01T00:00:00Z') RETURNING id",
            (pid, '{"version": 1}'),
        ).fetchone()
        assert id1 is not None
        id2 = db.execute(
            "INSERT INTO knowledge_entries (project_id, scope, key, value, created_at) "
            "VALUES (%s, 'project', 'entity:User', %s::jsonb, '2025-01-02T00:00:00Z') RETURNING id",
            (pid, '{"version": 2}'),
        ).fetchone()
        assert id2 is not None

        history = get_knowledge_history(db, pid, "entity:User")
        assert len(history) == 2
        # Newest first
        assert history[0]["value"]["version"] == 2
        assert history[1]["value"]["version"] == 1


class TestDetectConflicts:
    def test_no_conflicts(self, db: psycopg.Connection) -> None:
        """detect_conflicts returns empty list when no conflicts exist."""
        pid = _create_project(db)
        contribute_knowledge(db, pid, "entity:User", {"v": 1})
        contribute_knowledge(db, pid, "entity:Order", {"v": 1})

        conflicts = detect_conflicts(db, pid)
        assert conflicts == []

    def test_detects_multi_contributor_conflict(self, db: psycopg.Connection) -> None:
        """detect_conflicts finds keys with multiple non-superseded entries from different contributors."""
        pid = _create_project(db)
        run1_id, run2_id = _create_two_agent_runs(db, pid)

        # Two different contributors write the same key (different scopes would not conflict,
        # but same key at same scope with different contributors does)
        contribute_knowledge(
            db, pid, "entity:VendorType", {"fields": ["a"]}, contributed_by=run1_id
        )
        contribute_knowledge(
            db, pid, "entity:VendorType", {"fields": ["b"]}, contributed_by=run2_id
        )

        # These are both non-superseded because they have different contributed_by,
        # so supersede logic (same key+scope+scope_id) would match... but the requirement
        # says "if an entry with the same key+scope+scope_id already exists (and isn't superseded),
        # mark the old one as superseded_by the new one". So we need to create a scenario
        # where multiple non-superseded entries exist. Let's use different scope_ids.
        # Actually re-reading: contribute_knowledge supersedes by key+scope+scope_id,
        # not by contributor. So two entries with same key+scope+scope_id but different
        # contributors would result in the first being superseded. To get a conflict,
        # we need entries with the same key but different scope or scope_id.

        # Let me re-do: use different scope_ids so they're not superseded
        db.execute("DELETE FROM knowledge_entries WHERE project_id = %s", (pid,))

        contribute_knowledge(
            db, pid, "entity:VendorType", {"fields": ["a"]},
            scope="node", scope_id=run1_id, contributed_by=run1_id,
        )
        contribute_knowledge(
            db, pid, "entity:VendorType", {"fields": ["b"]},
            scope="node", scope_id=run2_id, contributed_by=run2_id,
        )

        conflicts = detect_conflicts(db, pid)
        assert len(conflicts) == 1
        assert conflicts[0]["key"] == "entity:VendorType"
        assert conflicts[0]["contributor_count"] == 2
        assert len(conflicts[0]["entries"]) == 2

    def test_same_contributor_no_conflict(self, db: psycopg.Connection) -> None:
        """Same contributor with multiple entries for the same key is not a conflict."""
        pid = _create_project(db)
        run1_id, _ = _create_two_agent_runs(db, pid)

        # Same contributor, different scope_ids (so neither superseded)
        contribute_knowledge(
            db, pid, "entity:VendorType", {"fields": ["a"]},
            scope="node", scope_id=run1_id, contributed_by=run1_id,
        )
        contribute_knowledge(
            db, pid, "entity:VendorType", {"fields": ["b"]},
            scope="phase", contributed_by=run1_id,
        )

        conflicts = detect_conflicts(db, pid)
        assert conflicts == []


class TestResolveConflict:
    def test_marks_losers_superseded(self, db: psycopg.Connection) -> None:
        """resolve_conflict marks losing entries as superseded_by the winner."""
        pid = _create_project(db)
        run1_id, run2_id = _create_two_agent_runs(db, pid)

        id1 = contribute_knowledge(
            db, pid, "entity:VendorType", {"fields": ["a"]},
            scope="node", scope_id=run1_id, contributed_by=run1_id,
        )
        id2 = contribute_knowledge(
            db, pid, "entity:VendorType", {"fields": ["b"]},
            scope="node", scope_id=run2_id, contributed_by=run2_id,
        )

        resolve_conflict(db, winning_entry_id=id1, losing_entry_ids=[id2])

        loser = db.execute(
            "SELECT superseded_by FROM knowledge_entries WHERE id = %s", (id2,)
        ).fetchone()
        assert loser is not None
        assert loser["superseded_by"] == id1

    def test_winner_remains_active(self, db: psycopg.Connection) -> None:
        """resolve_conflict does not supersede the winning entry."""
        pid = _create_project(db)
        run1_id, run2_id = _create_two_agent_runs(db, pid)

        id1 = contribute_knowledge(
            db, pid, "entity:VendorType", {"fields": ["a"]},
            scope="node", scope_id=run1_id, contributed_by=run1_id,
        )
        id2 = contribute_knowledge(
            db, pid, "entity:VendorType", {"fields": ["b"]},
            scope="node", scope_id=run2_id, contributed_by=run2_id,
        )

        resolve_conflict(db, winning_entry_id=id1, losing_entry_ids=[id2])

        winner = db.execute(
            "SELECT superseded_by FROM knowledge_entries WHERE id = %s", (id1,)
        ).fetchone()
        assert winner is not None
        assert winner["superseded_by"] is None


class TestDeleteKnowledge:
    def test_deletes_entry(self, db: psycopg.Connection) -> None:
        """delete_knowledge removes the entry and returns True."""
        pid = _create_project(db)
        entry_id = contribute_knowledge(db, pid, "entity:User", {"v": 1})

        result = delete_knowledge(db, entry_id)
        assert result is True

        row = db.execute(
            "SELECT id FROM knowledge_entries WHERE id = %s", (entry_id,)
        ).fetchone()
        assert row is None

    def test_missing_returns_false(self, db: psycopg.Connection) -> None:
        """delete_knowledge returns False when the entry does not exist."""
        from uuid import uuid4

        result = delete_knowledge(db, uuid4())
        assert result is False
