"""Tests for etc_installer.settings_merge — pure-Python hooks-section merge.

Covers the settings-merge AC of Ftmp-5afddbce task 003:

- merge_hooks(target_settings: Path, template_path: Path) -> None replaces
  the 'hooks' top-level key with the template's 'hooks' value.
- Every other top-level key in target is preserved byte-for-byte.
- Edge case 5: invalid JSON in target raises json.JSONDecodeError; the
  caller catches and prints `✗ settings.json at <path> is not valid JSON
  — skipping merge`. The merge function MUST NOT silently overwrite a
  corrupt file.
- Pure Python — no shell-embedded heredocs (ADR-Ftmp-5afddbce-004).

Per design.md / ADR-004 the function reads the target via
pathlib.Path.read_text(), parses with json.loads, mutates the 'hooks'
key in place, writes back via json.dumps(merged, indent=2) + "\\n".
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from etc_installer import settings_merge  # noqa: E402


class TestMergeHooks:
    """merge_hooks(target_settings, template_path) -> None."""

    def test_should_replace_hooks_key_when_target_has_hooks(
        self, tmp_path: Path
    ) -> None:
        # Arrange
        target = tmp_path / "settings.json"
        template = tmp_path / "settings-hooks.json"
        target.write_text(
            json.dumps({"hooks": {"PreToolUse": [{"old": True}]}}, indent=2),
            encoding="utf-8",
        )
        template.write_text(
            json.dumps({"hooks": {"PreToolUse": [{"new": True}]}}, indent=2),
            encoding="utf-8",
        )

        # Act
        settings_merge.merge_hooks(target, template, tmp_path / "hooks")

        # Assert
        merged = json.loads(target.read_text(encoding="utf-8"))
        assert merged["hooks"] == {"PreToolUse": [{"new": True}]}

    def test_should_preserve_other_top_level_keys_when_merging(
        self, tmp_path: Path
    ) -> None:
        # Arrange — operator has unrelated top-level keys that MUST survive
        target = tmp_path / "settings.json"
        template = tmp_path / "settings-hooks.json"
        target.write_text(
            json.dumps(
                {
                    "hooks": {"PreToolUse": [{"old": True}]},
                    "permissions": {"defaultMode": "interactive"},
                    "statusLine": {"type": "command", "command": "old.sh"},
                    "operatorCustomKey": {"keep": "me"},
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        template.write_text(
            json.dumps({"hooks": {"PreToolUse": [{"new": True}]}}, indent=2),
            encoding="utf-8",
        )

        # Act
        settings_merge.merge_hooks(target, template, tmp_path / "hooks")

        # Assert — every non-hooks key untouched
        merged = json.loads(target.read_text(encoding="utf-8"))
        assert merged["permissions"] == {"defaultMode": "interactive"}
        assert merged["statusLine"] == {"type": "command", "command": "old.sh"}
        assert merged["operatorCustomKey"] == {"keep": "me"}
        assert merged["hooks"] == {"PreToolUse": [{"new": True}]}

    def test_should_write_indent_2_and_trailing_newline(self, tmp_path: Path) -> None:
        # Arrange
        target = tmp_path / "settings.json"
        template = tmp_path / "settings-hooks.json"
        target.write_text('{"hooks": {}}', encoding="utf-8")
        template.write_text(
            json.dumps({"hooks": {"X": "Y"}}, indent=2),
            encoding="utf-8",
        )

        # Act
        settings_merge.merge_hooks(target, template, tmp_path / "hooks")

        # Assert — indent=2 (so contains "\n  ") and trailing newline
        body = target.read_text(encoding="utf-8")
        assert body.endswith("\n")
        # indent=2: second-level keys are prefixed by exactly two spaces
        assert '\n  "hooks":' in body

    def test_should_raise_json_decode_error_when_target_is_invalid_json(
        self, tmp_path: Path
    ) -> None:
        # Arrange — invalid JSON in operator's settings.json (Edge Case 5)
        target = tmp_path / "settings.json"
        template = tmp_path / "settings-hooks.json"
        target.write_text("{not valid json", encoding="utf-8")
        template.write_text(json.dumps({"hooks": {}}, indent=2), encoding="utf-8")
        before = target.read_text(encoding="utf-8")

        # Act / Assert — JSONDecodeError surfaces; file content unchanged
        with pytest.raises(json.JSONDecodeError):
            settings_merge.merge_hooks(target, template, tmp_path / "hooks")
        after = target.read_text(encoding="utf-8")
        assert after == before, (
            "merge_hooks MUST NOT overwrite a corrupt target settings.json "
            "(Edge Case 5)"
        )

    def test_should_add_hooks_key_when_target_has_no_hooks_key(
        self, tmp_path: Path
    ) -> None:
        # Arrange — target settings.json exists but has no hooks key yet
        target = tmp_path / "settings.json"
        template = tmp_path / "settings-hooks.json"
        target.write_text(
            json.dumps({"permissions": {"defaultMode": "ask"}}, indent=2),
            encoding="utf-8",
        )
        template.write_text(
            json.dumps({"hooks": {"PreToolUse": [{"new": True}]}}, indent=2),
            encoding="utf-8",
        )

        # Act
        settings_merge.merge_hooks(target, template, tmp_path / "hooks")

        # Assert
        merged = json.loads(target.read_text(encoding="utf-8"))
        assert merged["hooks"] == {"PreToolUse": [{"new": True}]}
        assert merged["permissions"] == {"defaultMode": "ask"}

    def test_should_substitute_hooks_dir_placeholder_when_merging(
        self, tmp_path: Path
    ) -> None:
        # Arrange — template uses the {{ETC_HOOKS_DIR}} placeholder for
        # hook command paths (per compile-sdlc.py). merge_hooks must
        # substitute it with the resolved hooks_dir.
        target = tmp_path / "settings.json"
        template = tmp_path / "settings-hooks.json"
        hooks_dir = tmp_path / "etc-install" / "hooks"
        target.write_text("{}", encoding="utf-8")
        template.write_text(
            json.dumps(
                {
                    "hooks": {
                        "PreToolUse": [
                            {
                                "hooks": [
                                    {
                                        "type": "command",
                                        "command": "{{ETC_HOOKS_DIR}}/check-test-exists.sh",
                                    }
                                ]
                            }
                        ]
                    }
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        # Act
        settings_merge.merge_hooks(target, template, hooks_dir)

        # Assert — placeholder gone, resolved path present
        merged = json.loads(target.read_text(encoding="utf-8"))
        command = merged["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
        assert "{{ETC_HOOKS_DIR}}" not in command
        assert command == f"{hooks_dir}/check-test-exists.sh"


class TestSubstituteHooksDir:
    """substitute_hooks_dir(template_text, hooks_dir) -> str."""

    def test_should_replace_every_placeholder_occurrence(
        self, tmp_path: Path
    ) -> None:
        # Arrange
        hooks_dir = tmp_path / "hooks"
        template_text = (
            '{"a": "{{ETC_HOOKS_DIR}}/one.sh", '
            '"b": "{{ETC_HOOKS_DIR}}/two.sh"}'
        )

        # Act
        result = settings_merge.substitute_hooks_dir(template_text, hooks_dir)

        # Assert
        assert "{{ETC_HOOKS_DIR}}" not in result
        assert f'"{hooks_dir}/one.sh"' in result
        assert f'"{hooks_dir}/two.sh"' in result

    def test_should_passthrough_text_with_no_placeholder(
        self, tmp_path: Path
    ) -> None:
        # Arrange
        template_text = '{"unrelated": "value"}'

        # Act
        result = settings_merge.substitute_hooks_dir(
            template_text, tmp_path / "hooks"
        )

        # Assert
        assert result == template_text
