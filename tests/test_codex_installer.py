"""Codex installer coverage through etc_installer.

The parent installer architecture keeps install.sh as a uv bootstrap and routes
real install behavior through etc_installer. These tests exercise that Python
path directly so Codex support does not depend on the old Bash installer body.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

from typer.testing import CliRunner

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from etc_installer import cli  # noqa: E402


def test_should_dry_run_codex_project_install_without_writes(tmp_path: Path) -> None:
    dist = tmp_path / "dist" / "codex"
    project = tmp_path / "project"
    home = tmp_path / "home"
    _write_codex_dist(dist)
    project.mkdir()
    home.mkdir()

    result = CliRunner().invoke(
        cli.app,
        [
            "--client",
            "codex",
            "--scope",
            "project",
            "--dist-dir",
            str(dist),
            "--target-dir",
            str(project),
            "--dry-run",
        ],
        env={"HOME": str(home)},
    )

    assert result.exit_code == 0, result.output
    assert "Dry run: Codex project install plan" in result.output
    assert str(project / ".codex" / "expected") in result.output
    assert str(project / ".codex" / "source") in result.output
    assert not (project / ".codex").exists()
    assert not (home / ".codex").exists()
    assert not (home / ".claude").exists()


def test_should_fail_clearly_for_unsupported_codex_global_scope(
    tmp_path: Path,
) -> None:
    dist = tmp_path / "dist" / "codex"
    project = tmp_path / "project"
    home = tmp_path / "home"
    _write_codex_dist(dist)
    project.mkdir()
    home.mkdir()

    result = CliRunner().invoke(
        cli.app,
        [
            "--client",
            "codex",
            "--scope",
            "global",
            "--dist-dir",
            str(dist),
            "--target-dir",
            str(project),
        ],
        env={"HOME": str(home)},
    )

    assert result.exit_code == 1
    assert "Codex user/global install is not enabled" in result.output
    assert not (project / ".codex").exists()
    assert not (home / ".codex").exists()


def test_should_fail_clearly_for_unsupported_codex_user_scope(
    tmp_path: Path,
) -> None:
    dist = tmp_path / "dist" / "codex"
    project = tmp_path / "project"
    home = tmp_path / "home"
    _write_codex_dist(dist)
    project.mkdir()
    home.mkdir()

    result = CliRunner().invoke(
        cli.app,
        [
            "--client",
            "codex",
            "--scope",
            "user",
            "--dist-dir",
            str(dist),
            "--target-dir",
            str(project),
        ],
        env={"HOME": str(home)},
    )

    assert result.exit_code == 1
    assert "Codex user/global install is not enabled" in result.output
    assert not (project / ".codex").exists()
    assert not (home / ".codex").exists()


def test_should_install_codex_artifacts_when_project_target_is_clean(
    tmp_path: Path,
) -> None:
    dist = tmp_path / "dist" / "codex"
    project = tmp_path / "project"
    home = tmp_path / "home"
    _write_codex_dist(dist)
    project.mkdir()
    home.mkdir()

    result = _run_codex_install(dist, project, home)

    assert result.exit_code == 0, result.output
    assert (project / "AGENTS.md").read_text(encoding="utf-8").startswith(
        "# ETC Codex Harness"
    )
    assert (project / ".codex" / "hooks.json").is_file()
    assert (project / ".codex" / "hooks" / "check-test.sh").is_file()
    assert os.access(project / ".codex" / "hooks" / "check-test.sh", os.X_OK)
    assert (project / ".codex" / "agents" / "sem.toml").is_file()
    assert (project / ".codex" / "scripts" / "etc-runtime").is_file()
    assert os.access(project / ".codex" / "scripts" / "etc-runtime", os.X_OK)
    assert (project / ".codex" / "schemas" / "task-proof.schema.json").is_file()
    assert (
        project / "standards" / "process" / "interactive-user-input.md"
    ).is_file()
    assert (project / "standards" / "process" / "codebase-navigation.md").is_file()
    assert (
        project / ".codex" / "standards" / "process" / "interactive-user-input.md"
    ).is_file()
    assert (project / ".codex" / "expected" / "AGENTS.md").is_file()
    assert (project / ".codex" / "source" / "compile-sdlc.py").is_file()
    assert (project / ".agents" / "skills" / "spec" / "SKILL.md").is_file()
    assert (project / "gate-classification.json").is_file()
    assert not (home / ".codex").exists()
    assert not (home / ".claude").exists()


def test_should_fail_codex_install_when_standards_surface_is_missing(
    tmp_path: Path,
) -> None:
    dist = tmp_path / "dist" / "codex"
    project = tmp_path / "project"
    home = tmp_path / "home"
    _write_codex_dist(dist)
    project.mkdir()
    home.mkdir()
    _remove_tree(dist / ".codex" / "standards")

    result = _run_codex_install(dist, project, home)

    assert result.exit_code == 1
    assert "dist/codex/.codex/standards not found" in result.output
    assert not (project / ".codex" / "hooks").exists()
    assert not (home / ".codex").exists()


def test_should_fail_codex_install_when_root_standards_surface_is_missing(
    tmp_path: Path,
) -> None:
    dist = tmp_path / "dist" / "codex"
    project = tmp_path / "project"
    home = tmp_path / "home"
    _write_codex_dist(dist)
    project.mkdir()
    home.mkdir()
    _remove_tree(dist / "standards")

    result = _run_codex_install(dist, project, home)

    assert result.exit_code == 1
    assert "dist/codex/standards not found" in result.output
    assert not (project / ".codex" / "hooks").exists()
    assert not (project / "standards").exists()
    assert not (home / ".codex").exists()


def test_should_use_etc_project_dir_for_codex_project_install(
    tmp_path: Path,
) -> None:
    dist = tmp_path / "dist" / "codex"
    project = tmp_path / "project"
    home = tmp_path / "home"
    isolated_cwd = tmp_path / "cwd"
    _write_codex_dist(dist)
    project.mkdir()
    home.mkdir()
    isolated_cwd.mkdir()

    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=isolated_cwd):
        cwd = Path.cwd()
        result = runner.invoke(
            cli.app,
            [
                "--client",
                "codex",
                "--scope",
                "project",
                "--dist-dir",
                str(dist),
            ],
            env={"HOME": str(home), "ETC_PROJECT_DIR": str(project)},
        )
        assert not (cwd / ".codex").exists()

    assert result.exit_code == 0, result.output
    assert (project / ".codex" / "hooks" / "check-test.sh").is_file()
    assert (project / ".agents" / "skills" / "spec" / "SKILL.md").is_file()
    assert (
        project / "standards" / "process" / "interactive-user-input.md"
    ).is_file()
    assert not (home / ".codex").exists()
    assert not (home / ".claude").exists()


def test_should_replace_etc_owned_skill_dirs_without_deleting_project_skills(
    tmp_path: Path,
) -> None:
    dist = tmp_path / "dist" / "codex"
    project = tmp_path / "project"
    home = tmp_path / "home"
    _write_codex_dist(dist)
    project.mkdir()
    home.mkdir()

    first = _run_codex_install(dist, project, home)
    stale_etc_file = project / ".agents" / "skills" / "spec" / "stale.md"
    stale_etc_file.write_text("stale\n", encoding="utf-8")
    project_skill = project / ".agents" / "skills" / "project-skill" / "SKILL.md"
    project_skill.parent.mkdir(parents=True)
    project_skill.write_text("project skill\n", encoding="utf-8")
    second = _run_codex_install(dist, project, home)

    assert first.exit_code == 0, first.output
    assert second.exit_code == 0, second.output
    assert not stale_etc_file.exists()
    assert project_skill.read_text(encoding="utf-8") == "project skill\n"
    assert (project / ".agents" / "skills" / "spec" / "SKILL.md").is_file()


def test_should_merge_root_standards_without_deleting_project_standards(
    tmp_path: Path,
) -> None:
    dist = tmp_path / "dist" / "codex"
    project = tmp_path / "project"
    home = tmp_path / "home"
    _write_codex_dist(dist)
    project.mkdir()
    home.mkdir()
    project_standard = project / "standards" / "process" / "project-only.md"
    project_standard.parent.mkdir(parents=True)
    project_standard.write_text("project standard\n", encoding="utf-8")

    result = _run_codex_install(dist, project, home)

    assert result.exit_code == 0, result.output
    assert project_standard.read_text(encoding="utf-8") == "project standard\n"
    assert (
        project / "standards" / "process" / "interactive-user-input.md"
    ).is_file()
    assert (project / "standards" / "process" / "codebase-navigation.md").is_file()


def test_should_keep_codex_install_idempotent_when_re_run(tmp_path: Path) -> None:
    dist = tmp_path / "dist" / "codex"
    project = tmp_path / "project"
    home = tmp_path / "home"
    _write_codex_dist(dist)
    project.mkdir()
    home.mkdir()

    first = _run_codex_install(dist, project, home)
    before = _project_file_snapshot(project)
    second = _run_codex_install(dist, project, home)
    after = _project_file_snapshot(project)

    assert first.exit_code == 0, first.output
    assert second.exit_code == 0, second.output
    assert after == before
    assert not (home / ".codex").exists()
    assert not (home / ".claude").exists()


def test_should_merge_codex_instructions_and_preserve_project_skills(
    tmp_path: Path,
) -> None:
    dist = tmp_path / "dist" / "codex"
    project = tmp_path / "project"
    home = tmp_path / "home"
    _write_codex_dist(dist)
    project.mkdir()
    home.mkdir()
    (project / "AGENTS.md").write_text(
        "# Project Instructions\n\nKeep this repo-specific context.\n",
        encoding="utf-8",
    )
    project_skill = project / ".agents" / "skills" / "project-skill" / "SKILL.md"
    project_skill.parent.mkdir(parents=True)
    project_skill.write_text("project skill\n", encoding="utf-8")

    first = _run_codex_install(dist, project, home)
    second = _run_codex_install(dist, project, home)

    assert first.exit_code == 0, first.output
    assert second.exit_code == 0, second.output
    agents_md = (project / "AGENTS.md").read_text(encoding="utf-8")
    assert "# Project Instructions" in agents_md
    assert "# ETC Codex Harness" in agents_md
    assert agents_md.count("<!-- ETC_CODEX_BEGIN -->") == 1
    assert agents_md.count("<!-- ETC_CODEX_END -->") == 1
    assert project_skill.read_text(encoding="utf-8") == "project skill\n"
    assert (project / ".agents" / "skills" / "spec" / "SKILL.md").is_file()


def _run_codex_install(dist: Path, project: Path, home: Path):
    return CliRunner().invoke(
        cli.app,
        [
            "--client",
            "codex",
            "--scope",
            "project",
            "--dist-dir",
            str(dist),
            "--target-dir",
            str(project),
        ],
        env={"HOME": str(home)},
    )


def _write_codex_dist(dist: Path) -> None:
    (dist / ".codex" / "hooks").mkdir(parents=True)
    (dist / ".codex" / "hooks" / "check-test.sh").write_text(
        "#!/usr/bin/env bash\nexit 0\n",
        encoding="utf-8",
    )
    (dist / ".codex" / "hooks.json").write_text(
        json.dumps(
            {
                "PostToolUse": [
                    {
                        "matcher": "apply_patch",
                        "hooks": [
                            {
                                "type": "command",
                                "command": "bash .codex/hooks/check-test.sh",
                            }
                        ],
                    }
                ]
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    (dist / ".codex" / "agents").mkdir(parents=True)
    (dist / ".codex" / "agents" / "sem.toml").write_text(
        'name = "sem"\n',
        encoding="utf-8",
    )
    (dist / ".codex" / "scripts").mkdir(parents=True)
    (dist / ".codex" / "scripts" / "etc-runtime").write_text(
        "#!/usr/bin/env bash\nexit 0\n",
        encoding="utf-8",
    )
    (dist / ".codex" / "schemas").mkdir(parents=True)
    (dist / ".codex" / "schemas" / "task-proof.schema.json").write_text(
        '{"type":"object"}\n',
        encoding="utf-8",
    )
    (dist / ".codex" / "expected").mkdir(parents=True)
    (dist / ".codex" / "expected" / "AGENTS.md").write_text(
        "# ETC Codex Harness\n",
        encoding="utf-8",
    )
    (dist / ".codex" / "source" / "spec").mkdir(parents=True)
    (dist / ".codex" / "source" / "compile-sdlc.py").write_text(
        "#!/usr/bin/env python3\n",
        encoding="utf-8",
    )
    (dist / ".codex" / "source" / "spec" / "etc_sdlc.yaml").write_text(
        "version: 1.0\n",
        encoding="utf-8",
    )
    for standards_root in (dist / "standards", dist / ".codex" / "standards"):
        (standards_root / "code").mkdir(parents=True)
        (standards_root / "code" / "python-conventions.md").write_text(
            "codex standard\n",
            encoding="utf-8",
        )
        (standards_root / "process").mkdir(parents=True)
        (
            standards_root / "process" / "interactive-user-input.md"
        ).write_text(
            "interactive input standard\n",
            encoding="utf-8",
        )
        (standards_root / "process" / "codebase-navigation.md").write_text(
            "navigation standard\n",
            encoding="utf-8",
        )
    (dist / ".agents" / "skills" / "spec").mkdir(parents=True)
    (dist / ".agents" / "skills" / "spec" / "SKILL.md").write_text(
        "codex skill\n",
        encoding="utf-8",
    )
    (dist / "AGENTS.md").write_text("# ETC Codex Harness\n", encoding="utf-8")
    (dist / "gate-classification.json").write_text(
        '{"check-test":{"mode":"active"}}\n',
        encoding="utf-8",
    )


def _remove_tree(path: Path) -> None:
    shutil.rmtree(path)


def _project_file_snapshot(project_dir: Path) -> dict[str, str]:
    return {
        str(path.relative_to(project_dir)): path.read_text(encoding="utf-8")
        for path in sorted(project_dir.rglob("*"))
        if path.is_file()
    }
