"""Tests for scripts/detect_profiles.py — F020 profile detection."""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path
from types import ModuleType

SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "detect_profiles.py"


def _load_detect_profiles() -> ModuleType:
    """Load scripts/detect_profiles.py without making scripts/ a package."""
    spec = importlib.util.spec_from_file_location("detect_profiles", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _make_profile(
    repo: Path,
    name: str,
    markers: list[str],
    file_globs: list[str] | None = None,
    exclude_globs: list[str] | None = None,
) -> None:
    """Create a minimal profile directory with detection.yaml."""
    profile_dir = repo / "standards" / "code" / "profiles" / name
    profile_dir.mkdir(parents=True, exist_ok=True)
    file_globs = file_globs or [f"**/*.{name[:2]}"]
    exclude_globs = exclude_globs or []
    body = f"profile: {name}\n"
    body += "markers:\n"
    for m in markers:
        # Quote markers to avoid YAML interpreting glob chars (e.g., '*.tf'
        # would be parsed as an alias reference without quoting)
        body += f"  - \"{m}\"\n"
    body += "file_globs:\n"
    for g in file_globs:
        body += f"  - \"{g}\"\n"
    body += "exclude_globs:\n"
    for g in exclude_globs:
        body += f"  - \"{g}\"\n"
    body += "canonical_sources:\n  - https://example.com\n"
    (profile_dir / "detection.yaml").write_text(body)


class TestDetect:
    """Library API: detect_profiles.detect(repo_root) -> list[str]"""

    def test_should_return_empty_when_no_profiles_dir(self, tmp_path: Path) -> None:
        detect_profiles = _load_detect_profiles()
        result = detect_profiles.detect(tmp_path)
        assert result == []

    def test_should_return_empty_when_no_markers_present(self, tmp_path: Path) -> None:
        _make_profile(tmp_path, "python", markers=["pyproject.toml"])
        detect_profiles = _load_detect_profiles()
        result = detect_profiles.detect(tmp_path)
        assert result == []

    def test_should_detect_python_when_marker_present(self, tmp_path: Path) -> None:
        _make_profile(tmp_path, "python", markers=["pyproject.toml"])
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'demo'\n")
        detect_profiles = _load_detect_profiles()
        result = detect_profiles.detect(tmp_path)
        assert result == ["python"]

    def test_should_activate_all_profiles_in_monorepo(self, tmp_path: Path) -> None:
        """F020 BR-004: monorepo activates every detected profile."""
        _make_profile(tmp_path, "python", markers=["pyproject.toml"])
        _make_profile(tmp_path, "typescript", markers=["package.json"])
        _make_profile(tmp_path, "go", markers=["go.mod"])
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'demo'\n")
        (tmp_path / "package.json").write_text("{}")
        (tmp_path / "go.mod").write_text("module demo\n")
        detect_profiles = _load_detect_profiles()
        result = detect_profiles.detect(tmp_path)
        assert result == ["go", "python", "typescript"]  # sorted alphabetically

    def test_should_be_deterministic_across_runs(self, tmp_path: Path) -> None:
        """F020 BR-003: same repo state, same output, same order."""
        _make_profile(tmp_path, "python", markers=["pyproject.toml"])
        _make_profile(tmp_path, "typescript", markers=["package.json"])
        (tmp_path / "pyproject.toml").write_text("")
        (tmp_path / "package.json").write_text("{}")
        detect_profiles = _load_detect_profiles()
        first = detect_profiles.detect(tmp_path)
        second = detect_profiles.detect(tmp_path)
        third = detect_profiles.detect(tmp_path)
        assert first == second == third

    def test_should_honor_pin_override(self, tmp_path: Path) -> None:
        """F020 BR-005: profiles.yaml pin: overrides auto-detect."""
        _make_profile(tmp_path, "python", markers=["pyproject.toml"])
        _make_profile(tmp_path, "typescript", markers=["package.json"])
        (tmp_path / "pyproject.toml").write_text("")
        (tmp_path / "package.json").write_text("{}")
        (tmp_path / ".etc_sdlc").mkdir()
        (tmp_path / ".etc_sdlc" / "profiles.yaml").write_text("pin: [typescript]\n")
        detect_profiles = _load_detect_profiles()
        result = detect_profiles.detect(tmp_path)
        assert result == ["typescript"]  # pin wins, python suppressed

    def test_should_honor_add_override(self, tmp_path: Path) -> None:
        """F020 BR-005: profiles.yaml add: extends auto-detect."""
        _make_profile(tmp_path, "python", markers=["pyproject.toml"])
        _make_profile(tmp_path, "terraform", markers=["*.tf"])
        (tmp_path / "pyproject.toml").write_text("")
        # No .tf files; terraform would NOT auto-detect
        (tmp_path / ".etc_sdlc").mkdir()
        (tmp_path / ".etc_sdlc" / "profiles.yaml").write_text("add: [terraform]\n")
        detect_profiles = _load_detect_profiles()
        result = detect_profiles.detect(tmp_path)
        assert result == ["python", "terraform"]

    def test_should_reject_invalid_profile_name_in_override(self, tmp_path: Path) -> None:
        """F020 Security: profile names in override are whitelisted."""
        _make_profile(tmp_path, "python", markers=["pyproject.toml"])
        (tmp_path / "pyproject.toml").write_text("")
        (tmp_path / ".etc_sdlc").mkdir()
        # Malicious shell-injection attempt — must be rejected
        (tmp_path / ".etc_sdlc" / "profiles.yaml").write_text(
            'add: ["python; rm -rf /", "python"]\n'
        )
        detect_profiles = _load_detect_profiles()
        result = detect_profiles.detect(tmp_path)
        # Only the valid 'python' is preserved; the injection attempt is filtered
        assert result == ["python"]

    def test_should_skip_malformed_detection_yaml(self, tmp_path: Path) -> None:
        """F020 EC-002: malformed marker file does not crash; profile is skipped."""
        profile_dir = tmp_path / "standards" / "code" / "profiles" / "python"
        profile_dir.mkdir(parents=True)
        # Profile declares wrong name (directory mismatch)
        (profile_dir / "detection.yaml").write_text("profile: not_python\nmarkers: [pyproject.toml]\n")
        (tmp_path / "pyproject.toml").write_text("")
        detect_profiles = _load_detect_profiles()
        result = detect_profiles.detect(tmp_path)
        # Detection rejects the mismatched profile; no profile activates
        assert result == []


class TestCli:
    """CLI: scripts/detect_profiles.py"""

    def test_should_print_one_profile_per_line(self, tmp_path: Path) -> None:
        _make_profile(tmp_path, "python", markers=["pyproject.toml"])
        _make_profile(tmp_path, "typescript", markers=["package.json"])
        (tmp_path / "pyproject.toml").write_text("")
        (tmp_path / "package.json").write_text("{}")
        result = subprocess.run(
            ["python3", str(SCRIPT_PATH), "--repo-root", str(tmp_path)],
            capture_output=True, text=True, check=True,
        )
        lines = [l for l in result.stdout.splitlines() if l.strip()]
        assert lines == ["python", "typescript"]

    def test_should_emit_json_with_flag(self, tmp_path: Path) -> None:
        _make_profile(tmp_path, "python", markers=["pyproject.toml"])
        (tmp_path / "pyproject.toml").write_text("")
        result = subprocess.run(
            ["python3", str(SCRIPT_PATH), "--repo-root", str(tmp_path), "--json"],
            capture_output=True, text=True, check=True,
        )
        import json
        assert json.loads(result.stdout) == ["python"]

    def test_should_write_lock_with_flag(self, tmp_path: Path) -> None:
        _make_profile(tmp_path, "python", markers=["pyproject.toml"])
        (tmp_path / "pyproject.toml").write_text("")
        subprocess.run(
            ["python3", str(SCRIPT_PATH), "--repo-root", str(tmp_path), "--write-lock"],
            capture_output=True, text=True, check=True,
        )
        lock = tmp_path / ".etc_sdlc" / "profiles.lock"
        assert lock.read_text() == "python\n"

    def test_check_stale_exits_zero_when_fresh(self, tmp_path: Path) -> None:
        _make_profile(tmp_path, "python", markers=["pyproject.toml"])
        (tmp_path / "pyproject.toml").write_text("")
        subprocess.run(
            ["python3", str(SCRIPT_PATH), "--repo-root", str(tmp_path), "--write-lock"],
            check=True, capture_output=True,
        )
        # profiles.lock is fresh — exit 0
        result = subprocess.run(
            ["python3", str(SCRIPT_PATH), "--repo-root", str(tmp_path), "--check-stale"],
            capture_output=True,
        )
        assert result.returncode == 0

    def test_check_stale_exits_one_when_lock_missing(self, tmp_path: Path) -> None:
        _make_profile(tmp_path, "python", markers=["pyproject.toml"])
        (tmp_path / "pyproject.toml").write_text("")
        # No lock written
        result = subprocess.run(
            ["python3", str(SCRIPT_PATH), "--repo-root", str(tmp_path), "--check-stale"],
            capture_output=True,
        )
        assert result.returncode == 1
