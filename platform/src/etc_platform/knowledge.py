"""Knowledge Graph — shared working memory with scoping, versioning, and conflict detection.

Provides CRUD operations on the knowledge_entries table. Agents contribute
knowledge entries scoped to project, phase, graph, or node. Entries are
versioned via a superseded_by chain, and conflicts (same key, different
contributors) can be detected and resolved.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import psycopg

VALID_SCOPES: set[str] = {"project", "phase", "graph", "node"}


def contribute_knowledge(
    conn: psycopg.Connection,
    project_id: UUID,
    key: str,
    value: Any,
    scope: str = "project",
    scope_id: UUID | None = None,
    contributed_by: UUID | None = None,
) -> UUID:
    """Insert a new knowledge entry, superseding any existing entry with the same key+scope+scope_id.

    Returns the new entry's UUID.
    """
    if scope not in VALID_SCOPES:
        raise ValueError(
            f"Invalid scope: {scope!r}. Must be one of {sorted(VALID_SCOPES)}"
        )

    # Insert the new entry
    row = conn.execute(
        """
        INSERT INTO knowledge_entries (project_id, scope, scope_id, key, value, contributed_by)
        VALUES (%s, %s, %s, %s, %s::jsonb, %s)
        RETURNING id
        """,
        (project_id, scope, scope_id, key, json.dumps(value), contributed_by),
    ).fetchone()
    assert row is not None
    new_id: UUID = row["id"]

    # Supersede any existing non-superseded entry with the same key+scope+scope_id
    if scope_id is None:
        conn.execute(
            """
            UPDATE knowledge_entries
            SET superseded_by = %s
            WHERE project_id = %s
              AND key = %s
              AND scope = %s
              AND scope_id IS NULL
              AND superseded_by IS NULL
              AND id != %s
            """,
            (new_id, project_id, key, scope, new_id),
        )
    else:
        conn.execute(
            """
            UPDATE knowledge_entries
            SET superseded_by = %s
            WHERE project_id = %s
              AND key = %s
              AND scope = %s
              AND scope_id = %s
              AND superseded_by IS NULL
              AND id != %s
            """,
            (new_id, project_id, key, scope, scope_id, new_id),
        )

    return new_id


def query_knowledge(
    conn: psycopg.Connection,
    project_id: UUID,
    key: str,
    scope: str | None = None,
    scope_id: UUID | None = None,
) -> dict[str, Any] | None:
    """Return the latest non-superseded entry for the given key, or None.

    Optionally filter by scope and/or scope_id.
    """
    query = (
        "SELECT * FROM knowledge_entries "
        "WHERE project_id = %s AND key = %s AND superseded_by IS NULL"
    )
    params: list[Any] = [project_id, key]

    if scope is not None:
        query += " AND scope = %s"
        params.append(scope)

    if scope_id is not None:
        query += " AND scope_id = %s"
        params.append(scope_id)

    query += " ORDER BY created_at DESC LIMIT 1"

    row = conn.execute(query, params).fetchone()
    if row is None:
        return None
    return dict(row)


def list_knowledge(
    conn: psycopg.Connection,
    project_id: UUID,
    scope: str | None = None,
    scope_id: UUID | None = None,
) -> list[dict[str, Any]]:
    """Return all non-superseded entries for the project, optionally filtered. Ordered by key."""
    query = (
        "SELECT * FROM knowledge_entries "
        "WHERE project_id = %s AND superseded_by IS NULL"
    )
    params: list[Any] = [project_id]

    if scope is not None:
        query += " AND scope = %s"
        params.append(scope)

    if scope_id is not None:
        query += " AND scope_id = %s"
        params.append(scope_id)

    query += " ORDER BY key"

    rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]


def get_knowledge_history(
    conn: psycopg.Connection,
    project_id: UUID,
    key: str,
) -> list[dict[str, Any]]:
    """Return all entries (including superseded) for a key, ordered by created_at descending."""
    rows = conn.execute(
        "SELECT * FROM knowledge_entries "
        "WHERE project_id = %s AND key = %s "
        "ORDER BY created_at DESC",
        (project_id, key),
    ).fetchall()
    return [dict(r) for r in rows]


def detect_conflicts(
    conn: psycopg.Connection,
    project_id: UUID,
) -> list[dict[str, Any]]:
    """Find keys where multiple non-superseded entries exist from different contributors.

    Returns a list of conflict dicts, each containing the key, the conflicting entries,
    and the number of distinct contributors.
    """
    # Find keys with multiple distinct non-null contributed_by values among non-superseded entries
    conflict_keys = conn.execute(
        """
        SELECT key, COUNT(DISTINCT contributed_by) AS contributor_count
        FROM knowledge_entries
        WHERE project_id = %s
          AND superseded_by IS NULL
          AND contributed_by IS NOT NULL
        GROUP BY key
        HAVING COUNT(DISTINCT contributed_by) > 1
        ORDER BY key
        """,
        (project_id,),
    ).fetchall()

    conflicts: list[dict[str, Any]] = []
    for ck in conflict_keys:
        entries = conn.execute(
            """
            SELECT * FROM knowledge_entries
            WHERE project_id = %s
              AND key = %s
              AND superseded_by IS NULL
            ORDER BY created_at
            """,
            (project_id, ck["key"]),
        ).fetchall()

        conflicts.append({
            "key": ck["key"],
            "entries": [dict(e) for e in entries],
            "contributor_count": ck["contributor_count"],
        })

    return conflicts


def resolve_conflict(
    conn: psycopg.Connection,
    winning_entry_id: UUID,
    losing_entry_ids: list[UUID],
) -> None:
    """Mark the losing entries as superseded by the winning entry."""
    for loser_id in losing_entry_ids:
        conn.execute(
            "UPDATE knowledge_entries SET superseded_by = %s WHERE id = %s",
            (winning_entry_id, loser_id),
        )


def delete_knowledge(
    conn: psycopg.Connection,
    entry_id: UUID,
) -> bool:
    """Delete a single knowledge entry. Returns True if deleted, False if not found."""
    result = conn.execute(
        "DELETE FROM knowledge_entries WHERE id = %s", (entry_id,)
    )
    return result.rowcount > 0
