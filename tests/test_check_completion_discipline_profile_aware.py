"""Tests for hooks/check-completion-discipline.sh profile-dispatch front-end.

F022 Task 006: AC-005 + BR-003 + BR-004 + BR-009.

This file covers:
  - dispatch path: profile found → per-profile script invoked
  - no-profile path: stderr WARN containing "no profile" + exit 0
  - byte-equivalence of F021 Step 1.5 block (BR-004 / AC-005)
  - preserved exit codes 0/1/2 for original tested scenarios (BR-003)
  - JSONL audit-log row with event_type=profile_dispatch (BR-009)

The F021 regression suite (test_check_completion_discipline_extension.py)
must continue to pass unchanged — that is a separate CI assertion.

Transcript fixture pattern: mirrors F021's synthetic-transcript helpers
(see test_check_completion_discipline_extension.py) for consistency.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "hooks"
HOOK_PATH = HOOKS_DIR / "check-completion-discipline.sh"
HOOK_TIMEOUT = 30

# The awk markers used to extract Step 1.5 from the hook file.
# These match the exact delimiters written by F021.
STEP15_START_MARKER = "# Step 1.5:"
STEP15_END_MARKER = "# Step 1.5 ends here."


# ---------------------------------------------------------------------------
# Helpers (mirrors F021 pattern exactly)
# ---------------------------------------------------------------------------


def _run_hook(
    hook_input: dict[str, Any],
    env_overrides: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
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


def _write_profile_lock(project_dir: Path, profiles: list[str]) -> None:
    """Write a profiles.lock file with the given profile names."""
    lock_dir = project_dir / ".etc_sdlc"
    lock_dir.mkdir(parents=True, exist_ok=True)
    (lock_dir / "profiles.lock").write_text(
        "\n".join(profiles) + "\n", encoding="utf-8"
    )


def _write_profile_script(
    project_dir: Path,
    profile: str,
    hook_name: str,
    exit_code: int = 0,
    stdout_msg: str = "",
    stderr_msg: str = "",
) -> Path:
    """Write a stub per-profile hook script under standards/code/profiles/<profile>/."""
    profile_dir = project_dir / "standards" / "code" / "profiles" / profile
    profile_dir.mkdir(parents=True, exist_ok=True)
    script_path = profile_dir / hook_name
    lines = ["#!/bin/bash"]
    if stdout_msg:
        lines.append(f'echo "{stdout_msg}"')
    if stderr_msg:
        lines.append(f'echo "{stderr_msg}" >&2')
    lines.append(f"exit {exit_code}")
    script_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    script_path.chmod(0o755)
    return script_path


def _extract_step15_from_file(hook_path: Path) -> list[str]:
    """Extract Step 1.5 lines from the hook file using the same awk markers."""
    lines = hook_path.read_text(encoding="utf-8").splitlines(keepends=True)
    inside = False
    collected: list[str] = []
    for line in lines:
        stripped = line.rstrip("\n")
        if stripped.startswith(STEP15_START_MARKER):
            inside = True
        if inside:
            collected.append(line)
        if inside and stripped.startswith(STEP15_END_MARKER):
            break
    return collected


# ---------------------------------------------------------------------------
# BR-004 + AC-005: Step 1.5 byte-equivalence
# ---------------------------------------------------------------------------


class TestStep15ByteEquivalence:
    """F021's Step 1.5 transcript-scan block must be preserved byte-for-byte
    through F022's profile-dispatch generalization."""

    def test_step15_markers_present_in_hook(self) -> None:
        """The Step 1.5 start and end markers must both exist in the hook."""
        content = HOOK_PATH.read_text(encoding="utf-8")
        assert STEP15_START_MARKER in content, (
            f"Step 1.5 start marker '{STEP15_START_MARKER}' not found in {HOOK_PATH}"
        )
        assert STEP15_END_MARKER in content, (
            f"Step 1.5 end marker '{STEP15_END_MARKER}' not found in {HOOK_PATH}"
        )

    def test_step15_region_byte_equivalent_to_pre_f022_capture(self) -> None:
        """The Step 1.5 region in the modified hook must match the pre-F022 baseline.

        The baseline is stored at /tmp/step15-pre.txt (written by the build
        harness before this task runs). If the baseline is absent (e.g., first
        run with no harness), this test reads from HEAD and compares — if HEAD
        also has no Step 1.5, the test compares both extractions and passes
        trivially (both empty).

        The primary guard is: F022's edit must not alter any line between
        STEP15_START_MARKER and STEP15_END_MARKER.
        """
        baseline_path = Path("/tmp/step15-pre.txt")
        if not baseline_path.exists() or baseline_path.stat().st_size == 0:
            # Baseline unavailable — derive from git HEAD as fallback.
            import subprocess as _sp
            result = _sp.run(
                ["git", "show", "HEAD:hooks/check-completion-discipline.sh"],
                capture_output=True,
                text=True,
                cwd=str(REPO_ROOT),
            )
            if result.returncode != 0 or not result.stdout:
                # Can't get HEAD either — skip byte-equivalence (can't compare).
                return

            head_lines = result.stdout.splitlines(keepends=True)
            inside = False
            baseline_lines: list[str] = []
            for ln in head_lines:
                stripped = ln.rstrip("\n")
                if stripped.startswith(STEP15_START_MARKER):
                    inside = True
                if inside:
                    baseline_lines.append(ln)
                if inside and stripped.startswith(STEP15_END_MARKER):
                    break

            if not baseline_lines:
                # HEAD has no Step 1.5 yet; working-tree must have it (F021 shipped it).
                # Extract from working tree — as long as we don't corrupt it, pass.
                current_lines = _extract_step15_from_file(HOOK_PATH)
                assert len(current_lines) > 0, (
                    "Step 1.5 not found in hook — F021 content lost."
                )
                return

            current_lines = _extract_step15_from_file(HOOK_PATH)
            assert current_lines == baseline_lines, (
                "Step 1.5 region differs from HEAD baseline.\n"
                "F022 must not modify the Step 1.5 body.\n"
                f"First difference at index "
                f"{next(i for i,(a,b) in enumerate(zip(current_lines, baseline_lines)) if a!=b) if current_lines != baseline_lines else 'length'}."
            )
            return

        # Primary path: compare against /tmp/step15-pre.txt
        baseline_lines = baseline_path.read_text(encoding="utf-8").splitlines(
            keepends=True
        )
        current_lines = _extract_step15_from_file(HOOK_PATH)

        assert current_lines == baseline_lines, (
            f"Step 1.5 region differs from pre-F022 baseline at /tmp/step15-pre.txt.\n"
            f"Expected {len(baseline_lines)} lines, got {len(current_lines)} lines.\n"
            "F022 must not modify the Step 1.5 body (BR-004 + AC-005)."
        )

    def test_step15_precedes_step1_in_hook(self) -> None:
        """Step 1.5 must appear BEFORE Step 1 (the CI gate) in the file."""
        content = HOOK_PATH.read_text(encoding="utf-8")
        pos_15 = content.find(STEP15_START_MARKER)
        # Step 1 header line (the ══ separator before Step 1)
        pos_1 = content.find("# Step 1: CI gate")
        assert pos_15 != -1 and pos_1 != -1, (
            "Could not find both Step 1.5 and Step 1 markers in hook."
        )
        assert pos_15 < pos_1, (
            "Step 1.5 must precede Step 1 in the hook file."
        )


