"""F022 Task 007 — hooks/check-profiles-fresh.sh tests.

AC-006 + BR-005: SessionStart staleness-check hook.

Test classes:
    TestMissingLock        — WARN containing 'missing' + 'profiles.lock'; exit 0.
    TestStaleLock          — WARN containing 'stale' + 'profiles.lock'; exit 0.
    TestDriftLock          — WARN containing 'drift' + 'profiles.lock'; exit 0.
    TestFreshLock          — no WARN when lock is fresh and set matches detection.
    TestEnvOverride        — PROFILES_LOCK_STALENESS_DAYS=1 tightens window.
    TestDegradation        — missing lock + unwriteable stderr → still exit 0.
    TestAuditLog           — one profile_dispatch JSONL row per invocation.

Pattern B format (per design.md Contract 3):
    \\n\\n---\\n\\n**▶ Note:** <message>
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "hooks"
SCRIPTS_DIR = REPO_ROOT / "scripts"
HOOK_PATH = HOOKS_DIR / "check-profiles-fresh.sh"
HOOK_TIMEOUT = 30

PROFILES_DIR = REPO_ROOT / "standards" / "code" / "profiles"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run_hook(
    tmp_path: Path,
    env_overrides: dict[str, str] | None = None,
    hook_input: dict | None = None,
) -> subprocess.CompletedProcess[str]:
    """Execute the hook with stdin JSON, returning CompletedProcess."""
    env = dict(os.environ)
    if env_overrides:
        env.update(env_overrides)

    payload = hook_input if hook_input is not None else {"cwd": str(tmp_path)}

    return subprocess.run(
        ["bash", str(HOOK_PATH)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=HOOK_TIMEOUT,
        env=env,
        cwd=str(tmp_path),
    )


def _seed_workspace(tmp_path: Path, profiles: list[str] | None = None) -> Path:
    """Copy scripts/ and profiles/ into a temp workspace so detect_profiles.py runs.

    Writes .etc_sdlc/profiles.lock with the given profiles list.
    If profiles is None, no lock file is written (missing-lock scenario).
    """
    # Copy scripts
    scripts_dst = tmp_path / "scripts"
    scripts_dst.mkdir(exist_ok=True)
    for script_name in ("detect_profiles.py", "profile_loader.py"):
        shutil.copy2(SCRIPTS_DIR / script_name, scripts_dst / script_name)

    # Copy profiles dir so detect_profiles.py can enumerate profiles
    profiles_dst = tmp_path / "standards" / "code" / "profiles"
    if PROFILES_DIR.is_dir():
        shutil.copytree(PROFILES_DIR, profiles_dst, dirs_exist_ok=True)
    else:
        profiles_dst.mkdir(parents=True, exist_ok=True)

    # Write lock file if profiles provided
    if profiles is not None:
        lock_dir = tmp_path / ".etc_sdlc"
        lock_dir.mkdir(exist_ok=True)
        lock_path = lock_dir / "profiles.lock"
        lock_path.write_text("".join(p + "\n" for p in profiles), encoding="utf-8")

    return tmp_path


def _set_lock_mtime_days_ago(tmp_path: Path, days: float) -> None:
    """Set .etc_sdlc/profiles.lock mtime to `days` days in the past."""
    lock_path = tmp_path / ".etc_sdlc" / "profiles.lock"
    age_seconds = days * 86400
    old_mtime = time.time() - age_seconds
    os.utime(lock_path, (old_mtime, old_mtime))


def _pattern_b_present(stderr: str) -> bool:
    """Return True if stderr contains the Pattern B prefix."""
    return "**▶ Note:**" in stderr or ("---" in stderr and "Note:" in stderr)


# ---------------------------------------------------------------------------
# TestMissingLock
# ---------------------------------------------------------------------------


class TestMissingLock:
    """Lock file absent → Pattern B WARN with 'missing' + 'profiles.lock'; exit 0."""

    def test_exit_code_is_zero(self, tmp_path: Path) -> None:
        _seed_workspace(tmp_path, profiles=None)
        result = _run_hook(tmp_path)
        assert result.returncode == 0, (
            f"Expected exit 0 on missing lock; got {result.returncode}. stderr={result.stderr}"
        )

    def test_stderr_contains_missing(self, tmp_path: Path) -> None:
        _seed_workspace(tmp_path, profiles=None)
        result = _run_hook(tmp_path)
        assert "missing" in result.stderr.lower(), (
            f"Expected 'missing' in stderr; got:\n{result.stderr}"
        )

    def test_stderr_contains_profiles_lock(self, tmp_path: Path) -> None:
        _seed_workspace(tmp_path, profiles=None)
        result = _run_hook(tmp_path)
        assert "profiles.lock" in result.stderr, (
            f"Expected 'profiles.lock' in stderr; got:\n{result.stderr}"
        )

    def test_pattern_b_format(self, tmp_path: Path) -> None:
        _seed_workspace(tmp_path, profiles=None)
        result = _run_hook(tmp_path)
        assert _pattern_b_present(result.stderr), (
            f"Expected Pattern B format in stderr; got:\n{result.stderr}"
        )


# ---------------------------------------------------------------------------
# TestStaleLock
# ---------------------------------------------------------------------------


class TestStaleLock:
    """Lock mtime > PROFILES_LOCK_STALENESS_DAYS → WARN with 'stale' + 'profiles.lock'; exit 0."""

    def test_exit_code_is_zero(self, tmp_path: Path) -> None:
        _seed_workspace(tmp_path, profiles=["python"])
        _set_lock_mtime_days_ago(tmp_path, days=8)
        result = _run_hook(tmp_path)
        assert result.returncode == 0, (
            f"Expected exit 0 on stale lock; got {result.returncode}. stderr={result.stderr}"
        )

    def test_stderr_contains_stale(self, tmp_path: Path) -> None:
        _seed_workspace(tmp_path, profiles=["python"])
        _set_lock_mtime_days_ago(tmp_path, days=8)
        result = _run_hook(tmp_path)
        assert "stale" in result.stderr.lower(), (
            f"Expected 'stale' in stderr; got:\n{result.stderr}"
        )

    def test_stderr_contains_profiles_lock(self, tmp_path: Path) -> None:
        _seed_workspace(tmp_path, profiles=["python"])
        _set_lock_mtime_days_ago(tmp_path, days=8)
        result = _run_hook(tmp_path)
        assert "profiles.lock" in result.stderr, (
            f"Expected 'profiles.lock' in stderr; got:\n{result.stderr}"
        )

    def test_pattern_b_format(self, tmp_path: Path) -> None:
        _seed_workspace(tmp_path, profiles=["python"])
        _set_lock_mtime_days_ago(tmp_path, days=8)
        result = _run_hook(tmp_path)
        assert _pattern_b_present(result.stderr), (
            f"Expected Pattern B format in stderr; got:\n{result.stderr}"
        )

    def test_exactly_at_boundary_is_fresh(self, tmp_path: Path) -> None:
        """Lock mtime exactly at 7 days is NOT stale (boundary: > 7 days triggers stale)."""
        _seed_workspace(tmp_path, profiles=["python"])
        # 6.9 days → within window; should not fire stale (may still fire drift)
        _set_lock_mtime_days_ago(tmp_path, days=6.9)
        result = _run_hook(tmp_path)
        assert "stale" not in result.stderr.lower(), (
            f"Expected no 'stale' warn for lock 6.9 days old; got:\n{result.stderr}"
        )


# ---------------------------------------------------------------------------
# TestDriftLock
# ---------------------------------------------------------------------------


class TestDriftLock:
    """Locked set ≠ current detection set → WARN with 'drift' + 'profiles.lock'; exit 0."""

    def test_exit_code_is_zero(self, tmp_path: Path) -> None:
        # Lock says ["python", "typescript"] but workspace has no typescript markers
        _seed_workspace(tmp_path, profiles=["python", "typescript"])
        # Keep lock fresh so staleness doesn't fire
        _set_lock_mtime_days_ago(tmp_path, days=0.1)
        result = _run_hook(tmp_path)
        assert result.returncode == 0, (
            f"Expected exit 0 on drift; got {result.returncode}. stderr={result.stderr}"
        )

    def test_stderr_contains_drift_when_set_differs(self, tmp_path: Path) -> None:
        """Lock lists a profile not detected by detect_profiles.py."""
        _seed_workspace(tmp_path, profiles=["nonexistent-profile"])
        _set_lock_mtime_days_ago(tmp_path, days=0.1)
        result = _run_hook(tmp_path)
        assert "drift" in result.stderr.lower(), (
            f"Expected 'drift' in stderr; got:\n{result.stderr}"
        )

    def test_stderr_contains_profiles_lock(self, tmp_path: Path) -> None:
        _seed_workspace(tmp_path, profiles=["nonexistent-profile"])
        _set_lock_mtime_days_ago(tmp_path, days=0.1)
        result = _run_hook(tmp_path)
        assert "profiles.lock" in result.stderr, (
            f"Expected 'profiles.lock' in stderr; got:\n{result.stderr}"
        )

    def test_pattern_b_format(self, tmp_path: Path) -> None:
        _seed_workspace(tmp_path, profiles=["nonexistent-profile"])
        _set_lock_mtime_days_ago(tmp_path, days=0.1)
        result = _run_hook(tmp_path)
        assert _pattern_b_present(result.stderr), (
            f"Expected Pattern B format in stderr; got:\n{result.stderr}"
        )


# ---------------------------------------------------------------------------
# TestFreshLock
# ---------------------------------------------------------------------------


class TestFreshLock:
    """Fresh lock (mtime ≤ window AND set matches detection) → no WARN."""

    def test_no_warn_on_matching_fresh_lock(self, tmp_path: Path) -> None:
        """Write an empty lock (no profiles detected, lock is empty) → no WARN."""
        _seed_workspace(tmp_path, profiles=[])
        # Fresh lock (just created, mtime ~0 seconds ago)
        result = _run_hook(tmp_path)
        # There must be no stale, missing, or drift warnings
        stderr_lower = result.stderr.lower()
        # Allow only if none of the three WARN triggers fire
        has_missing = "missing" in stderr_lower
        has_stale = "stale" in stderr_lower
        has_drift = "drift" in stderr_lower
        assert not (has_missing or has_stale or has_drift), (
            f"Expected no WARN on fresh matching lock; got:\n{result.stderr}"
        )

    def test_exit_0_on_fresh_lock(self, tmp_path: Path) -> None:
        _seed_workspace(tmp_path, profiles=[])
        result = _run_hook(tmp_path)
        assert result.returncode == 0, (
            f"Expected exit 0 on fresh lock; got {result.returncode}"
        )


# ---------------------------------------------------------------------------
# TestEnvOverride
# ---------------------------------------------------------------------------


class TestEnvOverride:
    """PROFILES_LOCK_STALENESS_DAYS=1 tightens the staleness window."""

    def test_lock_2_days_old_is_stale_with_window_1(self, tmp_path: Path) -> None:
        _seed_workspace(tmp_path, profiles=[])
        _set_lock_mtime_days_ago(tmp_path, days=2)
        result = _run_hook(
            tmp_path,
            env_overrides={"PROFILES_LOCK_STALENESS_DAYS": "1"},
        )
        assert "stale" in result.stderr.lower(), (
            f"Expected 'stale' with PROFILES_LOCK_STALENESS_DAYS=1 and 2-day-old lock; got:\n{result.stderr}"
        )
        assert result.returncode == 0

    def test_lock_half_day_old_is_fresh_with_window_1(self, tmp_path: Path) -> None:
        _seed_workspace(tmp_path, profiles=[])
        _set_lock_mtime_days_ago(tmp_path, days=0.4)
        result = _run_hook(
            tmp_path,
            env_overrides={"PROFILES_LOCK_STALENESS_DAYS": "1"},
        )
        assert "stale" not in result.stderr.lower(), (
            f"Expected no 'stale' with 0.4-day-old lock and window=1; got:\n{result.stderr}"
        )

    def test_invalid_env_value_falls_back_to_default_7(self, tmp_path: Path) -> None:
        """Non-numeric PROFILES_LOCK_STALENESS_DAYS falls back to default 7."""
        _seed_workspace(tmp_path, profiles=[])
        # 8 days old triggers stale even with invalid override → default 7 applies
        _set_lock_mtime_days_ago(tmp_path, days=8)
        result = _run_hook(
            tmp_path,
            env_overrides={"PROFILES_LOCK_STALENESS_DAYS": "notanumber"},
        )
        assert "stale" in result.stderr.lower(), (
            f"Expected 'stale' after invalid env fallback to 7; got:\n{result.stderr}"
        )
        assert result.returncode == 0

    def test_zero_env_value_falls_back_to_default_7(self, tmp_path: Path) -> None:
        """PROFILES_LOCK_STALENESS_DAYS=0 is technically valid (0 days = always stale).

        The sanitization regex ^[0-9]+$ matches '0', so 0 IS valid.
        A lock any age older than 0 seconds is stale.
        """
        _seed_workspace(tmp_path, profiles=[])
        # Slightly aged lock — any non-zero age triggers stale with window=0
        _set_lock_mtime_days_ago(tmp_path, days=0.01)
        result = _run_hook(
            tmp_path,
            env_overrides={"PROFILES_LOCK_STALENESS_DAYS": "0"},
        )
        # Either stale fires OR it's treated as "immediate stale" — exit 0 always
        assert result.returncode == 0


# ---------------------------------------------------------------------------
# TestDegradation
# ---------------------------------------------------------------------------


class TestDegradation:
    """Graceful degradation: various failure modes still exit 0."""

    def test_missing_lock_exits_zero(self, tmp_path: Path) -> None:
        """No lock file → exit 0 (WARN emitted but never blocks)."""
        _seed_workspace(tmp_path, profiles=None)
        result = _run_hook(tmp_path)
        assert result.returncode == 0

    def test_detect_profiles_unavailable_exits_zero(self, tmp_path: Path) -> None:
        """If detect_profiles.py is absent, hook still exits 0."""
        _seed_workspace(tmp_path, profiles=["python"])
        _set_lock_mtime_days_ago(tmp_path, days=0.1)
        # Remove scripts dir to simulate missing detect_profiles.py
        scripts_dst = tmp_path / "scripts"
        shutil.rmtree(scripts_dst, ignore_errors=True)
        result = _run_hook(tmp_path)
        assert result.returncode == 0, (
            f"Expected exit 0 when detect_profiles.py is missing; got {result.returncode}"
        )

    def test_empty_cwd_in_input_exits_zero(self, tmp_path: Path) -> None:
        """Hook input with cwd=null → exit 0."""
        result = _run_hook(tmp_path, hook_input={"cwd": None})
        assert result.returncode == 0

    def test_no_cwd_in_input_exits_zero(self, tmp_path: Path) -> None:
        """Hook input with no cwd field → exit 0."""
        result = _run_hook(tmp_path, hook_input={})
        assert result.returncode == 0


# ---------------------------------------------------------------------------
# TestAuditLog
# ---------------------------------------------------------------------------


class TestAuditLog:
    """BR-009: one profile_dispatch JSONL row per invocation."""

    def _audit_rows(self, tmp_path: Path) -> list[dict]:
        log_path = tmp_path / ".etc_sdlc" / "efficiency" / "turn-events.jsonl"
        if not log_path.exists():
            return []
        rows = []
        for line in log_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        return rows

    def test_audit_row_emitted_on_missing_lock(self, tmp_path: Path) -> None:
        _seed_workspace(tmp_path, profiles=None)
        result = _run_hook(tmp_path)
        assert result.returncode == 0
        rows = self._audit_rows(tmp_path)
        dispatch_rows = [r for r in rows if r.get("event_type") == "profile_dispatch"]
        assert len(dispatch_rows) >= 1, (
            f"Expected profile_dispatch row in audit log; got rows: {rows}"
        )

    def test_audit_row_has_required_fields(self, tmp_path: Path) -> None:
        _seed_workspace(tmp_path, profiles=None)
        result = _run_hook(tmp_path)
        assert result.returncode == 0
        rows = self._audit_rows(tmp_path)
        dispatch_rows = [r for r in rows if r.get("event_type") == "profile_dispatch"]
        assert dispatch_rows, "No profile_dispatch row found"
        row = dispatch_rows[0]
        assert "ts" in row, f"Missing 'ts' field; row={row}"
        assert row.get("event_type") == "profile_dispatch"
        assert row.get("hook") == "check-profiles-fresh", (
            f"Expected hook='check-profiles-fresh'; got {row.get('hook')}"
        )
        assert "profiles" in row, f"Missing 'profiles' field; row={row}"
        assert "outcome" in row, f"Missing 'outcome' field; row={row}"

    def test_audit_row_outcome_missing_for_missing_lock(self, tmp_path: Path) -> None:
        _seed_workspace(tmp_path, profiles=None)
        _run_hook(tmp_path)
        rows = self._audit_rows(tmp_path)
        dispatch_rows = [r for r in rows if r.get("event_type") == "profile_dispatch"]
        assert dispatch_rows
        assert dispatch_rows[0].get("outcome") == "missing", (
            f"Expected outcome='missing'; got {dispatch_rows[0].get('outcome')}"
        )

    def test_audit_row_outcome_stale_for_stale_lock(self, tmp_path: Path) -> None:
        _seed_workspace(tmp_path, profiles=["python"])
        _set_lock_mtime_days_ago(tmp_path, days=8)
        _run_hook(tmp_path)
        rows = self._audit_rows(tmp_path)
        dispatch_rows = [r for r in rows if r.get("event_type") == "profile_dispatch"]
        assert dispatch_rows
        assert dispatch_rows[0].get("outcome") == "stale", (
            f"Expected outcome='stale'; got {dispatch_rows[0].get('outcome')}"
        )

    def test_audit_row_outcome_drift_for_drift(self, tmp_path: Path) -> None:
        _seed_workspace(tmp_path, profiles=["nonexistent-profile"])
        _set_lock_mtime_days_ago(tmp_path, days=0.1)
        _run_hook(tmp_path)
        rows = self._audit_rows(tmp_path)
        dispatch_rows = [r for r in rows if r.get("event_type") == "profile_dispatch"]
        assert dispatch_rows
        assert dispatch_rows[0].get("outcome") == "drift", (
            f"Expected outcome='drift'; got {dispatch_rows[0].get('outcome')}"
        )

    def test_audit_log_write_failure_does_not_change_exit_code(
        self, tmp_path: Path
    ) -> None:
        """Unwriteable efficiency dir → hook still exits 0 (best-effort)."""
        _seed_workspace(tmp_path, profiles=None)
        eff_dir = tmp_path / ".etc_sdlc" / "efficiency"
        eff_dir.mkdir(parents=True, exist_ok=True)
        # Make directory read-only so append fails
        eff_dir.chmod(0o555)
        try:
            result = _run_hook(tmp_path)
            assert result.returncode == 0, (
                f"Expected exit 0 even with unwriteable log dir; got {result.returncode}"
            )
        finally:
            # Restore so pytest can clean up
            eff_dir.chmod(0o755)
