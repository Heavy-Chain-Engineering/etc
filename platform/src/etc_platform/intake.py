"""Source material intake — CRUD and triage for project source materials."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from uuid import UUID

    import psycopg

VALID_TYPES: set[str] = {"pdf", "code", "export", "spreadsheet", "document"}

VALID_CLASSIFICATIONS: set[str] = {
    "business_operations",
    "requirements",
    "implementation_artifact",
    "domain_truth",
}

VALID_PRIORITIES: set[str] = {"primary", "high", "medium", "context_only"}

# Ordering used for list queries: primary first, context_only last.
_PRIORITY_ORDER = ("primary", "high", "medium", "context_only")


def _validate_field(field_name: str, value: str, valid_values: set[str]) -> None:
    """Raise ValueError if value is not in the allowed set."""
    if value not in valid_values:
        raise ValueError(
            f"Invalid {field_name}: {value!r}. Must be one of {sorted(valid_values)}"
        )


def add_source_material(
    conn: psycopg.Connection,
    project_id: UUID,
    name: str,
    type: str,
    classification: str,
    priority: str,
    path: str | None = None,
    reading_instructions: str | None = None,
) -> UUID:
    """Insert a source material and return its id.

    Validates type, classification, and priority before inserting.
    Raises ValueError for invalid values.
    """
    _validate_field("type", type, VALID_TYPES)
    _validate_field("classification", classification, VALID_CLASSIFICATIONS)
    _validate_field("priority", priority, VALID_PRIORITIES)

    row = conn.execute(
        """
        INSERT INTO source_materials
            (project_id, name, type, classification, priority, path, reading_instructions)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (project_id, name, type, classification, priority, path, reading_instructions),
    ).fetchone()
    assert row is not None
    return row["id"]


def list_source_materials(conn: psycopg.Connection, project_id: UUID) -> list[dict[str, Any]]:
    """Return all source materials for a project, ordered by priority.

    Priority order: primary, high, medium, context_only.
    """
    rows = conn.execute(
        """
        SELECT *
        FROM source_materials
        WHERE project_id = %s
        ORDER BY array_position(ARRAY['primary','high','medium','context_only'], priority),
                 created_at
        """,
        (project_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_source_material(conn: psycopg.Connection, material_id: UUID) -> dict[str, Any] | None:
    """Return a single source material by id, or None if not found."""
    row = conn.execute(
        "SELECT * FROM source_materials WHERE id = %s",
        (material_id,),
    ).fetchone()
    return dict(row) if row is not None else None


# Fields that are allowed to be updated, with their validation sets.
_UPDATABLE_FIELDS: dict[str, set[str] | None] = {
    "classification": VALID_CLASSIFICATIONS,
    "priority": VALID_PRIORITIES,
    "reading_instructions": None,  # No CHECK constraint — any string is fine.
}


def update_source_material(conn: psycopg.Connection, material_id: UUID, **kwargs: Any) -> None:
    """Update allowed fields on a source material.

    Accepted keyword arguments: classification, priority, reading_instructions.
    Validates fields that have CHECK constraints. Raises ValueError on invalid values.
    """
    if not kwargs:
        return

    sets: list[str] = []
    params: list[Any] = []

    for field, value in kwargs.items():
        if field not in _UPDATABLE_FIELDS:
            raise ValueError(
                f"Cannot update field {field!r}. "
                f"Updatable fields: {sorted(_UPDATABLE_FIELDS)}"
            )
        valid_values = _UPDATABLE_FIELDS[field]
        if valid_values is not None:
            _validate_field(field, value, valid_values)
        sets.append(f"{field} = %s")
        params.append(value)

    params.append(material_id)
    conn.execute(
        f"UPDATE source_materials SET {', '.join(sets)} WHERE id = %s",
        params,
    )


def delete_source_material(conn: psycopg.Connection, material_id: UUID) -> bool:
    """Delete a source material. Returns True if deleted, False if not found."""
    cur = conn.execute(
        "DELETE FROM source_materials WHERE id = %s",
        (material_id,),
    )
    return cur.rowcount > 0


def batch_add_materials(
    conn: psycopg.Connection,
    project_id: UUID,
    materials: list[dict[str, str]],
) -> list[UUID]:
    """Add multiple source materials at once. Returns list of created IDs.

    Each dict in materials should have: name, type, classification, priority,
    and optionally: path, reading_instructions.
    """
    ids = []
    for mat in materials:
        mat_id = add_source_material(
            conn=conn,
            project_id=project_id,
            name=mat["name"],
            type=mat["type"],
            classification=mat["classification"],
            priority=mat["priority"],
            path=mat.get("path"),
            reading_instructions=mat.get("reading_instructions"),
        )
        ids.append(mat_id)
    return ids


def generate_domain_briefing_skeleton(
    conn: psycopg.Connection,
    project_id: UUID,
) -> str:
    """Generate a domain briefing skeleton from primary source materials.

    Returns a markdown string with sections for each primary material.
    """
    materials = list_source_materials(conn, project_id)
    primary_materials = [m for m in materials if m["priority"] == "primary"]

    parts = ["# Domain Briefing\n"]
    parts.append("## Project Context\n")
    parts.append("<!-- Describe the business domain and project goals -->\n")

    if primary_materials:
        parts.append("\n## Primary Source Materials\n")
        for m in primary_materials:
            parts.append(f"### {m['name']} ({m['type']})")
            parts.append(f"Classification: {m['classification']}")
            if m.get("reading_instructions"):
                parts.append(f"Reading Instructions: {m['reading_instructions']}")
            parts.append("<!-- Key facts extracted from this source -->\n")

    parts.append("\n## Domain Axioms\n")
    parts.append("<!-- List non-negotiable facts about the domain -->")
    parts.append("<!-- These are used by the domain fidelity guardrail -->\n")

    return "\n".join(parts)


def triage_summary(conn: psycopg.Connection, project_id: UUID) -> dict[str, Any]:
    """Return a summary of source materials for a project.

    Returns:
        {
            "total": N,
            "by_classification": {"requirements": M, ...},
            "by_priority": {"primary": K, ...},
        }
    """
    rows = conn.execute(
        """
        SELECT classification, priority, count(*) as cnt
        FROM source_materials
        WHERE project_id = %s
        GROUP BY classification, priority
        """,
        (project_id,),
    ).fetchall()

    total = 0
    by_classification: dict[str, int] = {}
    by_priority: dict[str, int] = {}

    for row in rows:
        cnt = row["cnt"]
        total += cnt
        by_classification[row["classification"]] = (
            by_classification.get(row["classification"], 0) + cnt
        )
        by_priority[row["priority"]] = by_priority.get(row["priority"], 0) + cnt

    return {
        "total": total,
        "by_classification": by_classification,
        "by_priority": by_priority,
    }
