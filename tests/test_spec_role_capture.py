"""Contract tests for /spec author-role capture + F<NNN> + value-hypothesis + spec tag.

Covers .etc_sdlc/features/metrics-and-release-notes/spec.md acceptance
criteria AC-001, AC-003, AC-004, AC-005, and AC-007 (and the supporting
business rules BR-001, BR-004, BR-005) by grep-based assertions over the
source skills/spec/SKILL.md.

Precedent: tests/test_spec_three_state.py (grep-based skill-contract tests).
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


class TestPhase1RoleCapture:
    """Phase 1 of /spec asks a Pattern B author-role question (AC-003, BR-004)."""

    def test_phase_1_renders_pattern_b_role_question(self, skill_text: str) -> None:
        """AC-003: Phase 1 includes a Pattern B 'What's your role?' question."""
        assert "**▶ Your answer needed:** What's your role?" in skill_text, (
            "Phase 1 must include a Pattern B marker asking the author role"
        )

    def test_phase_1_role_question_lists_all_five_options(
        self, skill_text: str
    ) -> None:
        """AC-003 / BR-004: the role question offers SME, Engineer, PM,
        Designer, and Other (free-form) inline."""
        for option in ("SME", "Engineer", "PM", "Designer", "Other"):
            assert option in skill_text, (
                f"Phase 1 role question must list option {option!r}"
            )
        # The free-form nature of "Other" must be made explicit.
        assert "free-form" in skill_text, (
            "Phase 1 role question must label 'Other' as free-form"
        )

    def test_phase_1_role_question_appears_in_phase_1(
        self, skill_text: str
    ) -> None:
        """The role question lands inside the Phase 1 section, not later."""
        phase_1_start = skill_text.find("### Phase 1: Intent Capture")
        phase_2_start = skill_text.find("### Phase 2:")
        assert phase_1_start != -1, "Phase 1 section header missing"
        assert phase_2_start != -1, "Phase 2 section header missing"
        role_q = skill_text.find("**▶ Your answer needed:** What's your role?")
        assert role_q != -1, "role question missing"
        assert phase_1_start < role_q < phase_2_start, (
            "the role question must appear inside the Phase 1 section"
        )


class TestOtherSanitizationContract:
    """The 'Other' free-form value sanitization contract is documented (security AC-008
    of the PRD security section: 64-char cap, control-character strip)."""

    def test_other_value_documents_64_char_cap(self, skill_text: str) -> None:
        """The skill body must describe the 64-character cap for Other values."""
        assert "64" in skill_text, (
            "the Other free-form sanitization contract must mention the 64-character cap"
        )

    def test_other_value_documents_control_char_strip(
        self, skill_text: str
    ) -> None:
        """The skill body must describe stripping control characters from Other."""
        lowered = skill_text.lower()
        assert "control character" in lowered or "control-character" in lowered, (
            "the Other free-form sanitization contract must mention "
            "stripping control characters"
        )


class TestPhase5FeatureIdAllocation:
    """Phase 5 uses feature_id.allocate_next() to create F<NNN>-<slug> (AC-001, BR-001)."""

    def test_phase_5_invokes_allocate_next(self, skill_text: str) -> None:
        """AC-001 / BR-001: Phase 5 calls scripts/feature_id.allocate_next()."""
        assert "feature_id.allocate_next" in skill_text or (
            "allocate_next(" in skill_text
        ), "Phase 5 must invoke feature_id.allocate_next()"

    def test_phase_5_describes_f_nnn_slug_directory(
        self, skill_text: str
    ) -> None:
        """The feature directory follows the F<NNN>-<slug> convention."""
        assert "F<NNN>-<slug>" in skill_text or (
            "F<NNN>-{slug}" in skill_text
        ) or ("F<NNN>" in skill_text and "{slug}" in skill_text), (
            "Phase 5 must describe the F<NNN>-<slug> directory naming"
        )

    def test_phase_5_no_longer_uses_slug_only_mkdir(
        self, skill_text: str
    ) -> None:
        """AC-001: replaces the legacy slug-only mkdir with the F-ID allocator.

        We verify the legacy literal `Create feature directory:
        .etc_sdlc/features/{slug}/` (slug-only, no F-prefix) is gone.
        """
        legacy = "Create feature directory:** `.etc_sdlc/features/{slug}/`"
        # The exact bolded phrase from the prior skill text. Tolerate either
        # form (with or without the bold-after-colon) but ensure no
        # slug-only path appears as the primary directory creation step.
        assert legacy not in skill_text, (
            "Phase 5 must no longer create a slug-only feature directory; "
            "it must call feature_id.allocate_next() and use F<NNN>-<slug>"
        )


