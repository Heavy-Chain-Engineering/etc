"""Tests for install.sh @google/design.md preflight (F018).

Verify the new F018 preflight INFO line + non-blocking behavior.
"""

from __future__ import annotations

from pathlib import Path

INSTALL_SH = Path(__file__).parent.parent / "install.sh"


def _install_sh_text() -> str:
    return INSTALL_SH.read_text(encoding="utf-8")


class TestPreflightInfo:
    def test_f018_info_constant_defined(self) -> None:
        text = _install_sh_text()
        assert "F018_INFO_LINE" in text

    def test_info_message_contains_package_name(self) -> None:
        text = _install_sh_text()
        assert "@google/design.md" in text

    def test_info_message_links_to_google_spec(self) -> None:
        text = _install_sh_text()
        assert "google-labs-code/design.md" in text

    def test_info_message_documents_install_command(self) -> None:
        text = _install_sh_text()
        assert "npm install -g @google/design.md" in text


class TestPreflightPattern:
    def test_preflight_uses_offer_install_helper(self) -> None:
        """F018 preflight uses the existing offer_install helper (non-blocking,
        prompted in interactive mode, INFO-only in non-interactive)."""
        text = _install_sh_text()
        # Find the F018 region (between F016 mergiraf block and the end)
        f018_idx = text.find("F018")
        assert f018_idx != -1
        region = text[f018_idx : f018_idx + 1500]
        assert "offer_install" in region
        assert "@google/design.md" in region

    def test_preflight_does_not_abort_on_absent_package(self) -> None:
        """The preflight is informational — no `exit 1` near the offer_install."""
        text = _install_sh_text()
        # Locate the @google/design.md preflight call site
        google_idx = text.find('"@google/design.md"')
        assert google_idx != -1
        # 200 chars before + 200 after should be free of `exit 1`
        region = text[max(0, google_idx - 200) : google_idx + 400]
        assert "exit 1" not in region


class TestDetectionApproach:
    """install.sh probes for the package via `npm list -g` (consistent
    with the offline-friendly detection used for impeccable)."""

    def test_npm_list_used_for_detection(self) -> None:
        text = _install_sh_text()
        # The preflight uses `npm list -g --depth=0 @google/design.md` as
        # the detection probe (avoids unconditional npx invocation which
        # would download the package on first install.sh run).
        assert "npm list -g" in text
        assert "@google/design.md" in text
