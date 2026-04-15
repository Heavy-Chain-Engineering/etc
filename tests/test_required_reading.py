"""Tests for hooks/check-required-reading.sh — the required reading gate.

Verifies that the hook blocks edits to files in a task's scope when the agent
has not read the required files listed in the active task, and allows edits
in all other cases (no task dir, no active task, file not in scope, all
required files read).
"""

from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path
from typing import Any


def _marker_key(transcript_path: str) -> str:
    """Derive the 16-char marker key from a transcript path.

    Mirrors the hook's key derivation: sha256(transcript_path) | cut -c1-16.
    """
    digest = hashlib.sha256(transcript_path.encode()).hexdigest()
    return digest[:16]


def _marker_path(project_root: Path, transcript_path: str) -> Path:
    """Compute the marker file path for a given project and transcript."""
    key = _marker_key(transcript_path)
    return project_root / ".etc_sdlc" / ".hook-markers" / f"{key}-required-reading"


def _write_marker(project_root: Path, transcript_path: str) -> Path:
    """Create a fresh marker file at the expected location."""
    marker = _marker_path(project_root, transcript_path)
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("")
    return marker


HOOK_NAME = "check-required-reading.sh"


def _build_input(
    file_path: str,
    cwd: str,
    transcript_path: str,
) -> dict[str, Any]:
    """Build the JSON input structure expected by the hook."""
    return {
        "tool_input": {"file_path": file_path},
        "cwd": cwd,
        "transcript_path": transcript_path,
    }


def test_should_allow_when_no_task_dir(
    run_hook: Any,
    tmp_path: Path,
) -> None:
    """No .etc_sdlc/tasks/ directory exists -- hook should allow."""
    # Arrange
    transcript_path = tmp_path / "transcript.jsonl"
    transcript_path.write_text("")
    file_path = str(tmp_path / "src" / "handler.py")
    hook_input = _build_input(file_path, str(tmp_path), str(transcript_path))

    # Act
    result = run_hook(HOOK_NAME, hook_input)

    # Assert
    assert result.exit_code == 0


def test_should_allow_when_no_active_task(
    run_hook: Any,
    tmp_project: Path,
    task_file: Any,
    transcript_file: Any,
) -> None:
    """Tasks exist but none has status: in_progress -- hook should allow."""
    # Arrange
    task_file(
        task_id="001",
        title="Some task",
        status="pending",
        requires_reading=["spec/design.md"],
        files_in_scope=["src/"],
    )
    transcript = transcript_file([])
    file_path = str(tmp_project / "src" / "handler.py")
    hook_input = _build_input(file_path, str(tmp_project), str(transcript))

    # Act
    result = run_hook(HOOK_NAME, hook_input)

    # Assert
    assert result.exit_code == 0


def test_should_allow_when_file_not_in_scope(
    run_hook: Any,
    tmp_project: Path,
    task_file: Any,
    transcript_file: Any,
) -> None:
    """Editing a file NOT in the task's files_in_scope -- hook should allow."""
    # Arrange
    task_file(
        task_id="002",
        title="Scoped task",
        status="in_progress",
        requires_reading=["spec/design.md"],
        files_in_scope=["src/api/"],
    )
    transcript = transcript_file([])
    file_path = str(tmp_project / "docs" / "notes.md")
    hook_input = _build_input(file_path, str(tmp_project), str(transcript))

    # Act
    result = run_hook(HOOK_NAME, hook_input)

    # Assert
    assert result.exit_code == 0


def test_should_block_when_required_files_not_read(
    run_hook: Any,
    tmp_project: Path,
    task_file: Any,
    transcript_file: Any,
) -> None:
    """Task requires reading spec/design.md but transcript has no Read calls."""
    # Arrange
    task_file(
        task_id="003",
        title="Reading task",
        status="in_progress",
        requires_reading=["spec/design.md"],
        files_in_scope=["src/"],
    )
    transcript = transcript_file([])
    file_path = str(tmp_project / "src" / "handler.py")
    hook_input = _build_input(file_path, str(tmp_project), str(transcript))

    # Act
    result = run_hook(HOOK_NAME, hook_input)

    # Assert
    assert result.exit_code == 2
    assert "spec/design.md" in result.stderr
    assert "BLOCKED" in result.stderr


def test_should_allow_when_required_files_read(
    run_hook: Any,
    tmp_project: Path,
    task_file: Any,
    transcript_file: Any,
) -> None:
    """Transcript has Read calls for all required files -- hook should allow."""
    # Arrange
    task_file(
        task_id="004",
        title="Fully read task",
        status="in_progress",
        requires_reading=["spec/design.md", "spec/adr-001.md"],
        files_in_scope=["src/"],
    )
    transcript = transcript_file([
        ("Read", "spec/design.md"),
        ("Read", "spec/adr-001.md"),
    ])
    file_path = str(tmp_project / "src" / "handler.py")
    hook_input = _build_input(file_path, str(tmp_project), str(transcript))

    # Act
    result = run_hook(HOOK_NAME, hook_input)

    # Assert
    assert result.exit_code == 0


