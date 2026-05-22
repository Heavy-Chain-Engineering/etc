"""Tests for etc_installer.paths — POSIX-to-native path conversion + helpers.

Covers AC-010 paths-portion: detect MINGW/MSYS/CYGWIN via
platform.uname().system and shell out to `cygpath -w` via subprocess.run
with argv-list form (never shell string). On macOS/Linux returns
str(path).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

# etc_installer lives at repo root (not yet declared as a packaged
# distribution — that's BR-003 in task 001's scope). Prepend repo root
# to sys.path so `from etc_installer import paths` resolves under
# pytest. Raw `python3 -c "import etc_installer"` from the repo root
# (AC-003) does not need this — cwd is auto-prepended there.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from etc_installer import paths  # noqa: E402  (sys.path setup must precede import)


class TestToNativePath:
    """to_native_path(path: Path) -> str."""

    def test_should_return_str_of_path_when_system_is_darwin(self) -> None:
        # Arrange
        sample = Path("/Users/operator/.claude")
        fake_uname = mock.MagicMock()
        fake_uname.system = "Darwin"

        # Act
        with mock.patch.object(paths.platform, "uname", return_value=fake_uname):
            result = paths.to_native_path(sample)

        # Assert
        assert result == str(sample)

    def test_should_return_str_of_path_when_system_is_linux(self) -> None:
        # Arrange
        sample = Path("/home/operator/.claude")
        fake_uname = mock.MagicMock()
        fake_uname.system = "Linux"

        # Act
        with mock.patch.object(paths.platform, "uname", return_value=fake_uname):
            result = paths.to_native_path(sample)

        # Assert
        assert result == str(sample)

    def test_should_shell_out_to_cygpath_when_system_is_mingw(self) -> None:
        # Arrange
        sample = Path("/c/Users/operator/.claude")
        fake_uname = mock.MagicMock()
        fake_uname.system = "MINGW64_NT-10.0-19045"
        completed = subprocess.CompletedProcess(
            args=["cygpath", "-w", str(sample)],
            returncode=0,
            stdout="C:\\Users\\operator\\.claude\n",
            stderr="",
        )

        # Act
        with mock.patch.object(paths.platform, "uname", return_value=fake_uname), \
                mock.patch.object(paths.subprocess, "run", return_value=completed) as run_mock:
            result = paths.to_native_path(sample)

        # Assert
        assert result == "C:\\Users\\operator\\.claude"
        run_mock.assert_called_once()
        called_args, called_kwargs = run_mock.call_args
        # MUST be argv-list form (positional argv = list), never shell=True
        assert called_args[0] == ["cygpath", "-w", str(sample)]
        assert called_kwargs.get("shell", False) is False

    def test_should_shell_out_to_cygpath_when_system_is_msys(self) -> None:
        # Arrange
        sample = Path("/c/work")
        fake_uname = mock.MagicMock()
        fake_uname.system = "MSYS_NT-10.0-19045"
        completed = subprocess.CompletedProcess(
            args=["cygpath", "-w", str(sample)],
            returncode=0,
            stdout="C:\\work\r\n",
            stderr="",
        )

        # Act
        with mock.patch.object(paths.platform, "uname", return_value=fake_uname), \
                mock.patch.object(paths.subprocess, "run", return_value=completed):
            result = paths.to_native_path(sample)

        # Assert — trailing CRLF stripped
        assert result == "C:\\work"

    def test_should_shell_out_to_cygpath_when_system_is_cygwin(self) -> None:
        # Arrange
        sample = Path("/cygdrive/c/work")
        fake_uname = mock.MagicMock()
        fake_uname.system = "CYGWIN_NT-10.0"
        completed = subprocess.CompletedProcess(
            args=["cygpath", "-w", str(sample)],
            returncode=0,
            stdout="C:\\work\n",
            stderr="",
        )

        # Act
        with mock.patch.object(paths.platform, "uname", return_value=fake_uname), \
                mock.patch.object(paths.subprocess, "run", return_value=completed):
            result = paths.to_native_path(sample)

        # Assert
        assert result == "C:\\work"


class TestIsStdoutTty:
    """is_stdout_tty() -> bool. Honest TTY detection helper."""

    def test_should_return_true_when_stdout_isatty_is_true(self) -> None:
        # Arrange
        fake_stdout = mock.MagicMock()
        fake_stdout.isatty.return_value = True

        # Act
        with mock.patch.object(sys, "stdout", fake_stdout):
            result = paths.is_stdout_tty()

        # Assert
        assert result is True

    def test_should_return_false_when_stdout_isatty_is_false(self) -> None:
        # Arrange
        fake_stdout = mock.MagicMock()
        fake_stdout.isatty.return_value = False

        # Act
        with mock.patch.object(sys, "stdout", fake_stdout):
            result = paths.is_stdout_tty()

        # Assert
        assert result is False

    def test_should_return_false_when_stdout_has_no_isatty(self) -> None:
        # Arrange — captured / non-stream stdout (e.g. pytest capsys without a tty)
        class NoIsAtty:
            pass

        # Act
        with mock.patch.object(sys, "stdout", NoIsAtty()):
            result = paths.is_stdout_tty()

        # Assert — defaults to False (conservative)
        assert result is False


class TestResolveHome:
    """resolve_home() -> Path. Returns Path of operator HOME."""

    def test_should_return_path_of_home_env_when_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Arrange
        monkeypatch.setenv("HOME", "/Users/operator")

        # Act
        result = paths.resolve_home()

        # Assert
        assert result == Path("/Users/operator")

    def test_should_fall_back_to_path_home_when_home_env_unset(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Arrange — strip HOME so Path.home() falls back to pwd / userprofile
        monkeypatch.delenv("HOME", raising=False)
        # USERPROFILE governs Path.home() on Windows; we set it so Path.home()
        # doesn't crash on Windows CI. On POSIX, this var is ignored.
        monkeypatch.setenv("USERPROFILE", "/Users/operator-fallback")
        fake_home = Path("/Users/operator-fallback")

        # Act
        with mock.patch.object(paths.Path, "home", return_value=fake_home):
            result = paths.resolve_home()

        # Assert
        assert result == fake_home
