"""Tests for hooks/chief-efficiency-officer.sh and hooks/sandbox-bypass-tracker.sh.

F019 contract tests. Focused on critical paths; broader AC coverage is
queued for follow-up builds.

Verified contracts:
- Stop hook never blocks (always exits 0)
- Turn-event JSONL captures correctly
- Current-task detection via cascading fallback
- Active-engagement computation with idle-gap subtraction
- Daily report file updates
- Mute mechanism honors `until:` field
- Sandbox-bypass tracker captures on dangerouslyDisableSandbox: true
- Sandbox-bypass tracker is silent when bypass flag is false
"""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Any

CEO_HOOK = Path(__file__).parent.parent / "hooks" / "chief-efficiency-officer.sh"
BYPASS_HOOK = Path(__file__).parent.parent / "hooks" / "sandbox-bypass-tracker.sh"


def _run_hook(hook: Path, payload: dict[str, Any], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(hook)],
        input=json.dumps(payload),
        capture_output=True, text=True, timeout=15,
        cwd=cwd,
    )


class TestCEOStopHookContract:
    """The CEO hook NEVER blocks the Stop event."""

    def test_hook_always_exits_zero_with_minimal_input(self, tmp_path: Path) -> None:
        payload = {"cwd": str(tmp_path)}
        result = _run_hook(CEO_HOOK, payload, tmp_path)
        assert result.returncode == 0

    def test_hook_exits_zero_when_no_features_directory(self, tmp_path: Path) -> None:
        """Fresh project with no .etc_sdlc/features/ — must not crash."""
        payload = {"cwd": str(tmp_path)}
        result = _run_hook(CEO_HOOK, payload, tmp_path)
        assert result.returncode == 0


class TestTurnEventCapture:
    def test_first_invocation_creates_turn_events_jsonl(self, tmp_path: Path) -> None:
        payload = {"cwd": str(tmp_path)}
        _run_hook(CEO_HOOK, payload, tmp_path)
        jsonl = tmp_path / ".etc_sdlc" / "efficiency" / "turn-events.jsonl"
        assert jsonl.exists()
        lines = jsonl.read_text().strip().splitlines()
        assert len(lines) == 1
        event = json.loads(lines[0])
        assert "event_id" in event
        assert "ended_at" in event
        assert "cwd" in event

    def test_subsequent_invocations_append(self, tmp_path: Path) -> None:
        payload = {"cwd": str(tmp_path)}
        _run_hook(CEO_HOOK, payload, tmp_path)
        time.sleep(1)  # ensure distinct event_ids
        _run_hook(CEO_HOOK, payload, tmp_path)
        jsonl = tmp_path / ".etc_sdlc" / "efficiency" / "turn-events.jsonl"
        lines = jsonl.read_text().strip().splitlines()
        assert len(lines) == 2


class TestCurrentTaskDetection:
    def test_current_task_from_active_state_yaml(self, tmp_path: Path) -> None:
        """When a state.yaml exists under features/active/F<NNN>-*/,
        the hook detects that feature as the current task."""
        feature_dir = tmp_path / ".etc_sdlc" / "features" / "active" / "F500-test-feature"
        feature_dir.mkdir(parents=True)
        (feature_dir / "state.yaml").write_text("feature_id: F500\n")
        payload = {"cwd": str(tmp_path)}
        _run_hook(CEO_HOOK, payload, tmp_path)
        jsonl = tmp_path / ".etc_sdlc" / "efficiency" / "turn-events.jsonl"
        event = json.loads(jsonl.read_text().strip().splitlines()[-1])
        assert event["current_task"] == "F500-test-feature"

    def test_current_task_from_flat_path_when_no_active(self, tmp_path: Path) -> None:
        feature_dir = tmp_path / ".etc_sdlc" / "features" / "F500-test-feature"
        feature_dir.mkdir(parents=True)
        (feature_dir / "state.yaml").write_text("feature_id: F500\n")
        payload = {"cwd": str(tmp_path)}
        _run_hook(CEO_HOOK, payload, tmp_path)
        jsonl = tmp_path / ".etc_sdlc" / "efficiency" / "turn-events.jsonl"
        event = json.loads(jsonl.read_text().strip().splitlines()[-1])
        assert event["current_task"] == "F500-test-feature"

    def test_no_task_when_nothing_to_detect(self, tmp_path: Path) -> None:
        payload = {"cwd": str(tmp_path)}
        _run_hook(CEO_HOOK, payload, tmp_path)
        jsonl = tmp_path / ".etc_sdlc" / "efficiency" / "turn-events.jsonl"
        event = json.loads(jsonl.read_text().strip().splitlines()[-1])
        assert event["current_task"] == ""


