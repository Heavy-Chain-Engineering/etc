"""Tests for hooks/block-config-changes.sh.

Verifies that the config-change hook blocks agent modifications to settings,
skills, and other governance files while allowing policy-controlled changes.
"""

from __future__ import annotations

from typing import Any

import pytest


HOOK_NAME = "block-config-changes.sh"

BLOCKED_SOURCES = [
    "project_settings",
    "user_settings",
    "local_settings",
    "skills",
]


@pytest.mark.parametrize("source", BLOCKED_SOURCES)
def test_should_block_when_non_policy_source(
    run_hook: Any, source: str
) -> None:
    """Hook must exit 2 for any source that is not policy_settings."""
    result = run_hook(HOOK_NAME, {"source": source, "file_path": "settings.json"})

    assert result.exit_code == 2


def test_should_block_when_project_settings(run_hook: Any) -> None:
    result = run_hook(
        HOOK_NAME,
        {"source": "project_settings", "file_path": ".claude/settings.json"},
    )

    assert result.exit_code == 2


def test_should_block_when_user_settings(run_hook: Any) -> None:
    result = run_hook(
        HOOK_NAME,
        {"source": "user_settings", "file_path": "~/.claude/settings.json"},
    )

    assert result.exit_code == 2


def test_should_block_when_local_settings(run_hook: Any) -> None:
    result = run_hook(
        HOOK_NAME,
        {"source": "local_settings", "file_path": ".claude/settings.local.json"},
    )

    assert result.exit_code == 2


def test_should_allow_when_policy_settings(run_hook: Any) -> None:
    result = run_hook(
        HOOK_NAME,
        {"source": "policy_settings", "file_path": "policy.json"},
    )

    assert result.exit_code == 0


def test_should_block_when_skills_change(run_hook: Any) -> None:
    result = run_hook(
        HOOK_NAME,
        {"source": "skills", "file_path": "implement.md"},
    )

    assert result.exit_code == 2


def test_should_mention_governance_in_blocked_message(run_hook: Any) -> None:
    result = run_hook(
        HOOK_NAME,
        {"source": "project_settings", "file_path": "settings.json"},
    )

    assert "governance" in result.stderr.lower()


def test_should_mention_sdlc_dsl_in_blocked_message(run_hook: Any) -> None:
    result = run_hook(
        HOOK_NAME,
        {"source": "project_settings", "file_path": "settings.json"},
    )

    assert "SDLC DSL" in result.stderr
