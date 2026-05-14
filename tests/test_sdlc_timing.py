"""Tests for scripts/sdlc_timing.py.

Synthetic git repos with crafted feat() commits at controlled timestamps.
We pin `GIT_AUTHOR_DATE` / `GIT_COMMITTER_DATE` to make wall-clock deltas
deterministic.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).parent.parent / "scripts" / "sdlc_timing.py"


def _commit(
    repo: Path, message: str, date_iso: str, file_name: str = "file.txt"
) -> str:
    """Make a commit with a controlled timestamp. Returns the new HEAD sha."""
    (repo / file_name).write_text(f"{message}\n{date_iso}\n", encoding="utf-8")
    env = {
        **os.environ,
        "GIT_AUTHOR_DATE": date_iso,
        "GIT_COMMITTER_DATE": date_iso,
        "GIT_AUTHOR_NAME": "Test",
        "GIT_AUTHOR_EMAIL": "test@example.com",
        "GIT_COMMITTER_NAME": "Test",
        "GIT_COMMITTER_EMAIL": "test@example.com",
    }
    subprocess.run(
        ["git", "-C", str(repo), "add", "-A"],
        env=env, check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-m", message, "--no-verify"],
        env=env, check=True, capture_output=True,
    )
    result = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        env=env, check=True, capture_output=True, text=True,
    )
    return result.stdout.strip()


def _init_repo(tmp_path: Path) -> Path:
    """Init a fresh git repo. Returns the path."""
    subprocess.run(
        ["git", "init", "-q", str(tmp_path)],
        check=True, capture_output=True,
    )
    return tmp_path


def _run(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python3", str(SCRIPT), *args],
        capture_output=True, text=True, timeout=15, cwd=repo,
    )


class TestEmptyRepo:
    def test_no_commits_prints_no_ships_message(self, tmp_path: Path) -> None:
        _init_repo(tmp_path)
        # Need at least one commit for the repo to be "valid" in some configs.
        # Just an empty-init repo: HEAD doesn't exist; git log will fail.
        # Add a chore commit so HEAD exists, but it's not a feat().
        _commit(tmp_path, "chore: init", "2026-05-01T10:00:00+00:00")
        result = _run(tmp_path)
        assert result.returncode == 0
        assert "No feat" in result.stdout

    def test_not_in_git_repo_exits_one(self, tmp_path: Path) -> None:
        result = _run(tmp_path)  # tmp_path with no `.git`
        assert result.returncode == 1
        assert "not a git" in result.stderr.lower()


class TestFeatCommitDetection:
    def test_feat_commit_recognized(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        _commit(repo, "feat(F001): user flow completeness", "2026-05-01T10:00:00+00:00")
        result = _run(repo)
        assert result.returncode == 0
        assert "F001" in result.stdout

    def test_fix_commit_also_recognized(self, tmp_path: Path) -> None:
        """fix(F<NNN>:...) commits are also ship events."""
        repo = _init_repo(tmp_path)
        _commit(repo, "fix(F012): wire auto-checkpoint", "2026-05-13T08:00:00+00:00")
        result = _run(repo)
        assert "F012" in result.stdout

    def test_non_feat_commits_skipped(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        _commit(repo, "chore: lint", "2026-05-01T10:00:00+00:00")
        _commit(repo, "docs: update README", "2026-05-01T11:00:00+00:00")
        result = _run(repo)
        assert "No feat" in result.stdout

    def test_feat_with_slug_in_paren_recognized(self, tmp_path: Path) -> None:
        """`feat(F017-journey):` should still match — extracts F017."""
        repo = _init_repo(tmp_path)
        _commit(
            repo,
            "feat(F017-journey-skill): SME journey capture",
            "2026-05-13T11:00:00+00:00",
        )
        result = _run(repo)
        assert "F017" in result.stdout


class TestInterShipGap:
    def test_gap_between_two_features(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        _commit(repo, "feat(F001): first", "2026-05-01T10:00:00+00:00")
        _commit(repo, "feat(F002): second", "2026-05-01T12:30:00+00:00", "second.txt")
        result = _run(repo)
        assert "F001" in result.stdout
        assert "F002" in result.stdout
        # Gap: 2h 30m
        assert "2h 30m" in result.stdout

    def test_first_feature_has_no_gap_from_prev(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        _commit(repo, "feat(F001): first", "2026-05-01T10:00:00+00:00")
        result = _run(repo)
        # The "—" placeholder appears for the first feature's gap
        assert "—" in result.stdout

    def test_dedupe_keeps_earliest_commit_per_feature(self, tmp_path: Path) -> None:
        """F012 had a fix-up commit; only the earliest ship counts as 'when shipped'."""
        repo = _init_repo(tmp_path)
        _commit(repo, "feat(F012): auto-checkpoint", "2026-05-13T08:00:00+00:00")
        _commit(
            repo,
            "fix(F012): hook wiring follow-up",
            "2026-05-13T09:30:00+00:00",
            "second.txt",
        )
        result = _run(repo, "--feature", "F012", "--json")
        payload = json.loads(result.stdout)
        # The recorded ship date is the EARLIEST feat commit, not the fix-up
        assert payload["commit_date"].startswith("2026-05-13T08:00:00")


class TestFilters:
    def test_feature_filter_returns_single_entry(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        _commit(repo, "feat(F001): first", "2026-05-01T10:00:00+00:00")
        _commit(repo, "feat(F002): second", "2026-05-02T10:00:00+00:00", "f2.txt")
        result = _run(repo, "--feature", "F001")
        assert "F001" in result.stdout
        # F002 must not appear in F001's detail view
        assert "F002" not in result.stdout

    def test_feature_filter_nonexistent_feature(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        _commit(repo, "feat(F001): first", "2026-05-01T10:00:00+00:00")
        result = _run(repo, "--feature", "F999")
        assert result.returncode == 0
        assert "No feat(F999) commit found" in result.stdout


class TestBaseline:
    def test_baseline_with_multiple_ships(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        _commit(repo, "feat(F001): a", "2026-05-01T10:00:00+00:00")
        _commit(repo, "feat(F002): b", "2026-05-01T11:00:00+00:00", "f2.txt")
        _commit(repo, "feat(F003): c", "2026-05-01T14:00:00+00:00", "f3.txt")
        result = _run(repo, "--baseline")
        assert "median" in result.stdout
        assert "p90" in result.stdout
        assert "Ships per day" in result.stdout

    def test_baseline_with_only_one_ship_explains(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        _commit(repo, "feat(F001): only one", "2026-05-01T10:00:00+00:00")
        result = _run(repo, "--baseline")
        # Can't compute a baseline from one feature
        assert "at least 2" in result.stdout


class TestWeeklyRollup:
    def test_by_week_groups_correctly(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        _commit(repo, "feat(F001): w1", "2026-05-04T10:00:00+00:00")  # Mon W19
        _commit(repo, "feat(F002): w1", "2026-05-05T10:00:00+00:00", "f2.txt")
        _commit(repo, "feat(F003): w2", "2026-05-12T10:00:00+00:00", "f3.txt")  # Mon W20
        result = _run(repo, "--by", "week")
        assert result.returncode == 0
        # 2026-W19 has 2 features; W20 has 1
        assert "2026-W19" in result.stdout
        assert "2026-W20" in result.stdout


class TestJSON:
    def test_default_json_is_list(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        _commit(repo, "feat(F001): a", "2026-05-01T10:00:00+00:00")
        _commit(repo, "feat(F002): b", "2026-05-02T10:00:00+00:00", "f2.txt")
        result = _run(repo, "--json")
        assert result.returncode == 0
        payload = json.loads(result.stdout)
        assert isinstance(payload, list)
        assert len(payload) == 2
        fids = [p["feature_id"] for p in payload]
        assert fids == ["F001", "F002"]

    def test_feature_json_has_phase_tags_array(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        _commit(repo, "feat(F001): a", "2026-05-01T10:00:00+00:00")
        result = _run(repo, "--feature", "F001", "--json")
        payload = json.loads(result.stdout)
        assert payload["feature_id"] == "F001"
        assert "phase_tags" in payload
        assert isinstance(payload["phase_tags"], list)


class TestSinceFilter:
    def test_since_filter_excludes_old_commits(self, tmp_path: Path) -> None:
        """A feature shipped 10 days ago is excluded from --since 3d."""
        repo = _init_repo(tmp_path)
        # Old feature: 30 days before "now" (but our test uses fixed dates)
        # We construct using a recent date so the filter is testable.
        import datetime
        now = datetime.datetime.now(datetime.timezone.utc)
        recent = (now - datetime.timedelta(days=1)).isoformat()
        old = (now - datetime.timedelta(days=30)).isoformat()
        _commit(repo, "feat(F001): old", old)
        _commit(repo, "feat(F002): recent", recent, "f2.txt")
        result = _run(repo, "--since", "3d")
        assert "F002" in result.stdout
        # F001 should be excluded
        assert "F001" not in result.stdout

    def test_invalid_since_argument_exits_one(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        _commit(repo, "feat(F001): a", "2026-05-01T10:00:00+00:00")
        result = _run(repo, "--since", "garbage")
        assert result.returncode == 1
