"""Interactive end-to-end composition test for the etc installer.

This is the behavioral test whose ABSENCE let the F026 interactive
surface certify VERIFIED while shipping dead. The audit
("built-but-never-wired") found that ``preflights.offer_install``,
``status_line.install_status_line``, and
``sandbox_config.install_sandbox_config`` had unit tests but ZERO call
sites — the modules were green, the composed feature was dead.

These tests drive the WHOLE ``cli.app`` (the same entry point
``python -m etc_installer`` lands on) with scripted stdin against a
tmp_path target, and assert the prompts actually fire end-to-end:

- Interactive run (no ``--client`` flag), declining every prompt:
  (a) the third-party offer prompts + status-line + sandbox prompts
      appear in the output;
  (b) the four third-party INFO lines appear when the tools are absent;
  (c) declining leaves NO ``statusLine`` / ``permissions`` block written;
  (d) exit code is 0.
- Non-interactive run (``--client claude``): NONE of the prompt strings
  appear in the output (no hangs, no prompts).

The four tool-detection predicates are forced to "absent" so the run is
deterministic regardless of which tools happen to be installed on the
machine running the suite. No real third-party install ever fires: every
prompt is declined.

Reference: spec.md BR-005 / BR-007 / BR-008, AC-005 / AC-007 / AC-008,
design.md API Contracts ("Interactive mode: prompt for client + run
status-line + sandbox-config prompts").
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest import mock

from typer.testing import CliRunner

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from etc_installer import cli, install_steps, preflights  # noqa: E402

# Verbatim prompt + INFO-line pins. Drift here means the operator-visible
# surface drifted from spec.md.
_STATUS_LINE_PROMPT = (
    "Install the etc default status line? This will overwrite your "
    "existing status line if you have one. [y/N]"
)
_SANDBOX_PROMPT = (
    "Install the etc default sandbox config? This enables auto-mode "
    "without --dangerously-skip-permissions. [y/N]"
)


def _seed_minimal_dist(dist: Path) -> None:
    """Create a minimal dist/ tree so run_all reaches a 0 exit.

    Mirrors the shape compile-sdlc.py produces, trimmed to the paths the
    eleven install steps read. Enough for the install to complete; the
    point of this test is the interactive surface, not install parity
    (covered by tests/test_etc_installer_parity.py).
    """
    agents = dist / "agents"
    agents.mkdir(parents=True)
    (agents / "backend-developer.md").write_text("# backend\n", encoding="utf-8")

    skill = dist / "skills" / "implement"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("# implement\n", encoding="utf-8")

    code = dist / "standards" / "code"
    code.mkdir(parents=True)
    (code / "clean-code.md").write_text("# clean\n", encoding="utf-8")

    profiles_dir = dist / "standards" / "code" / "profiles" / "python"
    profiles_dir.mkdir(parents=True)
    (profiles_dir / "detection.yaml").write_text("name: python\n", encoding="utf-8")

    hooks = dist / "hooks"
    hooks.mkdir(parents=True)
    (hooks / "check-test-exists.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")

    sdlc = dist / "sdlc"
    sdlc.mkdir(parents=True)
    (sdlc / "tracker.py").write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    (sdlc / "dod-templates.json").write_text("{}\n", encoding="utf-8")

    templates = dist / "templates"
    templates.mkdir(parents=True)
    (templates / "agent.md.tmpl").write_text("agent\n", encoding="utf-8")

    scripts = dist / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "detect_profiles.py").write_text(
        "#!/usr/bin/env python3\nimport sys\nsys.exit(0)\n", encoding="utf-8"
    )

    (dist / "settings-hooks.json").write_text(
        json.dumps({"hooks": {"PreToolUse": []}}, indent=2) + "\n",
        encoding="utf-8",
    )


def _force_all_tools_absent() -> object:
    """Context manager patching every tool-detection predicate to False.

    Keeps the run deterministic — the four INFO lines always appear and
    every offer prompt fires — independent of the host machine's tools.
    """
    return mock.patch.multiple(
        install_steps.preflights,
        is_gh_stack_present=mock.DEFAULT,
        is_impeccable_present=mock.DEFAULT,
        is_mergiraf_present=mock.DEFAULT,
        is_google_designmd_present=mock.DEFAULT,
    )


class TestInteractiveDeclineEverything:
    """No --client flag, scripted stdin declines every prompt."""

    def _run(self, tmp_path: Path) -> tuple[int, str, Path]:
        dist = tmp_path / "dist"
        target = tmp_path / "target" / ".claude"
        target.mkdir(parents=True)
        _seed_minimal_dist(dist)

        # stdin script (one answer per line, in prompt order):
        #   1            -> client selection: Claude Code
        #   n            -> impeccable offer (gh-stack is INFO-only)
        #   n            -> Mergiraf offer
        #   n            -> @google/design.md offer
        #   n            -> status-line prompt
        #   n            -> sandbox-config prompt
        stdin_script = "1\nn\nn\nn\nn\nn\n"

        runner = CliRunner()
        with _force_all_tools_absent() as predicates:
            for predicate in predicates.values():
                predicate.return_value = False
            result = runner.invoke(
                cli.app,
                [
                    "--scope",
                    "project",
                    "--dist-dir",
                    str(dist),
                    "--target-dir",
                    str(target),
                ],
                input=stdin_script,
            )
        return result.exit_code, result.output, target

    def test_should_exit_zero_when_declining_every_prompt(
        self, tmp_path: Path
    ) -> None:
        exit_code, output, _ = self._run(tmp_path)
        assert exit_code == 0, f"interactive decline run must exit 0; output={output!r}"

    def test_should_print_status_line_prompt(self, tmp_path: Path) -> None:
        _, output, _ = self._run(tmp_path)
        assert _STATUS_LINE_PROMPT in output, (
            "the status-line prompt must actually fire in interactive mode"
        )

    def test_should_print_sandbox_config_prompt(self, tmp_path: Path) -> None:
        _, output, _ = self._run(tmp_path)
        assert _SANDBOX_PROMPT in output, (
            "the sandbox-config prompt must actually fire in interactive mode"
        )

    def test_should_surface_all_four_third_party_tools_when_absent(
        self, tmp_path: Path
    ) -> None:
        # In INTERACTIVE mode each absent tool is surfaced to the operator:
        # gh-stack is INFO-only (verbatim INFO line, no prompt — private
        # preview), the other three each print a "<tool> not detected."
        # offer line before prompting. (The verbatim INFO lines for the
        # prompted three are rich-rendered/word-wrapped in this path; the
        # byte-for-byte pin is asserted on the non-interactive run below,
        # where they go through plain print().)
        _, output, _ = self._run(tmp_path)
        assert preflights.F010_INFO_LINE in output, "gh-stack INFO line missing"
        assert "impeccable not detected." in output, "impeccable not offered"
        assert "Mergiraf not detected." in output, "Mergiraf not offered"
        assert "@google/design.md not detected." in output, (
            "@google/design.md not offered"
        )

    def test_should_not_write_status_line_key_when_declined(
        self, tmp_path: Path
    ) -> None:
        _, _, target = self._run(tmp_path)
        body = json.loads((target / "settings.json").read_text(encoding="utf-8"))
        assert "statusLine" not in body, (
            "declining the status-line prompt must leave no statusLine key"
        )

    def test_should_not_write_sandbox_permissions_when_declined(
        self, tmp_path: Path
    ) -> None:
        _, _, target = self._run(tmp_path)
        body = json.loads((target / "settings.json").read_text(encoding="utf-8"))
        assert "permissions" not in body, (
            "declining the sandbox-config prompt must leave no permissions block"
        )


class TestNonInteractiveAsksNothing:
    """--client flag set: every prompt is skipped; nothing is asked."""

    def _run(self, tmp_path: Path) -> tuple[int, str]:
        dist = tmp_path / "dist"
        target = tmp_path / "target" / ".claude"
        target.mkdir(parents=True)
        _seed_minimal_dist(dist)

        runner = CliRunner()
        with _force_all_tools_absent() as predicates:
            for predicate in predicates.values():
                predicate.return_value = False
            result = runner.invoke(
                cli.app,
                [
                    "--client",
                    "claude",
                    "--scope",
                    "project",
                    "--dist-dir",
                    str(dist),
                    "--target-dir",
                    str(target),
                ],
                # No stdin: a non-interactive run must never block on input.
                input="",
            )
        return result.exit_code, result.output

    def test_should_exit_zero_when_non_interactive(self, tmp_path: Path) -> None:
        exit_code, output = self._run(tmp_path)
        assert exit_code == 0, f"non-interactive run must exit 0; output={output!r}"

    def test_should_not_print_status_line_prompt_when_non_interactive(
        self, tmp_path: Path
    ) -> None:
        _, output = self._run(tmp_path)
        assert _STATUS_LINE_PROMPT not in output, (
            "non-interactive run must NOT print the status-line prompt"
        )

    def test_should_not_print_sandbox_config_prompt_when_non_interactive(
        self, tmp_path: Path
    ) -> None:
        _, output = self._run(tmp_path)
        assert _SANDBOX_PROMPT not in output, (
            "non-interactive run must NOT print the sandbox-config prompt"
        )

    def test_should_print_all_four_info_lines_verbatim_when_non_interactive(
        self, tmp_path: Path
    ) -> None:
        # Non-interactive does not PROMPT, but it still informs the
        # operator which tools are missing — offer_install prints the
        # verbatim INFO line (plain print, byte-for-byte) in
        # NON_INTERACTIVE mode (AC-005). All four appear when absent.
        _, output = self._run(tmp_path)
        assert preflights.F010_INFO_LINE in output, "gh-stack INFO line missing"
        assert preflights.F011_INFO_LINE in output, "impeccable INFO line missing"
        assert preflights.F016_INFO_LINE in output, "Mergiraf INFO line missing"
        assert preflights.F018_INFO_LINE in output, "@google/design.md INFO line missing"
