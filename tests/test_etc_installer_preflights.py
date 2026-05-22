"""Tests for etc_installer.preflights — verbatim INFO_LINEs + offer_install.

Covers AC-005 (byte-for-byte INFO_LINE preservation from install.sh:196-199)
and the preflights AC from Ftmp-5afddbce task 003:

- F010_INFO_LINE, F011_INFO_LINE, F016_INFO_LINE, F018_INFO_LINE constants
  are byte-for-byte identical to install.sh:196-199.
- OperatorMode is an enum with INTERACTIVE / NON_INTERACTIVE members.
- offer_install(tool_name, info_line, install_command_argv, mode) prints
  the verbatim info_line and skips when mode is NON_INTERACTIVE.
- offer_install prompts y/N via rich.prompt.Prompt.ask and runs the
  argv-list install command via subprocess.run when mode is INTERACTIVE
  and the answer is affirmative.
- offer_install does NOT call sys.exit / raise SystemExit on tool absence
  (non-blocking by contract — F010 AC11, F011 AC15, F018 AC).
- Tool-presence predicates is_gh_stack_present, is_impeccable_present,
  is_mergiraf_present, is_google_designmd_present return bool and probe
  via shutil.which (or npm list -g for design.md, per
  test_install_sh_google_designmd_preflight's DetectionApproach class).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from etc_installer import preflights  # noqa: E402

# ── INFO_LINE byte-for-byte pins (AC-005) ────────────────────────────────

# These literals are the canonical source. They are copied from
# install.sh:196-199 (the corrected post-e6b4274 form using
# github/gh-stack — NOT the pre-correction jiazh/gh-stack). The task
# YAML AC-005 source-of-truth is install.sh:196-199 verbatim.

_F010 = (
    "INFO: gh-stack not detected. Stacked-PR builds (etc F010+) require "
    "gh-stack (GitHub's official extension, currently in private preview "
    "at https://github.github.com/gh-stack/). Install via: gh extension "
    "install github/gh-stack (or equivalent). Single-wave builds work "
    "without it."
)

_F011 = (
    "INFO: impeccable not detected. /design phase requires impeccable "
    "(etc F011+). Install via: npm install -g impeccable (or "
    "equivalent). Features without a /design phase work without it."
)

_F016 = (
    "INFO: Mergiraf not detected. Semantic merge conflicts (etc F016+) "
    "are resolved manually without it. Install via: brew install mergiraf "
    "(macOS) | cargo install mergiraf | https://mergiraf.org for other "
    "platforms."
)

_F018 = (
    "INFO: @google/design.md not detected. /design phase output (etc "
    "F018+) validates against Google's DESIGN.md spec "
    "(https://github.com/google-labs-code/design.md). Install via: npm "
    "install -g @google/design.md (or run via npx). Features without "
    "/design work without it."
)


class TestInfoLineConstants:
    """AC-005: four module-level constants byte-for-byte from install.sh:196-199."""

    def test_should_expose_f010_info_line_verbatim(self) -> None:
        assert preflights.F010_INFO_LINE == _F010

    def test_should_expose_f011_info_line_verbatim(self) -> None:
        assert preflights.F011_INFO_LINE == _F011

    def test_should_expose_f016_info_line_verbatim(self) -> None:
        assert preflights.F016_INFO_LINE == _F016

    def test_should_expose_f018_info_line_verbatim(self) -> None:
        assert preflights.F018_INFO_LINE == _F018


class TestOperatorMode:
    """OperatorMode enum exposes INTERACTIVE and NON_INTERACTIVE members."""

    def test_should_expose_interactive_and_non_interactive_members(self) -> None:
        assert hasattr(preflights, "OperatorMode")
        assert preflights.OperatorMode.INTERACTIVE != preflights.OperatorMode.NON_INTERACTIVE


class TestOfferInstallNonInteractive:
    """Mode == NON_INTERACTIVE: print info_line verbatim; never prompt; never run."""

    def test_should_print_info_line_when_mode_is_non_interactive(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Act
        preflights.offer_install(
            tool_name="gh-stack",
            info_line=preflights.F010_INFO_LINE,
            install_command_argv=["gh", "extension", "install", "github/gh-stack"],
            mode=preflights.OperatorMode.NON_INTERACTIVE,
        )

        # Assert
        out = capsys.readouterr().out
        assert preflights.F010_INFO_LINE in out

    def test_should_not_prompt_when_mode_is_non_interactive(self) -> None:
        # Arrange — patch Prompt.ask to assert it is never invoked
        with mock.patch.object(
            preflights.Prompt, "ask", side_effect=AssertionError("must not prompt")
        ):
            # Act + Assert (side_effect on prompt raises if hit)
            preflights.offer_install(
                tool_name="gh-stack",
                info_line=preflights.F010_INFO_LINE,
                install_command_argv=["gh", "extension", "install", "github/gh-stack"],
                mode=preflights.OperatorMode.NON_INTERACTIVE,
            )

    def test_should_not_invoke_subprocess_when_mode_is_non_interactive(self) -> None:
        # Arrange — patch subprocess.run to assert it is never invoked
        with mock.patch.object(
            preflights.subprocess, "run", side_effect=AssertionError("must not run")
        ):
            # Act + Assert (side_effect on subprocess raises if hit)
            preflights.offer_install(
                tool_name="gh-stack",
                info_line=preflights.F010_INFO_LINE,
                install_command_argv=["gh", "extension", "install", "github/gh-stack"],
                mode=preflights.OperatorMode.NON_INTERACTIVE,
            )


class TestOfferInstallInteractive:
    """Mode == INTERACTIVE: prompt y/N; on y, run argv-list subprocess."""

    def test_should_run_install_command_when_operator_answers_yes(self) -> None:
        # Arrange — operator answers "y"
        argv = ["npm", "install", "-g", "impeccable"]
        completed = subprocess.CompletedProcess(args=argv, returncode=0)

        with mock.patch.object(preflights.Prompt, "ask", return_value="y"), \
                mock.patch.object(
                    preflights.subprocess, "run", return_value=completed
                ) as run_mock:
            # Act
            preflights.offer_install(
                tool_name="impeccable",
                info_line=preflights.F011_INFO_LINE,
                install_command_argv=argv,
                mode=preflights.OperatorMode.INTERACTIVE,
            )

            # Assert — argv list passed positionally; shell=False
            run_mock.assert_called_once()
            called_args, called_kwargs = run_mock.call_args
            assert called_args[0] == argv
            assert called_kwargs.get("shell", False) is False

    def test_should_skip_install_command_when_operator_answers_no(self) -> None:
        # Arrange — operator answers "n"
        with mock.patch.object(preflights.Prompt, "ask", return_value="n"), \
                mock.patch.object(
                    preflights.subprocess, "run", side_effect=AssertionError("skip")
                ):
            # Act / Assert — must not invoke subprocess
            preflights.offer_install(
                tool_name="impeccable",
                info_line=preflights.F011_INFO_LINE,
                install_command_argv=["npm", "install", "-g", "impeccable"],
                mode=preflights.OperatorMode.INTERACTIVE,
            )

    def test_should_skip_install_command_when_operator_answers_empty(self) -> None:
        # Arrange — operator hits enter (empty / default N)
        with mock.patch.object(preflights.Prompt, "ask", return_value=""), \
                mock.patch.object(
                    preflights.subprocess, "run", side_effect=AssertionError("skip")
                ):
            # Act / Assert
            preflights.offer_install(
                tool_name="impeccable",
                info_line=preflights.F011_INFO_LINE,
                install_command_argv=["npm", "install", "-g", "impeccable"],
                mode=preflights.OperatorMode.INTERACTIVE,
            )


class TestOfferInstallNonBlocking:
    """offer_install never aborts the install on subprocess failure.

    Mirrors F010 AC11 / F011 AC15 contract: the preflight is informational,
    not a hard gate. A non-zero install exit prints a warning and returns.
    """

    def test_should_not_raise_when_subprocess_returns_non_zero(self) -> None:
        # Arrange — operator says yes; npm install fails
        argv = ["npm", "install", "-g", "impeccable"]
        completed = subprocess.CompletedProcess(args=argv, returncode=1)

        with mock.patch.object(preflights.Prompt, "ask", return_value="yes"), \
                mock.patch.object(preflights.subprocess, "run", return_value=completed):
            # Act — must not raise
            preflights.offer_install(
                tool_name="impeccable",
                info_line=preflights.F011_INFO_LINE,
                install_command_argv=argv,
                mode=preflights.OperatorMode.INTERACTIVE,
            )


class TestToolPresencePredicates:
    """Tool-presence predicates return bool via shutil.which / npm list."""

    def test_is_gh_stack_present_returns_true_when_shutil_which_resolves(self) -> None:
        with mock.patch.object(preflights.shutil, "which", return_value="/usr/local/bin/gh-stack"):
            assert preflights.is_gh_stack_present() is True

    def test_is_gh_stack_present_returns_false_when_shutil_which_returns_none(self) -> None:
        with mock.patch.object(preflights.shutil, "which", return_value=None):
            assert preflights.is_gh_stack_present() is False

    def test_is_impeccable_present_returns_true_when_shutil_which_resolves(self) -> None:
        with mock.patch.object(preflights.shutil, "which", return_value="/usr/local/bin/impeccable"):
            assert preflights.is_impeccable_present() is True

    def test_is_impeccable_present_returns_false_when_shutil_which_returns_none(self) -> None:
        with mock.patch.object(preflights.shutil, "which", return_value=None):
            assert preflights.is_impeccable_present() is False

    def test_is_mergiraf_present_returns_true_when_shutil_which_resolves(self) -> None:
        with mock.patch.object(preflights.shutil, "which", return_value="/usr/local/bin/mergiraf"):
            assert preflights.is_mergiraf_present() is True

    def test_is_mergiraf_present_returns_false_when_shutil_which_returns_none(self) -> None:
        with mock.patch.object(preflights.shutil, "which", return_value=None):
            assert preflights.is_mergiraf_present() is False

    def test_is_google_designmd_present_returns_true_when_npm_list_exit_zero(self) -> None:
        # Arrange — `npm list -g --depth=0 @google/design.md` exits zero
        completed = subprocess.CompletedProcess(
            args=["npm", "list", "-g", "--depth=0", "@google/design.md"],
            returncode=0,
        )
        with mock.patch.object(preflights.subprocess, "run", return_value=completed):
            assert preflights.is_google_designmd_present() is True

    def test_is_google_designmd_present_returns_false_when_npm_list_exit_nonzero(self) -> None:
        # Arrange — npm list returns non-zero (package absent)
        completed = subprocess.CompletedProcess(
            args=["npm", "list", "-g", "--depth=0", "@google/design.md"],
            returncode=1,
        )
        with mock.patch.object(preflights.subprocess, "run", return_value=completed):
            assert preflights.is_google_designmd_present() is False

    def test_is_google_designmd_present_returns_false_when_npm_missing(self) -> None:
        # Arrange — `npm` not on PATH at all (FileNotFoundError)
        with mock.patch.object(preflights.subprocess, "run", side_effect=FileNotFoundError):
            assert preflights.is_google_designmd_present() is False
