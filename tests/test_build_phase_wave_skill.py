"""Doc-contract tests for F-2026-05-26-phase-wave-decoupling (#35), AC-09.

The phase/wave decoupling MVP gives /build a `feature → phase → wave → task`
execution hierarchy. Step 6 must iterate phase → wave and write the nested
tag form `etc/feature/<id>/build/phase-<P>/wave-<W>/{start,done}`, and the
fused-model stopgap sentence ("Treat the current wave as phase-N ... the
build does not yet maintain an explicit phase->wave mapping") must be gone.

These are grep contracts over the committed source `skills/build/SKILL.md`,
mirroring the style of tests/test_build_stacked_prs.py.
"""

from __future__ import annotations

from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent / "skills" / "build" / "SKILL.md"


def _skill_text() -> str:
    return SKILL.read_text(encoding="utf-8")


class TestPhaseWaveTagContract:
    """AC-09: Step 6 documents nested phase/wave tags."""

    def test_nested_wave_start_tag_documented(self) -> None:
        text = _skill_text()
        assert "build/phase-<P>/wave-<W>/start" in text, (
            "Step 6a must document the nested wave-start tag form"
        )

    def test_nested_wave_done_tag_documented(self) -> None:
        text = _skill_text()
        assert "build/phase-<P>/wave-<W>/done" in text, (
            "Step 6d must document the nested wave-done tag form"
        )

    def test_phase_boundary_tags_documented(self) -> None:
        text = _skill_text()
        assert "build/phase-<P>/start" in text and "build/phase-<P>/done" in text, (
            "Step 6 must document phase-start and phase-done boundary tags"
        )


class TestPhasePlanContract:
    """AC-09: Step 5 computes and persists the phase plan."""

    def test_phases_command_invoked(self) -> None:
        text = _skill_text()
        assert "tasks.py phases" in text, (
            "Step 5 must invoke the `tasks.py phases` command to compute "
            "the phase plan"
        )

    def test_phase_plan_persisted_to_state(self) -> None:
        text = _skill_text()
        assert "phase_plan" in text, (
            "Step 5 must persist the phase plan to state.yaml.build.phase_plan"
        )


class TestStopgapRemoved:
    """AC-09: the fused phase==wave stopgap language is gone."""

    def test_fused_stopgap_sentence_absent(self) -> None:
        text = _skill_text()
        assert "does not yet maintain an explicit phase->wave mapping" not in text, (
            "The fused-model stopgap sentence must be removed — the "
            "phase->wave mapping now exists (compute_phase_plan)."
        )

    def test_treat_the_current_wave_as_phase_n_absent(self) -> None:
        text = _skill_text()
        assert "Treat the current wave as phase-N" not in text, (
            "The 'Treat the current wave as phase-N' stopgap must be removed."
        )
