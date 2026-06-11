"""Tests for compile-sdlc.py.

Validates that the compiler produces correct output from the SDLC DSL spec.
Tests inspect the existing compiled artifacts in dist/ and verify structure,
content, and correctness of the generated files.
"""

from __future__ import annotations

import errno
import importlib.util
import json
import shutil
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

# Compiled artifacts are read from the shared session-scoped ``compiled_dist``
# fixture (conftest.py), which compiles into a tmp dir — the operator's real
# dist/ is never read by this suite. Tests that drive the compiler directly
# into their own ``tmp_path`` (via ``_load_compile_sdlc_module``) are already
# hermetic and unaffected.

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
def hooks_json(compiled_dist: Path) -> dict[str, Any]:
    """Load and parse the compiled settings-hooks.json once for all tests."""
    settings_path = compiled_dist / "settings-hooks.json"
    assert settings_path.exists(), (
        f"Compiled artifact not found: {settings_path}. "
        "The shared compiled_dist fixture should have created it."
    )
    content = settings_path.read_text()
    return json.loads(content)


@pytest.fixture(scope="module")
def dod_templates(compiled_dist: Path) -> dict[str, Any]:
    """Load and parse the compiled sdlc/dod-templates.json once for all tests."""
    dod_path = compiled_dist / "sdlc" / "dod-templates.json"
    assert dod_path.exists(), (
        f"Compiled artifact not found: {dod_path}. "
        "The shared compiled_dist fixture should have created it."
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


def test_should_compile_precompact_gate_without_matcher(hooks_json: dict[str, Any]) -> None:
    """A no-matcher PreCompact gate compiles to a hooks entry with no matcher key."""
    # Arrange
    precompact = hooks_json["hooks"]["PreCompact"]

    # Act
    entry = precompact[0]
    commands = [h["command"] for h in entry["hooks"]]

    # Assert
    assert "matcher" not in entry
    assert any("pre-compact-checkpoint.sh" in c for c in commands)


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


# -- Test 3.5: Harness feedback Stop hook was removed in v1.5.2 ------------


class TestHarnessFeedbackHookRemoved:
    """Regression test for the v1.5.2 emergency removal.

    The v1.5.1 harness-feedback prompt hook on Stop shipped with a latent
    bug where Sonnet evaluators returned prose reasoning alongside (or
    instead of) the bare silent-case JSON. Every attempt to tighten the
    prompt — strict silence language, explicit stakes statement, rubric
    restructuring — failed to produce compliant output in practice.

    The core architectural problem: prompt-type Stop hooks fire on every
    turn across every project, so any deviation from the silent contract
    floods session output and gets the hook muted. And because Claude
    Code caches hook configuration at session start, iterating on the
    prompt in the session that authored it is impossible. The debugging
    feedback loop is broken for prompt Stop hooks in general.

    The v1.5.2 decision: remove the hook entirely. Cross-project lesson
    capture will return in a future release, but only once
    scripts/test-hook-prompt.py (or equivalent local fixture runner)
    exists so prompt changes can be verified without a Claude Code
    restart, AND once we have a design that does not rely on a prompt
    hook for silent-by-default behavior (candidate: agent-type hook
    with tool calls that enforce response shape mechanically).

    This test enforces the removal: no prompt-type hook may register
    on the Stop event until the two blockers above are resolved.
    """

    def test_should_not_register_prompt_hook_on_stop(
        self, hooks_json: dict[str, Any]
    ) -> None:
        stop_entries = hooks_json["hooks"].get("Stop", [])
        for entry in stop_entries:
            for handler in entry.get("hooks", []):
                assert handler.get("type") != "prompt", (
                    "v1.5.2 removed the harness-feedback prompt hook from "
                    "Stop because its silent-case contract could not be "
                    "enforced against Sonnet's tendency to narrate its "
                    "reasoning, and because Claude Code's session-start "
                    "cache makes in-session iteration impossible. Do not "
                    "re-register a prompt hook on Stop until (a) a local "
                    "fixture runner exists that verifies prompt behavior "
                    "without a Claude Code restart, and (b) the silent "
                    "contract is enforced mechanically (agent-type hook "
                    "with tool calls) rather than by prose instruction."
                )


# -- Test 4: Correct script references ----------------------------------------


class TestShouldReferenceCorrectScripts:
    """Command hooks must reference the install-time hooks-dir placeholder.

    The compiler emits ``{{ETC_HOOKS_DIR}}/<script>.sh`` rather than a
    hardcoded ``~/.claude/hooks/`` path; the installer substitutes the
    placeholder for the resolved target hooks dir during merge (see
    etc_installer.settings_merge.substitute_hooks_dir). This decouples
    dist/ from any specific install target.
    """

    HOOKS_DIR_PLACEHOLDER = "{{ETC_HOOKS_DIR}}/"

    def test_should_reference_hook_path_when_command_type(
        self, hooks_json: dict[str, Any]
    ) -> None:
        """All command-type hooks must reference {{ETC_HOOKS_DIR}}/<script>.sh."""
        # Arrange
        all_command_hooks = _extract_all_hooks_by_type(hooks_json, "command")

        # Act & Assert
        for hook in all_command_hooks:
            command = hook.get("command", "")
            assert command.startswith(self.HOOKS_DIR_PLACEHOLDER), (
                f"Command hook does not reference {self.HOOKS_DIR_PLACEHOLDER}: {command!r}"
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
        assert f"{self.HOOKS_DIR_PLACEHOLDER}check-test-exists.sh" in commands

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
        assert f"{self.HOOKS_DIR_PLACEHOLDER}check-phase-gate.sh" in commands, (
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
        assert f"{self.HOOKS_DIR_PLACEHOLDER}block-dangerous-commands.sh" in commands


# -- Test 5: Skill directory ---------------------------------------------------


def test_should_create_skill_directory(compiled_dist: Path) -> None:
    """dist/skills/implement/SKILL.md must exist."""
    # Arrange
    skill_path = compiled_dist / "skills" / "implement" / "SKILL.md"

    # Act — just check existence and non-emptiness

    # Assert
    assert skill_path.exists(), f"Skill file not found: {skill_path}"
    assert skill_path.stat().st_size > 0, "SKILL.md exists but is empty"


# -- Test 6: Agent definitions -------------------------------------------------


def test_should_copy_agent_definitions(compiled_dist: Path) -> None:
    """dist/agents/ must contain sem.md, backend-developer.md, and others."""
    # Arrange
    agents_dir = compiled_dist / "agents"
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


def _wired_hook_scripts(hooks_json: dict[str, Any]) -> set[str]:
    """Basenames of every .sh script referenced by a wired hook command."""
    wired: set[str] = set()
    for groups in hooks_json.get("hooks", {}).values():
        for group in groups:
            for handler in group.get("hooks", []):
                for token in str(handler.get("command", "")).split():
                    if token.endswith(".sh"):
                        wired.add(token.rsplit("/", 1)[-1])
    return wired


# Hooks that legitimately are NOT event-wired: they are invoked directly by
# other hooks or by skill bodies (verified call sites), not by Claude Code
# events. Adding a hook here requires naming its real call site.
INDIRECTLY_INVOKED_HOOKS = frozenset(
    {
        "verify-green.sh",  # invoked by mark-dirty/check-completion-discipline/inject-standards/runtime-verify
        "runtime-verify.sh",  # invoked by /build Step 6c + behavioral-runtime-dod standard
    }
)


def test_every_hook_on_disk_is_wired_or_allowlisted(hooks_json: dict[str, Any]) -> None:
    """Audit init 2 (built-but-never-wired family): three hooks shipped
    compiled-and-installed but fired in NO installed environment because
    they were never declared in the DSL. This is the structural gate: every
    hooks/*.sh must either appear in a wired hook command or be explicitly
    allowlisted as indirectly invoked (with its real call site named).
    """
    on_disk = {p.name for p in (REPO_ROOT / "hooks").glob("*.sh")}
    wired = _wired_hook_scripts(hooks_json)
    dead = on_disk - wired - INDIRECTLY_INVOKED_HOOKS
    assert not dead, (
        f"hooks on disk that no event wires and no allowlist entry covers: "
        f"{sorted(dead)}. Either declare them in spec/etc_sdlc.yaml gates, "
        f"delete them, or allowlist them here WITH their real call site."
    )


def test_audit_revived_hooks_are_wired(hooks_json: dict[str, Any]) -> None:
    """The three formerly-dead hooks must stay wired (audit init 2)."""
    wired = _wired_hook_scripts(hooks_json)
    for script in (
        "tier-0-design-preflight.sh",
        "check-diagnostic-evidence.sh",
        "check-profiles-fresh.sh",
    ):
        assert script in wired, f"{script} regressed to unwired"


def test_dist_contains_no_python_bytecode(tmp_path: Path) -> None:
    """No __pycache__/*.pyc may ship in compiler output (audit init 8).

    The claude hooks-helpers copy site lacked the cache filter the codex
    path has (is_generated_cache_path), so host bytecode shipped into
    dist/hooks/helpers/. Compile into a tmp dir (hermetic — does not touch
    the operator's real dist/) and assert the output is bytecode-free.
    """
    compile_sdlc = _load_compile_sdlc_module()

    # Seed a real-looking helpers tree with a bytecode cache in it.
    fake_repo = tmp_path / "repo"
    helpers = fake_repo / "hooks" / "helpers"
    (helpers / "__pycache__").mkdir(parents=True)
    (helpers / "helper.py").write_text("x = 1\n")
    (helpers / "__pycache__" / "helper.cpython-312.pyc").write_bytes(b"\x00")
    (fake_repo / "hooks" / "real-hook.sh").write_text("#!/bin/bash\nexit 0\n")

    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()

    compile_sdlc.compile_gates({"gates": {}}, dist_dir, fake_repo)

    offenders = [
        p
        for p in dist_dir.rglob("*")
        if p.name == "__pycache__" or p.suffix == ".pyc"
    ]
    assert not offenders, (
        f"compiler output must not contain Python bytecode; found: "
        f"{[str(p.relative_to(dist_dir)) for p in offenders]}"
    )


def test_reset_output_dir_clears_contents_when_dir_is_bind_mount(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#62: a bind-mounted dist/ cannot be unlinked — rmtree raises
    OSError(EBUSY) on the mountpoint rmdir. reset_output_dir must fall back
    to clearing the directory's CONTENTS in place instead of crashing.
    """
    compile_sdlc = _load_compile_sdlc_module()

    out = tmp_path / "dist"
    out.mkdir()
    (out / "stale.txt").write_text("old")
    (out / "sub").mkdir()
    (out / "sub" / "nested.txt").write_text("old")

    real_rmtree = shutil.rmtree

    def fake_rmtree(path: Any, *args: Any, **kwargs: Any) -> None:
        # Simulate a bind mount: the mountpoint itself can't be removed,
        # but its children can (delegate those to the real rmtree).
        if Path(path) == out:
            raise OSError(errno.EBUSY, "Device or resource busy")
        real_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(compile_sdlc.shutil, "rmtree", fake_rmtree)

    # Must not raise, must preserve the mountpoint, must empty the contents.
    compile_sdlc.reset_output_dir(out)

    assert out.exists(), "bind-mount point must survive (not be removed)"
    assert list(out.iterdir()) == [], "dist/ contents must be cleared"


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


# -- Test 9: compile_dispatcher_hooks mirrors top-level hooks -----------------


NAMED_DISPATCHER_SCRIPTS = (
    "verify-green.sh",
    "check-diagnostic-evidence.sh",
    "check-profiles-fresh.sh",
    "tier-0-design-preflight.sh",
)


def _build_fake_hooks_repo(tmp_path: Path) -> Path:
    """Create a fake repo_root/hooks/ tree mirroring the real layout.

    Includes top-level .sh dispatchers, a hooks/helpers/ dir of .py modules,
    and a hooks/git/ dir that compile_dispatcher_hooks must NOT touch.
    """
    fake_repo = tmp_path / "repo"
    hooks_src = fake_repo / "hooks"
    hooks_src.mkdir(parents=True)

    for script in NAMED_DISPATCHER_SCRIPTS:
        (hooks_src / script).write_text(f"#!/usr/bin/env bash\n# {script}\n")

    helpers_src = hooks_src / "helpers"
    helpers_src.mkdir()
    (helpers_src / "check_mutable_globals.py").write_text("# mutable globals\n")
    (helpers_src / "check_noop_functions.py").write_text("# noop functions\n")

    git_src = hooks_src / "git"
    git_src.mkdir()
    (git_src / "post-commit").write_text("#!/usr/bin/env bash\n# post-commit\n")

    return fake_repo


def test_should_mirror_verify_green_when_compiling_dispatcher_hooks(
    tmp_path: Path,
) -> None:
    """compile_dispatcher_hooks must land verify-green.sh in dist/hooks/.

    Regression test for the F020 dispatcher being silently dropped from
    dist/ — installed downstream users got a hooks/ missing verify-green.sh,
    breaking /build Step 6c on every non-Python project.
    """
    # Arrange
    fake_repo = _build_fake_hooks_repo(tmp_path)
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    compile_sdlc = _load_compile_sdlc_module()

    # Act
    compile_sdlc.compile_dispatcher_hooks(dist_dir, fake_repo)

    # Assert
    assert (dist_dir / "hooks" / "verify-green.sh").exists()


def test_should_set_exec_bit_when_mirroring_dispatcher_hooks(
    tmp_path: Path,
) -> None:
    """Mirrored .sh dispatchers must be marked executable (0o755)."""
    # Arrange
    fake_repo = _build_fake_hooks_repo(tmp_path)
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    compile_sdlc = _load_compile_sdlc_module()

    # Act
    compile_sdlc.compile_dispatcher_hooks(dist_dir, fake_repo)

    # Assert
    mode = (dist_dir / "hooks" / "verify-green.sh").stat().st_mode
    assert mode & 0o755 == 0o755


def test_should_land_all_named_dispatchers_when_compiling(tmp_path: Path) -> None:
    """All four named dispatcher scripts must land in dist/hooks/."""
    # Arrange
    fake_repo = _build_fake_hooks_repo(tmp_path)
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    compile_sdlc = _load_compile_sdlc_module()

    # Act
    compile_sdlc.compile_dispatcher_hooks(dist_dir, fake_repo)

    # Assert
    missing = [
        s for s in NAMED_DISPATCHER_SCRIPTS
        if not (dist_dir / "hooks" / s).exists()
    ]
    assert not missing, f"Missing dispatcher scripts in dist/hooks/: {missing}"


def test_should_copy_helpers_recursively_when_compiling_dispatcher_hooks(
    tmp_path: Path,
) -> None:
    """hooks/helpers/*.py must be copied recursively into dist/hooks/helpers/."""
    # Arrange
    fake_repo = _build_fake_hooks_repo(tmp_path)
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    compile_sdlc = _load_compile_sdlc_module()

    # Act
    compile_sdlc.compile_dispatcher_hooks(dist_dir, fake_repo)

    # Assert
    helpers_dst = dist_dir / "hooks" / "helpers"
    assert (helpers_dst / "check_mutable_globals.py").exists()
    assert (helpers_dst / "check_noop_functions.py").exists()


def test_should_exclude_git_hooks_when_compiling_dispatcher_hooks(
    tmp_path: Path,
) -> None:
    """compile_dispatcher_hooks must NOT copy hooks/git/ (compile_git_hooks owns it)."""
    # Arrange
    fake_repo = _build_fake_hooks_repo(tmp_path)
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    compile_sdlc = _load_compile_sdlc_module()

    # Act
    compile_sdlc.compile_dispatcher_hooks(dist_dir, fake_repo)

    # Assert
    assert not (dist_dir / "hooks" / "git").exists(), (
        "compile_dispatcher_hooks must leave hooks/git/ to compile_git_hooks"
    )


def test_should_not_raise_when_hooks_dir_absent(tmp_path: Path) -> None:
    """compile_dispatcher_hooks must be graceful when repo has no hooks/."""
    # Arrange
    fake_repo = tmp_path / "repo"
    fake_repo.mkdir()
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    compile_sdlc = _load_compile_sdlc_module()

    # Act — must not raise
    compile_sdlc.compile_dispatcher_hooks(dist_dir, fake_repo)

    # Assert — nothing landed, no exception
    assert not (dist_dir / "hooks").exists() or not list(
        (dist_dir / "hooks").glob("*.sh")
    )


def test_should_be_idempotent_when_compiling_dispatcher_hooks_twice(
    tmp_path: Path,
) -> None:
    """Re-running compile_dispatcher_hooks must produce byte-identical output."""
    # Arrange
    fake_repo = _build_fake_hooks_repo(tmp_path)
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    compile_sdlc = _load_compile_sdlc_module()

    # Act
    compile_sdlc.compile_dispatcher_hooks(dist_dir, fake_repo)
    first = (dist_dir / "hooks" / "verify-green.sh").read_bytes()
    compile_sdlc.compile_dispatcher_hooks(dist_dir, fake_repo)
    second = (dist_dir / "hooks" / "verify-green.sh").read_bytes()

    # Assert
    assert first == second


# -- Test 10: source/dist hook set-equality parity guard ----------------------


def test_should_mirror_every_source_hook_into_dist(tmp_path: Path) -> None:
    """Every repo_root/hooks/*.sh basename must appear in dist/hooks/.

    Systemic parity guard (converts the silent-drop bug family from
    'caught downstream by luck' to 'caught in CI'). The failure message
    NAMES the missing files — the failure mode that bit us was an unnamed
    silent drop of verify-green.sh.
    """
    # Arrange — compile the REAL spec into an isolated dist
    compile_sdlc = _load_compile_sdlc_module()
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    compile_sdlc.compile_gates(_load_real_spec(), dist_dir, REPO_ROOT)
    compile_sdlc.compile_dispatcher_hooks(dist_dir, REPO_ROOT)
    compile_sdlc.compile_git_hooks(dist_dir, REPO_ROOT)

    # Act
    source_sh = {p.name for p in (REPO_ROOT / "hooks").glob("*.sh")}
    dist_sh = {p.name for p in (dist_dir / "hooks").glob("*.sh")}
    missing = source_sh - dist_sh

    # Assert
    assert not missing, (
        f"Source hooks missing from dist/hooks/: {sorted(missing)}. "
        f"compile_dispatcher_hooks must mirror every top-level hooks/*.sh."
    )


def test_should_mirror_every_source_helper_into_dist(tmp_path: Path) -> None:
    """Every repo_root/hooks/helpers/* must appear in dist/hooks/helpers/."""
    # Arrange
    compile_sdlc = _load_compile_sdlc_module()
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    compile_sdlc.compile_dispatcher_hooks(dist_dir, REPO_ROOT)

    helpers_src = REPO_ROOT / "hooks" / "helpers"
    source_helpers = {
        p.name for p in helpers_src.iterdir() if p.is_file()
    }

    # Act
    helpers_dst = dist_dir / "hooks" / "helpers"
    dist_helpers = (
        {p.name for p in helpers_dst.iterdir() if p.is_file()}
        if helpers_dst.exists()
        else set()
    )
    missing = source_helpers - dist_helpers

    # Assert
    assert not missing, (
        f"Source helpers missing from dist/hooks/helpers/: {sorted(missing)}. "
        f"compile_dispatcher_hooks must mirror hooks/helpers/ recursively."
    )


def _load_real_spec() -> dict[str, Any]:
    """Load the real SDLC spec for parity tests."""
    import yaml

    spec_path = REPO_ROOT / "spec" / "etc_sdlc.yaml"
    return yaml.safe_load(spec_path.read_text(encoding="utf-8"))


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
    for entries in hooks_json.get("hooks", {}).values():
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