class TestCacheHit:
    """Per-subagent marker caching — cache-hit early-exit.

    BR-001: If a marker exists and is newer than all task files, the hook
    MUST exit 0 immediately without running the verification body.
    """

    def test_should_skip_verification_when_marker_is_fresh(
        self,
        run_hook: Any,
        tmp_project: Path,
        task_file: Any,
        transcript_file: Any,
    ) -> None:
        """A fresh marker file causes the hook to early-exit with 0 even
        when the live verification would block.
        """
        # Arrange: task that WOULD block (required reading not in transcript)
        task_file(
            task_id="100",
            title="Cache hit task",
            status="in_progress",
            requires_reading=["spec/prd.md"],
            files_in_scope=["src/"],
        )
        transcript = transcript_file([])  # no Read calls → live check blocks
        file_path = str(tmp_project / "src" / "handler.py")
        hook_input = _build_input(file_path, str(tmp_project), str(transcript))

        # Pre-create the marker to simulate a cached previous success.
        marker = _write_marker(tmp_project, str(transcript))
        # Ensure the marker mtime is newer than the task file's mtime.
        future = time.time() + 10
        os.utime(marker, (future, future))

        # Act
        result = run_hook(HOOK_NAME, hook_input)

        # Assert: cache-hit path should early-exit with 0 despite the
        # missing required reading.
        assert result.exit_code == 0, (
            f"Expected cache-hit early-exit (exit 0), got exit "
            f"{result.exit_code}. stderr={result.stderr!r}"
        )


class TestCacheMiss:
    """Per-subagent marker caching — cache-miss full check.

    BR-002: If no marker exists, the hook MUST run its existing
    verification logic unchanged.
    """

    def test_should_run_full_check_when_marker_is_absent(
        self,
        run_hook: Any,
        tmp_project: Path,
        task_file: Any,
        transcript_file: Any,
    ) -> None:
        """With no marker, the full verification runs. On success, the
        hook MUST create the marker file so subsequent Edits early-exit.
        """
        # Arrange: task that will PASS the full check (required file was
        # read), so we can assert the success-path creates the marker.
        task_file(
            task_id="101",
            title="Cache miss task",
            status="in_progress",
            requires_reading=["spec/design.md"],
            files_in_scope=["src/"],
        )
        transcript = transcript_file([("Read", "spec/design.md")])
        file_path = str(tmp_project / "src" / "handler.py")
        hook_input = _build_input(file_path, str(tmp_project), str(transcript))

        # Sanity check: no marker exists before the call.
        marker = _marker_path(tmp_project, str(transcript))
        assert not marker.exists()

        # Act
        result = run_hook(HOOK_NAME, hook_input)

        # Assert: full verification ran and passed.
        assert result.exit_code == 0, (
            f"Expected passing full-check (exit 0), got "
            f"{result.exit_code}. stderr={result.stderr!r}"
        )
        # And on cache-miss success the hook MUST have written the marker
        # so the next Edit in this subagent session can early-exit (BR-002).
        assert marker.exists(), (
            "On a successful cache-miss path the hook MUST create the "
            f"marker file at {marker} (BR-002)."
        )


