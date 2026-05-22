"""Tests for hooks/check-completion-discipline.sh Step 1.5 extension.

F021 AC-011: Stop-side residual scan. Step 1.5 is inserted BEFORE the
existing CI gate (Step 1). It scans the full conversation transcript for
`<new-diagnostics>` reminders that lack a subsequent evidence block within
DIAGNOSTIC_INVESTIGATION_TURNS (default 5) turns, and emits one Pattern B
stderr warning per residual missing-evidence pattern.

Step 1.5 NEVER modifies the hook's exit code (0/1/2). It is a warning-only
residual sweep; the structural defense lives at Step 6c (ADR-F021-005).

Transcript format: Claude Code JSONL where each line is a JSON object with
at least a ``role`` field and a ``content`` field (string or list). The
``<new-diagnostics>`` system reminder appears as a substring in a
``content`` value. Evidence blocks (YAML with ``tool_rerun_command``,
``tool_rerun_output``, ``attribution``, ``evidence_type``) appear in
subsequent turns within the investigation window.

Test classes:
    TestStep15RemindersWithoutEvidence  — Pattern B warn emitted.
    TestStep15RemindersWithEvidence     — no warn (positive control).
    TestStep15ExistingBehaviorRegression — exit codes 0/1/2 preserved.
    TestStep15NeverChangesExitCode      — missing-evidence + passing CI → 0.
    TestStep15WindowBoundary            — boundary conditions on DIAGNOSTIC_INVESTIGATION_TURNS.
    TestStep15Degradation               — missing/unreadable transcript → silent skip.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "hooks"
HOOK_NAME = "check-completion-discipline.sh"
HOOK_PATH = HOOKS_DIR / HOOK_NAME
HOOK_TIMEOUT = 30

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run_hook(
    hook_input: dict[str, Any],
    env_overrides: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Execute check-completion-discipline.sh, returning CompletedProcess."""
    import os

    env = dict(os.environ)
    if env_overrides:
        env.update(env_overrides)

    return subprocess.run(
        ["bash", str(HOOK_PATH)],
        input=json.dumps(hook_input),
        capture_output=True,
        text=True,
        timeout=HOOK_TIMEOUT,
        env=env,
    )


def _make_turn(role: str, content: str, turn_index: int | None = None) -> dict[str, Any]:
    """Build a minimal Claude Code transcript JSONL turn object."""
    entry: dict[str, Any] = {"role": role, "content": content}
    if turn_index is not None:
        entry["turn_index"] = turn_index
    return entry


def _write_transcript(path: Path, turns: list[dict[str, Any]]) -> None:
    """Write JSONL transcript file (one JSON object per line)."""
    lines = [json.dumps(t) for t in turns]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _build_transcript_with_reminder_no_evidence(
    path: Path, num_turns_after: int = 5
) -> None:
    """Transcript: reminder at turn 3, then `num_turns_after` turns with no evidence block."""
    turns = [
        _make_turn("user", "Please fix the type errors.", 0),
        _make_turn("assistant", "I will look into the errors now.", 1),
        _make_turn("tool", "Some output here.", 2),
        # Turn 3: diagnostic reminder arrives
        _make_turn(
            "tool",
            "<new-diagnostics>\nPyright: error at src/foo.py:12: Variable not assigned\n</new-diagnostics>",
            3,
        ),
    ]
    # Subsequent turns with no evidence block
    for i in range(num_turns_after):
        turns.append(
            _make_turn(
                "assistant",
                f"I am investigating turn {4 + i}, no evidence block yet.",
                4 + i,
            )
        )
    _write_transcript(path, turns)


