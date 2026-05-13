"""Tests for scripts/journey_lineage_check.py (F017 / /build Step 7.4).

The gate enforces that every post-F017 feature has either journey_refs
resolving to docs/mvp/journeys/*.md OR an infrastructure_only sentinel
with a non-empty reason. Legacy features (pre-F017 release tag) pass.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

SCRIPT = Path(__file__).parent.parent / "scripts" / "journey_lineage_check.py"


def _run(feature_dir: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python3", str(SCRIPT), str(feature_dir)],
        capture_output=True,
        text=True,
        timeout=15,
    )


def _make_feature(
    tmp_path: Path,
    state_yaml: str,
    journeys: dict[str, str] | None = None,
) -> Path:
    """Create a synthetic feature directory with the given state.yaml content.

    Also init a git repo at tmp_path so the script's repo_root_from()
    resolves correctly. The F017 release tag is NOT created — that means
    `f017_release_tag_date()` returns None, which the script treats as
    "F017 hasn't shipped yet → skip gate". To test post-F017 behavior,
    tests pass a state.yaml with completed_at AFTER a fake F017 tag date
    (we'll set the tag in tests that need post-F017 semantics).
    """
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True, timeout=10)
    feature_dir = tmp_path / ".etc_sdlc" / "features" / "F999-test-feature"
    feature_dir.mkdir(parents=True)
    (feature_dir / "state.yaml").write_text(state_yaml, encoding="utf-8")
    if journeys:
        journeys_dir = tmp_path / "docs" / "mvp" / "journeys"
        journeys_dir.mkdir(parents=True)
        for name, content in journeys.items():
            (journeys_dir / name).write_text(content, encoding="utf-8")
    return feature_dir


def _create_f017_tag(repo: Path, date_iso: str = "2026-05-13T00:00:00Z") -> None:
    """Stamp a fake F017 release tag at a committable point with a known
    commit date. The script reads the tag's commit date via git log."""
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.email", "test@example.com"],
        check=True, timeout=10,
    )
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.name", "test"],
        check=True, timeout=10,
    )
    # Create at least one file to commit
    (repo / ".gitkeep").write_text("")
    subprocess.run(
        ["git", "-C", str(repo), "add", "-A"],
        check=True, timeout=10,
    )
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-m", "init", "--date", date_iso],
        check=True, timeout=10,
        env={"GIT_AUTHOR_DATE": date_iso, "GIT_COMMITTER_DATE": date_iso,
             "PATH": __import__("os").environ.get("PATH", "")},
    )
    subprocess.run(
        ["git", "-C", str(repo), "tag", "etc/feature/F017/release"],
        check=True, timeout=10,
    )


class TestLegacyFeaturesPass:
    """Features without an F017 release tag (or filed before it) pass."""

    def test_no_f017_tag_passes_with_empty_journey_refs(
        self, tmp_path: Path
    ) -> None:
        state = "spec_phase:\n  completed_at: '2026-04-01T00:00:00Z'\n"
        feature_dir = _make_feature(tmp_path, state)
        # No F017 tag created — gate should skip
        result = _run(feature_dir)
        assert result.returncode == 0

    def test_feature_predating_f017_passes(self, tmp_path: Path) -> None:
        feature_dir = _make_feature(
            tmp_path,
            "spec_phase:\n  completed_at: '2026-04-01T00:00:00Z'\n",
        )
        _create_f017_tag(tmp_path, "2026-05-13T00:00:00Z")
        result = _run(feature_dir)
        assert result.returncode == 0


class TestInfrastructureOnlyPath:
    """Post-F017 features with infrastructure_only: true + reason pass."""

    def test_infrastructure_only_with_reason_passes(self, tmp_path: Path) -> None:
        state = (
            "spec_phase:\n"
            "  completed_at: '2026-06-01T00:00:00Z'\n"
            "  infrastructure_only: true\n"
            "  infrastructure_reason: 'library upgrade Python 3.13'\n"
        )
        feature_dir = _make_feature(tmp_path, state)
        _create_f017_tag(tmp_path, "2026-05-13T00:00:00Z")
        result = _run(feature_dir)
        assert result.returncode == 0

    def test_infrastructure_only_without_reason_fails(self, tmp_path: Path) -> None:
        state = (
            "spec_phase:\n"
            "  completed_at: '2026-06-01T00:00:00Z'\n"
            "  infrastructure_only: true\n"
        )
        feature_dir = _make_feature(tmp_path, state)
        _create_f017_tag(tmp_path, "2026-05-13T00:00:00Z")
        result = _run(feature_dir)
        assert result.returncode == 2
        assert "infrastructure_reason" in result.stderr

    def test_infrastructure_only_with_empty_reason_fails(
        self, tmp_path: Path
    ) -> None:
        state = (
            "spec_phase:\n"
            "  completed_at: '2026-06-01T00:00:00Z'\n"
            "  infrastructure_only: true\n"
            "  infrastructure_reason: ''\n"
        )
        feature_dir = _make_feature(tmp_path, state)
        _create_f017_tag(tmp_path, "2026-05-13T00:00:00Z")
        result = _run(feature_dir)
        assert result.returncode == 2


