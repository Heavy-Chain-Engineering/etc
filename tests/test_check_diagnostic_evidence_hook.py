"""Integration tests for hooks/check-diagnostic-evidence.sh (F021 AC-011).

PreToolUse hook: reads transcript_path from Claude Code JSON stdin, scans
the last DIAGNOSTIC_INVESTIGATION_TURNS (default 5) entries backward for
``<new-diagnostics>`` system reminders, invokes
scripts/diagnostic_evidence.py::validate_block on subsequent turns to check
whether an evidence block exists, emits Pattern B stderr warning on missing
evidence, and appends an audit-log row to
``<cwd>/.etc_sdlc/efficiency/turn-events.jsonl``.

Hook ALWAYS exits 0 (never blocks). All failure paths degrade gracefully.

Transcript JSONL format (Claude Code): one JSON object per line.  System
reminder entries have ``"type": "system"`` and a ``"content"`` string that
contains the ``<new-diagnostics>`` tag when new diagnostics surfaced.
Assistant response entries have ``"type": "assistant"`` and a ``"content"``
list (or string) with the agent's response text.

TDD order: tests written first, run RED, then hook implemented to GREEN.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOK_PATH = REPO_ROOT / "hooks" / "check-diagnostic-evidence.sh"
HOOK_TIMEOUT = 15  # seconds


# ── Transcript helpers ────────────────────────────────────────────────────


def _system_reminder(content: str) -> dict[str, Any]:
    """Build a system-reminder transcript entry containing `<new-diagnostics>`."""
    return {"type": "system", "content": f"<new-diagnostics>{content}</new-diagnostics>"}


def _assistant_turn(text: str) -> dict[str, Any]:
    """Build an assistant response transcript entry."""
    return {"type": "assistant", "content": text}


def _user_turn(text: str) -> dict[str, Any]:
    """Build a user message transcript entry."""
    return {"type": "user", "content": text}


def _valid_evidence_block() -> str:
    """Return assistant response text that embeds a valid evidence block."""
    return (
        "I re-ran the type-checker and confirmed the following.\n"
        "```yaml\n"
        'tool_rerun_command: "uv run mypy scripts/foo.py"\n'
        'tool_rerun_output: "Success: no issues found in 1 source file"\n'
        'attribution: "IDE was running stale mypy 1.10; CLI is 1.14"\n'
        "evidence_type: interpreter-diff\n"
        "```\n"
    )


def _write_transcript(path: Path, entries: list[dict[str, Any]]) -> None:
    """Write a JSONL transcript file from a list of entry dicts."""
    lines = [json.dumps(entry) for entry in entries]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _audit_log_path(cwd: Path) -> Path:
    """Return the audit-log path for a given cwd."""
    return cwd / ".etc_sdlc" / "efficiency" / "turn-events.jsonl"


def _run_hook(
    tmp_path: Path,
    transcript_path: Path | None,
    tool_name: str = "Edit",
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run the hook, piping the Claude Code PreToolUse JSON to stdin."""
    hook_input: dict[str, Any] = {
        "tool_name": tool_name,
        "tool_input": {"file_path": str(tmp_path / "src" / "foo.py")},
        "cwd": str(tmp_path),
    }
    if transcript_path is not None:
        hook_input["transcript_path"] = str(transcript_path)

    env: dict[str, str] | None = None
    if extra_env:
        import os

        env = {**os.environ, **extra_env}

    return subprocess.run(
        ["bash", str(HOOK_PATH)],
        input=json.dumps(hook_input),
        capture_output=True,
        text=True,
        timeout=HOOK_TIMEOUT,
        env=env,
        cwd=str(REPO_ROOT),  # so python3 scripts/diagnostic_evidence.py resolves
    )


# ── Structural preconditions ──────────────────────────────────────────────


def test_hook_file_exists() -> None:
    """Trivial: the hook script must exist before tests run."""
    assert HOOK_PATH.is_file(), f"Hook not found at {HOOK_PATH}"


# ── AC-011: Pattern B warning on missing evidence ─────────────────────────