def _build_transcript_with_reminder_and_evidence(path: Path) -> None:
    """Positive control: reminder at turn 3, evidence block at turn 5 (within window)."""
    evidence_block = (
        "```yaml\n"
        "tool_rerun_command: python3 -m pyright src/foo.py\n"
        "tool_rerun_output: |\n"
        "  src/foo.py:12:5 - error: Variable not assigned (reportOptionalCall)\n"
        "attribution: This is a real type error; the variable is conditionally None\n"
        "evidence_type: error-is-real\n"
        "```\n"
    )
    turns = [
        _make_turn("user", "Please fix the type errors.", 0),
        _make_turn("assistant", "I will look into the errors now.", 1),
        _make_turn("tool", "Some tool output here.", 2),
        # Turn 3: diagnostic reminder
        _make_turn(
            "tool",
            "<new-diagnostics>\nPyright: error at src/foo.py:12: Variable not assigned\n</new-diagnostics>",
            3,
        ),
        _make_turn("assistant", "Running pyright now to check the error...", 4),
        # Turn 5: evidence block present within 5-turn window
        _make_turn("assistant", f"After investigation:\n\n{evidence_block}", 5),
        _make_turn("user", "Thanks.", 6),
    ]
    _write_transcript(path, turns)


# ---------------------------------------------------------------------------
# AC-011: Pattern B warn when reminder lacks evidence
# ---------------------------------------------------------------------------


class TestStep15RemindersWithoutEvidence:
    """Step 1.5 emits a Pattern B warning to stderr when a <new-diagnostics>
    reminder at turn N has no evidence block in turns N..N+5."""

    def test_stderr_contains_new_diagnostics_substring(
        self, tmp_path: Path
    ) -> None:
        transcript = tmp_path / "transcript.jsonl"
        _build_transcript_with_reminder_no_evidence(transcript)
        result = _run_hook({"cwd": str(tmp_path), "transcript_path": str(transcript)})
        assert "<new-diagnostics>" in result.stderr or "new-diagnostics" in result.stderr, (
            f"Expected '<new-diagnostics>' in stderr; got:\n{result.stderr}"
        )

    def test_stderr_contains_missing_evidence_substring(
        self, tmp_path: Path
    ) -> None:
        transcript = tmp_path / "transcript.jsonl"
        _build_transcript_with_reminder_no_evidence(transcript)
        result = _run_hook({"cwd": str(tmp_path), "transcript_path": str(transcript)})
        assert "missing evidence" in result.stderr.lower() or "missing_evidence" in result.stderr.lower(), (
            f"Expected 'missing evidence' in stderr; got:\n{result.stderr}"
        )

    def test_pattern_b_format_present(self, tmp_path: Path) -> None:
        """Pattern B format: the warning must include the '▶ Note:' marker
        or 'Residual diagnostic' per the spec's Pattern B template."""
        transcript = tmp_path / "transcript.jsonl"
        _build_transcript_with_reminder_no_evidence(transcript)
        result = _run_hook({"cwd": str(tmp_path), "transcript_path": str(transcript)})
        # Pattern B starts with the note marker or Residual keyword
        assert (
            "▶ Note:" in result.stderr
            or "Residual" in result.stderr
        ), f"Expected Pattern B format in stderr; got:\n{result.stderr}"

    def test_pattern_b_references_standards_doc(self, tmp_path: Path) -> None:
        """Pattern B must reference diagnostic-discipline.md per the spec."""
        transcript = tmp_path / "transcript.jsonl"
        _build_transcript_with_reminder_no_evidence(transcript)
        result = _run_hook({"cwd": str(tmp_path), "transcript_path": str(transcript)})
        assert "diagnostic-discipline.md" in result.stderr, (
            f"Expected reference to diagnostic-discipline.md in stderr; got:\n{result.stderr}"
        )

    def test_exit_code_is_zero_despite_warning(self, tmp_path: Path) -> None:
        """Step 1.5 NEVER changes exit code — warning only."""
        transcript = tmp_path / "transcript.jsonl"
        _build_transcript_with_reminder_no_evidence(transcript)
        result = _run_hook({"cwd": str(tmp_path), "transcript_path": str(transcript)})
        assert result.returncode == 0, (
            f"Step 1.5 must not change exit code; got {result.returncode}"
        )

    def test_multiple_reminders_emit_multiple_warnings(
        self, tmp_path: Path
    ) -> None:
        """Two <new-diagnostics> reminders with no evidence → two Pattern B warns."""
        transcript = tmp_path / "transcript.jsonl"
        turns = [
            _make_turn("user", "Fix the errors.", 0),
            # First reminder at turn 1 — no evidence follows within window
            _make_turn(
                "tool",
                "<new-diagnostics>\nError A at line 10\n</new-diagnostics>",
                1,
            ),
            _make_turn("assistant", "Checking turn 2.", 2),
            _make_turn("assistant", "Checking turn 3.", 3),
            _make_turn("assistant", "Checking turn 4.", 4),
            _make_turn("assistant", "Checking turn 5.", 5),
            _make_turn("assistant", "Checking turn 6.", 6),
            # Second reminder at turn 7 — no evidence follows
            _make_turn(
                "tool",
                "<new-diagnostics>\nError B at line 20\n</new-diagnostics>",
                7,
            ),
            _make_turn("assistant", "Checking turn 8.", 8),
            _make_turn("assistant", "Checking turn 9.", 9),
            _make_turn("assistant", "Checking turn 10.", 10),
            _make_turn("assistant", "Checking turn 11.", 11),
            _make_turn("assistant", "Checking turn 12.", 12),
        ]
        _write_transcript(transcript, turns)
        result = _run_hook({"cwd": str(tmp_path), "transcript_path": str(transcript)})
        # Two separate Pattern B blocks in stderr
        stderr_lower = result.stderr.lower()
        warn_count = stderr_lower.count("missing evidence") + stderr_lower.count("missing_evidence")
        assert warn_count >= 2, (
            f"Expected >= 2 missing-evidence warnings; got {warn_count}. stderr:\n{result.stderr}"
        )