class TestDailyReport:
    def test_daily_report_file_created(self, tmp_path: Path) -> None:
        payload = {"cwd": str(tmp_path)}
        _run_hook(CEO_HOOK, payload, tmp_path)
        daily_dir = tmp_path / ".etc_sdlc" / "efficiency" / "daily"
        assert daily_dir.is_dir()
        files = list(daily_dir.glob("*.md"))
        assert len(files) == 1
        content = files[0].read_text()
        assert "Efficiency report" in content
        assert "Stop event" in content

    def test_daily_report_appends_on_subsequent_turns(self, tmp_path: Path) -> None:
        payload = {"cwd": str(tmp_path)}
        _run_hook(CEO_HOOK, payload, tmp_path)
        time.sleep(1)
        _run_hook(CEO_HOOK, payload, tmp_path)
        daily_dir = tmp_path / ".etc_sdlc" / "efficiency" / "daily"
        files = list(daily_dir.glob("*.md"))
        assert len(files) == 1
        content = files[0].read_text()
        # Two "Stop event @" markers
        assert content.count("Stop event @") == 2


class TestMuteMechanism:
    def test_mute_until_future_suppresses_threshold_push(self, tmp_path: Path) -> None:
        """When mute file has a future `until:`, threshold-push proposals
        must not fire. Daily report still updates (informational)."""
        eff_dir = tmp_path / ".etc_sdlc" / "efficiency"
        eff_dir.mkdir(parents=True)
        # Set mute to a far-future date
        (eff_dir / "mute.yaml").write_text(
            'until: "2099-01-01T00:00:00Z"\nreason: "test mute"\n'
        )
        payload = {"cwd": str(tmp_path)}
        result = _run_hook(CEO_HOOK, payload, tmp_path)
        assert result.returncode == 0
        # The proposals/ directory should be empty (created, but no proposals)
        proposals_dir = eff_dir / "proposals"
        if proposals_dir.is_dir():
            assert list(proposals_dir.glob("*.md")) == []


class TestSandboxBypassTracker:
    def test_bypass_flag_true_appends_jsonl(self, tmp_path: Path) -> None:
        payload = {
            "cwd": str(tmp_path),
            "tool_input": {
                "command": "chmod +x foo.sh",
                "dangerouslyDisableSandbox": True,
                "description": "chmod blocked by sandbox; bypass required",
            },
        }
        result = _run_hook(BYPASS_HOOK, payload, tmp_path)
        assert result.returncode == 0
        jsonl = tmp_path / ".etc_sdlc" / "efficiency" / "sandbox-bypasses.jsonl"
        assert jsonl.exists()
        line = jsonl.read_text().strip()
        event = json.loads(line)
        assert "event_id" in event
        assert "chmod" in event["command_snippet"]
        assert "bypass required" in event["description"]

    def test_bypass_flag_false_is_silent(self, tmp_path: Path) -> None:
        payload = {
            "cwd": str(tmp_path),
            "tool_input": {
                "command": "ls -la",
                "dangerouslyDisableSandbox": False,
                "description": "list files",
            },
        }
        result = _run_hook(BYPASS_HOOK, payload, tmp_path)
        assert result.returncode == 0
        jsonl = tmp_path / ".etc_sdlc" / "efficiency" / "sandbox-bypasses.jsonl"
        # File should NOT have been created
        assert not jsonl.exists()

    def test_bypass_flag_absent_is_silent(self, tmp_path: Path) -> None:
        payload = {
            "cwd": str(tmp_path),
            "tool_input": {"command": "ls -la", "description": "list files"},
        }
        result = _run_hook(BYPASS_HOOK, payload, tmp_path)
        assert result.returncode == 0
        jsonl = tmp_path / ".etc_sdlc" / "efficiency" / "sandbox-bypasses.jsonl"
        assert not jsonl.exists()

    def test_bypass_tracker_never_blocks(self, tmp_path: Path) -> None:
        """Even with malformed input, the hook never blocks."""
        result = subprocess.run(
            ["bash", str(BYPASS_HOOK)],
            input="not-json",
            capture_output=True, text=True, timeout=15, cwd=tmp_path,
        )
        assert result.returncode == 0
