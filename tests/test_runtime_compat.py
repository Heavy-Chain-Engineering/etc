"""Tests for the ETC runtime compatibility layer."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
RUNTIME_PATH = REPO_ROOT / "scripts" / "etc_runtime.py"
RUNTIME_SHIM = REPO_ROOT / "scripts" / "etc-runtime"


def _load_runtime() -> Any:
    spec = importlib.util.spec_from_file_location("etc_runtime", RUNTIME_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _artifact_payload(
    task_id: str,
    changed_files: list[str],
    updated_at: datetime,
    **extra: Any,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": 1,
        "task_id": task_id,
        "client": "codex",
        "created_at": updated_at.isoformat(),
        "updated_at": updated_at.isoformat(),
        "source_commit": "abc123",
        "changed_files": changed_files,
        "status": "pass",
        "checks": [{"name": "unit", "status": "pass"}],
        "notes": [],
    }
    payload.update(extra)
    return payload


def test_should_resolve_project_codex_paths_without_claude_root(tmp_path: Path) -> None:
    runtime = _load_runtime()
    home = tmp_path / "home"
    project = tmp_path / "repo"

    paths = runtime.resolve_install_paths(
        client="codex",
        scope="project",
        cwd=project,
        home=home,
    )

    assert paths["config_root"] == project / ".codex"
    assert paths["hooks"] == project / ".codex" / "hooks"
    assert paths["agents"] == project / ".codex" / "agents"
    assert paths["skills"] == project / ".agents" / "skills"
    assert paths["standards"] == project / "standards"
    assert paths["runtime"] == project / ".codex" / "scripts"
    assert paths["schemas"] == project / ".codex" / "schemas"
    assert all(".claude" not in str(path) for path in paths.values())


def test_should_resolve_user_codex_paths_without_claude_root(tmp_path: Path) -> None:
    runtime = _load_runtime()
    home = tmp_path / "home"

    paths = runtime.resolve_install_paths(client="codex", scope="user", home=home)

    assert paths["config_root"] == home / ".codex"
    assert paths["hooks"] == home / ".codex" / "hooks"
    assert paths["agents"] == home / ".codex" / "agents"
    assert paths["skills"] == home / ".agents" / "skills"
    assert paths["standards"] == home / "standards"
    assert paths["runtime"] == home / ".codex" / "scripts"
    assert paths["schemas"] == home / ".codex" / "schemas"
    assert all(".claude" not in str(path) for path in paths.values())


def test_should_resolve_project_codex_paths_from_git_root(tmp_path: Path) -> None:
    runtime = _load_runtime()
    project = tmp_path / "repo"
    nested = project / "services" / "api"
    nested.mkdir(parents=True)
    (project / ".git").mkdir()

    paths = runtime.resolve_install_paths(client="codex", scope="project", cwd=nested)

    assert paths["config_root"] == project / ".codex"
    assert paths["skills"] == project / ".agents" / "skills"
    assert paths["standards"] == project / "standards"


def test_should_reject_unknown_codex_install_scope(tmp_path: Path) -> None:
    runtime = _load_runtime()

    with pytest.raises(ValueError, match="Unsupported codex install scope"):
        runtime.resolve_install_paths(client="codex", scope="plugin", home=tmp_path)


def test_should_validate_current_completion_artifact(tmp_path: Path) -> None:
    runtime = _load_runtime()
    task_id = "T-001"
    changed = tmp_path / "src" / "example.py"
    changed.parent.mkdir()
    changed.write_text("value = 1\n")
    artifact_dir = tmp_path / ".etc_sdlc" / "tasks" / task_id
    artifact_dir.mkdir(parents=True)

    now = datetime.now(UTC)
    os.utime(changed, (now.timestamp(), now.timestamp()))
    payload = _artifact_payload(
        task_id,
        ["src/example.py"],
        now + timedelta(seconds=1),
        test_evidence=[{"command": "pytest", "status": "pass"}],
        review_evidence={"review": "review.json"},
        acceptance_criteria_results=[{"criterion": "AC1", "status": "pass"}],
        unresolved_risks=[],
        final_status="pass",
    )
    (artifact_dir / "completion.json").write_text(json.dumps(payload))

    result = runtime.validate_task_artifact(
        tmp_path,
        task_id=task_id,
        artifact_name="completion.json",
        changed_files=["src/example.py"],
    )

    assert result.ok is True
    assert result.errors == []


def test_should_fail_when_completion_artifact_has_failed_semantics(
    tmp_path: Path,
) -> None:
    runtime = _load_runtime()
    task_id = "T-001B"
    artifact_dir = tmp_path / ".etc_sdlc" / "tasks" / task_id
    artifact_dir.mkdir(parents=True)
    payload = _artifact_payload(
        task_id,
        ["src/example.py"],
        datetime.now(UTC),
        status="fail",
        checks=[{"name": "unit", "status": "fail"}],
        test_evidence=[{"command": "pytest", "status": "fail"}],
        review_evidence={"review": "review.json"},
        acceptance_criteria_results=[{"criterion": "AC1", "status": "fail"}],
        unresolved_risks=["coverage gap"],
        final_status="fail",
    )
    (artifact_dir / "completion.json").write_text(json.dumps(payload))

    result = runtime.validate_task_artifact(
        tmp_path,
        task_id=task_id,
        artifact_name="completion.json",
        changed_files=["src/example.py"],
    )

    assert result.ok is False
    assert "status must be pass" in result.errors
    assert "checks[0] status must be pass" in result.errors
    assert "test_evidence[0] status must be pass" in result.errors
    assert "acceptance_criteria_results[0] status must be pass" in result.errors
    assert "unresolved_risks must be empty" in result.errors
    assert "final_status must be pass" in result.errors


def test_should_fail_when_readiness_artifact_is_not_ready(tmp_path: Path) -> None:
    runtime = _load_runtime()
    task_id = "T-001C"
    artifact_dir = tmp_path / ".etc_sdlc" / "tasks" / task_id
    artifact_dir.mkdir(parents=True)
    payload = _artifact_payload(
        task_id,
        [],
        datetime.now(UTC),
        phase="build",
        risk_tier="low",
        files_in_scope=[],
        acceptance_criteria=[],
        required_reading=[],
        test_strategy="unit",
        dependencies=[],
        ready=False,
    )
    (artifact_dir / "readiness.json").write_text(json.dumps(payload))

    result = runtime.validate_task_artifact(
        tmp_path,
        task_id=task_id,
        artifact_name="readiness.json",
    )

    assert result.ok is False
    assert "ready must be true" in result.errors


def test_should_fail_when_task_artifact_required_field_is_missing(
    tmp_path: Path,
) -> None:
    runtime = _load_runtime()
    task_id = "T-002"
    artifact_dir = tmp_path / ".etc_sdlc" / "tasks" / task_id
    artifact_dir.mkdir(parents=True)
    payload = _artifact_payload(
        task_id,
        [],
        datetime.now(UTC),
        phase="build",
        risk_tier="low",
        files_in_scope=[],
        acceptance_criteria=[],
        required_reading=[],
        test_strategy="unit",
        dependencies=[],
    )
    payload.pop("ready", None)
    (artifact_dir / "readiness.json").write_text(json.dumps(payload))

    result = runtime.validate_task_artifact(
        tmp_path,
        task_id=task_id,
        artifact_name="readiness.json",
    )

    assert result.ok is False
    assert "missing required field: ready" in result.errors


def test_should_fail_when_task_artifact_is_stale_for_changed_file(
    tmp_path: Path,
) -> None:
    runtime = _load_runtime()
    task_id = "T-003"
    changed = tmp_path / "src" / "example.py"
    changed.parent.mkdir()
    changed.write_text("value = 1\n")
    artifact_dir = tmp_path / ".etc_sdlc" / "tasks" / task_id
    artifact_dir.mkdir(parents=True)

    now = datetime.now(UTC)
    artifact_time = now - timedelta(hours=1)
    file_time = now
    os.utime(changed, (file_time.timestamp(), file_time.timestamp()))
    payload = _artifact_payload(
        task_id,
        ["src/example.py"],
        artifact_time,
        required_reading=["src/example.py"],
        read_entries=[
            {
                "path": "src/example.py",
                "reason": "implementation context",
                "recorded_at": artifact_time.isoformat(),
                "mtime": artifact_time.timestamp(),
            }
        ],
        coverage={"src/example.py": True},
        missing=[],
        fresh=True,
    )
    (artifact_dir / "reading-ledger.json").write_text(json.dumps(payload))

    result = runtime.validate_task_artifact(
        tmp_path,
        task_id=task_id,
        artifact_name="reading-ledger.json",
        changed_files=["src/example.py"],
    )

    assert result.ok is False
    assert any("stale for changed file" in error for error in result.errors)


def test_cli_hook_normalize_wrapper_outputs_json(tmp_path: Path) -> None:
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "cwd": str(tmp_path),
        "tool_input": {"command": "pwd"},
    }

    result = subprocess.run(
        [str(RUNTIME_SHIM), "hook-normalize", "--client", "codex"],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    normalized = json.loads(result.stdout)
    assert normalized["tool_kind"] == "shell"
    assert normalized["commands"] == ["pwd"]


def test_cli_task_validate_requires_changed_file_for_freshness(
    tmp_path: Path,
) -> None:
    task_id = "T-004"
    artifact_dir = tmp_path / ".etc_sdlc" / "tasks" / task_id
    artifact_dir.mkdir(parents=True)
    payload = _artifact_payload(
        task_id,
        ["src/example.py"],
        datetime.now(UTC),
        test_evidence=[{"command": "pytest", "status": "pass"}],
        review_evidence={"review": "review.json"},
        acceptance_criteria_results=[{"criterion": "AC1", "status": "pass"}],
        unresolved_risks=[],
        final_status="pass",
    )
    (artifact_dir / "completion.json").write_text(json.dumps(payload))

    result = subprocess.run(
        [
            sys.executable,
            str(RUNTIME_PATH),
            "task",
            "validate",
            "--task-id",
            task_id,
            "--artifact",
            "completion.json",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    assert result.returncode == 1
    assert "--changed-file is required" in result.stderr


def test_cli_ci_check_fails_when_codex_install_surfaces_are_missing(
    tmp_path: Path,
) -> None:
    result = subprocess.run(
        [sys.executable, str(RUNTIME_PATH), "ci-check", "--client", "codex"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    assert result.returncode == 1
    assert "instructions missing" in result.stderr
    assert "not fully implemented" not in result.stderr
