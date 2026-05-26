#!/usr/bin/env python3
"""precompact_checkpoint.py — best-effort checkpoint writer for /compact.

F-2026-05-26-compact-autocheckpoint (#36). etc's first PreCompact hook.

Invoked by hooks/pre-compact-checkpoint.sh with the Claude Code PreCompact
hook JSON on stdin. Writes (or refreshes) a best-effort
`<cwd>/.etc_sdlc/checkpoint.md` and always appends one entry to
`<cwd>/.etc_sdlc/journal.md`, then exits 0.

Design constraints:
  - Fail-OPEN: exit 0 in ALL paths (malformed input, missing transcript,
    state-collection failure). Never block compaction (exit 2 is forbidden).
  - Reads/writes only within the hook-provided `cwd`. No ~/.claude writes,
    no network.
  - Freshness guard: if a model-written checkpoint is younger than
    FRESH_MINUTES, it is richer than anything this script can produce, so
    it is preserved untouched.

Stdlib only.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

DEFAULT_FRESH_MINUTES = 5
OBJECTIVE_MAX_CHARS = 200
FALLBACK_OBJECTIVE = "(auto-captured at compaction; objective not derived)"
TASKS_UNAVAILABLE_NOTE = (
    "_Task state was unavailable (tasks.py missing or errored); "
    "checkpoint written without a task table._"
)
NOT_REASONED_NOTE = (
    "- _(auto-captured: the hook cannot reason over the session; "
    "run /checkpoint for a model-reasoned checkpoint)_"
)
JOURNAL_HEADER = (
    "# Governance Journal\n\n"
    "Append-only log of checkpoints, decisions, and phase transitions.\n"
)
SECTION_HEADINGS: tuple[str, ...] = (
    "## Task Status",
    "## Decisions Made This Session",
    "## Discovered Context",
    "## Pending Items",
)


def fresh_minutes() -> int:
    """Read the freshness window from the environment, defaulting to 5."""
    raw = os.environ.get("CHECKPOINT_FRESH_MINUTES")
    if raw is None:
        return DEFAULT_FRESH_MINUTES
    try:
        return int(raw)
    except ValueError:
        return DEFAULT_FRESH_MINUTES


def is_checkpoint_fresh(checkpoint_path: Path, now: float) -> bool:
    """Return True when the checkpoint exists and is younger than the window."""
    if not checkpoint_path.exists():
        return False
    age_seconds = now - checkpoint_path.stat().st_mtime
    return age_seconds < fresh_minutes() * 60


def _block_text(content: object) -> str:
    """Extract text from a single content block (dict or str)."""
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        text = content.get("text")
        if isinstance(text, str):
            return text
    return ""


def _message_text(content: object) -> str:
    """Flatten a user message's content (string OR list of blocks) to text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [_block_text(block) for block in content]
        return " ".join(part for part in parts if part)
    return ""


def derive_objective(transcript_path: str | None) -> str:
    """Derive the Objective from the last user message in the transcript.

    Falls back to FALLBACK_OBJECTIVE when the transcript is missing,
    unreadable, or contains no user message.
    """
    if not transcript_path:
        return FALLBACK_OBJECTIVE
    path = Path(transcript_path)
    if not path.is_file():
        return FALLBACK_OBJECTIVE
    last_user_text = ""
    try:
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(record, dict) or record.get("type") != "user":
                continue
            message = record.get("message")
            content = message.get("content") if isinstance(message, dict) else None
            text = _message_text(content).strip()
            if text:
                last_user_text = text
    except OSError:
        return FALLBACK_OBJECTIVE
    if not last_user_text:
        return FALLBACK_OBJECTIVE
    return last_user_text[:OBJECTIVE_MAX_CHARS]