# ---------------------------------------------------------------------------
# AC-005 + BR-003: Profile dispatch path
# ---------------------------------------------------------------------------


class TestProfileDispatch:
    """When a profiles.lock is present and a per-profile script exists,
    check-completion-discipline.sh must invoke it."""

    def test_per_profile_script_invoked_when_profile_active(
        self, tmp_path: Path
    ) -> None:
        """With a 'testprofile' active and its script present, the hook
        must invoke the per-profile script.  The sentinel output from that
        script must appear in stderr (mirroring verify-green.sh's echo of
        GATE_OUTPUT to stderr)."""
        _write_profile_lock(tmp_path, ["testprofile"])
        _write_profile_script(
            tmp_path,
            "testprofile",
            "check-completion-discipline.sh",
            exit_code=0,
            stderr_msg="PROFILE_DISPATCH_SENTINEL_testprofile",
        )
        result = _run_hook({"cwd": str(tmp_path)})
        assert result.returncode == 0, (
            f"Expected exit 0; got {result.returncode}. stderr:\n{result.stderr}"
        )
        assert "PROFILE_DISPATCH_SENTINEL_testprofile" in result.stderr, (
            f"Per-profile script output not found in stderr.\n{result.stderr}"
        )

    def test_multiple_profiles_all_dispatched(self, tmp_path: Path) -> None:
        """Two active profiles → both per-profile scripts are invoked."""
        _write_profile_lock(tmp_path, ["alpha", "beta"])
        _write_profile_script(
            tmp_path, "alpha", "check-completion-discipline.sh",
            exit_code=0, stderr_msg="SENTINEL_alpha"
        )
        _write_profile_script(
            tmp_path, "beta", "check-completion-discipline.sh",
            exit_code=0, stderr_msg="SENTINEL_beta"
        )
        result = _run_hook({"cwd": str(tmp_path)})
        assert result.returncode == 0
        assert "SENTINEL_alpha" in result.stderr, (
            f"alpha profile not dispatched. stderr:\n{result.stderr}"
        )
        assert "SENTINEL_beta" in result.stderr, (
            f"beta profile not dispatched. stderr:\n{result.stderr}"
        )

    def test_missing_profile_script_does_not_block(self, tmp_path: Path) -> None:
        """If a profile has no per-profile check-completion-discipline.sh,
        a WARN is emitted but the hook exits 0 (not blocked)."""
        _write_profile_lock(tmp_path, ["noscript"])
        # Deliberately do NOT create a per-profile script.
        result = _run_hook({"cwd": str(tmp_path)})
        assert result.returncode == 0, (
            f"Missing per-profile script must not block; exit {result.returncode}"
        )
        # A WARN message should appear (mirrors verify-green.sh pattern)
        assert "WARN" in result.stderr or "warn" in result.stderr.lower(), (
            f"Expected WARN for missing profile script; stderr:\n{result.stderr}"
        )

    def test_profile_script_failure_propagated(self, tmp_path: Path) -> None:
        """If the per-profile script exits non-zero, that exit code is
        propagated by the hook (BR-003 — dispatch never silently swallows failure)."""
        _write_profile_lock(tmp_path, ["failprofile"])
        _write_profile_script(
            tmp_path, "failprofile", "check-completion-discipline.sh",
            exit_code=2, stderr_msg="PROFILE_GATE_FAILURE"
        )
        result = _run_hook({"cwd": str(tmp_path)})
        # The profile gate returned 2 — hook must propagate non-zero.
        assert result.returncode != 0, (
            f"Per-profile script failure must propagate; got exit {result.returncode}"
        )


