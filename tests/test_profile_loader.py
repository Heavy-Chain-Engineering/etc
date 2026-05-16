"""Tests for scripts/profile_loader.py — F020 file-to-profile resolution."""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path
from types import ModuleType

SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "profile_loader.py"


def _load_profile_loader() -> ModuleType:
    spec = importlib.util.spec_from_file_location("profile_loader", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _make_profile_in_repo(
    repo: Path,
    name: str,
    file_globs: list[str],
    exclude_globs: list[str] | None = None,
) -> None:
    profile_dir = repo / "standards" / "code" / "profiles" / name
    profile_dir.mkdir(parents=True, exist_ok=True)
    exclude_globs = exclude_globs or []
    body = f"profile: {name}\n"
    body += "markers: [pyproject.toml]\n"
    body += "file_globs:\n"
    for g in file_globs:
        body += f"  - \"{g}\"\n"
    body += "exclude_globs:\n"
    for g in exclude_globs:
        body += f"  - \"{g}\"\n"
    body += "canonical_sources: [https://example.com]\n"
    (profile_dir / "detection.yaml").write_text(body)


def _write_lock(repo: Path, profiles: list[str]) -> Path:
    lock_dir = repo / ".etc_sdlc"
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock = lock_dir / "profiles.lock"
    lock.write_text("".join(p + "\n" for p in profiles))
    return lock


class TestProfileFor:
    """Library API: profile_for(file_path, lock_path) -> str | None"""

    def test_should_return_none_when_no_active_profiles(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        loader = _load_profile_loader()
        result = loader.profile_for("src/foo.py")
        assert result is None

    def test_should_match_python_for_py_file(self, tmp_path: Path, monkeypatch) -> None:
        _make_profile_in_repo(tmp_path, "python", file_globs=["**/*.py"])
        lock = _write_lock(tmp_path, ["python"])
        monkeypatch.chdir(tmp_path)
        loader = _load_profile_loader()
        result = loader.profile_for("src/foo.py", lock)
        assert result == "python"

    def test_should_return_none_when_no_profile_claims_file(self, tmp_path: Path, monkeypatch) -> None:
        _make_profile_in_repo(tmp_path, "python", file_globs=["**/*.py"])
        lock = _write_lock(tmp_path, ["python"])
        monkeypatch.chdir(tmp_path)
        loader = _load_profile_loader()
        result = loader.profile_for("src/foo.lua", lock)
        assert result is None

    def test_should_route_by_extension_in_monorepo(self, tmp_path: Path, monkeypatch) -> None:
        """F020 BR-004: file-scope routing in monorepos."""
        _make_profile_in_repo(tmp_path, "python", file_globs=["**/*.py"])
        _make_profile_in_repo(tmp_path, "typescript", file_globs=["**/*.ts", "**/*.tsx"])
        lock = _write_lock(tmp_path, ["python", "typescript"])
        monkeypatch.chdir(tmp_path)
        loader = _load_profile_loader()
        assert loader.profile_for("backend/app.py", lock) == "python"
        assert loader.profile_for("frontend/component.tsx", lock) == "typescript"
        assert loader.profile_for("frontend/util.ts", lock) == "typescript"

    def test_should_honor_exclude_globs(self, tmp_path: Path, monkeypatch) -> None:
        _make_profile_in_repo(
            tmp_path,
            "python",
            file_globs=["**/*.py"],
            exclude_globs=["**/legacy/**"],
        )
        lock = _write_lock(tmp_path, ["python"])
        monkeypatch.chdir(tmp_path)
        loader = _load_profile_loader()
        assert loader.profile_for("src/foo.py", lock) == "python"
        assert loader.profile_for("src/legacy/old.py", lock) is None

    def test_more_specific_glob_wins(self, tmp_path: Path, monkeypatch) -> None:
        """F020 EC-005: more-specific path wins on overlapping globs."""
        _make_profile_in_repo(tmp_path, "python", file_globs=["**/*.py"])
        _make_profile_in_repo(tmp_path, "myscripts", file_globs=["scripts/special/*.py"])
        lock = _write_lock(tmp_path, ["myscripts", "python"])
        monkeypatch.chdir(tmp_path)
        loader = _load_profile_loader()
        # The more-specific scripts/special/ glob beats **/*.py
        assert loader.profile_for("scripts/special/x.py", lock) == "myscripts"
        # Generic .py file goes to python
        assert loader.profile_for("src/foo.py", lock) == "python"


class TestActiveProfiles:
    def test_should_return_empty_when_no_lock(self, tmp_path: Path) -> None:
        loader = _load_profile_loader()
        result = loader.active_profiles(tmp_path / "missing.lock")
        assert result == []

    def test_should_read_lock_lines(self, tmp_path: Path) -> None:
        lock = _write_lock(tmp_path, ["python", "typescript"])
        loader = _load_profile_loader()
        result = loader.active_profiles(lock)
        assert result == ["python", "typescript"]


class TestCli:
    def test_profile_for_prints_name_or_empty(self, tmp_path: Path, monkeypatch) -> None:
        _make_profile_in_repo(tmp_path, "python", file_globs=["**/*.py"])
        lock = _write_lock(tmp_path, ["python"])
        monkeypatch.chdir(tmp_path)

        result = subprocess.run(
            ["python3", str(SCRIPT_PATH), "profile-for", "src/foo.py",
             "--lock-path", str(lock)],
            capture_output=True, text=True, check=True,
        )
        assert result.stdout.strip() == "python"

        # No-match → empty stdout, exit 0
        result = subprocess.run(
            ["python3", str(SCRIPT_PATH), "profile-for", "src/foo.lua",
             "--lock-path", str(lock)],
            capture_output=True, text=True, check=True,
        )
        assert result.stdout.strip() == ""

    def test_active_prints_lock_lines(self, tmp_path: Path) -> None:
        lock = _write_lock(tmp_path, ["python", "typescript"])
        result = subprocess.run(
            ["python3", str(SCRIPT_PATH), "active", "--lock-path", str(lock)],
            capture_output=True, text=True, check=True,
        )
        assert result.stdout.strip().splitlines() == ["python", "typescript"]
