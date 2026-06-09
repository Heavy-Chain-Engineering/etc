"""Tests for scripts/cross_feature_collision_check.py (F016 / R2).

Synthetic feature directories under pytest tmp_path. The detector
identifies cross-feature file-set overlaps; tests verify it correctly
excludes the current feature, shipped/, and rejections/.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

SCRIPT = Path(__file__).parent.parent / "scripts" / "cross_feature_collision_check.py"


def _run(feature_dir: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python3", str(SCRIPT), str(feature_dir)],
        capture_output=True,
        text=True,
        timeout=15,
    )


def _make_feature(
    tmp_path: Path,
    feature_id: str,
    slug: str = "test",
    files_in_scope: list[str] | None = None,
    location: str = "flat",
    released: bool = False,
) -> Path:
    """Create a feature directory with one task whose files_in_scope is
    the given list. `location` can be 'flat' (features/F<NNN>-...),
    'active' (features/active/F<NNN>-...), 'shipped', or 'rejections'.

    When `released` is True, a state.yaml with a terminal `build.completed_at`
    timestamp is written. This models a feature that shipped IN PLACE (flat or
    active layout) without ever being moved into shipped/ — the #56 false
    positive: such a feature is done and must not be treated as in-flight.
    """
    features_root = tmp_path / ".etc_sdlc" / "features"
    if location == "flat":
        parent = features_root
    elif location == "active":
        parent = features_root / "active"
    elif location == "shipped":
        parent = features_root / "shipped"
    elif location == "rejections":
        parent = features_root / "rejections"
    else:
        raise ValueError(f"unknown location {location!r}")
    feature_dir = parent / f"{feature_id}-{slug}"
    (feature_dir / "tasks").mkdir(parents=True)
    if files_in_scope is not None:
        # Write a minimal valid task YAML
        files_yaml = "\n".join(f"  - {f}" for f in files_in_scope)
        (feature_dir / "tasks" / "001-test.yaml").write_text(
            f"task_id: '001'\n"
            f"title: test task\n"
            f"status: pending\n"
            f"files_in_scope:\n{files_yaml}\n",
            encoding="utf-8",
        )
    if released:
        (feature_dir / "state.yaml").write_text(
            "build:\n"
            "  current_step: 8\n"
            "  completed_at: '2026-05-01T22:50:55.938959+00:00'\n",
            encoding="utf-8",
        )
    return feature_dir


class TestNoCollisions:
    def test_no_other_features_returns_zero(self, tmp_path: Path) -> None:
        current = _make_feature(tmp_path, "F100", files_in_scope=["src/a.py"])
        result = _run(current)
        assert result.returncode == 0

    def test_other_features_with_disjoint_files_returns_zero(
        self, tmp_path: Path
    ) -> None:
        current = _make_feature(tmp_path, "F100", files_in_scope=["src/a.py"])
        _make_feature(tmp_path, "F101", files_in_scope=["src/b.py"])
        result = _run(current)
        assert result.returncode == 0


class TestCollisions:
    def test_overlap_with_another_in_flight_returns_two(
        self, tmp_path: Path
    ) -> None:
        current = _make_feature(tmp_path, "F100", files_in_scope=["src/shared.py"])
        _make_feature(tmp_path, "F101", files_in_scope=["src/shared.py"])
        result = _run(current)
        assert result.returncode == 2

    def test_collision_report_lists_file_and_other_feature_id(
        self, tmp_path: Path
    ) -> None:
        current = _make_feature(tmp_path, "F100", files_in_scope=["src/shared.py"])
        _make_feature(tmp_path, "F101", files_in_scope=["src/shared.py"])
        result = _run(current)
        assert "src/shared.py" in result.stdout
        assert "F101" in result.stdout

    def test_collision_with_multiple_other_features(self, tmp_path: Path) -> None:
        current = _make_feature(tmp_path, "F100", files_in_scope=["src/shared.py"])
        _make_feature(tmp_path, "F101", files_in_scope=["src/shared.py"])
        _make_feature(tmp_path, "F102", files_in_scope=["src/shared.py"])
        result = _run(current)
        assert result.returncode == 2
        assert "F101" in result.stdout
        assert "F102" in result.stdout

    def test_active_subdir_features_are_scanned(self, tmp_path: Path) -> None:
        """Per F009, allocator output goes to features/active/F<NNN>-...
        The detector MUST scan both flat path AND active/."""
        current = _make_feature(tmp_path, "F100", files_in_scope=["src/shared.py"])
        _make_feature(tmp_path, "F101", files_in_scope=["src/shared.py"], location="active")
        result = _run(current)
        assert result.returncode == 2
        assert "F101" in result.stdout


class TestExclusions:
    def test_shipped_features_are_excluded(self, tmp_path: Path) -> None:
        """Shipped features are done — they won't generate new conflicts."""
        current = _make_feature(tmp_path, "F100", files_in_scope=["src/shared.py"])
        _make_feature(tmp_path, "F099", files_in_scope=["src/shared.py"], location="shipped")
        result = _run(current)
        assert result.returncode == 0

    def test_rejections_are_excluded(self, tmp_path: Path) -> None:
        """Rejected specs aren't in flight either."""
        current = _make_feature(tmp_path, "F100", files_in_scope=["src/shared.py"])
        _make_feature(tmp_path, "F098", files_in_scope=["src/shared.py"], location="rejections")
        result = _run(current)
        assert result.returncode == 0

    def test_should_exclude_feature_released_in_place_when_completed_at_is_set(
        self, tmp_path: Path
    ) -> None:
        """#56 — a feature that shipped IN PLACE (flat layout, never moved to
        shipped/) carries build.completed_at. It is done and must not produce a
        cross-feature collision even though it claims the same file."""
        current = _make_feature(tmp_path, "F100", files_in_scope=["src/shared.py"])
        _make_feature(
            tmp_path,
            "F099",
            files_in_scope=["src/shared.py"],
            location="flat",
            released=True,
        )
        result = _run(current)
        assert result.returncode == 0, result.stdout

    def test_should_still_collide_with_active_feature_alongside_released_one(
        self, tmp_path: Path
    ) -> None:
        """#56 control — excluding released features must NOT suppress a real
        collision from an in-flight (not-yet-completed) feature."""
        current = _make_feature(tmp_path, "F100", files_in_scope=["src/shared.py"])
        _make_feature(
            tmp_path,
            "F099",
            files_in_scope=["src/shared.py"],
            location="flat",
            released=True,
        )
        _make_feature(
            tmp_path, "F101", files_in_scope=["src/shared.py"], location="active"
        )
        result = _run(current)
        assert result.returncode == 2
        assert "F101" in result.stdout
        assert "F099" not in result.stdout

    def test_self_excluded_from_collision_check(self, tmp_path: Path) -> None:
        """The current feature's OWN files don't count as collisions."""
        current = _make_feature(tmp_path, "F100", files_in_scope=["src/a.py", "src/b.py"])
        # No other features at all
        result = _run(current)
        assert result.returncode == 0


