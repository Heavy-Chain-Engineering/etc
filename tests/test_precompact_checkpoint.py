"""Tests for scripts/precompact_checkpoint.py + hooks/pre-compact-checkpoint.sh.

F-2026-05-26-compact-autocheckpoint (#36). etc's first PreCompact hook.

The script reads the PreCompact hook JSON on stdin, writes/refreshes a
best-effort .etc_sdlc/checkpoint.md (UNLESS a fresh model-written one
exists — freshness guard), and always appends one journal entry. It is
fail-open: exit 0 in all cases, never blocking compaction.

Tests drive the script as a subprocess with synthetic hook JSON on stdin
(mirrors tests/test_spec_coupling_check.py), pointing cwd at a tmp dir so
no real project files are touched (AC-08).
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "precompact_checkpoint.py"
WRAPPER = REPO_ROOT / "hooks" / "pre-compact-checkpoint.sh"
FALLBACK_OBJECTIVE = "(auto-captured at compaction; objective not derived)"


def _hook_json(
    cwd: Path,
    *,
    trigger: str = "manual",
    transcript_path: str | None = None,
) -> str:
    payload: dict[str, object] = {
        "session_id": "test-session",
        "cwd": str(cwd),
        "trigger": trigger,
        "hook_event_name": "PreCompact",
        "permission_mode": "default",
    }
    if transcript_path is not None:
        payload["transcript_path"] = transcript_path
    return json.dumps(payload)


def _run_script(stdin: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python3", str(SCRIPT)],
        input=stdin,
        capture_output=True,
        text=True,
        timeout=20,
    )


def _checkpoint(cwd: Path) -> Path:
    return cwd / ".etc_sdlc" / "checkpoint.md"


def _journal(cwd: Path) -> Path:
    return cwd / ".etc_sdlc" / "journal.md"


def _write_transcript(cwd: Path, lines: list[dict[str, object]]) -> Path:
    path = cwd / "transcript.jsonl"
    path.write_text("\n".join(json.dumps(line) for line in lines), encoding="utf-8")
    return path


def test_should_create_checkpoint_when_none_exists(tmp_path: Path) -> None:
    # Arrange
    stdin = _hook_json(tmp_path, trigger="manual")

    # Act
    result = _run_script(stdin)

    # Assert
    assert result.returncode == 0
    content = _checkpoint(tmp_path).read_text(encoding="utf-8")
    assert "# Session Checkpoint" in content
    assert "**Saved:**" in content
    assert "manual" in content
    assert "## Task Status" in content


def test_should_preserve_checkpoint_when_fresh(tmp_path: Path) -> None:
    # Arrange — a model-written checkpoint 1 minute old
    checkpoint = _checkpoint(tmp_path)
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    original = "# Session Checkpoint\n\n**Saved:** 2020-01-01 00:00\nRICH MODEL CONTENT\n"
    checkpoint.write_text(original, encoding="utf-8")
    one_minute_ago = time.time() - 60
    os.utime(checkpoint, (one_minute_ago, one_minute_ago))

    # Act
    result = _run_script(_hook_json(tmp_path))

    # Assert — byte-identical (freshness guard hit)
    assert result.returncode == 0
    assert checkpoint.read_text(encoding="utf-8") == original


def test_should_rewrite_checkpoint_when_stale(tmp_path: Path) -> None:
    # Arrange — a checkpoint 30 minutes old
    checkpoint = _checkpoint(tmp_path)
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    original = "# Session Checkpoint\n\n**Saved:** 2020-01-01 00:00\nSTALE CONTENT\n"
    checkpoint.write_text(original, encoding="utf-8")
    thirty_minutes_ago = time.time() - 1800
    os.utime(checkpoint, (thirty_minutes_ago, thirty_minutes_ago))

    # Act
    result = _run_script(_hook_json(tmp_path))

    # Assert — rewritten with a newer Saved timestamp
    assert result.returncode == 0
    content = _checkpoint(tmp_path).read_text(encoding="utf-8")
    assert content != original
    assert "2020-01-01 00:00" not in content


def test_should_exit_zero_when_stdin_malformed(tmp_path: Path) -> None:
    # Arrange — non-JSON stdin, cwd has no checkpoint
    # Act
    result = _run_script("not json")

    # Assert — fail-open, nothing destructive written, stderr note present
    assert result.returncode == 0
    assert result.stderr.strip() != ""
    assert not _checkpoint(tmp_path).exists()


def test_should_append_one_journal_entry_when_journal_exists(tmp_path: Path) -> None:
    # Arrange — pre-existing journal with content
    journal = _journal(tmp_path)
    journal.parent.mkdir(parents=True, exist_ok=True)
    prior = "# Governance Journal\n\n### 2020-01-01 00:00 — checkpoint\nPRIOR ENTRY\n"
    journal.write_text(prior, encoding="utf-8")

    # Act
    result = _run_script(_hook_json(tmp_path, trigger="auto"))

    # Assert — prior content verbatim + exactly one new entry
    assert result.returncode == 0
    text = journal.read_text(encoding="utf-8")
    assert prior in text
    assert text.count("— compaction") == 1


def test_should_derive_objective_from_last_user_message(tmp_path: Path) -> None:
    # Arrange — transcript whose last user message is "work on X"
    transcript = _write_transcript(
        tmp_path,
        [
            {"type": "user", "message": {"role": "user", "content": "earlier message"}},
            {"type": "assistant", "message": {"role": "assistant", "content": "ok"}},
            {"type": "user", "message": {"role": "user", "content": "work on X"}},
        ],
    )

    # Act
    result = _run_script(_hook_json(tmp_path, transcript_path=str(transcript)))

    # Assert
    assert result.returncode == 0
    content = _checkpoint(tmp_path).read_text(encoding="utf-8")
    assert "work on X" in content


def test_should_use_fallback_objective_when_no_transcript(tmp_path: Path) -> None:
    # Arrange — no transcript_path field at all
    # Act
    result = _run_script(_hook_json(tmp_path))

    # Assert
    assert result.returncode == 0
    content = _checkpoint(tmp_path).read_text(encoding="utf-8")
    assert FALLBACK_OBJECTIVE in content


def test_should_parse_objective_from_content_block_list(tmp_path: Path) -> None:
    # Arrange — content as a list of blocks (the richer shape)
    transcript = _write_transcript(
        tmp_path,
        [
            {
                "type": "user",
                "message": {
                    "role": "user",
                    "content": [{"type": "text", "text": "block-shaped objective"}],
                },
            },
        ],
    )

    # Act
    result = _run_script(_hook_json(tmp_path, transcript_path=str(transcript)))

    # Assert
    assert result.returncode == 0
    content = _checkpoint(tmp_path).read_text(encoding="utf-8")
    assert "block-shaped objective" in content


def test_should_write_only_within_cwd(tmp_path: Path) -> None:
    # Arrange — record the full tree outside .etc_sdlc before running
    sibling = tmp_path / "sibling"
    sibling.mkdir()
    (sibling / "untouched.txt").write_text("keep", encoding="utf-8")

    # Act
    result = _run_script(_hook_json(tmp_path))

    # Assert — only paths under cwd/.etc_sdlc were created
    assert result.returncode == 0
    created = {p for p in tmp_path.rglob("*") if p.is_file()}
    etc_sdlc = tmp_path / ".etc_sdlc"
    for path in created:
        in_etc = etc_sdlc in path.parents
        in_sibling = path == sibling / "untouched.txt"
        assert in_etc or in_sibling, f"unexpected write: {path}"
    assert (sibling / "untouched.txt").read_text(encoding="utf-8") == "keep"


def test_should_exit_zero_when_wrapper_script_missing(tmp_path: Path) -> None:
    # Arrange — run the wrapper with HOME pointing at an empty dir and cwd at a
    # tmp dir with no scripts/, so precompact_checkpoint.py cannot resolve.
    empty_home = tmp_path / "home"
    empty_home.mkdir()
    env = dict(os.environ, HOME=str(empty_home))
    stdin = _hook_json(tmp_path)

    # Act
    result = subprocess.run(
        ["bash", str(WRAPPER)],
        input=stdin,
        capture_output=True,
        text=True,
        timeout=20,
        env=env,
    )

    # Assert — wrapper fail-open
    assert result.returncode == 0


def test_should_register_precompact_gate_in_spec_yaml() -> None:
    # Arrange
    spec = yaml.safe_load((REPO_ROOT / "spec" / "etc_sdlc.yaml").read_text(encoding="utf-8"))

    # Act
    gate = spec["gates"]["precompact-checkpoint"]

    # Assert
    assert gate["event"] == "PreCompact"
    assert gate["on_failure"] == "continue"
    assert gate["script"] == "pre-compact-checkpoint.sh"


def test_should_wire_precompact_in_repo_settings_json() -> None:
    # Arrange
    settings_path = REPO_ROOT / ".claude" / "settings.json"
    settings = json.loads(settings_path.read_text(encoding="utf-8"))

    # Act
    precompact = settings["hooks"]["PreCompact"]

    # Assert
    commands = [h["command"] for entry in precompact for h in entry["hooks"]]
    assert any("pre-compact-checkpoint.sh" in c for c in commands)
