"""rust profile — end-to-end integration tests.

Fourth-language proof case for F020. Exercises the full dispatch path
against `tests/fixtures/rust-repo/`.

Coverage:
  1. detect_profiles.py detects rust when Cargo.toml is present.
  2. profile_loader.py routes .rs files (top-level + nested) to rust.
  3. exclude_globs filter target/.
  4. check-test-exists allows when #[cfg(test)] is present in-file.
  5. check-test-exists blocks when no test block and no integration test.
  6. check-code-quality blocks empty function bodies (CQ-RS-001).
  7. check-code-quality blocks .unwrap() in production code (CQ-RS-002).
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

ETC_ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ETC_ROOT / "tests" / "fixtures" / "rust-repo"
HOOKS_DIR = ETC_ROOT / "hooks"
SCRIPTS_DIR = ETC_ROOT / "scripts"


def _seed_rust_workspace(tmp_path: Path) -> Path:
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

    profile_src = ETC_ROOT / "standards" / "code" / "profiles" / "rust"
    profile_dst = tmp_path / "standards" / "code" / "profiles" / "rust"
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


class TestRustProfileDetection:
    def test_should_detect_rust_from_cargo_toml(self, tmp_path: Path) -> None:
        workspace = _seed_rust_workspace(tmp_path)
        result = subprocess.run(
            ["python3", str(SCRIPTS_DIR / "detect_profiles.py"),
             "--repo-root", str(workspace)],
            capture_output=True, text=True, check=True,
        )
        assert "rust" in result.stdout


class TestRustProfileRouting:
    def test_should_route_rs_files(self, tmp_path: Path) -> None:
        workspace = _seed_rust_workspace(tmp_path)
        (workspace / ".etc_sdlc").mkdir(exist_ok=True)
        (workspace / ".etc_sdlc" / "profiles.lock").write_text("rust\n")

        result = subprocess.run(
            ["python3", str(SCRIPTS_DIR / "profile_loader.py"),
             "profile-for", "src/lib.rs",
             "--lock-path", str(workspace / ".etc_sdlc" / "profiles.lock")],
            capture_output=True, text=True, check=True,
            cwd=str(workspace),
        )
        assert result.stdout.strip() == "rust"

    def test_should_exclude_target(self, tmp_path: Path) -> None:
        workspace = _seed_rust_workspace(tmp_path)
        (workspace / ".etc_sdlc").mkdir(exist_ok=True)
        (workspace / ".etc_sdlc" / "profiles.lock").write_text("rust\n")

        result = subprocess.run(
            ["python3", str(SCRIPTS_DIR / "profile_loader.py"),
             "profile-for", "target/debug/build/whatever.rs",
             "--lock-path", str(workspace / ".etc_sdlc" / "profiles.lock")],
            capture_output=True, text=True, check=False,
            cwd=str(workspace),
        )
        assert result.stdout.strip() == ""


class TestRustTddGate:
    def test_should_allow_when_cfg_test_block_present(self, tmp_path: Path) -> None:
        workspace = _seed_rust_workspace(tmp_path)
        (workspace / ".etc_sdlc").mkdir(exist_ok=True)
        (workspace / ".etc_sdlc" / "profiles.lock").write_text("rust\n")

        # Create a module file with a #[cfg(test)] block
        target = workspace / "src" / "math.rs"
        target.write_text(
            "pub fn add(a: i32, b: i32) -> i32 { a + b }\n"
            "\n"
            "#[cfg(test)]\n"
            "mod tests {\n"
            "    use super::*;\n"
            "    #[test]\n"
            "    fn add_works() { assert_eq!(add(1, 2), 3); }\n"
            "}\n"
        )

        result = _run_hook(
            "check-test-exists.sh",
            {"tool_input": {"file_path": str(target)},
             "cwd": str(workspace)},
            workspace,
        )
        assert result.returncode == 0, f"Expected allow (0); stderr={result.stderr}"

    def test_should_block_when_no_test_coverage(self, tmp_path: Path) -> None:
        workspace = _seed_rust_workspace(tmp_path)
        (workspace / ".etc_sdlc").mkdir(exist_ok=True)
        (workspace / ".etc_sdlc" / "profiles.lock").write_text("rust\n")

        # New module file with no #[cfg(test)] and no tests/orphan.rs
        target = workspace / "src" / "orphan.rs"
        target.write_text("pub fn do_thing() -> i32 { 42 }\n")

        result = _run_hook(
            "check-test-exists.sh",
            {"tool_input": {"file_path": str(target)},
             "cwd": str(workspace)},
            workspace,
        )
        assert result.returncode == 2, f"Expected block (2); got {result.returncode}; stderr={result.stderr}"


class TestRustCodeQualityGate:
    def test_should_block_empty_function_body(self, tmp_path: Path) -> None:
        workspace = _seed_rust_workspace(tmp_path)
        (workspace / ".etc_sdlc").mkdir(exist_ok=True)
        (workspace / ".etc_sdlc" / "profiles.lock").write_text("rust\n")

        bad = workspace / "src" / "noop.rs"
        bad.write_text("pub fn do_nothing() {}\n")

        result = _run_hook(
            "check-code-quality.sh",
            {"tool_input": {"file_path": str(bad)},
             "cwd": str(workspace)},
            workspace,
        )
        assert result.returncode == 2, f"Expected block (2); got {result.returncode}; stderr={result.stderr}"
        assert "CQ-RS-001" in result.stderr or "Empty" in result.stderr

    def test_should_block_unwrap_in_production_code(self, tmp_path: Path) -> None:
        workspace = _seed_rust_workspace(tmp_path)
        (workspace / ".etc_sdlc").mkdir(exist_ok=True)
        (workspace / ".etc_sdlc" / "profiles.lock").write_text("rust\n")

        bad = workspace / "src" / "danger.rs"
        bad.write_text(
            "pub fn risky(s: &str) -> i32 {\n"
            "    s.parse::<i32>().unwrap()\n"
            "}\n"
        )

        result = _run_hook(
            "check-code-quality.sh",
            {"tool_input": {"file_path": str(bad)},
             "cwd": str(workspace)},
            workspace,
        )
        assert result.returncode == 2, f"Expected block (2); got {result.returncode}; stderr={result.stderr}"
        assert "CQ-RS-002" in result.stderr or "unwrap" in result.stderr.lower()

    def test_should_allow_clean_rust_file(self, tmp_path: Path) -> None:
        workspace = _seed_rust_workspace(tmp_path)
        (workspace / ".etc_sdlc").mkdir(exist_ok=True)
        (workspace / ".etc_sdlc" / "profiles.lock").write_text("rust\n")

        result = _run_hook(
            "check-code-quality.sh",
            {"tool_input": {"file_path": str(workspace / "src" / "lib.rs")},
             "cwd": str(workspace)},
            workspace,
        )
        assert result.returncode == 0, f"Expected allow (0); stderr={result.stderr}"