class TestCacheInvalidation:
    """Per-subagent marker caching — mtime-based invalidation.

    BR-009: If the task file is newer than the marker, the hook MUST run
    the full check path and ignore the stale marker.
    """

    def test_should_invalidate_marker_when_task_file_is_newer(
        self,
        run_hook: Any,
        tmp_project: Path,
        task_file: Any,
        transcript_file: Any,
    ) -> None:
        """A task file newer than the marker forces a full check.

        We arrange a state where the full check PASSES (required file
        read). If the stale marker were honored, the hook would
        early-exit without touching the marker — its mtime would remain
        in the past. If the marker is properly invalidated, the full
        check runs and on success refreshes the marker to a current
        mtime. Asserting the marker mtime is fresh proves the stale
        marker was invalidated AND the full-check path was taken.
        """
        task_path = task_file(
            task_id="102",
            title="Invalidation task",
            status="in_progress",
            requires_reading=["spec/contract.md"],
            files_in_scope=["src/"],
        )
        transcript = transcript_file([("Read", "spec/contract.md")])
        file_path = str(tmp_project / "src" / "handler.py")
        hook_input = _build_input(file_path, str(tmp_project), str(transcript))

        # Write a stale marker (pretending we have a cached pass).
        marker = _write_marker(tmp_project, str(transcript))
        past = time.time() - 1_000_000  # far in the past
        os.utime(marker, (past, past))
        stale_mtime = marker.stat().st_mtime
        assert stale_mtime < time.time() - 100_000

        # Force the task file's mtime into the future so it is strictly
        # newer than the stale marker.
        future = time.time() + 10
        os.utime(task_path, (future, future))

        # Act
        result = run_hook(HOOK_NAME, hook_input)

        # Assert: full check ran and passed.
        assert result.exit_code == 0, (
            f"Expected passing full-check (exit 0) after marker "
            f"invalidation, got {result.exit_code}. "
            f"stderr={result.stderr!r}"
        )
        # The marker must still exist (refreshed) after the success-path.
        assert marker.exists()
        new_mtime = marker.stat().st_mtime
        # If the stale marker was honored (bug), mtime would equal the
        # ancient stale_mtime. If invalidated and refreshed, mtime is
        # recent. We assert a large delta to make this unambiguous.
        assert new_mtime > stale_mtime + 1000, (
            f"Marker mtime was not refreshed after full-check success: "
            f"stale={stale_mtime}, now={new_mtime}. Either the stale "
            f"marker was honored (BR-009 violation) or the success path "
            f"did not refresh the marker (BR-002 violation)."
        )


class TestCacheFailureNoMark:
    """Per-subagent marker caching — failing checks do not poison the cache.

    BR-008: On exit code 2, the hook MUST NOT create the marker file.
    """

    def test_should_not_create_marker_when_check_fails(
        self,
        run_hook: Any,
        tmp_project: Path,
        task_file: Any,
        transcript_file: Any,
    ) -> None:
        """A failing check must leave the marker directory untouched."""
        # Arrange: task where the required reading has not happened.
        task_file(
            task_id="103",
            title="No-marker-on-fail task",
            status="in_progress",
            requires_reading=["spec/security.md"],
            files_in_scope=["src/"],
        )
        transcript = transcript_file([])  # no Read calls → check blocks
        file_path = str(tmp_project / "src" / "handler.py")
        hook_input = _build_input(file_path, str(tmp_project), str(transcript))

        marker = _marker_path(tmp_project, str(transcript))
        assert not marker.exists()

        # Act
        result = run_hook(HOOK_NAME, hook_input)

        # Assert
        assert result.exit_code == 2
        assert not marker.exists(), (
            "Failing check must not create marker (BR-008)."
        )
        # The marker directory may or may not exist, but no
        # required-reading marker must be present.
        markers_dir = tmp_project / ".etc_sdlc" / ".hook-markers"
        if markers_dir.exists():
            required_reading_markers = list(
                markers_dir.glob("*-required-reading")
            )
            assert required_reading_markers == [], (
                f"Unexpected marker files after failing check: "
                f"{required_reading_markers}"
            )


class TestGracefulDegradation:
    """Per-subagent marker caching — missing transcript_path degrades.

    BR-005 / AC-7: With no transcript_path, the hook MUST run the full
    check and MUST NOT cache.
    """

    def test_should_run_full_check_when_transcript_path_missing(
        self,
        run_hook: Any,
        tmp_project: Path,
        task_file: Any,
    ) -> None:
        """Missing transcript_path still runs the full verification, does
        not crash, and does not create a marker file.
        """
        # Arrange: a task in-progress. With no transcript, the current
        # hook short-circuits to exit 0 (can't verify reading history).
        # That is the expected verification result for this input, so we
        # assert on it directly.
        task_file(
            task_id="104",
            title="Graceful degradation task",
            status="in_progress",
            requires_reading=["spec/anything.md"],
            files_in_scope=["src/"],
        )
        file_path = str(tmp_project / "src" / "handler.py")
        # Build input with an EMPTY transcript_path — the "missing key" case.
        hook_input = {
            "tool_input": {"file_path": file_path},
            "cwd": str(tmp_project),
            "transcript_path": "",
        }

        # Act
        result = run_hook(HOOK_NAME, hook_input)

        # Assert: hook ran to completion (not a crash) and returned the
        # verification result (exit 0 — the existing short-circuit for
        # missing transcript).
        assert result.exit_code == 0

        # And: no marker was created, because without a transcript_path
        # there is no cache key to derive.
        markers_dir = tmp_project / ".etc_sdlc" / ".hook-markers"
        if markers_dir.exists():
            entries = list(markers_dir.iterdir())
            assert entries == [], (
                f"No marker should be created when transcript_path is "
                f"missing (BR-005); found: {entries}"
            )