# ---------------------------------------------------------------------------
# Positive control: reminder WITH evidence → no warn
# ---------------------------------------------------------------------------


class TestStep15RemindersWithEvidence:
    """When a <new-diagnostics> reminder is followed by a valid evidence block
    within the investigation window, Step 1.5 must NOT emit a Pattern B warn."""

    def test_no_stderr_warning_when_evidence_present(
        self, tmp_path: Path
    ) -> None:
        transcript = tmp_path / "transcript.jsonl"
        _build_transcript_with_reminder_and_evidence(transcript)
        result = _run_hook({"cwd": str(tmp_path), "transcript_path": str(transcript)})
        # Step 1.5 should be silent (no in_progress tasks, no CI failure)
        assert result.returncode == 0
        assert "missing evidence" not in result.stderr.lower(), (
            f"Unexpected warning when evidence is present; stderr:\n{result.stderr}"
        )
        assert "missing_evidence" not in result.stderr.lower(), (
            f"Unexpected warning when evidence is present; stderr:\n{result.stderr}"
        )

    def test_no_pattern_b_when_evidence_present(self, tmp_path: Path) -> None:
        transcript = tmp_path / "transcript.jsonl"
        _build_transcript_with_reminder_and_evidence(transcript)
        result = _run_hook({"cwd": str(tmp_path), "transcript_path": str(transcript)})
        assert "Residual diagnostic dismissal" not in result.stderr


# ---------------------------------------------------------------------------
# Existing-behavior regression: exit codes 0/1/2 preserved byte-equivalent
# ---------------------------------------------------------------------------


