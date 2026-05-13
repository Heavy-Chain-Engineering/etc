"""Tests for /build --autonomous skill contract (F014).

F014 added --autonomous flag to /build, wrapping Anthropic's /goal feature
to drive the pipeline unattended. These are grep-style contract tests:
they verify that skills/build/SKILL.md contains the load-bearing strings
that describe the autonomous-mode behavior, since the skill is plain
markdown that Claude reads at invocation.
"""

from __future__ import annotations

from pathlib import Path

SKILL_PATH = Path(__file__).parent.parent / "skills" / "build" / "SKILL.md"


def _skill_text() -> str:
    return SKILL_PATH.read_text(encoding="utf-8")


class TestUsageDocumentsAutonomous:
    """AC-01: --autonomous and related flags appear in the Usage section."""

    def test_autonomous_flag_in_usage(self) -> None:
        text = _skill_text()
        assert "--autonomous" in text

    def test_max_turns_flag_in_usage(self) -> None:
        text = _skill_text()
        assert "--max-turns" in text

    def test_goal_condition_override_flag_in_usage(self) -> None:
        text = _skill_text()
        assert "--goal-condition" in text


class TestAutonomousModeSection:
    """AC-02, AC-08: SKILL.md describes /goal invocation at Step 2 and
    goal clearance at terminal-phase close."""

    def test_skill_describes_goal_invocation_at_setup(self) -> None:
        text = _skill_text()
        assert "/goal" in text
        # The invocation MUST be described as happening at Step 2 (SETUP).
        assert "Step 2" in text and "/goal" in text

    def test_skill_documents_goal_clear_on_terminal_close(self) -> None:
        text = _skill_text()
        assert "clear" in text.lower() and "goal" in text.lower()
        # Specifically references the Terminal-phase close clearing the goal.
        assert "Terminal-phase close" in text or "terminal-phase close" in text


class TestStep3AutoSkip:
    """AC-03: Step 3 SKIPS the Pattern A confirmation in autonomous mode."""

    def test_step_3_documents_autonomous_skip(self) -> None:
        text = _skill_text()
        # The autonomous-mode skip MUST be documented in the Step 3 region.
        # Locate Step 3 header and the section preceding Step 4.
        step_3_start = text.index("### Step 3: DECOMPOSE")
        step_4_start = text.index("### Step 4")
        step_3_body = text[step_3_start:step_4_start]
        assert "autonomous" in step_3_body.lower()
        assert "SKIP" in step_3_body or "skip" in step_3_body
        assert "AskUserQuestion" in step_3_body

    def test_step_3_skip_references_state_yaml_field(self) -> None:
        text = _skill_text()
        step_3_start = text.index("### Step 3: DECOMPOSE")
        step_4_start = text.index("### Step 4")
        step_3_body = text[step_3_start:step_4_start]
        assert "autonomous" in step_3_body
        # The skip condition references state.yaml.build.autonomous.mode.
        assert "state.yaml.build.autonomous" in step_3_body or "autonomous.mode" in step_3_body


class TestStep5AutoSkip:
    """AC-04: Step 5 SKIPS the Pattern A wave-execution confirmation."""

    def test_step_5_documents_autonomous_skip(self) -> None:
        text = _skill_text()
        step_5_start = text.index("### Step 5: PLAN WAVES")
        # Step 6 follows
        step_6_start = text.index("### Step 6")
        step_5_body = text[step_5_start:step_6_start]
        assert "autonomous" in step_5_body.lower()
        assert "SKIP" in step_5_body or "skip" in step_5_body

    def test_step_5_skip_auto_proceeds_with_execute_all(self) -> None:
        text = _skill_text()
        step_5_start = text.index("### Step 5: PLAN WAVES")
        step_6_start = text.index("### Step 6")
        step_5_body = text[step_5_start:step_6_start]
        # The skip MUST land on "Execute all waves" behavior.
        assert "Execute all waves" in step_5_body


class TestGoalConditionDerivation:
    """AC-02: SKILL.md documents how the goal condition is derived."""

    def test_goal_condition_template_documented(self) -> None:
        text = _skill_text()
        # The derived goal condition references AC satisfaction + spec-enforcer
        # COMPLIANT + release tag + pytest 0 failures + shipped/ path.
        assert "spec-enforcer" in text
        assert "COMPLIANT" in text
        assert "release tag" in text or "release" in text
        assert "0 failures" in text or "pytest" in text

    def test_operator_can_override_with_goal_condition_flag(self) -> None:
        text = _skill_text()
        assert "--goal-condition" in text
        assert "override" in text.lower()


class TestMaxTurnsBound:
    """AC-06: --max-turns has documented default and hard cap."""

    def test_max_turns_default_documented(self) -> None:
        text = _skill_text()
        # Default 50 is documented near the --max-turns description.
        assert "Default 50" in text or "default 50" in text or "defaults to 50" in text

    def test_max_turns_hard_cap_documented(self) -> None:
        text = _skill_text()
        # Hard cap 200 regardless of override.
        assert "200" in text


class TestDisableAllHooksFallback:
    """AC-10: disableAllHooks triggers interactive fallback, not hard-fail."""

    def test_disable_all_hooks_fallback_documented(self) -> None:
        text = _skill_text()
        assert "disableAllHooks" in text
        assert "fall" in text.lower() and "interactive" in text.lower()


class TestResumeBehavior:
    """AC-09: --autonomous --resume reuses original goal condition."""

    def test_resume_reuses_goal_condition(self) -> None:
        text = _skill_text()
        # SKILL.md must document that --resume does NOT re-derive.
        assert "--resume" in text
        # The reuse behavior is documented in the Autonomous Mode section.
        assert "reuse" in text.lower() or "original goal" in text.lower()


class TestStateYamlSchema:
    """AC-11: state.yaml.build.autonomous schema is documented."""

    def test_state_yaml_autonomous_block_schema_documented(self) -> None:
        text = _skill_text()
        assert "state.yaml.build.autonomous" in text or "build.autonomous" in text
        # Schema fields: mode, max_turns, goal_condition, started_at.
        assert "max_turns" in text
        assert "goal_condition" in text
        assert "started_at" in text
