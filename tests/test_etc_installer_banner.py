"""Tests for etc_installer.banner — TTY-gated raw-bytes banner write.

Covers AC-006 and ADR-005: when sys.stdout.isatty() is True, raw bytes
of assets/etsy-logo.ascii are written to sys.stdout.buffer. When stdout
is piped/redirected (isatty False), no logo bytes appear. Banner is
decorative — missing asset emits a warning but does NOT raise.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path
from unittest import mock

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from etc_installer import banner  # noqa: E402

BANNER_ASSET = _REPO_ROOT / "assets" / "etsy-logo.ascii"


class _FakeStdoutTty:
    """Stand-in for sys.stdout that reports isatty()=True and captures buffer writes."""

    def __init__(self) -> None:
        self.buffer = io.BytesIO()

    def isatty(self) -> bool:
        return True

    def write(self, _: str) -> int:
        # Text-mode writes should NOT carry banner bytes per ADR-005.
        return 0

    def flush(self) -> None:
        return None


class _FakeStdoutPipe:
    """Stand-in for sys.stdout in a non-TTY context (piped/redirected)."""

    def __init__(self) -> None:
        self.buffer = io.BytesIO()

    def isatty(self) -> bool:
        return False

    def write(self, _: str) -> int:
        return 0

    def flush(self) -> None:
        return None


class TestPrintBanner:
    """print_banner() -> None. TTY-gated raw-bytes write."""

    def test_should_write_raw_asset_bytes_to_stdout_buffer_when_stdout_is_tty(
        self,
    ) -> None:
        # Arrange
        fake_stdout = _FakeStdoutTty()
        expected_bytes = BANNER_ASSET.read_bytes()

        # Act
        with mock.patch.object(sys, "stdout", fake_stdout):
            banner.print_banner()

        # Assert — buffer holds the exact bytes of the asset
        assert fake_stdout.buffer.getvalue() == expected_bytes

    def test_banner_skipped_when_not_tty(self) -> None:
        # Arrange — non-TTY stdout (piped/redirected)
        fake_stdout = _FakeStdoutPipe()

        # Act
        with mock.patch.object(sys, "stdout", fake_stdout):
            banner.print_banner()

        # Assert — no bytes written
        assert fake_stdout.buffer.getvalue() == b""

    def test_should_not_raise_when_asset_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Arrange — point banner at a non-existent file; isatty=True
        missing = tmp_path / "no-such-banner.ascii"
        monkeypatch.setattr(banner, "BANNER_ASSET_PATH", missing)
        fake_stdout = _FakeStdoutTty()

        # Act
        with mock.patch.object(sys, "stdout", fake_stdout):
            banner.print_banner()  # must not raise

        # Assert — nothing went to the buffer (graceful degrade)
        assert fake_stdout.buffer.getvalue() == b""

    def test_should_use_sys_stdout_buffer_not_text_write(self) -> None:
        # Arrange — explicit guard that the raw-bytes write path is used
        # (per ADR-005, NOT sys.stdout.write(text)).
        fake_stdout = _FakeStdoutTty()

        # Act
        with mock.patch.object(sys, "stdout", fake_stdout):
            banner.print_banner()

        # Assert — the buffer (raw bytes channel) received the payload
        assert len(fake_stdout.buffer.getvalue()) > 0
