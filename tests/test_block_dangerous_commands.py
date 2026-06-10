"""Behavioral tests for hooks/block-dangerous-commands.sh (audit init 8).

First dedicated test file for this hook. Focus: the force-push rule must
block bare ``--force`` / ``-f`` while ALLOWING ``--force-with-lease`` — the
safe remediation the hook's own error message recommends. The old
bare-substring match (``--force``) blocked the remediation too, a recurring
operator-attention drain.

House pattern: invoke the hook as a subprocess with a PreToolUse-shaped
JSON payload on stdin; assert on the exit code (0 = allow, 2 = block).
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOK = REPO_ROOT / "hooks" / "block-dangerous-commands.sh"


def _run_hook(command: str) -> subprocess.CompletedProcess[str]:
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
    return subprocess.run(
        ["bash", str(HOOK)],
        input=payload,
        capture_output=True,
        text=True,
        timeout=15,
    )


def test_force_with_lease_is_allowed() -> None:
    """The remediation the error message recommends must not be blocked."""
    result = _run_hook("git push --force-with-lease internal my-branch")
    assert result.returncode == 0, (
        f"--force-with-lease must be ALLOWED (it is the safe remediation the "
        f"hook itself recommends); got exit {result.returncode}: {result.stderr}"
    )


def test_bare_force_push_still_blocks() -> None:
    result = _run_hook("git push --force internal my-branch")
    assert result.returncode == 2, "bare --force push must still block"
    assert "Force push" in result.stderr


def test_force_at_end_of_command_still_blocks() -> None:
    result = _run_hook("git push internal my-branch --force")
    assert result.returncode == 2, "--force as the final token must still block"


def test_short_f_force_push_still_blocks() -> None:
    result = _run_hook("git push -f internal my-branch")
    assert result.returncode == 2, "git push -f must still block"
    assert "Force push" in result.stderr
