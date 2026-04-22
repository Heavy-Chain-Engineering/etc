"""Tests for database module — verifies apply_schema handles multiple migration files."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import psycopg


class TestApplySchema:
    def test_apply_schema_picks_up_all_migrations(self, db: psycopg.Connection) -> None:
        """Verify that apply_schema applies all SQL files including overrides migration."""
        # The guardrail_checks table should have override columns after migrations
        result = db.execute(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'guardrail_checks'
            AND column_name IN ('override_reason', 'overridden_by', 'overridden_at')
            ORDER BY column_name
            """
        ).fetchall()
        column_names = [r["column_name"] for r in result]
        assert "override_reason" in column_names
        assert "overridden_by" in column_names
        assert "overridden_at" in column_names
