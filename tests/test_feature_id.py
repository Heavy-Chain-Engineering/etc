"""Tests for scripts/feature_id.py — atomic F<NNN> feature-ID allocator.

Coverage targets (per spec.md BR-001, BR-003, AC-002 and gray-area GA-006):
- Happy-path single allocation against an empty features dir.
- Happy-path allocation when prior F<NNN> dirs exist (max + 1).
- Concurrent allocation race via threading: two threads racing for the same
  target dir; both must succeed with distinct IDs (the EEXIST retry path).
- F999 ceiling: clear error rather than silent overflow.
- slugify edges: empty string, all-punctuation, length-overflow.

F009 additions (BR-001, BR-002, BR-003):
- ``_scan_max_feature_id`` rglobs across ``.etc_sdlc/`` so the legacy flat
  path, ``features/active/``, ``features/shipped/``, and ``rejections/`` all
  contribute to the max-id calculation.
- ``allocate_next`` lands new features under ``features/active/`` instead of
  the legacy flat ``features/`` location.
- A new public ``resolve_feature_path(feature_id, etc_sdlc_root)`` function
  checks four locations in priority order and returns the first match.

The allocator under test must use POSIX atomic os.mkdir() with EEXIST retry.
"""

from __future__ import annotations

import re
import subprocess
import sys
import threading
from pathlib import Path

import pytest

# Make the scripts/ directory importable as a flat module.
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import feature_id  # pyright: ignore[reportMissingImports]  # noqa: E402, I001  — sys.path inserted above


# ── allocate_next: happy paths ──────────────────────────────────────────


class TestAllocateNextHappyPath:
    def test_should_allocate_f001_under_active_when_features_dir_is_empty(
        self, tmp_path: Path
    ) -> None:
        features_dir = tmp_path / "features"
        features_dir.mkdir()

        feature_id_str, feature_path = feature_id.allocate_next(
            features_dir, "first-feature"
        )

        assert feature_id_str == "F001"
        assert feature_path == features_dir / "active" / "F001-first-feature"
        assert feature_path.is_dir()

    def test_should_allocate_max_plus_one_when_prior_features_exist(
        self, tmp_path: Path
    ) -> None:
        # Legacy flat F001/F003 entries simulate F001-F008 grandfathered state.
        features_dir = tmp_path / "features"
        features_dir.mkdir()
        (features_dir / "F001-alpha").mkdir()
        (features_dir / "F003-gamma").mkdir()  # gap at F002 — must still pick F004

        feature_id_str, feature_path = feature_id.allocate_next(
            features_dir, "delta"
        )

        assert feature_id_str == "F004"
        assert feature_path == features_dir / "active" / "F004-delta"
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
        assert feature_path.parent == features_dir / "active"


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
        assert feature_path == features_dir / "active" / "F002-racy"
        assert feature_path.is_dir()
        # Confirm the collided F001-* directory is also present (created by
        # the simulated competing writer) under active/.
        assert (features_dir / "active" / "F001-racy").is_dir()


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

    def test_should_raise_feature_id_exhausted_when_f999_is_under_active(
        self, tmp_path: Path
    ) -> None:
        # F009 BR-001: rglob must find F999 even when nested under active/.
        features_dir = tmp_path / "features"
        (features_dir / "active").mkdir(parents=True)
        (features_dir / "active" / "F999-final").mkdir()

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


# ── CLI subcommand: allocate-next ───────────────────────────────────────


_SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "feature_id.py"


