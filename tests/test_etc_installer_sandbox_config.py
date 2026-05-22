"""Tests for etc_installer.sandbox_config — interactive sandbox-defaults installer.

Covers AC-008 (Ftmp-5afddbce task 004 / spec BR-008):

- install_sandbox_config(target_dir, mode) is the public entry point.
- INTERACTIVE mode prints the literal BR-008 prompt byte-for-byte to
  stdout, reads y/yes (case-insensitive) -> merge defaults, n/empty
  -> skip.
- INTERACTIVE + affirmative: merges sandbox defaults into the top-level
  ``permissions`` key of ``target_dir/settings.json``. The merged
  ``permissions`` dict contains ``defaultMode`` (a string),
  ``allow`` / ``ask`` / ``deny`` (lists). Every other top-level key
  is preserved byte-for-byte.
- INTERACTIVE + negative: no settings.json mutation.
- NON_INTERACTIVE mode skips entirely — no prompt fires, no mutation.

The OperatorMode enum is the canonical INTERACTIVE / NON_INTERACTIVE
classification exposed by etc_installer.preflights.
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

from etc_installer import preflights, sandbox_config  # noqa: E402

# Verbatim BR-008 prompt string pin.
_BR_008_PROMPT = (
    "Install the etc default sandbox config? This enables auto-mode "
    "without --dangerously-skip-permissions. [y/N]"
)


def _seed_settings(target_dir: Path, payload: dict[str, object]) -> Path:
    target_dir.mkdir(parents=True, exist_ok=True)
    settings = target_dir / "settings.json"
    settings.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return settings


class TestPromptLiteral:
    """AC-008: the BR-008 prompt string is printed byte-for-byte."""

    def test_should_print_br_008_prompt_verbatim_when_mode_is_interactive(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Arrange
        _seed_settings(tmp_path, {})

        # Act — operator answers "n"
        with mock.patch.object(sandbox_config.Prompt, "ask", return_value="n"):
            sandbox_config.install_sandbox_config(
                target_dir=tmp_path,
                mode=preflights.OperatorMode.INTERACTIVE,
            )

        # Assert
        out = capsys.readouterr().out
        assert _BR_008_PROMPT in out, (
            f"BR-008 prompt must appear byte-for-byte in stdout.\n"
            f"Expected substring: {_BR_008_PROMPT!r}\n"
            f"Got: {out!r}"
        )


class TestInteractiveAffirmative:
    """INTERACTIVE + y/yes: merge permissions defaults into settings.json."""

    def test_should_write_permissions_key_when_operator_answers_yes(
        self, tmp_path: Path
    ) -> None:
        # Arrange
        settings = _seed_settings(tmp_path, {"existing": "key"})

        # Act
        with mock.patch.object(sandbox_config.Prompt, "ask", return_value="y"):
            sandbox_config.install_sandbox_config(
                target_dir=tmp_path,
                mode=preflights.OperatorMode.INTERACTIVE,
            )

        # Assert
        body = json.loads(settings.read_text(encoding="utf-8"))
        assert "permissions" in body
        assert body["existing"] == "key", "other top-level keys preserved"

    def test_should_write_default_mode_and_allow_ask_deny_lists(
        self, tmp_path: Path
    ) -> None:
        # Arrange
        settings = _seed_settings(tmp_path, {})

        # Act
        with mock.patch.object(sandbox_config.Prompt, "ask", return_value="yes"):
            sandbox_config.install_sandbox_config(
                target_dir=tmp_path,
                mode=preflights.OperatorMode.INTERACTIVE,
            )

        # Assert — BR-008 mandates defaultMode + allow/ask/deny keys
        body = json.loads(settings.read_text(encoding="utf-8"))
        perms = body["permissions"]
        assert isinstance(perms["defaultMode"], str)
        assert isinstance(perms["allow"], list)
        assert isinstance(perms["ask"], list)
        assert isinstance(perms["deny"], list)

    def test_should_set_default_mode_to_a_known_sandbox_mode(
        self, tmp_path: Path
    ) -> None:
        # Arrange — BR-008 says the prompt advertises "auto-mode without
        # --dangerously-skip-permissions". The resulting defaultMode
        # must be one of Claude Code's published modes (acceptDocs,
        # auto, default, plan, etc.). The author's own settings.json
        # uses "auto"; we accept the documented set conservatively.
        _seed_settings(tmp_path, {})

        # Act
        with mock.patch.object(sandbox_config.Prompt, "ask", return_value="y"):
            sandbox_config.install_sandbox_config(
                target_dir=tmp_path,
                mode=preflights.OperatorMode.INTERACTIVE,
            )

        # Assert
        body = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
        assert body["permissions"]["defaultMode"] in {
            "auto",
            "acceptEdits",
            "default",
            "plan",
        }

    def test_should_accept_yes_case_insensitively(self, tmp_path: Path) -> None:
        # Arrange
        settings = _seed_settings(tmp_path, {})

        # Act — uppercase Y
        with mock.patch.object(sandbox_config.Prompt, "ask", return_value="YES"):
            sandbox_config.install_sandbox_config(
                target_dir=tmp_path,
                mode=preflights.OperatorMode.INTERACTIVE,
            )

        # Assert
        body = json.loads(settings.read_text(encoding="utf-8"))
        assert "permissions" in body

    def test_should_preserve_other_top_level_keys_when_merging(
        self, tmp_path: Path
    ) -> None:
        # Arrange — settings.json has hooks + statusLine + custom key
        settings = _seed_settings(
            tmp_path,
            {
                "hooks": {"PreToolUse": [{"x": "y"}]},
                "statusLine": {"type": "command", "command": "old.sh"},
                "operatorCustomKey": {"keep": "me"},
            },
        )

        # Act
        with mock.patch.object(sandbox_config.Prompt, "ask", return_value="y"):
            sandbox_config.install_sandbox_config(
                target_dir=tmp_path,
                mode=preflights.OperatorMode.INTERACTIVE,
            )

        # Assert — every non-permissions key preserved byte-for-byte
        body = json.loads(settings.read_text(encoding="utf-8"))
        assert body["hooks"] == {"PreToolUse": [{"x": "y"}]}
        assert body["statusLine"] == {"type": "command", "command": "old.sh"}
        assert body["operatorCustomKey"] == {"keep": "me"}
        assert "permissions" in body


class TestInteractiveNegative:
    """INTERACTIVE + n/empty: no mutation."""

    def test_should_not_write_permissions_key_when_operator_answers_no(
        self, tmp_path: Path
    ) -> None:
        # Arrange
        settings = _seed_settings(tmp_path, {"existing": "key"})

        # Act
        with mock.patch.object(sandbox_config.Prompt, "ask", return_value="n"):
            sandbox_config.install_sandbox_config(
                target_dir=tmp_path,
                mode=preflights.OperatorMode.INTERACTIVE,
            )

        # Assert
        body = json.loads(settings.read_text(encoding="utf-8"))
        assert "permissions" not in body
        assert body == {"existing": "key"}

    def test_should_not_write_permissions_key_when_operator_answers_empty(
        self, tmp_path: Path
    ) -> None:
        # Arrange
        settings = _seed_settings(tmp_path, {})

        # Act
        with mock.patch.object(sandbox_config.Prompt, "ask", return_value=""):
            sandbox_config.install_sandbox_config(
                target_dir=tmp_path,
                mode=preflights.OperatorMode.INTERACTIVE,
            )

        # Assert
        body = json.loads(settings.read_text(encoding="utf-8"))
        assert "permissions" not in body


class TestNonInteractive:
    """NON_INTERACTIVE: skip entirely; never prompt, never mutate."""

    def test_should_not_prompt_when_mode_is_non_interactive(
        self, tmp_path: Path
    ) -> None:
        # Arrange
        _seed_settings(tmp_path, {})

        # Act + Assert
        with mock.patch.object(
            sandbox_config.Prompt,
            "ask",
            side_effect=AssertionError("must not prompt"),
        ):
            sandbox_config.install_sandbox_config(
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
        sandbox_config.install_sandbox_config(
            target_dir=tmp_path,
            mode=preflights.OperatorMode.NON_INTERACTIVE,
        )

        # Assert
        after = settings.read_text(encoding="utf-8")
        assert after == before
