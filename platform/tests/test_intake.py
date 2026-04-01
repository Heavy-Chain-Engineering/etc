"""Tests for source material intake — CRUD, validation, and triage summary."""

from __future__ import annotations

from uuid import UUID

import psycopg
import pytest

from etc_platform.intake import (
    VALID_CLASSIFICATIONS,
    VALID_PRIORITIES,
    VALID_TYPES,
    add_source_material,
    batch_add_materials,
    delete_source_material,
    generate_domain_briefing_skeleton,
    get_source_material,
    list_source_materials,
    triage_summary,
    update_source_material,
)


def _create_project(db: psycopg.Connection) -> UUID:
    """Helper: insert a project and return its id."""
    row = db.execute(
        "INSERT INTO projects (name, root_path, classification) "
        "VALUES ('p', '/tmp', 'greenfield') RETURNING id"
    ).fetchone()
    assert row is not None
    return row["id"]


class TestConstants:
    def test_valid_types(self) -> None:
        assert VALID_TYPES == {"pdf", "code", "export", "spreadsheet", "document"}

    def test_valid_classifications(self) -> None:
        assert VALID_CLASSIFICATIONS == {
            "business_operations",
            "requirements",
            "implementation_artifact",
            "domain_truth",
        }

    def test_valid_priorities(self) -> None:
        assert VALID_PRIORITIES == {"primary", "high", "medium", "context_only"}


class TestAddSourceMaterial:
    def test_add_returns_uuid(self, db: psycopg.Connection) -> None:
        pid = _create_project(db)
        mid = add_source_material(
            db, pid, "requirements.pdf", "pdf", "requirements", "primary"
        )
        assert isinstance(mid, UUID)

    def test_add_with_all_fields(self, db: psycopg.Connection) -> None:
        pid = _create_project(db)
        mid = add_source_material(
            db,
            pid,
            "legacy-export.csv",
            "export",
            "business_operations",
            "high",
            path="/data/legacy-export.csv",
            reading_instructions="Skip header row; columns A-F are relevant",
        )
        row = db.execute(
            "SELECT * FROM source_materials WHERE id = %s", (mid,)
        ).fetchone()
        assert row is not None
        assert row["name"] == "legacy-export.csv"
        assert row["type"] == "export"
        assert row["classification"] == "business_operations"
        assert row["priority"] == "high"
        assert row["path"] == "/data/legacy-export.csv"
        assert row["reading_instructions"] == "Skip header row; columns A-F are relevant"
        assert row["project_id"] == pid

    def test_add_invalid_type_raises(self, db: psycopg.Connection) -> None:
        pid = _create_project(db)
        with pytest.raises(ValueError, match="type"):
            add_source_material(db, pid, "x", "invalid_type", "requirements", "primary")

    def test_add_invalid_classification_raises(self, db: psycopg.Connection) -> None:
        pid = _create_project(db)
        with pytest.raises(ValueError, match="classification"):
            add_source_material(db, pid, "x", "pdf", "bad_class", "primary")

    def test_add_invalid_priority_raises(self, db: psycopg.Connection) -> None:
        pid = _create_project(db)
        with pytest.raises(ValueError, match="priority"):
            add_source_material(db, pid, "x", "pdf", "requirements", "ultra")


class TestListSourceMaterials:
    def test_list_empty(self, db: psycopg.Connection) -> None:
        pid = _create_project(db)
        result = list_source_materials(db, pid)
        assert result == []

    def test_list_returns_ordered_by_priority(self, db: psycopg.Connection) -> None:
        pid = _create_project(db)
        # Insert in non-priority order
        add_source_material(db, pid, "ctx", "document", "requirements", "context_only")
        add_source_material(db, pid, "hi", "pdf", "requirements", "high")
        add_source_material(db, pid, "pri", "code", "domain_truth", "primary")
        add_source_material(db, pid, "med", "spreadsheet", "business_operations", "medium")

        result = list_source_materials(db, pid)
        assert len(result) == 4
        priorities = [r["priority"] for r in result]
        assert priorities == ["primary", "high", "medium", "context_only"]

    def test_list_scoped_to_project(self, db: psycopg.Connection) -> None:
        pid1 = _create_project(db)
        pid2 = _create_project(db)
        add_source_material(db, pid1, "doc1", "pdf", "requirements", "primary")
        add_source_material(db, pid2, "doc2", "pdf", "requirements", "primary")

        result1 = list_source_materials(db, pid1)
        result2 = list_source_materials(db, pid2)
        assert len(result1) == 1
        assert len(result2) == 1
        assert result1[0]["name"] == "doc1"
        assert result2[0]["name"] == "doc2"


class TestGetSourceMaterial:
    def test_get_existing(self, db: psycopg.Connection) -> None:
        pid = _create_project(db)
        mid = add_source_material(db, pid, "spec.pdf", "pdf", "requirements", "primary")
        row = get_source_material(db, mid)
        assert row is not None
        assert row["id"] == mid
        assert row["name"] == "spec.pdf"

    def test_get_nonexistent_returns_none(self, db: psycopg.Connection) -> None:
        result = get_source_material(db, UUID("00000000-0000-0000-0000-000000000000"))
        assert result is None


