"""Tests for scripts/sdlc_timing.py.

Synthetic git repos with crafted feat() commits at controlled timestamps.
We pin `GIT_AUTHOR_DATE` / `GIT_COMMITTER_DATE` to make wall-clock deltas
deterministic.
"""

from __future__ import annotations

import datetime as _datetime
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType

SCRIPT = Path(__file__).parent.parent / "scripts" / "sdlc_timing.py"


def _load_timing_module() -> ModuleType:
    """Import scripts/sdlc_timing.py for direct function access."""
    spec = importlib.util.spec_from_file_location("sdlc_timing_under_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _utc(minute: int) -> _datetime.datetime:
    """Fixed UTC timestamp at 2026-05-26T10:<minute>:00 for deterministic deltas."""
    return _datetime.datetime(
        2026, 5, 26, 10, minute, 0, tzinfo=_datetime.timezone.utc
    )


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


class TestLOCFields:
    """Each ship dict carries files_changed, insertions, deletions, churn."""

    def test_loc_fields_present_in_json_output(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        _commit(repo, "feat(F001): first ship", "2026-05-01T10:00:00+00:00")
        result = _run(repo, "--json")
        payload = json.loads(result.stdout)
        assert len(payload) == 1
        s = payload[0]
        for field in ("files_changed", "insertions", "deletions", "churn"):
            assert field in s, f"missing LOC field: {field}"

    def test_loc_fields_have_nonzero_values_for_real_commits(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        # Commit a file with content; should produce >0 insertions
        _commit(repo, "feat(F001): content ship", "2026-05-01T10:00:00+00:00")
        result = _run(repo, "--json")
        payload = json.loads(result.stdout)
        assert payload[0]["files_changed"] >= 1
        assert payload[0]["insertions"] >= 1
        assert payload[0]["churn"] == payload[0]["insertions"] + payload[0]["deletions"]

    def test_detail_view_renders_loc_lines(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        _commit(repo, "feat(F001): detail", "2026-05-01T10:00:00+00:00")
        result = _run(repo, "--feature", "F001")
        assert "Files changed:" in result.stdout
        assert "Insertions:" in result.stdout
        assert "Deletions:" in result.stdout
        assert "Churn" in result.stdout

    def test_baseline_view_reports_churn_percentiles(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        _commit(repo, "feat(F001): a", "2026-05-01T10:00:00+00:00")
        _commit(repo, "feat(F002): b", "2026-05-01T12:00:00+00:00", "f2.txt")
        _commit(repo, "feat(F003): c", "2026-05-02T10:00:00+00:00", "f3.txt")
        result = _run(repo, "--baseline")
        assert "Churn per ship" in result.stdout
        assert "median:" in result.stdout
        assert "LOC" in result.stdout


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


class TestDualFormPhaseTagParsing:
    """AC-07 / BR-07: compute_phase_intervals must parse BOTH the legacy flat
    `build/phase-<N>/{start,done}` form AND the new nested
    `build/phase-<P>/wave-<W>/{start,done}` form without crashing, attributing
    each tag to the correct feature/phase."""

    def test_should_measure_flat_phase_interval_when_legacy_form(self) -> None:
        timing = _load_timing_module()
        tags_by_feature = {
            "F001": [
                ("build/phase-1/start", _utc(0)),
                ("build/phase-1/done", _utc(5)),
            ]
        }

        intervals = timing.compute_phase_intervals(tags_by_feature)

        assert intervals["F001"]["build/phase-1"] == 300.0

    def test_should_measure_nested_phase_interval_when_wave_form(self) -> None:
        timing = _load_timing_module()
        tags_by_feature = {
            "F002": [
                ("build/phase-0/wave-1/start", _utc(0)),
                ("build/phase-0/wave-1/done", _utc(3)),
            ]
        }

        intervals = timing.compute_phase_intervals(tags_by_feature)

        # The nested tag is attributed to phase-0 (the wave rolls up into it).
        assert intervals["F002"]["build/phase-0"] == 180.0

    def test_should_attribute_both_forms_without_crash_in_mixed_set(
        self,
    ) -> None:
        timing = _load_timing_module()
        tags_by_feature = {
            "F001": [
                ("build/phase-1/start", _utc(0)),
                ("build/phase-1/done", _utc(5)),
            ],
            "F002": [
                ("build/phase-0/wave-1/start", _utc(0)),
                ("build/phase-0/wave-1/done", _utc(3)),
            ],
        }

        intervals = timing.compute_phase_intervals(tags_by_feature)

        assert intervals["F001"]["build/phase-1"] == 300.0
        assert intervals["F002"]["build/phase-0"] == 180.0


class TestTagCategorizer:
    """AC-08 / BR-07: the tag categorizer (used by /metrics) must bucket BOTH
    flat and nested build-phase tags under the build-phase category."""

    def test_should_bucket_flat_phase_tag_under_build_phase(self) -> None:
        timing = _load_timing_module()
        assert timing.categorize_tag_suffix("build/phase-1/start") == "build-phase"
        assert timing.categorize_tag_suffix("build/phase-2/done") == "build-phase"

    def test_should_bucket_nested_wave_tag_under_build_phase(self) -> None:
        timing = _load_timing_module()
        assert (
            timing.categorize_tag_suffix("build/phase-0/wave-1/start")
            == "build-phase"
        )
        assert (
            timing.categorize_tag_suffix("build/phase-3/wave-2/done")
            == "build-phase"
        )

    def test_should_bucket_non_phase_tags_to_their_own_category(self) -> None:
        timing = _load_timing_module()
        assert timing.categorize_tag_suffix("spec") == "spec"
        assert timing.categorize_tag_suffix("release") == "release"
        assert timing.categorize_tag_suffix("hotfix/H001") == "hotfix"


class TestDatedFeatureIdParsing:
    """#39: FEATURE_TAG_PATTERN and FEAT_COMMIT_PATTERN must capture BOTH the
    legacy sequential `F<NNN>` form AND the current date-based
    `F-YYYY-MM-DD-<slug>` form. Before the fix `F\\d+` silently dropped every
    dated-ID feature from the timing report."""

    def test_tag_pattern_matches_dated_feature_id(self) -> None:
        timing = _load_timing_module()
        m = timing.FEATURE_TAG_PATTERN.match(
            "etc/feature/F-2026-05-27-reasoned-checkpoint-agent-hook/spec"
        )
        assert m is not None, "dated feature-id tag did not match FEATURE_TAG_PATTERN"
        assert m.group(1) == "F-2026-05-27-reasoned-checkpoint-agent-hook"
        assert m.group(2) == "spec"

    def test_tag_pattern_still_matches_legacy_sequential_id(self) -> None:
        timing = _load_timing_module()
        m = timing.FEATURE_TAG_PATTERN.match("etc/feature/F042/build/phase-1/done")
        assert m is not None
        assert m.group(1) == "F042"
        assert m.group(2) == "build/phase-1/done"

    def test_commit_pattern_matches_dated_feature_id(self) -> None:
        timing = _load_timing_module()
        m = timing.FEAT_COMMIT_PATTERN.search(
            "feat(F-2026-05-26-checkpoint-template-and-gate): add gate\n"
        )
        assert m is not None, "dated feature-id commit did not match FEAT_COMMIT_PATTERN"
        assert m.group(1) == "F-2026-05-26-checkpoint-template-and-gate"

    def test_commit_pattern_still_matches_legacy_sequential_id(self) -> None:
        timing = _load_timing_module()
        m = timing.FEAT_COMMIT_PATTERN.search("fix(F007): stub grep\n")
        assert m is not None
        assert m.group(1) == "F007"

    def test_list_feature_tags_attributes_dated_feature(self, tmp_path: Path) -> None:
        """End-to-end via a real repo: list_feature_tags must bucket a
        dated-ID feature under its full id (not silently drop it)."""
        timing = _load_timing_module()
        repo = _init_repo(tmp_path)
        _commit(repo, "feat(F-2026-05-27-foo): seed", "2026-05-27T10:00:00+00:00")
        for suffix in ("spec", "release"):
            subprocess.run(
                ["git", "-C", str(repo), "tag", f"etc/feature/F-2026-05-27-foo/{suffix}"],
                check=True, capture_output=True,
            )
        tags_by_feature = timing.list_feature_tags(repo)
        assert "F-2026-05-27-foo" in tags_by_feature
        suffixes = {suffix for suffix, _ in tags_by_feature["F-2026-05-27-foo"]}
        assert suffixes == {"spec", "release"}