class TestJourneyRefsPath:
    """Post-F017 features with journey_refs resolving to files pass."""

    def test_journey_refs_resolving_to_existing_journey_passes(
        self, tmp_path: Path
    ) -> None:
        state = (
            "spec_phase:\n"
            "  completed_at: '2026-06-01T00:00:00Z'\n"
            "  journey_refs:\n"
            "    - J-007\n"
        )
        feature_dir = _make_feature(
            tmp_path,
            state,
            journeys={"J-007-test-journey.md": "# J-007\nContent.\n"},
        )
        _create_f017_tag(tmp_path, "2026-05-13T00:00:00Z")
        result = _run(feature_dir)
        assert result.returncode == 0

    def test_journey_refs_with_missing_journey_file_fails(
        self, tmp_path: Path
    ) -> None:
        state = (
            "spec_phase:\n"
            "  completed_at: '2026-06-01T00:00:00Z'\n"
            "  journey_refs:\n"
            "    - J-999\n"
        )
        feature_dir = _make_feature(tmp_path, state)
        _create_f017_tag(tmp_path, "2026-05-13T00:00:00Z")
        result = _run(feature_dir)
        assert result.returncode == 2
        assert "J-999" in result.stdout

    def test_empty_journey_refs_fails(self, tmp_path: Path) -> None:
        state = (
            "spec_phase:\n"
            "  completed_at: '2026-06-01T00:00:00Z'\n"
            "  journey_refs: []\n"
        )
        feature_dir = _make_feature(tmp_path, state)
        _create_f017_tag(tmp_path, "2026-05-13T00:00:00Z")
        result = _run(feature_dir)
        assert result.returncode == 2
        assert "JOURNEY LINEAGE MISSING" in result.stdout


class TestBlockReport:
    """AC-09: block-stop report includes remediation hints."""

    def test_report_includes_journey_capture_option(self, tmp_path: Path) -> None:
        state = (
            "spec_phase:\n"
            "  completed_at: '2026-06-01T00:00:00Z'\n"
            "  journey_refs: []\n"
        )
        feature_dir = _make_feature(tmp_path, state)
        _create_f017_tag(tmp_path, "2026-05-13T00:00:00Z")
        result = _run(feature_dir)
        assert result.returncode == 2
        assert "/journey" in result.stdout

    def test_report_includes_infrastructure_option(self, tmp_path: Path) -> None:
        state = (
            "spec_phase:\n"
            "  completed_at: '2026-06-01T00:00:00Z'\n"
            "  journey_refs: []\n"
        )
        feature_dir = _make_feature(tmp_path, state)
        _create_f017_tag(tmp_path, "2026-05-13T00:00:00Z")
        result = _run(feature_dir)
        assert result.returncode == 2
        assert "infrastructure_only" in result.stdout

    def test_report_includes_skip_flag(self, tmp_path: Path) -> None:
        state = (
            "spec_phase:\n"
            "  completed_at: '2026-06-01T00:00:00Z'\n"
            "  journey_refs: []\n"
        )
        feature_dir = _make_feature(tmp_path, state)
        _create_f017_tag(tmp_path, "2026-05-13T00:00:00Z")
        result = _run(feature_dir)
        assert result.returncode == 2
        assert "--skip-journey-check" in result.stdout


class TestUsage:
    def test_missing_arg_returns_one(self) -> None:
        result = subprocess.run(
            ["python3", str(SCRIPT)],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 1

    def test_nonexistent_feature_dir_returns_one(self, tmp_path: Path) -> None:
        result = _run(tmp_path / "does-not-exist")
        assert result.returncode == 1
