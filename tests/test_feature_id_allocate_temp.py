"""Tests for `scripts/feature_id.py allocate-temp` (F023 BR-001, BR-008).

Coverage targets:
- AC-001 (BR-001): `allocate-temp <slug>` returns `Ftmp-<8-hex>` matching
  `^Ftmp-[0-9a-f]{8}$`; creates `<etc_sdlc_root>/features/active/Ftmp-<hex>-<slug>/`
  with initial `state.yaml.id_history[0]={form:temp, value:Ftmp-<hex>,
  written_at:ISO-8601-UTC}`. 1000 consecutive calls produce 1000 unique IDs
  (zero collisions across the entropy domain).
- AC-001+EC-001: Collision retry — up to 3 attempts when `secrets.token_hex`
  returns an existing ID. After 3 retries, exit non-zero with stderr.
- EC-009: On `AttributeError` from `secrets.token_hex` (FIPS-restricted
  Python), exit non-zero with stderr naming the dependency.
- AC-011: `scripts/feature_id.py` module docstring contains the literal HTML
  comment `<!-- forward-only: temp-ID allocation enforced from F023 release
  tag onward -->` within first 10 lines.
- Security: path-traversal rejection on slug input (rejects `..`, absolute
  paths; caps length at 64 chars).
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import feature_id  # pyright: ignore[reportMissingImports]  # noqa: E402, I001  — sys.path inserted above

_SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "feature_id.py"

_TEMP_ID_PATTERN = re.compile(r"^Ftmp-[0-9a-f]{8}$")


# ── allocate_temp: happy paths (AC-001+BR-001) ──────────────────────────


class TestAllocateTempHappyPath:
    def test_should_return_temp_id_matching_regex_when_slug_is_valid(
        self, tmp_path: Path
    ) -> None:
        etc_sdlc_root = tmp_path / ".etc_sdlc"

        temp_id, feature_path = feature_id.allocate_temp(
            "test-feature", etc_sdlc_root
        )

        assert _TEMP_ID_PATTERN.match(temp_id), (
            f"temp_id {temp_id!r} does not match ^Ftmp-[0-9a-f]{{8}}$"
        )
        assert feature_path.is_dir()
        assert feature_path.name == f"{temp_id}-test-feature"
        assert feature_path.parent == etc_sdlc_root / "features" / "active"

    def test_should_create_active_parent_when_etc_sdlc_root_does_not_exist(
        self, tmp_path: Path
    ) -> None:
        etc_sdlc_root = tmp_path / ".etc_sdlc"  # not yet created

        _, feature_path = feature_id.allocate_temp(
            "bootstrap", etc_sdlc_root
        )

        assert feature_path.is_dir()
        assert feature_path.parent == etc_sdlc_root / "features" / "active"

    def test_should_write_state_yaml_with_temp_id_history_entry(
        self, tmp_path: Path
    ) -> None:
        etc_sdlc_root = tmp_path / ".etc_sdlc"

        temp_id, feature_path = feature_id.allocate_temp(
            "init-state", etc_sdlc_root
        )

        state_path = feature_path / "state.yaml"
        assert state_path.is_file()
        loaded: dict[str, Any] = yaml.safe_load(state_path.read_text())
        assert "id_history" in loaded
        assert isinstance(loaded["id_history"], list)
        assert len(loaded["id_history"]) == 1
        entry = loaded["id_history"][0]
        assert entry["form"] == "temp"
        assert entry["value"] == temp_id
        assert "written_at" in entry
        # ISO-8601-UTC: must contain T and end with Z OR +00:00.
        written_at = entry["written_at"]
        assert "T" in written_at
        assert written_at.endswith("Z") or written_at.endswith("+00:00")


# ── allocate_temp: uniqueness across 1000 calls (BR-001) ────────────────


class TestAllocateTempUniqueness:
    def test_should_produce_1000_unique_ids_across_1000_consecutive_calls(
        self, tmp_path: Path
    ) -> None:
        # AC-001+BR-001: 1000 consecutive calls produce 1000 unique IDs.
        etc_sdlc_root = tmp_path / ".etc_sdlc"

        seen: set[str] = set()
        for i in range(1000):
            temp_id, _ = feature_id.allocate_temp(
                f"slug-{i}", etc_sdlc_root
            )
            assert _TEMP_ID_PATTERN.match(temp_id), (
                f"call {i}: temp_id {temp_id!r} malformed"
            )
            seen.add(temp_id)

        assert len(seen) == 1000, (
            f"expected 1000 unique IDs across 1000 calls; got {len(seen)}"
        )


# ── allocate_temp: collision retry path (EC-001) ────────────────────────


class TestAllocateTempCollisionRetry:
    def test_should_retry_when_first_hex_matches_existing_dir(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """First token_hex returns a colliding value; second succeeds."""
        etc_sdlc_root = tmp_path / ".etc_sdlc"
        active = etc_sdlc_root / "features" / "active"
        active.mkdir(parents=True)
        # Pre-create the dir that the first token_hex call will return.
        colliding_hex = "deadbeef"
        (active / f"Ftmp-{colliding_hex}-already-here").mkdir()

        fresh_hex = "cafef00d"
        sequence = iter([colliding_hex, fresh_hex])

        def fake_token_hex(_n: int) -> str:
            del _n
            return next(sequence)

        monkeypatch.setattr(feature_id.secrets, "token_hex", fake_token_hex)

        temp_id, feature_path = feature_id.allocate_temp(
            "retry-test", etc_sdlc_root
        )

        assert temp_id == f"Ftmp-{fresh_hex}"
        assert feature_path.name == f"{temp_id}-retry-test"

    def test_should_exit_nonzero_after_three_consecutive_collisions(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """3 retries exhausted → non-zero exit + stderr."""
        etc_sdlc_root = tmp_path / ".etc_sdlc"
        active = etc_sdlc_root / "features" / "active"
        active.mkdir(parents=True)
        # Pre-create three colliding dirs.
        colliding = ["aaaaaaaa", "bbbbbbbb", "cccccccc"]
        for hx in colliding:
            (active / f"Ftmp-{hx}-stuck").mkdir()

        sequence = iter(colliding)

        def fake_token_hex(_n: int) -> str:
            del _n
            return next(sequence)

        monkeypatch.setattr(feature_id.secrets, "token_hex", fake_token_hex)

        with pytest.raises(feature_id.TempIdCollisionError):
            feature_id.allocate_temp("stuck", etc_sdlc_root)


# ── allocate_temp: FIPS-restricted Python (EC-009) ──────────────────────


class TestAllocateTempFipsRestricted:
    def test_should_raise_when_secrets_token_hex_unavailable(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        etc_sdlc_root = tmp_path / ".etc_sdlc"

        def attribute_error_raiser(_n: int) -> str:
            del _n
            raise AttributeError("token_hex unavailable on this build")

        monkeypatch.setattr(
            feature_id.secrets, "token_hex", attribute_error_raiser
        )

        with pytest.raises(AttributeError):
            feature_id.allocate_temp("fips", etc_sdlc_root)


# ── allocate_temp: slug sanitization (security) ─────────────────────────


class TestAllocateTempSlugSanitization:
    def test_should_reject_path_traversal_slug(self, tmp_path: Path) -> None:
        etc_sdlc_root = tmp_path / ".etc_sdlc"
        with pytest.raises(ValueError):
            feature_id.allocate_temp("../etc/passwd", etc_sdlc_root)

    def test_should_reject_absolute_path_slug(self, tmp_path: Path) -> None:
        etc_sdlc_root = tmp_path / ".etc_sdlc"
        with pytest.raises(ValueError):
            feature_id.allocate_temp("/abs/path", etc_sdlc_root)

    def test_should_reject_slug_exceeding_max_length(
        self, tmp_path: Path
    ) -> None:
        etc_sdlc_root = tmp_path / ".etc_sdlc"
        with pytest.raises(ValueError):
            feature_id.allocate_temp("a" * 65, etc_sdlc_root)


# ── AC-011: module docstring carries forward-only HTML comment ──────────


class TestForwardOnlyDocstringMarker:
    def test_should_carry_forward_only_html_comment_near_top_of_module(
        self,
    ) -> None:
        # AC-011: literal HTML comment must appear within first 10 lines.
        source = _SCRIPT_PATH.read_text()
        first_lines = source.splitlines()[:10]
        marker = (
            "<!-- forward-only: temp-ID allocation enforced from F023 "
            "release tag onward -->"
        )
        assert any(marker in line for line in first_lines), (
            f"marker {marker!r} not found in first 10 lines of "
            f"{_SCRIPT_PATH}"
        )


# ── CLI subcommand: allocate-temp ───────────────────────────────────────


class TestAllocateTempCLI:
    def test_should_print_temp_id_and_feature_path_to_stdout(
        self, tmp_path: Path
    ) -> None:
        etc_sdlc_root = tmp_path / ".etc_sdlc"

        result = subprocess.run(
            [
                sys.executable,
                str(_SCRIPT_PATH),
                "allocate-temp",
                str(etc_sdlc_root),
                "cli-feature",
            ],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert result.returncode == 0, (
            f"CLI exited {result.returncode}; stderr={result.stderr!r}"
        )
        line = result.stdout.rstrip("\n")
        assert "\n" not in line
        parts = line.split(" ", 1)
        assert len(parts) == 2
        temp_id_str, feature_path_str = parts
        assert _TEMP_ID_PATTERN.match(temp_id_str), (
            f"unexpected temp id {temp_id_str!r}"
        )
        feature_path = Path(feature_path_str)
        assert feature_path.is_dir()
        assert feature_path.name == f"{temp_id_str}-cli-feature"

    def test_should_exit_nonzero_when_slug_contains_path_traversal(
        self, tmp_path: Path
    ) -> None:
        etc_sdlc_root = tmp_path / ".etc_sdlc"

        result = subprocess.run(
            [
                sys.executable,
                str(_SCRIPT_PATH),
                "allocate-temp",
                str(etc_sdlc_root),
                "../escape",
            ],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert result.returncode != 0
        assert result.stderr.strip(), "expected non-empty stderr"