class TestAllocateNextCLI:
    """Smoke tests for the `allocate-next` CLI subcommand.

    These run via subprocess with ``cwd=tmp_path`` to guarantee no
    ``scripts/`` directory leaks onto CWD-derived sys.path. Skills
    invoke this script as ``python3 ~/.claude/scripts/feature_id.py
    allocate-next ...`` from arbitrary projects, so it must work without
    being importable as a module.
    """

    def test_should_allocate_next_via_subprocess_from_unrelated_cwd(
        self, tmp_path: Path
    ) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(_SCRIPT_PATH),
                "allocate-next",
                str(tmp_path),
                "my-feature",
            ],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert result.returncode == 0, (
            f"CLI exited {result.returncode}; stderr={result.stderr!r}"
        )
        # Single newline-terminated line: "F001 <path>\n"
        assert result.stdout.endswith("\n")
        line = result.stdout.rstrip("\n")
        assert "\n" not in line  # exactly one line of output
        assert line.startswith("F001 "), f"unexpected stdout: {result.stdout!r}"

        # The feature path is everything after "F001 "
        feature_path = Path(line[len("F001 "):])
        assert feature_path.is_dir(), f"feature dir not created: {feature_path}"
        # F009 BR-002: new features land under <features_dir>/active/.
        assert feature_path.parent == tmp_path / "active"
        assert feature_path.name == "F001-my-feature"

    def test_should_allocate_f002_when_f001_exists(self, tmp_path: Path) -> None:
        first = subprocess.run(
            [
                sys.executable,
                str(_SCRIPT_PATH),
                "allocate-next",
                str(tmp_path),
                "alpha",
            ],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert first.returncode == 0, first.stderr
        assert first.stdout.startswith("F001 ")

        second = subprocess.run(
            [
                sys.executable,
                str(_SCRIPT_PATH),
                "allocate-next",
                str(tmp_path),
                "beta",
            ],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert second.returncode == 0, second.stderr
        assert second.stdout.startswith("F002 ")
        line = second.stdout.rstrip("\n")
        feature_path = Path(line[len("F002 "):])
        assert feature_path.is_dir()
        assert feature_path.name == "F002-beta"

    def test_should_exit_nonzero_when_features_dir_parent_missing(
        self, tmp_path: Path
    ) -> None:
        # Construct a path whose parent does not exist. mkdir(parents=True)
        # would normally create it, so we force a real failure by pointing
        # at a path under an existing FILE — that makes the parent
        # un-creatable (cannot mkdir under a regular file).
        blocker = tmp_path / "not-a-dir"
        blocker.write_text("blocking file\n")
        impossible_features_dir = blocker / "features"

        result = subprocess.run(
            [
                sys.executable,
                str(_SCRIPT_PATH),
                "allocate-next",
                str(impossible_features_dir),
                "x",
            ],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert result.returncode != 0
        assert result.stderr.strip(), "expected a non-empty stderr message"


# ── F009 BR-001: rglob across .etc_sdlc/ ────────────────────────────────


class TestScanMaxFeatureIdRglob:
    """``_scan_max_feature_id`` must find F<NNN> dirs at any depth.

    The scan is rooted at the ``.etc_sdlc/`` directory and inspects each
    candidate name against ``_FEATURE_DIR_PATTERN``. Legacy flat path,
    ``features/active/``, ``features/shipped/``, and ``rejections/`` all
    contribute to the max-id calculation.
    """

    def _build_etc_sdlc_tree(self, tmp_path: Path) -> Path:
        etc_sdlc = tmp_path / ".etc_sdlc"
        (etc_sdlc / "features").mkdir(parents=True)
        (etc_sdlc / "features" / "active").mkdir()
        (etc_sdlc / "features" / "shipped").mkdir()
        (etc_sdlc / "rejections").mkdir()
        return etc_sdlc

    def test_should_return_zero_when_etc_sdlc_has_no_feature_dirs(
        self, tmp_path: Path
    ) -> None:
        etc_sdlc = self._build_etc_sdlc_tree(tmp_path)

        assert feature_id._scan_max_feature_id(etc_sdlc / "features") == 0

    def test_should_find_legacy_flat_feature_when_only_legacy_present(
        self, tmp_path: Path
    ) -> None:
        etc_sdlc = self._build_etc_sdlc_tree(tmp_path)
        (etc_sdlc / "features" / "F005-legacy").mkdir()

        assert feature_id._scan_max_feature_id(etc_sdlc / "features") == 5

    def test_should_find_active_feature_when_only_active_present(
        self, tmp_path: Path
    ) -> None:
        etc_sdlc = self._build_etc_sdlc_tree(tmp_path)
        (etc_sdlc / "features" / "active" / "F012-in-flight").mkdir()

        assert feature_id._scan_max_feature_id(etc_sdlc / "features") == 12

    def test_should_find_shipped_feature_when_only_shipped_present(
        self, tmp_path: Path
    ) -> None:
        etc_sdlc = self._build_etc_sdlc_tree(tmp_path)
        (etc_sdlc / "features" / "shipped" / "F020-done").mkdir()

        assert feature_id._scan_max_feature_id(etc_sdlc / "features") == 20

    def test_should_find_rejected_feature_when_only_rejection_present(
        self, tmp_path: Path
    ) -> None:
        etc_sdlc = self._build_etc_sdlc_tree(tmp_path)
        (etc_sdlc / "rejections" / "F031-killed").mkdir()

        assert feature_id._scan_max_feature_id(etc_sdlc / "features") == 31

    def test_should_return_max_when_features_exist_in_all_four_locations(
        self, tmp_path: Path
    ) -> None:
        etc_sdlc = self._build_etc_sdlc_tree(tmp_path)
        (etc_sdlc / "features" / "F001-legacy").mkdir()
        (etc_sdlc / "features" / "active" / "F050-active").mkdir()
        (etc_sdlc / "features" / "shipped" / "F042-shipped").mkdir()
        (etc_sdlc / "rejections" / "F099-killed").mkdir()

        assert feature_id._scan_max_feature_id(etc_sdlc / "features") == 99

    def test_should_ignore_unrelated_dirs_matching_no_feature_pattern(
        self, tmp_path: Path
    ) -> None:
        etc_sdlc = self._build_etc_sdlc_tree(tmp_path)
        (etc_sdlc / "features" / "active" / "F008-real").mkdir()
        (etc_sdlc / "features" / "active" / "not-a-feature").mkdir()
        (etc_sdlc / "rejections" / "another-non-feature").mkdir()

        assert feature_id._scan_max_feature_id(etc_sdlc / "features") == 8

    def test_should_allocate_max_plus_one_using_rglob_when_features_split_across_locations(
        self, tmp_path: Path
    ) -> None:
        # End-to-end: allocator pulls max from rglob across legacy + active +
        # shipped + rejections, lands new dir under active/.
        etc_sdlc = self._build_etc_sdlc_tree(tmp_path)
        (etc_sdlc / "features" / "F001-legacy").mkdir()
        (etc_sdlc / "features" / "active" / "F003-active").mkdir()
        (etc_sdlc / "features" / "shipped" / "F005-shipped").mkdir()
        (etc_sdlc / "rejections" / "F007-killed").mkdir()

        feature_id_str, feature_path = feature_id.allocate_next(
            etc_sdlc / "features", "next-up"
        )

        assert feature_id_str == "F008"
        assert feature_path == etc_sdlc / "features" / "active" / "F008-next-up"
        assert feature_path.is_dir()


# ── F009 BR-002: allocate_next places under active/ ─────────────────────


class TestAllocateNextActivePlacement:
    def test_should_create_active_parent_when_features_dir_lacks_active_subdir(
        self, tmp_path: Path
    ) -> None:
        features_dir = tmp_path / "features"
        features_dir.mkdir()
        # active/ does not exist yet — allocator must create it lazily.

        _, feature_path = feature_id.allocate_next(features_dir, "lazy-parent")

        assert (features_dir / "active").is_dir()
        assert feature_path.parent == features_dir / "active"

    def test_should_reuse_existing_active_subdir_when_present(
        self, tmp_path: Path
    ) -> None:
        features_dir = tmp_path / "features"
        (features_dir / "active").mkdir(parents=True)

        _, feature_path = feature_id.allocate_next(features_dir, "reuse-parent")

        assert feature_path == features_dir / "active" / "F001-reuse-parent"
        assert feature_path.is_dir()


# ── F009 BR-003: resolve_feature_path ───────────────────────────────────


class TestResolveFeaturePath:
    """``resolve_feature_path`` checks four locations in priority order.

    Priority: legacy flat → active → shipped → rejections. Returns the first
    match as a ``Path`` (resolved), or ``None`` if no match is found anywhere.
    Slug-suffix matching uses ``glob('F<NNN>-*')`` so callers pass only the
    F-ID.
    """

    def _build_etc_sdlc_tree(self, tmp_path: Path) -> Path:
        etc_sdlc = tmp_path / ".etc_sdlc"
        (etc_sdlc / "features" / "active").mkdir(parents=True)
        (etc_sdlc / "features" / "shipped").mkdir()
        (etc_sdlc / "rejections").mkdir()
        return etc_sdlc

    def test_should_return_legacy_flat_path_when_feature_at_legacy_location(
        self, tmp_path: Path
    ) -> None:
        etc_sdlc = self._build_etc_sdlc_tree(tmp_path)
        legacy = etc_sdlc / "features" / "F001-bootstrap"
        legacy.mkdir()

        result = feature_id.resolve_feature_path("F001", etc_sdlc)

        assert result == legacy.resolve()

    def test_should_return_active_path_when_feature_at_active_location(
        self, tmp_path: Path
    ) -> None:
        etc_sdlc = self._build_etc_sdlc_tree(tmp_path)
        active = etc_sdlc / "features" / "active" / "F042-in-flight"
        active.mkdir()

        result = feature_id.resolve_feature_path("F042", etc_sdlc)

        assert result == active.resolve()

    def test_should_return_shipped_path_when_feature_at_shipped_location(
        self, tmp_path: Path
    ) -> None:
        etc_sdlc = self._build_etc_sdlc_tree(tmp_path)
        shipped = etc_sdlc / "features" / "shipped" / "F020-done"
        shipped.mkdir()

        result = feature_id.resolve_feature_path("F020", etc_sdlc)

        assert result == shipped.resolve()

    def test_should_return_rejection_path_when_feature_at_rejections_location(
        self, tmp_path: Path
    ) -> None:
        etc_sdlc = self._build_etc_sdlc_tree(tmp_path)
        rejected = etc_sdlc / "rejections" / "F099-killed"
        rejected.mkdir()

        result = feature_id.resolve_feature_path("F099", etc_sdlc)

        assert result == rejected.resolve()

    def test_should_return_none_when_feature_id_absent_in_all_locations(
        self, tmp_path: Path
    ) -> None:
        etc_sdlc = self._build_etc_sdlc_tree(tmp_path)

        assert feature_id.resolve_feature_path("F123", etc_sdlc) is None

    def test_should_prefer_legacy_flat_when_feature_exists_in_multiple_locations(
        self, tmp_path: Path
    ) -> None:
        etc_sdlc = self._build_etc_sdlc_tree(tmp_path)
        legacy = etc_sdlc / "features" / "F050-collision"
        legacy.mkdir()
        # Construct an unlikely-but-defensive collision in active/.
        (etc_sdlc / "features" / "active" / "F050-collision").mkdir()

        result = feature_id.resolve_feature_path("F050", etc_sdlc)

        assert result == legacy.resolve()

    def test_should_prefer_active_over_shipped_and_rejections(
        self, tmp_path: Path
    ) -> None:
        etc_sdlc = self._build_etc_sdlc_tree(tmp_path)
        active = etc_sdlc / "features" / "active" / "F060-priority"
        active.mkdir()
        (etc_sdlc / "features" / "shipped" / "F060-priority").mkdir()
        (etc_sdlc / "rejections" / "F060-priority").mkdir()

        result = feature_id.resolve_feature_path("F060", etc_sdlc)

        assert result == active.resolve()

    def test_should_prefer_shipped_over_rejections(self, tmp_path: Path) -> None:
        etc_sdlc = self._build_etc_sdlc_tree(tmp_path)
        shipped = etc_sdlc / "features" / "shipped" / "F070-priority"
        shipped.mkdir()
        (etc_sdlc / "rejections" / "F070-priority").mkdir()

        result = feature_id.resolve_feature_path("F070", etc_sdlc)

        assert result == shipped.resolve()

    def test_should_return_none_when_feature_id_is_malformed(
        self, tmp_path: Path
    ) -> None:
        etc_sdlc = self._build_etc_sdlc_tree(tmp_path)

        # Malformed inputs must return None per F009 Security Considerations
        # item 1 (path-traversal guard).
        assert feature_id.resolve_feature_path("not-a-feature", etc_sdlc) is None
        assert feature_id.resolve_feature_path("F12", etc_sdlc) is None  # too short
        assert feature_id.resolve_feature_path("F1234", etc_sdlc) is None  # too long
        assert feature_id.resolve_feature_path("", etc_sdlc) is None
        assert feature_id.resolve_feature_path("FABC", etc_sdlc) is None

    def test_should_return_none_when_feature_id_attempts_path_traversal(
        self, tmp_path: Path
    ) -> None:
        etc_sdlc = self._build_etc_sdlc_tree(tmp_path)

        # Path-traversal markers must not bypass the regex guard.
        assert feature_id.resolve_feature_path("../etc/passwd", etc_sdlc) is None
        assert feature_id.resolve_feature_path("F001/../../etc", etc_sdlc) is None
        assert feature_id.resolve_feature_path("/F001", etc_sdlc) is None

    def test_should_match_feature_with_any_slug_suffix(self, tmp_path: Path) -> None:
        etc_sdlc = self._build_etc_sdlc_tree(tmp_path)
        target = etc_sdlc / "features" / "active" / "F015-some-arbitrary-slug-name"
        target.mkdir()

        result = feature_id.resolve_feature_path("F015", etc_sdlc)

        assert result == target.resolve()

    def test_should_not_match_partial_id_prefix(self, tmp_path: Path) -> None:
        # Caller passes "F01" — must not match "F015-..." or "F010-...".
        etc_sdlc = self._build_etc_sdlc_tree(tmp_path)
        (etc_sdlc / "features" / "active" / "F015-foo").mkdir()
        (etc_sdlc / "features" / "active" / "F010-bar").mkdir()

        # "F01" is malformed (3-digit required) → returns None via regex guard.
        assert feature_id.resolve_feature_path("F01", etc_sdlc) is None