class TestEdgeCases:
    def test_task_yaml_without_files_in_scope_is_skipped(self, tmp_path: Path) -> None:
        current = _make_feature(tmp_path, "F100", files_in_scope=["src/a.py"])
        # Create a feature whose task YAML has NO files_in_scope field
        other_dir = tmp_path / ".etc_sdlc" / "features" / "F101-no-files"
        (other_dir / "tasks").mkdir(parents=True)
        (other_dir / "tasks" / "001.yaml").write_text(
            "task_id: '001'\ntitle: t\nstatus: pending\n", encoding="utf-8"
        )
        result = _run(current)
        assert result.returncode == 0

    def test_current_feature_with_no_files_returns_zero(self, tmp_path: Path) -> None:
        """Pre-decomposition (before Step 3), files_in_scope is empty —
        nothing to compare against. Return 0 (no collisions possible)."""
        current = _make_feature(tmp_path, "F100", files_in_scope=[])
        _make_feature(tmp_path, "F101", files_in_scope=["src/a.py"])
        result = _run(current)
        assert result.returncode == 0

    def test_missing_feature_dir_returns_one(self, tmp_path: Path) -> None:
        result = _run(tmp_path / "does-not-exist")
        assert result.returncode == 1

    def test_missing_arg_returns_one(self) -> None:
        result = subprocess.run(
            ["python3", str(SCRIPT)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 1


class TestReportFormat:
    def test_collision_report_includes_resolution_options(
        self, tmp_path: Path
    ) -> None:
        current = _make_feature(tmp_path, "F100", files_in_scope=["src/shared.py"])
        _make_feature(tmp_path, "F101", files_in_scope=["src/shared.py"])
        result = _run(current)
        assert result.returncode == 2
        # AC-05 + AC-06: report mentions Cancel / Proceed / Serialize
        assert "Cancel" in result.stdout
        assert "Proceed with risk" in result.stdout
        assert "Serialize" in result.stdout

    def test_collision_report_mentions_autonomous_mode_behavior(
        self, tmp_path: Path
    ) -> None:
        current = _make_feature(tmp_path, "F100", files_in_scope=["src/shared.py"])
        _make_feature(tmp_path, "F101", files_in_scope=["src/shared.py"])
        result = _run(current)
        assert result.returncode == 2
        # AC-07: report mentions autonomous-mode behavior
        assert "autonomous" in result.stdout.lower()
        assert "state.yaml" in result.stdout
