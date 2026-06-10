"""Tests for the Codex compiler target."""

from __future__ import annotations

import json
import subprocess
import sys
import tomllib
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
COMPILE_SCRIPT = REPO_ROOT / "compile-sdlc.py"
SPEC_PATH = REPO_ROOT / "spec" / "etc_sdlc.yaml"
DOMAIN_USER_FLOW_FIXTURE = (
    REPO_ROOT / "tests" / "fixtures" / "codex-build" / "domain-user-flow-task.yaml"
)
SURFACE_USER_FLOW_FIXTURE = (
    REPO_ROOT / "tests" / "fixtures" / "codex-build" / "surface-user-flow-task.yaml"
)


def test_should_emit_codex_artifact_tree_when_client_is_codex(tmp_path: Path) -> None:
    output_dir = tmp_path / "codex"

    _run_compile(output_dir, "--client", "codex")

    assert (output_dir / "AGENTS.md").exists()
    assert (output_dir / "gate-classification.json").exists()
    assert (output_dir / ".codex" / "hooks.json").exists()
    assert (output_dir / ".codex" / "hooks" / "check-test-exists.sh").exists()
    assert (output_dir / ".codex" / "agents" / "backend-developer.toml").exists()
    assert (output_dir / ".codex" / "scripts" / "etc_runtime.py").exists()
    assert (output_dir / ".codex" / "schemas" / "completion.schema.json").exists()
    assert (
        output_dir / "standards" / "process" / "interactive-user-input.md"
    ).exists()
    assert (
        output_dir / "standards" / "process" / "codebase-navigation.md"
    ).exists()
    assert (
        output_dir / ".codex" / "standards" / "process" / "interactive-user-input.md"
    ).exists()
    assert (output_dir / ".codex" / "source" / "compile-sdlc.py").exists()
    assert (output_dir / ".codex" / "source" / "spec" / "etc_sdlc.yaml").exists()
    assert (output_dir / ".agents" / "skills" / "build" / "SKILL.md").exists()


def test_should_classify_every_gate_when_client_is_codex(tmp_path: Path) -> None:
    output_dir = tmp_path / "codex"
    spec = yaml.safe_load(SPEC_PATH.read_text(encoding="utf-8"))
    expected_gates = set(spec["gates"])

    _run_compile(output_dir, "--client", "codex")

    classifications = json.loads(
        (output_dir / "gate-classification.json").read_text(encoding="utf-8")
    )
    actual_gates = set(classifications["gates"])
    uncategorized = [
        gate_name
        for gate_name, gate in classifications["gates"].items()
        if gate["codex_bucket"] == "uncategorized"
    ]

    assert actual_gates == expected_gates
    assert uncategorized == []
    assert classifications["gates"]["task-readiness"]["active_hook"] is False
    assert classifications["gates"]["task-completion"]["active_hook"] is False
    assert classifications["gates"]["adversarial-review"]["active_hook"] is False


def test_should_emit_only_active_command_hooks_when_client_is_codex(tmp_path: Path) -> None:
    output_dir = tmp_path / "codex"

    _run_compile(output_dir, "--client", "codex")

    hooks_config = json.loads(
        (output_dir / ".codex" / "hooks.json").read_text(encoding="utf-8")
    )
    handlers = _all_hook_handlers(hooks_config)
    handler_types = {handler["type"] for handler in handlers}
    hook_events = set(hooks_config["hooks"])

    assert handler_types == {"command"}
    assert "TaskCreated" not in hook_events
    assert "TaskCompleted" not in hook_events
    assert "SubagentStop" not in hook_events
    assert "ConfigChange" not in hook_events


