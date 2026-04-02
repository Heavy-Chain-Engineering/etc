"""Tests for compile-sdlc.py.

Validates that the compiler produces correct output from the SDLC DSL spec.
Tests inspect the existing compiled artifacts in dist/ and verify structure,
content, and correctness of the generated files.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
DIST_DIR = REPO_ROOT / "dist"
SETTINGS_HOOKS_PATH = DIST_DIR / "settings-hooks.json"

EXPECTED_GATE_EVENTS = frozenset({
    "UserPromptSubmit",
    "PreToolUse",
    "PostToolUse",
    "TaskCreated",
    "TaskCompleted",
    "SubagentStart",
    "SubagentStop",
    "Stop",
    "ConfigChange",
    "SessionStart",
})

EXPECTED_PHASES = frozenset({
    "bootstrap",
    "spec",
    "design",
    "decompose",
    "build",
    "verify",
    "ship",
    "evaluate",
})

EXPECTED_AGENTS = frozenset({
    "sem.md",
    "backend-developer.md",
    "frontend-developer.md",
    "architect.md",
    "code-reviewer.md",
    "verifier.md",
    "security-reviewer.md",
    "product-manager.md",
    "product-owner.md",
})


@pytest.fixture(scope="module")
def hooks_json() -> dict[str, Any]:
    """Load and parse dist/settings-hooks.json once for all tests."""
    assert SETTINGS_HOOKS_PATH.exists(), (
        f"Compiled artifact not found: {SETTINGS_HOOKS_PATH}. "
        f"Run 'python3 compile-sdlc.py spec/etc_sdlc.yaml' first."
    )
    content = SETTINGS_HOOKS_PATH.read_text()
    return json.loads(content)


@pytest.fixture(scope="module")
def dod_templates() -> dict[str, Any]:
    """Load and parse dist/sdlc/dod-templates.json once for all tests."""
    dod_path = DIST_DIR / "sdlc" / "dod-templates.json"
    assert dod_path.exists(), (
        f"Compiled artifact not found: {dod_path}. "
        f"Run 'python3 compile-sdlc.py spec/etc_sdlc.yaml' first."
    )
    content = dod_path.read_text()
    return json.loads(content)


# -- Test 1: Valid JSON -------------------------------------------------------


def test_should_produce_valid_json(hooks_json: dict[str, Any]) -> None:
    """dist/settings-hooks.json must be valid JSON with a 'hooks' key."""
    # Arrange — hooks_json fixture already parsed the file

    # Act — access the top-level structure
    hooks = hooks_json.get("hooks")

    # Assert
    assert hooks is not None, "Top-level 'hooks' key missing from settings-hooks.json"
    assert isinstance(hooks, dict), "'hooks' value must be a dict"


# -- Test 2: All gate events present ------------------------------------------


def test_should_include_all_gate_events(hooks_json: dict[str, Any]) -> None:
    """settings-hooks.json must contain entries for all 10 gate events."""
    # Arrange
    hooks = hooks_json["hooks"]
    actual_events = frozenset(hooks.keys())

    # Act — compare sets
    missing = EXPECTED_GATE_EVENTS - actual_events

    # Assert
    assert not missing, f"Missing gate events in settings-hooks.json: {missing}"


# -- Test 3: Role text in prompt hooks ----------------------------------------


class TestShouldIncludeRoleInPromptHooks:
    """Prompt-type hooks must have their prompt field prefixed with role text."""

    def test_should_start_with_role_when_user_prompt_submit(
        self, hooks_json: dict[str, Any]
    ) -> None:
        """UserPromptSubmit prompt must start with 'You are the VP of Engineering'."""
        # Arrange
        hook_entries = hooks_json["hooks"]["UserPromptSubmit"]
        prompt_hooks = _extract_hooks_by_type(hook_entries, "prompt")

        # Act
        first_prompt = prompt_hooks[0]["prompt"]

        # Assert
        assert first_prompt.startswith("You are the VP of Engineering"), (
            f"UserPromptSubmit prompt does not start with expected role. "
            f"Got: {first_prompt[:80]!r}"
        )

    def test_should_start_with_role_when_task_created(
        self, hooks_json: dict[str, Any]
    ) -> None:
        """TaskCreated prompt must start with 'You are a senior engineering manager'."""
        # Arrange
        hook_entries = hooks_json["hooks"]["TaskCreated"]
        prompt_hooks = _extract_hooks_by_type(hook_entries, "prompt")

        # Act
        first_prompt = prompt_hooks[0]["prompt"]

        # Assert
        assert first_prompt.startswith("You are a senior engineering manager"), (
            f"TaskCreated prompt does not start with expected role. "
            f"Got: {first_prompt[:80]!r}"
        )

    def test_should_be_agent_type_with_adversarial_role_when_subagent_stop(
        self, hooks_json: dict[str, Any]
    ) -> None:
        """SubagentStop must be an agent hook with adversarial/hostile role text."""
        # Arrange
        hook_entries = hooks_json["hooks"]["SubagentStop"]
        agent_hooks = _extract_hooks_by_type(hook_entries, "agent")

        # Act — the SubagentStop gate should now be type 'agent', not 'prompt'
        assert len(agent_hooks) > 0, (
            "SubagentStop has no agent-type hooks. "
            "Expected adversarial-review to be type 'agent'."
        )
        role_text = agent_hooks[0]["prompt"].lower()

        # Assert — role text must contain adversarial framing
        assert "hostile" in role_text or "adversarial" in role_text, (
            f"SubagentStop agent role does not contain 'hostile' or 'adversarial'. "
            f"Got: {agent_hooks[0]['prompt'][:120]!r}"
        )


# -- Test 4: Correct script references ----------------------------------------


class TestShouldReferenceCorrectScripts:
    """Command hooks must reference scripts under ~/.claude/hooks/."""

    def test_should_reference_hook_path_when_command_type(
        self, hooks_json: dict[str, Any]
    ) -> None:
        """All command-type hooks must reference ~/.claude/hooks/<script>.sh."""
        # Arrange
        all_command_hooks = _extract_all_hooks_by_type(hooks_json, "command")

        # Act & Assert
        for hook in all_command_hooks:
            command = hook.get("command", "")
            assert command.startswith("~/.claude/hooks/"), (
                f"Command hook does not reference ~/.claude/hooks/: {command!r}"
            )
            assert command.endswith(".sh"), (
                f"Command hook does not reference a .sh script: {command!r}"
            )

    def test_should_reference_check_test_exists_when_edit_write_gate(
        self, hooks_json: dict[str, Any]
    ) -> None:
        """PreToolUse Edit|Write matcher must include check-test-exists.sh."""
        # Arrange
        pre_tool_entries = hooks_json["hooks"]["PreToolUse"]
        edit_write_hooks = _extract_hooks_for_matcher(pre_tool_entries, "Edit|Write")
        command_hooks = [h for h in edit_write_hooks if h["type"] == "command"]
        commands = [h["command"] for h in command_hooks]

        # Assert
        assert "~/.claude/hooks/check-test-exists.sh" in commands

    def test_should_reference_check_phase_gate_when_edit_write_gate(
        self, hooks_json: dict[str, Any]
    ) -> None:
        """PreToolUse Edit|Write matcher must include check-phase-gate.sh."""
        # Arrange
        pre_tool_entries = hooks_json["hooks"]["PreToolUse"]
        edit_write_hooks = _extract_hooks_for_matcher(pre_tool_entries, "Edit|Write")
        command_hooks = [h for h in edit_write_hooks if h["type"] == "command"]
        commands = [h["command"] for h in command_hooks]

        # Assert
        assert "~/.claude/hooks/check-phase-gate.sh" in commands, (
            "PreToolUse Edit|Write hooks must include check-phase-gate.sh "
            f"for phase-aware file gating. Found commands: {commands}"
        )

    def test_should_reference_block_dangerous_when_bash_gate(
        self, hooks_json: dict[str, Any]
    ) -> None:
        """PreToolUse Bash matcher must include block-dangerous-commands.sh."""
        # Arrange
        pre_tool_entries = hooks_json["hooks"]["PreToolUse"]
        bash_hooks = _extract_hooks_for_matcher(pre_tool_entries, "Bash")
        command_hooks = [h for h in bash_hooks if h["type"] == "command"]
        commands = [h["command"] for h in command_hooks]

        # Assert
        assert "~/.claude/hooks/block-dangerous-commands.sh" in commands


# -- Test 5: Skill directory ---------------------------------------------------


def test_should_create_skill_directory() -> None:
    """dist/skills/implement/SKILL.md must exist."""
    # Arrange
    skill_path = DIST_DIR / "skills" / "implement" / "SKILL.md"

    # Act — just check existence and non-emptiness

    # Assert
    assert skill_path.exists(), f"Skill file not found: {skill_path}"
    assert skill_path.stat().st_size > 0, "SKILL.md exists but is empty"


# -- Test 6: Agent definitions -------------------------------------------------


def test_should_copy_agent_definitions() -> None:
    """dist/agents/ must contain sem.md, backend-developer.md, and others."""
    # Arrange
    agents_dir = DIST_DIR / "agents"
    actual_agents = frozenset(f.name for f in agents_dir.glob("*.md"))

    # Act
    missing = EXPECTED_AGENTS - actual_agents

    # Assert
    assert agents_dir.exists(), f"Agents directory not found: {agents_dir}"
    assert not missing, f"Missing agent definitions: {missing}"


# -- Test 7: DoD templates with all 8 phases ----------------------------------


def test_should_generate_dod_templates_when_all_phases_present(
    dod_templates: dict[str, Any],
) -> None:
    """dist/sdlc/dod-templates.json must contain all 8 SDLC phases."""
    # Arrange
    actual_phases = frozenset(dod_templates.keys())

    # Act
    missing = EXPECTED_PHASES - actual_phases

    # Assert
    assert not missing, f"Missing phases in dod-templates.json: {missing}"


def test_should_include_dod_items_when_phase_present(
    dod_templates: dict[str, Any],
) -> None:
    """Each phase in dod-templates.json must have a non-empty 'dod' list."""
    # Arrange & Act
    empty_phases = [
        phase for phase, data in dod_templates.items()
        if not data.get("dod")
    ]

    # Assert
    assert not empty_phases, (
        f"Phases with empty DoD lists: {empty_phases}"
    )


# -- Helpers -------------------------------------------------------------------


def _extract_hooks_by_type(
    hook_entries: list[dict[str, Any]], hook_type: str
) -> list[dict[str, Any]]:
    """Extract hooks of a specific type from a list of hook entry groups."""
    result: list[dict[str, Any]] = []
    for entry in hook_entries:
        for hook in entry.get("hooks", []):
            if hook.get("type") == hook_type:
                result.append(hook)
    return result


def _extract_all_hooks_by_type(
    hooks_json: dict[str, Any], hook_type: str
) -> list[dict[str, Any]]:
    """Extract all hooks of a specific type across all events."""
    result: list[dict[str, Any]] = []
    for _event, entries in hooks_json.get("hooks", {}).items():
        result.extend(_extract_hooks_by_type(entries, hook_type))
    return result


def _extract_hooks_for_matcher(
    hook_entries: list[dict[str, Any]], matcher: str
) -> list[dict[str, Any]]:
    """Extract hooks from entries that match a specific matcher string."""
    result: list[dict[str, Any]] = []
    for entry in hook_entries:
        if entry.get("matcher") == matcher:
            result.extend(entry.get("hooks", []))
    return result