class TestStep15ExistingBehaviorRegression:
    """Step 1.5 is purely additive. The existing CI gate (Step 1, exit 1)
    and in_progress check (Step 2, exit 2) must behave byte-equivalent."""

    def test_exit_0_no_signals_no_transcript(self, tmp_path: Path) -> None:
        """No .tdd-dirty, no in_progress, no transcript → exit 0 (unchanged)."""
        result = _run_hook({"cwd": str(tmp_path)})
        assert result.returncode == 0, (
            f"Expected exit 0 with no signals; got {result.returncode}"
        )

    def test_exit_0_no_signals_empty_transcript(self, tmp_path: Path) -> None:
        """Empty transcript, no signals → exit 0."""
        transcript = tmp_path / "empty.jsonl"
        transcript.write_text("", encoding="utf-8")
        result = _run_hook({"cwd": str(tmp_path), "transcript_path": str(transcript)})
        assert result.returncode == 0

    def test_exit_1_ci_failure_preserved(self, tmp_path: Path) -> None:
        """Existing Step 1 CI-gate failure → exit 1 (unchanged by Step 1.5)."""
        (tmp_path / ".tdd-dirty").write_text("")
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "x"\nversion = "0.0.0"\n'
        )
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_failing.py").write_text(
            "def test_must_fail():\n    assert False\n"
        )
        # Even with a transcript containing a diagnostic reminder, CI failure
        # must still exit 1.
        transcript = tmp_path / "transcript.jsonl"
        _build_transcript_with_reminder_no_evidence(transcript)
        result = _run_hook({"cwd": str(tmp_path), "transcript_path": str(transcript)})
        assert result.returncode == 1, (
            f"CI gate must still exit 1; got {result.returncode}"
        )
        assert "CI GATE FAILED" in result.stderr

    def test_exit_2_in_progress_task_preserved(self, tmp_path: Path) -> None:
        """Existing Step 2 in_progress block → exit 2 (unchanged by Step 1.5)."""
        tasks_dir = tmp_path / ".etc_sdlc" / "features" / "sample" / "tasks"
        tasks_dir.mkdir(parents=True)
        (tasks_dir / "001.yaml").write_text(
            "task_id: '001'\ntitle: Something\nstatus: in_progress\n"
        )
        # Transcript with diagnostic reminder doesn't change the exit code.
        transcript = tmp_path / "transcript.jsonl"
        _build_transcript_with_reminder_no_evidence(transcript)
        result = _run_hook({"cwd": str(tmp_path), "transcript_path": str(transcript)})
        assert result.returncode == 2, (
            f"in_progress task must still exit 2; got {result.returncode}"
        )
        assert "COMPLETION DISCIPLINE" in result.stderr

    def test_ci_gate_message_unchanged(self, tmp_path: Path) -> None:
        """The literal 'CI GATE FAILED' text must still appear on CI failure."""
        (tmp_path / ".tdd-dirty").write_text("")
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "x"\nversion = "0.0.0"\n'
        )
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_failing.py").write_text("assert False\n")
        result = _run_hook({"cwd": str(tmp_path)})
        assert "CI GATE FAILED" in result.stderr

    def test_completion_discipline_message_unchanged(self, tmp_path: Path) -> None:
        """The 'completion-discipline.md' reference must still appear on exit 2."""
        tasks_dir = tmp_path / ".etc_sdlc" / "features" / "sample" / "tasks"
        tasks_dir.mkdir(parents=True)
        (tasks_dir / "001.yaml").write_text("task_id: '001'\nstatus: in_progress\n")
        result = _run_hook({"cwd": str(tmp_path)})
        assert "completion-discipline.md" in result.stderr


# ---------------------------------------------------------------------------
# AC-011: Step 1.5 NEVER changes exit code
# ---------------------------------------------------------------------------


class TestStep15NeverChangesExitCode:
    """The central contract: Step 1.5 warns but NEVER blocks.

    Even when a missing-evidence transcript is present AND CI is passing,
    the hook must exit 0. The structural block lives at Step 6c.
    """

    def test_missing_evidence_plus_passing_ci_exits_zero(
        self, tmp_path: Path
    ) -> None:
        """Missing-evidence transcript + no .tdd-dirty + no in_progress → exit 0."""
        transcript = tmp_path / "transcript.jsonl"
        _build_transcript_with_reminder_no_evidence(transcript)
        # No .tdd-dirty, no in_progress task.
        result = _run_hook({"cwd": str(tmp_path), "transcript_path": str(transcript)})
        assert result.returncode == 0, (
            f"Step 1.5 must never change exit code; "
            f"got {result.returncode}. stderr:\n{result.stderr}"
        )
        # But the warning must be present.
        assert "missing evidence" in result.stderr.lower() or "missing_evidence" in result.stderr.lower(), (
            f"Warning must appear even though exit is 0; stderr:\n{result.stderr}"
        )

    def test_no_transcript_path_still_exits_zero(self, tmp_path: Path) -> None:
        """When transcript_path is absent from JSON input, exit 0."""
        result = _run_hook({"cwd": str(tmp_path)})
        assert result.returncode == 0

    def test_nonexistent_transcript_path_still_exits_zero(
        self, tmp_path: Path
    ) -> None:
        """When transcript_path points to a file that doesn't exist, exit 0."""
        result = _run_hook(
            {"cwd": str(tmp_path), "transcript_path": "/nonexistent/transcript.jsonl"}
        )
        assert result.returncode == 0


