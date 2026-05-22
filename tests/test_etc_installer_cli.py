"""Tests for etc_installer.cli — the typer app top-level argv parser.

Covers AC-004 (full) and the cli-surface portion of AC-012 / AC-013 from
Ftmp-5afddbce task 005:

- ``etc_installer.cli`` exposes a ``typer.Typer()`` app named ``app``.
- ``--help`` prints usage text containing the four contract-pinned
  substrings: ``--client``, ``--scope``, ``claude|antigravity``,
  ``global|project``.
- ``--client {claude|antigravity}`` and ``--scope {global|project}`` are
  accepted as enum options. Invalid values exit non-zero.
- Unknown flags exit non-zero and print usage to stderr.
- Missing-``dist/`` preflight exits non-zero with a one-line error
  mentioning ``compile-sdlc.py`` (AC-013).
- ``etc_installer/__main__.py`` exposes ``app()`` invocation so the
  bootstrap's ``uv run -m etc_installer "$@"`` lands in the typer app.

These tests use ``typer.testing.CliRunner`` for behavioral coverage of
the argv surface; the parity test (``tests/test_etc_installer_parity.py``)
covers end-to-end install behavior against the bash bootstrap.

Reference: spec.md BR-004 (CLI argv compatibility), BR-012 (no silent
failure modes), AC-004 / AC-013.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

import pytest
from typer.testing import CliRunner

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from etc_installer import cli  # noqa: E402

# ── AC-004: argv surface ─────────────────────────────────────────────────


class TestAppPresence:
    """The module exposes ``app`` as a typer.Typer instance."""

    def test_should_expose_typer_app_named_app(self) -> None:
        import typer

        assert hasattr(cli, "app")
        assert isinstance(cli.app, typer.Typer)


class TestHelp:
    """AC-004: --help prints usage with the four pinned argv substrings."""

    def test_should_exit_zero_when_help_invoked(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli.app, ["--help"])
        assert result.exit_code == 0

    def test_should_list_client_flag_when_help_invoked(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli.app, ["--help"])
        assert "--client" in result.stdout

    def test_should_list_scope_flag_when_help_invoked(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli.app, ["--help"])
        assert "--scope" in result.stdout

    def test_should_list_claude_antigravity_literal_when_help_invoked(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli.app, ["--help"])
        assert "claude|antigravity" in result.stdout

    def test_should_list_global_project_literal_when_help_invoked(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli.app, ["--help"])
        assert "global|project" in result.stdout


class TestUnknownFlag:
    """AC-004: unknown flags exit non-zero."""

    def test_should_exit_nonzero_when_unknown_flag(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli.app, ["--bogus-unknown-flag"])
        assert result.exit_code != 0


class TestInvalidClientValue:
    """--client only accepts claude or antigravity."""

    def test_should_exit_nonzero_when_client_value_is_invalid(
        self, tmp_path: Path
    ) -> None:
        runner = CliRunner()
        result = runner.invoke(
            cli.app,
            ["--client", "notavalidclient", "--scope", "project"],
        )
        assert result.exit_code != 0


class TestInvalidScopeValue:
    """--scope only accepts global or project."""

    def test_should_exit_nonzero_when_scope_value_is_invalid(self) -> None:
        runner = CliRunner()
        result = runner.invoke(
            cli.app,
            ["--client", "claude", "--scope", "notavalidscope"],
        )
        assert result.exit_code != 0


# ── AC-013: missing-dist preflight ───────────────────────────────────────


class TestMissingDistPreflight:
    """AC-013: missing dist/ exits non-zero with compile-sdlc.py mention."""

    def test_should_exit_nonzero_when_dist_dir_absent(
        self, tmp_path: Path
    ) -> None:
        runner = CliRunner()
        # tmp_path has no dist/ subdirectory; point the cli at it
        result = runner.invoke(
            cli.app,
            [
                "--client",
                "claude",
                "--scope",
                "project",
                "--dist-dir",
                str(tmp_path / "nonexistent-dist"),
                "--target-dir",
                str(tmp_path / "target"),
            ],
        )
        assert result.exit_code != 0

    def test_should_mention_compile_sdlc_when_dist_dir_absent(
        self, tmp_path: Path
    ) -> None:
        runner = CliRunner()
        result = runner.invoke(
            cli.app,
            [
                "--client",
                "claude",
                "--scope",
                "project",
                "--dist-dir",
                str(tmp_path / "nonexistent-dist"),
                "--target-dir",
                str(tmp_path / "target"),
            ],
        )
        # Error may go to stdout or stderr depending on rich/typer routing
        combined = (result.stdout or "") + (result.output or "")
        assert "compile-sdlc.py" in combined, (
            "missing-dist preflight must mention compile-sdlc.py "
            f"(got: {combined!r})"
        )


# ── __main__.py entrypoint ──────────────────────────────────────────────


class TestMainModuleEntrypoint:
    """`python -m etc_installer` invokes cli.app()."""

    def test_should_call_app_when_main_module_executed(self) -> None:
        # Arrange — patch cli.app so we can detect the call without
        # actually running the typer chain.
        with mock.patch.object(cli, "app") as app_mock:
            # Act — exec the __main__ module body
            import importlib

            main_module = importlib.import_module("etc_installer.__main__")
            # Re-execute the module body to trigger the app() call under
            # the patched cli.app. Reload is the canonical way.
            importlib.reload(main_module)

            # Assert
            assert app_mock.called, (
                "etc_installer/__main__.py must call cli.app() so "
                "`python -m etc_installer` invokes the typer entrypoint."
            )


# ── Non-interactive client/scope combos accepted ─────────────────────────


class TestNonInteractiveCombos:
    """--client + --scope is the canonical non-interactive form.

    These tests verify the cli accepts the four valid combos without
    falling through to interactive mode. We point the cli at an empty
    tmp dist/ so the dist preflight passes (we create a stub
    settings-hooks.json) but the install short-circuits before doing any
    real work via --dry-run.
    """

    def _seed_minimal_dist(self, dist_dir: Path) -> None:
        dist_dir.mkdir(parents=True, exist_ok=True)
        (dist_dir / "settings-hooks.json").write_text(
            '{"hooks": {}}\n', encoding="utf-8"
        )

    @pytest.mark.parametrize(
        "client,scope",
        [
            ("claude", "global"),
            ("claude", "project"),
            ("antigravity", "global"),
            ("antigravity", "project"),
        ],
    )
    def test_should_accept_valid_client_scope_combo(
        self, tmp_path: Path, client: str, scope: str
    ) -> None:
        # Arrange — seed minimal dist, point cli at it via --dist-dir
        dist_dir = tmp_path / "dist"
        self._seed_minimal_dist(dist_dir)

        runner = CliRunner()

        # Act — invoke with --dry-run to short-circuit the heavy work
        result = runner.invoke(
            cli.app,
            [
                "--client",
                client,
                "--scope",
                scope,
                "--dist-dir",
                str(dist_dir),
                "--target-dir",
                str(tmp_path / "target"),
                "--dry-run",
            ],
        )

        # Assert
        assert result.exit_code == 0, (
            f"--client {client} --scope {scope} should succeed in dry-run, "
            f"got exit={result.exit_code}, output={result.output!r}"
        )
