"""Shared test fixtures for hook test suite.

Provides reusable fixtures for invoking hook scripts, creating temporary
project structures, task files, transcript files, and invariant files.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "hooks"
HOOK_TIMEOUT_SECONDS = 10


@dataclass(frozen=True, slots=True)
class HookResult:
    """Result of executing a hook script."""

    exit_code: int
    stdout: str
    stderr: str


def _execute_hook(hook_name: str, hook_input: dict[str, Any]) -> HookResult:
    """Locate and execute a hook script, piping JSON input via stdin.

    Args:
        hook_name: Filename of the hook script (e.g. "block-dangerous-commands.sh").
        hook_input: Dictionary to serialize as JSON and pipe to the script's stdin.

    Returns:
        HookResult with exit_code, stdout, and stderr.

    Raises:
        FileNotFoundError: If the hook script does not exist.
        subprocess.TimeoutExpired: If the script exceeds the timeout.
    """
    hook_path = HOOKS_DIR / hook_name
    if not hook_path.is_file():
        msg = f"Hook script not found: {hook_path}"
        raise FileNotFoundError(msg)

    completed = subprocess.run(
        ["bash", str(hook_path)],
        input=json.dumps(hook_input),
        capture_output=True,
        text=True,
        timeout=HOOK_TIMEOUT_SECONDS,
    )
    return HookResult(
        exit_code=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


@pytest.fixture()
def run_hook() -> Any:
    """Fixture that returns a callable to execute hook scripts.

    Usage:
        result = run_hook("block-dangerous-commands.sh", {"tool_input": {"command": "ls"}})
        assert result.exit_code == 0
    """
    return _execute_hook


@pytest.fixture()
def tmp_project(tmp_path: Path) -> Path:
    """Create a temporary project directory with standard subdirectories.

    Creates: src/, tests/, .etc_sdlc/tasks/
    """
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / ".etc_sdlc" / "tasks").mkdir(parents=True)
    return tmp_path


@pytest.fixture()
def task_file(tmp_project: Path) -> Any:
    """Factory fixture to create YAML task files in .etc_sdlc/tasks/.

    Args:
        task_id: Task identifier (e.g. "001").
        title: Human-readable task title.
        status: Task status (default: "in_progress").
        requires_reading: List of file paths the task requires reading.
        files_in_scope: List of file paths in the task's edit scope.

    Returns:
        Path to the created YAML file.
    """

    def _create(
        task_id: str,
        title: str,
        status: str = "in_progress",
        requires_reading: list[str] | None = None,
        files_in_scope: list[str] | None = None,
    ) -> Path:
        task_dir = tmp_project / ".etc_sdlc" / "tasks"
        task_path = task_dir / f"task-{task_id}.yaml"

        lines = [
            f"id: {task_id}",
            f"title: {title}",
            f"status: {status}",
        ]

        if requires_reading:
            lines.append("requires_reading:")
            for item in requires_reading:
                lines.append(f"  - {item}")

        if files_in_scope:
            lines.append("files_in_scope:")
            for item in files_in_scope:
                lines.append(f"  - {item}")

        task_path.write_text("\n".join(lines) + "\n")
        return task_path

    return _create


@pytest.fixture()
def transcript_file(tmp_project: Path) -> Any:
    """Factory fixture to create JSONL transcript files.

    Args:
        entries: List of (tool_name, file_path) tuples representing Read tool calls.

    Returns:
        Path to the created JSONL file.
    """

    def _create(entries: list[tuple[str, str]]) -> Path:
        transcript_path = tmp_project / "transcript.jsonl"
        lines = []
        for tool_name, file_path in entries:
            record = {"tool_name": tool_name, "file_path": file_path}
            lines.append(json.dumps(record))
        transcript_path.write_text("\n".join(lines) + "\n")
        return transcript_path

    return _create


@pytest.fixture()
def invariants_file(tmp_project: Path) -> Any:
    """Factory fixture to create INVARIANTS.md files.

    Args:
        entries: List of dicts with keys "id", "description", "verify".

    Returns:
        Path to the created INVARIANTS.md file.
    """

    def _create(entries: list[dict[str, str]]) -> Path:
        invariants_path = tmp_project / "INVARIANTS.md"
        sections = ["# Project Invariants\n"]

        for entry in entries:
            section = (
                f"## {entry['id']}: {entry['description']}\n"
                f"\n"
                f"- **Verify:** `{entry['verify']}`\n"
            )
            sections.append(section)

        invariants_path.write_text("\n".join(sections) + "\n")
        return invariants_path

    return _create
