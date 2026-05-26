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

import importlib.util
import json
import os
import string
import subprocess
import time
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "precompact_checkpoint.py"
WRAPPER = REPO_ROOT / "hooks" / "pre-compact-checkpoint.sh"
TEMPLATE = REPO_ROOT / "templates" / "checkpoint.md.tmpl"
FALLBACK_OBJECTIVE = "(auto-captured at compaction; objective not derived)"
AUTO_SIGNATURE = "_AUTO-captured by the PreCompact hook"


def _load_module() -> object:
    spec = importlib.util.spec_from_file_location("precompact_checkpoint", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _hook_json(
    cwd: Path,
    *,
    trigger: str = "auto",
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
    # Arrange — auto trigger writes the floor (manual now goes through the gate)
    stdin = _hook_json(tmp_path, trigger="auto")

    # Act
    result = _run_script(stdin)

    # Assert
    assert result.returncode == 0
    content = _checkpoint(tmp_path).read_text(encoding="utf-8")
    assert "# Session Checkpoint" in content
    assert "**Saved:**" in content
    assert "auto" in content
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
    # The gate now has an intentional exit-2 block path (manual-compact forcing
    # gate). on_failure is descriptive metadata only — the compiler does not
    # wrap the command exit code — so it reflects the block path it can take.
    assert gate["on_failure"] == "block"
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


# --- F-2026-05-26-checkpoint-template-and-gate (content half) ---


def test_should_exist_as_valid_string_template_when_template_loaded() -> None:
    # Arrange / Act
    raw = TEMPLATE.read_text(encoding="utf-8")

    # Assert — parses as string.Template input (no malformed $)
    identifiers = string.Template(raw).get_identifiers()
    assert "# Session Checkpoint" in raw
    expected = {
        "saved",
        "objective",
        "phase",
        "trigger",
        "head_sha",
        "task_status",
        "decisions",
        "discovered",
        "pending",
    }
    assert expected.issubset(set(identifiers))


def test_should_contain_four_sections_when_template_loaded() -> None:
    # Arrange / Act
    raw = TEMPLATE.read_text(encoding="utf-8")

    # Assert
    assert "## Task Status" in raw
    assert "## Decisions Made This Session" in raw
    assert "## Discovered Context" in raw
    assert "## Pending Items" in raw


def test_should_carry_auto_signature_when_floor_rendered_from_template(
    tmp_path: Path,
) -> None:
    # Arrange
    stdin = _hook_json(tmp_path, trigger="auto")

    # Act
    result = _run_script(stdin)

    # Assert
    assert result.returncode == 0
    content = _checkpoint(tmp_path).read_text(encoding="utf-8")
    assert AUTO_SIGNATURE in content
    assert "## Task Status" in content
    assert "## Pending Items" in content


def test_should_use_fallback_structure_when_template_absent(tmp_path: Path) -> None:
    # Arrange — a fake templates dir without checkpoint.md.tmpl, isolated copy
    fake_root = tmp_path / "install"
    (fake_root / "scripts").mkdir(parents=True)
    (fake_root / "templates").mkdir(parents=True)
    script_copy = fake_root / "scripts" / "precompact_checkpoint.py"
    script_copy.write_text(SCRIPT.read_text(encoding="utf-8"), encoding="utf-8")
    project = tmp_path / "project"
    project.mkdir()
    stdin = _hook_json(project, trigger="auto")

    # Act
    result = subprocess.run(
        ["python3", str(script_copy)],
        input=stdin,
        capture_output=True,
        text=True,
        timeout=20,
    )

    # Assert — fail-open: checkpoint still produced via embedded fallback
    assert result.returncode == 0
    content = (project / ".etc_sdlc" / "checkpoint.md").read_text(encoding="utf-8")
    assert "# Session Checkpoint" in content
    assert "## Task Status" in content
    assert "template unavailable" in content.lower()


def test_should_render_reasoned_path_without_auto_signature() -> None:
    # Arrange
    module = _load_module()

    # Act
    rendered = module.render_from_template(  # type: ignore[attr-defined]
        objective="do the thing",
        trigger="manual",
        task_status=None,
        head_sha="abc1234",
        reasoned=True,
    )

    # Assert
    assert AUTO_SIGNATURE not in rendered
    assert "# Session Checkpoint" in rendered


def test_should_skip_acknowledgment_and_return_directive_when_deriving_objective(
    tmp_path: Path,
) -> None:
    # Arrange
    module = _load_module()
    transcript = _write_transcript(
        tmp_path,
        [
            {"type": "user", "message": {"role": "user", "content": "do #35, #38, and #36"}},
            {"type": "user", "message": {"role": "user", "content": "Ahhhhh... got it."}},
        ],
    )

    # Act
    objective = module.derive_objective(str(transcript))  # type: ignore[attr-defined]

    # Assert
    assert objective == "do #35, #38, and #36"


def test_should_return_fallback_when_all_messages_are_acknowledgments(
    tmp_path: Path,
) -> None:
    # Arrange
    module = _load_module()
    transcript = _write_transcript(
        tmp_path,
        [
            {"type": "user", "message": {"role": "user", "content": "ok"}},
            {"type": "user", "message": {"role": "user", "content": "got it"}},
            {"type": "user", "message": {"role": "user", "content": "thanks!"}},
            {"type": "user", "message": {"role": "user", "content": "👍"}},
        ],
    )

    # Act
    objective = module.derive_objective(str(transcript))  # type: ignore[attr-defined]

    # Assert
    assert objective == FALLBACK_OBJECTIVE


def test_should_skip_slash_command_only_line_when_deriving_objective(
    tmp_path: Path,
) -> None:
    # Arrange
    module = _load_module()
    transcript = _write_transcript(
        tmp_path,
        [
            {"type": "user", "message": {"role": "user", "content": "refactor the parser"}},
            {"type": "user", "message": {"role": "user", "content": "/compact"}},
        ],
    )

    # Act
    objective = module.derive_objective(str(transcript))  # type: ignore[attr-defined]

    # Assert
    assert objective == "refactor the parser"


def test_should_truncate_objective_after_selection(tmp_path: Path) -> None:
    # Arrange
    module = _load_module()
    long_directive = "build " + "x" * 500
    transcript = _write_transcript(
        tmp_path,
        [{"type": "user", "message": {"role": "user", "content": long_directive}}],
    )

    # Act
    objective = module.derive_objective(str(transcript))  # type: ignore[attr-defined]

    # Assert
    assert len(objective) == module.OBJECTIVE_MAX_CHARS  # type: ignore[attr-defined]


# --- F-2026-05-26-checkpoint-template-and-gate (control half: forcing gate) ---

BLOCK_MESSAGE = (
    "Manual /compact blocked: no fresh checkpoint. Run /checkpoint to capture "
    "goals/decisions/intentions, then /compact again."
)


def _write_reasoned_checkpoint(cwd: Path, *, age_seconds: float = 60) -> Path:
    # A fresh, model-reasoned checkpoint: lacks the auto-capture signature.
    checkpoint = _checkpoint(cwd)
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    checkpoint.write_text(
        "# Session Checkpoint\n\n**Saved:** now\n_Checkpoint captured (trigger: manual)._\n"
        "RICH MODEL-REASONED CONTENT\n",
        encoding="utf-8",
    )
    mtime = time.time() - age_seconds
    os.utime(checkpoint, (mtime, mtime))
    return checkpoint


def _write_floor_checkpoint(cwd: Path, *, age_seconds: float = 60) -> Path:
    # A floor checkpoint carries the auto-capture signature (not reasoned).
    checkpoint = _checkpoint(cwd)
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    checkpoint.write_text(
        f"# Session Checkpoint\n\n**Saved:** now\n{AUTO_SIGNATURE} (trigger: auto)._\n",
        encoding="utf-8",
    )
    mtime = time.time() - age_seconds
    os.utime(checkpoint, (mtime, mtime))
    return checkpoint


def test_should_allow_manual_compact_when_fresh_reasoned_checkpoint_exists(
    tmp_path: Path,
) -> None:
    # Arrange — fresh AND reasoned checkpoint present
    checkpoint = _write_reasoned_checkpoint(tmp_path)
    original = checkpoint.read_text(encoding="utf-8")

    # Act
    result = _run_script(_hook_json(tmp_path, trigger="manual"))

    # Assert — allowed (exit 0), checkpoint preserved, journal refreshed
    assert result.returncode == 0
    assert checkpoint.read_text(encoding="utf-8") == original
    assert _journal(tmp_path).read_text(encoding="utf-8").count("— compaction") == 1


def test_should_block_manual_compact_when_no_fresh_reasoned_checkpoint(
    tmp_path: Path,
) -> None:
    # Arrange — no checkpoint at all
    # Act
    result = _run_script(_hook_json(tmp_path, trigger="manual"))

    # Assert — blocked (exit 2), message to stderr, no checkpoint written
    assert result.returncode == 2
    assert BLOCK_MESSAGE in result.stderr
    assert not _checkpoint(tmp_path).exists()


def test_should_block_manual_compact_when_only_floor_checkpoint_exists(
    tmp_path: Path,
) -> None:
    # Arrange — a fresh but NOT-reasoned (floor) checkpoint
    checkpoint = _write_floor_checkpoint(tmp_path)
    original = checkpoint.read_text(encoding="utf-8")

    # Act
    result = _run_script(_hook_json(tmp_path, trigger="manual"))

    # Assert — floor does not satisfy the gate; blocked, not overwritten
    assert result.returncode == 2
    assert checkpoint.read_text(encoding="utf-8") == original


def test_should_block_manual_compact_when_reasoned_checkpoint_is_stale(
    tmp_path: Path,
) -> None:
    # Arrange — a reasoned checkpoint but 30 minutes old (not fresh)
    _write_reasoned_checkpoint(tmp_path, age_seconds=1800)

    # Act
    result = _run_script(_hook_json(tmp_path, trigger="manual"))

    # Assert — staleness fails the gate
    assert result.returncode == 2
    assert BLOCK_MESSAGE in result.stderr


def test_should_emit_block_message_verbatim_when_manual_compact_blocked(
    tmp_path: Path,
) -> None:
    # Arrange / Act
    result = _run_script(_hook_json(tmp_path, trigger="manual"))

    # Assert — exact greppable string (AC-004)
    assert BLOCK_MESSAGE in result.stderr


def test_should_warn_and_write_floor_when_gate_env_is_warn(tmp_path: Path) -> None:
    # Arrange — no reasoned checkpoint, escape hatch engaged (case-insensitive)
    env = dict(os.environ, ETC_PRECOMPACT_GATE="WaRn")

    # Act
    result = subprocess.run(
        ["python3", str(SCRIPT)],
        input=_hook_json(tmp_path, trigger="manual"),
        capture_output=True,
        text=True,
        timeout=20,
        env=env,
    )

    # Assert — exit 0, floor written, warning (not block message)
    assert result.returncode == 0
    assert BLOCK_MESSAGE not in result.stderr
    assert result.stderr.strip() != ""
    content = _checkpoint(tmp_path).read_text(encoding="utf-8")
    assert AUTO_SIGNATURE in content


def test_should_block_when_gate_env_is_other_value(tmp_path: Path) -> None:
    # Arrange — any non-warn value falls back to default blocking
    env = dict(os.environ, ETC_PRECOMPACT_GATE="off")

    # Act
    result = subprocess.run(
        ["python3", str(SCRIPT)],
        input=_hook_json(tmp_path, trigger="manual"),
        capture_output=True,
        text=True,
        timeout=20,
        env=env,
    )

    # Assert
    assert result.returncode == 2
    assert BLOCK_MESSAGE in result.stderr


def test_should_never_block_when_trigger_is_auto(tmp_path: Path) -> None:
    # Arrange — auto trigger, no checkpoint at all
    # Act
    result = _run_script(_hook_json(tmp_path, trigger="auto"))

    # Assert — floor written, exit 0, never 2 (AC-007)
    assert result.returncode == 0
    content = _checkpoint(tmp_path).read_text(encoding="utf-8")
    assert AUTO_SIGNATURE in content


def test_should_never_block_when_trigger_is_unknown(tmp_path: Path) -> None:
    # Arrange — unknown/absent trigger
    # Act
    result = _run_script(_hook_json(tmp_path, trigger="something-else"))

    # Assert — floor written, exit 0
    assert result.returncode == 0
    assert _checkpoint(tmp_path).exists()


def test_should_propagate_child_exit_code_through_wrapper(tmp_path: Path) -> None:
    # Arrange — a repo-local copy of the script the wrapper resolves from cwd,
    # with a manual trigger and no fresh reasoned checkpoint (so it blocks).
    block_dir = tmp_path / "block_root"
    (block_dir / "scripts").mkdir(parents=True)
    (block_dir / "scripts" / "precompact_checkpoint.py").write_text(
        SCRIPT.read_text(encoding="utf-8"), encoding="utf-8"
    )
    (block_dir / "templates").mkdir()
    (block_dir / "templates" / "checkpoint.md.tmpl").write_text(
        TEMPLATE.read_text(encoding="utf-8"), encoding="utf-8"
    )
    stdin = _hook_json(block_dir, trigger="manual")

    # Act
    result = subprocess.run(
        ["bash", str(WRAPPER)],
        input=stdin,
        capture_output=True,
        text=True,
        timeout=20,
        env=dict(os.environ),
    )

    # Assert — wrapper must NOT swallow the child's exit 2
    assert result.returncode == 2
    assert BLOCK_MESSAGE in result.stderr