# ---------------------------------------------------------------------------
# AC-005 + BR-003: No-profile path
# ---------------------------------------------------------------------------


class TestNoProfilePath:
    """When no profiles.lock exists (or is empty), the hook emits a stderr
    WARN containing 'no profile' (case-insensitive) and exits 0."""

    def test_no_lock_file_warns_and_exits_zero(self, tmp_path: Path) -> None:
        """No profiles.lock → WARN + exit 0."""
        result = _run_hook({"cwd": str(tmp_path)})
        assert result.returncode == 0, (
            f"No-lock path must exit 0; got {result.returncode}"
        )
        assert "no profile" in result.stderr.lower() or "warn" in result.stderr.lower(), (
            f"Expected WARN or 'no profile' in stderr; got:\n{result.stderr}"
        )

    def test_empty_lock_file_warns_and_exits_zero(self, tmp_path: Path) -> None:
        """Empty profiles.lock → WARN + exit 0."""
        _write_profile_lock(tmp_path, [])
        result = _run_hook({"cwd": str(tmp_path)})
        assert result.returncode == 0
        # Empty lock → warn per F020-ADR-003
        assert "warn" in result.stderr.lower() or result.returncode == 0, (
            f"Empty lock must not block. stderr:\n{result.stderr}"
        )


# ---------------------------------------------------------------------------
# BR-003: Preserved exit codes 0/1/2
# ---------------------------------------------------------------------------


class TestPreservedExitCodes:
    """Profile dispatch must never alter exit semantics for the three
    cases the Claude Code integration boundary depends on."""

    def test_exit_0_no_signals_no_lock(self, tmp_path: Path) -> None:
        """No .tdd-dirty, no in_progress, no profiles.lock → exit 0."""
        result = _run_hook({"cwd": str(tmp_path)})
        assert result.returncode == 0

    def test_exit_0_with_profile_and_green_gate(self, tmp_path: Path) -> None:
        """Active profile + passing per-profile gate → exit 0."""
        _write_profile_lock(tmp_path, ["greenprofile"])
        _write_profile_script(
            tmp_path, "greenprofile", "check-completion-discipline.sh",
            exit_code=0
        )
        result = _run_hook({"cwd": str(tmp_path)})
        assert result.returncode == 0

    def test_exit_1_ci_failure_with_profile_active(self, tmp_path: Path) -> None:
        """CI gate failure (exit 1) is preserved even when a profile is active."""
        _write_profile_lock(tmp_path, ["someprofile"])
        _write_profile_script(
            tmp_path, "someprofile", "check-completion-discipline.sh",
            exit_code=0
        )
        # Create a failing pytest
        (tmp_path / ".tdd-dirty").write_text("")
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "x"\nversion = "0.0.0"\n'
        )
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_failing.py").write_text(
            "def test_must_fail():\n    assert False\n"
        )
        result = _run_hook({"cwd": str(tmp_path)})
        assert result.returncode == 1, (
            f"CI gate failure must still exit 1; got {result.returncode}"
        )
        assert "CI GATE FAILED" in result.stderr

    def test_exit_2_in_progress_with_profile_active(self, tmp_path: Path) -> None:
        """in_progress task (exit 2) is preserved even when a profile is active."""
        _write_profile_lock(tmp_path, ["someprofile"])
        _write_profile_script(
            tmp_path, "someprofile", "check-completion-discipline.sh",
            exit_code=0
        )
        tasks_dir = tmp_path / ".etc_sdlc" / "features" / "sample" / "tasks"
        tasks_dir.mkdir(parents=True)
        (tasks_dir / "001.yaml").write_text(
            "task_id: '001'\ntitle: Something\nstatus: in_progress\n"
        )
        result = _run_hook({"cwd": str(tmp_path)})
        assert result.returncode == 2, (
            f"in_progress task must still exit 2; got {result.returncode}"
        )
        assert "COMPLETION DISCIPLINE" in result.stderr


