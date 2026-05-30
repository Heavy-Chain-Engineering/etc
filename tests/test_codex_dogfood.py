"""Synthetic dogfood coverage for installed Codex harnesses."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_installed_codex_harness_passes_synthetic_dogfood(tmp_path: Path) -> None:
    harness = _copy_harness_source(tmp_path / "harness")
    target = tmp_path / "target"
    target.mkdir()

    _run(
        [
            sys.executable,
            "compile-sdlc.py",
            "spec/etc_sdlc.yaml",
            "--client",
            "codex",
        ],
        cwd=harness,
    )
    _run(
        ["bash", "install.sh", "--client", "codex", "--scope", "project"],
        cwd=harness,
        env={"ETC_PROJECT_DIR": str(target)},
    )

    _write_target_repo(target)
    _write_task_artifacts(target)
    _commit_all(target, "synthetic installed codex harness")

    assert (
        target / "standards" / "process" / "interactive-user-input.md"
    ).is_file()
    assert (target / "standards" / "process" / "codebase-navigation.md").is_file()

    blocked = _run_hook(
        target / ".codex" / "hooks" / "check-test-exists.sh",
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "apply_patch",
            "cwd": str(target),
            "tool_input": {
                "command": "\n".join(
                    [
                        "*** Begin Patch",
                        "*** Add File: src/no_test.py",
                        "+value = 1",
                        "*** End Patch",
                    ]
                )
            },
        },
    )
    assert blocked.returncode == 2
    assert "test_no_test.py" in blocked.stderr

    doctor = _run(
        [str(target / ".codex" / "scripts" / "etc-runtime"), "doctor", "--client", "codex"],
        cwd=target,
        check=False,
    )
    assert doctor.returncode == 0, doctor.stdout + doctor.stderr
    assert "ci_state: available-but-not-wired" in doctor.stdout

    ci_check = _run(
        [str(target / ".codex" / "scripts" / "etc-runtime"), "ci-check", "--client", "codex"],
        cwd=target,
        check=False,
    )
    assert ci_check.returncode == 0, ci_check.stdout + ci_check.stderr
    assert "OK: codex ci-check passed" in ci_check.stdout


def _copy_harness_source(destination: Path) -> Path:
    ignore = shutil.ignore_patterns(
        ".git",
        ".venv",
        "__pycache__",
        ".pytest_cache",
        "dist",
    )
    shutil.copytree(REPO_ROOT, destination, ignore=ignore)
    return destination


def _write_target_repo(target: Path) -> None:
    (target / "src").mkdir()
    (target / "src" / "example.py").write_text("value = 1\n", encoding="utf-8")
    (target / "tests").mkdir()
    (target / "tests" / "test_example.py").write_text(
        "def test_example():\n    assert True\n",
        encoding="utf-8",
    )


def _write_task_artifacts(target: Path) -> None:
    task_id = "T-001"
    changed_files = ["src/example.py"]
    artifact_dir = target / ".etc_sdlc" / "tasks" / task_id
    artifact_dir.mkdir(parents=True)
    updated_at = datetime.now(UTC) + timedelta(minutes=5)
    source_mtime = (target / "src" / "example.py").stat().st_mtime

    artifacts = {
        "readiness.json": _artifact_payload(
            task_id,
            changed_files,
            updated_at,
            phase="build",
            risk_tier="low",
            files_in_scope=changed_files,
            acceptance_criteria=["synthetic ci-check passes"],
            required_reading=["AGENTS.md"],
            test_strategy="pytest",
            dependencies=[],
            ready=True,
        ),
        "reading-ledger.json": _artifact_payload(
            task_id,
            changed_files,
            updated_at,
            required_reading=["AGENTS.md"],
            read_entries=[
                {
                    "path": "AGENTS.md",
                    "reason": "installed harness instructions",
                    "recorded_at": updated_at.isoformat(),
                    "mtime": source_mtime,
                }
            ],
            coverage={"AGENTS.md": True},
            missing=[],
            fresh=True,
        ),
        "review.json": _artifact_payload(
            task_id,
            changed_files,
            updated_at,
            reviewer="synthetic-reviewer",
            review_type="dogfood",
            findings=[],
            required_fixes=[],
            verdict="pass",
            fresh_for_changed_files=True,
        ),
        "completion.json": _artifact_payload(
            task_id,
            changed_files,
            updated_at,
            test_evidence=[{"command": "pytest", "status": "pass"}],
            review_evidence={"review": "review.json"},
            acceptance_criteria_results=[
                {"criterion": "synthetic ci-check passes", "status": "pass"}
            ],
            unresolved_risks=[],
            final_status="pass",
        ),
    }

    for name, payload in artifacts.items():
        (artifact_dir / name).write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _artifact_payload(
    task_id: str,
    changed_files: list[str],
    updated_at: datetime,
    **extra: object,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": 1,
        "task_id": task_id,
        "client": "codex",
        "created_at": updated_at.isoformat(),
        "updated_at": updated_at.isoformat(),
        "source_commit": "synthetic",
        "changed_files": changed_files,
        "status": "pass",
        "checks": [{"name": "synthetic", "status": "pass"}],
        "notes": [],
    }
    payload.update(extra)
    return payload


def _commit_all(repo: Path, message: str) -> None:
    _run(["git", "init"], cwd=repo)
    _run(["git", "add", "."], cwd=repo)
    _run(
        [
            "git",
            "-c",
            "user.name=Codex Test",
            "-c",
            "user.email=codex@example.test",
            "commit",
            "-m",
            message,
        ],
        cwd=repo,
    )


def _run_hook(hook: Path, payload: dict[str, object]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(hook)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )


def _run(
    args: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    return subprocess.run(
        args,
        cwd=cwd,
        env=merged_env,
        capture_output=True,
        text=True,
        timeout=60,
        check=check,
    )
