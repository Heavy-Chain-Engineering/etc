"""Behavioral tests for hooks/check-baseline-fresh.sh.

F-2026-06-10 brownfield architecture baseline, task 005 / AC-2.

SessionStart advisory hook. NEVER blocks (exit 0 always). Three Pattern B
stderr WARN paths, each naming the exact backfill command
``/init-project --phase=baseline``:

    TestMissingBaseline  — brownfield-shaped repo (DOMAIN.md + PROJECT.md, no
                           baseline) → WARN 'missing' + 'architecture-baseline'.
    TestSilentSkip       — repo WITHOUT etc tier-0 artifacts → no WARN (not
                           onboarded; never cry-wolf).
    TestStaleBaseline    — mtime > BASELINE_STALENESS_DAYS → WARN 'stale'.
    TestDriftBaseline    — workspace seam-map newer than baseline → WARN 'drift'.
    TestFreshBaseline    — present, fresh, not behind seam-map → no WARN.
    TestEnvOverride      — BASELINE_STALENESS_DAYS tightens the window.
    TestAlwaysExitsZero  — every path, including unwriteable stderr/telemetry.
    TestTelemetry        — one baseline_freshness JSONL row per invocation.

Pattern B format: \\n\\n---\\n\\n**▶ Note:** <message>
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOK_PATH = REPO_ROOT / "hooks" / "check-baseline-fresh.sh"
HOOK_TIMEOUT = 30

BACKFILL_CMD = "/init-project --phase=baseline"

VALID_BASELINE = """\
schema_version: 1
status: unratified
confidence:
  score: low
  inputs: {}
inventory: []
claims: []
rules: []
seams: []
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run_hook(
    tmp_path: Path,
    env_overrides: dict[str, str] | None = None,
    hook_input: dict | None = None,
) -> subprocess.CompletedProcess[str]:
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


def _onboard(tmp_path: Path) -> None:
    """Write the etc tier-0 artifacts so the repo is 'brownfield-shaped'."""
    (tmp_path / "DOMAIN.md").write_text("# domain\n", encoding="utf-8")
    (tmp_path / "PROJECT.md").write_text("# project\n", encoding="utf-8")


def _write_baseline(tmp_path: Path, content: str = VALID_BASELINE) -> Path:
    path = tmp_path / ".etc_sdlc" / "architecture-baseline.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _write_seam_map(tmp_path: Path) -> Path:
    path = tmp_path / ".etc_workspace" / "seam-map.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("schema_version: 1\nrepos: []\nseams: []\n", encoding="utf-8")
    return path


def _set_mtime_days_ago(path: Path, days: float) -> None:
    age_seconds = days * 86400
    old = time.time() - age_seconds
    os.utime(path, (old, old))


def _pattern_b_present(stderr: str) -> bool:
    return "**▶ Note:**" in stderr or ("---" in stderr and "Note:" in stderr)


def _audit_rows(tmp_path: Path) -> list[dict]:
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


def _freshness_rows(tmp_path: Path) -> list[dict]:
    return [r for r in _audit_rows(tmp_path) if r.get("event_type") == "baseline_freshness"]


# ---------------------------------------------------------------------------
# TestMissingBaseline
# ---------------------------------------------------------------------------


