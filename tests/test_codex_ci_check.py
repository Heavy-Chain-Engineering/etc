"""Integration tests for Codex runtime health and CI validation."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RUNTIME_PATH = REPO_ROOT / "scripts" / "etc_runtime.py"


def test_should_report_codex_runtime_health_when_fixture_repo_is_valid(
    tmp_path: Path,
) -> None:
    project = _create_valid_codex_project(tmp_path)

    result = _run_runtime(project, "doctor", "--client", "codex")

    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "instructions: present" in result.stdout
    assert "skills: present" in result.stdout
    assert "agents: present" in result.stdout
    assert "hooks: present" in result.stdout
    assert "runtime: present" in result.stdout
    assert "schemas: present" in result.stdout
    assert "standards: present" in result.stdout
    assert "source: present" in result.stdout
    assert "ci_state: available-but-not-wired" in result.stdout
    assert "unsupported_gaps:" in result.stdout


def test_should_report_enabled_ci_when_workflow_wires_ci_check(
    tmp_path: Path,
) -> None:
    project = _create_valid_codex_project(tmp_path)
    workflow = project / ".github" / "workflows" / "codex.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        "jobs:\n"
        "  codex:\n"
        "    steps:\n"
        "      - run: .codex/scripts/etc-runtime ci-check --client codex\n",
        encoding="utf-8",
    )
    _run_git(project, "add", ".github/workflows/codex.yml")
    _run_git(
        project,
        "-c",
        "user.name=Codex Test",
        "-c",
        "user.email=codex@example.test",
        "commit",
        "-m",
        "wire codex ci",
    )

    result = _run_runtime(project, "doctor", "--client", "codex")

    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "ci_state: enabled" in result.stdout


def test_should_report_unsupported_ci_when_runtime_is_missing(
    tmp_path: Path,
) -> None:
    project = _create_valid_codex_project(tmp_path)
    (project / ".codex" / "scripts" / "etc-runtime").unlink()

    result = _run_runtime(project, "doctor", "--client", "codex")

    output = result.stdout + result.stderr
    assert result.returncode == 1, output
    assert "ci_state: unsupported" in result.stdout
    assert "runtime missing" in result.stdout


def test_should_pass_ci_check_when_fixture_repo_is_valid(tmp_path: Path) -> None:
    project = _create_valid_codex_project(tmp_path)

    result = _run_runtime(project, "ci-check", "--client", "codex")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "OK: codex ci-check passed" in result.stdout


def test_should_fail_ci_check_when_generated_codex_output_drifts(
    tmp_path: Path,
) -> None:
    project = _create_valid_codex_project(tmp_path)
    (project / "AGENTS.md").write_text("drifted\n", encoding="utf-8")

    result = _run_runtime(project, "ci-check", "--client", "codex")

    assert result.returncode == 1
    assert "generated output drift: AGENTS.md" in result.stderr


def test_should_fail_ci_check_when_source_snapshot_is_missing(
    tmp_path: Path,
) -> None:
    project = _create_valid_codex_project(tmp_path)
    shutil.rmtree(project / ".codex" / "source")

    result = _run_runtime(project, "ci-check", "--client", "codex")

    assert result.returncode == 1
    assert "source missing" in result.stderr


def test_should_fail_ci_check_when_root_standards_surface_is_missing(
    tmp_path: Path,
) -> None:
    project = _create_valid_codex_project(tmp_path)
    shutil.rmtree(project / "standards")

    result = _run_runtime(project, "ci-check", "--client", "codex")

    assert result.returncode == 1
    assert "standards missing" in result.stderr
    assert (
        "generated output drift: standards/process/interactive-user-input.md missing"
        in result.stderr
    )


def test_should_pass_ci_check_when_agents_md_uses_managed_codex_block(
    tmp_path: Path,
) -> None:
    project = _create_valid_codex_project(tmp_path)
    generated = (project / "AGENTS.md").read_text(encoding="utf-8")
    (project / "AGENTS.md").write_text(
        "# Project Instructions\n\n"
        "Keep this repo-specific context.\n\n"
        "<!-- ETC_CODEX_BEGIN -->\n"
        f"{generated.rstrip()}\n"
        "<!-- ETC_CODEX_END -->\n",
        encoding="utf-8",
    )
    _run_git(project, "add", "AGENTS.md")
    _run_git(
        project,
        "-c",
        "user.name=Codex Test",
        "-c",
        "user.email=codex@example.test",
        "commit",
        "-m",
        "merge codex instructions",
    )

    result = _run_runtime(project, "ci-check", "--client", "codex")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "OK: codex ci-check passed" in result.stdout


def test_should_fail_ci_check_when_required_proof_artifact_is_missing(
    tmp_path: Path,
) -> None:
    project = _create_valid_codex_project(tmp_path)
    (project / ".etc_sdlc" / "tasks" / "T-001" / "review.json").unlink()

    result = _run_runtime(project, "ci-check", "--client", "codex")

    assert result.returncode == 1
    assert "missing artifact" in result.stderr
    assert "review.json" in result.stderr


def test_should_fail_ci_check_when_proof_artifact_is_stale(
    tmp_path: Path,
) -> None:
    project = _create_valid_codex_project(tmp_path)
    changed = project / "src" / "example.py"
    changed.write_text("value = 2\n", encoding="utf-8")
    future = datetime.now(UTC) + timedelta(hours=1)
    os.utime(changed, (future.timestamp(), future.timestamp()))

    result = _run_runtime(project, "ci-check", "--client", "codex")

    assert result.returncode == 1
    assert "artifact stale for changed file: src/example.py" in result.stderr


def test_should_fail_ci_check_when_harness_config_change_is_unauthorized(
    tmp_path: Path,
) -> None:
    project = _create_valid_codex_project(tmp_path)
    (project / "install.sh").write_text("# changed\n", encoding="utf-8")

    result = _run_runtime(project, "ci-check", "--client", "codex")

    assert result.returncode == 1
    assert "unauthorized harness/config change: install.sh" in result.stderr


def test_should_fail_ci_check_when_codex_output_contains_claude_home(
    tmp_path: Path,
) -> None:
    project = _create_valid_codex_project(tmp_path)
    bad_hook = project / ".codex" / "hooks" / "bad.sh"
    bad_hook.write_text("echo ~/.claude\n", encoding="utf-8")

    result = _run_runtime(project, "ci-check", "--client", "codex")

    assert result.returncode == 1
    assert "hardcoded ~/.claude in Codex output: .codex/hooks/bad.sh" in result.stderr


def _run_runtime(project: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(RUNTIME_PATH), *args],
        cwd=project,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )


def _create_valid_codex_project(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    compiled = tmp_path / "compiled"
    project.mkdir()
    _copy_source_inputs(project)
    _compile_codex(project, compiled)
    _copy_tree_contents(compiled, project)
    _write_example_source(project)
    _write_task_artifacts(project)
    _commit_fixture(project)
    return project


def _copy_source_inputs(project: Path) -> None:
    shutil.copy2(REPO_ROOT / "compile-sdlc.py", project / "compile-sdlc.py")
    shutil.copy2(REPO_ROOT / "install.sh", project / "install.sh")
    # agents/ included: the compiler's declared-vs-disk parity gate (audit
    # init 3) fails a repo whose declared agents are missing on disk — a
    # partial fixture tree now fails the compile, faithfully.
    for directory in ("spec", "hooks", "skills", "standards", "scripts", "agents"):
        shutil.copytree(
            REPO_ROOT / directory,
            project / directory,
            ignore=shutil.ignore_patterns("__pycache__"),
        )


def _compile_codex(project: Path, output: Path) -> None:
    subprocess.run(
        [
            sys.executable,
            str(project / "compile-sdlc.py"),
            str(project / "spec" / "etc_sdlc.yaml"),
            "--client",
            "codex",
            "--output",
            str(output),
        ],
        cwd=project,
        capture_output=True,
        text=True,
        timeout=20,
        check=True,
    )


def _copy_tree_contents(source: Path, destination: Path) -> None:
    for path in sorted(source.iterdir(), key=lambda item: item.name):
        target = destination / path.name
        if path.is_dir():
            shutil.copytree(path, target, dirs_exist_ok=True)
        else:
            shutil.copy2(path, target)


def _write_example_source(project: Path) -> None:
    source = project / "src" / "example.py"
    source.parent.mkdir()
    source.write_text("value = 1\n", encoding="utf-8")


def _write_task_artifacts(project: Path) -> None:
    task_id = "T-001"
    changed_files = ["src/example.py"]
    artifact_dir = project / ".etc_sdlc" / "tasks" / task_id
    artifact_dir.mkdir(parents=True)
    updated_at = datetime.now(UTC) + timedelta(minutes=5)
    source_mtime = (project / "src" / "example.py").stat().st_mtime

    artifacts = {
        "readiness.json": _artifact_payload(
            task_id,
            changed_files,
            updated_at,
            phase="build",
            risk_tier="low",
            files_in_scope=changed_files,
            acceptance_criteria=["ci-check passes"],
            required_reading=["spec/etc_sdlc.yaml"],
            test_strategy="pytest",
            dependencies=[],
            ready=True,
        ),
        "reading-ledger.json": _artifact_payload(
            task_id,
            changed_files,
            updated_at,
            required_reading=["spec/etc_sdlc.yaml"],
            read_entries=[
                {
                    "path": "spec/etc_sdlc.yaml",
                    "reason": "source of truth",
                    "recorded_at": updated_at.isoformat(),
                    "mtime": source_mtime,
                }
            ],
            coverage={"spec/etc_sdlc.yaml": True},
            missing=[],
            fresh=True,
        ),
        "review.json": _artifact_payload(
            task_id,
            changed_files,
            updated_at,
            reviewer="code-reviewer",
            review_type="deterministic",
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
                {"criterion": "ci-check passes", "status": "pass"}
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
        "source_commit": "fixture",
        "changed_files": changed_files,
        "status": "pass",
        "checks": [{"name": "unit", "status": "pass"}],
        "notes": [],
    }
    payload.update(extra)
    return payload


def _commit_fixture(project: Path) -> None:
    _run_git(project, "init")
    _run_git(project, "add", ".")
    _run_git(
        project,
        "-c",
        "user.name=Codex Test",
        "-c",
        "user.email=codex@example.test",
        "commit",
        "-m",
        "fixture",
    )


def _run_git(project: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=project,
        capture_output=True,
        text=True,
        timeout=20,
        check=True,
    )
