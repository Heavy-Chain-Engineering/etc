"""Tests for skills/journey/SKILL.md (F017).

Contract tests: SKILL.md must avoid engineering jargon, use plain-English
Socratic prompts via Pattern B, document the 6+1 question set, document
the artifact template, and document the --refine / --list / --from-text
/ --from-voice modes.
"""

from __future__ import annotations

from pathlib import Path

SKILL_PATH = Path(__file__).parent.parent / "skills" / "journey" / "SKILL.md"


def _skill_text() -> str:
    return SKILL_PATH.read_text(encoding="utf-8")


class TestForbiddenVocabulary:
    """AC-04: SKILL.md must NOT use engineering jargon in PROMPTS the SME
    sees. Forbidden phrases (case-insensitive) may appear in operator-
    facing guardrails ("NEVER ask the SME to validate acceptance
    criteria") — that's the skill's job, to TELL the operator what not
    to do. The contract under test is that forbidden phrases don't
    appear inside Pattern B prompt blocks (`**▶ Your answer needed:**`)
    where the SME would actually see them.
    """

    def _extract_pattern_b_prompts(self) -> list[str]:
        """Return all text spans delimited by `**▶ Your answer needed:**`
        markers. Each span is one full prompt body, including the wording
        the SME reads."""
        text = _skill_text()
        marker = "**▶ Your answer needed:**"
        prompts: list[str] = []
        idx = 0
        while True:
            start = text.find(marker, idx)
            if start == -1:
                break
            # End at the next blank-line + closing-fence pattern. Safe
            # heuristic: 500 chars after the marker covers any single prompt.
            end = min(start + 500, len(text))
            prompts.append(text[start:end])
            idx = end
        return prompts

    def _forbidden_phrase_in_any_prompt(self, phrase: str) -> bool:
        return any(
            phrase.lower() in prompt.lower()
            for prompt in self._extract_pattern_b_prompts()
        )

    def test_acceptance_criteria_not_in_any_smefacing_prompt(self) -> None:
        assert not self._forbidden_phrase_in_any_prompt("acceptance criteria")

    def test_stakeholder_not_in_any_smefacing_prompt(self) -> None:
        assert not self._forbidden_phrase_in_any_prompt("stakeholder")

    def test_user_story_not_in_any_smefacing_prompt(self) -> None:
        assert not self._forbidden_phrase_in_any_prompt("user story")

    def test_definition_of_ready_not_in_any_smefacing_prompt(self) -> None:
        assert not self._forbidden_phrase_in_any_prompt("definition of ready")

    def test_skill_md_does_list_forbidden_vocabulary_as_guidance(self) -> None:
        """The forbidden-vocabulary list itself MUST appear in SKILL.md
        as operator guidance, so the contract is documented."""
        text = _skill_text().lower()
        assert "forbidden vocabulary" in text


class TestEncouragedVocabulary:
    """Conversely, the prompts MUST use plain-English journey-shape language."""

    def test_includes_click_or_type_phrasing(self) -> None:
        text = _skill_text().lower()
        assert "click" in text
        assert "type" in text

    def test_includes_failure_mode_phrasing(self) -> None:
        text = _skill_text().lower()
        # "frustrate" / "stuck" / "goes wrong" all qualify
        assert any(w in text for w in ["frustrate", "stuck", "goes wrong"])

    def test_includes_emotion_phrasing(self) -> None:
        text = _skill_text().lower()
        assert any(w in text for w in ["how they feel", "confident", "anxious"])

    def test_includes_tools_systems_phrasing(self) -> None:
        text = _skill_text().lower()
        assert "tools" in text
        assert "systems" in text


class TestSocraticStructure:
    """6+1 Socratic questions asked one at a time via Pattern B."""

    def test_six_mandatory_questions_documented(self) -> None:
        text = _skill_text()
        # Question 1 through Question 6 should appear as section markers
        for n in range(1, 7):
            assert f"Question {n}:" in text, f"Question {n} not documented"

    def test_seventh_question_is_optional(self) -> None:
        text = _skill_text()
        assert "Question 7" in text
        # Must explicitly say "OPTIONAL" or "(Optional)"
        assert "OPTIONAL" in text or "(Optional)" in text or "optional" in text

    def test_pattern_b_visual_marker_used_for_questions(self) -> None:
        """Pattern B uses `---` separator + `**▶ Your answer needed:**` marker."""
        text = _skill_text()
        assert "**▶ Your answer needed:**" in text

    def test_one_at_a_time_discipline_documented(self) -> None:
        text = _skill_text()
        assert "ONE AT A TIME" in text or "one at a time" in text


class TestArtifactTemplate:
    """AC-05: SKILL.md documents the output template (frontmatter + sections)."""

    def test_frontmatter_fields_documented(self) -> None:
        text = _skill_text()
        for field in ["journey_id", "title", "actor", "trigger", "outcome", "status"]:
            assert field in text, f"frontmatter field {field!r} not documented"

    def test_eight_body_sections_documented(self) -> None:
        text = _skill_text()
        sections = [
            "## Actor",
            "## Trigger",
            "## Outcome",
            "## Steps",
            "## Failure modes",
            "## Tools / Systems touched",
            "## Emotional journey",
            "## Open questions",
        ]
        for section in sections:
            assert section in text, f"body section {section!r} not in template"

    def test_status_values_documented(self) -> None:
        text = _skill_text()
        assert "draft" in text
        assert "refined" in text
        assert "locked" in text


class TestModes:
    """AC-03 + AC-06: SKILL.md documents one-liner, --from-text, --from-voice,
    --refine, --list modes."""

    def test_one_liner_invocation_documented(self) -> None:
        text = _skill_text()
        assert '/journey "Counsel executes a contract"' in text or '/journey "' in text

    def test_from_text_flag_documented(self) -> None:
        assert "--from-text" in _skill_text()

    def test_from_voice_flag_is_stubbed_for_v1(self) -> None:
        text = _skill_text()
        assert "--from-voice" in text
        # Stub message hints
        assert "deferred" in text.lower() or "future release" in text.lower()

    def test_refine_mode_documented(self) -> None:
        assert "--refine" in _skill_text()

    def test_list_mode_documented(self) -> None:
        assert "--list" in _skill_text()


class TestAllocatorInvocation:
    """AC-02: SKILL.md invokes scripts/journey_id.py for J-NNN allocation."""

    def test_allocator_invoked_via_bash(self) -> None:
        text = _skill_text()
        assert "journey_id.py" in text
        assert "allocate-next" in text
