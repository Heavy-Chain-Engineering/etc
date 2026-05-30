"""Tests for the behavioral-runtime deferred-outcome surfacing in release_notes.

Covers F-2026-05-30-behavioral-runtime-dod-gate AC-8 and BR-009:

- AC-8: the behavioral-runtime deferred set surfaces in release-notes (and is
  exposed for verification.md rendering), read from
  ``state.yaml.build.runtime_verification``.
- BR-009 (anti-gaming): mass deferral lists EVERY deferral by ``ac_id`` +
  ``reason`` and is NEVER collapsed into an aggregate count. A milestone
  ``terminal_tag`` is surfaced prominently as a milestone (not clean) release.
- Forward-only: a feature with no ``runtime_verification`` block (or no
  deferrals) emits no false noise — existing release_notes behavior preserved.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import release_notes  # noqa: E402  (sys.path mutated above)

# Reuse the existing phase-report fixture helpers so a feature dir has the
# minimal phase data build() requires to render the full document.
from test_release_notes import (  # noqa: E402
    _example_phase_body,
    _write_phase_report,
)

# An aggregate-count phrasing is the exact anti-pattern BR-009 forbids: a
# summary like "3 outcomes deferred" that hides which ACs were deferred.
_AGGREGATE_COUNT_PATTERN = re.compile(
    r"\b\d+\s+(?:outcomes?|acs?|deferral?s?|items?)\s+deferred\b",
    re.IGNORECASE,
)


def _write_state(feature_dir: Path, body: str) -> Path:
    """Write feature_dir/state.yaml with the given YAML body."""
    state_path = feature_dir / "state.yaml"
    state_path.write_text(body, encoding="utf-8")
    return state_path


def _runtime_verification_state(
    *,
    deferrals: list[tuple[str, str]],
    terminal_tag: str | None,
) -> str:
    """Build a state.yaml body with a build.runtime_verification block.

    `deferrals` is a list of (ac_id, reason) pairs; each becomes one
    `deferred[]` entry with a matching `results[]` entry (status: deferred,
    live_at: deferred).
    """
    lines: list[str] = [
        "build:",
        "  runtime_verification:",
        "    schema_version: 1",
        "    stage: release",
        "    results:",
    ]
    for ac_id, _reason in deferrals:
        lines.append(f"      - ac_id: {ac_id}")
        lines.append("        status: deferred")
        lines.append("        live_at: deferred")
        lines.append("        profile: python")
    lines.append("    deferred:")
    for ac_id, reason in deferrals:
        lines.append(f"      - ac_id: {ac_id}")
        lines.append(f'        reason: "{reason}"')
    tag_value = terminal_tag if terminal_tag is not None else "null"
    lines.append(f"    terminal_tag: {tag_value}")
    return "\n".join(lines) + "\n"


def _feature_with_phase(tmp_path: Path) -> Path:
    feature_dir = tmp_path / "F-2026-05-30-behavioral-runtime-dod-gate"
    feature_dir.mkdir()
    _write_phase_report(feature_dir, 1, _example_phase_body(phase_number=1))
    return feature_dir


# ── Single deferral ──────────────────────────────────────────────────────


class TestSingleDeferral:
    def test_should_surface_section_when_one_ac_deferred(
        self,
        tmp_path: Path,
    ) -> None:
        feature_dir = _feature_with_phase(tmp_path)
        _write_state(
            feature_dir,
            _runtime_verification_state(
                deferrals=[("AC-9", "drawer persistence pending web profile")],
                terminal_tag="etc/feature/F-2026-05-30/milestone/001",
            ),
        )

        result = release_notes.build(feature_dir)

        assert "## Behavioral Runtime — Deferred Outcomes" in result
        assert "AC-9" in result
        assert "drawer persistence pending web profile" in result

    def test_should_list_ac_id_with_its_reason_verbatim(
        self,
        tmp_path: Path,
    ) -> None:
        feature_dir = _feature_with_phase(tmp_path)
        reason = "auth flow deferred to wave-3 per liveness block"
        _write_state(
            feature_dir,
            _runtime_verification_state(
                deferrals=[("AC-4", reason)],
                terminal_tag="etc/feature/F-2026-05-30/milestone/001",
            ),
        )

        result = release_notes.build(feature_dir)

        assert f"AC-4 — {reason}" in result


# ── Mass deferral (BR-009 anti-gaming) ───────────────────────────────────


class TestMassDeferralNeverCollapsesToCount:
    def test_should_list_every_deferral_when_three_acs_deferred(
        self,
        tmp_path: Path,
    ) -> None:
        feature_dir = _feature_with_phase(tmp_path)
        deferrals = [
            ("AC-2", "search ranking deferred — needs prod corpus"),
            ("AC-5", "export pipeline deferred to milestone 2"),
            ("AC-7", "notification fan-out deferred — vendor not provisioned"),
        ]
        _write_state(
            feature_dir,
            _runtime_verification_state(
                deferrals=deferrals,
                terminal_tag="etc/feature/F-2026-05-30/milestone/002",
            ),
        )

        result = release_notes.build(feature_dir)

        for ac_id, reason in deferrals:
            assert ac_id in result, f"{ac_id} missing from output"
            assert reason in result, f"reason for {ac_id} missing from output"

    def test_should_never_collapse_mass_deferral_to_aggregate_count(
        self,
        tmp_path: Path,
    ) -> None:
        feature_dir = _feature_with_phase(tmp_path)
        deferrals = [
            ("AC-2", "search ranking deferred — needs prod corpus"),
            ("AC-5", "export pipeline deferred to milestone 2"),
            ("AC-7", "notification fan-out deferred — vendor not provisioned"),
        ]
        _write_state(
            feature_dir,
            _runtime_verification_state(
                deferrals=deferrals,
                terminal_tag="etc/feature/F-2026-05-30/milestone/002",
            ),
        )

        result = release_notes.build(feature_dir)

        match = _AGGREGATE_COUNT_PATTERN.search(result)
        assert match is None, (
            f"aggregate-count phrasing forbidden by BR-009: {match!r}"
        )

    def test_should_flag_milestone_terminal_tag_prominently(
        self,
        tmp_path: Path,
    ) -> None:
        feature_dir = _feature_with_phase(tmp_path)
        _write_state(
            feature_dir,
            _runtime_verification_state(
                deferrals=[("AC-2", "deferred reason text")],
                terminal_tag="etc/feature/F-2026-05-30/milestone/002",
            ),
        )

        result = release_notes.build(feature_dir)

        assert "MILESTONE" in result
        assert "etc/feature/F-2026-05-30/milestone/002" in result
        # The milestone tag must NOT be misreported as a clean release.
        assert "not a clean release" in result.lower()


# ── Forward-only (no false noise) ────────────────────────────────────────


class TestForwardOnly:
    def test_should_omit_section_when_no_runtime_verification_block(
        self,
        tmp_path: Path,
    ) -> None:
        feature_dir = _feature_with_phase(tmp_path)
        # No state.yaml at all — legacy / pre-gate feature.

        result = release_notes.build(feature_dir)

        assert "Behavioral Runtime" not in result

    def test_should_omit_section_when_runtime_verification_has_no_deferrals(
        self,
        tmp_path: Path,
    ) -> None:
        feature_dir = _feature_with_phase(tmp_path)
        _write_state(
            feature_dir,
            _runtime_verification_state(
                deferrals=[],
                terminal_tag="etc/feature/F-2026-05-30/release",
            ),
        )

        result = release_notes.build(feature_dir)

        assert "Behavioral Runtime" not in result

    def test_should_preserve_existing_sections_when_block_present(
        self,
        tmp_path: Path,
    ) -> None:
        feature_dir = _feature_with_phase(tmp_path)
        _write_state(
            feature_dir,
            _runtime_verification_state(
                deferrals=[("AC-1", "deferred reason")],
                terminal_tag="etc/feature/F-2026-05-30/milestone/001",
            ),
        )

        result = release_notes.build(feature_dir)

        # Existing roll-up sections still present (no regression).
        assert result.startswith("# Release Notes")
        assert "## Phases" in result
        assert "## Deferred Items" in result
        assert "## Known Limitations" in result


# ── Data exposure for verification.md ────────────────────────────────────


class TestDeferralDataExposure:
    """The deferred set must be programmatically available (for verification.md)."""

    def test_should_expose_parsed_deferrals_for_reuse(
        self,
        tmp_path: Path,
    ) -> None:
        feature_dir = _feature_with_phase(tmp_path)
        _write_state(
            feature_dir,
            _runtime_verification_state(
                deferrals=[
                    ("AC-3", "reason three"),
                    ("AC-8", "reason eight"),
                ],
                terminal_tag="etc/feature/F-2026-05-30/milestone/001",
            ),
        )

        record = release_notes.collect_runtime_verification(feature_dir)

        assert record is not None
        assert record.is_milestone is True
        assert record.terminal_tag == "etc/feature/F-2026-05-30/milestone/001"
        assert [(d.ac_id, d.reason) for d in record.deferred] == [
            ("AC-3", "reason three"),
            ("AC-8", "reason eight"),
        ]

    def test_should_return_none_when_no_block(self, tmp_path: Path) -> None:
        feature_dir = _feature_with_phase(tmp_path)

        record = release_notes.collect_runtime_verification(feature_dir)

        assert record is None
