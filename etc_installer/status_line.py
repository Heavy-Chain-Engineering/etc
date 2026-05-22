"""status_line — interactive status-line installer.

Implements BR-007 / AC-007 of Ftmp-5afddbce: prompt the operator
(when running INTERACTIVE) to opt into etc's default status line,
which overwrites any existing ``statusLine`` key in the operator's
``settings.json``. On affirmative answer, the installer writes the
``statusLine`` key into ``$TARGET_DIR/settings.json`` (preserving
every other top-level key) AND copies the bundled ``statusline.sh``
shell script into ``$TARGET_DIR/scripts/``.

Non-interactive runs (``--client`` flag set → ``OperatorMode.NON_INTERACTIVE``)
skip the prompt and the install entirely. The status-line install is
operator-opt-in by design — overwriting an operator's custom status
line silently would violate BR-007's overwrite-warning contract.

The verbatim prompt string is defined at module level as
``BR_007_PROMPT_LITERAL`` and printed via Python's built-in ``print()``
(NOT via rich.Console) because rich's Console word-wraps long lines
and would break the byte-for-byte capsys assertion in
``tests/test_etc_installer_status_line.py``. The same pattern is used
in ``etc_installer.preflights`` for the NON_INTERACTIVE INFO_LINE
echo (preflights.py:114).

Per design.md Module Structure this module sits in the Infrastructure
layer and MUST NOT import from cli or install_steps.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from rich.prompt import Prompt

from etc_installer.preflights import OperatorMode

# ── BR-007 verbatim prompt literal ────────────────────────────────────────
#
# spec.md BR-007 mandates this string byte-for-byte. It is asserted in
# tests/test_etc_installer_status_line.py::TestPromptLiteral. The
# E501 line-too-long suppression is justified by F021
# diagnostic-discipline: splitting the literal across concatenated
# strings would still satisfy the runtime byte-for-byte check, but
# pinning the canonical form as a single-line literal here makes the
# source-of-truth textually identical to spec.md and detectable by a
# one-line diff against spec.md BR-007.
BR_007_PROMPT_LITERAL = "Install the etc default status line? This will overwrite your existing status line if you have one. [y/N]"  # noqa: E501

# Path to the bundled statusline.sh asset, copied into
# ``$TARGET_DIR/scripts/`` on affirmative install. Lives alongside this
# module under ``etc_installer/assets/`` so it ships with the package.
_STATUSLINE_ASSET = Path(__file__).resolve().parent / "assets" / "statusline.sh"

# Canonical ``statusLine`` payload written into settings.json. Mirrors
# the operator-facing shape in ~/.claude/settings.json:220-224 (the
# author's own working settings) — type=command, command points at
# ``~/.claude/statusline.sh``, padding=1. Operators on ``--scope
# project`` get ``./.claude/scripts/statusline.sh`` instead; the path
# is resolved at install time from ``target_dir``.
_STATUS_LINE_KEY = "statusLine"


def install_status_line(target_dir: Path, mode: OperatorMode) -> None:
    """Install (or skip) the etc default status line.

    INTERACTIVE: print the verbatim BR-007 prompt to stdout, then read
    operator input via ``rich.prompt.Prompt.ask``. On ``y`` / ``yes``
    (case-insensitive), write the ``statusLine`` key into
    ``target_dir/settings.json`` (preserving every other top-level
    key) and copy ``statusline.sh`` into ``target_dir/scripts/``. On
    ``n``, empty input, or any other answer, skip.

    NON_INTERACTIVE: skip the prompt AND the install entirely. The
    operator's settings.json is left untouched. No ``scripts/``
    directory is created.

    Args:
        target_dir: Resolved install target — either ``$HOME/.claude``
            (``--scope global``) or ``$PWD/.claude`` (``--scope
            project``). The directory must already exist; this
            function does NOT create ``target_dir`` itself.
        mode: OperatorMode.INTERACTIVE → prompt + conditional install;
            OperatorMode.NON_INTERACTIVE → skip entirely.
    """
    if mode is OperatorMode.NON_INTERACTIVE:
        return

    # Verbatim BR-007 echo via plain print() — rich.Console word-wraps
    # long lines and would break the byte-for-byte capsys assertion.
    print(BR_007_PROMPT_LITERAL)
    answer = Prompt.ask("", default="n", show_default=False)

    if answer.strip().lower() not in {"y", "yes"}:
        return

    _write_status_line_key(target_dir)
    _copy_statusline_asset(target_dir)


def _write_status_line_key(target_dir: Path) -> None:
    """Write the ``statusLine`` key into ``target_dir/settings.json``.

    Reads the existing settings.json (must exist — created by an
    earlier install step), merges the canonical statusLine payload
    into the top-level dict, and writes back via
    ``json.dumps(merged, indent=2) + "\\n"``. Every other top-level
    key is preserved byte-for-byte.

    The command path uses ``$TARGET_DIR/scripts/statusline.sh`` (relative
    to settings.json) so the entry resolves the same way regardless of
    ``--scope global`` vs ``--scope project``.
    """
    settings_path = target_dir / "settings.json"
    body = json.loads(settings_path.read_text(encoding="utf-8"))
    body[_STATUS_LINE_KEY] = {
        "type": "command",
        "command": str(target_dir / "scripts" / "statusline.sh"),
        "padding": 1,
    }
    settings_path.write_text(
        json.dumps(body, indent=2) + "\n",
        encoding="utf-8",
    )


def _copy_statusline_asset(target_dir: Path) -> None:
    """Copy the bundled statusline.sh into ``target_dir/scripts/``.

    Creates ``target_dir/scripts/`` if absent, then copies
    ``etc_installer/assets/statusline.sh`` to
    ``target_dir/scripts/statusline.sh``. Uses ``shutil.copy2`` so the
    executable bit is preserved (the asset is committed as +x).
    """
    scripts_dir = target_dir / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(_STATUSLINE_ASSET, scripts_dir / "statusline.sh")