class TestMissingBaseline:
    """Brownfield-shaped repo with no baseline → WARN; exit 0."""

    def test_exit_code_is_zero(self, tmp_path: Path) -> None:
        _onboard(tmp_path)
        result = _run_hook(tmp_path)
        assert result.returncode == 0, result.stderr

    def test_stderr_contains_missing(self, tmp_path: Path) -> None:
        _onboard(tmp_path)
        result = _run_hook(tmp_path)
        assert "missing" in result.stderr.lower(), result.stderr

    def test_stderr_contains_architecture_baseline(self, tmp_path: Path) -> None:
        _onboard(tmp_path)
        result = _run_hook(tmp_path)
        assert "architecture-baseline" in result.stderr, result.stderr

    def test_stderr_names_backfill_command(self, tmp_path: Path) -> None:
        _onboard(tmp_path)
        result = _run_hook(tmp_path)
        assert BACKFILL_CMD in result.stderr, (
            f"WARN must name the exact backfill command '{BACKFILL_CMD}'; got:\n{result.stderr}"
        )

    def test_pattern_b_format(self, tmp_path: Path) -> None:
        _onboard(tmp_path)
        result = _run_hook(tmp_path)
        assert _pattern_b_present(result.stderr), result.stderr

    def test_telemetry_outcome_missing(self, tmp_path: Path) -> None:
        _onboard(tmp_path)
        _run_hook(tmp_path)
        rows = _freshness_rows(tmp_path)
        assert rows and rows[0].get("outcome") == "missing", rows


# ---------------------------------------------------------------------------
# TestSilentSkip
# ---------------------------------------------------------------------------


class TestSilentSkip:
    """Repo with NO etc tier-0 artifacts → no WARN (not onboarded)."""

    def test_no_warn_when_not_onboarded(self, tmp_path: Path) -> None:
        # No DOMAIN.md / PROJECT.md, no baseline.
        result = _run_hook(tmp_path)
        stderr_lower = result.stderr.lower()
        assert "missing" not in stderr_lower, (
            f"must NOT cry-wolf on a non-onboarded repo; got:\n{result.stderr}"
        )

    def test_exit_zero_when_not_onboarded(self, tmp_path: Path) -> None:
        result = _run_hook(tmp_path)
        assert result.returncode == 0

    def test_telemetry_outcome_skip(self, tmp_path: Path) -> None:
        _run_hook(tmp_path)
        rows = _freshness_rows(tmp_path)
        assert rows and rows[0].get("outcome") == "skip", rows

    def test_only_domain_present_still_skips(self, tmp_path: Path) -> None:
        """Partial onboarding (DOMAIN.md but no PROJECT.md) → silent skip."""
        (tmp_path / "DOMAIN.md").write_text("# domain\n", encoding="utf-8")
        result = _run_hook(tmp_path)
        assert "missing" not in result.stderr.lower(), result.stderr
        rows = _freshness_rows(tmp_path)
        assert rows and rows[0].get("outcome") == "skip", rows


# ---------------------------------------------------------------------------
# TestStaleBaseline
# ---------------------------------------------------------------------------


class TestStaleBaseline:
    """Baseline mtime > BASELINE_STALENESS_DAYS (default 30) → WARN 'stale'."""

    def test_exit_code_is_zero(self, tmp_path: Path) -> None:
        _onboard(tmp_path)
        baseline = _write_baseline(tmp_path)
        _set_mtime_days_ago(baseline, days=31)
        result = _run_hook(tmp_path)
        assert result.returncode == 0, result.stderr

    def test_stderr_contains_stale(self, tmp_path: Path) -> None:
        _onboard(tmp_path)
        baseline = _write_baseline(tmp_path)
        _set_mtime_days_ago(baseline, days=31)
        result = _run_hook(tmp_path)
        assert "stale" in result.stderr.lower(), result.stderr

    def test_stderr_contains_architecture_baseline(self, tmp_path: Path) -> None:
        _onboard(tmp_path)
        baseline = _write_baseline(tmp_path)
        _set_mtime_days_ago(baseline, days=31)
        result = _run_hook(tmp_path)
        assert "architecture-baseline" in result.stderr, result.stderr

    def test_stderr_names_backfill_command(self, tmp_path: Path) -> None:
        _onboard(tmp_path)
        baseline = _write_baseline(tmp_path)
        _set_mtime_days_ago(baseline, days=31)
        result = _run_hook(tmp_path)
        assert BACKFILL_CMD in result.stderr, result.stderr

    def test_fresh_baseline_not_stale(self, tmp_path: Path) -> None:
        _onboard(tmp_path)
        baseline = _write_baseline(tmp_path)
        _set_mtime_days_ago(baseline, days=29)
        result = _run_hook(tmp_path)
        assert "stale" not in result.stderr.lower(), result.stderr

    def test_telemetry_outcome_stale(self, tmp_path: Path) -> None:
        _onboard(tmp_path)
        baseline = _write_baseline(tmp_path)
        _set_mtime_days_ago(baseline, days=31)
        _run_hook(tmp_path)
        rows = _freshness_rows(tmp_path)
        assert rows and rows[0].get("outcome") == "stale", rows