class TestPatternBWarningOnMissingEvidence:
    """When a <new-diagnostics> reminder is within the investigation window
    and no evidence block follows it, the hook emits a Pattern B stderr
    warning and exits 0.
    """

    def test_should_emit_pattern_b_warning_when_reminder_lacks_evidence_block(
        self, tmp_path: Path
    ) -> None:
        """Main positive case: reminder at turn N, N+1 and N+2 are plain
        assistant turns (no evidence block), within the 5-turn window.
        """
        transcript = tmp_path / "transcript.jsonl"
        entries = [
            _user_turn("Run mypy"),
            _system_reminder("mypy found 3 errors"),
            _assistant_turn("These are likely host-env false positives."),
            _assistant_turn("Continuing with the next edit."),
        ]
        _write_transcript(transcript, entries)

        result = _run_hook(tmp_path, transcript)

        assert result.returncode == 0, f"Hook must always exit 0; got {result.returncode}"
        assert "Note" in result.stderr or "▶" in result.stderr, (
            f"Pattern B warning not found in stderr:\n{result.stderr}"
        )
        assert "<new-diagnostics>" in result.stderr, (
            f"Pattern B warning must name '<new-diagnostics>' in stderr:\n{result.stderr}"
        )

    def test_should_warn_when_reminder_at_last_position_in_window(
        self, tmp_path: Path
    ) -> None:
        """Reminder is the most-recent entry in the transcript — investigation
        window incomplete (EC-001 path). Still emits Pattern B.
        """
        transcript = tmp_path / "transcript.jsonl"
        entries = [
            _user_turn("Let's go"),
            _assistant_turn("Working on it."),
            _system_reminder("3 new lint errors"),
        ]
        _write_transcript(transcript, entries)

        result = _run_hook(tmp_path, transcript)

        assert result.returncode == 0
        assert "<new-diagnostics>" in result.stderr

    def test_should_warn_for_each_unresolved_reminder_in_window(
        self, tmp_path: Path
    ) -> None:
        """Multiple <new-diagnostics> reminders within the 5-turn window
        each without evidence blocks → warning must mention the reminder.
        """
        transcript = tmp_path / "transcript.jsonl"
        entries = [
            _system_reminder("error batch A"),
            _assistant_turn("That's just noise."),
            _system_reminder("error batch B"),
            _assistant_turn("Also noise."),
        ]
        _write_transcript(transcript, entries)

        result = _run_hook(tmp_path, transcript)

        assert result.returncode == 0
        assert "<new-diagnostics>" in result.stderr

    def test_should_include_tool_name_in_pattern_b_warning(
        self, tmp_path: Path
    ) -> None:
        """Pattern B warning must name the triggering tool."""
        transcript = tmp_path / "transcript.jsonl"
        entries = [
            _system_reminder("2 type errors"),
            _assistant_turn("Seems like tooling drift."),
        ]
        _write_transcript(transcript, entries)

        result = _run_hook(tmp_path, transcript, tool_name="Write")

        assert result.returncode == 0
        # Tool name appears in warning
        assert "Write" in result.stderr

    def test_should_not_warn_when_reminder_is_outside_investigation_window(
        self, tmp_path: Path
    ) -> None:
        """A <new-diagnostics> reminder more than DIAGNOSTIC_INVESTIGATION_TURNS
        (default 5) turns before the current position is out of window and
        must NOT trigger a warning.
        """
        transcript = tmp_path / "transcript.jsonl"
        # Reminder at position 0; 6 subsequent turns push it out of the 5-turn window
        entries = [
            _system_reminder("old error"),
            _assistant_turn("Turn 1 after reminder"),
            _assistant_turn("Turn 2"),
            _assistant_turn("Turn 3"),
            _assistant_turn("Turn 4"),
            _assistant_turn("Turn 5"),
            _assistant_turn("Turn 6 — reminder now out of window"),
        ]
        _write_transcript(transcript, entries)

        result = _run_hook(tmp_path, transcript)

        assert result.returncode == 0
        assert "<new-diagnostics>" not in result.stderr, (
            f"Reminder was outside window but warning still emitted:\n{result.stderr}"
        )


# ── AC-011: No warning when evidence block present ────────────────────────