def collect_task_status(cwd: Path) -> str | None:
    """Collect task status via tasks.py, or None when unavailable."""
    tasks_script = Path.home() / ".claude" / "scripts" / "tasks.py"
    if not tasks_script.is_file():
        return None
    try:
        result = subprocess.run(
            ["python3", str(tasks_script), "status"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(cwd),
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    output = result.stdout.strip()
    return output or None


def git_head_sha(cwd: Path) -> str | None:
    """Return the short HEAD SHA, or None when git is unavailable."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(cwd),
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    sha = result.stdout.strip()
    return sha or None


def render_checkpoint(
    objective: str,
    trigger: str,
    task_status: str | None,
    head_sha: str | None,
) -> str:
    """Render the auto-captured checkpoint markdown."""
    saved = datetime.now().strftime("%Y-%m-%d %H:%M")
    sha_line = head_sha if head_sha else "unavailable"
    lines = [
        "# Session Checkpoint",
        "",
        f"**Saved:** {saved}",
        f"**Objective:** {objective}",
        "**SDLC Phase:** not initialized",
        "",
        f"_AUTO-captured by the PreCompact hook (trigger: {trigger}). "
        "Best-effort; run /checkpoint for a richer model-reasoned checkpoint._",
        f"_Git HEAD: {sha_line}_",
        "",
        "## Task Status",
        "",
    ]
    if task_status:
        lines.append("```")
        lines.append(task_status)
        lines.append("```")
    else:
        lines.append(TASKS_UNAVAILABLE_NOTE)
    lines.extend(
        [
            "",
            "## Decisions Made This Session",
            "",
            NOT_REASONED_NOTE,
            "",
            "## Discovered Context",
            "",
            NOT_REASONED_NOTE,
            "",
            "## Pending Items",
            "",
            NOT_REASONED_NOTE,
            "",
        ]
    )
    return "\n".join(lines)


def append_journal(journal_path: Path, trigger: str, action: str) -> None:
    """Append exactly one journal entry, preserving prior bytes."""
    if not journal_path.exists():
        journal_path.write_text(JOURNAL_HEADER, encoding="utf-8")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    entry = (
        f"\n### {timestamp} — compaction\n"
        f"Auto-checkpoint on /compact (trigger: {trigger}). "
        f"Checkpoint {action}.\n"
    )
    with journal_path.open("a", encoding="utf-8") as handle:
        handle.write(entry)


def write_checkpoint(cwd: Path, trigger: str, transcript_path: str | None) -> str:
    """Write or preserve the checkpoint; return the action taken."""
    etc_sdlc = cwd / ".etc_sdlc"
    etc_sdlc.mkdir(parents=True, exist_ok=True)
    checkpoint_path = etc_sdlc / "checkpoint.md"
    journal_path = etc_sdlc / "journal.md"

    if is_checkpoint_fresh(checkpoint_path, now=datetime.now().timestamp()):
        append_journal(journal_path, trigger, "PRESERVED (fresh checkpoint already present)")
        return "preserved"

    objective = derive_objective(transcript_path)
    task_status = collect_task_status(cwd)
    head_sha = git_head_sha(cwd)
    checkpoint_path.write_text(
        render_checkpoint(objective, trigger, task_status, head_sha),
        encoding="utf-8",
    )
    append_journal(journal_path, trigger, "WRITTEN")
    return "written"


def run(stdin_text: str) -> int:
    """Parse the hook JSON and run the checkpoint writer. Always returns 0."""
    try:
        payload = json.loads(stdin_text)
    except (json.JSONDecodeError, ValueError):
        print(
            "precompact_checkpoint: malformed hook JSON on stdin; "
            "skipping checkpoint (compaction proceeds).",
            file=sys.stderr,
        )
        return 0
    if not isinstance(payload, dict):
        print(
            "precompact_checkpoint: hook JSON was not an object; skipping checkpoint.",
            file=sys.stderr,
        )
        return 0
    cwd = Path(str(payload.get("cwd", ".")))
    trigger = str(payload.get("trigger", "unknown"))
    transcript = payload.get("transcript_path")
    transcript_path = transcript if isinstance(transcript, str) else None
    try:
        write_checkpoint(cwd, trigger, transcript_path)
    except OSError as error:
        print(
            f"precompact_checkpoint: checkpoint write failed ({error}); "
            "compaction proceeds.",
            file=sys.stderr,
        )
    return 0


def main() -> int:
    """Read stdin and run; never raises out of this boundary."""
    try:
        stdin_text = sys.stdin.read()
    except (OSError, ValueError):
        stdin_text = ""
    return run(stdin_text)


if __name__ == "__main__":
    sys.exit(main())