def test_should_emit_parseable_codex_agent_toml_when_client_is_codex(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "codex"

    _run_compile(output_dir, "--client", "codex")

    agent = tomllib.loads(
        (output_dir / ".codex" / "agents" / "backend-developer.toml").read_text(
            encoding="utf-8"
        )
    )

    assert agent["name"] == "backend-developer"
    assert agent["description"]
    assert "developer_instructions" in agent
    assert "TDD" in agent["developer_instructions"]


def test_should_not_emit_hardcoded_claude_home_when_client_is_codex(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "codex"

    _run_compile(output_dir, "--client", "codex")

    offenders = _files_containing(output_dir, "~/.claude")

    assert offenders == []


def test_should_not_emit_hardcoded_codex_home_scripts_when_client_is_codex(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "codex"

    _run_compile(output_dir, "--client", "codex")

    offenders: dict[str, list[str]] = {}
    for path in _codex_skill_surface_paths(output_dir):
        text = path.read_text(encoding="utf-8")
        hits = [
            needle
            for needle in (
                "~/.codex/scripts",
                "~/.Codex/scripts",
                "python3 ~/.codex/scripts",
                "`.codex/scripts/`, not the user's project",
                "not the user's",
            )
            if needle in text
        ]
        if hits:
            offenders[str(path.relative_to(output_dir))] = hits

    assert offenders == {}


def test_should_rewrite_claude_primitives_out_of_codex_skill_surfaces(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "codex"

    _run_compile(output_dir, "--client", "codex")

    forbidden = (
        "AskUserQuestion",
        "Agent(",
        "Agent({",
        "Task(",
        "Task({",
        "Agent-tool",
        "Invoke the Agent tool",
        "Task tool",
        "`/goal`",
    )
    offenders: dict[str, list[str]] = {}
    for path in _codex_skill_surface_paths(output_dir):
        text = path.read_text(encoding="utf-8")
        hits = [needle for needle in forbidden if needle in text]
        if hits:
            offenders[str(path.relative_to(output_dir))] = hits

    assert offenders == {}


def test_codex_build_skill_skips_parent_prompt_for_domain_user_flow_task(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "codex"
    domain_task = yaml.safe_load(DOMAIN_USER_FLOW_FIXTURE.read_text(encoding="utf-8"))

    _run_compile(output_dir, "--client", "codex")

    build_text = (output_dir / ".agents" / "skills" / "build" / "SKILL.md").read_text(
        encoding="utf-8"
    )

    assert domain_task["files_in_scope"] == [
        "types/index.ts",
        "apps/example-app/domain/upcomingItemsWidget.ts",
        "apps/example-app/domain/__tests__/upcomingItemsWidget.test.ts",
    ]
    assert "As a user, navigate from" in domain_task["acceptance_criteria"][0]
    assert "surface_status: not_applicable" in build_text
    assert "no parent wiring file applies" in build_text
    assert "Domain-only pure domain/data tasks" in build_text
    assert "no heuristic, no clause injection, no operator prompt" in build_text


def test_codex_build_skill_still_prompts_for_actual_surface_tasks(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "codex"
    surface_task = yaml.safe_load(SURFACE_USER_FLOW_FIXTURE.read_text(encoding="utf-8"))

    _run_compile(output_dir, "--client", "codex")

    build_text = (output_dir / ".agents" / "skills" / "build" / "SKILL.md").read_text(
        encoding="utf-8"
    )

    assert any(path.endswith(".tsx") for path in surface_task["files_in_scope"])
    assert "As a user, navigate from" in surface_task["acceptance_criteria"][0]
    assert "Actual surface tasks" in build_text
    assert "auto-add heuristic" in build_text
    assert "Operator-prompt fallback" in build_text
    assert "request_user_input(" in build_text


def test_should_emit_claude_output_when_client_is_claude(tmp_path: Path) -> None:
    output_dir = tmp_path / "claude"

    _run_compile(output_dir, "--client", "claude")

    hooks_config = json.loads(
        (output_dir / "settings-hooks.json").read_text(encoding="utf-8")
    )
    commands: list[str] = [
        str(handler["command"])
        for handler in _all_hook_handlers(hooks_config)
        if handler["type"] == "command"
    ]

    assert (output_dir / "settings-hooks.json").exists()
    assert all(command.startswith("{{ETC_HOOKS_DIR}}/") for command in commands)
    assert all("~/.claude/hooks/" not in command for command in commands)
    assert not (output_dir / ".codex").exists()


def test_should_emit_both_targets_when_client_is_all(tmp_path: Path) -> None:
    output_dir = tmp_path / "all"

    _run_compile(output_dir, "--client", "all")

    assert (output_dir / "claude" / "settings-hooks.json").exists()
    assert (output_dir / "codex" / ".codex" / "hooks.json").exists()


def test_every_compiled_codex_python_script_must_parse(tmp_path: Path) -> None:
    """Deterministic gate on the codex rewrite footgun (audit init 11).

    The codex target rewrites every UTF-8 file — including executable
    Python — through an ordered string-replacement table. A replacement
    that lands inside code can corrupt a script silently. This test
    ast.parses EVERY .py file in the codex output tree so any such
    corruption fails loudly with the offending filename.
    """
    import ast

    output_dir = tmp_path / "codex"
    _run_compile(output_dir, "--client", "codex")

    py_files = sorted(output_dir.rglob("*.py"))
    assert py_files, "codex output tree contains no .py files — layout changed?"

    failures: list[str] = []
    for py in py_files:
        try:
            ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        except SyntaxError as exc:
            failures.append(f"{py.relative_to(output_dir)}: {exc}")
    assert not failures, (
        "codex string-replacement corrupted executable Python — these "
        "compiled scripts no longer parse:\n  " + "\n  ".join(failures)
    )


def _run_compile(output_dir: Path, *client_args: str) -> None:
    subprocess.run(
        [
            sys.executable,
            str(COMPILE_SCRIPT),
            str(SPEC_PATH),
            *client_args,
            "--output",
            str(output_dir),
        ],
        cwd=REPO_ROOT,
        check=True,
        text=True,
        capture_output=True,
    )


def _all_hook_handlers(hooks_config: dict[str, object]) -> list[dict[str, object]]:
    handlers: list[dict[str, object]] = []
    hooks = hooks_config["hooks"]
    assert isinstance(hooks, dict)
    for entries in hooks.values():
        assert isinstance(entries, list)
        for entry in entries:
            assert isinstance(entry, dict)
            entry_hooks = entry["hooks"]
            assert isinstance(entry_hooks, list)
            handlers.extend(entry_hooks)
    return handlers


def _files_containing(root: Path, needle: str) -> list[str]:
    offenders: list[str] = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and _file_contains(path, needle):
            offenders.append(str(path.relative_to(root)))
    return offenders


def _file_contains(path: Path, needle: str) -> bool:
    try:
        return needle in path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return False


def _codex_skill_surface_paths(root: Path) -> list[Path]:
    paths = [root / "AGENTS.md"]
    paths.extend((root / ".agents" / "skills").glob("*/SKILL.md"))
    paths.extend((root / "plugins" / "etc-sdlc" / "skills").glob("*/SKILL.md"))
    paths.extend((root / ".codex" / "agents").glob("*.toml"))
    return sorted(path for path in paths if path.is_file())