class TestUpdateSourceMaterial:
    def test_update_classification(self, db: psycopg.Connection) -> None:
        pid = _create_project(db)
        mid = add_source_material(db, pid, "x", "pdf", "requirements", "primary")
        update_source_material(db, mid, classification="domain_truth")
        row = get_source_material(db, mid)
        assert row is not None
        assert row["classification"] == "domain_truth"

    def test_update_priority(self, db: psycopg.Connection) -> None:
        pid = _create_project(db)
        mid = add_source_material(db, pid, "x", "pdf", "requirements", "primary")
        update_source_material(db, mid, priority="context_only")
        row = get_source_material(db, mid)
        assert row is not None
        assert row["priority"] == "context_only"

    def test_update_reading_instructions(self, db: psycopg.Connection) -> None:
        pid = _create_project(db)
        mid = add_source_material(db, pid, "x", "pdf", "requirements", "primary")
        update_source_material(db, mid, reading_instructions="Focus on section 3")
        row = get_source_material(db, mid)
        assert row is not None
        assert row["reading_instructions"] == "Focus on section 3"

    def test_update_invalid_priority_raises(self, db: psycopg.Connection) -> None:
        pid = _create_project(db)
        mid = add_source_material(db, pid, "x", "pdf", "requirements", "primary")
        with pytest.raises(ValueError, match="priority"):
            update_source_material(db, mid, priority="ultra")

    def test_update_invalid_classification_raises(self, db: psycopg.Connection) -> None:
        pid = _create_project(db)
        mid = add_source_material(db, pid, "x", "pdf", "requirements", "primary")
        with pytest.raises(ValueError, match="classification"):
            update_source_material(db, mid, classification="bogus")

    def test_update_no_kwargs_is_noop(self, db: psycopg.Connection) -> None:
        pid = _create_project(db)
        mid = add_source_material(db, pid, "x", "pdf", "requirements", "primary")
        # Should not raise
        update_source_material(db, mid)
        row = get_source_material(db, mid)
        assert row is not None
        assert row["classification"] == "requirements"


class TestDeleteSourceMaterial:
    def test_delete_existing(self, db: psycopg.Connection) -> None:
        pid = _create_project(db)
        mid = add_source_material(db, pid, "x", "pdf", "requirements", "primary")
        assert delete_source_material(db, mid) is True
        assert get_source_material(db, mid) is None

    def test_delete_nonexistent_returns_false(self, db: psycopg.Connection) -> None:
        result = delete_source_material(db, UUID("00000000-0000-0000-0000-000000000000"))
        assert result is False


class TestTriageSummary:
    def test_summary_empty(self, db: psycopg.Connection) -> None:
        pid = _create_project(db)
        summary = triage_summary(db, pid)
        assert summary == {
            "total": 0,
            "by_classification": {},
            "by_priority": {},
        }

    def test_summary_with_materials(self, db: psycopg.Connection) -> None:
        pid = _create_project(db)
        add_source_material(db, pid, "a", "pdf", "requirements", "primary")
        add_source_material(db, pid, "b", "code", "requirements", "high")
        add_source_material(db, pid, "c", "document", "domain_truth", "primary")
        add_source_material(db, pid, "d", "export", "business_operations", "medium")

        summary = triage_summary(db, pid)
        assert summary["total"] == 4
        assert summary["by_classification"] == {
            "requirements": 2,
            "domain_truth": 1,
            "business_operations": 1,
        }
        assert summary["by_priority"] == {
            "primary": 2,
            "high": 1,
            "medium": 1,
        }


class TestBatchAddMaterials:
    def test_adds_multiple_materials(self, db: psycopg.Connection) -> None:
        pid = _create_project(db)
        materials = [
            {"name": "Doc A", "type": "document", "classification": "requirements", "priority": "primary"},
            {"name": "Doc B", "type": "spreadsheet", "classification": "domain_truth", "priority": "high"},
        ]
        ids = batch_add_materials(db, pid, materials)
        assert len(ids) == 2
        all_mats = list_source_materials(db, pid)
        assert len(all_mats) == 2

    def test_adds_with_optional_fields(self, db: psycopg.Connection) -> None:
        pid = _create_project(db)
        materials = [
            {
                "name": "Doc A",
                "type": "document",
                "classification": "requirements",
                "priority": "primary",
                "path": "/tmp/doc.pdf",
                "reading_instructions": "Focus on section 3",
            },
        ]
        ids = batch_add_materials(db, pid, materials)
        mat = get_source_material(db, ids[0])
        assert mat is not None
        assert mat["path"] == "/tmp/doc.pdf"
        assert mat["reading_instructions"] == "Focus on section 3"

    def test_returns_empty_list_for_no_materials(self, db: psycopg.Connection) -> None:
        pid = _create_project(db)
        ids = batch_add_materials(db, pid, [])
        assert ids == []


class TestGenerateDomainBriefingSkeleton:
    def test_includes_primary_materials(self, db: psycopg.Connection) -> None:
        pid = _create_project(db)
        add_source_material(
            db, pid, "CX Workflows", "spreadsheet", "domain_truth", "primary",
            reading_instructions="Focus on trigger columns",
        )
        briefing = generate_domain_briefing_skeleton(db, pid)
        assert "CX Workflows" in briefing
        assert "Focus on trigger columns" in briefing
        assert "Domain Axioms" in briefing

    def test_empty_when_no_primary(self, db: psycopg.Connection) -> None:
        pid = _create_project(db)
        add_source_material(db, pid, "Ref Doc", "document", "requirements", "context_only")
        briefing = generate_domain_briefing_skeleton(db, pid)
        assert "Primary Source Materials" not in briefing
        assert "Domain Briefing" in briefing

    def test_structure(self, db: psycopg.Connection) -> None:
        pid = _create_project(db)
        briefing = generate_domain_briefing_skeleton(db, pid)
        assert "# Domain Briefing" in briefing
        assert "## Project Context" in briefing
        assert "## Domain Axioms" in briefing
