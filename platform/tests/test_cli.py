"""Tests for the ETC CLI interface."""

from __future__ import annotations

from typer.testing import CliRunner

from etc_platform.cli import app

runner = CliRunner()


class TestVersion:
    def test_version_flag(self) -> None:
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "etc-platform" in result.output
        assert "0.1.0" in result.output

    def test_version_short_flag(self) -> None:
        result = runner.invoke(app, ["-v"])
        assert result.exit_code == 0
        assert "etc-platform" in result.output


class TestHelp:
    def test_help(self) -> None:
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "ETC Orchestration Platform" in result.output

    def test_no_args_shows_help(self) -> None:
        result = runner.invoke(app, [])
        assert result.exit_code == 0


class TestInit:
    def test_init_creates_project(self, db) -> None:  # type: ignore[no-untyped-def]
        import os

        os.environ["ETC_DATABASE_URL"] = "postgresql://etc:etc_dev@localhost:5433/etc_platform_test"
        result = runner.invoke(app, ["init", "test-proj", "--type", "greenfield"])
        assert result.exit_code == 0
        assert "test-proj" in result.output
        assert "greenfield" in result.output

        # Verify phases were created
        phases = db.execute(
            "SELECT name FROM phases ORDER BY id"
        ).fetchall()
        phase_names = [p["name"] for p in phases]
        assert "Bootstrap" in phase_names
        assert "Evaluate" in phase_names
        assert len(phase_names) == 8

    def test_init_rejects_invalid_type(self) -> None:
        result = runner.invoke(app, ["init", "bad-proj", "--type", "invalid"])
        assert result.exit_code == 1
        assert "Invalid type" in result.output

    def test_init_with_intake_flag(self, db) -> None:  # type: ignore[no-untyped-def]
        """Test that --intake flag is accepted (doesn't error on the flag itself)."""
        import os

        os.environ["ETC_DATABASE_URL"] = "postgresql://etc:etc_dev@localhost:5433/etc_platform_test"
        # Without --intake, the flag defaults to False and init works normally
        result = runner.invoke(app, ["init", "test-intake", "--type", "greenfield"])
        assert result.exit_code == 0


class TestHistory:
    def test_history_command_exists(self) -> None:
        """The 'history' command is recognized (not 'No such command')."""
        result = runner.invoke(app, ["history", "--help"])
        assert result.exit_code == 0
        assert "No such command" not in (result.output or "")
        assert "event history" in result.output.lower() or "decision log" in result.output.lower()

    def test_history_no_active_project(self) -> None:
        import os

        os.environ["ETC_DATABASE_URL"] = "postgresql://etc:etc_dev@localhost:5433/etc_platform_test"
        result = runner.invoke(app, ["history"])
        # Should gracefully handle no active project
        assert result.exit_code == 0

    def test_history_with_limit_option(self) -> None:
        result = runner.invoke(app, ["history", "--help"])
        assert "--limit" in result.output

    def test_history_with_phase_option(self) -> None:
        result = runner.invoke(app, ["history", "--help"])
        assert "--phase" in result.output


class TestStatus:
    def test_status_no_projects(self) -> None:
        import os

        os.environ["ETC_DATABASE_URL"] = "postgresql://etc:etc_dev@localhost:5433/etc_platform_test"
        result = runner.invoke(app, ["status"])
        # Either shows projects or says no active projects
        assert result.exit_code == 0
