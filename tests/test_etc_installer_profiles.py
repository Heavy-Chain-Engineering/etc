"""Tests for etc_installer.profiles — F020 profile detection invocation.

Mirrors install.sh:472-492 (the F020 profile-detection block): shells
out to `scripts/detect_profiles.py --repo-root <repo> --write-lock`
via subprocess.run with argv-list form. Returns a structured result
indicating ok / warn so the caller (install_steps in task 005) can emit
the matching ✓/⚠ status line.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest import mock

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from etc_installer import profiles  # noqa: E402


class TestDetectAndWriteLock:
    """detect_and_write_lock(...) -> ProfileDetectionResult."""

    def test_should_shell_out_to_detect_profiles_script_with_argv_list(
        self, tmp_path: Path
    ) -> None:
        # Arrange
        detect_script = tmp_path / "scripts" / "detect_profiles.py"
        detect_script.parent.mkdir(parents=True)
        detect_script.write_text("# stub\n")
        lock_dir = tmp_path / ".etc_sdlc"
        lock_dir.mkdir()
        (lock_dir / "profiles.lock").write_text("python\n")

        completed = subprocess.CompletedProcess(
            args=[sys.executable, str(detect_script), "--repo-root", str(tmp_path), "--write-lock"],
            returncode=0,
            stdout="",
            stderr="",
        )

        # Act
        with mock.patch.object(profiles.subprocess, "run", return_value=completed) as run_mock:
            result = profiles.detect_and_write_lock(
                detect_script=detect_script,
                repo_root=tmp_path,
            )

        # Assert — argv list form (never shell=True)
        run_mock.assert_called_once()
        called_args, called_kwargs = run_mock.call_args
        assert called_args[0] == [
            sys.executable,
            str(detect_script),
            "--repo-root",
            str(tmp_path),
            "--write-lock",
        ]
        assert called_kwargs.get("shell", False) is False
        assert result.ok is True
        assert result.detected == ["python"]

    def test_should_return_warn_when_detect_script_exits_nonzero(
        self, tmp_path: Path
    ) -> None:
        # Arrange
        detect_script = tmp_path / "scripts" / "detect_profiles.py"
        detect_script.parent.mkdir(parents=True)
        detect_script.write_text("# stub\n")

        completed = subprocess.CompletedProcess(
            args=[],
            returncode=2,
            stdout="",
            stderr="detect_profiles: detection failed: boom\n",
        )

        # Act
        with mock.patch.object(profiles.subprocess, "run", return_value=completed):
            result = profiles.detect_and_write_lock(
                detect_script=detect_script,
                repo_root=tmp_path,
            )

        # Assert
        assert result.ok is False
        assert result.detected == []
        assert "detection failed" in result.message

    def test_should_return_ok_with_empty_detected_when_lock_is_empty(
        self, tmp_path: Path
    ) -> None:
        # Arrange — script succeeds, lock file exists but empty
        detect_script = tmp_path / "scripts" / "detect_profiles.py"
        detect_script.parent.mkdir(parents=True)
        detect_script.write_text("# stub\n")
        lock_dir = tmp_path / ".etc_sdlc"
        lock_dir.mkdir()
        (lock_dir / "profiles.lock").write_text("")

        completed = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr=""
        )

        # Act
        with mock.patch.object(profiles.subprocess, "run", return_value=completed):
            result = profiles.detect_and_write_lock(
                detect_script=detect_script,
                repo_root=tmp_path,
            )

        # Assert
        assert result.ok is True
        assert result.detected == []

    def test_should_split_multi_line_lock_into_profile_list(
        self, tmp_path: Path
    ) -> None:
        # Arrange — multiple profiles, one per line per F020-005
        detect_script = tmp_path / "scripts" / "detect_profiles.py"
        detect_script.parent.mkdir(parents=True)
        detect_script.write_text("# stub\n")
        lock_dir = tmp_path / ".etc_sdlc"
        lock_dir.mkdir()
        (lock_dir / "profiles.lock").write_text("python\ntypescript\ngo\n")

        completed = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr=""
        )

        # Act
        with mock.patch.object(profiles.subprocess, "run", return_value=completed):
            result = profiles.detect_and_write_lock(
                detect_script=detect_script,
                repo_root=tmp_path,
            )

        # Assert
        assert result.ok is True
        assert result.detected == ["python", "typescript", "go"]

    def test_should_create_lock_dir_when_missing(self, tmp_path: Path) -> None:
        # Arrange — no .etc_sdlc/ in repo root yet
        detect_script = tmp_path / "scripts" / "detect_profiles.py"
        detect_script.parent.mkdir(parents=True)
        detect_script.write_text("# stub\n")

        completed = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr=""
        )

        # Act
        with mock.patch.object(profiles.subprocess, "run", return_value=completed):
            profiles.detect_and_write_lock(
                detect_script=detect_script,
                repo_root=tmp_path,
            )

        # Assert — caller-side mkdir before invoking the script (mirrors install.sh:481)
        assert (tmp_path / ".etc_sdlc").is_dir()
