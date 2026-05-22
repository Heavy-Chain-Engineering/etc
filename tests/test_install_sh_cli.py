"""Tests for install.sh — the bash bootstrap layer (Ftmp-5afddbce task 001).

After the Python installer rewrite, install.sh is a ~30-line bash bootstrap
whose entire job is:

  1. Provide a minimal `--help` listing the contract-pinned argv surface.
  2. Detect `uv` on PATH. If absent, install it via the official Astral
     curl-pipe installer; if that fails, exit non-zero with a one-line
     error mentioning the Astral docs URL.
  3. Hand off via `exec uv run --from "$SCRIPT_DIR" -m etc_installer "$@"`.

These tests cover ONLY that bootstrap surface. Deeper install behavior
(directory creation, settings.json merge, third-party preflights,
INFO_LINE constants, banner) moves to ``tests/test_etc_installer.py`` in
task 005 of the Ftmp-5afddbce rollout.

Reference: ACs AC-001, AC-002, AC-004 (partial), AC-009 (partial) of the
task YAML at
``.etc_sdlc/features/active/Ftmp-5afddbce-python-installer-rewrite/tasks/001-bash-bootstrap-pyproject-toml-deps-bootstrap-only-test-shrink.yaml``.
"""

from __future__ import annotations

import re
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


def _install_sh_text() -> str:
    return INSTALL_SH.read_text(encoding="utf-8")


def _executable_line_count(text: str) -> int:
    """Count executable lines (non-blank, non-comment).

    A line is "comment" iff its first non-whitespace character is ``#``,
    EXCLUDING the shebang on line 1 (``#!/usr/bin/env bash`` is executable
    metadata, not a comment-out).
    """
    count = 0
    for idx, raw in enumerate(text.splitlines()):
        stripped = raw.strip()
        if not stripped:
            continue
        if idx == 0 and stripped.startswith("#!"):
            count += 1
            continue
        if stripped.startswith("#"):
            continue
        count += 1
    return count


class TestBootstrapLineCount:
    """AC-001: install.sh is <= 50 lines of executable code."""

    def test_should_be_under_50_executable_lines_when_counted(self) -> None:
        text = _install_sh_text()
        loc = _executable_line_count(text)
        assert loc <= 50, (
            f"install.sh executable LOC = {loc} (limit: 50). "
            "The bootstrap must delegate to etc_installer; do not "
            "expand bash logic here."
        )

    # Explicit AC-001 name pin: the task YAML names this test verbatim.
    def test_bootstrap_line_count_under_50(self) -> None:
        text = _install_sh_text()
        assert _executable_line_count(text) <= 50


class TestHelp:
    """AC-004 (partial — bootstrap level): --help exits 0 with usage text
    containing the four contract-pinned argv substrings."""

    def test_should_exit_zero_when_help_long_flag(self) -> None:
        result = _run(["--help"])
        assert result.returncode == 0

    def test_should_exit_zero_when_help_short_flag(self) -> None:
        result = _run(["-h"])
        assert result.returncode == 0

    def test_should_list_client_flag_when_help_invoked(self) -> None:
        result = _run(["--help"])
        assert "--client" in result.stdout

    def test_should_list_scope_flag_when_help_invoked(self) -> None:
        result = _run(["--help"])
        assert "--scope" in result.stdout

    def test_should_list_claude_antigravity_literal_when_help_invoked(self) -> None:
        """AC-004 pins the literal substring ``claude|antigravity``."""
        result = _run(["--help"])
        assert "claude|antigravity" in result.stdout

    def test_should_list_global_project_literal_when_help_invoked(self) -> None:
        """AC-004 pins the literal substring ``global|project``."""
        result = _run(["--help"])
        assert "global|project" in result.stdout


class TestUnknownFlag:
    """AC-004 (partial): unknown flags exit non-zero."""

    def test_should_exit_nonzero_when_unknown_flag(self) -> None:
        result = _run(["--bogus"])
        assert result.returncode != 0


class TestUvDetectionAndHandoff:
    """AC-002 (text-scan side): the bootstrap detects `uv` on PATH, auto-
    installs via the Astral curl-pipe when missing, and hands off via
    `exec uv run --from "$SCRIPT_DIR" -m etc_installer "$@"`.

    These assertions scan the bootstrap source rather than executing the
    install path end-to-end. Behavioral coverage of the hand-off lives in
    ``tests/test_etc_installer.py`` (added in task 005) once the Python
    module ships in tasks 002-005.
    """

    def test_should_detect_uv_on_path_via_command_v(self) -> None:
        text = _install_sh_text()
        assert "command -v uv" in text, (
            "bootstrap must probe PATH for uv via `command -v uv`"
        )

    def test_should_invoke_astral_curl_pipe_when_uv_missing(self) -> None:
        text = _install_sh_text()
        assert "https://astral.sh/uv/install.sh" in text, (
            "bootstrap must install uv via curl-pipe of the official "
            "Astral installer URL"
        )
        assert "curl" in text, "bootstrap must invoke curl for the uv install"

    def test_should_hand_off_via_exec_uv_run(self) -> None:
        """AC-004 (partial): argv passes through via `exec` (process
        replacement) so exit codes propagate naturally. The path flag
        (``--project`` on uv>=0.4 / the design's ``--from`` shorthand)
        is intentionally not pinned here — the binding contract is the
        ``exec uv run ... -m etc_installer "$@"`` shape."""
        text = _install_sh_text()
        assert re.search(r'exec\s+uv\s+run\s+', text), (
            "bootstrap must hand off via `exec uv run ...` so the Python "
            "module replaces the bash process and exit codes propagate "
            "naturally"
        )
        assert "-m etc_installer" in text, (
            "hand-off must invoke `-m etc_installer`"
        )
        assert '"$@"' in text, (
            'hand-off must forward argv via "$@" (quoted, expanded)'
        )

    def test_should_reference_script_dir_for_uv_from_path(self) -> None:
        """Per ADR-003 (etc_installer inline-in-repo): the `--from` flag
        resolves the package source via $SCRIPT_DIR, not $PWD."""
        text = _install_sh_text()
        assert "SCRIPT_DIR" in text


class TestUvInstallFailureMessage:
    """AC-002: if the uv install fails, the bootstrap exits non-zero with
    a one-line error mentioning the Astral docs URL. Text-scan only; the
    failure-path behavioral test would need to break PATH lookup +
    network, which is fragile in CI."""

    def test_should_mention_astral_docs_url_in_error_path(self) -> None:
        text = _install_sh_text()
        assert "astral.sh" in text, (
            "uv-install-failure error must point operator at Astral docs"
        )

    def test_should_set_errexit_to_propagate_uv_install_failure(self) -> None:
        """`set -e` (or `set -euo pipefail`) ensures a failed curl/sh
        pipeline exits the bootstrap non-zero."""
        text = _install_sh_text()
        # Accept either the strict form (`set -euo pipefail`) or just `set -e`.
        assert re.search(r"set\s+-e", text), (
            "bootstrap must enable errexit so failed uv install exits non-zero"
        )
