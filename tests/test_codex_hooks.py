"""Codex direct hook behavior for normalized edit and shell payloads."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent


_MISSING = object()


def _codex_apply_patch_input(cwd: Path, patch_lines: list[str]) -> dict[str, Any]:
    return {
        "hook_event_name": "PreToolUse",
        "tool_name": "apply_patch",
        "cwd": str(cwd),
        "tool_input": {"command": "\n".join(patch_lines)},
    }


def _apply_patch_update(path: str) -> list[str]:
    return [
        "*** Begin Patch",
        f"*** Update File: {path}",
        "@@",
        "-old = True",
        "+old = False",
        "*** End Patch",
    ]


def _write_reading_ledger(
    tmp_project: Path,
    task_id: str,
    *,
    changed_files: object = _MISSING,
) -> None:
    artifact_dir = tmp_project / ".etc_sdlc" / "tasks" / task_id
    artifact_dir.mkdir()
    payload: dict[str, object] = {
        "schema_version": 1,
        "task_id": task_id,
        "client": "codex",
        "updated_at": "2999-01-01T00:00:00+00:00",
        "status": "pass",
        "required_reading": ["spec/design.md"],
        "read_entries": [
            {
                "path": "spec/design.md",
                "reason": "task context",
                "recorded_at": "2999-01-01T00:00:00+00:00",
                "digest": "abc123",
            }
        ],
        "missing": [],
        "fresh": True,
    }
    if changed_files is not _MISSING:
        payload["changed_files"] = changed_files
    (artifact_dir / "reading-ledger.json").write_text(json.dumps(payload))


def _write_reading_task(task_file: Any, task_id: str) -> None:
    task_file(
        task_id=task_id,
        title="Codex reading task",
        status="in_progress",
        requires_reading=["spec/design.md"],
        files_in_scope=["src/"],
    )


def test_should_allow_tdd_gate_when_codex_patch_contains_test_and_src(
    run_hook: Any,
    tmp_project: Path,
) -> None:
    hook_input = _codex_apply_patch_input(
        tmp_project,
        [
            "*** Begin Patch",
            "*** Add File: tests/test_handler.py",
            "+def test_should_handle_request_when_called():",
            "+    assert True",
            "*** Add File: src/handler.py",
            "+def handle_request():",
            "+    return True",
            "*** End Patch",
        ],
    )

    result = run_hook("check-test-exists.sh", hook_input)

    assert result.exit_code == 0


def test_should_block_tdd_gate_when_codex_patch_adds_src_without_test(
    run_hook: Any,
    tmp_project: Path,
) -> None:
    hook_input = _codex_apply_patch_input(
        tmp_project,
        [
            "*** Begin Patch",
            "*** Add File: src/handler.py",
            "+def handle_request():",
            "+    return True",
            "*** End Patch",
        ],
    )

    result = run_hook("check-test-exists.sh", hook_input)

    assert result.exit_code == 2
    assert "test_handler.py" in result.stderr


def test_should_mark_dirty_when_codex_patch_edits_src(
    run_hook: Any,
    tmp_project: Path,
) -> None:
    hook_input = _codex_apply_patch_input(tmp_project, _apply_patch_update("src/app.py"))

    result = run_hook("mark-dirty.sh", hook_input)

    assert result.exit_code == 0
    assert (tmp_project / ".tdd-dirty").exists()


def test_should_block_tier_zero_when_codex_patch_edits_code_without_context(
    run_hook: Any,
    tmp_project: Path,
) -> None:
    hook_input = _codex_apply_patch_input(tmp_project, _apply_patch_update("src/app.py"))

    result = run_hook("check-tier-0.sh", hook_input)

    assert result.exit_code == 2
    assert "Tier 0" in result.stderr


def test_should_check_component_invariants_for_codex_patch(
    run_hook: Any,
    tmp_project: Path,
) -> None:
    component = tmp_project / "src" / "api"
    component.mkdir(parents=True)
    (component / "INVARIANTS.md").write_text(
        "\n".join(
            [
                "# API invariants",
                "",
                "## INV-101: Component failure",
                "- **Verify:** `echo component violation`",
                "",
            ]
        )
    )
    hook_input = _codex_apply_patch_input(
        tmp_project,
        _apply_patch_update("src/api/handler.py"),
    )

    result = run_hook("check-invariants.sh", hook_input)

    assert result.exit_code == 2
    assert "INV-101" in result.stderr


def test_should_run_code_quality_for_codex_patch_python_file(
    run_hook: Any,
    tmp_project: Path,
) -> None:
    (tmp_project / "src" / "bad.py").write_text("handlers = []\n")
    hook_input = _codex_apply_patch_input(tmp_project, _apply_patch_update("src/bad.py"))

    result = run_hook("check-code-quality.sh", hook_input)

    assert result.exit_code == 2
    assert "CQ-001" in result.stderr


def test_should_block_phase_gate_when_codex_patch_edits_blocked_path(
    run_hook: Any,
    tmp_project: Path,
) -> None:
    state_dir = tmp_project / ".sdlc"
    state_dir.mkdir()
    (state_dir / "state.json").write_text(json.dumps({"current_phase": "Build"}))
    hook_input = _codex_apply_patch_input(tmp_project, _apply_patch_update("spec/prd.md"))

    result = run_hook("check-phase-gate.sh", hook_input)

    assert result.exit_code == 2
    assert "Build" in result.stderr


def test_should_block_required_reading_for_codex_task_scope_without_ledger(
    run_hook: Any,
    tmp_project: Path,
    task_file: Any,
) -> None:
    _write_reading_task(task_file, "200")
    hook_input = _codex_apply_patch_input(
        tmp_project,
        _apply_patch_update("src/handler.py"),
    )

    result = run_hook("check-required-reading.sh", hook_input)

    assert result.exit_code == 2
    assert "reading-ledger.json" in result.stderr


def test_should_allow_required_reading_for_codex_task_scope_with_fresh_ledger(
    run_hook: Any,
    tmp_project: Path,
    task_file: Any,
) -> None:
    _write_reading_task(task_file, "201")
    _write_reading_ledger(tmp_project, "201", changed_files=["src/handler.py"])
    hook_input = _codex_apply_patch_input(
        tmp_project,
        _apply_patch_update("src/handler.py"),
    )

    result = run_hook("check-required-reading.sh", hook_input)

    assert result.exit_code == 0


def test_should_block_required_reading_when_ledger_missing_changed_files(
    run_hook: Any,
    tmp_project: Path,
    task_file: Any,
) -> None:
    _write_reading_task(task_file, "202")
    _write_reading_ledger(tmp_project, "202")
    hook_input = _codex_apply_patch_input(
        tmp_project,
        _apply_patch_update("src/handler.py"),
    )

    result = run_hook("check-required-reading.sh", hook_input)

    assert result.exit_code == 2
    assert "changed_files must be a list" in result.stderr


def test_should_block_required_reading_when_ledger_changed_files_wrong_type(
    run_hook: Any,
    tmp_project: Path,
    task_file: Any,
) -> None:
    _write_reading_task(task_file, "203")
    _write_reading_ledger(tmp_project, "203", changed_files="src/handler.py")
    hook_input = _codex_apply_patch_input(
        tmp_project,
        _apply_patch_update("src/handler.py"),
    )

    result = run_hook("check-required-reading.sh", hook_input)

    assert result.exit_code == 2
    assert "changed_files must be a list" in result.stderr


def test_should_block_required_reading_when_ledger_omits_scoped_edit(
    run_hook: Any,
    tmp_project: Path,
    task_file: Any,
) -> None:
    _write_reading_task(task_file, "204")
    _write_reading_ledger(tmp_project, "204", changed_files=["src/other.py"])
    hook_input = _codex_apply_patch_input(
        tmp_project,
        _apply_patch_update("src/handler.py"),
    )

    result = run_hook("check-required-reading.sh", hook_input)

    assert result.exit_code == 2
    assert "changed file not covered by reading-ledger.json: src/handler.py" in result.stderr


def test_should_block_dangerous_command_from_normalized_payload(
    run_hook: Any,
) -> None:
    hook_input = {
        "schema_version": 1,
        "client": "codex",
        "tool_kind": "shell",
        "commands": ["git reset --hard"],
        "edited_files": [],
    }

    result = run_hook("block-dangerous-commands.sh", hook_input)

    assert result.exit_code == 2
    assert "Hard reset" in result.stderr


def test_should_check_all_normalized_commands_after_safe_cache_removal(
    run_hook: Any,
) -> None:
    hook_input = {
        "schema_version": 1,
        "client": "codex",
        "tool_kind": "shell",
        "commands": ["rm -rf node_modules", "git reset --hard"],
        "edited_files": [],
    }

    result = run_hook("block-dangerous-commands.sh", hook_input)

    assert result.exit_code == 2
    assert "Hard reset" in result.stderr


def test_should_print_normalized_payload_json_from_helper(tmp_path: Path) -> None:
    payload = _codex_apply_patch_input(tmp_path, _apply_patch_update("src/app.py"))

    completed = subprocess.run(
        [sys.executable, str(REPO_ROOT / "hooks" / "helpers" / "hook_payload.py")],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=10,
    )

    normalized = json.loads(completed.stdout)

    assert completed.returncode == 0
    assert normalized["client"] == "codex"
    assert normalized["edited_files"] == ["src/app.py"]
