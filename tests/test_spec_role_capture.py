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


class TestFeatureIdAllocation:
    """Phase 2 (start) invokes feature_id allocate-next to create F<NNN>-<slug>
    BEFORE any research, gray-areas, or other directory writes (AC-001, BR-001).
    """

    def test_skill_invokes_allocate_next_via_cli(self, skill_text: str) -> None:
        """AC-001 / BR-001: skill invokes the feature_id.py CLI allocate-next
        subcommand so it works from any project working tree (helpers are
        installed under ~/.claude/scripts/, not the user's project)."""
        assert (
            "python3 ~/.claude/scripts/feature_id.py allocate-next"
            in skill_text
        ), (
            "skill must invoke the feature_id.py CLI form "
            "'python3 ~/.claude/scripts/feature_id.py allocate-next' so it "
            "resolves from any project working directory"
        )

    def test_skill_no_longer_uses_python_import_for_feature_id(
        self, skill_text: str
    ) -> None:
        """The legacy `from scripts.feature_id import` invocation must be
        removed — the helpers are installed under ~/.claude/scripts/, not in
        the user's project, so import-style invocation breaks outside this
        repo."""
        assert "from scripts.feature_id import" not in skill_text, (
            "skill must NOT use 'from scripts.feature_id import' — that path "
            "only resolves inside this checkout. Use the CLI form instead."
        )

    def test_skill_documents_capturing_id_and_path_from_cli_stdout(
        self, skill_text: str
    ) -> None:
        """The CLI prints '<feature_id> <feature_path>' on a single line; the
        skill must document how a runtime conductor parses that output."""
        # Either an awk-style parse, or an explicit description of the
        # space-separated stdout contract.
        lowered = skill_text.lower()
        has_parse_guidance = (
            "first token" in lowered
            or "second token" in lowered
            or "awk" in lowered
            or "space-separated" in lowered
            or "stdout" in lowered
        )
        assert has_parse_guidance, (
            "skill must document how to parse the allocate-next stdout "
            "(first token = feature_id, second token = feature_path)"
        )

    def test_allocation_happens_before_phase_2_5_gray_areas(
        self, skill_text: str
    ) -> None:
        """The F<NNN> allocation must occur at the start of Phase 2 — BEFORE
        Phase 2.5 writes gray-areas.md — so every subdirectory write uses
        the F<NNN>-<slug> path."""
        alloc_idx = skill_text.find(
            "python3 ~/.claude/scripts/feature_id.py allocate-next"
        )
        assert alloc_idx != -1, "allocate-next CLI invocation missing"
        gray_areas_idx = skill_text.find("### Phase 2.5: Gray Area Resolution")
        assert gray_areas_idx != -1, "Phase 2.5 header missing"
        assert alloc_idx < gray_areas_idx, (
            "allocate-next must be invoked BEFORE Phase 2.5 so the gray-areas.md "
            "write lands under F<NNN>-<slug>/, not a slug-only path"
        )

    def test_phase_5_describes_f_nnn_slug_directory(
        self, skill_text: str
    ) -> None:
        """The feature directory follows the F<NNN>-<slug> convention."""
        assert "F<NNN>-<slug>" in skill_text or (
            "F<NNN>-{slug}" in skill_text
        ) or ("F<NNN>" in skill_text and "{slug}" in skill_text), (
            "skill must describe the F<NNN>-<slug> directory naming"
        )

    def test_phase_5_no_longer_uses_slug_only_mkdir(
        self, skill_text: str
    ) -> None:
        """AC-001: replaces the legacy slug-only mkdir with the F-ID allocator."""
        legacy = "Create feature directory:** `.etc_sdlc/features/{slug}/`"
        assert legacy not in skill_text, (
            "skill must no longer create a slug-only feature directory; "
            "it must call feature_id.py allocate-next and use F<NNN>-<slug>"
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
    """Phase 5 writes etc/feature/F<NNN>/spec via the git_tags.py CLI
    (AC-007, BR-007)."""

    def test_phase_5_writes_spec_git_tag(self, skill_text: str) -> None:
        """AC-007: Phase 5 lays down the etc/feature/F<NNN>/spec git tag."""
        assert "etc/feature/F<NNN>/spec" in skill_text, (
            "Phase 5 must describe the etc/feature/F<NNN>/spec git tag"
        )

    def test_phase_5_invokes_write_tag_via_cli(self, skill_text: str) -> None:
        """AC-007: Phase 5 calls the git_tags.py write-tag CLI to create the tag."""
        assert (
            "python3 ~/.claude/scripts/git_tags.py write-tag" in skill_text
        ), (
            "Phase 5 must invoke 'python3 ~/.claude/scripts/git_tags.py write-tag' "
            "so the tag write resolves from any project working directory"
        )

    def test_phase_5_no_longer_uses_python_import_for_git_tags(
        self, skill_text: str
    ) -> None:
        """The legacy `from scripts.git_tags import` form must be removed."""
        assert "from scripts.git_tags import" not in skill_text, (
            "Phase 5 must NOT use 'from scripts.git_tags import' — it only "
            "resolves inside this checkout. Use the CLI form instead."
        )


class TestPhase5ValueHypothesisValidation:
    """Phase 5 validates value-hypothesis.yaml via the value_hypothesis.py CLI
    (AC-004, AC-005)."""

    def test_phase_5_invokes_validate_via_cli(self, skill_text: str) -> None:
        """AC-005: Phase 5 invokes the value_hypothesis.py validate
        subcommand after writing the YAML, so missing fields are caught."""
        assert (
            "python3 ~/.claude/scripts/value_hypothesis.py validate"
            in skill_text
        ), (
            "Phase 5 must invoke 'python3 ~/.claude/scripts/value_hypothesis.py "
            "validate' against the freshly-written value-hypothesis.yaml"
        )

    def test_phase_5_no_longer_uses_python_import_for_value_hypothesis(
        self, skill_text: str
    ) -> None:
        """The legacy import-style invocation must be removed."""
        assert "from scripts.value_hypothesis import" not in skill_text, (
            "Phase 5 must NOT use 'from scripts.value_hypothesis import' — "
            "it only resolves inside this checkout. Use the CLI form."
        )


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
