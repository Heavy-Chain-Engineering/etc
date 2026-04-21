"""Tests for check-phase-gate.sh hook.

Validates that the phase-aware file gating hook blocks edits to files
inappropriate for the current SDLC phase and allows edits to files
that are appropriate.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

HOOK_NAME = "check-phase-gate.sh"


def _create_state(tmp_project: Path, phase: str) -> None:
    """Write a .sdlc/state.json with the given phase into tmp_project."""
    sdlc_dir = tmp_project / ".sdlc"
    sdlc_dir.mkdir(exist_ok=True)
    state = {"current_phase": phase}
    (sdlc_dir / "state.json").write_text(json.dumps(state))


def test_should_block_when_spec_phase_and_src_file(
    run_hook: Any, tmp_project: Path
) -> None:
    """Editing src/app.py during spec phase must be blocked."""
    _create_state(tmp_project, "Spec")
    result = run_hook(
        HOOK_NAME,
        {
            "tool_input": {"file_path": str(tmp_project / "src" / "app.py")},
            "cwd": str(tmp_project),
        },
    )
    assert result.exit_code == 2


def test_should_block_when_build_phase_and_spec_file(
    run_hook: Any, tmp_project: Path
) -> None:
    """Editing spec/prd.md during build phase must be blocked."""
    _create_state(tmp_project, "Build")
    result = run_hook(
        HOOK_NAME,
        {
            "tool_input": {"file_path": str(tmp_project / "spec" / "prd.md")},
            "cwd": str(tmp_project),
        },
    )
    assert result.exit_code == 2


def test_should_allow_when_build_phase_and_src_file(
    run_hook: Any, tmp_project: Path
) -> None:
    """Editing src/app.py during build phase must be allowed."""
    _create_state(tmp_project, "Build")
    result = run_hook(
        HOOK_NAME,
        {
            "tool_input": {"file_path": str(tmp_project / "src" / "app.py")},
            "cwd": str(tmp_project),
        },
    )
    assert result.exit_code == 0


def test_should_allow_when_no_state_file(
    run_hook: Any, tmp_project: Path
) -> None:
    """When .sdlc/state.json does not exist, all edits are allowed."""
    result = run_hook(
        HOOK_NAME,
        {
            "tool_input": {"file_path": str(tmp_project / "src" / "app.py")},
            "cwd": str(tmp_project),
        },
    )
    assert result.exit_code == 0


def test_should_block_when_bootstrap_and_src_file(
    run_hook: Any, tmp_project: Path
) -> None:
    """Editing src/ during bootstrap phase must be blocked."""
    _create_state(tmp_project, "Bootstrap")
    result = run_hook(
        HOOK_NAME,
        {
            "tool_input": {"file_path": str(tmp_project / "src" / "main.py")},
            "cwd": str(tmp_project),
        },
    )
    assert result.exit_code == 2


def test_should_allow_when_spec_phase_and_spec_file(
    run_hook: Any, tmp_project: Path
) -> None:
    """Editing spec/prd.md during spec phase must be allowed."""
    _create_state(tmp_project, "Spec")
    result = run_hook(
        HOOK_NAME,
        {
            "tool_input": {"file_path": str(tmp_project / "spec" / "prd.md")},
            "cwd": str(tmp_project),
        },
    )
    assert result.exit_code == 0


def test_should_allow_when_design_phase_and_docs_file(
    run_hook: Any, tmp_project: Path
) -> None:
    """Editing docs/design.md during design phase must be allowed."""
    _create_state(tmp_project, "Design")
    result = run_hook(
        HOOK_NAME,
        {
            "tool_input": {"file_path": str(tmp_project / "docs" / "design.md")},
            "cwd": str(tmp_project),
        },
    )
    assert result.exit_code == 0


def test_should_block_when_evaluate_phase_and_src_file(
    run_hook: Any, tmp_project: Path
) -> None:
    """Editing src/ during evaluate phase must be blocked."""
    _create_state(tmp_project, "Evaluate")
    result = run_hook(
        HOOK_NAME,
        {
            "tool_input": {"file_path": str(tmp_project / "src" / "app.py")},
            "cwd": str(tmp_project),
        },
    )
    assert result.exit_code == 2


def test_should_include_phase_name_in_error(
    run_hook: Any, tmp_project: Path
) -> None:
    """Error message must include the current phase name."""
    _create_state(tmp_project, "Spec")
    result = run_hook(
        HOOK_NAME,
        {
            "tool_input": {"file_path": str(tmp_project / "src" / "app.py")},
            "cwd": str(tmp_project),
        },
    )
    assert result.exit_code == 2
    assert "Spec" in result.stderr


# ---------------------------------------------------------------------------
# Per-subagent marker-file caching tests (RED phase for task 005).
#
# Task 005 will add cache-check / marker-write logic to
# hooks/check-phase-gate.sh. These tests encode the required behavior per
# PRD BR-003, BR-004, BR-005, BR-008, BR-009 (acceptance criteria 4-7).
# They MUST fail against the current unchanged hook.
# ---------------------------------------------------------------------------


def _marker_key(transcript_path: str) -> str:
    """Derive the 16-hex-char marker key from a transcript path.

    Mirrors the shell pipeline:
        echo -n "$TRANSCRIPT" | sha256sum | cut -c1-16
    """
    digest = hashlib.sha256(transcript_path.encode()).hexdigest()
    return digest[:16]


def _marker_path(tmp_project: Path, transcript_path: str) -> Path:
    """Compute the expected marker file path for the phase-gate hook."""
    key = _marker_key(transcript_path)
    return tmp_project / ".etc_sdlc" / ".hook-markers" / f"{key}-phase-gate"


def _write_marker(marker: Path) -> None:
    """Create the marker file, ensuring its parent directory exists."""
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.touch()


class TestCacheHit:
    """BR-003 / AC-4: fresh marker short-circuits the full verification."""

    def test_should_skip_verification_when_marker_is_fresh(
        self, run_hook: Any, tmp_project: Path
    ) -> None:
        _create_state(tmp_project, "Spec")
        transcript_path = str(tmp_project / "transcript.jsonl")

        # Ensure the state file mtime is safely in the past so the marker is
        # strictly newer.
        state_file = tmp_project / ".sdlc" / "state.json"
        past = time.time() - 100
        os.utime(state_file, (past, past))

        marker = _marker_path(tmp_project, transcript_path)
        _write_marker(marker)
        now = time.time()
        os.utime(marker, (now, now))

        # Scenario that would normally block: spec phase editing src/ file.
        result = run_hook(
            HOOK_NAME,
            {
                "tool_input": {"file_path": str(tmp_project / "src" / "app.py")},
                "cwd": str(tmp_project),
                "transcript_path": transcript_path,
            },
        )
        assert result.exit_code == 0, (
            "Fresh marker should cause the hook to early-exit with 0, "
            f"but exit was {result.exit_code}; stderr={result.stderr!r}"
        )


class TestCacheMiss:
    """BR-004: absent marker forces full verification AND writes marker on pass."""

    def test_should_run_full_check_when_marker_is_absent(
        self, run_hook: Any, tmp_project: Path
    ) -> None:
        # Use an allowing scenario so the full check exits 0 and the hook is
        # required to write the marker afterward. This makes the test
        # strictly red against the current hook (which never writes markers).
        _create_state(tmp_project, "Build")
        transcript_path = str(tmp_project / "transcript.jsonl")

        marker = _marker_path(tmp_project, transcript_path)
        assert not marker.exists()

        result = run_hook(
            HOOK_NAME,
            {
                "tool_input": {"file_path": str(tmp_project / "src" / "app.py")},
                "cwd": str(tmp_project),
                "transcript_path": transcript_path,
            },
        )
        assert result.exit_code == 0, (
            f"Allowed scenario should exit 0; stderr={result.stderr!r}"
        )
        assert marker.exists(), (
            "After a successful full check, the marker must be written at "
            f"{marker} so subsequent Edits can early-exit."
        )


class TestCacheInvalidation:
    """BR-009 / AC-5: stale marker invalidated when state.json is newer.

    Strictly-red strategy: use an ALLOWING scenario with a stale marker.
    A caching hook must (a) run the full check because the marker is
    invalidated, and (b) refresh the marker so its mtime is newer than
    state.json afterward. The current hook never touches the marker, so
    the post-run marker mtime stays stale and this test fails.
    """

    def test_should_invalidate_marker_when_state_json_is_newer(
        self, run_hook: Any, tmp_project: Path
    ) -> None:
        _create_state(tmp_project, "Build")
        transcript_path = str(tmp_project / "transcript.jsonl")

        marker = _marker_path(tmp_project, transcript_path)
        _write_marker(marker)
        past = time.time() - 100
        os.utime(marker, (past, past))

        state_file = tmp_project / ".sdlc" / "state.json"
        future = time.time() + 10
        os.utime(state_file, (future, future))

        result = run_hook(
            HOOK_NAME,
            {
                "tool_input": {"file_path": str(tmp_project / "src" / "app.py")},
                "cwd": str(tmp_project),
                "transcript_path": transcript_path,
            },
        )
        assert result.exit_code == 0, (
            f"Allowed scenario should exit 0; stderr={result.stderr!r}"
        )
        # After the full check runs, the marker must have been refreshed so
        # that its mtime is newer than state.json — otherwise the next Edit
        # would also see it as stale and never benefit from the cache.
        marker_mtime = marker.stat().st_mtime
        state_mtime = state_file.stat().st_mtime
        assert marker_mtime > state_mtime, (
            "Stale marker must be refreshed after full check; "
            f"marker mtime={marker_mtime}, state.json mtime={state_mtime}"
        )


class TestCacheFailureNoMark:
    """BR-008 / AC-6: failing checks must not poison the cache.

    Strictly-red strategy: run a failing check first and assert no marker
    is created, then run an allowing scenario on the same transcript and
    assert the marker IS created. The second assertion fails against the
    current (non-caching) hook.
    """

    def test_should_not_create_marker_when_check_fails(
        self, run_hook: Any, tmp_project: Path
    ) -> None:
        _create_state(tmp_project, "Spec")
        transcript_path = str(tmp_project / "transcript.jsonl")

        marker = _marker_path(tmp_project, transcript_path)
        assert not marker.exists()

        # Blocking scenario: Spec phase + src/ file.
        blocked = run_hook(
            HOOK_NAME,
            {
                "tool_input": {"file_path": str(tmp_project / "src" / "app.py")},
                "cwd": str(tmp_project),
                "transcript_path": transcript_path,
            },
        )
        assert blocked.exit_code == 2
        assert not marker.exists(), (
            "Failing check must NOT create the marker file; found marker at "
            f"{marker}"
        )

        # Positive control: switch to an allowing scenario on the same
        # transcript. A caching hook must now write the marker.
        _create_state(tmp_project, "Build")
        allowed = run_hook(
            HOOK_NAME,
            {
                "tool_input": {"file_path": str(tmp_project / "src" / "app.py")},
                "cwd": str(tmp_project),
                "transcript_path": transcript_path,
            },
        )
        assert allowed.exit_code == 0
        assert marker.exists(), (
            "After a successful check, the marker must be created at "
            f"{marker} (positive control for the caching mechanism)."
        )


class TestGracefulDegradation:
    """BR-005 / AC-7: missing transcript_path degrades gracefully.

    Strictly-red strategy: first run without transcript_path and assert
    the hook runs the full check and writes NO marker. Then run with a
    transcript_path on an allowing scenario and assert the marker IS
    written. The positive control fails against the current hook.
    """

    def test_should_run_full_check_when_transcript_path_missing(
        self, run_hook: Any, tmp_project: Path
    ) -> None:
        _create_state(tmp_project, "Spec")

        # Blocking scenario; no transcript_path field in stdin.
        result = run_hook(
            HOOK_NAME,
            {
                "tool_input": {"file_path": str(tmp_project / "src" / "app.py")},
                "cwd": str(tmp_project),
            },
        )
        # Full verification body still runs and blocks.
        assert result.exit_code == 2, (
            "Missing transcript_path must fall through to full check; "
            f"exit was {result.exit_code}; stderr={result.stderr!r}"
        )

        markers_dir = tmp_project / ".etc_sdlc" / ".hook-markers"
        if markers_dir.exists():
            assert not any(markers_dir.iterdir()), (
                "No marker must be written when transcript_path is missing; "
                f"found entries in {markers_dir}"
            )

        # Positive control: with transcript_path and an allowing scenario,
        # the caching hook must write a marker. Proves the "no-marker on
        # missing transcript" above is a real negative rather than the hook
        # simply never writing markers.
        _create_state(tmp_project, "Build")
        transcript_path = str(tmp_project / "transcript.jsonl")
        marker = _marker_path(tmp_project, transcript_path)

        allowed = run_hook(
            HOOK_NAME,
            {
                "tool_input": {"file_path": str(tmp_project / "src" / "app.py")},
                "cwd": str(tmp_project),
                "transcript_path": transcript_path,
            },
        )
        assert allowed.exit_code == 0
        assert marker.exists(), (
            "Positive control: marker must be written when transcript_path "
            f"is present and the check passes; expected at {marker}."
        )
