"""preflights — third-party-tool preflights (gh-stack, impeccable,
Mergiraf, @google/design.md).

Reproduces install.sh:196-274's preflight chain in pure Python. The
module exposes:

- Four byte-for-byte INFO_LINE constants (``F010_INFO_LINE``,
  ``F011_INFO_LINE``, ``F016_INFO_LINE``, ``F018_INFO_LINE``) sourced
  verbatim from install.sh:196-199 (AC-005, BR-005).
- ``OperatorMode`` enum (INTERACTIVE / NON_INTERACTIVE) classifying the
  operator's interaction posture. install.sh's ``CLIENT_FLAG`` set →
  NON_INTERACTIVE; unset → INTERACTIVE.
- ``offer_install`` — analog of install.sh:201-235's ``offer_install``
  bash function. NON_INTERACTIVE prints the verbatim info line and
  returns. INTERACTIVE prompts via rich.prompt.Prompt.ask and on
  affirmative answer runs the install argv via subprocess.run with
  shell=False (argv-list form, never a shell string).
- ``is_gh_stack_present``, ``is_impeccable_present``,
  ``is_mergiraf_present``, ``is_google_designmd_present`` — tool
  detection predicates. The first three use shutil.which (the Python
  analog of bash's ``command -v``). The fourth probes ``npm list -g
  --depth=0 @google/design.md`` (consistent with the offline-friendly
  detection install.sh:271 uses).

The preflights are non-blocking by contract (F010 AC11, F011 AC15,
F018 — all "informational only"). offer_install never calls sys.exit
or raises SystemExit. A non-zero install exit prints a warning and
returns; the caller continues with the install.

Per design.md Module Structure this module is Infrastructure-tier and
MUST NOT import from cli or install_steps.
"""

from __future__ import annotations

import enum
import shutil
import subprocess

from rich.console import Console
from rich.prompt import Prompt

# ── INFO_LINE constants — AC-005 byte-for-byte from install.sh:196-199 ───
#
# F021 diagnostic-discipline evidence (E501 line-too-long suppression):
# AC-005 mandates byte-for-byte preservation of the four INFO lines from
# install.sh:196-199. Splitting them across lines via concatenation
# would still satisfy the runtime byte-for-byte check, but pinning the
# canonical form as single-line literals here makes the source-of-truth
# textually identical to install.sh — drift is detectable by a one-line
# diff against the original install.sh. The four pins below are the ONLY
# place in the codebase where the verbatim INFO lines live; downstream
# consumers (install_steps.py) import these constants by name.

F010_INFO_LINE = "INFO: gh-stack not detected. Stacked-PR builds (etc F010+) require gh-stack (GitHub's official extension, currently in private preview at https://github.github.com/gh-stack/). Install via: gh extension install github/gh-stack (or equivalent). Single-wave builds work without it."  # noqa: E501
F011_INFO_LINE = "INFO: impeccable not detected. /design phase requires impeccable (etc F011+). Install via: npm install -g impeccable (or equivalent). Features without a /design phase work without it."  # noqa: E501
F016_INFO_LINE = "INFO: Mergiraf not detected. Semantic merge conflicts (etc F016+) are resolved manually without it. Install via: brew install mergiraf (macOS) | cargo install mergiraf | https://mergiraf.org for other platforms."  # noqa: E501
F018_INFO_LINE = "INFO: @google/design.md not detected. /design phase output (etc F018+) validates against Google's DESIGN.md spec (https://github.com/google-labs-code/design.md). Install via: npm install -g @google/design.md (or run via npx). Features without /design work without it."  # noqa: E501


class OperatorMode(enum.Enum):
    """Operator interaction posture.

    INTERACTIVE: no --client flag; prompt the operator before any
    third-party install. install.sh:208's ``CLIENT_FLAG`` unset branch.

    NON_INTERACTIVE: --client flag set; print the verbatim info line
    and skip without prompting. install.sh:208's ``CLIENT_FLAG`` set
    branch.
    """

    INTERACTIVE = "interactive"
    NON_INTERACTIVE = "non_interactive"


