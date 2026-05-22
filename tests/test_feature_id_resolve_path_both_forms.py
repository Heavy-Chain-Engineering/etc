"""Tests for `resolve_feature_path` accepting both ID forms (F023 BR-004).

Coverage targets:
- AC-004+BR-004: `resolve_feature_path(feature_id, etc_sdlc_root)` accepts
  both `Ftmp-<hex>` and `F<NNN>` forms. Walks F009 lifecycle order
  (legacy flat → active → shipped → rejections). Returns `None` on no
  match without raising. Pre-F023 `F<NNN>` callers see no behavior change.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import feature_id  # pyright: ignore[reportMissingImports]  # noqa: E402, I001  — sys.path inserted above


def _build_etc_sdlc_tree(tmp_path: Path) -> Path:
    etc_sdlc = tmp_path / ".etc_sdlc"
    (etc_sdlc / "features" / "active").mkdir(parents=True)
    (etc_sdlc / "features" / "shipped").mkdir()
    (etc_sdlc / "rejections").mkdir()
    return etc_sdlc


# ── Ftmp-<hex> form ─────────────────────────────────────────────────────


class TestResolveFeaturePathTempForm:
    def test_should_resolve_temp_id_when_active_dir_exists(
        self, tmp_path: Path
    ) -> None:
        etc_sdlc = _build_etc_sdlc_tree(tmp_path)
        target = (
            etc_sdlc / "features" / "active" / "Ftmp-abcdef12-some-feature"
        )
        target.mkdir()

        result = feature_id.resolve_feature_path("Ftmp-abcdef12", etc_sdlc)

        assert result == target.resolve()

    def test_should_resolve_temp_id_when_shipped_dir_exists(
        self, tmp_path: Path
    ) -> None:
        etc_sdlc = _build_etc_sdlc_tree(tmp_path)
        target = (
            etc_sdlc / "features" / "shipped" / "Ftmp-feed0bad-old-feature"
        )
        target.mkdir()

        result = feature_id.resolve_feature_path("Ftmp-feed0bad", etc_sdlc)

        assert result == target.resolve()

    def test_should_resolve_temp_id_when_rejection_dir_exists(
        self, tmp_path: Path
    ) -> None:
        etc_sdlc = _build_etc_sdlc_tree(tmp_path)
        target = etc_sdlc / "rejections" / "Ftmp-bad1dea0-killed"
        target.mkdir()

        result = feature_id.resolve_feature_path("Ftmp-bad1dea0", etc_sdlc)

        assert result == target.resolve()

    def test_should_return_none_when_temp_id_absent_everywhere(
        self, tmp_path: Path
    ) -> None:
        etc_sdlc = _build_etc_sdlc_tree(tmp_path)

        assert (
            feature_id.resolve_feature_path("Ftmp-deadbeef", etc_sdlc)
            is None
        )

    def test_should_return_none_when_temp_hex_is_malformed(
        self, tmp_path: Path
    ) -> None:
        etc_sdlc = _build_etc_sdlc_tree(tmp_path)
        # Path-traversal guard: malformed temp IDs must NOT touch the FS.
        assert feature_id.resolve_feature_path("Ftmp-", etc_sdlc) is None
        # 7 hex chars (one short) is malformed.
        assert feature_id.resolve_feature_path("Ftmp-abcdef1", etc_sdlc) is None
        # 9 hex chars (one too many) is malformed.
        assert (
            feature_id.resolve_feature_path("Ftmp-abcdef123", etc_sdlc) is None
        )
        # Non-hex characters
        assert (
            feature_id.resolve_feature_path("Ftmp-zzzzzzzz", etc_sdlc) is None
        )

    def test_should_return_none_when_temp_id_attempts_path_traversal(
        self, tmp_path: Path
    ) -> None:
        etc_sdlc = _build_etc_sdlc_tree(tmp_path)

        assert (
            feature_id.resolve_feature_path("Ftmp-../etc/passwd", etc_sdlc)
            is None
        )
        assert feature_id.resolve_feature_path("/Ftmp-abcdef12", etc_sdlc) is None


# ── F<NNN> form: pre-F023 behavior preserved ────────────────────────────


class TestResolveFeaturePathFinalFormPreserved:
    def test_should_resolve_final_id_when_active_dir_exists(
        self, tmp_path: Path
    ) -> None:
        etc_sdlc = _build_etc_sdlc_tree(tmp_path)
        target = etc_sdlc / "features" / "active" / "F042-in-flight"
        target.mkdir()

        result = feature_id.resolve_feature_path("F042", etc_sdlc)

        assert result == target.resolve()

    def test_should_resolve_legacy_flat_form_still_takes_priority(
        self, tmp_path: Path
    ) -> None:
        # Pre-F023 lifecycle order: legacy flat → active → shipped → rejections.
        etc_sdlc = _build_etc_sdlc_tree(tmp_path)
        legacy = etc_sdlc / "features" / "F010-legacy"
        legacy.mkdir()
        # Decoy in active that must NOT be returned.
        (etc_sdlc / "features" / "active" / "F010-decoy").mkdir()

        result = feature_id.resolve_feature_path("F010", etc_sdlc)

        assert result == legacy.resolve()

    def test_should_return_none_when_final_id_absent_everywhere(
        self, tmp_path: Path
    ) -> None:
        etc_sdlc = _build_etc_sdlc_tree(tmp_path)

        assert feature_id.resolve_feature_path("F999", etc_sdlc) is None


# ── Both forms in the same call site ────────────────────────────────────


class TestResolveFeaturePathBothFormsCoexist:
    def test_should_resolve_both_temp_and_final_forms_in_same_tree(
        self, tmp_path: Path
    ) -> None:
        etc_sdlc = _build_etc_sdlc_tree(tmp_path)
        temp_target = (
            etc_sdlc / "features" / "active" / "Ftmp-abcdef12-coexist-a"
        )
        temp_target.mkdir()
        final_target = (
            etc_sdlc / "features" / "active" / "F050-coexist-b"
        )
        final_target.mkdir()

        assert (
            feature_id.resolve_feature_path("Ftmp-abcdef12", etc_sdlc)
            == temp_target.resolve()
        )
        assert (
            feature_id.resolve_feature_path("F050", etc_sdlc)
            == final_target.resolve()
        )