class TestNoWarningWhenEvidenceBlockPresent:
    """When a <new-diagnostics> reminder is followed by a valid evidence
    block within the investigation window, no Pattern B warning is emitted.
    """

    def test_should_not_warn_when_reminder_followed_by_valid_evidence_block(
        self, tmp_path: Path
    ) -> None:
        """Negative test: transcript with reminder at N, evidence block at N+1."""
        transcript = tmp_path / "transcript.jsonl"
        entries = [
            _user_turn("Run mypy"),
            _system_reminder("mypy found 3 errors"),
            _assistant_turn(_valid_evidence_block()),
            _assistant_turn("Fixed the issue."),
        ]
        _write_transcript(transcript, entries)

        result = _run_hook(tmp_path, transcript)

        assert result.returncode == 0
        assert "<new-diagnostics>" not in result.stderr, (
            f"No warning expected (evidence block present) but got:\n{result.stderr}"
        )

    def test_should_not_warn_when_no_reminders_in_transcript(
        self, tmp_path: Path
    ) -> None:
        """Transcript with no <new-diagnostics> → no warning, exit 0."""
        transcript = tmp_path / "transcript.jsonl"
        entries = [
            _user_turn("Let's build"),
            _assistant_turn("Starting work."),
            _assistant_turn("Done."),
        ]
        _write_transcript(transcript, entries)

        result = _run_hook(tmp_path, transcript)

        assert result.returncode == 0
        assert "<new-diagnostics>" not in result.stderr


# ── AC-003: Audit-log emission ────────────────────────────────────────────


class TestAuditLogEmission:
    """Hook emits one JSONL row per dismissal event to the audit log."""

    def test_should_append_missing_evidence_row_when_no_evidence_block(
        self, tmp_path: Path
    ) -> None:
        """When reminder lacks evidence, audit log gets
        `diagnostic_dismissal_missing_evidence` row.
        """
        transcript = tmp_path / "transcript.jsonl"
        entries = [
            _system_reminder("mypy: 2 errors"),
            _assistant_turn("Host-env false positive."),
        ]
        _write_transcript(transcript, entries)

        result = _run_hook(tmp_path, transcript)

        assert result.returncode == 0
        log = _audit_log_path(tmp_path)
        assert log.is_file(), f"Audit log not written to {log}"

        rows = [json.loads(line) for line in log.read_text().splitlines() if line.strip()]
        event_types = [r.get("event_type") for r in rows]
        assert "diagnostic_dismissal_missing_evidence" in event_types, (
            f"Expected diagnostic_dismissal_missing_evidence in audit rows; got {event_types}"
        )

    def test_should_append_with_evidence_row_when_evidence_block_present(
        self, tmp_path: Path
    ) -> None:
        """When reminder is followed by valid evidence block, audit log gets
        `diagnostic_dismissal_with_evidence` row.
        """
        transcript = tmp_path / "transcript.jsonl"
        entries = [
            _system_reminder("mypy: 2 errors"),
            _assistant_turn(_valid_evidence_block()),
        ]
        _write_transcript(transcript, entries)

        result = _run_hook(tmp_path, transcript)

        assert result.returncode == 0
        log = _audit_log_path(tmp_path)
        assert log.is_file(), f"Audit log not written to {log}"

        rows = [json.loads(line) for line in log.read_text().splitlines() if line.strip()]
        event_types = [r.get("event_type") for r in rows]
        assert "diagnostic_dismissal_with_evidence" in event_types, (
            f"Expected diagnostic_dismissal_with_evidence in audit rows; got {event_types}"
        )

    def test_audit_row_has_required_fields(
        self, tmp_path: Path
    ) -> None:
        """Each audit row must contain `ts`, `event_type`, and `decision`."""
        transcript = tmp_path / "transcript.jsonl"
        entries = [
            _system_reminder("type errors"),
            _assistant_turn("Probably noise."),
        ]
        _write_transcript(transcript, entries)

        _run_hook(tmp_path, transcript)

        log = _audit_log_path(tmp_path)
        rows = [json.loads(line) for line in log.read_text().splitlines() if line.strip()]
        assert len(rows) >= 1
        row = rows[0]
        assert "ts" in row, f"Row missing 'ts': {row}"
        assert "event_type" in row, f"Row missing 'event_type': {row}"
        assert "decision" in row, f"Row missing 'decision': {row}"


# ── AC-004: Graceful degradation ─────────────────────────────────────────


