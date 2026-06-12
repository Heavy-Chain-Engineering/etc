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


# -- gh delivery scoping (security review F-2026-06-12) ------------------------
#
# These tests PIN the deliberate decision NOT to block gh delivery commands in
# this hook. The safety-guardrails gate (spec/etc_sdlc.yaml) is
# event=PreToolUse, matcher="Bash" with NO agent scoping: it fires on EVERY
# Bash call, in the MAIN orchestrator session as well as in subagents. The
# orchestrator's LEGITIMATE delivery runs through this exact hook
# (`/janitor` and `/pull-tickets` open PRs with `gh pr create`; /build ships
# PRs), and the PreToolUse Bash payload carries no reliable
# main-session-vs-subagent discriminator. A blanket block here would brick
# legitimate delivery; the correct fix for the janitor-subagent trust boundary
# is a subagent-scoped hook (an operator wiring decision), not a rule in this
# global gate. If a future change adds a blanket gh-delivery block here, these
# tests fail loudly and route the fix to the right layer. See the SCOPING NOTE
# in hooks/block-dangerous-commands.sh.

import pytest  # noqa: E402  (placed next to the tests it parametrizes)


@pytest.mark.parametrize(
    "command",
    [
        'gh pr create --draft --title "janitor: lint cleanup" --body "..."',
        "gh pr create --base main --head claude/janitor/lint-2026-06-12",
        "gh pr merge 42 --squash",
        "gh pr close 42",
        "gh release create v1.2.3 --notes 'release'",
        "gh repo delete owner/throwaway --yes",
    ],
    ids=[
        "gh_pr_create_draft",
        "gh_pr_create_ready",
        "gh_pr_merge",
        "gh_pr_close",
        "gh_release_create",
        "gh_repo_delete",
    ],
)
def test_gh_delivery_commands_are_allowed_by_this_global_hook(command: str) -> None:
    """This global Bash gate must NOT block gh delivery: the orchestrator's
    legitimate PR/release flow runs through it. The janitor-subagent boundary
    is enforced elsewhere (toolset / subagent-scoped hook), not here."""
    result = _run_hook(command)
    assert result.returncode == 0, (
        f"{command!r} must be ALLOWED by this global PreToolUse-Bash hook — the "
        f"orchestrator's legitimate delivery runs through it. If you intended to "
        f"block gh delivery for the janitor subagent, do it in a subagent-scoped "
        f"hook, not here (see the SCOPING NOTE in the hook). "
        f"got exit {result.returncode}: {result.stderr}"
    )


def test_gh_delivery_still_subject_to_other_existing_rules() -> None:
    """Scoping the gh carve-out must not weaken sibling rules: a gh command
    smuggling a blocked bypass flag (--no-verify) is still blocked."""
    result = _run_hook("gh pr merge 42 --merge -- --no-verify")
    assert result.returncode == 2, (
        "an embedded --no-verify must still block even within a gh command line"
    )
    assert "bypass safety" in result.stderr
