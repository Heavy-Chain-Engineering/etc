"""go profile — end-to-end integration tests.

These tests exercise the full F020 dispatch path against the fixture at
`tests/fixtures/go-repo/`. They are the third-language proof case that
the profile architecture works beyond Python and TypeScript.

Coverage:
  1. detect_profiles.py detects go when go.mod is present.
  2. profile_loader.py routes .go files to go.
  3. hooks/check-test-exists.sh BLOCKS when a go source file under
     cmd/ has no sibling _test.go.
  4. hooks/check-test-exists.sh ALLOWS when a sibling _test.go exists.
  5. hooks/check-code-quality.sh BLOCKS an empty function body.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

ETC_ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ETC_ROOT / "tests" / "fixtures" / "go-repo"
HOOKS_DIR = ETC_ROOT / "hooks"
SCRIPTS_DIR = ETC_ROOT / "scripts"


def _seed_go_workspace(tmp_path: Path) -> Path:
    """Copy the go fixture + F020 dispatch assets into tmp_path."""
    for f in FIXTURE.rglob("*"):
        if f.is_file():
            dest = tmp_path / f.relative_to(FIXTURE)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, dest)

    scripts_dst = tmp_path / "scripts"
    scripts_dst.mkdir(exist_ok=True)
    shutil.copy2(SCRIPTS_DIR / "profile_loader.py", scripts_dst / "profile_loader.py")
    shutil.copy2(SCRIPTS_DIR / "dispatch_profile.sh", scripts_dst / "dispatch_profile.sh")
    shutil.copy2(SCRIPTS_DIR / "detect_profiles.py", scripts_dst / "detect_profiles.py")

    profile_src = ETC_ROOT / "standards" / "code" / "profiles" / "go"
    profile_dst = tmp_path / "standards" / "code" / "profiles" / "go"
    profile_dst.mkdir(parents=True, exist_ok=True)
    for f in profile_src.iterdir():
        if f.is_file():
            shutil.copy2(f, profile_dst / f.name)

    return tmp_path


def _run_hook(hook_name: str, payload: dict, cwd: Path) -> subprocess.CompletedProcess[str]:
    hook = HOOKS_DIR / hook_name
    return subprocess.run(
        ["bash", str(hook)],
        input=json.dumps(payload),
        capture_output=True, text=True, timeout=30,
        cwd=str(cwd),
    )


class TestGoProfileDetection:
    def test_should_detect_go_from_go_mod(self, tmp_path: Path) -> None:
        workspace = _seed_go_workspace(tmp_path)
        result = subprocess.run(
            ["python3", str(SCRIPTS_DIR / "detect_profiles.py"),
             "--repo-root", str(workspace)],
            capture_output=True, text=True, check=True,
        )
        assert "go" in result.stdout

    def test_should_write_go_to_profiles_lock(self, tmp_path: Path) -> None:
        workspace = _seed_go_workspace(tmp_path)
        subprocess.run(
            ["python3", str(SCRIPTS_DIR / "detect_profiles.py"),
             "--repo-root", str(workspace), "--write-lock"],
            capture_output=True, text=True, check=True,
        )
        lock = workspace / ".etc_sdlc" / "profiles.lock"
        assert lock.is_file()
        assert "go" in lock.read_text().strip().splitlines()


class TestGoProfileRouting:
    def test_should_route_go_files_to_go_profile(self, tmp_path: Path) -> None:
        workspace = _seed_go_workspace(tmp_path)
        (workspace / ".etc_sdlc").mkdir(exist_ok=True)
        (workspace / ".etc_sdlc" / "profiles.lock").write_text("go\n")

        result = subprocess.run(
            ["python3", str(SCRIPTS_DIR / "profile_loader.py"),
             "profile-for", "cmd/greet/greet.go",
             "--lock-path", str(workspace / ".etc_sdlc" / "profiles.lock")],
            capture_output=True, text=True, check=True,
            cwd=str(workspace),
        )
        assert result.stdout.strip() == "go"

    def test_should_route_main_go_at_top_level(self, tmp_path: Path) -> None:
        workspace = _seed_go_workspace(tmp_path)
        (workspace / ".etc_sdlc").mkdir(exist_ok=True)
        (workspace / ".etc_sdlc" / "profiles.lock").write_text("go\n")

        result = subprocess.run(
            ["python3", str(SCRIPTS_DIR / "profile_loader.py"),
             "profile-for", "main.go",
             "--lock-path", str(workspace / ".etc_sdlc" / "profiles.lock")],
            capture_output=True, text=True, check=True,
            cwd=str(workspace),
        )
        assert result.stdout.strip() == "go"

    def test_should_exclude_vendor_directory(self, tmp_path: Path) -> None:
        workspace = _seed_go_workspace(tmp_path)
        (workspace / ".etc_sdlc").mkdir(exist_ok=True)
        (workspace / ".etc_sdlc" / "profiles.lock").write_text("go\n")

        result = subprocess.run(
            ["python3", str(SCRIPTS_DIR / "profile_loader.py"),
             "profile-for", "vendor/github.com/foo/bar.go",
             "--lock-path", str(workspace / ".etc_sdlc" / "profiles.lock")],
            capture_output=True, text=True, check=False,
            cwd=str(workspace),
        )
        assert result.stdout.strip() == ""


class TestGoTddGate:
    def test_should_allow_when_sibling_test_exists(self, tmp_path: Path) -> None:
        workspace = _seed_go_workspace(tmp_path)
        (workspace / ".etc_sdlc").mkdir(exist_ok=True)
        (workspace / ".etc_sdlc" / "profiles.lock").write_text("go\n")

        result = _run_hook(
            "check-test-exists.sh",
            {"tool_input": {"file_path": str(workspace / "cmd" / "greet" / "greet.go")},
             "cwd": str(workspace)},
            workspace,
        )
        assert result.returncode == 0, f"Expected allow (0); stderr={result.stderr}"

    def test_should_block_when_no_sibling_test(self, tmp_path: Path) -> None:
        workspace = _seed_go_workspace(tmp_path)
        (workspace / ".etc_sdlc").mkdir(exist_ok=True)
        (workspace / ".etc_sdlc" / "profiles.lock").write_text("go\n")

        # Create a new source file without a corresponding _test.go
        orphan = workspace / "cmd" / "orphan" / "orphan.go"
        orphan.parent.mkdir(parents=True, exist_ok=True)
        orphan.write_text("package orphan\n\nfunc Run() {}\n")

        result = _run_hook(
            "check-test-exists.sh",
            {"tool_input": {"file_path": str(orphan)},
             "cwd": str(workspace)},
            workspace,
        )
        assert result.returncode == 2, f"Expected block (2); got {result.returncode}; stderr={result.stderr}"


class TestGoCodeQualityGate:
    def test_should_block_empty_function_body(self, tmp_path: Path) -> None:
        workspace = _seed_go_workspace(tmp_path)
        (workspace / ".etc_sdlc").mkdir(exist_ok=True)
        (workspace / ".etc_sdlc" / "profiles.lock").write_text("go\n")

        bad = workspace / "cmd" / "greet" / "noop.go"
        bad.write_text("package greet\n\nfunc DoNothing() {}\n")

        result = _run_hook(
            "check-code-quality.sh",
            {"tool_input": {"file_path": str(bad)},
             "cwd": str(workspace)},
            workspace,
        )
        assert result.returncode == 2, f"Expected block (2); got {result.returncode}; stderr={result.stderr}"
        assert "Empty function" in result.stderr or "CQ-GO-001" in result.stderr

    def test_should_allow_clean_go_file(self, tmp_path: Path) -> None:
        workspace = _seed_go_workspace(tmp_path)
        (workspace / ".etc_sdlc").mkdir(exist_ok=True)
        (workspace / ".etc_sdlc" / "profiles.lock").write_text("go\n")

        result = _run_hook(
            "check-code-quality.sh",
            {"tool_input": {"file_path": str(workspace / "cmd" / "greet" / "greet.go")},
             "cwd": str(workspace)},
            workspace,
        )
        assert result.returncode == 0, f"Expected allow (0); stderr={result.stderr}"