class TestGracefulDegradation:
    """Hook always exits 0 and degrades gracefully on pathological inputs."""

    def test_should_exit_0_when_transcript_path_missing_from_input(
        self, tmp_path: Path
    ) -> None:
        """transcript_path absent from JSON → silent exit 0."""
        result = _run_hook(tmp_path, transcript_path=None)

        assert result.returncode == 0

    def test_should_exit_0_when_transcript_file_does_not_exist(
        self, tmp_path: Path
    ) -> None:
        """transcript_path provided but file is gone → exit 0, possible warn."""
        missing = tmp_path / "nonexistent_transcript.jsonl"
        result = _run_hook(tmp_path, transcript_path=missing)

        assert result.returncode == 0

    def test_should_exit_0_when_transcript_is_empty(
        self, tmp_path: Path
    ) -> None:
        """Empty transcript → exit 0, no warning."""
        transcript = tmp_path / "transcript.jsonl"
        transcript.write_text("")

        result = _run_hook(tmp_path, transcript)

        assert result.returncode == 0

    def test_should_exit_0_when_transcript_contains_invalid_json_lines(
        self, tmp_path: Path
    ) -> None:
        """Transcript with malformed JSONL lines → hook skips them, exits 0."""
        transcript = tmp_path / "transcript.jsonl"
        transcript.write_text(
            'not-json\n{"type":"user","content":"hello"}\nalso not json\n',
            encoding="utf-8",
        )

        result = _run_hook(tmp_path, transcript)

        assert result.returncode == 0

    def test_should_reject_transcript_path_with_dotdot_traversal(
        self, tmp_path: Path
    ) -> None:
        """Security: transcript_path containing '..' must be rejected silently (exit 0)."""
        import json as _json

        hook_input = {
            "tool_name": "Edit",
            "tool_input": {"file_path": str(tmp_path / "src" / "foo.py")},
            "cwd": str(tmp_path),
            "transcript_path": "/tmp/../etc/passwd",
        }
        result = subprocess.run(
            ["bash", str(HOOK_PATH)],
            input=_json.dumps(hook_input),
            capture_output=True,
            text=True,
            timeout=HOOK_TIMEOUT,
            cwd=str(REPO_ROOT),
        )
        assert result.returncode == 0


# ── Environment variable: DIAGNOSTIC_INVESTIGATION_TURNS ─────────────────


class TestInvestigationWindowOverride:
    """DIAGNOSTIC_INVESTIGATION_TURNS env var controls the lookback window."""

    def test_should_warn_when_window_set_to_2_and_reminder_within_2_turns(
        self, tmp_path: Path
    ) -> None:
        """Window=2: reminder at N, N+1 plain turn → within window → warn."""
        transcript = tmp_path / "transcript.jsonl"
        entries = [
            _system_reminder("2 errors"),
            _assistant_turn("Just noise."),
        ]
        _write_transcript(transcript, entries)

        result = _run_hook(
            tmp_path, transcript, extra_env={"DIAGNOSTIC_INVESTIGATION_TURNS": "2"}
        )

        assert result.returncode == 0
        assert "<new-diagnostics>" in result.stderr

    def test_should_not_warn_when_window_set_to_1_and_reminder_2_turns_back(
        self, tmp_path: Path
    ) -> None:
        """Window=1: reminder 2 turns back → out of window → no warn."""
        transcript = tmp_path / "transcript.jsonl"
        entries = [
            _system_reminder("errors"),
            _assistant_turn("Turn 1"),
            _assistant_turn("Turn 2 — reminder out of window=1"),
        ]
        _write_transcript(transcript, entries)

        result = _run_hook(
            tmp_path, transcript, extra_env={"DIAGNOSTIC_INVESTIGATION_TURNS": "1"}
        )

        assert result.returncode == 0
        assert "<new-diagnostics>" not in result.stderr

    def test_should_sanitize_non_numeric_investigation_turns_and_use_default(
        self, tmp_path: Path
    ) -> None:
        """Non-numeric DIAGNOSTIC_INVESTIGATION_TURNS → fall back to default 5."""
        transcript = tmp_path / "transcript.jsonl"
        entries = [
            _system_reminder("errors"),
            _assistant_turn("Noise."),
        ]
        _write_transcript(transcript, entries)

        result = _run_hook(
            tmp_path,
            transcript,
            extra_env={"DIAGNOSTIC_INVESTIGATION_TURNS": "not-a-number"},
        )

        # Should still work (uses default 5); reminder is within window → warn
        assert result.returncode == 0
        assert "<new-diagnostics>" in result.stderr