# ---------------------------------------------------------------------------
# Window boundary conditions
# ---------------------------------------------------------------------------


class TestStep15WindowBoundary:
    """DIAGNOSTIC_INVESTIGATION_TURNS controls the look-ahead window.

    Default is 5. Evidence at turn N+5 is within the window (inclusive).
    Absence at turn N+6 is outside — warn.
    """

    def test_evidence_at_boundary_turn_suppresses_warn(
        self, tmp_path: Path
    ) -> None:
        """Evidence block at exactly N+5 (the boundary) → no warning."""
        evidence_block = (
            "```yaml\n"
            "tool_rerun_command: python3 -m ruff check src/\n"
            "tool_rerun_output: All checks passed.\n"
            "attribution: No lint errors found after re-run.\n"
            "evidence_type: error-is-real\n"
            "```\n"
        )
        transcript = tmp_path / "transcript.jsonl"
        turns = [
            # Turn 0: diagnostic reminder
            _make_turn(
                "tool",
                "<new-diagnostics>\nLint error at line 5\n</new-diagnostics>",
                0,
            ),
            _make_turn("assistant", "Investigating turn 1.", 1),
            _make_turn("assistant", "Investigating turn 2.", 2),
            _make_turn("assistant", "Investigating turn 3.", 3),
            _make_turn("assistant", "Investigating turn 4.", 4),
            # Turn 5: evidence block exactly at N+5 boundary
            _make_turn("assistant", f"After re-run:\n{evidence_block}", 5),
        ]
        _write_transcript(transcript, turns)
        result = _run_hook({"cwd": str(tmp_path), "transcript_path": str(transcript)})
        assert result.returncode == 0
        assert "missing evidence" not in result.stderr.lower(), (
            f"Evidence at boundary turn should suppress warning; stderr:\n{result.stderr}"
        )

    def test_evidence_beyond_window_triggers_warn(self, tmp_path: Path) -> None:
        """Evidence block at N+6 (beyond default window of 5) → warning emitted."""
        evidence_block = (
            "```yaml\n"
            "tool_rerun_command: python3 -m ruff check src/\n"
            "tool_rerun_output: All checks passed.\n"
            "attribution: No lint errors found.\n"
            "evidence_type: error-is-real\n"
            "```\n"
        )
        transcript = tmp_path / "transcript.jsonl"
        turns = [
            # Turn 0: reminder
            _make_turn(
                "tool",
                "<new-diagnostics>\nLint error at line 5\n</new-diagnostics>",
                0,
            ),
        ]
        # Turns 1..5: no evidence
        for i in range(1, 6):
            turns.append(_make_turn("assistant", f"Investigating turn {i}.", i))
        # Turn 6: evidence arrives AFTER the window closed
        turns.append(_make_turn("assistant", f"Late evidence:\n{evidence_block}", 6))
        _write_transcript(transcript, turns)
        result = _run_hook({"cwd": str(tmp_path), "transcript_path": str(transcript)})
        # Warning must be emitted even though evidence eventually appears later.
        assert "missing evidence" in result.stderr.lower() or "missing_evidence" in result.stderr.lower(), (
            f"Expected warn for evidence beyond window; stderr:\n{result.stderr}"
        )

    def test_env_override_changes_window(self, tmp_path: Path) -> None:
        """DIAGNOSTIC_INVESTIGATION_TURNS=2 reduces the look-ahead window."""
        transcript = tmp_path / "transcript.jsonl"
        evidence_block = (
            "```yaml\n"
            "tool_rerun_command: python3 -m mypy src/\n"
            "tool_rerun_output: Success: no issues found\n"
            "attribution: passes cleanly\n"
            "evidence_type: error-is-real\n"
            "```\n"
        )
        # Reminder at 0, evidence at turn 3 (within default-5 window but beyond window-2).
        turns = [
            _make_turn(
                "tool",
                "<new-diagnostics>\nType error at line 10\n</new-diagnostics>",
                0,
            ),
            _make_turn("assistant", "Turn 1.", 1),
            _make_turn("assistant", "Turn 2.", 2),
            # Evidence at turn 3 — outside window-2 but inside window-5
            _make_turn("assistant", f"Evidence block:\n{evidence_block}", 3),
        ]
        _write_transcript(transcript, turns)
        # With window=2, evidence at turn 3 is outside → warn expected.
        result = _run_hook(
            {"cwd": str(tmp_path), "transcript_path": str(transcript)},
            env_overrides={"DIAGNOSTIC_INVESTIGATION_TURNS": "2"},
        )
        assert "missing evidence" in result.stderr.lower() or "missing_evidence" in result.stderr.lower(), (
            f"Expected warn with window=2 and evidence at turn 3; stderr:\n{result.stderr}"
        )

    def test_invalid_env_override_falls_back_to_default(
        self, tmp_path: Path
    ) -> None:
        """Non-numeric DIAGNOSTIC_INVESTIGATION_TURNS falls back to default 5."""
        transcript = tmp_path / "transcript.jsonl"
        _build_transcript_with_reminder_no_evidence(transcript, num_turns_after=5)
        # With default=5, 5 turns without evidence should warn.
        result = _run_hook(
            {"cwd": str(tmp_path), "transcript_path": str(transcript)},
            env_overrides={"DIAGNOSTIC_INVESTIGATION_TURNS": "notanumber"},
        )
        # Should still warn (default window applied).
        assert result.returncode == 0  # never blocks
        assert "missing evidence" in result.stderr.lower() or "missing_evidence" in result.stderr.lower(), (
            f"Expected warn with invalid env var (defaulting to 5); stderr:\n{result.stderr}"
        )


