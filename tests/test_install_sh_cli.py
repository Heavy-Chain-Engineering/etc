"""Tests for install.sh CLI flag parsing (F013).

F013 added --client, --scope, --help flag parsing to install.sh.
These tests exercise the flag-parsing behavior via subprocess without
actually performing any install — they invoke install.sh with flags
that short-circuit (--help) or trigger errors (unknown flag) so the
real install steps never run.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

INSTALL_SH = Path(__file__).parent.parent / "install.sh"


def _run(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(INSTALL_SH), *args],
        capture_output=True,
        text=True,
        timeout=15,
        cwd=cwd,
    )


class TestHelp:
    def test_help_long_flag_exits_zero_with_usage(self) -> None:
        result = _run(["--help"])
        assert result.returncode == 0
        assert "Usage:" in result.stdout
        assert "--client" in result.stdout
        assert "--scope" in result.stdout

    def test_help_short_flag_exits_zero(self) -> None:
        result = _run(["-h"])
        assert result.returncode == 0
        assert "Usage:" in result.stdout

    def test_help_lists_both_scope_values(self) -> None:
        result = _run(["--help"])
        assert "global" in result.stdout
        assert "project" in result.stdout

    def test_help_lists_both_client_values(self) -> None:
        result = _run(["--help"])
        assert "claude" in result.stdout
        assert "antigravity" in result.stdout


class TestUnknownFlag:
    def test_unknown_flag_exits_nonzero(self) -> None:
        result = _run(["--bogus"])
        assert result.returncode != 0

    def test_unknown_flag_emits_error_to_stderr(self) -> None:
        result = _run(["--bogus"])
        assert "unknown flag" in result.stderr.lower()
        assert "--bogus" in result.stderr

    def test_unknown_flag_includes_usage_in_stderr(self) -> None:
        result = _run(["--bogus"])
        assert "Usage:" in result.stderr


class TestFlagValidation:
    def test_invalid_client_value_exits_nonzero(self) -> None:
        result = _run(["--client", "vim"])
        assert result.returncode != 0
        assert "--client must be" in result.stderr

    def test_invalid_scope_value_exits_nonzero(self) -> None:
        result = _run(["--scope", "system"])
        assert result.returncode != 0
        assert "--scope must be" in result.stderr

    def test_valid_client_claude_passes_validation(self, tmp_path: Path) -> None:
        # Run from a directory without dist/ so install short-circuits at the
        # dist preflight, not at flag validation. We're testing that flag
        # values parse cleanly, not that install completes.
        result = _run(["--client", "claude", "--scope", "project"], cwd=tmp_path)
        # Either it fails on dist/ preflight (exit 1) — which means flag
        # parsing succeeded — or it succeeds. It MUST NOT fail with
        # "must be 'claude' or 'antigravity'".
        assert "--client must be" not in result.stderr
        assert "--scope must be" not in result.stderr

    def test_valid_client_antigravity_passes_validation(self, tmp_path: Path) -> None:
        result = _run(["--client", "antigravity", "--scope", "project"], cwd=tmp_path)
        assert "--client must be" not in result.stderr
        assert "--scope must be" not in result.stderr

    def test_valid_scope_global_passes_validation(self, tmp_path: Path) -> None:
        result = _run(["--client", "claude", "--scope", "global"], cwd=tmp_path)
        assert "--scope must be" not in result.stderr

    def test_valid_scope_project_passes_validation(self, tmp_path: Path) -> None:
        result = _run(["--client", "claude", "--scope", "project"], cwd=tmp_path)
        assert "--scope must be" not in result.stderr


class TestBackwardCompatibility:
    def test_no_flags_does_not_print_error(self, tmp_path: Path) -> None:
        """install.sh with no flags should fall through to interactive mode.
        Running in a tmp_path with no dist/ means it exits early at dist
        preflight, not at flag parsing. We just verify no flag-parsing
        error appears in stderr."""
        result = _run([], cwd=tmp_path)
        assert "unknown flag" not in result.stderr.lower()
        assert "--client must be" not in result.stderr
        assert "--scope must be" not in result.stderr
