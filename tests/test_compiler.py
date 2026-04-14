"""Tests for compile-sdlc.py.

Validates that the compiler produces correct output from the SDLC DSL spec.
Tests inspect the existing compiled artifacts in dist/ and verify structure,
content, and correctness of the generated files.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
DIST_DIR = REPO_ROOT / "dist"
SETTINGS_HOOKS_PATH = DIST_DIR / "settings-hooks.json"

EXPECTED_GATE_EVENTS = frozenset({
    # UserPromptSubmit removed in v1.5 — conversation is no longer gated.
    # DoR now lives at /build Step 1 as an artifact preflight, not a prompt gate.
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


def test_should_not_register_userpromptsubmit_gate(
    hooks_json: dict[str, Any],
) -> None:
    """v1.5: the DoR gate moved from UserPromptSubmit to /build Step 1.

    Conversation is no longer gated at the thread boundary — only the
    spec artifact is gated, and only at /build invocation. If someone
    re-adds a UserPromptSubmit hook to the DSL, this test fails loudly
    to preserve the architectural decision: rigor lives at lane
    boundaries, not on every keystroke.

    See RELEASE_NOTES.md v1.5 and spec/hotfix-skill-brief.md for the
    rationale behind the three-lane model (conversation / spec→build /
    hotfix) that this assertion enforces.
    """
    user_prompt_hooks = hooks_json.get("hooks", {}).get("UserPromptSubmit", [])
    assert not user_prompt_hooks, (
        "UserPromptSubmit gate should be absent in v1.5+. DoR lives in "
        "/build Step 1 as an artifact preflight. If you need to re-add a "
        "conversation-level gate, update RELEASE_NOTES and this test "
        "intentionally."
    )


def test_should_exempt_builtin_todos_from_task_readiness(
    hooks_json: dict[str, Any],
) -> None:
    """The task-readiness TaskCreated hook must exempt built-in TaskCreate
    todos from formal ETC DoR evaluation.

    Regression test: Claude Code's built-in TaskCreate tool creates
    lightweight todos (`{title, status, activeForm}`) that don't have the
    fields the ETC DoR checklist requires (`task_id`, `files_in_scope`,
    `acceptance_criteria`, `requires_reading`). Without a shape check, the
    task-readiness gate rejects every built-in todo an agent tries to
    create, blocking in-context progress tracking inside skills like
    /init-project and /build.
    """
    task_created_hooks = hooks_json.get("hooks", {}).get("TaskCreated", [])
    assert task_created_hooks, "No TaskCreated hooks registered"

    readiness_prompts: list[str] = []
    for matcher_group in task_created_hooks:
        for handler in matcher_group.get("hooks", []):
            prompt_text = handler.get("prompt", "")
            if "Definition of Ready" in prompt_text:
                readiness_prompts.append(prompt_text)

    assert readiness_prompts, "task-readiness hook not found on TaskCreated"

    for prompt_text in readiness_prompts:
        assert "SHAPE CHECK" in prompt_text, (
            "task-readiness prompt missing SHAPE CHECK section — built-in "
            "TaskCreate todos will be rejected"
        )
        assert "built-in TaskCreate" in prompt_text or "built-in todo" in prompt_text, (
            "task-readiness prompt does not name the built-in TaskCreate "
            "exemption — future maintainers will not understand why the "
            "shape check exists"
        )
        # Must name at least one of the formal task fields as the discriminator
        assert "task_id" in prompt_text and "files_in_scope" in prompt_text, (
            "task-readiness prompt must name formal task fields "
            "(task_id, files_in_scope) so the AI evaluator knows how to "
            "discriminate formal tasks from built-in todos"
        )
        # Shape check must come BEFORE the DoR checklist
        idx_shape = prompt_text.find("SHAPE CHECK")
        idx_checklist = prompt_text.find("A task is NOT ready")
        assert idx_shape < idx_checklist, (
            "SHAPE CHECK must appear BEFORE the 'task is NOT ready' "
            "checklist so the AI evaluator short-circuits on built-in todos"
        )


def test_should_exempt_builtin_todos_from_task_completion(
    hooks_json: dict[str, Any],
) -> None:
    """The task-completion TaskCompleted hook must exempt built-in
    TaskCreate todo completions from formal ETC DoD verification.

    Regression test: same class of bug as task-readiness — the
    TaskCompleted event fires for both formal ETC task YAML files and
    lightweight built-in todos. Running the full DoD verification
    (coverage, type check, test suite) on a built-in todo is nonsensical.
    """
    task_completed_hooks = hooks_json.get("hooks", {}).get("TaskCompleted", [])
    assert task_completed_hooks, "No TaskCompleted hooks registered"

    dod_prompts: list[str] = []
    for matcher_group in task_completed_hooks:
        for handler in matcher_group.get("hooks", []):
            prompt_text = handler.get("prompt", "")
            if "Definition of Done" in prompt_text:
                dod_prompts.append(prompt_text)

    assert dod_prompts, "task-completion hook not found on TaskCompleted"

    for prompt_text in dod_prompts:
        assert "SHAPE CHECK" in prompt_text, (
            "task-completion prompt missing SHAPE CHECK section — built-in "
            "todo completions will trigger full DoD verification"
        )
        assert "built-in TaskCreate" in prompt_text or "built-in todo" in prompt_text, (
            "task-completion prompt does not name the built-in TaskCreate "
            "exemption"
        )
        # Must name at least one formal task field
        assert "task_id" in prompt_text and "files_in_scope" in prompt_text, (
            "task-completion prompt must name formal task fields as the "
            "discriminator between formal tasks and built-in todos"
        )
        # Shape check before DoD verification
        idx_shape = prompt_text.find("SHAPE CHECK")
        idx_verification = prompt_text.find("Verify by inspecting")
        assert idx_shape < idx_verification, (
            "SHAPE CHECK must appear BEFORE the DoD verification steps"
        )


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


# -- Test 8: compile_skills copies skill subdirectories (BR-011, AC7) ---------


def _load_compile_sdlc_module() -> Any:
    """Load compile-sdlc.py as a module (hyphenated filename requires importlib)."""
    module_path = REPO_ROOT / "compile-sdlc.py"
    spec = importlib.util.spec_from_file_location("compile_sdlc", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_should_copy_skill_subdir_when_templates_present(tmp_path: Path) -> None:
    """compile_skills must recursively copy skill subdirectories (BR-011, AC7).

    Regression test for the task 001 change: compile_skills() uses
    shutil.copytree so templates/ siblings of SKILL.md ride along into dist/.
    """
    # Arrange — build a fake repo_root with skills/fake/SKILL.md + templates/foo.txt
    fake_repo = tmp_path / "repo"
    skill_src = fake_repo / "skills" / "fake"
    (skill_src / "templates").mkdir(parents=True)
    skill_md_content = "# Fake Skill\n\nBody.\n"
    template_content = "template payload\n"
    (skill_src / "SKILL.md").write_text(skill_md_content)
    (skill_src / "templates" / "foo.txt").write_text(template_content)

    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()

    compile_sdlc = _load_compile_sdlc_module()

    # Act
    compile_sdlc.compile_skills(dist_dir, fake_repo)

    # Assert — both files present in dist/skills/fake/
    dst_skill = dist_dir / "skills" / "fake" / "SKILL.md"
    dst_template = dist_dir / "skills" / "fake" / "templates" / "foo.txt"
    assert dst_skill.exists(), f"SKILL.md not copied to {dst_skill}"
    assert dst_template.exists(), f"templates/foo.txt not copied to {dst_template}"

    # Assert — contents are byte-identical to source
    assert dst_skill.read_bytes() == (skill_src / "SKILL.md").read_bytes()
    assert dst_template.read_bytes() == (skill_src / "templates" / "foo.txt").read_bytes()


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
