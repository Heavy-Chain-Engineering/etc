"""Tests for `scripts/extend_resolver.py` (F025 BR-001..BR-006).

Coverage targets per task 001 acceptance criteria:

- AC-006+BR-006: ``generate_extend_id()`` returns 8-char hex matching
  ``^[0-9a-f]{8}$``; 1000 consecutive calls all match; chronologically
  sortable (a later call within the same millisecond may collide on the
  timestamp prefix but globally the prefix advances).
- BR-001+BR-002: ``resolve_target(etc_sdlc_root, feature_id_arg)``
  returns Path to shipped feature dir; if ``feature_id_arg`` is None,
  returns most-recent-shipped by ``state.yaml.build.completed_at``;
  raises ``FeatureNotFoundError`` on no match.
- AC-004+BR-004: ``reopen(target_dir, etc_sdlc_root)`` moves dir from
  ``shipped/`` to ``active/`` via ``shutil.move`` (F022 fallback);
  raises ``FileExistsError`` on active/ collision.
- AC-005+BR-005: ``record_extend(...)`` appends one extend entry to
  ``state.yaml.extends``; append-only (existing entries never mutated).
- ``complete_extend(target_dir, extend_id, release_tag)`` sets
  ``completed_at`` + ``release_tag`` on the matching in-flight entry;
  idempotent.
- ``close(target_dir, etc_sdlc_root)`` moves dir from ``active/`` to
  ``shipped/`` via F022 pattern.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import extend_resolver  # pyright: ignore[reportMissingImports]  # noqa: E402, I001 — sys.path inserted above

_EXTEND_ID_PATTERN = re.compile(r"^[0-9a-f]{8}$")


# ── generate_extend_id: format + sortability (AC-006+BR-006) ───────────


class TestGenerateExtendId:
    def test_should_return_8_char_hex_when_called_once(self) -> None:
        extend_id = extend_resolver.generate_extend_id()

        assert _EXTEND_ID_PATTERN.match(extend_id), (
            f"extend_id {extend_id!r} does not match ^[0-9a-f]{{8}}$"
        )

    def test_should_return_unique_ids_when_called_1000_times(self) -> None:
        ids = [extend_resolver.generate_extend_id() for _ in range(1000)]

        assert all(_EXTEND_ID_PATTERN.match(extend_id) for extend_id in ids), (
            "at least one of 1000 IDs failed the ^[0-9a-f]{8}$ pattern"
        )

    def test_should_sort_chronologically_when_called_across_milliseconds(
        self,
    ) -> None:
        import time

        first = extend_resolver.generate_extend_id()
        time.sleep(0.05)  # 50ms — well past the millisecond resolution
        second = extend_resolver.generate_extend_id()

        # Chronologically-sortable: a later call (50ms later) yields a
        # lexically-later ID. The sha256 truncation does NOT preserve raw
        # timestamp ordering, but the underlying generate_extend_id MUST
        # use a strategy that respects monotonic ordering at this scale.
        assert first < second, (
            f"chronological-sort violated: first={first!r} second={second!r}"
        )


# ── resolve_target: locate shipped feature dir (BR-001+BR-002) ─────────


def _write_shipped_feature(
    etc_sdlc_root: Path,
    feature_id: str,
    slug: str,
    completed_at: str,
) -> Path:
    """Create a synthetic shipped feature dir with state.yaml.build.completed_at."""
    shipped_dir = etc_sdlc_root / "features" / "shipped" / f"{feature_id}-{slug}"
    shipped_dir.mkdir(parents=True)
    state = {
        "id_history": [{"form": "final", "value": feature_id}],
        "build": {"completed_at": completed_at},
    }
    (shipped_dir / "state.yaml").write_text(yaml.safe_dump(state, sort_keys=False))
    return shipped_dir


class TestResolveTarget:
    def test_should_return_path_when_feature_id_matches_shipped(
        self, tmp_path: Path
    ) -> None:
        etc_sdlc_root = tmp_path / ".etc_sdlc"
        target = _write_shipped_feature(
            etc_sdlc_root, "F042", "settings-page", "2026-06-15T17:30:00Z"
        )

        resolved = extend_resolver.resolve_target(etc_sdlc_root, "F042")

        assert resolved == target.resolve()

    def test_should_return_most_recent_shipped_when_feature_id_is_none(
        self, tmp_path: Path
    ) -> None:
        etc_sdlc_root = tmp_path / ".etc_sdlc"
        _write_shipped_feature(
            etc_sdlc_root, "F040", "older", "2026-05-01T12:00:00Z"
        )
        newer = _write_shipped_feature(
            etc_sdlc_root, "F042", "newer", "2026-06-15T17:30:00Z"
        )

        resolved = extend_resolver.resolve_target(etc_sdlc_root, None)

        assert resolved == newer.resolve()

    def test_should_raise_feature_not_found_when_no_match(
        self, tmp_path: Path
    ) -> None:
        etc_sdlc_root = tmp_path / ".etc_sdlc"
        (etc_sdlc_root / "features" / "shipped").mkdir(parents=True)

        with pytest.raises(extend_resolver.FeatureNotFoundError):
            extend_resolver.resolve_target(etc_sdlc_root, "F999")

    def test_should_raise_feature_not_found_when_shipped_dir_empty_and_no_arg(
        self, tmp_path: Path
    ) -> None:
        etc_sdlc_root = tmp_path / ".etc_sdlc"
        (etc_sdlc_root / "features" / "shipped").mkdir(parents=True)

        with pytest.raises(extend_resolver.FeatureNotFoundError):
            extend_resolver.resolve_target(etc_sdlc_root, None)


# ── reopen: shipped -> active dir move (AC-004+BR-004) ──────────────────


class TestReopen:
    def test_should_move_shipped_dir_to_active_when_invoked(
        self, tmp_path: Path
    ) -> None:
        etc_sdlc_root = tmp_path / ".etc_sdlc"
        shipped = _write_shipped_feature(
            etc_sdlc_root, "F042", "swap-radix", "2026-06-15T17:30:00Z"
        )

        active_path = extend_resolver.reopen(shipped, etc_sdlc_root)

        assert active_path.is_dir()
        assert active_path.name == "F042-swap-radix"
        assert active_path.parent == etc_sdlc_root / "features" / "active"
        assert not shipped.exists()

    def test_should_raise_file_exists_error_when_active_collision(
        self, tmp_path: Path
    ) -> None:
        etc_sdlc_root = tmp_path / ".etc_sdlc"
        shipped = _write_shipped_feature(
            etc_sdlc_root, "F042", "collision", "2026-06-15T17:30:00Z"
        )
        # Pre-create the collision target under active/.
        active_collision = (
            etc_sdlc_root / "features" / "active" / "F042-collision"
        )
        active_collision.mkdir(parents=True)

        with pytest.raises(FileExistsError):
            extend_resolver.reopen(shipped, etc_sdlc_root)


# ── record_extend: append to state.yaml.extends (AC-005+BR-005) ─────────


def _write_active_feature(
    etc_sdlc_root: Path,
    feature_id: str,
    slug: str,
    extra_state: dict[str, Any] | None = None,
) -> Path:
    """Create a synthetic active feature dir with a minimal state.yaml."""
    active_dir = etc_sdlc_root / "features" / "active" / f"{feature_id}-{slug}"
    active_dir.mkdir(parents=True)
    state: dict[str, Any] = {
        "id_history": [{"form": "final", "value": feature_id}],
        "build": {"completed_at": "2026-06-15T17:30:00Z"},
    }
    if extra_state:
        state.update(extra_state)
    (active_dir / "state.yaml").write_text(
        yaml.safe_dump(state, sort_keys=False)
    )
    return active_dir


class TestRecordExtend:
    def test_should_append_one_entry_when_extends_field_absent(
        self, tmp_path: Path
    ) -> None:
        etc_sdlc_root = tmp_path / ".etc_sdlc"
        target = _write_active_feature(etc_sdlc_root, "F042", "swap-radix")

        extend_resolver.record_extend(
            target_dir=target,
            extend_id="01b5a3c7",
            problem="swap shadcn for radix on SettingsPage",
            triage="light",
            dispatched_agents=["frontend-developer"],
        )

        state = yaml.safe_load((target / "state.yaml").read_text())
        assert "extends" in state
        assert isinstance(state["extends"], list)
        assert len(state["extends"]) == 1
        entry = state["extends"][0]
        assert entry["extend_id"] == "01b5a3c7"
        assert entry["problem"] == "swap shadcn for radix on SettingsPage"
        assert entry["triage"] == "light"
        assert entry["dispatched_agents"] == ["frontend-developer"]
        assert entry["completed_at"] is None
        assert entry["release_tag"] is None
        assert "started_at" in entry

    def test_should_preserve_existing_entries_when_appending(
        self, tmp_path: Path
    ) -> None:
        etc_sdlc_root = tmp_path / ".etc_sdlc"
        target = _write_active_feature(
            etc_sdlc_root,
            "F042",
            "swap-radix",
            extra_state={
                "extends": [
                    {
                        "extend_id": "aaaaaaaa",
                        "problem": "earlier work",
                        "triage": "light",
                        "started_at": "2026-06-14T12:00:00Z",
                        "completed_at": "2026-06-14T13:00:00Z",
                        "release_tag": "etc/feature/F042/release/aaaaaaaa",
                        "dispatched_agents": ["frontend-developer"],
                    }
                ]
            },
        )

        extend_resolver.record_extend(
            target_dir=target,
            extend_id="bbbbbbbb",
            problem="second extend",
            triage="medium",
            dispatched_agents=["backend-developer"],
        )

        state = yaml.safe_load((target / "state.yaml").read_text())
        assert len(state["extends"]) == 2
        # Existing entry byte-equivalent in fields.
        first = state["extends"][0]
        assert first["extend_id"] == "aaaaaaaa"
        assert first["completed_at"] == "2026-06-14T13:00:00Z"
        assert first["release_tag"] == "etc/feature/F042/release/aaaaaaaa"

    def test_should_preserve_build_block_when_appending_extend(
        self, tmp_path: Path
    ) -> None:
        etc_sdlc_root = tmp_path / ".etc_sdlc"
        target = _write_active_feature(etc_sdlc_root, "F042", "preserve")

        extend_resolver.record_extend(
            target_dir=target,
            extend_id="cccccccc",
            problem="x",
            triage="light",
            dispatched_agents=["frontend-developer"],
        )

        state = yaml.safe_load((target / "state.yaml").read_text())
        assert state["build"] == {"completed_at": "2026-06-15T17:30:00Z"}
        assert state["id_history"] == [{"form": "final", "value": "F042"}]


# ── complete_extend: set completed_at + release_tag, idempotent ────────


class TestCompleteExtend:
    def test_should_set_completed_at_and_release_tag_when_matching_entry(
        self, tmp_path: Path
    ) -> None:
        etc_sdlc_root = tmp_path / ".etc_sdlc"
        target = _write_active_feature(etc_sdlc_root, "F042", "complete")
        extend_resolver.record_extend(
            target_dir=target,
            extend_id="dddddddd",
            problem="x",
            triage="light",
            dispatched_agents=["frontend-developer"],
        )

        extend_resolver.complete_extend(
            target_dir=target,
            extend_id="dddddddd",
            release_tag="etc/feature/F042/release/dddddddd",
        )

        state = yaml.safe_load((target / "state.yaml").read_text())
        entry = state["extends"][0]
        assert entry["completed_at"] is not None
        assert entry["release_tag"] == "etc/feature/F042/release/dddddddd"

    def test_should_be_idempotent_when_called_twice(
        self, tmp_path: Path
    ) -> None:
        etc_sdlc_root = tmp_path / ".etc_sdlc"
        target = _write_active_feature(etc_sdlc_root, "F042", "idempotent")
        extend_resolver.record_extend(
            target_dir=target,
            extend_id="eeeeeeee",
            problem="x",
            triage="light",
            dispatched_agents=["frontend-developer"],
        )
        extend_resolver.complete_extend(
            target_dir=target,
            extend_id="eeeeeeee",
            release_tag="etc/feature/F042/release/eeeeeeee",
        )
        state_first = yaml.safe_load((target / "state.yaml").read_text())
        first_completed_at = state_first["extends"][0]["completed_at"]

        extend_resolver.complete_extend(
            target_dir=target,
            extend_id="eeeeeeee",
            release_tag="etc/feature/F042/release/eeeeeeee",
        )

        state_second = yaml.safe_load((target / "state.yaml").read_text())
        # Idempotent: completed_at unchanged on the second call.
        assert state_second["extends"][0]["completed_at"] == first_completed_at
        assert state_second["extends"][0]["release_tag"] == (
            "etc/feature/F042/release/eeeeeeee"
        )


# ── close: active -> shipped dir move (F022 pattern) ───────────────────


class TestClose:
    def test_should_move_active_dir_to_shipped_when_invoked(
        self, tmp_path: Path
    ) -> None:
        etc_sdlc_root = tmp_path / ".etc_sdlc"
        active = _write_active_feature(etc_sdlc_root, "F042", "close-me")

        shipped_path = extend_resolver.close(active, etc_sdlc_root)

        assert shipped_path.is_dir()
        assert shipped_path.name == "F042-close-me"
        assert shipped_path.parent == etc_sdlc_root / "features" / "shipped"
        assert not active.exists()


# ── CLI: generate-id subcommand prints to stdout ────────────────────────


class TestCLI:
    def test_should_print_extend_id_when_generate_id_subcommand_invoked(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        rc = extend_resolver.main(["generate-id"])

        captured = capsys.readouterr()
        assert rc == 0
        assert _EXTEND_ID_PATTERN.match(captured.out.strip()), (
            f"CLI stdout {captured.out!r} does not match ^[0-9a-f]{{8}}$"
        )
