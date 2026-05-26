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
import string
import subprocess
import sys
from datetime import datetime
from pathlib import Path

DEFAULT_FRESH_MINUTES = 5
OBJECTIVE_MAX_CHARS = 200
FALLBACK_OBJECTIVE = "(auto-captured at compaction; objective not derived)"
TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "templates" / "checkpoint.md.tmpl"
AUTO_SIGNATURE_PREFIX = "_AUTO-captured by the PreCompact hook"
GATE_ENV_VAR = "ETC_PRECOMPACT_GATE"
GATE_WARN_MODE = "warn"
MANUAL_TRIGGER = "manual"
BLOCK_EXIT_CODE = 2
BLOCK_MESSAGE = (
    "Manual /compact blocked: no fresh checkpoint. Run /checkpoint to capture "
    "goals/decisions/intentions, then /compact again."
)
WARN_MESSAGE = (
    "precompact_checkpoint: no fresh reasoned checkpoint, but "
    f"{GATE_ENV_VAR}={GATE_WARN_MODE} — writing the floor and allowing "
    "compaction. Run /checkpoint for a reasoned ledger."
)
# Normalized acknowledgments that are NOT substantive operator directives.
ACKNOWLEDGMENT_STOP_LIST: frozenset[str] = frozenset(
    {
        "ok",
        "okay",
        "k",
        "kk",
        "got it",
        "gotit",
        "thanks",
        "thank you",
        "ty",
        "yep",
        "yes",
        "no",
        "sure",
        "sounds good",
        "continue",
        "go",
        "go ahead",
        "do it",
        "perfect",
        "great",
        "nice",
        "cool",
        "lgtm",
        "ack",
        "👍",
    }
)
EMBEDDED_FALLBACK_TEMPLATE = (
    "# Session Checkpoint\n"
    "\n"
    "**Saved:** $saved\n"
    "**Objective:** $objective\n"
    "**SDLC Phase:** $phase\n"
    "\n"
    "$trigger\n"
    "_Git HEAD: ${head_sha}_\n"
    "_(checkpoint template unavailable; rendered from embedded fallback structure)_\n"
    "\n"
    "## Task Status\n"
    "\n"
    "$task_status\n"
    "\n"
    "## Decisions Made This Session\n"
    "\n"
    "$decisions\n"
    "\n"
    "## Discovered Context\n"
    "\n"
    "$discovered\n"
    "\n"
    "## Pending Items\n"
    "\n"
    "$pending\n"
)
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


def is_checkpoint_reasoned(checkpoint_path: Path) -> bool:
    """Return True when the checkpoint is model-reasoned, not the auto floor.

    A checkpoint is reasoned iff it does NOT contain the auto-capture
    signature the floor always writes (BR-004 / D2). A missing or unreadable
    checkpoint is treated as not reasoned.
    """
    try:
        content = checkpoint_path.read_text(encoding="utf-8")
    except OSError:
        return False
    return AUTO_SIGNATURE_PREFIX not in content


def is_gate_in_warn_mode() -> bool:
    """Return True when the operator escape hatch ETC_PRECOMPACT_GATE=warn is set."""
    raw = os.environ.get(GATE_ENV_VAR)
    if raw is None:
        return False
    return raw.strip().lower() == GATE_WARN_MODE


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


_TRAILING_PUNCTUATION = " .!?,;:…"


def _normalize_for_stop_list(text: str) -> str:
    """Lowercase and strip surrounding whitespace and trailing punctuation."""
    return text.strip().lower().rstrip(_TRAILING_PUNCTUATION)


def _stop_list_candidates(text: str) -> list[str]:
    """Yield normalized forms to test against the stop-list.

    Includes the whole normalized message and the trailing clause after an
    ellipsis-delimited interjection, so "Ahhhhh... got it." resolves to the
    acknowledgment "got it".
    """
    normalized = _normalize_for_stop_list(text)
    candidates = [normalized]
    if "..." in normalized or "…" in normalized:
        tail = normalized.replace("…", "...").rsplit("...", 1)[-1].strip(_TRAILING_PUNCTUATION)
        candidates.append(tail)
    return candidates


def _is_substantive(text: str) -> bool:
    """Return True when a user message is a real directive, not an ack/command."""
    candidates = _stop_list_candidates(text)
    if not candidates[0]:
        return False
    if any(candidate in ACKNOWLEDGMENT_STOP_LIST for candidate in candidates):
        return False
    return not text.strip().startswith("/")


def _collect_user_messages(transcript_path: str) -> list[str]:
    """Return all non-empty user message texts in transcript order, oldest first."""
    path = Path(transcript_path)
    if not path.is_file():
        return []
    messages: list[str] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    for raw_line in lines:
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
            messages.append(text)
    return messages


