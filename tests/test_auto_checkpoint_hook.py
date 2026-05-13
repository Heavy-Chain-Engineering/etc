"""Tests for hooks/auto-checkpoint.sh.

F012 (2026-05-13). Source: venlink-platform proposal 2026-05-11.

The hook is a Stop hook that blocks session-end when BOTH:
  1. context_window.used_percentage >= CHECKPOINT_CTX_THRESHOLD (default 85)
  2. .etc_sdlc/checkpoint.md mtime > CHECKPOINT_STALE_MINUTES (default 30)
     ago, OR the file is absent

Both conditions met → exit 2 with stderr containing "AUTO-CHECKPOINT REQUIRED".
Either condition unmet → exit 0 silently.

The .context_window.used_percentage field's availability in Stop-hook
input is not formally documented in Anthropic public docs as of 2026-05-13;
the hook safe-fails to exit 0 when the field is absent.
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from typing import Any

HOOK_NAME = "auto-checkpoint.sh"


def _build_input(cwd: Path, ctx_pct: int | None = None) -> dict[str, Any]:
    """Build the Stop-hook JSON input.

    Args:
        cwd: Working directory (controls where .etc_sdlc/checkpoint.md is sought).
        ctx_pct: Context-window used percentage (0-100), or None to omit the field
            entirely (exercises safe-fail behavior).
    """
    payload: dict[str, Any] = {"cwd": str(cwd)}
    if ctx_pct is not None:
        payload["context_window"] = {"used_percentage": ctx_pct}
    return payload


def _write_checkpoint(cwd: Path, *, mtime_age_seconds: int = 0) -> Path:
    """Create a fake checkpoint file under cwd/.etc_sdlc/ with controlled mtime.

    Args:
        cwd: Project root.
        mtime_age_seconds: Number of seconds ago the mtime should be set to.
            0 means "right now"; 3600 means "1 hour ago".

    Returns:
        Path to the created checkpoint file.
    """
    ckpt_dir = cwd / ".etc_sdlc"
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    ckpt = ckpt_dir / "checkpoint.md"
    ckpt.write_text("# fake checkpoint\n")
    if mtime_age_seconds > 0:
        now = time.time()
        target_mtime = now - mtime_age_seconds
        os.utime(ckpt, (target_mtime, target_mtime))
    return ckpt


class TestBelowThreshold:
    """When context utilization is below the threshold, the hook always
    allows the stop — regardless of checkpoint state."""

    def test_should_allow_stop_when_pct_far_below_default_threshold(
        self, run_hook: Any, tmp_path: Path
    ) -> None:
        result = run_hook(HOOK_NAME, _build_input(tmp_path, ctx_pct=5))
        assert result.exit_code == 0
        assert result.stderr == ""

    def test_should_allow_stop_when_pct_just_below_default_threshold(
        self, run_hook: Any, tmp_path: Path
    ) -> None:
        """Default threshold is 85; 84 is just below."""
        result = run_hook(HOOK_NAME, _build_input(tmp_path, ctx_pct=84))
        assert result.exit_code == 0
        assert result.stderr == ""

    def test_should_allow_stop_when_below_threshold_with_missing_checkpoint(
        self, run_hook: Any, tmp_path: Path
    ) -> None:
        """Even with a missing checkpoint, low context does not trigger."""
        result = run_hook(HOOK_NAME, _build_input(tmp_path, ctx_pct=10))
        assert result.exit_code == 0


class TestAboveThresholdFreshCheckpoint:
    """When context utilization is at/above threshold but the checkpoint
    is fresh, the hook allows the stop."""

    def test_should_allow_stop_at_threshold_with_fresh_checkpoint(
        self, run_hook: Any, tmp_path: Path
    ) -> None:
        """85 is the default threshold; >= comparison means 85 fires gate."""
        _write_checkpoint(tmp_path, mtime_age_seconds=0)
        result = run_hook(HOOK_NAME, _build_input(tmp_path, ctx_pct=85))
        assert result.exit_code == 0
        assert result.stderr == ""

    def test_should_allow_stop_well_above_threshold_with_fresh_checkpoint(
        self, run_hook: Any, tmp_path: Path
    ) -> None:
        _write_checkpoint(tmp_path, mtime_age_seconds=60)
        result = run_hook(HOOK_NAME, _build_input(tmp_path, ctx_pct=95))
        assert result.exit_code == 0


class TestAboveThresholdStaleCheckpoint:
    """When context utilization is at/above threshold AND the checkpoint
    is stale (or missing), the hook blocks the stop with exit 2."""

    def test_should_block_stop_when_checkpoint_file_missing(
        self, run_hook: Any, tmp_path: Path
    ) -> None:
        """No .etc_sdlc/checkpoint.md at all → block."""
        result = run_hook(HOOK_NAME, _build_input(tmp_path, ctx_pct=90))
        assert result.exit_code == 2
        assert "AUTO-CHECKPOINT REQUIRED" in result.stderr
        assert "checkpoint file absent" in result.stderr

    def test_should_block_stop_when_checkpoint_stale_by_an_hour(
        self, run_hook: Any, tmp_path: Path
    ) -> None:
        """Default stale threshold is 30 min; 60 min is well past it."""
        _write_checkpoint(tmp_path, mtime_age_seconds=3600)
        result = run_hook(HOOK_NAME, _build_input(tmp_path, ctx_pct=88))
        assert result.exit_code == 2
        assert "AUTO-CHECKPOINT REQUIRED" in result.stderr
        assert "stale" in result.stderr

    def test_should_emit_actual_age_in_blocking_message(
        self, run_hook: Any, tmp_path: Path
    ) -> None:
        """The block message should include the actual mtime age in
        minutes so the operator can see how stale the file is."""
        _write_checkpoint(tmp_path, mtime_age_seconds=3000)  # 50 min
        result = run_hook(HOOK_NAME, _build_input(tmp_path, ctx_pct=92))
        assert result.exit_code == 2
        # Age computation: 3000s / 60 = 50 min. Allow for a +/-1 boundary
        # because integer division and wallclock skew.
        assert "50 minutes stale" in result.stderr or "49 minutes stale" in result.stderr


class TestEnvVarOverrides:
    """Both thresholds are tunable via environment variables. Operator on
    a smaller context window can lower CHECKPOINT_CTX_THRESHOLD."""

    def test_threshold_override_to_lower_value_fires_gate_earlier(
        self, tmp_path: Path
    ) -> None:
        """With CHECKPOINT_CTX_THRESHOLD=20, a 30% utilization fires."""
        import json
        # Bypass the run_hook fixture because we need env var injection.
        # The fixture's subprocess.run inherits parent env; setting via
        # monkeypatch.setenv before calling would work, but bypassing
        # is more explicit about what we're testing.
        hooks_dir = Path(__file__).parent.parent / "hooks"
        env = os.environ.copy()
        env["CHECKPOINT_CTX_THRESHOLD"] = "20"
        payload = {
            "cwd": str(tmp_path),
            "context_window": {"used_percentage": 30},
        }
        result = subprocess.run(
            ["bash", str(hooks_dir / HOOK_NAME)],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            timeout=15,
            env=env,
        )
        assert result.returncode == 2
        assert "AUTO-CHECKPOINT REQUIRED" in result.stderr
        assert "threshold: 20%" in result.stderr

    def test_stale_minutes_override_to_zero_makes_any_checkpoint_stale(
        self, tmp_path: Path
    ) -> None:
        """With CHECKPOINT_STALE_MINUTES=0, even a freshly-touched
        checkpoint is considered stale (any age > 0)."""
        import json
        _write_checkpoint(tmp_path, mtime_age_seconds=60)
        hooks_dir = Path(__file__).parent.parent / "hooks"
        env = os.environ.copy()
        env["CHECKPOINT_STALE_MINUTES"] = "0"
        payload = {
            "cwd": str(tmp_path),
            "context_window": {"used_percentage": 90},
        }
        result = subprocess.run(
            ["bash", str(hooks_dir / HOOK_NAME)],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            timeout=15,
            env=env,
        )
        assert result.returncode == 2
        assert "stale" in result.stderr


class TestSafeFail:
    """When inputs are malformed or fields are absent, the hook must
    fail safely — exit 0 — not loudly fail with non-zero exit."""

    def test_should_allow_stop_when_context_window_field_absent(
        self, run_hook: Any, tmp_path: Path
    ) -> None:
        """Stop-hook input schema may not include .context_window in some
        contexts. The hook's `// 0` default treats absent as 0, which is
        always below threshold, which exits 0."""
        result = run_hook(HOOK_NAME, _build_input(tmp_path, ctx_pct=None))
        assert result.exit_code == 0

    def test_should_allow_stop_when_cwd_field_absent(
        self, run_hook: Any
    ) -> None:
        """If .cwd is absent, the jq default `// "."` falls back to the
        bash CWD. With no checkpoint there, behavior depends on threshold
        check — but with no context_window field, the threshold check
        bails first via safe-fail."""
        result = run_hook(HOOK_NAME, {})
        assert result.exit_code == 0

    def test_should_allow_stop_on_completely_empty_input(
        self, run_hook: Any
    ) -> None:
        """Empty JSON object: both threshold check and cwd lookup default."""
        result = run_hook(HOOK_NAME, {})
        assert result.exit_code == 0
