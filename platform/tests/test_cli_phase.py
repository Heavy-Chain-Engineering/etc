"""Tests for phase management and DoD CLI commands."""

from __future__ import annotations

import json
import os
from uuid import UUID

import psycopg
import pytest
from psycopg.rows import dict_row
from typer.testing import CliRunner

from etc_platform.cli import app

runner = CliRunner()

# Point CLI commands at the test database
os.environ["ETC_DATABASE_URL"] = "postgresql://etc:etc_dev@localhost:5433/etc_platform_test"

PHASES = ["Bootstrap", "Spec", "Design", "Decompose", "Build", "Verify", "Ship", "Evaluate"]


@pytest.fixture
def project_with_phases(pg_dsn: str, setup_test_db: None):
    """Create a project with phases that CLI commands can see (committed)."""
    with psycopg.connect(pg_dsn, row_factory=dict_row) as conn:
        row = conn.execute(
            "INSERT INTO projects (name, root_path, classification) "
            "VALUES ('test-proj', '/tmp', 'greenfield') RETURNING id"
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


@pytest.fixture
def active_project_with_dod(pg_dsn: str, setup_test_db: None):
    """Create a project with an active Bootstrap phase and DoD items."""
    with psycopg.connect(pg_dsn, row_factory=dict_row) as conn:
        row = conn.execute(
            "INSERT INTO projects (name, root_path, classification) "
            "VALUES ('dod-proj', '/tmp', 'greenfield') RETURNING id"
        ).fetchone()
        assert row is not None
        project_id = row["id"]

        for phase in PHASES:
            status = "active" if phase == "Bootstrap" else "pending"
            conn.execute(
                "INSERT INTO phases (project_id, name, dod_items, status) "
                "VALUES (%s, %s, '[]', %s)",
                (project_id, phase, status),
            )

        # Add DoD items to Bootstrap
        dod_items = json.dumps([
            {
                "text": "PRD written",
                "check_type": "agent_verified",
                "checked": True,
                "checked_at": "2026-01-01T00:00:00+00:00",
                "checked_by": "spec_agent",
            },
            {
                "text": "Stakeholder sign-off",
                "check_type": "human_confirmed",
                "checked": False,
                "checked_at": None,
                "checked_by": None,
            },
        ])
        conn.execute(
            "UPDATE phases SET dod_items = %s::jsonb WHERE project_id = %s AND name = 'Bootstrap'",
            (dod_items, project_id),
        )
        conn.commit()

    yield project_id

    # Cleanup
    with psycopg.connect(pg_dsn, row_factory=dict_row) as conn:
        conn.execute("DELETE FROM projects WHERE id = %s", (project_id,))
        conn.commit()


@pytest.fixture
def fully_checked_project(pg_dsn: str, setup_test_db: None):
    """Create a project with an active Bootstrap phase where all DoD items are checked."""
    with psycopg.connect(pg_dsn, row_factory=dict_row) as conn:
        row = conn.execute(
            "INSERT INTO projects (name, root_path, classification) "
            "VALUES ('done-proj', '/tmp', 'greenfield') RETURNING id"
        ).fetchone()
        assert row is not None
        project_id = row["id"]

        for phase in PHASES:
            status = "active" if phase == "Bootstrap" else "pending"
            conn.execute(
                "INSERT INTO phases (project_id, name, dod_items, status) "
                "VALUES (%s, %s, '[]', %s)",
                (project_id, phase, status),
            )

        # All DoD items checked
        dod_items = json.dumps([
            {
                "text": "PRD written",
                "check_type": "agent_verified",
                "checked": True,
                "checked_at": "2026-01-01T00:00:00+00:00",
                "checked_by": "spec_agent",
            },
        ])
        conn.execute(
            "UPDATE phases SET dod_items = %s::jsonb WHERE project_id = %s AND name = 'Bootstrap'",
            (dod_items, project_id),
        )
        conn.commit()

    yield project_id

    # Cleanup
    with psycopg.connect(pg_dsn, row_factory=dict_row) as conn:
        conn.execute("DELETE FROM projects WHERE id = %s", (project_id,))
        conn.commit()


# ============================================================================
# Phase status
# ============================================================================


class TestPhaseStatus:
    def test_phase_status_shows_current(self, active_project_with_dod: UUID) -> None:
        result = runner.invoke(app, ["phase", "status"])
        assert result.exit_code == 0
        assert "Bootstrap" in result.output
        assert "active" in result.output.lower()

    def test_phase_status_shows_dod_progress(self, active_project_with_dod: UUID) -> None:
        result = runner.invoke(app, ["phase", "status"])
        assert result.exit_code == 0
        # Should show 1/2 checked
        assert "1" in result.output
        assert "2" in result.output

    def test_phase_status_no_project(self, setup_test_db: None, pg_dsn: str) -> None:
        # Clean out all projects first
        with psycopg.connect(pg_dsn, row_factory=dict_row) as conn:
            conn.execute("DELETE FROM projects")
            conn.commit()
        try:
            result = runner.invoke(app, ["phase", "status"])
            assert result.exit_code == 0
            assert "no active project" in result.output.lower()
        finally:
            pass  # nothing to restore


# ============================================================================
# Phase approve
# ============================================================================


class TestPhaseApprove:
    def test_approve_advances_phase(self, fully_checked_project: UUID) -> None:
        result = runner.invoke(app, ["phase", "approve", "--reason", "Bootstrap complete"])
        assert result.exit_code == 0
        assert "Spec" in result.output

    def test_approve_blocked_by_dod(self, active_project_with_dod: UUID) -> None:
        result = runner.invoke(app, ["phase", "approve", "--reason", "Trying early"])
        assert result.exit_code == 1
        assert "DoD not met" in result.output or "dod" in result.output.lower()


# ============================================================================
# Phase list
# ============================================================================


class TestPhaseList:
    def test_list_shows_all_phases(self, active_project_with_dod: UUID) -> None:
        result = runner.invoke(app, ["phase", "list"])
        assert result.exit_code == 0
        for phase in PHASES:
            assert phase in result.output

    def test_list_shows_statuses(self, active_project_with_dod: UUID) -> None:
        result = runner.invoke(app, ["phase", "list"])
        assert result.exit_code == 0
        assert "active" in result.output.lower()
        assert "pending" in result.output.lower()


# ============================================================================
# DoD status
# ============================================================================


class TestDodStatus:
    def test_dod_status_shows_items(self, active_project_with_dod: UUID) -> None:
        result = runner.invoke(app, ["dod", "status"])
        assert result.exit_code == 0
        assert "PRD written" in result.output
        assert "Stakeholder sign-off" in result.output

    def test_dod_status_shows_check_marks(self, active_project_with_dod: UUID) -> None:
        result = runner.invoke(app, ["dod", "status"])
        assert result.exit_code == 0
        # Checked item should have a checkmark symbol
        output = result.output
        # The first item is checked, second is not
        assert any(c in output for c in ["✓", "✔", "[x]", "checked"])

    def test_dod_status_empty(self, project_with_phases: UUID) -> None:
        result = runner.invoke(app, ["dod", "status"])
        assert result.exit_code == 0
        assert "no dod items" in result.output.lower() or "no items" in result.output.lower() or "empty" in result.output.lower()


# ============================================================================
# DoD check
# ============================================================================


class TestDodCheck:
    def test_check_marks_item(self, active_project_with_dod: UUID, pg_dsn: str) -> None:
        # Item 1 is unchecked ("Stakeholder sign-off")
        result = runner.invoke(app, ["dod", "check", "1"])
        assert result.exit_code == 0
        assert "checked" in result.output.lower() or "✓" in result.output

        # Verify in DB
        with psycopg.connect(pg_dsn, row_factory=dict_row) as conn:
            row = conn.execute(
                "SELECT dod_items FROM phases WHERE project_id = %s AND name = 'Bootstrap'",
                (active_project_with_dod,),
            ).fetchone()
            assert row is not None
            items = row["dod_items"]
            assert items[1]["checked"] is True


# ============================================================================
# DoD add
# ============================================================================


class TestDodAdd:
    def test_add_creates_item(self, active_project_with_dod: UUID, pg_dsn: str) -> None:
        result = runner.invoke(
            app, ["dod", "add", "--text", "All tests passing", "--type", "automatic"]
        )
        assert result.exit_code == 0
        assert "added" in result.output.lower() or "All tests passing" in result.output

        # Verify in DB
        with psycopg.connect(pg_dsn, row_factory=dict_row) as conn:
            row = conn.execute(
                "SELECT dod_items FROM phases WHERE project_id = %s AND name = 'Bootstrap'",
                (active_project_with_dod,),
            ).fetchone()
            assert row is not None
            items = row["dod_items"]
            assert len(items) == 3  # 2 original + 1 new
            assert items[2]["text"] == "All tests passing"
            assert items[2]["check_type"] == "automatic"

    def test_add_invalid_type(self, active_project_with_dod: UUID) -> None:
        result = runner.invoke(
            app, ["dod", "add", "--text", "Something", "--type", "bogus"]
        )
        assert result.exit_code != 0 or "invalid" in result.output.lower() or "error" in result.output.lower()


# ============================================================================
# Enhanced status command
# ============================================================================


class TestEnhancedStatus:
    def test_status_shows_phase_info(self, active_project_with_dod: UUID) -> None:
        result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        # Should still show the project
        assert "dod-proj" in result.output
        # Should also show phase info
        assert "Bootstrap" in result.output

    def test_status_shows_dod_progress(self, active_project_with_dod: UUID) -> None:
        result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        # Should show DoD progress like "1/2"
        assert "1/2" in result.output or ("1" in result.output and "2" in result.output)