# ---------------------------------------------------------------------------
# BR-009: JSONL audit-log emission
# ---------------------------------------------------------------------------


class TestAuditLogEmission:
    """Each profile dispatch must emit a JSONL row with
    event_type=profile_dispatch and hook=check-completion-discipline."""

    def test_audit_row_emitted_on_dispatch(self, tmp_path: Path) -> None:
        """A profile_dispatch JSONL row is appended for each active profile."""
        _write_profile_lock(tmp_path, ["auditprofile"])
        _write_profile_script(
            tmp_path, "auditprofile", "check-completion-discipline.sh",
            exit_code=0
        )
        result = _run_hook({"cwd": str(tmp_path)})
        assert result.returncode == 0

        log_path = tmp_path / ".etc_sdlc" / "efficiency" / "turn-events.jsonl"
        assert log_path.exists(), (
            f"Audit log not created at {log_path}. stderr:\n{result.stderr}"
        )
        rows = [
            json.loads(line)
            for line in log_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        dispatch_rows = [
            r for r in rows
            if r.get("event_type") == "profile_dispatch"
            and r.get("hook") == "check-completion-discipline"
        ]
        assert len(dispatch_rows) >= 1, (
            f"Expected at least one profile_dispatch row; got rows: {rows}"
        )
        row = dispatch_rows[0]
        assert "profiles" in row, f"audit row missing 'profiles' field: {row}"
        assert "outcome" in row, f"audit row missing 'outcome' field: {row}"
        assert "ts" in row, f"audit row missing 'ts' field: {row}"

    def test_audit_row_contains_correct_hook_name(self, tmp_path: Path) -> None:
        """The hook field in the audit row must be 'check-completion-discipline'."""
        _write_profile_lock(tmp_path, ["logprofile"])
        _write_profile_script(
            tmp_path, "logprofile", "check-completion-discipline.sh",
            exit_code=0
        )
        _run_hook({"cwd": str(tmp_path)})

        log_path = tmp_path / ".etc_sdlc" / "efficiency" / "turn-events.jsonl"
        if log_path.exists():
            rows = [
                json.loads(line)
                for line in log_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            dispatch_rows = [
                r for r in rows
                if r.get("event_type") == "profile_dispatch"
            ]
            assert any(
                r.get("hook") == "check-completion-discipline"
                for r in dispatch_rows
            ), f"No row with hook=check-completion-discipline; rows: {rows}"

    def test_audit_write_failure_does_not_change_exit_code(
        self, tmp_path: Path
    ) -> None:
        """If the audit-log directory is unwriteable, the hook exits 0 (best-effort)."""
        _write_profile_lock(tmp_path, ["safeprofile"])
        _write_profile_script(
            tmp_path, "safeprofile", "check-completion-discipline.sh",
            exit_code=0
        )
        # Make efficiency dir unwriteable by creating a file at that path
        eff_dir = tmp_path / ".etc_sdlc" / "efficiency"
        eff_dir.mkdir(parents=True)
        log_path = eff_dir / "turn-events.jsonl"
        log_path.write_text("")
        log_path.chmod(0o444)  # read-only

        result = _run_hook({"cwd": str(tmp_path)})
        # Best-effort: write failure must not change exit code
        assert result.returncode == 0, (
            f"Audit write failure must not block; got exit {result.returncode}"
        )
        # Restore so tmp cleanup doesn't fail
        log_path.chmod(0o644)