class TestPhase5ValueHypothesisDiscipline:
    """Phase 5 writes value-hypothesis.yaml before spec.md (AC-004, AC-005, BR-005)."""

    def test_phase_5_writes_value_hypothesis_yaml(self, skill_text: str) -> None:
        """AC-004: Phase 5 writes value-hypothesis.yaml in the feature dir."""
        assert "value-hypothesis.yaml" in skill_text, (
            "Phase 5 must write value-hypothesis.yaml"
        )

    def test_phase_5_describes_required_hypothesis_fields(
        self, skill_text: str
    ) -> None:
        """AC-004: required hypothesis fields are enumerated."""
        for field in ("who", "current_cost", "predicted", "how_we_know"):
            assert field in skill_text, (
                f"Phase 5 must enumerate required hypothesis field {field!r}"
            )

    def test_phase_5_prompts_pattern_b_for_missing_fields(
        self, skill_text: str
    ) -> None:
        """AC-005: missing hypothesis fields are filled via Pattern B prompts."""
        # The Phase 5 description must call out Pattern B prompting for
        # missing required fields.
        lowered = skill_text.lower()
        assert "pattern b" in lowered, (
            "Phase 5 must describe Pattern B prompting for missing hypothesis fields"
        )

    def test_spec_md_not_written_until_hypothesis_complete(
        self, skill_text: str
    ) -> None:
        """AC-005: spec.md is NOT written until value-hypothesis.yaml is complete."""
        # Look for an explicit discipline statement linking the two.
        lowered = skill_text.lower()
        assert "spec.md" in lowered and "value-hypothesis.yaml" in lowered, (
            "Phase 5 must mention both spec.md and value-hypothesis.yaml"
        )
        # The discipline must be made textually explicit.
        assert (
            "not written until" in lowered
            or "not be written until" in lowered
            or "before `spec.md`" in lowered
            or "before spec.md" in lowered
            or "complete before" in lowered
        ), (
            "Phase 5 must explicitly state spec.md is not written until "
            "value-hypothesis.yaml is complete"
        )


class TestPhase5SpecGitTag:
    """Phase 5 writes etc/feature/F<NNN>/spec via git_tags.write_tag (AC-007, BR-007)."""

    def test_phase_5_writes_spec_git_tag(self, skill_text: str) -> None:
        """AC-007: Phase 5 lays down the etc/feature/F<NNN>/spec git tag."""
        assert "etc/feature/F<NNN>/spec" in skill_text, (
            "Phase 5 must describe the etc/feature/F<NNN>/spec git tag"
        )

    def test_phase_5_invokes_write_tag(self, skill_text: str) -> None:
        """AC-007: Phase 5 calls git_tags.write_tag() to create the tag."""
        assert "git_tags.write_tag" in skill_text or (
            "write_tag(" in skill_text
        ), "Phase 5 must invoke git_tags.write_tag()"


class TestPhase5StateYamlAuthorRole:
    """Phase 5 appends author_role to state.yaml (BR-004)."""

    def test_phase_5_writes_author_role_to_state_yaml(
        self, skill_text: str
    ) -> None:
        """BR-004: state.yaml records the captured author_role."""
        assert "author_role" in skill_text, (
            "Phase 5 must mention author_role"
        )
        assert "state.yaml" in skill_text, (
            "Phase 5 must write to state.yaml"
        )
        # The two concepts must co-occur in the same vicinity (within 400 chars
        # of each other) so we can be confident the skill describes appending
        # author_role specifically to state.yaml.
        author_role_idx = skill_text.find("author_role")
        # Look for state.yaml within a 400-char window around any author_role.
        window = 400
        found_pair = False
        idx = 0
        while True:
            idx = skill_text.find("author_role", idx)
            if idx == -1:
                break
            window_text = skill_text[
                max(0, idx - window) : idx + window
            ]
            if "state.yaml" in window_text:
                found_pair = True
                break
            idx += 1
        assert found_pair, (
            "author_role and state.yaml must appear together so the skill "
            "is unambiguous about appending author_role to state.yaml"
        )
        assert author_role_idx != -1
