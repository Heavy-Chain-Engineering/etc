"""Tests for feature_id.allocate_temp under the date-based revision.

REVISION HISTORY:
- F023 (original): tested ``Ftmp-<8-char-hex>`` form. Those tests are
  REPLACED in this file (not preserved with skipif) because the
  Ftmp-<hex> form is no longer produced by allocate_temp. The legacy
  regex constants (_TEMP_ID_PATTERN, _TEMP_DIR_PATTERN, _ADR_TEMP_PATTERN)
  remain in feature_id.py only as backward-compat readers for any
  in-flight Ftmp-<hex> directories from the F021-F026 era; no new
  allocate_temp call produces that form.
- Current: tests the date-based ``F-YYYY-MM-DD-<slug>`` form. See the
  revision ADR superseding ADR-F023-001 for the format rationale.
"""

from __future__ import annotations

import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts import feature_id  # noqa: E402

_DATED_ID_REGEX = re.compile(r"^F-\d{4}-\d{2}-\d{2}-[a-z][a-z0-9-]*$")


def _today_utc() -> str:
    """Return today's UTC date as ``YYYY-MM-DD``."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


class TestAllocateTempHappyPath:
    """allocate_temp returns ``F-YYYY-MM-DD-<slug>`` and creates the dir."""

    def test_should_return_dated_id_matching_regex_when_slug_is_valid(
        self, tmp_path: Path
    ) -> None:
        etc_sdlc_root = tmp_path / ".etc_sdlc"

        feature_id_value, _ = feature_id.allocate_temp(
            "test-feature", etc_sdlc_root
        )

        assert _DATED_ID_REGEX.match(feature_id_value), (
            f"feature_id {feature_id_value!r} does not match "
            f"^F-\\d{{4}}-\\d{{2}}-\\d{{2}}-<slug>$"
        )

    def test_should_include_todays_utc_date_in_returned_id(
        self, tmp_path: Path
    ) -> None:
        etc_sdlc_root = tmp_path / ".etc_sdlc"

        feature_id_value, _ = feature_id.allocate_temp(
            "test-feature", etc_sdlc_root
        )

        today = _today_utc()
        assert today in feature_id_value, (
            f"feature_id {feature_id_value!r} missing today's UTC date "
            f"{today!r}"
        )

    def test_should_create_active_dir_with_id_as_name(
        self, tmp_path: Path
    ) -> None:
        etc_sdlc_root = tmp_path / ".etc_sdlc"

        feature_id_value, feature_path = feature_id.allocate_temp(
            "test-feature", etc_sdlc_root
        )

        assert feature_path.is_dir()
        # Per the revision: dir name IS the feature_id (no separate
        # -<slug> suffix segment).
        assert feature_path.name == feature_id_value
        assert feature_path.parent.name == "active"

    def test_should_write_initial_state_yaml_to_new_dir(
        self, tmp_path: Path
    ) -> None:
        etc_sdlc_root = tmp_path / ".etc_sdlc"

        _, feature_path = feature_id.allocate_temp(
            "test-feature", etc_sdlc_root
        )

        state_path = feature_path / "state.yaml"
        assert state_path.is_file()


class TestAllocateTempCollision:
    """Same-day same-slug collisions auto-suffix with ``-2``, ``-3``, ..."""

    def test_should_auto_suffix_when_same_slug_called_twice_same_day(
        self, tmp_path: Path
    ) -> None:
        etc_sdlc_root = tmp_path / ".etc_sdlc"

        first_id, _ = feature_id.allocate_temp("dup-slug", etc_sdlc_root)
        second_id, _ = feature_id.allocate_temp("dup-slug", etc_sdlc_root)

        assert first_id != second_id
        assert second_id == f"{first_id}-2"

    def test_should_continue_auto_suffix_for_third_collision(
        self, tmp_path: Path
    ) -> None:
        etc_sdlc_root = tmp_path / ".etc_sdlc"

        first_id, _ = feature_id.allocate_temp("dup-slug", etc_sdlc_root)
        feature_id.allocate_temp("dup-slug", etc_sdlc_root)
        third_id, _ = feature_id.allocate_temp("dup-slug", etc_sdlc_root)

        assert third_id == f"{first_id}-3"


class TestAllocateTempSecurityValidation:
    """Slug validation: rejects '..', absolute paths, and over-long input."""

    def test_should_raise_value_error_when_slug_contains_path_traversal(
        self, tmp_path: Path
    ) -> None:
        with pytest.raises(ValueError, match="path-traversal"):
            feature_id.allocate_temp("../escape", tmp_path / ".etc_sdlc")

    def test_should_raise_value_error_when_slug_starts_with_slash(
        self, tmp_path: Path
    ) -> None:
        with pytest.raises(ValueError, match="absolute path"):
            feature_id.allocate_temp("/absolute", tmp_path / ".etc_sdlc")

    def test_should_raise_value_error_when_slug_exceeds_64_chars(
        self, tmp_path: Path
    ) -> None:
        long_slug = "x" * 65
        with pytest.raises(ValueError, match="exceeds"):
            feature_id.allocate_temp(long_slug, tmp_path / ".etc_sdlc")

    def test_should_raise_value_error_when_slug_is_empty(
        self, tmp_path: Path
    ) -> None:
        with pytest.raises(ValueError, match="empty"):
            feature_id.allocate_temp("", tmp_path / ".etc_sdlc")


class TestAllocateTempCLI:
    """The ``allocate-temp`` CLI subcommand prints ``<id> <path>``."""

    def test_should_print_dated_id_and_feature_path_to_stdout(
        self, tmp_path: Path
    ) -> None:
        etc_sdlc_root = tmp_path / ".etc_sdlc"
        etc_sdlc_root.mkdir()

        result = subprocess.run(
            [
                sys.executable,
                str(_REPO_ROOT / "scripts" / "feature_id.py"),
                "allocate-temp",
                str(etc_sdlc_root),
                "cli-test",
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 0, result.stderr
        parts = result.stdout.strip().split(" ", maxsplit=1)
        assert len(parts) == 2
        feature_id_value, feature_path = parts
        assert _DATED_ID_REGEX.match(feature_id_value)
        assert feature_path.endswith(feature_id_value)


class TestResolveFinalIdOnDatedForm:
    """resolve_final_id is a no-op for date-based feature IDs.

    Date-based form is final by construction; /build Step 7c.0 has no
    rename to perform.
    """

    def test_should_return_input_unchanged_when_called_with_dated_id(
        self, tmp_path: Path
    ) -> None:
        etc_sdlc_root = tmp_path / ".etc_sdlc"

        feature_id_value, _ = feature_id.allocate_temp(
            "noop-test", etc_sdlc_root
        )

        result = feature_id.resolve_final_id(
            feature_id_value, etc_sdlc_root, repo_root=tmp_path
        )
        assert result == feature_id_value


class TestResolveFeaturePathOnDatedForm:
    """resolve_feature_path finds date-based dirs via exact-match."""

    def test_should_find_dated_dir_under_active(
        self, tmp_path: Path
    ) -> None:
        etc_sdlc_root = tmp_path / ".etc_sdlc"

        feature_id_value, feature_path = feature_id.allocate_temp(
            "resolver-test", etc_sdlc_root
        )

        resolved = feature_id.resolve_feature_path(
            feature_id_value, etc_sdlc_root
        )
        assert resolved == feature_path.resolve()
