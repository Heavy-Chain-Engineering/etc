"""F022 Task 005 — check-seam-evidence.sh profile-aware dispatch.

AC-004: hooks/check-seam-evidence.sh invokes profile_loader.py for active
profiles, dispatches to standards/code/profiles/<profile>/check-seam-evidence.sh
for each. On no-profile path emits stderr WARN containing 'no profile' + exits 0.
Audit-log row appended with event_type=profile_dispatch for both paths.

Test structure mirrors test_check_code_quality_profile.py and
test_go_profile.py — uses tmp_path fixtures, copies dispatch assets,
never pollutes the repo's audit log.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import textwrap
from pathlib import Path

ETC_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = ETC_ROOT / "hooks"
SCRIPTS_DIR = ETC_ROOT / "scripts"
PROFILES_DIR = ETC_ROOT / "standards" / "code" / "profiles"

# ---------------------------------------------------------------------------
# Workspace helpers
# ---------------------------------------------------------------------------


def _seed_workspace(tmp_path: Path, profiles: list[str]) -> Path:
    """Copy dispatch assets into tmp_path and write profiles.lock.

    Sets up:
      - tmp_path/scripts/profile_loader.py
      - tmp_path/.etc_sdlc/profiles.lock  (lines = profiles)
      - tmp_path/.etc_sdlc/efficiency/    (writable, for audit log)
    """
    scripts_dst = tmp_path / "scripts"
    scripts_dst.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SCRIPTS_DIR / "profile_loader.py", scripts_dst / "profile_loader.py")
    shutil.copy2(SCRIPTS_DIR / "dispatch_profile.sh", scripts_dst / "dispatch_profile.sh")
    shutil.copy2(SCRIPTS_DIR / "detect_profiles.py", scripts_dst / "detect_profiles.py")

    etc_dir = tmp_path / ".etc_sdlc"
    etc_dir.mkdir(parents=True, exist_ok=True)

    # Write profiles.lock (may be empty list for no-profile tests)
    lock = etc_dir / "profiles.lock"
    lock.write_text("".join(p + "\n" for p in profiles))

    # Pre-create the efficiency dir so audit-log writes succeed
    efficiency_dir = etc_dir / "efficiency"
    efficiency_dir.mkdir(parents=True, exist_ok=True)

    return tmp_path


def _install_profile_script(workspace: Path, profile: str, script_body: str) -> Path:
    """Write a stub per-profile check-seam-evidence.sh into the workspace."""
    profile_dir = workspace / "standards" / "code" / "profiles" / profile
    profile_dir.mkdir(parents=True, exist_ok=True)
    gate = profile_dir / "check-seam-evidence.sh"
    gate.write_text(script_body)
    gate.chmod(0o755)
    return gate


def _run_hook(
    payload: dict,
    cwd: Path,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(HOOKS_DIR / "check-seam-evidence.sh")],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=30,
        cwd=str(cwd),
    )


def _read_audit_rows(workspace: Path) -> list[dict]:
    """Return parsed JSONL rows from the workspace audit log."""
    log_path = workspace / ".etc_sdlc" / "efficiency" / "turn-events.jsonl"
    if not log_path.exists():
        return []
    rows = []
    for line in log_path.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return rows


# ---------------------------------------------------------------------------
# AC-004(b): No-profile path
# ---------------------------------------------------------------------------


class TestNoProfilePath:
    """BR-003 / F020-ADR-003: empty profiles.lock → stderr WARN + exit 0."""

    def test_no_profile_exits_0(self, tmp_path: Path) -> None:
        workspace = _seed_workspace(tmp_path, profiles=[])
        result = _run_hook({"cwd": str(workspace)}, workspace)
        assert result.returncode == 0, (
            f"Expected exit 0 on no-profile path, got {result.returncode}; "
            f"stderr={result.stderr!r}"
        )

    def test_no_profile_emits_warn_containing_no_profile(self, tmp_path: Path) -> None:
        workspace = _seed_workspace(tmp_path, profiles=[])
        result = _run_hook({"cwd": str(workspace)}, workspace)
        assert "no profile" in result.stderr.lower(), (
            f"Expected stderr to contain 'no profile'; got: {result.stderr!r}"
        )

    def test_no_profile_audit_log_row_appended(self, tmp_path: Path) -> None:
        """AC-004(c): audit log row emitted even on the no-profile (warn-and-skip) path."""
        workspace = _seed_workspace(tmp_path, profiles=[])
        _run_hook({"cwd": str(workspace)}, workspace)

        rows = _read_audit_rows(workspace)
        dispatch_rows = [r for r in rows if r.get("event_type") == "profile_dispatch"]
        assert len(dispatch_rows) >= 1, (
            f"Expected at least one profile_dispatch row; got rows: {rows}"
        )
        row = dispatch_rows[-1]
        assert row.get("hook") == "check-seam-evidence", (
            f"Expected hook='check-seam-evidence'; got: {row}"
        )
        assert row.get("outcome") == "warn-and-skip", (
            f"Expected outcome='warn-and-skip'; got: {row}"
        )
        assert row.get("profiles") == [], (
            f"Expected profiles=[]; got: {row}"
        )
        assert "ts" in row, f"Expected 'ts' field; got: {row}"
        assert row.get("event_type") == "profile_dispatch"


# ---------------------------------------------------------------------------
# AC-004(a): Dispatch path
# ---------------------------------------------------------------------------


class TestDispatchPath:
    """AC-004+BR-003: profiles.lock with 'python' dispatches to per-profile script."""

    def _make_passing_stub(self) -> str:
        return textwrap.dedent("""\
            #!/bin/bash
            # Stub check-seam-evidence.sh for test — always passes
            echo "[check-seam-evidence] python stub ran" >&2
            exit 0
        """)

    def _make_failing_stub(self) -> str:
        return textwrap.dedent("""\
            #!/bin/bash
            # Stub check-seam-evidence.sh for test — always fails
            echo "[check-seam-evidence] python stub FAILED" >&2
            exit 2
        """)

    def test_dispatch_invokes_per_profile_script(self, tmp_path: Path) -> None:
        workspace = _seed_workspace(tmp_path, profiles=["python"])
        _install_profile_script(workspace, "python", self._make_passing_stub())
        result = _run_hook({"cwd": str(workspace)}, workspace)
        assert result.returncode == 0, (
            f"Expected exit 0; got {result.returncode}; stderr={result.stderr!r}"
        )
        assert "python stub ran" in result.stderr, (
            f"Expected per-profile stub output; stderr={result.stderr!r}"
        )

    def test_dispatch_propagates_profile_failure(self, tmp_path: Path) -> None:
        workspace = _seed_workspace(tmp_path, profiles=["python"])
        _install_profile_script(workspace, "python", self._make_failing_stub())
        result = _run_hook({"cwd": str(workspace)}, workspace)
        assert result.returncode != 0, (
            f"Expected non-zero exit on profile failure; got {result.returncode}; stderr={result.stderr!r}"
        )

    def test_missing_profile_script_is_noop(self, tmp_path: Path) -> None:
        """AC-004: if per-profile script doesn't exist, treat as no-op (don't fail)."""
        workspace = _seed_workspace(tmp_path, profiles=["python"])
        # No per-profile script installed — hook must not fail
        result = _run_hook({"cwd": str(workspace)}, workspace)
        assert result.returncode == 0, (
            f"Expected exit 0 when per-profile script absent; "
            f"got {result.returncode}; stderr={result.stderr!r}"
        )

    def test_dispatch_audit_log_row_appended_pass(self, tmp_path: Path) -> None:
        """AC-004(c): audit log row with outcome=pass emitted on dispatch path."""
        workspace = _seed_workspace(tmp_path, profiles=["python"])
        _install_profile_script(workspace, "python", self._make_passing_stub())
        _run_hook({"cwd": str(workspace)}, workspace)

        rows = _read_audit_rows(workspace)
        dispatch_rows = [r for r in rows if r.get("event_type") == "profile_dispatch"]
        assert len(dispatch_rows) >= 1, (
            f"Expected at least one profile_dispatch row; got: {rows}"
        )
        row = dispatch_rows[-1]
        assert row.get("hook") == "check-seam-evidence", f"Unexpected hook name: {row}"
        assert row.get("outcome") == "pass", f"Expected outcome=pass; got: {row}"
        assert "python" in (row.get("profiles") or []), (
            f"Expected python in profiles list; got: {row}"
        )
        assert "ts" in row

    def test_dispatch_audit_log_row_outcome_fail(self, tmp_path: Path) -> None:
        """AC-004(c): audit log row with outcome=fail emitted when profile script fails."""
        workspace = _seed_workspace(tmp_path, profiles=["python"])
        _install_profile_script(workspace, "python", self._make_failing_stub())
        _run_hook({"cwd": str(workspace)}, workspace)

        rows = _read_audit_rows(workspace)
        dispatch_rows = [r for r in rows if r.get("event_type") == "profile_dispatch"]
        assert len(dispatch_rows) >= 1, (
            f"Expected at least one profile_dispatch row; got: {rows}"
        )
        row = dispatch_rows[-1]
        assert row.get("outcome") == "fail", f"Expected outcome=fail; got: {row}"

    def test_dispatch_audit_log_row_missing_profile_is_warn_and_skip(
        self, tmp_path: Path
    ) -> None:
        """AC-004(c): audit outcome=warn-and-skip when per-profile script absent."""
        workspace = _seed_workspace(tmp_path, profiles=["python"])
        # No stub installed — profile script is missing
        _run_hook({"cwd": str(workspace)}, workspace)

        rows = _read_audit_rows(workspace)
        dispatch_rows = [r for r in rows if r.get("event_type") == "profile_dispatch"]
        assert len(dispatch_rows) >= 1, (
            f"Expected at least one profile_dispatch row; got: {rows}"
        )
        row = dispatch_rows[-1]
        # Missing script → warn-and-skip at the profile level; overall exit 0
        assert row.get("outcome") in ("warn-and-skip", "pass"), (
            f"Expected warn-and-skip or pass for missing profile script; got: {row}"
        )


# ---------------------------------------------------------------------------
# EC-005: write-failure degrades silently (audit log best-effort)
# ---------------------------------------------------------------------------


class TestAuditLogBestEffort:
    """BR-009: write failures degrade silently — hook still exits 0."""

    def test_readonly_efficiency_dir_does_not_break_hook(self, tmp_path: Path) -> None:
        workspace = _seed_workspace(tmp_path, profiles=[])
        efficiency_dir = workspace / ".etc_sdlc" / "efficiency"
        efficiency_dir.chmod(0o444)  # read-only
        try:
            result = _run_hook({"cwd": str(workspace)}, workspace)
            assert result.returncode == 0, (
                f"Expected exit 0 even with read-only audit dir; "
                f"got {result.returncode}; stderr={result.stderr!r}"
            )
        finally:
            efficiency_dir.chmod(0o755)  # restore so tmp cleanup succeeds
