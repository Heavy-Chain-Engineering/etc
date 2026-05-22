"""Tests for scripts/release_notes.py — `## Extensions` section emission (F025).

Covers .etc_sdlc/features/active/Ftmp-6bb526cc-post-ship-long-tail-discipline/
spec.md BR-008 + AC-008:

- When `state.yaml.extends` is a non-empty list, `release_notes.build` emits
  an append-only `## Extensions` section, with one `### Extension <extend_id>`
  sub-section per extend entry.
- When `state.yaml.extends` is absent OR an empty list, the rendered output
  is byte-equivalent to the pre-F025 behavior (backwards-compatible).
- The pre-existing sections (Phases, Deferred Items, Known Limitations) are
  byte-equivalent across the absent-extends and present-extends cases — the
  Extensions section is purely an append, never a mutation of prior content.

The `extends` schema is defined by F025 Data-Model Entity 1 (design.md):

    extends:
      - extend_id: "01b5a3c7"
        problem: "<verbatim operator string>"
        triage: light | medium | heavy
        started_at: <ISO-8601 UTC>
        completed_at: <ISO-8601 UTC | null>
        release_tag: "etc/feature/F<NNN>/release_<extend_id>"
        dispatched_agents: ["<role>", ...]

The `release_notes` module reads `state.yaml` from `feature_dir/state.yaml`
when present; absence of the file (legacy / pre-F025 features) is silently
tolerated and treated identically to `extends: []`.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"

# Make scripts/ importable (sibling to tests/).
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import release_notes  # noqa: E402  (sys.path mutated above)

# ── Fixture helpers ──────────────────────────────────────────────────────


def _write_phase_report(
    feature_dir: Path,
    phase_number: int,
    body: str,
) -> Path:
    """Create build/phase-<N>/completion-report.md under feature_dir."""
    phase_dir = feature_dir / "build" / f"phase-{phase_number}"
    phase_dir.mkdir(parents=True, exist_ok=True)
    report_path = phase_dir / "completion-report.md"
    report_path.write_text(body, encoding="utf-8")
    return report_path


def _minimal_phase_body(phase_number: int) -> str:
    """Smallest valid phase report — used when the test only cares about
    extensions-section behavior, not the phase rollup itself."""
    return (
        f"# Phase {phase_number} — Completion Report\n"
        "\n"
        "## PRD\n"
        "- Title: F025 fixture phase\n"
        "- ID: F025\n"
        "\n"
        "## Acceptance Criteria\n"
        "- [x] AC-001 — fixture pass\n"
        "\n"
        "## Deferred Items\n"
        "- None\n"
        "\n"
        "## Known Limitations\n"
        "- None\n"
    )


def _write_state_yaml(
    feature_dir: Path,
    extends: list[dict[str, object]] | None,
) -> Path:
    """Write a minimal state.yaml at feature_dir/state.yaml.

    If extends is None, the `extends:` key is omitted entirely (legacy /
    pre-F025 shape). If it is `[]`, the key is present with an empty list.
    """
    payload: dict[str, object] = {
        "build": {
            "feature": "f025-fixture",
            "spec_path": "irrelevant.md",
            "current_step": 8,
            "mode": "STANDARD",
        },
    }
    if extends is not None:
        payload["extends"] = extends
    state_path = feature_dir / "state.yaml"
    state_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return state_path


def _make_feature_dir_with_one_phase(tmp_path: Path) -> Path:
    """Standard fixture: a feature dir with one minimal phase report."""
    feature_dir = tmp_path / "F042-fixture"
    feature_dir.mkdir()
    _write_phase_report(feature_dir, 1, _minimal_phase_body(1))
    return feature_dir


def _example_extend_entry(
    *,
    extend_id: str = "01b5a3c7",
    problem: str = "swap shadcn for radix in frontend/src/SettingsPage.tsx",
    triage: str = "light",
    dispatched_agents: list[str] | None = None,
    release_tag: str = "etc/feature/F042/release_01b5a3c7",
    completed_at: str | None = "2026-06-15T17:30:00Z",
) -> dict[str, object]:
    """Canonical extend entry shape for fixture data."""
    return {
        "extend_id": extend_id,
        "problem": problem,
        "triage": triage,
        "started_at": "2026-06-15T14:00:00Z",
        "completed_at": completed_at,
        "release_tag": release_tag,
        "dispatched_agents": dispatched_agents or ["frontend-developer"],
    }


# ── Backwards compatibility (extends absent / empty) ─────────────────────


class TestBackwardsCompatibility:
    """When state.yaml is missing or `extends` is absent/empty, output MUST
    be byte-equivalent to the pre-F025 rendering. The Extensions section
    is a pure append; its presence is gated on a non-empty `extends` list.
    """

    def test_should_not_emit_extensions_section_when_state_yaml_missing(
        self,
        tmp_path: Path,
    ) -> None:
        feature_dir = _make_feature_dir_with_one_phase(tmp_path)
        # No state.yaml on disk at all (legacy / pre-F025 feature).

        result = release_notes.build(feature_dir)

        assert "## Extensions" not in result

    def test_should_not_emit_extensions_section_when_extends_field_absent(
        self,
        tmp_path: Path,
    ) -> None:
        feature_dir = _make_feature_dir_with_one_phase(tmp_path)
        _write_state_yaml(feature_dir, extends=None)

        result = release_notes.build(feature_dir)

        assert "## Extensions" not in result

    def test_should_not_emit_extensions_section_when_extends_empty_list(
        self,
        tmp_path: Path,
    ) -> None:
        feature_dir = _make_feature_dir_with_one_phase(tmp_path)
        _write_state_yaml(feature_dir, extends=[])

        result = release_notes.build(feature_dir)

        assert "## Extensions" not in result

    def test_should_render_byte_equivalent_when_extends_empty_vs_no_state(
        self,
        tmp_path: Path,
    ) -> None:
        """AC-008 backwards-compat regression: an empty extends list MUST
        produce identical output to the pre-F025 (no state.yaml) case."""
        # First render: no state.yaml at all (pre-F025 shape).
        legacy_dir = tmp_path / "F042-legacy"
        legacy_dir.mkdir()
        _write_phase_report(legacy_dir, 1, _minimal_phase_body(1))
        legacy_output = release_notes.build(legacy_dir)

        # Second render: state.yaml present with extends: [].
        modern_dir = tmp_path / "F042-modern"
        modern_dir.mkdir()
        _write_phase_report(modern_dir, 1, _minimal_phase_body(1))
        _write_state_yaml(modern_dir, extends=[])
        modern_output = release_notes.build(modern_dir)

        # Outputs differ only by the feature-dir name in the header line.
        # Normalize by stripping the header so the structural content is
        # what is compared — that is the byte-equivalence guarantee.
        legacy_body = legacy_output.split("\n", 1)[1]
        modern_body = modern_output.split("\n", 1)[1]
        assert legacy_body == modern_body


# ── Extensions section emission (one extend) ─────────────────────────────


class TestSingleExtension:
    """One entry in `extends` produces exactly one `### Extension <id>`
    sub-section under a top-level `## Extensions` heading."""

    def test_should_emit_extensions_heading_when_one_extend_present(
        self,
        tmp_path: Path,
    ) -> None:
        feature_dir = _make_feature_dir_with_one_phase(tmp_path)
        _write_state_yaml(feature_dir, extends=[_example_extend_entry()])

        result = release_notes.build(feature_dir)

        assert "## Extensions" in result

    def test_should_emit_extend_id_subheading_when_one_extend_present(
        self,
        tmp_path: Path,
    ) -> None:
        feature_dir = _make_feature_dir_with_one_phase(tmp_path)
        _write_state_yaml(
            feature_dir,
            extends=[_example_extend_entry(extend_id="01b5a3c7")],
        )

        result = release_notes.build(feature_dir)

        assert "### Extension 01b5a3c7" in result

    def test_should_emit_problem_triage_agents_and_tag_when_one_extend_present(
        self,
        tmp_path: Path,
    ) -> None:
        feature_dir = _make_feature_dir_with_one_phase(tmp_path)
        _write_state_yaml(
            feature_dir,
            extends=[
                _example_extend_entry(
                    extend_id="01b5a3c7",
                    problem="swap shadcn for radix",
                    triage="light",
                    dispatched_agents=["frontend-developer"],
                    release_tag="etc/feature/F042/release_01b5a3c7",
                ),
            ],
        )

        result = release_notes.build(feature_dir)

        # AC-008+BR-008 mandates each sub-section include the four fields.
        assert "swap shadcn for radix" in result
        assert "light" in result
        assert "frontend-developer" in result
        assert "etc/feature/F042/release_01b5a3c7" in result

    def test_should_emit_exactly_one_extension_subsection_when_one_extend(
        self,
        tmp_path: Path,
    ) -> None:
        feature_dir = _make_feature_dir_with_one_phase(tmp_path)
        _write_state_yaml(feature_dir, extends=[_example_extend_entry()])

        result = release_notes.build(feature_dir)

        # Count "### Extension " sub-headers — must be exactly 1.
        assert result.count("### Extension ") == 1


# ── Extensions section emission (three extends, chronological) ───────────


class TestMultipleExtensionsChronological:
    """Three extends produce three sub-sections, ordered chronologically.

    Per AC-008 case (c): extend_ids are time-ordered (UUID7-derived), so
    lexicographic sort = creation order. The renderer must preserve the
    array order from state.yaml (which the resolver appends in creation
    order) — it MUST NOT reorder by, e.g., alphabetic on triage.
    """

    def test_should_emit_three_subsections_when_three_extends_present(
        self,
        tmp_path: Path,
    ) -> None:
        feature_dir = _make_feature_dir_with_one_phase(tmp_path)
        _write_state_yaml(
            feature_dir,
            extends=[
                _example_extend_entry(extend_id="01b5a3c7"),
                _example_extend_entry(extend_id="01b5d291"),
                _example_extend_entry(extend_id="01b5f0a4"),
            ],
        )

        result = release_notes.build(feature_dir)

        assert result.count("### Extension ") == 3
        assert "### Extension 01b5a3c7" in result
        assert "### Extension 01b5d291" in result
        assert "### Extension 01b5f0a4" in result

    def test_should_emit_subsections_in_array_order_when_three_extends_present(
        self,
        tmp_path: Path,
    ) -> None:
        feature_dir = _make_feature_dir_with_one_phase(tmp_path)
        _write_state_yaml(
            feature_dir,
            extends=[
                _example_extend_entry(extend_id="01b5a3c7"),
                _example_extend_entry(extend_id="01b5d291"),
                _example_extend_entry(extend_id="01b5f0a4"),
            ],
        )

        result = release_notes.build(feature_dir)

        idx_first = result.find("### Extension 01b5a3c7")
        idx_second = result.find("### Extension 01b5d291")
        idx_third = result.find("### Extension 01b5f0a4")
        assert 0 <= idx_first < idx_second < idx_third


# ── Append-only: pre-existing content byte-equivalent ────────────────────


class TestAppendOnlyPreservesPriorContent:
    """AC-008: when extends become non-empty, the Phases / Deferred /
    Known-Limitations sections rendered earlier MUST be byte-equivalent
    to the pre-F025 rendering. The Extensions section is purely additive.
    """

    def test_should_render_pre_f025_sections_byte_equivalent_when_extends_added(
        self,
        tmp_path: Path,
    ) -> None:
        # Render without state.yaml (pre-F025 baseline).
        baseline_dir = tmp_path / "F042-baseline"
        baseline_dir.mkdir()
        _write_phase_report(baseline_dir, 1, _minimal_phase_body(1))
        baseline_output = release_notes.build(baseline_dir)

        # Render with state.yaml + one extend (post-F025).
        extended_dir = tmp_path / "F042-baseline"
        # Re-use same dir name so the header line matches byte-for-byte
        # across both invocations; we tear down between renders by using
        # a separate fresh tmp namespace.
        ext_root = tmp_path / "post"
        ext_root.mkdir()
        extended_dir = ext_root / "F042-baseline"
        extended_dir.mkdir()
        _write_phase_report(extended_dir, 1, _minimal_phase_body(1))
        _write_state_yaml(extended_dir, extends=[_example_extend_entry()])
        extended_output = release_notes.build(extended_dir)

        # The baseline content (header + phases + deferred + limitations)
        # must appear verbatim at the START of the extended output. The
        # extensions block is purely appended.
        assert extended_output.startswith(baseline_output)
        # And the appended section is actually present.
        assert "## Extensions" in extended_output[len(baseline_output) :]
