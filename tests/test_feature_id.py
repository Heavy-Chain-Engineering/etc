"""Tests for scripts/feature_id.py — atomic F<NNN> feature-ID allocator.

Coverage targets (per spec.md BR-001, BR-003, AC-002 and gray-area GA-006):
- Happy-path single allocation against an empty features dir.
- Happy-path allocation when prior F<NNN> dirs exist (max + 1).
- Concurrent allocation race via threading: two threads racing for the same
  target dir; both must succeed with distinct IDs (the EEXIST retry path).
- F999 ceiling: clear error rather than silent overflow.
- slugify edges: empty string, all-punctuation, length-overflow.

The allocator under test must use POSIX atomic os.mkdir() with EEXIST retry.
"""

from __future__ import annotations

import re
import sys
import threading
from pathlib import Path

import pytest

# Make the scripts/ directory importable as a flat module.
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import feature_id  # noqa: E402, I001  — sys.path inserted above


# ── allocate_next: happy paths ──────────────────────────────────────────


class TestAllocateNextHappyPath:
    def test_should_allocate_f001_when_features_dir_is_empty(
        self, tmp_path: Path
    ) -> None:
        features_dir = tmp_path / "features"
        features_dir.mkdir()

        feature_id_str, feature_path = feature_id.allocate_next(
            features_dir, "first-feature"
        )

        assert feature_id_str == "F001"
        assert feature_path == features_dir / "F001-first-feature"
        assert feature_path.is_dir()

    def test_should_allocate_max_plus_one_when_prior_features_exist(
        self, tmp_path: Path
    ) -> None:
        features_dir = tmp_path / "features"
        features_dir.mkdir()
        (features_dir / "F001-alpha").mkdir()
        (features_dir / "F003-gamma").mkdir()  # gap at F002 — must still pick F004

        feature_id_str, feature_path = feature_id.allocate_next(
            features_dir, "delta"
        )

        assert feature_id_str == "F004"
        assert feature_path == features_dir / "F004-delta"
        assert feature_path.is_dir()

    def test_should_ignore_non_feature_directories_when_computing_max(
        self, tmp_path: Path
    ) -> None:
        features_dir = tmp_path / "features"
        features_dir.mkdir()
        (features_dir / "legacy-slug-only").mkdir()  # grandfathered (GA-002)
        (features_dir / "not-a-feature").mkdir()
        (features_dir / "F002-real").mkdir()

        feature_id_str, _ = feature_id.allocate_next(features_dir, "next")

        assert feature_id_str == "F003"

    def test_should_create_features_dir_when_missing(self, tmp_path: Path) -> None:
        features_dir = tmp_path / "features"  # not yet created

        feature_id_str, feature_path = feature_id.allocate_next(
            features_dir, "bootstrap"
        )

        assert feature_id_str == "F001"
        assert feature_path.is_dir()


# ── allocate_next: concurrent race (BR-003 / AC-002) ────────────────────