# ---------------------------------------------------------------------------
# TestDriftBaseline
# ---------------------------------------------------------------------------


class TestDriftBaseline:
    """Workspace seam-map newer than the baseline mirror → WARN 'drift'."""

    def test_exit_code_is_zero(self, tmp_path: Path) -> None:
        _onboard(tmp_path)
        baseline = _write_baseline(tmp_path)
        _set_mtime_days_ago(baseline, days=2)
        seam = _write_seam_map(tmp_path)
        _set_mtime_days_ago(seam, days=0.1)  # newer than the baseline
        result = _run_hook(tmp_path)
        assert result.returncode == 0, result.stderr

    def test_stderr_contains_drift(self, tmp_path: Path) -> None:
        _onboard(tmp_path)
        baseline = _write_baseline(tmp_path)
        _set_mtime_days_ago(baseline, days=2)
        seam = _write_seam_map(tmp_path)
        _set_mtime_days_ago(seam, days=0.1)
        result = _run_hook(tmp_path)
        assert "drift" in result.stderr.lower(), result.stderr

    def test_stderr_names_backfill_command(self, tmp_path: Path) -> None:
        _onboard(tmp_path)
        baseline = _write_baseline(tmp_path)
        _set_mtime_days_ago(baseline, days=2)
        seam = _write_seam_map(tmp_path)
        _set_mtime_days_ago(seam, days=0.1)
        result = _run_hook(tmp_path)
        assert BACKFILL_CMD in result.stderr, result.stderr

    def test_no_drift_when_baseline_newer_than_seam_map(self, tmp_path: Path) -> None:
        _onboard(tmp_path)
        seam = _write_seam_map(tmp_path)
        _set_mtime_days_ago(seam, days=2)
        baseline = _write_baseline(tmp_path)
        _set_mtime_days_ago(baseline, days=0.1)  # newer than the seam-map
        result = _run_hook(tmp_path)
        assert "drift" not in result.stderr.lower(), result.stderr

    def test_telemetry_outcome_drift(self, tmp_path: Path) -> None:
        _onboard(tmp_path)
        baseline = _write_baseline(tmp_path)
        _set_mtime_days_ago(baseline, days=2)
        seam = _write_seam_map(tmp_path)
        _set_mtime_days_ago(seam, days=0.1)
        _run_hook(tmp_path)
        rows = _freshness_rows(tmp_path)
        assert rows and rows[0].get("outcome") == "drift", rows


# ---------------------------------------------------------------------------
# TestFreshBaseline
# ---------------------------------------------------------------------------


class TestFreshBaseline:
    """Present, fresh, not behind the seam-map → no WARN; outcome 'fresh'."""

    def test_no_warn_on_fresh_baseline(self, tmp_path: Path) -> None:
        _onboard(tmp_path)
        _write_baseline(tmp_path)  # just-written, mtime ~now
        result = _run_hook(tmp_path)
        stderr_lower = result.stderr.lower()
        assert not any(t in stderr_lower for t in ("missing", "stale", "drift")), result.stderr

    def test_exit_zero_on_fresh_baseline(self, tmp_path: Path) -> None:
        _onboard(tmp_path)
        _write_baseline(tmp_path)
        result = _run_hook(tmp_path)
        assert result.returncode == 0

    def test_telemetry_outcome_fresh(self, tmp_path: Path) -> None:
        _onboard(tmp_path)
        _write_baseline(tmp_path)
        _run_hook(tmp_path)
        rows = _freshness_rows(tmp_path)
        assert rows and rows[0].get("outcome") == "fresh", rows