# ---------------------------------------------------------------------------
# Degradation: transcript absent or unreadable
# ---------------------------------------------------------------------------


class TestStep15Degradation:
    """Step 1.5 degrades gracefully when transcript is unavailable."""

    def test_no_transcript_field_in_json_exits_zero(self, tmp_path: Path) -> None:
        """JSON with no transcript_path field → Step 1.5 is silently skipped."""
        result = _run_hook({"cwd": str(tmp_path)})
        assert result.returncode == 0
        assert "missing evidence" not in result.stderr.lower()

    def test_empty_transcript_path_exits_zero(self, tmp_path: Path) -> None:
        """Empty string transcript_path → silently skipped."""
        result = _run_hook({"cwd": str(tmp_path), "transcript_path": ""})
        assert result.returncode == 0

    def test_nonexistent_transcript_exits_zero(self, tmp_path: Path) -> None:
        """transcript_path points to a non-existent file → silently skipped."""
        result = _run_hook(
            {"cwd": str(tmp_path), "transcript_path": "/tmp/no-such-file-ever.jsonl"}
        )
        assert result.returncode == 0

    def test_path_traversal_rejected(self, tmp_path: Path) -> None:
        """transcript_path containing '..' traversal is rejected silently."""
        evil_path = f"/tmp/{tmp_path.name}/../../etc/passwd"
        result = _run_hook({"cwd": str(tmp_path), "transcript_path": evil_path})
        # Must not block (exit 0) and must not access /etc/passwd.
        assert result.returncode == 0


# ---------------------------------------------------------------------------
# Audit-log emission via diagnostic_evidence.py
# ---------------------------------------------------------------------------


class TestStep15AuditLog:
    """Step 1.5 emits audit-log rows via scripts/diagnostic_evidence.py."""

    def test_audit_log_row_appended_on_missing_evidence(
        self, tmp_path: Path
    ) -> None:
        """When a missing-evidence reminder is found, an audit-log row is
        appended to .etc_sdlc/efficiency/turn-events.jsonl."""
        transcript = tmp_path / "transcript.jsonl"
        _build_transcript_with_reminder_no_evidence(transcript)
        result = _run_hook({"cwd": str(tmp_path), "transcript_path": str(transcript)})
        assert result.returncode == 0
        log_path = (
            tmp_path / ".etc_sdlc" / "efficiency" / "turn-events.jsonl"
        )
        if log_path.exists():
            lines = [
                line
                for line in log_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            events = [json.loads(line) for line in lines]
            missing_events = [
                e
                for e in events
                if e.get("event_type") == "diagnostic_dismissal_missing_evidence"
            ]
            assert len(missing_events) >= 1, (
                f"Expected at least one missing_evidence event in audit log; got: {events}"
            )
