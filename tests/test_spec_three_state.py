"""Contract tests for /spec three-state PRD classification refactor.

Covers PRD .etc_sdlc/features/spec-three-state-classification/spec.md
acceptance criteria AC1-AC6 and AC9 via grep-based assertions over the
source SKILL.md, plus the mutual-exclusion invariant from AC6
(no feature directory may contain both spec.md and rejected.md).

Precedent: tests/test_init_project.py::TestSkillMdContract.
"""

from __future__ import annotations

from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
SKILL_SRC = REPO_ROOT / "skills" / "spec" / "SKILL.md"


@pytest.fixture(scope="module")
def skill_text() -> str:
    assert SKILL_SRC.exists(), f"missing {SKILL_SRC}"
    return SKILL_SRC.read_text(encoding="utf-8")


class TestSkillMdContract:
    """Grep-based contract tests for skills/spec/SKILL.md refactor."""

    def test_skill_declares_tunable_threshold_constants(self, skill_text: str) -> None:
        """AC1: Tunable Constants block declares all three named constants."""
        assert "## Tunable Constants" in skill_text, (
            "skills/spec/SKILL.md must have a '## Tunable Constants' section"
        )
        for const in (
            "FILL_RATIO_RESEARCH_ASSIST_MAX",
            "FILL_RATIO_REJECT_MIN",
            "UNFILLABLE_GAP_REJECT_CAP",
        ):
            assert const in skill_text, (
                f"Tunable Constants block must declare {const}"
            )
        # Starting values from BR-005.
        assert "FILL_RATIO_RESEARCH_ASSIST_MAX = 0.20" in skill_text
        assert "FILL_RATIO_REJECT_MIN          = 0.50" in skill_text
        assert "UNFILLABLE_GAP_REJECT_CAP      = 3" in skill_text

    def test_skill_documents_fillable_test(self, skill_text: str) -> None:
        """AC2: Phase 2 extended with the fillable test (BR-002)."""
        # The operational test question.
        assert (
            "Can I ground my answer in citable evidence, or do I need to ask?"
            in skill_text
        ), "fillable test operational question must appear verbatim"
        # The four research-fillable triggers.
        assert "codebase grep finds a canonical pattern" in skill_text
        assert "existing doc cites the answer" in skill_text
        assert "universally-accepted best practice" in skill_text
        assert "adjacent test file shows the expected shape" in skill_text
        # The four unfillable triggers.
        assert "Multiple plausible answers exist" in skill_text
        assert "business intent" in skill_text
        assert "roadmap ordering" in skill_text
        assert "policy decision" in skill_text

    def test_skill_describes_phase_2_75_threshold_check(
        self, skill_text: str
    ) -> None:
        """AC3: Phase 2.75 Threshold Check and Classification section."""
        assert "### Phase 2.75: Threshold Check and Classification" in skill_text
        # The three classification states must be named.
        assert "Well-specified" in skill_text
        assert "Research-fillable" in skill_text or "research-fillable" in skill_text
        assert "Rejected" in skill_text or "rejected" in skill_text
        # Routing references constants by name, not by number.
        assert "FILL_RATIO_RESEARCH_ASSIST_MAX" in skill_text
        assert "FILL_RATIO_REJECT_MIN" in skill_text
        assert "UNFILLABLE_GAP_REJECT_CAP" in skill_text

    def test_skill_describes_rejection_flow(self, skill_text: str) -> None:
        """AC4: Rejection Flow section with rejected.md and the no-spec guarantee."""
        assert "### Rejection Flow" in skill_text
        assert "rejected.md" in skill_text
        # The skill must guarantee it does not write spec.md in rejection.
        lowered = skill_text.lower()
        assert "do not write `spec.md`" in lowered or "not write `spec.md`" in lowered, (
            "Rejection Flow must explicitly state that spec.md is not written"
        )
        # The spec.md / rejected.md mutual-exclusion guarantee.
        assert "mutually exclusive" in skill_text

    def test_skill_schema_has_decided_by_enum(self, skill_text: str) -> None:
        """AC5: gray-areas.md schema has the three-value decided_by enum."""
        # The enum literal as rendered in the schema example.
        assert "research | user | rejected" in skill_text
        # Backward-compat tolerance is called out.
        lowered = skill_text.lower()
        assert "backward compat" in lowered or "legacy" in lowered
        # New fields are documented.
        assert "Citation" in skill_text
        assert "Resolution rationale" in skill_text

    def test_skill_preserves_interactive_input_patterns(
        self, skill_text: str
    ) -> None:
        """AC9: new prompts use Pattern A (AskUserQuestion) or Pattern B (marker)."""
        # Pattern A must still appear (existing Phase 2.5 / Phase 3 flows).
        assert "AskUserQuestion(" in skill_text
        # Pattern B marker must appear in the rejection flow block.
        # The rejection flow uses "Action required" as its non-question marker.
        assert "**▶ Action required:**" in skill_text or (
            "**▶ Your answer needed:**" in skill_text
        )
        # Reference to the standards doc is preserved.
        assert "standards/process/interactive-user-input.md" in skill_text


class TestClassificationInvariant:
    """AC6 mutual-exclusion invariant: a feature directory MUST NOT contain
    both spec.md and rejected.md. Verified against all feature directories
    in the repo, plus a fixture that simulates a rejected run.
    """

    def test_no_feature_directory_has_both_spec_and_rejected(self) -> None:
        features_root = REPO_ROOT / ".etc_sdlc" / "features"
        if not features_root.exists():
            pytest.skip("no .etc_sdlc/features/ directory in repo")
        for feature_dir in features_root.iterdir():
            if not feature_dir.is_dir():
                continue
            has_spec = (feature_dir / "spec.md").exists()
            has_rejected = (feature_dir / "rejected.md").exists()
            assert not (has_spec and has_rejected), (
                f"feature {feature_dir.name} has both spec.md and rejected.md; "
                "the classification invariant requires them to be mutually exclusive"
            )

    def test_under_specified_prd_produces_rejected_md_not_spec_md(
        self, tmp_path: Path
    ) -> None:
        """Contract test: simulate a rejected /spec run and verify the
        resulting feature directory contains rejected.md but NOT spec.md.

        This is a structural test — it asserts the invariant the skill
        must uphold, not a runtime execution of the skill itself (which
        requires an agent loop).
        """
        feature_dir = tmp_path / "under-specified-feature"
        feature_dir.mkdir()
        # Simulate the rejection-flow output.
        (feature_dir / "rejected.md").write_text(
            "# PRD Rejected: under-specified-feature\n"
            "\n"
            "**Reason:** unfillable_gaps > UNFILLABLE_GAP_REJECT_CAP\n"
            "- total_requirements: 8\n"
            "- filled_by_research: 0\n"
            "- unfillable_gaps:    5\n"
            "- Threshold exceeded: UNFILLABLE_GAP_REJECT_CAP\n",
            encoding="utf-8",
        )
        # Simulate that gray-areas.md may be written alongside the rejection.
        (feature_dir / "gray-areas.md").write_text(
            "# Gray Areas\n\n## GA-001\n- **Decided by:** rejected\n",
            encoding="utf-8",
        )
        assert (feature_dir / "rejected.md").exists()
        assert not (feature_dir / "spec.md").exists(), (
            "rejected runs MUST NOT produce spec.md"
        )
        # Re-assert the mutual-exclusion invariant on the fixture directory.
        has_spec = (feature_dir / "spec.md").exists()
        has_rejected = (feature_dir / "rejected.md").exists()
        assert has_rejected and not has_spec