# ---------------------------------------------------------------------------
# TestEnvOverride
# ---------------------------------------------------------------------------


class TestEnvOverride:
    """BASELINE_STALENESS_DAYS tightens the staleness window."""

    def test_window_1_makes_2_day_baseline_stale(self, tmp_path: Path) -> None:
        _onboard(tmp_path)
        baseline = _write_baseline(tmp_path)
        _set_mtime_days_ago(baseline, days=2)
        result = _run_hook(tmp_path, env_overrides={"BASELINE_STALENESS_DAYS": "1"})
        assert "stale" in result.stderr.lower(), result.stderr
        assert result.returncode == 0

    def test_window_1_keeps_half_day_baseline_fresh(self, tmp_path: Path) -> None:
        _onboard(tmp_path)
        baseline = _write_baseline(tmp_path)
        _set_mtime_days_ago(baseline, days=0.4)
        result = _run_hook(tmp_path, env_overrides={"BASELINE_STALENESS_DAYS": "1"})
        assert "stale" not in result.stderr.lower(), result.stderr

    def test_invalid_env_falls_back_to_default_30(self, tmp_path: Path) -> None:
        _onboard(tmp_path)
        baseline = _write_baseline(tmp_path)
        _set_mtime_days_ago(baseline, days=31)
        result = _run_hook(tmp_path, env_overrides={"BASELINE_STALENESS_DAYS": "notanumber"})
        assert "stale" in result.stderr.lower(), result.stderr
        assert result.returncode == 0


# ---------------------------------------------------------------------------
# TestAlwaysExitsZero
# ---------------------------------------------------------------------------


class TestAlwaysExitsZero:
    """The SessionStart contract: exit 0 on every path."""

    def test_empty_cwd_exits_zero(self, tmp_path: Path) -> None:
        result = _run_hook(tmp_path, hook_input={"cwd": None})
        assert result.returncode == 0

    def test_no_cwd_field_exits_zero(self, tmp_path: Path) -> None:
        result = _run_hook(tmp_path, hook_input={})
        assert result.returncode == 0

    def test_malformed_input_exits_zero(self, tmp_path: Path) -> None:
        result = subprocess.run(
            ["bash", str(HOOK_PATH)],
            input="not json at all",
            capture_output=True,
            text=True,
            timeout=HOOK_TIMEOUT,
            cwd=str(tmp_path),
        )
        assert result.returncode == 0

    def test_unwriteable_telemetry_dir_exits_zero(self, tmp_path: Path) -> None:
        _onboard(tmp_path)
        eff = tmp_path / ".etc_sdlc" / "efficiency"
        eff.mkdir(parents=True, exist_ok=True)
        eff.chmod(0o555)
        try:
            result = _run_hook(tmp_path)
            assert result.returncode == 0, result.stderr
        finally:
            eff.chmod(0o755)


# ---------------------------------------------------------------------------
# TestTelemetry
# ---------------------------------------------------------------------------


class TestTelemetry:
    """One baseline_freshness JSONL row per invocation with required fields."""

    def test_row_has_required_fields(self, tmp_path: Path) -> None:
        _onboard(tmp_path)
        _write_baseline(tmp_path)
        _run_hook(tmp_path)
        rows = _freshness_rows(tmp_path)
        assert rows, "no baseline_freshness row emitted"
        row = rows[0]
        assert "ts" in row, row
        assert row.get("event_type") == "baseline_freshness", row
        assert row.get("hook") == "check-baseline-fresh", row
        assert "outcome" in row, row

    def test_one_row_per_invocation(self, tmp_path: Path) -> None:
        _onboard(tmp_path)
        _write_baseline(tmp_path)
        _run_hook(tmp_path)
        _run_hook(tmp_path)
        assert len(_freshness_rows(tmp_path)) == 2