class TestAllocateNextConcurrentRace:
    def test_should_allocate_distinct_ids_when_two_threads_race_same_slug(
        self, tmp_path: Path
    ) -> None:
        """Two threads racing with the SAME slug collide on F<NNN>-<slug>.

        This is the canonical EEXIST scenario the GA-006 atomic-mkdir pattern
        guards against: identical target name → exactly one mkdir wins, the
        loser receives FileExistsError and retries at +1. Both callers must
        ultimately receive distinct IDs and both succeed.
        """
        features_dir = tmp_path / "features"
        features_dir.mkdir()

        results: list[tuple[str, Path]] = []
        errors: list[BaseException] = []
        barrier = threading.Barrier(2)
        slug = "shared-target"

        def worker() -> None:
            try:
                barrier.wait(timeout=5)
                results.append(feature_id.allocate_next(features_dir, slug))
            except BaseException as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [
            threading.Thread(target=worker),
            threading.Thread(target=worker),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert errors == []
        assert len(results) == 2
        ids = {r[0] for r in results}
        assert ids == {"F001", "F002"}, f"expected distinct F001/F002, got {ids}"
        for _, path in results:
            assert path.is_dir()

    def test_should_recover_when_target_dir_is_pre_created_between_scan_and_mkdir(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Force the EEXIST retry branch deterministically.

        Wrap os.mkdir so the FIRST call against an ``F\\d{3}-`` target
        pre-creates the colliding directory and raises FileExistsError; the
        allocator must re-read max-existing and retry at +1. We only
        intercept feature-target mkdir calls (name matches ``F\\d{3}-``) so
        an earlier ``Path.mkdir(parents=True, exist_ok=True)`` against the
        features root passes through unaffected.
        """
        features_dir = tmp_path / "features"
        features_dir.mkdir()

        import os as real_os

        original_mkdir = real_os.mkdir
        target_pattern = re.compile(r"^F\d{3}-")
        first_call_intercepted = {"done": False}

        def flaky_mkdir(path: str | Path, mode: int = 0o777) -> None:
            name = Path(path).name
            if (
                not first_call_intercepted["done"]
                and target_pattern.match(name)
            ):
                first_call_intercepted["done"] = True
                original_mkdir(path, mode)
                raise FileExistsError(17, "File exists", str(path))
            original_mkdir(path, mode)

        monkeypatch.setattr(feature_id.os, "mkdir", flaky_mkdir)

        feature_id_str, feature_path = feature_id.allocate_next(
            features_dir, "racy"
        )

        # First attempt was at F001 (collided); retry must land on F002.
        assert first_call_intercepted["done"] is True
        assert feature_id_str == "F002"
        assert feature_path == features_dir / "F002-racy"
        assert feature_path.is_dir()
        # Confirm the collided F001-* directory is also present (created by
        # the simulated competing writer).
        assert (features_dir / "F001-racy").is_dir()


# ── allocate_next: F999 ceiling ─────────────────────────────────────────


class TestAllocateNextCeiling:
    def test_should_raise_feature_id_exhausted_when_f999_is_taken(
        self, tmp_path: Path
    ) -> None:
        features_dir = tmp_path / "features"
        features_dir.mkdir()
        (features_dir / "F999-final").mkdir()

        with pytest.raises(feature_id.FeatureIdExhaustedError) as exc_info:
            feature_id.allocate_next(features_dir, "overflow")

        assert "999" in str(exc_info.value)


# ── slugify ─────────────────────────────────────────────────────────────


class TestSlugify:
    def test_should_kebab_case_when_title_has_spaces_and_caps(self) -> None:
        assert feature_id.slugify("Hello World Feature") == "hello-world-feature"

    def test_should_collapse_punctuation_runs_to_single_hyphen(self) -> None:
        assert feature_id.slugify("foo!!! bar??? baz") == "foo-bar-baz"

    def test_should_strip_leading_and_trailing_hyphens(self) -> None:
        assert feature_id.slugify("  --hello--  ") == "hello"

    def test_should_return_task_fallback_when_input_is_empty(self) -> None:
        assert feature_id.slugify("") == "task"

    def test_should_return_task_fallback_when_input_is_all_punctuation(self) -> None:
        assert feature_id.slugify("!!!???---") == "task"

    def test_should_truncate_when_slug_exceeds_length_cap(self) -> None:
        long_title = "a" * 200
        result = feature_id.slugify(long_title)
        assert len(result) <= 80
        assert result == "a" * 80

    def test_should_truncate_without_trailing_hyphen_when_cap_lands_on_hyphen(
        self,
    ) -> None:
        # Construct a title where char 80 (0-indexed: 79) lands on a hyphen
        # so the truncated slug must rstrip("-") and remain non-empty.
        title = ("word " * 20).strip()  # "word word word ... word"
        result = feature_id.slugify(title)
        assert len(result) <= 80
        assert not result.endswith("-")
        assert result  # non-empty
