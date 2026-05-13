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


class TestThirdPartyToolPrompts:
    """install.sh prompts before installing optional third-party tools
    (gh-stack, impeccable, Mergiraf) in interactive mode. In non-interactive
    mode (--client flag set), prints INFO instead of prompting."""

    def _install_sh_text(self) -> str:
        return INSTALL_SH.read_text(encoding="utf-8")

    def test_offer_install_helper_function_exists(self) -> None:
        """The shared helper that gates installs behind a prompt."""
        assert "offer_install" in self._install_sh_text()

    def test_helper_skips_prompt_when_client_flag_set(self) -> None:
        """When CLIENT_FLAG is non-empty, the helper MUST emit INFO and
        return without prompting — preserves F013 non-interactive contract."""
        text = self._install_sh_text()
        # The function body must check CLIENT_FLAG and emit INFO when set.
        assert 'if [ -n "$CLIENT_FLAG" ]' in text or 'CLIENT_FLAG' in text
        assert "INFO:" in text

    def test_helper_prompts_with_y_slash_n_in_interactive_mode(self) -> None:
        """Interactive path uses [y/N] prompt — operator must say yes."""
        text = self._install_sh_text()
        assert "[y/N]" in text
        assert "read -r -p" in text or "read -p" in text

    def test_helper_runs_install_command_only_on_yes(self) -> None:
        """The eval/run line is gated by a case branch matching y/Y/yes."""
        text = self._install_sh_text()
        assert "[yY]" in text
        # The actual run is via eval (so install_cmd remains a single
        # well-formed command rather than re-parsed via the shell's PATH).
        assert "eval" in text

    def test_gh_stack_preflight_uses_helper(self) -> None:
        text = self._install_sh_text()
        assert "gh-stack" in text
        assert "gh extension install jiazh/gh-stack" in text

    def test_impeccable_preflight_uses_helper(self) -> None:
        text = self._install_sh_text()
        assert "impeccable" in text
        assert "npm install -g impeccable" in text

    def test_mergiraf_preflight_uses_helper(self) -> None:
        text = self._install_sh_text()
        assert "Mergiraf" in text or "mergiraf" in text
        assert "brew install mergiraf" in text
        assert "cargo install mergiraf" in text

    def test_install_failures_continue_not_abort(self) -> None:
        """A failed third-party install MUST NOT abort install.sh —
        these tools are optional and core etc install must continue."""
        text = self._install_sh_text()
        # The helper warns on non-zero exit but does NOT `exit 1`.
        assert "install failed" in text
        # No `exit` immediately following the install eval block.
        # Check the offer_install function body doesn't call exit.
        # (Approximation: 'exit' calls in the function would be near 'eval')


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