def derive_objective(transcript_path: str | None) -> str:
    """Derive the Objective from the last *substantive* user message.

    Walks user messages newest-to-oldest and returns the first that is
    substantive (non-empty after normalization, not in the acknowledgment
    stop-list, not a slash-command-only line). Falls back to
    FALLBACK_OBJECTIVE when the transcript is missing, unreadable, or holds
    no substantive message. Truncation to OBJECTIVE_MAX_CHARS applies after
    selection.
    """
    if not transcript_path:
        return FALLBACK_OBJECTIVE
    for text in reversed(_collect_user_messages(transcript_path)):
        if _is_substantive(text):
            return text[:OBJECTIVE_MAX_CHARS]
    return FALLBACK_OBJECTIVE


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


def _load_template() -> string.Template:
    """Load the canonical checkpoint template, or the embedded fallback."""
    try:
        raw = TEMPLATE_PATH.read_text(encoding="utf-8")
    except OSError:
        return string.Template(EMBEDDED_FALLBACK_TEMPLATE)
    return string.Template(raw)


def _task_status_block(task_status: str | None) -> str:
    """Render the Task Status section body."""
    if task_status:
        return f"```\n{task_status}\n```"
    return TASKS_UNAVAILABLE_NOTE


def _trigger_line(trigger: str, reasoned: bool) -> str:
    """Render the trigger/provenance line.

    The auto (floor) path carries the auto-capture signature; the reasoned
    path does not, so the gate's richness check (BR-004) can tell them apart.
    """
    if reasoned:
        return f"_Checkpoint captured (trigger: {trigger})._"
    return (
        f"{AUTO_SIGNATURE_PREFIX} (trigger: {trigger}). "
        "Best-effort; run /checkpoint for a richer model-reasoned checkpoint._"
    )


def render_from_template(
    objective: str,
    trigger: str,
    task_status: str | None,
    head_sha: str | None,
    reasoned: bool = False,
) -> str:
    """Render a checkpoint from the canonical template via safe_substitute.

    The auto (floor) path passes reasoned=False so the output carries the
    auto-capture signature and the not-reasoned placeholders.
    """
    template = _load_template()
    note = "_(reasoned content goes here)_" if reasoned else NOT_REASONED_NOTE
    return template.safe_substitute(
        saved=datetime.now().strftime("%Y-%m-%d %H:%M"),
        objective=objective,
        phase="not initialized",
        trigger=_trigger_line(trigger, reasoned),
        head_sha=head_sha if head_sha else "unavailable",
        task_status=_task_status_block(task_status),
        decisions=note,
        discovered=note,
        pending=note,
    )


def render_checkpoint(
    objective: str,
    trigger: str,
    task_status: str | None,
    head_sha: str | None,
) -> str:
    """Render the auto-captured (floor) checkpoint markdown from the template."""
    return render_from_template(objective, trigger, task_status, head_sha, reasoned=False)


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


def has_fresh_reasoned_checkpoint(cwd: Path) -> bool:
    """Return True when a fresh AND reasoned checkpoint exists (gate predicate)."""
    checkpoint_path = cwd / ".etc_sdlc" / "checkpoint.md"
    if not is_checkpoint_fresh(checkpoint_path, now=datetime.now().timestamp()):
        return False
    return is_checkpoint_reasoned(checkpoint_path)


def manual_gate(cwd: Path, trigger: str, transcript_path: str | None) -> int:
    """Apply the manual-compact forcing gate (BR-002). Returns the exit code.

    Allows (and refreshes the journal) when a fresh reasoned checkpoint
    exists; otherwise blocks with exit 2 — unless the operator escape hatch
    ETC_PRECOMPACT_GATE=warn downgrades the block to a floor write + warning.
    """
    if has_fresh_reasoned_checkpoint(cwd):
        write_checkpoint(cwd, trigger, transcript_path)
        return 0
    if is_gate_in_warn_mode():
        print(WARN_MESSAGE, file=sys.stderr)
        write_checkpoint(cwd, trigger, transcript_path)
        return 0
    print(BLOCK_MESSAGE, file=sys.stderr)
    return BLOCK_EXIT_CODE


def run(stdin_text: str) -> int:
    """Parse the hook JSON and run the checkpoint writer.

    Returns 0 in every path except the one intentional manual-block path
    (BR-002), which returns 2. All uncontrolled errors stay fail-open.
    """
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
        if trigger == MANUAL_TRIGGER:
            return manual_gate(cwd, trigger, transcript_path)
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
