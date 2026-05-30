"""Tests for Codex plugin convenience packaging."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
COMPILE_SCRIPT = REPO_ROOT / "compile-sdlc.py"
SPEC_PATH = REPO_ROOT / "spec" / "etc_sdlc.yaml"


def test_should_emit_codex_plugin_package_when_client_is_codex(tmp_path: Path) -> None:
    output_dir = tmp_path / "codex"

    _run_compile(output_dir, "--client", "codex")

    plugin_root = output_dir / "plugins" / "etc-sdlc"
    manifest = json.loads(
        (plugin_root / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
    )
    hooks_config = json.loads(
        (plugin_root / "hooks" / "hooks.json").read_text(encoding="utf-8")
    )

    assert manifest["name"] == "etc-sdlc"
    assert manifest["version"] == "1.0.0"
    assert manifest["skills"] == "./skills/"
    assert manifest["interface"]["defaultPrompt"] == [
        "Start an ETC spec workflow.",
        "Run ETC task readiness checks.",
        "Review ETC completion proof.",
    ]
    assert "agents" not in manifest
    assert "hooks" in hooks_config
    assert (plugin_root / "skills" / "build" / "SKILL.md").is_file()
    assert (plugin_root / "hooks" / "check-test-exists.sh").is_file()
    assert (plugin_root / "hooks" / "helpers" / "hook_payload.py").is_file()
    assert _generated_cache_files(output_dir) == []


def test_should_record_installer_owned_surfaces_when_agents_are_not_bundled(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "codex"

    _run_compile(output_dir, "--client", "codex")

    plugin_root = output_dir / "plugins" / "etc-sdlc"
    classification = json.loads(
        (plugin_root / "codex-plugin-classification.json").read_text(encoding="utf-8")
    )

    assert classification["custom_agents_bundled"] is False
    assert "skills" in classification["bundled_surfaces"]
    assert "hooks" in classification["bundled_surfaces"]
    assert ".codex/agents" in classification["installer_owned_surfaces"]
    assert ".codex/scripts" in classification["installer_owned_surfaces"]
    assert not (plugin_root / ".codex" / "agents").exists()


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


def _generated_cache_files(output_dir: Path) -> list[str]:
    offenders: list[str] = []
    for path in sorted(output_dir.rglob("*")):
        if "__pycache__" in path.parts or path.suffix in {".pyc", ".pyo"}:
            offenders.append(path.relative_to(output_dir).as_posix())
    return offenders
