"""Tests for etc_installer.status_line — interactive status-line installer.

Covers AC-007 (Ftmp-5afddbce task 004 / spec BR-007):

- install_status_line(target_dir, mode) is the public entry point.
- INTERACTIVE mode prints the literal BR-007 prompt byte-for-byte to
  stdout, reads y/yes (case-insensitive) -> install, n/empty -> skip.
- INTERACTIVE + affirmative: writes a ``statusLine`` key into
  ``target_dir/settings.json`` (preserving every other top-level key)
  AND copies a ``statusline.sh`` source into ``target_dir/scripts/``.
- INTERACTIVE + negative: no settings.json mutation, no scripts/ copy.
- NON_INTERACTIVE mode skips entirely — no prompt fires, no file
  mutation occurs.

The OperatorMode enum is the same enum exposed by
etc_installer.preflights (single canonical INTERACTIVE / NON_INTERACTIVE
classification across the installer; design.md Module Structure pins
this in the Infrastructure layer).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest import mock

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from etc_installer import preflights, status_line  # noqa: E402

# Verbatim BR-007 prompt string — the canonical pin. Any drift here
# means the operator-visible prompt has drifted from spec.md BR-007.
_BR_007_PROMPT = (
    "Install the etc default status line? This will overwrite your "
    "existing status line if you have one. [y/N]"
)


def _seed_settings(target_dir: Path, payload: dict[str, object]) -> Path:
    """Write a settings.json under ``target_dir`` and return its path."""
    target_dir.mkdir(parents=True, exist_ok=True)
    settings = target_dir / "settings.json"
    settings.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return settings


class TestPromptLiteral:
    """AC-007: the BR-007 prompt string is printed byte-for-byte."""

    def test_should_print_br_007_prompt_verbatim_when_mode_is_interactive(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Arrange — existing settings.json so the install path is exercised
        _seed_settings(tmp_path, {"existing": "key"})

        # Act — operator answers "n" so we don't touch files
        with mock.patch.object(status_line.Prompt, "ask", return_value="n"):
            status_line.install_status_line(
                target_dir=tmp_path,
                mode=preflights.OperatorMode.INTERACTIVE,
            )

        # Assert — the verbatim BR-007 literal is in stdout
        out = capsys.readouterr().out
        assert _BR_007_PROMPT in out, (
            f"BR-007 prompt must appear byte-for-byte in stdout.\n"
            f"Expected substring: {_BR_007_PROMPT!r}\n"
            f"Got: {out!r}"
        )


class TestInteractiveAffirmative:
    """INTERACTIVE + y/yes: install statusLine into settings.json + copy script."""

    def test_should_write_status_line_key_when_operator_answers_yes(
        self, tmp_path: Path
    ) -> None:
        # Arrange
        settings = _seed_settings(tmp_path, {"existing": "key"})

        # Act
        with mock.patch.object(status_line.Prompt, "ask", return_value="y"):
            status_line.install_status_line(
                target_dir=tmp_path,
                mode=preflights.OperatorMode.INTERACTIVE,
            )

        # Assert — settings.json now has a statusLine key
        body = json.loads(settings.read_text(encoding="utf-8"))
        assert "statusLine" in body
        assert body["existing"] == "key", "other top-level keys preserved"

    def test_should_copy_statusline_sh_to_scripts_when_operator_answers_yes(
        self, tmp_path: Path
    ) -> None:
        # Arrange
        _seed_settings(tmp_path, {})

        # Act
        with mock.patch.object(status_line.Prompt, "ask", return_value="yes"):
            status_line.install_status_line(
                target_dir=tmp_path,
                mode=preflights.OperatorMode.INTERACTIVE,
            )

        # Assert — target_dir/scripts/statusline.sh exists
        copied = tmp_path / "scripts" / "statusline.sh"
        assert copied.exists(), "statusline.sh must be copied into scripts/"
        assert copied.read_text(encoding="utf-8") != "", "must not copy empty file"

    def test_should_accept_yes_case_insensitively(self, tmp_path: Path) -> None:
        # Arrange
        settings = _seed_settings(tmp_path, {})

        # Act — uppercase Y
        with mock.patch.object(status_line.Prompt, "ask", return_value="Y"):
            status_line.install_status_line(
                target_dir=tmp_path,
                mode=preflights.OperatorMode.INTERACTIVE,
            )

        # Assert
        body = json.loads(settings.read_text(encoding="utf-8"))
        assert "statusLine" in body


class TestInteractiveNegative:
    """INTERACTIVE + n/empty: no mutation."""

    def test_should_not_write_status_line_key_when_operator_answers_no(
        self, tmp_path: Path
    ) -> None:
        # Arrange
        settings = _seed_settings(tmp_path, {"existing": "key"})

        # Act
        with mock.patch.object(status_line.Prompt, "ask", return_value="n"):
            status_line.install_status_line(
                target_dir=tmp_path,
                mode=preflights.OperatorMode.INTERACTIVE,
            )

        # Assert — settings.json unchanged
        body = json.loads(settings.read_text(encoding="utf-8"))
        assert "statusLine" not in body
        assert body == {"existing": "key"}

    def test_should_not_write_status_line_key_when_operator_answers_empty(
        self, tmp_path: Path
    ) -> None:
        # Arrange
        settings = _seed_settings(tmp_path, {})

        # Act — empty input (operator hits enter on default N)
        with mock.patch.object(status_line.Prompt, "ask", return_value=""):
            status_line.install_status_line(
                target_dir=tmp_path,
                mode=preflights.OperatorMode.INTERACTIVE,
            )

        # Assert
        body = json.loads(settings.read_text(encoding="utf-8"))
        assert "statusLine" not in body

    def test_should_not_create_scripts_dir_when_operator_answers_no(
        self, tmp_path: Path
    ) -> None:
        # Arrange
        _seed_settings(tmp_path, {})

        # Act
        with mock.patch.object(status_line.Prompt, "ask", return_value="n"):
            status_line.install_status_line(
                target_dir=tmp_path,
                mode=preflights.OperatorMode.INTERACTIVE,
            )

        # Assert — no scripts dir
        assert not (tmp_path / "scripts").exists()


class TestNonInteractive:
    """NON_INTERACTIVE mode: skip entirely; never prompt, never mutate."""

    def test_should_not_prompt_when_mode_is_non_interactive(
        self, tmp_path: Path
    ) -> None:
        # Arrange
        _seed_settings(tmp_path, {})

        # Act + Assert — Prompt.ask must NOT be called
        with mock.patch.object(
            status_line.Prompt, "ask", side_effect=AssertionError("must not prompt")
        ):
            status_line.install_status_line(
                target_dir=tmp_path,
                mode=preflights.OperatorMode.NON_INTERACTIVE,
            )

    def test_should_not_mutate_settings_when_mode_is_non_interactive(
        self, tmp_path: Path
    ) -> None:
        # Arrange
        settings = _seed_settings(tmp_path, {"existing": "key"})
        before = settings.read_text(encoding="utf-8")

        # Act
        status_line.install_status_line(
            target_dir=tmp_path,
            mode=preflights.OperatorMode.NON_INTERACTIVE,
        )

        # Assert
        after = settings.read_text(encoding="utf-8")
        assert after == before
        assert not (tmp_path / "scripts").exists()
