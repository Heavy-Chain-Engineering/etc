"""Tests for the @google/design.md preflight (F018).

Verify the F018 preflight INFO line + non-blocking behavior.

Ftmp-5afddbce task 006 migration note: F018's preflight implementation
moved from install.sh to ``etc_installer/preflights.py`` per design.md
(BR-005, AC-005). Pre-task-003 the rewrite module does not yet exist,
so every test in this file is gated with
``skipif(not PREFLIGHTS_PATH.exists(), reason=PREFLIGHTS_PENDING_REASON)``.
The skip-condition auto-clears once task 003 ships preflights.py and
the assertions become live again, scanning preflights.py instead of
install.sh.
"""

from __future__ import annotations

from pathlib import Path

import pytest

PREFLIGHTS_PATH = Path(__file__).parent.parent / "etc_installer" / "preflights.py"
PREFLIGHTS_PENDING_REASON = (
    "etc_installer/preflights.py not yet shipped (pending Ftmp-5afddbce "
    "task 003 preflights.py)"
)


def _preflights_text() -> str:
    return PREFLIGHTS_PATH.read_text(encoding="utf-8")


@pytest.mark.skipif(
    not PREFLIGHTS_PATH.exists(),
    reason=PREFLIGHTS_PENDING_REASON,
)
class TestPreflightInfo:
    def test_f018_info_constant_defined(self) -> None:
        text = _preflights_text()
        assert "F018_INFO_LINE" in text

    def test_info_message_contains_package_name(self) -> None:
        text = _preflights_text()
        assert "@google/design.md" in text

    def test_info_message_links_to_google_spec(self) -> None:
        text = _preflights_text()
        assert "google-labs-code/design.md" in text

    def test_info_message_documents_install_command(self) -> None:
        text = _preflights_text()
        assert "npm install -g @google/design.md" in text


@pytest.mark.skipif(
    not PREFLIGHTS_PATH.exists(),
    reason=PREFLIGHTS_PENDING_REASON,
)
class TestPreflightPattern:
    def test_preflight_uses_offer_install_helper(self) -> None:
        """F018 preflight uses the existing offer_install helper (non-blocking,
        prompted in interactive mode, INFO-only in non-interactive)."""
        text = _preflights_text()
        # Find the F018 region (post-migration: the F018_INFO_LINE
        # constant declaration + its surrounding offer_install call site).
        f018_idx = text.find("F018")
        assert f018_idx != -1
        region = text[f018_idx : f018_idx + 1500]
        assert "offer_install" in region
        assert "@google/design.md" in region

    def test_preflight_does_not_abort_on_absent_package(self) -> None:
        """The preflight is informational — no `sys.exit` near the
        offer_install call site (the Python equivalent of bash's `exit 1`).
        """
        text = _preflights_text()
        # Locate the @google/design.md preflight call site
        google_idx = text.find('"@google/design.md"')
        assert google_idx != -1
        # 200 chars before + 400 after should be free of sys.exit / raise SystemExit
        region = text[max(0, google_idx - 200) : google_idx + 400]
        assert "sys.exit" not in region
        assert "raise SystemExit" not in region


@pytest.mark.skipif(
    not PREFLIGHTS_PATH.exists(),
    reason=PREFLIGHTS_PENDING_REASON,
)
class TestDetectionApproach:
    """preflights.py probes for the package via `npm list -g` (consistent
    with the offline-friendly detection used for impeccable)."""

    def test_npm_list_used_for_detection(self) -> None:
        text = _preflights_text()
        # The preflight uses `npm list -g --depth=0 @google/design.md` as
        # the detection probe (avoids unconditional npx invocation which
        # would download the package on first installer run).
        assert "npm list -g" in text
        assert "@google/design.md" in text
