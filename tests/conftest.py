"""Shared test fixtures for hook test suite.

Provides reusable fixtures for invoking hook scripts, creating temporary
project structures, task files, transcript files, and invariant files.
"""

from __future__ import annotations

import importlib.util
import json
import os
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "hooks"
SCRIPTS_DIR = REPO_ROOT / "scripts"
SPEC_PATH = REPO_ROOT / "spec" / "etc_sdlc.yaml"
COMPILE_SCRIPT = REPO_ROOT / "compile-sdlc.py"
HOOK_TIMEOUT_SECONDS = 10


@pytest.fixture(scope="session")
def compiled_dist(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Compile ``spec/etc_sdlc.yaml`` ONCE per session into a tmp directory.

    Returns the output ``dist`` Path. Tests that need to read compiled
    artifacts (``settings-hooks.json``, ``skills/.../SKILL.md``,
    ``agents/*.md``, ``sdlc/dod-templates.json``) read them FROM THIS PATH —
    never from ``REPO_ROOT/dist``. This keeps the operator's real, hand-built
    ``dist/`` byte-untouched by a suite run and removes the per-file
    ``rmtree``-the-real-dist fixtures that caused the xdist flake.

    Invocation mirrors ``tests/test_codex_compiler.py::_run_compile``:
    ``sys.executable`` (NEVER bare ``"python3"`` — a bare interpreter may
    lack the ``filelock`` package, silently disabling the compile filelock)
    plus the compiler's ``--output <dir>`` flag.

    Under pytest-xdist this session fixture runs ONCE PER WORKER. That is
    intentional and safe: each worker compiles into its own
    ``tmp_path_factory`` directory, so no shared mutable state remains and
    workers cannot collide on a single dist tree.
    """
    output_dir = tmp_path_factory.mktemp("compiled_dist") / "dist"
    subprocess.run(
        [
            sys.executable,
            str(COMPILE_SCRIPT),
            str(SPEC_PATH),
            "--output",
            str(output_dir),
        ],
        cwd=str(REPO_ROOT),
        check=True,
        text=True,
        capture_output=True,
    )
    return output_dir


def load_script_module(name: str) -> ModuleType:
    """Load ``scripts/<name>.py`` as an importable module by file path.

    The single-file-CLI gate scripts under ``scripts/`` are not a package,
    so tests load them via ``importlib`` from their absolute path. This helper
    replaces the ~30 byte-similar per-file loaders. It registers the module in
    ``sys.modules`` under ``name`` (so dataclasses / enums defined inside
    resolve by qualified name) and asserts the import spec and loader are
    non-None before executing.

    Args:
        name: Module stem under ``scripts/`` (e.g. ``"review_gate"``).

    Returns:
        The executed module object.

    Raises:
        FileNotFoundError: If ``scripts/<name>.py`` does not exist.
    """
    module_path = SCRIPTS_DIR / f"{name}.py"
    if not module_path.is_file():
        msg = f"Script module not found: {module_path}"
        raise FileNotFoundError(msg)
    spec = importlib.util.spec_from_file_location(name, module_path)
    assert spec is not None and spec.loader is not None, (
        f"could not build import spec for {module_path}"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True, scope="session")
def windows_git_bash_path() -> Any:
    """Prepend Git Bash's usr/bin to PATH so hook scripts find cat, grep, jq.

    On Windows, when Python spawns bash and bash spawns Unix utilities, the
    child process inherits the Windows PATH. If Git was installed without
    "Add Unix tools to PATH", commands like cat/grep/awk/jq are missing
    inside hook scripts, causing silent failures (exit 0 instead of the
    expected blocking exit 2). The fixture is a no-op on macOS/Linux.
    """
    if platform.system() != "Windows":
        yield
        return
    git_bin = Path(r"C:\Program Files\Git\usr\bin")
    if not git_bin.is_dir():
        yield
        return
    old_path = os.environ.get("PATH", "")
    os.environ["PATH"] = str(git_bin) + os.pathsep + old_path
    yield
    os.environ["PATH"] = old_path


def _find_bash() -> str:
    """Return path to a working bash executable, preferring Git Bash on Windows.

    On Windows, C:\\Windows\\System32\\bash.exe is the WSL relay (exits 1 when
    WSL is unconfigured) and appears earlier in PATH than Git Bash. The
    helper hard-codes the Git for Windows default install path; if not
    present, falls back to shutil.which("bash"). On macOS/Linux always uses
    shutil.which("bash").
    """
    if platform.system() == "Windows":
        git_bash = Path(r"C:\Program Files\Git\usr\bin\bash.exe")
        if git_bash.is_file():
            return str(git_bash)
    found = shutil.which("bash")
    if found:
        return found
    raise FileNotFoundError("No bash executable found on PATH")


@dataclass(frozen=True, slots=True)
class HookResult:
    """Result of executing a hook script."""

    exit_code: int
    stdout: str
    stderr: str


def _execute_hook(hook_name: str, hook_input: dict[str, Any]) -> HookResult:
    """Locate and execute a hook script, piping JSON input via stdin.

    Args:
        hook_name: Filename of the hook script (e.g. "block-dangerous-commands.sh").
        hook_input: Dictionary to serialize as JSON and pipe to the script's stdin.

    Returns:
        HookResult with exit_code, stdout, and stderr.

    Raises:
        FileNotFoundError: If the hook script does not exist.
        subprocess.TimeoutExpired: If the script exceeds the timeout.
    """
    hook_path = HOOKS_DIR / hook_name
    if not hook_path.is_file():
        msg = f"Hook script not found: {hook_path}"
        raise FileNotFoundError(msg)

    completed = subprocess.run(
        [_find_bash(), str(hook_path)],
        input=json.dumps(hook_input),
        capture_output=True,
        text=True,
        timeout=HOOK_TIMEOUT_SECONDS,
    )
    return HookResult(
        exit_code=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


@pytest.fixture()
def run_hook() -> Any:
    """Fixture that returns a callable to execute hook scripts.

    Usage:
        result = run_hook("block-dangerous-commands.sh", {"tool_input": {"command": "ls"}})
        assert result.exit_code == 0
    """
    return _execute_hook


@pytest.fixture()
def tmp_project(tmp_path: Path) -> Path:
    """Create a temporary project directory with standard subdirectories.

    Creates: src/, tests/, .etc_sdlc/tasks/

    F020-aware: also writes `.etc_sdlc/profiles.lock` with the python
    profile active and stages a `scripts/` + `standards/code/profiles/python/`
    tree by copying from etc's own repo. Hook tests run against the real
    F020 dispatch path that operators see; no behavior is faked.

    The copy is best-effort: if the etc repo's profile files aren't
    locatable (e.g., tests run from an installed harness location with
    no source checkout), the lock is still written but profile gates
    won't resolve — tests should declare F020-independence in that case.
    """
    import shutil as _shutil

    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    etc_sdlc = tmp_path / ".etc_sdlc"
    etc_sdlc.mkdir()
    (etc_sdlc / "tasks").mkdir()
    (etc_sdlc / "profiles.lock").write_text("python\n")

    # Copy F020 dispatch assets from etc's own repo so hook tests exercise
    # the real F020 path. Falls through silently if assets aren't found
    # (tests using tmp_project that don't depend on F020 still work).
    etc_root = Path(__file__).resolve().parent.parent
    profile_loader = etc_root / "scripts" / "profile_loader.py"
    dispatcher = etc_root / "scripts" / "dispatch_profile.sh"
    if profile_loader.is_file() and dispatcher.is_file():
        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir()
        _shutil.copy2(profile_loader, scripts_dir / "profile_loader.py")
        _shutil.copy2(dispatcher, scripts_dir / "dispatch_profile.sh")

    python_profile_src = etc_root / "standards" / "code" / "profiles" / "python"
    if python_profile_src.is_dir():
        python_profile_dst = tmp_path / "standards" / "code" / "profiles" / "python"
        python_profile_dst.mkdir(parents=True)
        for f in python_profile_src.iterdir():
            if f.is_file():
                _shutil.copy2(f, python_profile_dst / f.name)

    # Copy hooks/helpers so the python profile's check-code-quality.sh
    # can resolve check_mutable_globals.py and check_noop_functions.py
    helpers_src = etc_root / "hooks" / "helpers"
    if helpers_src.is_dir():
        helpers_dst = tmp_path / "hooks" / "helpers"
        helpers_dst.mkdir(parents=True)
        for f in helpers_src.iterdir():
            if f.is_file() and f.suffix == ".py":
                _shutil.copy2(f, helpers_dst / f.name)

    return tmp_path


@pytest.fixture()
def task_file(tmp_project: Path) -> Any:
    """Factory fixture to create YAML task files in .etc_sdlc/tasks/.

    Args:
        task_id: Task identifier (e.g. "001").
        title: Human-readable task title.
        status: Task status (default: "in_progress").
        requires_reading: List of file paths the task requires reading.
        files_in_scope: List of file paths in the task's edit scope.

    Returns:
        Path to the created YAML file.
    """

    def _create(
        task_id: str,
        title: str,
        status: str = "in_progress",
        requires_reading: list[str] | None = None,
        files_in_scope: list[str] | None = None,
    ) -> Path:
        task_dir = tmp_project / ".etc_sdlc" / "tasks"
        task_path = task_dir / f"task-{task_id}.yaml"

        lines = [
            f"id: {task_id}",
            f"title: {title}",
            f"status: {status}",
        ]

        if requires_reading:
            lines.append("requires_reading:")
            for item in requires_reading:
                lines.append(f"  - {item}")

        if files_in_scope:
            lines.append("files_in_scope:")
            for item in files_in_scope:
                lines.append(f"  - {item}")

        task_path.write_text("\n".join(lines) + "\n")
        return task_path

    return _create


@pytest.fixture()
def transcript_file(tmp_project: Path) -> Any:
    """Factory fixture to create JSONL transcript files.

    Args:
        entries: List of (tool_name, file_path) tuples representing Read tool calls.

    Returns:
        Path to the created JSONL file.
    """

    def _create(entries: list[tuple[str, str]]) -> Path:
        transcript_path = tmp_project / "transcript.jsonl"
        lines = []
        for tool_name, file_path in entries:
            record = {"tool_name": tool_name, "file_path": file_path}
            lines.append(json.dumps(record))
        transcript_path.write_text("\n".join(lines) + "\n")
        return transcript_path

    return _create


@pytest.fixture()
def invariants_file(tmp_project: Path) -> Any:
    """Factory fixture to create INVARIANTS.md files.

    Args:
        entries: List of dicts with keys "id", "description", "verify".

    Returns:
        Path to the created INVARIANTS.md file.
    """

    def _create(entries: list[dict[str, str]]) -> Path:
        invariants_path = tmp_project / "INVARIANTS.md"
        sections = ["# Project Invariants\n"]

        for entry in entries:
            section = (
                f"## {entry['id']}: {entry['description']}\n"
                f"\n"
                f"- **Verify:** `{entry['verify']}`\n"
            )
            sections.append(section)

        invariants_path.write_text("\n".join(sections) + "\n")
        return invariants_path

    return _create
