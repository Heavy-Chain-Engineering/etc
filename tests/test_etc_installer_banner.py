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


import os  # noqa: E402 — used by the width-mock fixture below


def _wide_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub shutil.get_terminal_size() to report 200 cols wide.

    Required for tests that assert the banner DOES write — without this
    stub, the real terminal in CI / pytest is often 80 cols, and the
    width-gate in banner.py (banner is 106 cols visible) would skip
    the write. Tests of the wide-terminal happy path use this; tests
    of the narrow-terminal skip path use _narrow_terminal below.
    """
    monkeypatch.setattr(
        "shutil.get_terminal_size",
        lambda fallback=(80, 24): os.terminal_size((200, 50)),
    )


def _narrow_terminal(monkeypatch: pytest.MonkeyPatch, cols: int = 80) -> None:
    """Stub shutil.get_terminal_size() to report a narrow terminal."""
    monkeypatch.setattr(
        "shutil.get_terminal_size",
        lambda fallback=(80, 24): os.terminal_size((cols, 24)),
    )


class TestPrintBanner:
    """print_banner() -> None. TTY-gated + width-gated raw-bytes write."""

    def test_should_write_raw_asset_bytes_to_stdout_buffer_when_stdout_is_tty_and_terminal_is_wide(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Arrange — wide-terminal stub so width-gate passes
        _wide_terminal(monkeypatch)
        fake_stdout = _FakeStdoutTty()
        expected_bytes = BANNER_ASSET.read_bytes()

        # Act
        with mock.patch.object(sys, "stdout", fake_stdout):
            banner.print_banner()

        # Assert — buffer holds the exact bytes of the asset
        assert fake_stdout.buffer.getvalue() == expected_bytes

    def test_banner_skipped_when_not_tty(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Arrange — non-TTY stdout (piped/redirected). Width-gate also
        # stubbed wide so the only gating signal is the isatty() check.
        _wide_terminal(monkeypatch)
        fake_stdout = _FakeStdoutPipe()

        # Act
        with mock.patch.object(sys, "stdout", fake_stdout):
            banner.print_banner()

        # Assert — no bytes written
        assert fake_stdout.buffer.getvalue() == b""

    def test_banner_skipped_when_terminal_narrower_than_banner_width(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Arrange — TTY=True but terminal is 80 cols (banner needs 106).
        # The width-gate must skip; wrapping jp2a output on narrow
        # terminals produces visual garbage. This test was missing in
        # the original F026 ship — operator caught the gap 2026-05-23.
        _narrow_terminal(monkeypatch, cols=80)
        fake_stdout = _FakeStdoutTty()

        # Act
        with mock.patch.object(sys, "stdout", fake_stdout):
            banner.print_banner()

        # Assert — no bytes written because the terminal is too narrow
        assert fake_stdout.buffer.getvalue() == b""

    def test_banner_skipped_when_terminal_exactly_one_col_narrower_than_width(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Arrange — edge case: terminal is 105 cols, banner is 106 cols.
        # The gate is `columns < banner_width` (strict less-than), so
        # 105 cols MUST skip (105 < 106).
        _narrow_terminal(monkeypatch, cols=105)
        fake_stdout = _FakeStdoutTty()

        # Act
        with mock.patch.object(sys, "stdout", fake_stdout):
            banner.print_banner()

        # Assert — no bytes written (105 < 106 → skip)
        assert fake_stdout.buffer.getvalue() == b""

    def test_banner_writes_when_terminal_exactly_matches_banner_width(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Arrange — edge case: terminal is exactly 106 cols. The gate
        # is `columns < banner_width`, so 106 == 106 → write proceeds.
        _narrow_terminal(monkeypatch, cols=106)
        fake_stdout = _FakeStdoutTty()

        # Act
        with mock.patch.object(sys, "stdout", fake_stdout):
            banner.print_banner()

        # Assert — bytes written at the boundary
        assert len(fake_stdout.buffer.getvalue()) > 0

    def test_should_not_raise_when_asset_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Arrange — point banner at a non-existent file; isatty=True,
        # terminal wide enough.
        _wide_terminal(monkeypatch)
        missing = tmp_path / "no-such-banner.ascii"
        monkeypatch.setattr(banner, "BANNER_ASSET_PATH", missing)
        fake_stdout = _FakeStdoutTty()

        # Act
        with mock.patch.object(sys, "stdout", fake_stdout):
            banner.print_banner()  # must not raise

        # Assert — nothing went to the buffer (graceful degrade)
        assert fake_stdout.buffer.getvalue() == b""

    def test_should_use_sys_stdout_buffer_not_text_write(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Arrange — explicit guard that the raw-bytes write path is used
        # (per ADR-005, NOT sys.stdout.write(text)).
        _wide_terminal(monkeypatch)
        fake_stdout = _FakeStdoutTty()

        # Act
        with mock.patch.object(sys, "stdout", fake_stdout):
            banner.print_banner()

        # Assert — the buffer (raw bytes channel) received the payload
        assert len(fake_stdout.buffer.getvalue()) > 0
