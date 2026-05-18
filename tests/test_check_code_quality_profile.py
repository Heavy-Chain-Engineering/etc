"""F020 — check-code-quality profile-aware dispatch.

Generalizes hooks/check-code-quality.sh from Python-AST-only to a
profile dispatcher. The pre-F020 behavior (CQ-001 mutable globals +
CQ-002 noop functions on .py files) is preserved as the python profile's
gate script — BR-007 zero-regression. The typescript profile adds
PreToolUse grep checks for obvious patterns (empty function bodies,
module-level let). Other profiles WARN-skip per ADR-F020-003.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

ETC_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = ETC_ROOT / "hooks"
SCRIPTS_DIR = ETC_ROOT / "scripts"
PROFILES_DIR = ETC_ROOT / "standards" / "code" / "profiles"


def _seed_workspace(tmp_path: Path, profile: str) -> Path:
    """Seed a workspace with F020 dispatch assets + named profile + markers."""
    scripts_dst = tmp_path / "scripts"
    scripts_dst.mkdir(exist_ok=True)
    shutil.copy2(SCRIPTS_DIR / "profile_loader.py", scripts_dst / "profile_loader.py")
    shutil.copy2(SCRIPTS_DIR / "dispatch_profile.sh", scripts_dst / "dispatch_profile.sh")
    shutil.copy2(SCRIPTS_DIR / "detect_profiles.py", scripts_dst / "detect_profiles.py")

    profile_dst = tmp_path / "standards" / "code" / "profiles" / profile
    profile_dst.mkdir(parents=True, exist_ok=True)
    profile_src = PROFILES_DIR / profile
    for f in profile_src.iterdir():
        if f.is_file():
            shutil.copy2(f, profile_dst / f.name)

    # Copy helpers for python profile so check-code-quality can find them
    if profile == "python":
        helpers_dst = tmp_path / "hooks" / "helpers"
        helpers_dst.mkdir(parents=True, exist_ok=True)
        for f in (HOOKS_DIR / "helpers").iterdir():
            if f.is_file() and f.suffix == ".py":
                shutil.copy2(f, helpers_dst / f.name)

    # Write profiles.lock
    lockdir = tmp_path / ".etc_sdlc"
    lockdir.mkdir(exist_ok=True)
    (lockdir / "profiles.lock").write_text(f"{profile}\n")

    return tmp_path


def _run_hook(payload: dict, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(HOOKS_DIR / "check-code-quality.sh")],
        input=json.dumps(payload),
        capture_output=True, text=True, timeout=30,
        cwd=str(cwd),
    )


class TestPythonProfileCodeQuality:
    """python profile preserves pre-F020 AST-based checks (BR-007)."""

    def test_should_block_module_level_mutable_assignment(self, tmp_path: Path) -> None:
        workspace = _seed_workspace(tmp_path, "python")
        target = workspace / "src" / "app.py"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("CACHE = []\n")

        result = _run_hook(
            {"tool_input": {"file_path": str(target)}, "cwd": str(workspace)},
            workspace,
        )
        assert result.returncode == 2, f"Expected block (2), got {result.returncode}; stderr={result.stderr}"
        assert "CQ-001" in result.stderr

    def test_should_allow_clean_python_file(self, tmp_path: Path) -> None:
        workspace = _seed_workspace(tmp_path, "python")
        target = workspace / "src" / "app.py"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("def add(a: int, b: int) -> int:\n    return a + b\n")

        result = _run_hook(
            {"tool_input": {"file_path": str(target)}, "cwd": str(workspace)},
            workspace,
        )
        assert result.returncode == 0, f"Expected allow (0), got {result.returncode}; stderr={result.stderr}"


class TestTypescriptProfileCodeQuality:
    """typescript profile flags obvious anti-patterns at PreToolUse."""

    def _seed_ts(self, tmp_path: Path) -> Path:
        workspace = _seed_workspace(tmp_path, "typescript")
        (workspace / "package.json").write_text('{"name":"x","version":"0.0.1"}\n')
        (workspace / "tsconfig.json").write_text("{}\n")
        return workspace

    def test_should_block_empty_function_body(self, tmp_path: Path) -> None:
        workspace = self._seed_ts(tmp_path)
        target = workspace / "src" / "noop.ts"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("export function doNothing(): void {}\n")

        result = _run_hook(
            {"tool_input": {"file_path": str(target)}, "cwd": str(workspace)},
            workspace,
        )
        assert result.returncode == 2, f"Expected block (2), got {result.returncode}; stderr={result.stderr}"
        assert "no-op" in result.stderr.lower() or "empty" in result.stderr.lower()

    def test_should_allow_clean_typescript(self, tmp_path: Path) -> None:
        workspace = self._seed_ts(tmp_path)
        target = workspace / "src" / "greet.ts"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('export function greet(name: string): string {\n  return `Hi ${name}`;\n}\n')

        result = _run_hook(
            {"tool_input": {"file_path": str(target)}, "cwd": str(workspace)},
            workspace,
        )
        assert result.returncode == 0, f"Expected allow (0), got {result.returncode}; stderr={result.stderr}"

    def test_should_warn_skip_unknown_language(self, tmp_path: Path) -> None:
        """A .lua file claimed by no profile → WARN + exit 0."""
        workspace = self._seed_ts(tmp_path)
        target = workspace / "src" / "x.lua"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("function noop() end\n")

        result = _run_hook(
            {"tool_input": {"file_path": str(target)}, "cwd": str(workspace)},
            workspace,
        )
        assert result.returncode == 0, f"Expected WARN-skip (0), got {result.returncode}; stderr={result.stderr}"