# Module-level console for non-prompted output (info line echo,
# install-failure warning). Rich's default Console writes to stdout so
# the verbatim info lines are captured by capsys in tests.
_console = Console()


def offer_install(
    tool_name: str,
    info_line: str,
    install_command_argv: list[str],
    mode: OperatorMode,
) -> None:
    """Offer to install a third-party tool.

    NON_INTERACTIVE: print ``info_line`` verbatim to stdout and return.
    INTERACTIVE: print the tool name + info line, prompt the operator
    via rich.prompt.Prompt.ask, and on affirmative answer (``y``/``yes``,
    case-insensitive) invoke ``install_command_argv`` via
    ``subprocess.run`` with ``shell=False`` (argv-list form). On
    declined answer or empty input, print a skip line and return. On
    non-zero install exit, print a warning and return — the preflight
    is informational, never aborts.

    Mirrors install.sh:201-235's bash ``offer_install`` function.

    Args:
        tool_name: Display name (e.g. ``"Mergiraf"``).
        info_line: Verbatim INFO line — printed in NON_INTERACTIVE mode
            and shown to the operator in INTERACTIVE mode.
        install_command_argv: argv list (NOT a shell string) for the
            install invocation. Subprocess runs with shell=False.
        mode: OperatorMode.NON_INTERACTIVE skips prompting and
            invoking; INTERACTIVE prompts y/N and conditionally runs.
    """
    if mode is OperatorMode.NON_INTERACTIVE:
        # Verbatim info-line echo so the test grep on capsys.out finds it.
        # _console.print would re-render via rich's highlighter; print()
        # is the byte-for-byte path.
        print(info_line)
        return

    # INTERACTIVE: prompt + conditional install.
    _console.print()
    _console.print(f"  {tool_name} not detected.")
    _console.print(f"  {info_line}")
    display_cmd = " ".join(install_command_argv)
    answer = Prompt.ask(
        f"  Install now via: {display_cmd} ? [y/N]",
        default="",
        show_default=False,
    )
    if answer.strip().lower() not in {"y", "yes"}:
        _console.print(f"  Skipped. Install later via: {display_cmd}")
        return

    _console.print(f"  Running: {display_cmd}")
    completed = subprocess.run(install_command_argv, check=False)
    if completed.returncode == 0:
        _console.print(f"  [green]✓[/green] {tool_name} installed")
    else:
        _console.print(
            f"  [yellow]⚠[/yellow] {tool_name} install failed "
            f"(exit {completed.returncode}). Continuing without it."
        )


def is_gh_stack_present() -> bool:
    """Return True if ``gh-stack`` is on PATH.

    Mirrors install.sh:244's ``command -v gh-stack`` probe.
    """
    return shutil.which("gh-stack") is not None


def is_impeccable_present() -> bool:
    """Return True if ``impeccable`` is on PATH.

    Mirrors install.sh:251's ``command -v impeccable`` probe. The bash
    branch also checks for the Claude Code skill directory at
    ``$HOME/.claude/skills/impeccable``; that check is composed by the
    caller (install_steps.py) — this predicate covers only the
    command-on-PATH probe.
    """
    return shutil.which("impeccable") is not None


def is_mergiraf_present() -> bool:
    """Return True if ``mergiraf`` is on PATH.

    Mirrors install.sh:258's ``command -v mergiraf`` probe.
    """
    return shutil.which("mergiraf") is not None


def is_google_designmd_present() -> bool:
    """Return True if ``@google/design.md`` is installed globally via npm.

    Mirrors install.sh:271's ``npm list -g --depth=0 @google/design.md``
    probe. Detection by exit code: zero → present; non-zero → absent.
    If ``npm`` itself is not on PATH, FileNotFoundError is caught and
    treated as absent (operator can install design.md after installing
    Node tooling).
    """
    try:
        completed = subprocess.run(
            ["npm", "list", "-g", "--depth=0", "@google/design.md"],
            check=False,
            capture_output=True,
        )
    except FileNotFoundError:
        # npm not on PATH — package cannot be present.
        return False
    return completed.returncode == 0
