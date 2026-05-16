"""F021 typescript profile — end-to-end integration tests.

These tests exercise the full F020 dispatch path against the fixture at
`tests/fixtures/typescript-repo/`. They are the proof case that the
profile architecture works for a SECOND language (Python being profile-0).

Coverage:
  1. detect_profiles.py detects typescript when package.json + tsconfig.json
     are present (BR-003, BR-004).
  2. profile_loader.py routes .ts/.tsx files to typescript (BR-006).
  3. hooks/check-test-exists.sh BLOCKS when a typescript source file has
     no sibling test (F021 contract, BR-007 zero-regression equivalent).
  4. hooks/check-test-exists.sh ALLOWS when a sibling test exists.
  5. WARN-skip path: a .lua file (no profile claims it) → WARN + exit 0
     (BR-008).
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

ETC_ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ETC_ROOT / "tests" / "fixtures" / "typescript-repo"
HOOKS_DIR = ETC_ROOT / "hooks"
SCRIPTS_DIR = ETC_ROOT / "scripts"


def _seed_typescript_workspace(tmp_path: Path) -> Path:
    """Copy the typescript fixture + F020 dispatch assets into tmp_path.

    Returns the workspace root (== tmp_path).
    """
    # Copy fixture files
    for f in FIXTURE.rglob("*"):
        if f.is_file():
            dest = tmp_path / f.relative_to(FIXTURE)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, dest)

    # Copy F020 dispatch assets
    scripts_dst = tmp_path / "scripts"
    scripts_dst.mkdir(exist_ok=True)
    shutil.copy2(SCRIPTS_DIR / "profile_loader.py", scripts_dst / "profile_loader.py")
    shutil.copy2(SCRIPTS_DIR / "dispatch_profile.sh", scripts_dst / "dispatch_profile.sh")
    shutil.copy2(SCRIPTS_DIR / "detect_profiles.py", scripts_dst / "detect_profiles.py")

    # Copy the typescript profile
    profile_src = ETC_ROOT / "standards" / "code" / "profiles" / "typescript"
    profile_dst = tmp_path / "standards" / "code" / "profiles" / "typescript"
    profile_dst.mkdir(parents=True, exist_ok=True)
    for f in profile_src.iterdir():
        if f.is_file():
            shutil.copy2(f, profile_dst / f.name)

    return tmp_path


def _run_hook(hook_name: str, payload: dict, cwd: Path) -> subprocess.CompletedProcess[str]:
    """Invoke an etc hook against the workspace; return CompletedProcess."""
    hook = HOOKS_DIR / hook_name
    return subprocess.run(
        ["bash", str(hook)],
        input=json.dumps(payload),
        capture_output=True, text=True, timeout=30,
        cwd=str(cwd),
    )


class TestTypescriptProfileDetection:
    """detect_profiles.py + profiles.lock for a typescript-shaped repo."""

    def test_should_detect_typescript_from_package_json(self, tmp_path: Path) -> None:
        workspace = _seed_typescript_workspace(tmp_path)
        result = subprocess.run(
            ["python3", str(SCRIPTS_DIR / "detect_profiles.py"),
             "--repo-root", str(workspace)],
            capture_output=True, text=True, check=True,
        )
        profiles = [p for p in result.stdout.splitlines() if p.strip()]
        assert "typescript" in profiles

    def test_should_write_typescript_to_profiles_lock(self, tmp_path: Path) -> None:
        workspace = _seed_typescript_workspace(tmp_path)
        subprocess.run(
            ["python3", str(SCRIPTS_DIR / "detect_profiles.py"),
             "--repo-root", str(workspace), "--write-lock"],
            capture_output=True, text=True, check=True,
        )
        lock = workspace / ".etc_sdlc" / "profiles.lock"
        assert lock.read_text().strip() == "typescript"


class TestTypescriptProfileRouting:
    """profile_loader resolves .ts/.tsx files to typescript."""

    def test_should_route_ts_to_typescript(self, tmp_path: Path) -> None:
        workspace = _seed_typescript_workspace(tmp_path)
        (workspace / ".etc_sdlc").mkdir(exist_ok=True)
        (workspace / ".etc_sdlc" / "profiles.lock").write_text("typescript\n")

        result = subprocess.run(
            ["python3", str(SCRIPTS_DIR / "profile_loader.py"),
             "profile-for", "src/greet.ts",
             "--lock-path", str(workspace / ".etc_sdlc" / "profiles.lock")],
            capture_output=True, text=True, check=True,
            cwd=str(workspace),
        )
        assert result.stdout.strip() == "typescript"

    def test_should_route_tsx_to_typescript(self, tmp_path: Path) -> None:
        workspace = _seed_typescript_workspace(tmp_path)
        (workspace / ".etc_sdlc").mkdir(exist_ok=True)
        (workspace / ".etc_sdlc" / "profiles.lock").write_text("typescript\n")

        result = subprocess.run(
            ["python3", str(SCRIPTS_DIR / "profile_loader.py"),
             "profile-for", "src/Button.tsx",
             "--lock-path", str(workspace / ".etc_sdlc" / "profiles.lock")],
            capture_output=True, text=True, check=True,
            cwd=str(workspace),
        )
        assert result.stdout.strip() == "typescript"

    def test_should_exclude_node_modules(self, tmp_path: Path) -> None:
        workspace = _seed_typescript_workspace(tmp_path)
        (workspace / ".etc_sdlc").mkdir(exist_ok=True)
        (workspace / ".etc_sdlc" / "profiles.lock").write_text("typescript\n")

        result = subprocess.run(
            ["python3", str(SCRIPTS_DIR / "profile_loader.py"),
             "profile-for", "node_modules/lodash/index.ts",
             "--lock-path", str(workspace / ".etc_sdlc" / "profiles.lock")],
            capture_output=True, text=True, check=True,
            cwd=str(workspace),
        )
        # node_modules is in exclude_globs; profile_loader returns nothing
        assert result.stdout.strip() == ""


class TestTypescriptTddGate:
    """hooks/check-test-exists.sh dispatched to the typescript profile."""

    def test_should_allow_edit_when_sibling_test_exists(self, tmp_path: Path) -> None:
        workspace = _seed_typescript_workspace(tmp_path)
        (workspace / ".etc_sdlc").mkdir(exist_ok=True)
        (workspace / ".etc_sdlc" / "profiles.lock").write_text("typescript\n")

        # greet.ts has a sibling greet.test.ts; gate should pass
        payload = {
            "cwd": str(workspace),
            "tool_input": {"file_path": str(workspace / "src" / "greet.ts")},
        }
        result = _run_hook("check-test-exists.sh", payload, workspace)
        assert result.returncode == 0, (
            f"Expected exit 0 (allow); got {result.returncode}\n"
            f"stderr: {result.stderr}"
        )

    def test_should_block_edit_when_no_sibling_test(self, tmp_path: Path) -> None:
        workspace = _seed_typescript_workspace(tmp_path)
        (workspace / ".etc_sdlc").mkdir(exist_ok=True)
        (workspace / ".etc_sdlc" / "profiles.lock").write_text("typescript\n")

        # Create a new source file with no sibling test
        new_src = workspace / "src" / "untested.ts"
        new_src.write_text("export const x = 1;\n")

        payload = {
            "cwd": str(workspace),
            "tool_input": {"file_path": str(new_src)},
        }
        result = _run_hook("check-test-exists.sh", payload, workspace)
        assert result.returncode == 2, (
            f"Expected exit 2 (block); got {result.returncode}\n"
            f"stderr: {result.stderr}"
        )
        assert "BLOCKED" in result.stderr or "No test file" in result.stderr

    def test_should_allow_d_ts_declaration_file(self, tmp_path: Path) -> None:
        """*.d.ts files are declarations, not source; not gated."""
        workspace = _seed_typescript_workspace(tmp_path)
        (workspace / ".etc_sdlc").mkdir(exist_ok=True)
        (workspace / ".etc_sdlc" / "profiles.lock").write_text("typescript\n")

        d_ts = workspace / "src" / "types.d.ts"
        d_ts.write_text("export type T = string;\n")

        payload = {
            "cwd": str(workspace),
            "tool_input": {"file_path": str(d_ts)},
        }
        result = _run_hook("check-test-exists.sh", payload, workspace)
        # exclude_globs: "**/*.d.ts" — profile_loader returns nothing →
        # dispatcher WARN-skips → top-level hook exits 0
        assert result.returncode == 0


class TestWarnAndSkipForUnknownLanguage:
    """A file with no profile match emits WARN + exit 0 per BR-008."""

    def test_should_warn_skip_lua_file(self, tmp_path: Path) -> None:
        workspace = _seed_typescript_workspace(tmp_path)
        (workspace / ".etc_sdlc").mkdir(exist_ok=True)
        (workspace / ".etc_sdlc" / "profiles.lock").write_text("typescript\n")

        # .lua is not claimed by typescript; no other profile loaded
        lua_file = workspace / "src" / "addon.lua"
        lua_file.write_text("-- lua source\n")

        payload = {
            "cwd": str(workspace),
            "tool_input": {"file_path": str(lua_file)},
        }
        result = _run_hook("check-test-exists.sh", payload, workspace)
        # WARN-skip: exit 0, stderr names the gate that didn't apply
        assert result.returncode == 0
        # stderr should contain the WARN line; the exact prefix varies
        # by whether the hook went through dispatch or fallback
        assert "WARN" in result.stderr or "no profile" in result.stderr.lower()
