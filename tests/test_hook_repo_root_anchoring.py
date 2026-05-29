"""Regression tests for #48 — hooks must anchor .etc_sdlc/.sdlc to the repo
root, not the hook-input cwd.

When Claude is launched from a subdirectory (or a subagent inherits a subdir
cwd), the hook input `.cwd` is that subdir, not the repo root. Hooks that wrote
`${CWD}/.etc_sdlc/...` therefore fragmented state (efficiency proposals, daily
reports, turn-events, sandbox-bypass logs, checkpoints) into an orphan
`.etc_sdlc/` under the subdir, invisible to `/efficiency review` and the rest of
the harness which read the repo-root copy.

The fix: each hook resolves PROJECT_ROOT via `git -C "$CWD" rev-parse
--show-toplevel` (fall back to cwd when not a git repo) and writes under
PROJECT_ROOT. These tests prove a hook invoked with cwd=<repo>/subdir writes to
<repo>/.etc_sdlc, not <repo>/subdir/.etc_sdlc.
"""

from __future__ import annotations

import json
import platform
import shutil
import subprocess
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parent.parent / "hooks"


def _find_bash() -> str:
    if platform.system() == "Windows":
        git_bash = Path(r"C:\Program Files\Git\usr\bin\bash.exe")
        if git_bash.is_file():
            return str(git_bash)
    found = shutil.which("bash")
    if found:
        return found
    raise FileNotFoundError("No bash executable found on PATH")


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def _init_repo(tmp_path: Path) -> Path:
    """Init a real git repo with one commit so rev-parse --show-toplevel works."""
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True, capture_output=True)
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "Test")
    (tmp_path / "README.md").write_text("seed\n", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "seed", "--no-verify")
    return tmp_path


def _run_hook_from_subdir(hook_name: str, repo: Path, extra_input: dict) -> None:
    """Run a hook with cwd set to a subdir of the repo."""
    subdir = repo / "deep" / "nested"
    subdir.mkdir(parents=True, exist_ok=True)
    payload = {"cwd": str(subdir), "hook_event_name": "Stop"}
    payload.update(extra_input)
    subprocess.run(
        [_find_bash(), str(HOOKS_DIR / hook_name)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_ceo_hook_writes_efficiency_dir_at_repo_root_not_subdir(tmp_path: Path) -> None:
    """#48: chief-efficiency-officer.sh invoked from a subdir must create
    .etc_sdlc/efficiency at the REPO ROOT, never under the subdir."""
    repo = _init_repo(tmp_path)

    _run_hook_from_subdir("chief-efficiency-officer.sh", repo, {})

    root_eff = repo / ".etc_sdlc" / "efficiency"
    subdir_eff = repo / "deep" / "nested" / ".etc_sdlc"
    assert root_eff.is_dir(), (
        f"efficiency dir not created at repo root: {root_eff}"
    )
    assert not subdir_eff.exists(), (
        f"BUG #48: efficiency state fragmented into the subdir: {subdir_eff}"
    )


def test_sandbox_bypass_tracker_anchors_to_repo_root(tmp_path: Path) -> None:
    """#48: sandbox-bypass-tracker.sh must anchor its log dir to the repo root."""
    repo = _init_repo(tmp_path)

    # A PreToolUse Bash event with the bypass flag is what the tracker logs.
    _run_hook_from_subdir(
        "sandbox-bypass-tracker.sh",
        repo,
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "echo hi", "dangerouslyDisableSandbox": True},
        },
    )

    subdir_etc = repo / "deep" / "nested" / ".etc_sdlc"
    assert not subdir_etc.exists(), (
        f"BUG #48: sandbox-bypass log fragmented into the subdir: {subdir_etc}"
    )


def test_non_git_dir_falls_back_to_cwd(tmp_path: Path) -> None:
    """When cwd is NOT inside a git repo, the resolver falls back to cwd so
    behavior is unchanged (and existing tmp_path-based tests keep passing)."""
    # tmp_path is not a git repo here (no git init).
    payload = {"cwd": str(tmp_path), "hook_event_name": "Stop"}
    subprocess.run(
        [_find_bash(), str(HOOKS_DIR / "chief-efficiency-officer.sh")],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=30,
    )
    # Fallback to cwd: efficiency dir lands directly under tmp_path.
    assert (tmp_path / ".etc_sdlc" / "efficiency").is_dir(), (
        "non-git fallback should create .etc_sdlc/efficiency under cwd"
    )
