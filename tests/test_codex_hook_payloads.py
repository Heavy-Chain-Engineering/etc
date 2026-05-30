"""Tests for Codex hook payload normalization.

Codex edit hooks receive ``apply_patch`` payloads, not Claude-style
``tool_input.file_path`` values. The runtime adapter is the stable seam that
hook scripts should consume before making pass/fail decisions.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
RUNTIME_PATH = REPO_ROOT / "scripts" / "etc_runtime.py"


def _load_runtime() -> Any:
    spec = importlib.util.spec_from_file_location("etc_runtime", RUNTIME_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_should_normalize_bash_payload_commands(tmp_path: Path) -> None:
    runtime = _load_runtime()
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "cwd": str(tmp_path),
        "tool_input": {"command": "python3 -m pytest -q"},
    }

    normalized = runtime.normalize_hook_payload(payload, client="codex")

    assert normalized == {
        "schema_version": 1,
        "client": "codex",
        "event": "PreToolUse",
        "tool_name": "Bash",
        "tool_kind": "shell",
        "cwd": str(tmp_path),
        "edited_files": [],
        "file_changes": [],
        "commands": ["python3 -m pytest -q"],
        "raw_payload_available": True,
    }


def test_should_extract_single_file_apply_patch(tmp_path: Path) -> None:
    runtime = _load_runtime()
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "apply_patch",
        "cwd": str(tmp_path),
        "tool_input": {
            "command": "\n".join(
                [
                    "*** Begin Patch",
                    "*** Update File: src/example.py",
                    "@@",
                    "-old = True",
                    "+old = False",
                    "*** End Patch",
                ]
            )
        },
    }

    normalized = runtime.normalize_hook_payload(payload, client="codex")

    assert normalized["tool_kind"] == "edit"
    assert normalized["edited_files"] == ["src/example.py"]
    assert normalized["file_changes"] == [
        {"path": "src/example.py", "change_type": "modify"}
    ]


def test_should_extract_multi_file_apply_patch(tmp_path: Path) -> None:
    runtime = _load_runtime()
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "apply_patch",
        "cwd": str(tmp_path),
        "tool_input": {
            "command": "\n".join(
                [
                    "*** Begin Patch",
                    "*** Update File: src/one.py",
                    "@@",
                    "-one = 1",
                    "+one = 2",
                    "*** Update File: tests/test_one.py",
                    "@@",
                    "-assert one == 1",
                    "+assert one == 2",
                    "*** End Patch",
                ]
            )
        },
    }

    normalized = runtime.normalize_hook_payload(payload, client="codex")

    assert normalized["edited_files"] == ["src/one.py", "tests/test_one.py"]


def test_should_detect_apply_patch_create_delete_and_move(tmp_path: Path) -> None:
    runtime = _load_runtime()
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "apply_patch",
        "cwd": str(tmp_path),
        "tool_input": {
            "command": "\n".join(
                [
                    "*** Begin Patch",
                    "*** Add File: src/new_file.py",
                    "+value = 1",
                    "*** Delete File: src/old_file.py",
                    "*** Update File: src/original.py",
                    "*** Move to: src/renamed.py",
                    "@@",
                    "-value = 1",
                    "+value = 2",
                    "*** End Patch",
                ]
            )
        },
    }

    normalized = runtime.normalize_hook_payload(payload, client="codex")

    assert normalized["edited_files"] == [
        "src/new_file.py",
        "src/old_file.py",
        "src/original.py",
        "src/renamed.py",
    ]
    assert normalized["file_changes"] == [
        {"path": "src/new_file.py", "change_type": "create"},
        {"path": "src/old_file.py", "change_type": "delete"},
        {"path": "src/original.py", "change_type": "move_from"},
        {"path": "src/renamed.py", "change_type": "move_to"},
    ]


def test_should_fail_clearly_when_apply_patch_command_is_missing(tmp_path: Path) -> None:
    runtime = _load_runtime()
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "apply_patch",
        "cwd": str(tmp_path),
        "tool_input": {},
    }

    with pytest.raises(runtime.PayloadNormalizationError, match="apply_patch.*command"):
        runtime.normalize_hook_payload(payload, client="codex")
